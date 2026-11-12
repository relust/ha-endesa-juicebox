"""DataUpdateCoordinator for Endesa X JuiceBox with Solar Surplus Regulator."""
from datetime import timedelta
import asyncio
import json
import logging
import struct
import time

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import JuiceBoxAPI
from .const import (
    CONF_AUTO_START_ON_PLUGIN,
    CONF_ENABLE_VICTRON_MQTT,
    CONF_SOLAR_CLOUD_TOLERANCE_MIN,
    CONF_SOLAR_MIN_BATTERY_SOC,
    CONF_USER_MAX_CURRENT,
    CONF_VICTRON_TOPIC,
    DEFAULT_AUTO_START_ON_PLUGIN,
    DEFAULT_SOLAR_CLOUD_TOLERANCE_MIN,
    DEFAULT_SOLAR_MIN_BATTERY_SOC,
    DEFAULT_USER_MAX_CURRENT,
    DEFAULT_VICTRON_TOPIC,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

LEAF_USABLE_KWH = 59.0
CHARGING_EFFICIENCY = 0.90
KM_PER_KWH = 6.2


VICTRON_MODBUS_IP = "192.168.0.135"
VICTRON_MODBUS_PORT = 502


async def async_fetch_victron_direct(host: str = VICTRON_MODBUS_IP, port: int = VICTRON_MODBUS_PORT) -> dict | None:
    """Read PV, SoC, Consumption, Grid and Alarms directly from Cerbo GX via native Modbus TCP."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=0.8
        )
    except Exception as err:
        _LOGGER.debug("Direct Victron Modbus TCP connection failed (%s), using HA fallback", err)
        return None

    try:
        # 1. Read Unit 100: Registers 817..850 (34 regs)
        # 817 = Consumption L1, 820 = Grid L1, 843 = Battery SoC, 850 = PV Power
        req1 = struct.pack(">HHHBBHH", 1, 0, 6, 100, 3, 817, 34)
        writer.write(req1)
        await writer.drain()
        resp1 = await asyncio.wait_for(reader.read(1024), timeout=0.6)

        # 2. Read Unit 227 (MultiPlus-II): Reg 36 (Overload Alarm)
        req2 = struct.pack(">HHHBBHH", 2, 0, 6, 227, 3, 36, 1)
        writer.write(req2)
        await writer.drain()
        resp2 = await asyncio.wait_for(reader.read(1024), timeout=0.6)

        # 3. Read Unit 227 (MultiPlus-II): Reg 64 (Grid Lost Alarm)
        req3 = struct.pack(">HHHBBHH", 3, 0, 6, 227, 3, 64, 1)
        writer.write(req3)
        await writer.drain()
        resp3 = await asyncio.wait_for(reader.read(1024), timeout=0.6)

        if len(resp1) < 77:
            return None

        cons_l1 = float(struct.unpack(">H", resp1[9:11])[0])
        grid_l1 = float(struct.unpack(">h", resp1[15:17])[0])
        soc = float(struct.unpack(">H", resp1[61:63])[0])
        pv = float(struct.unpack(">H", resp1[75:77])[0])
        overload = int(struct.unpack(">H", resp2[9:11])[0]) if len(resp2) >= 11 else 0
        grid_lost = int(struct.unpack(">H", resp3[9:11])[0]) if len(resp3) >= 11 else 0

        return {
            "pv_power_w": pv,
            "cons_power_w": cons_l1,
            "home_bat_soc": soc,
            "grid_raw_w": grid_l1,
            "is_overload_alarm": overload > 0,
            "is_grid_lost": grid_lost > 0,
        }
    except Exception as err:
        _LOGGER.debug("Direct Victron Modbus TCP read error (%s), using HA fallback", err)
        return None
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


class JuiceBoxDataUpdateCoordinator(DataUpdateCoordinator[dict]):
    """Class to manage fetching JuiceBox data, solar surplus regulation, and Cerbo GX sync."""

    def __init__(self, hass: HomeAssistant, api: JuiceBoxAPI, scan_interval_sec: int, entry: ConfigEntry) -> None:
        self.api = api
        self.hass = hass
        self.entry = entry
        self.options = dict(entry.data)
        if entry.options:
            self.options.update(entry.options)

        self.auto_start_on_plugin: bool = bool(
            self.options.get(CONF_AUTO_START_ON_PLUGIN, DEFAULT_AUTO_START_ON_PLUGIN)
        )
        self.victron_mode: int = int(self.options.get("victron_mode", 0))
        self.solar_min_battery_soc: float = float(
            self.options.get(CONF_SOLAR_MIN_BATTERY_SOC, DEFAULT_SOLAR_MIN_BATTERY_SOC)
        )
        self.solar_cloud_tolerance_min: float = float(
            self.options.get(CONF_SOLAR_CLOUD_TOLERANCE_MIN, DEFAULT_SOLAR_CLOUD_TOLERANCE_MIN)
        )
        self.user_max_current: float = float(
            self.options.get(CONF_USER_MAX_CURRENT, DEFAULT_USER_MAX_CURRENT)
        )

        self._disconnected_cycles: int = 0
        self._is_physically_connected: bool | None = None
        self._session_start_energy: float | None = None
        self._session_energy_kwh: float = 0.0

        # Solar surplus regulation state
        self._cloud_timer_start: float | None = None
        self._deficit_timer_start: float | None = None
        self._surplus_start_timer: float | None = None
        self._last_set_current_time: float = 0.0
        self._manual_overload_throttled: bool = False
        self._overload_restore_timer: float | None = None

        # Nissan Leaf adaptive tracking state
        self._leaf_initial_soc: float | None = None
        self._leaf_initial_range: float | None = None
        self._last_leaf_refresh: float = 0.0

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval_sec),
            config_entry=entry,
        )

    def set_auto_start(self, enabled: bool) -> None:
        self.auto_start_on_plugin = enabled

    def set_victron_mode(self, mode: int) -> None:
        self.victron_mode = mode

    def set_solar_min_battery_soc(self, val: float) -> None:
        self.solar_min_battery_soc = val

    def set_solar_cloud_tolerance(self, val: float) -> None:
        self.solar_cloud_tolerance_min = val

    def set_user_max_current(self, val: float) -> None:
        self.user_max_current = val

    def _get_sensor_state(
        self,
        candidate_ids: list[str],
        fallback_pattern: str | None = None,
    ):
        """Find the freshest valid sensor state among candidates or by pattern."""
        now_utc = dt_util.utcnow()
        valid_states = []

        for cid in candidate_ids:
            st = self.hass.states.get(cid)
            if st and st.state not in (None, "unknown", "unavailable", ""):
                age = (now_utc - st.last_updated).total_seconds()
                valid_states.append((age, st))

        if valid_states:
            # Sort by age ascending: freshest sensor wins!
            valid_states.sort(key=lambda x: x[0])
            return valid_states[0][1]

        if fallback_pattern:
            pattern_states = []
            for entity in self.hass.states.async_all("sensor"):
                if fallback_pattern in entity.entity_id and entity.state not in (None, "unknown", "unavailable", ""):
                    age = (now_utc - entity.last_updated).total_seconds()
                    pattern_states.append((age, entity))
            if pattern_states:
                pattern_states.sort(key=lambda x: x[0])
                return pattern_states[0][1]

        return None

    def _get_float_sensor(
        self,
        candidate_ids: list[str],
        default: float = 0.0,
        fallback_pattern: str | None = None,
    ) -> float:
        st = self._get_sensor_state(candidate_ids, fallback_pattern)
        if st is not None:
            try:
                return float(st.state)
            except (ValueError, TypeError):
                pass
        return default

    def _get_str_sensor(
        self,
        candidate_ids: list[str],
        default: str = "",
        fallback_pattern: str | None = None,
    ) -> str:
        st = self._get_sensor_state(candidate_ids, fallback_pattern)
        if st is not None:
            return str(st.state)
        return default

    async def _async_trigger_leaf_refresh(self) -> None:
        now = time.time()
        if now - self._last_leaf_refresh < 60.0:
            _LOGGER.debug("Nissan Leaf refresh skipped (cooldown active)")
            return

        self._last_leaf_refresh = now
        btn_state = self.hass.states.get("button.leaf_update_data")
        if btn_state:
            _LOGGER.info("EV plugged in: triggering Nissan Leaf cloud data refresh")
            try:
                await self.hass.services.async_call(
                    "button",
                    "press",
                    {"entity_id": "button.leaf_update_data"},
                    blocking=False,
                )
            except Exception as err:
                _LOGGER.warning("Could not trigger button.leaf_update_data: %s", err)

    async def _async_update_data(self) -> dict:
        try:
            data = await self.api.fetch_data()
        except Exception as err:
            raise UpdateFailed(f"Error communicating with JuiceBox: {err}") from err

        raw_connected = data.get("connected", False)
        current_total_energy = data.get("energy_kwh", 0.0)

        # Anti-flapping debounce for physical cable disconnection:
        # Require 4 consecutive poll cycles (~12 seconds) of disconnection before treating
        # the EV as physically unplugged. This guarantees that transient Wi-Fi packet drops
        # or brief HTTP timeouts NEVER trigger false Plug & Charge / Auto-Start events!
        if not raw_connected:
            self._disconnected_cycles += 1
            if self._disconnected_cycles >= 4:
                # Genuine physical disconnection confirmed (> 12s)
                self._is_physically_connected = False
                current_connected = False
            else:
                # Within the 12s grace period: preserve previous connection state
                current_connected = True if self._is_physically_connected is not False else False
        else:
            # Reconnected or steadily connected
            self._disconnected_cycles = 0
            current_connected = True

            # Detect genuine fresh plug-in transition (Disconnected for >12s -> Reconnected)
            if self._is_physically_connected is False:
                self._is_physically_connected = True
                self.hass.async_create_task(self._async_trigger_leaf_refresh())

                if self.auto_start_on_plugin:
                    _LOGGER.info(
                        "Confirmed physical EV plug-in detected (after >12s disconnect): auto-starting charging in Manual mode (Plug & Charge)"
                    )
                    # Resetăm automat modul la Manual (0) la fiecare conectare fizică de cablu,
                    # astfel încât mașina să pornească garantat la încărcat fără intervenția utilizatorului!
                    # Dacă utilizatorul dorește surplus solar, poate comuta manual pe Auto din interfață.
                    self.victron_mode = 0
                    try:
                        await self.api.set_current(self.user_max_current)
                        await self.api.set_charging(True)
                        data["allow_start"] = 1
                        data["require_suspension"] = 0
                        data["charging"] = True
                        data["imax_a"] = self.user_max_current
                    except Exception as err:
                        _LOGGER.error("Failed to auto-start charging on plug-in: %s", err)
                    new_opts = dict(self.entry.options) if self.entry.options else dict(self.entry.data)
                    new_opts["victron_mode"] = 0
                    self.hass.config_entries.async_update_entry(self.entry, options=new_opts)
            else:
                self._is_physically_connected = True

        # Update high-level connected state in data dict
        data["connected"] = current_connected

        # Track session energy
        if not current_connected:
            self._session_start_energy = None
            self._session_energy_kwh = 0.0
            self._leaf_initial_soc = None
            self._leaf_initial_range = None
            live_soc = None
            live_range = None
            added_km = 0.0

            # Când mașina este deconectată fizic, ne asigurăm că stația este lăsată gata de pornire (Ready)
            # cu allow_start = 1 și require_suspension = 0, astfel încât firmware-ul nativ Plug & Charge
            # al stației să pornească automat orice mașină la simpla introducere a mufei!
            if data.get("require_suspension", 0) == 1 or data.get("allow_start", 1) == 0:
                try:
                    await self.api.set_charging(True)
                    data["allow_start"] = 1
                    data["require_suspension"] = 0
                except Exception as err:
                    _LOGGER.debug("Could not reset station to ready state while disconnected: %s", err)
        else:
            if self._session_start_energy is None and current_total_energy > 0:
                self._session_start_energy = current_total_energy
            if self._session_start_energy is not None:
                self._session_energy_kwh = max(0.0, current_total_energy - self._session_start_energy)

            # Latch initial SoC and Range
            if self._leaf_initial_soc is None:
                soc_state = self.hass.states.get("sensor.leaf_battery_level")
                if soc_state and soc_state.state not in ("unknown", "unavailable"):
                    try:
                        self._leaf_initial_soc = float(soc_state.state)
                        _LOGGER.info("Latched Nissan Leaf initial SoC: %.1f%%", self._leaf_initial_soc)
                    except ValueError:
                        pass

            if self._leaf_initial_range is None:
                range_state = self.hass.states.get("sensor.leaf_range_ac_off")
                if range_state and range_state.state not in ("unknown", "unavailable"):
                    try:
                        self._leaf_initial_range = float(range_state.state)
                        _LOGGER.info("Latched Nissan Leaf initial Range: %.1f km", self._leaf_initial_range)
                    except ValueError:
                        pass

            base_soc = self._leaf_initial_soc
            if base_soc is None:
                soc_state = self.hass.states.get("sensor.leaf_battery_level")
                try:
                    base_soc = float(soc_state.state) if soc_state else 41.0
                except (ValueError, TypeError):
                    base_soc = 41.0

            base_range = self._leaf_initial_range
            if base_range is None:
                range_state = self.hass.states.get("sensor.leaf_range_ac_off")
                try:
                    base_range = float(range_state.state) if range_state else 151.0
                except (ValueError, TypeError):
                    base_range = 151.0

            added_net_kwh = self._session_energy_kwh * CHARGING_EFFICIENCY
            added_soc_pct = (added_net_kwh / LEAF_USABLE_KWH) * 100.0
            live_soc = min(100.0, round(base_soc + added_soc_pct, 1))

            if base_soc > 0:
                km_per_pct = base_range / base_soc
                live_range = round(live_soc * km_per_pct, 0)
            else:
                live_range = round(live_soc * 3.6, 0)
            added_km = max(0.0, live_range - base_range)

        data["session_energy_kwh"] = round(self._session_energy_kwh, 3)
        data["leaf_live_soc"] = live_soc
        data["leaf_live_range"] = live_range
        data["leaf_added_km"] = added_km

        # --- SOLAR SURPLUS REGULATION (Active only in Auto Mode: victron_mode == 1) ---
        now = time.time()

        # 1. PRIMARY: Direct native Modbus TCP from Cerbo GX (100% independent of other HA integrations)
        victron_direct = await async_fetch_victron_direct()

        if victron_direct is not None:
            pv_power_w = victron_direct["pv_power_w"]
            cons_power_w = victron_direct["cons_power_w"]
            home_bat_soc = victron_direct["home_bat_soc"]
            grid_raw_w = victron_direct["grid_raw_w"]
            direct_overload_alarm = victron_direct["is_overload_alarm"]
            direct_grid_lost = victron_direct["is_grid_lost"]
        else:
            # 2. FALLBACK: Read from HA entities if direct connection is unavailable
            pv_power_w = self._get_float_sensor(
                ["sensor.victron_mqtt_system_0_system_dc_pv_power", "sensor.gx_device_pv_power"],
                default=0.0,
                fallback_pattern="_dc_pv_power",
            )
            cons_power_w = self._get_float_sensor(
                [
                    "sensor.victron_mqtt_system_0_system_consumption_power_l1_2",
                    "sensor.victron_mqtt_system_0_system_consumption_power_l1",
                    "sensor.gx_device_consumption_power_l1",
                ],
                default=0.0,
                fallback_pattern="_consumption_power_l1",
            )
            bat_soc_val = self._get_float_sensor(
                [
                    "sensor.victron_mqtt_battery_512_battery_soc",
                    "sensor.victron_mqtt_system_0_system_dc_battery_soc",
                    "sensor.dyness_l_battery_id_512_charge",
                ],
                default=-1.0,
                fallback_pattern="_battery_soc",
            )
            home_bat_soc = bat_soc_val if bat_soc_val >= 0.0 else None

            grid_raw_w = self._get_float_sensor(
                [
                    "sensor.victron_mqtt_system_0_system_grid_power_l1_2",
                    "sensor.victron_mqtt_system_0_system_grid_power_l1",
                    "sensor.gx_device_grid_power_l1",
                ],
                default=0.0,
                fallback_pattern="_grid_power_l1",
            )
            direct_overload_alarm = None
            direct_grid_lost = None

        # Putere importată din rețea (Grid Power > 0 = import)
        grid_import_w = max(0.0, grid_raw_w)

        # Sarcina reală suportată de invertor (AC Out minus aportul din rețea)
        inverter_load_w = max(0.0, cons_power_w - grid_import_w)

        ev_power_w = data.get("power_w", 0.0)
        current_imax = float(data.get("imax_a", 16.0))
        ev_charging = bool(data.get("charging", False))

        house_other_consumption = max(0.0, cons_power_w - ev_power_w)
        available_surplus_w = max(0.0, pv_power_w - house_other_consumption)
        data["solar_surplus_w"] = round(available_surplus_w, 1)

        victron_status_override = None

        if self.victron_mode == 0:
            self._cloud_timer_start = None
            self._deficit_timer_start = None
            self._surplus_start_timer = None
            
            # --- PROTECȚIE LA SUPRASARCINĂ INVERTOR ÎN MOD MANUAL ---
            # SE APLICĂ EXCLUSIV DACĂ:
            # 1. A picat rețeaua publică (Off-grid / Island mode) sau
            # 2. Invertorul MultiPlus raportează o alarmă reală de Overload (hardware pre-alarm)!
            # Cât timp rețeaua este conectată (On-grid), MultiPlus combină lin invertorul cu rețeaua
            # prin releul de 50A și nu se intervine asupra încărcării!
            if direct_overload_alarm is not None and direct_grid_lost is not None:
                is_grid_lost = direct_grid_lost
                is_overload_alarm = direct_overload_alarm
            else:
                grid_lost_alarm = self._get_str_sensor(
                    [
                        "sensor.victron_mqtt_vebus_276_vebus_inverter_alarm_grid_lost",
                        "sensor.multiplus_ii_48_5000_70_50_id_276_grid_lost_alarm",
                    ],
                    default="no_alarm",
                    fallback_pattern="alarm_grid_lost",
                )
                overload_alarm = self._get_str_sensor(
                    [
                        "sensor.victron_mqtt_vebus_276_vebus_inverter_alarm_overload",
                        "sensor.multiplus_ii_48_5000_70_50_id_276_overload_alarm",
                    ],
                    default="no_alarm",
                    fallback_pattern="alarm_overload",
                )
                sys_state_str = self._get_str_sensor(
                    [
                        "sensor.victron_mqtt_system_0_system_state",
                        "sensor.gx_device_system_state",
                    ],
                    default="",
                    fallback_pattern="system_state",
                )

                is_grid_lost = (
                    grid_lost_alarm in ("warning", "alarm", "on", "true", "1")
                    or sys_state_str == "inverting"
                )
                is_overload_alarm = overload_alarm in ("warning", "alarm", "on", "true", "1")

            if current_connected and ev_charging and (is_overload_alarm or (is_grid_lost and inverter_load_w > 4500.0)):
                self._overload_restore_timer = None
                safe_ev_headroom_w = max(0.0, 4200.0 - house_other_consumption)
                safe_amps = min(self.user_max_current, max(6.0, float(int(safe_ev_headroom_w / 230.0))))
                
                if safe_ev_headroom_w < 1380.0:
                    _LOGGER.warning(
                        "Off-Grid Overload Protection: Rețea căzută și consum casă (%.0fW) depășește limita invertorului. Pauză EV.",
                        house_other_consumption,
                    )
                    try:
                        await self.api.set_charging(False)
                        data["allow_start"] = 0
                        data["require_suspension"] = 1
                        data["charging"] = False
                        self._manual_overload_throttled = True
                    except Exception as err:
                        _LOGGER.error("Failed to pause EV on off-grid overload: %s", err)
                    data["solar_status_text"] = f"Pauză Off-Grid: Casă {house_other_consumption:.0f}W > 4500W"
                    victron_status_override = 4
                else:
                    if abs(safe_amps - current_imax) >= 1.0 and (now - self._last_set_current_time >= 3.0):
                        _LOGGER.warning(
                            "Off-Grid Overload Protection: Sarcină invertor %.0fW. Coborâre dinamică de la %.0fA la %.0fA.",
                            inverter_load_w, current_imax, safe_amps,
                        )
                        try:
                            await self.api.set_current(safe_amps)
                            data["imax_a"] = safe_amps
                            self._last_set_current_time = now
                            self._manual_overload_throttled = True
                        except Exception as err:
                            _LOGGER.error("Failed to throttle EV on off-grid overload: %s", err)
                    data["solar_status_text"] = f"Mod Manual: Limitat la {data.get('imax_a', safe_amps):.0f}A (Protecție Off-Grid)"
            
            # Revenire automată la curentul setat de utilizator când condiția de off-grid/alarmă dispare
            elif self._manual_overload_throttled and current_connected:
                if (not is_grid_lost and not is_overload_alarm) or inverter_load_w <= 3800.0:
                    if self._overload_restore_timer is None:
                        self._overload_restore_timer = now
                    elif now - self._overload_restore_timer >= 10.0:
                        _LOGGER.info(
                            "Off-Grid Overload Protection: Condiții normale restabilite. Revenire la setarea utilizator %.0fA.",
                            self.user_max_current,
                        )
                        try:
                            await self.api.set_current(self.user_max_current)
                            if not ev_charging:
                                await self.api.set_charging(True)
                                data["allow_start"] = 1
                                data["require_suspension"] = 0
                                data["charging"] = True
                            data["imax_a"] = self.user_max_current
                            self._last_set_current_time = now
                            self._manual_overload_throttled = False
                            self._overload_restore_timer = None
                        except Exception as err:
                            _LOGGER.error("Failed to restore user current: %s", err)
                        data["solar_status_text"] = f"Mod Manual: Restabilit la {self.user_max_current:.0f}A"
                    else:
                        rem_r = int(10.0 - (now - self._overload_restore_timer))
                        data["solar_status_text"] = f"Revenire curent în {rem_r}s"
                else:
                    self._overload_restore_timer = None
                    data["solar_status_text"] = f"Mod Manual: Menținut {data.get('imax_a', current_imax):.0f}A"
            else:
                self._manual_overload_throttled = False
                self._overload_restore_timer = None
                data["solar_status_text"] = f"Mod Manual: {self.user_max_current:.0f}A"
        elif not current_connected:
            self._cloud_timer_start = None
            self._deficit_timer_start = None
            self._surplus_start_timer = None
            data["solar_status_text"] = "Mașină deconectată"
        elif home_bat_soc is not None and home_bat_soc < self.solar_min_battery_soc:
            self._cloud_timer_start = None
            self._deficit_timer_start = None
            self._surplus_start_timer = None
            if ev_charging:
                _LOGGER.info(
                    "Solar Auto Mode: Bateria casei (%.1f%%) < pragul de %.0f%%. Pauză încărcare EV pentru a prioritiza casa.",
                    home_bat_soc, self.solar_min_battery_soc,
                )
                try:
                    await self.api.set_charging(False)
                    data["allow_start"] = 0
                    data["require_suspension"] = 1
                    data["charging"] = False
                except Exception as err:
                    _LOGGER.error("Failed to pause EV charging: %s", err)
            data["solar_status_text"] = f"Pauză: Baterie casă {home_bat_soc:.0f}% < {self.solar_min_battery_soc:.0f}% (prioritate casă)"
            victron_status_override = 4
        else:
            raw_amps = available_surplus_w / 230.0
            # Plafonare suplimentară: în Auto mode, niciodată peste capacitatea sigură a invertorului
            safe_auto_headroom_w = max(0.0, 4200.0 - (house_other_consumption - grid_import_w))
            max_inverter_allowed_amps = max(6.0, float(int(safe_auto_headroom_w / 230.0)))
            target_amps = min(self.user_max_current, max_inverter_allowed_amps, max(6.0, float(int(raw_amps))))

            if raw_amps >= 6.0:
                self._cloud_timer_start = None
                self._deficit_timer_start = None

                if not ev_charging:
                    if self._surplus_start_timer is None:
                        self._surplus_start_timer = now
                        data["solar_status_text"] = f"Surplus detectat ({available_surplus_w:.0f}W) - confirmare stabilitate..."
                        victron_status_override = 4
                    elif now - self._surplus_start_timer >= 15.0:
                        _LOGGER.info(
                            "Solar Auto Mode: Surplus stabil (%.0fW -> %.0fA) confirmat 15s. Pornire încărcare!",
                            available_surplus_w, target_amps,
                        )
                        try:
                            await self.api.set_current(target_amps)
                            await self.api.set_charging(True)
                            data["allow_start"] = 1
                            data["require_suspension"] = 0
                            data["charging"] = True
                            data["imax_a"] = target_amps
                            self._last_set_current_time = now
                            self._surplus_start_timer = None
                            data["solar_status_text"] = f"Încărcare solară: {target_amps:.0f}A ({available_surplus_w:.0f}W surplus)"
                            victron_status_override = 2
                        except Exception as err:
                            _LOGGER.error("Failed to start solar charging: %s", err)
                    else:
                        elapsed_st = int(now - self._surplus_start_timer)
                        data["solar_status_text"] = f"Confirmare surplus: {available_surplus_w:.0f}W ({elapsed_st}/15s)"
                        victron_status_override = 4
                else:
                    self._surplus_start_timer = None
                    if abs(target_amps - current_imax) >= 1.0 and (now - self._last_set_current_time >= 10.0):
                        _LOGGER.info(
                            "Solar Auto Mode: Ajustare dinamică curent de la %.0fA la %.0fA (Surplus: %.0fW)",
                            current_imax, target_amps, available_surplus_w,
                        )
                        try:
                            await self.api.set_current(target_amps)
                            data["imax_a"] = target_amps
                            self._last_set_current_time = now
                        except Exception as err:
                            _LOGGER.error("Failed to set dynamic current: %s", err)
                    data["solar_status_text"] = f"Încărcare solară activă: {data.get('imax_a', target_amps):.0f}A ({available_surplus_w:.0f}W surplus)"
                    victron_status_override = 2
            else:
                if not ev_charging:
                    self._surplus_start_timer = None
                    self._deficit_timer_start = None
                    self._cloud_timer_start = None
                    data["solar_status_text"] = f"Așteptare soare: surplus {available_surplus_w:.0f}W < 1380W (min 6A)"
                    victron_status_override = 4
                else:
                    # EV este conectat și încarcă, dar surplusul a scăzut sub pragul minim fizic de 6A (1380W)
                    # Coborâm imediat curentul la 6A pentru a minimiza consumul
                    if current_imax > 6.0 and (now - self._last_set_current_time >= 5.0):
                        _LOGGER.info(
                            "Solar Auto Mode: Surplus scăzut (%.0fW < 1380W). Coborâre la minim 6A.",
                            available_surplus_w,
                        )
                        try:
                            await self.api.set_current(6.0)
                            data["imax_a"] = 6.0
                            self._last_set_current_time = now
                        except Exception as err:
                            _LOGGER.error("Failed to drop current to 6A: %s", err)

                    # CAZUL 1: Consum mare în casă (ex: mașină de spălat, cuptor, plită, boiler)
                    # Consumul casei (fără EV) depășește producția solară -> Deficit net!
                    if available_surplus_w <= 0.0:
                        self._cloud_timer_start = None
                        if self._deficit_timer_start is None:
                            self._deficit_timer_start = now
                        elapsed_deficit = now - self._deficit_timer_start

                        # Dacă deficitul persistă mai mult de 10 secunde (confirmare că este un consumator real),
                        # oprim complet încărcarea mașinii pentru a proteja bateria casei de descărcare!
                        if elapsed_deficit >= 10.0:
                            _LOGGER.info(
                                "Solar Auto Mode: Consum mare în casă (%.0fW > PV %.0fW) timp de %.0fs. Pauză încărcare EV pentru a proteja bateria casei.",
                                house_other_consumption, pv_power_w, elapsed_deficit,
                            )
                            try:
                                await self.api.set_charging(False)
                                data["allow_start"] = 0
                                data["require_suspension"] = 1
                                data["charging"] = False
                                self._deficit_timer_start = None
                            except Exception as err:
                                _LOGGER.error("Failed to pause EV charging on high house consumption: %s", err)
                            data["solar_status_text"] = f"Pauză: Consum casă ({house_other_consumption:.0f}W) > PV ({pv_power_w:.0f}W) (protecție baterie)"
                            victron_status_override = 4
                        else:
                            rem_def = int(10.0 - elapsed_deficit)
                            data["solar_status_text"] = f"Consum mare casă: oprire EV în {rem_def}s dacă persistă"
                            victron_status_override = 2

                    # CAZUL 2: Nor ușor/mediu (există surplus parțial între 100W și 1300W, dar sub 6A)
                    else:
                        self._deficit_timer_start = None
                        tolerance_sec = self.solar_cloud_tolerance_min * 60.0
                        if self._cloud_timer_start is None:
                            self._cloud_timer_start = now
                        elapsed_cloud = now - self._cloud_timer_start

                        if elapsed_cloud >= tolerance_sec:
                            _LOGGER.info(
                                "Solar Auto Mode: Nor prelungit (%.0fs > toleranță %.0fs). Pauză încărcare.",
                                elapsed_cloud, tolerance_sec,
                            )
                            try:
                                await self.api.set_charging(False)
                                data["allow_start"] = 0
                                data["require_suspension"] = 1
                                data["charging"] = False
                                self._cloud_timer_start = None
                            except Exception as err:
                                _LOGGER.error("Failed to pause EV charging on cloud timeout: %s", err)
                            data["solar_status_text"] = "Pauză: Soare insuficient (nor prelungit)"
                            victron_status_override = 4
                        else:
                            rem_sec = int(tolerance_sec - elapsed_cloud)
                            data["solar_status_text"] = f"Nor temporar: menținut 6A (grație încă {rem_sec}s)"
                            victron_status_override = 2

        if self.options.get(CONF_ENABLE_VICTRON_MQTT, True) and "mqtt" in self.hass.config.components:
            await self._async_publish_victron_mqtt(data, victron_status_override)

        return data

    async def _async_publish_victron_mqtt(self, data: dict, victron_status_override: int | None = None) -> None:
        topic_base = self.options.get(CONF_VICTRON_TOPIC, DEFAULT_VICTRON_TOPIC)
        state_topic = f"{topic_base}/state"

        cp_state = data.get("cp_state", 1)
        if cp_state == 1:
            victron_status = 0
        elif data.get("charging"):
            victron_status = 2
        elif self.victron_mode == 1 and victron_status_override is not None:
            victron_status = victron_status_override
        else:
            victron_status = 1

        start_stop = 1 if (data.get("allow_start", 1) == 1 and data.get("require_suspension", 0) == 0) else 0
        current_connected = data.get("connected", False)

        if current_connected and data.get("leaf_live_soc") is not None:
            soc_int = int(round(data["leaf_live_soc"]))
            range_int = int(round(data.get("leaf_live_range", 151.0)))
            custom_name = f"Leaf: {soc_int}% ({range_int}km)"
        else:
            custom_name = "JuiceBox (Nissan Leaf)"

        display_set_current = self.user_max_current if self.victron_mode == 1 else data.get("imax_a", 16.0)

        payload = {
            "Status": victron_status,
            "CustomName": custom_name,
            "Ac": {
                "Power": data.get("power_w", 0.0),
                "L1": {
                    "Power": data.get("power_l1_w", 0.0),
                },
                "L2": {
                    "Power": data.get("power_l2_w", 0.0),
                },
                "L3": {
                    "Power": data.get("power_l3_w", 0.0),
                },
                "Energy": {
                    "Forward": data.get("energy_kwh", 0.0),
                },
            },
            "Session": {
                "Energy": round(data.get("session_energy_kwh", 0.0), 3),
            },
            "Current": data.get("current_l1_a", 0.0),
            "SetCurrent": display_set_current,
            "MaxCurrent": 32.0,
            "StartStop": start_stop,
            "Mode": self.victron_mode,
            "AutoStart": 1 if self.auto_start_on_plugin else 0,
        }

        try:
            await mqtt.async_publish(
                self.hass,
                state_topic,
                json.dumps(payload),
                qos=0,
                retain=True,
            )
            if topic_base != state_topic:
                await mqtt.async_publish(
                    self.hass,
                    topic_base,
                    json.dumps(payload),
                    qos=0,
                    retain=True,
                )
        except Exception as err:
            _LOGGER.error("Failed to publish Victron MQTT state: %s", err)
