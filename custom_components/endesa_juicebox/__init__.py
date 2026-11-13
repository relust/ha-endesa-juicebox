"""The Endesa X JuiceBox EV Charger integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL, Platform
from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import JuiceBoxAPI
from .const import (
    CONF_AUTO_START_ON_PLUGIN,
    CONF_ENABLE_VICTRON_MQTT,
    CONF_SOLAR_CLOUD_TOLERANCE_MIN,
    CONF_SOLAR_MIN_BATTERY_SOC,
    CONF_USER_MAX_CURRENT,
    CONF_VICTRON_TOPIC,
    DEFAULT_AUTO_START_ON_PLUGIN,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SOLAR_CLOUD_TOLERANCE_MIN,
    DEFAULT_SOLAR_MIN_BATTERY_SOC,
    DEFAULT_USER_MAX_CURRENT,
    DEFAULT_VICTRON_TOPIC,
    DOMAIN,
)
from .coordinator import JuiceBoxDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SWITCH,
]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    host = entry.data[CONF_HOST]
    password = entry.data[CONF_PASSWORD]
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))

    session = async_get_clientsession(hass)
    api = JuiceBoxAPI(host=host, password=password, session=session)

    await api.login()

    coordinator = JuiceBoxDataUpdateCoordinator(
        hass=hass,
        api=api,
        scan_interval_sec=scan_interval,
        entry=entry,
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "unsubs": [],
    }

    enable_victron = entry.options.get(
        CONF_ENABLE_VICTRON_MQTT,
        entry.data.get(CONF_ENABLE_VICTRON_MQTT, True),
    )
    if enable_victron:
        topic_base = entry.options.get(CONF_VICTRON_TOPIC, entry.data.get(CONF_VICTRON_TOPIC, DEFAULT_VICTRON_TOPIC))
        
        async def _handle_victron_set_current(msg):
            try:
                val = float(msg.payload)
                _LOGGER.info("Victron Cerbo GX requested current: %.1f A", val)
                coordinator.set_user_max_current(val)
                new_opts = dict(entry.options)
                new_opts[CONF_USER_MAX_CURRENT] = val
                hass.config_entries.async_update_entry(entry, options=new_opts)
                if coordinator.victron_mode == 0:
                    if coordinator.data:
                        coordinator.data["imax_a"] = val
                    await api.set_current(val)
                await coordinator.async_request_refresh()
            except ValueError:
                pass

        async def _handle_victron_mode(msg):
            try:
                val = int(msg.payload)
                _LOGGER.info("Victron Cerbo GX requested Mode: %d", val)
                coordinator.set_victron_mode(val)
                new_opts = dict(entry.options)
                new_opts["victron_mode"] = val
                hass.config_entries.async_update_entry(entry, options=new_opts)
                await coordinator.async_request_refresh()
            except ValueError:
                pass

        async def _handle_victron_autostart(msg):
            try:
                val = int(msg.payload)
                _LOGGER.info("Victron Cerbo GX requested AutoStart: %d", val)
                coordinator.set_auto_start(val == 1)
                new_opts = dict(entry.options)
                new_opts[CONF_AUTO_START_ON_PLUGIN] = (val == 1)
                hass.config_entries.async_update_entry(entry, options=new_opts)
                await coordinator.async_request_refresh()
            except ValueError:
                pass

        async def _handle_victron_start_stop(msg):
            try:
                val = int(msg.payload)
                _LOGGER.info("Victron Cerbo GX requested StartStop: %d", val)
                if coordinator.data:
                    coordinator.data["allow_start"] = 1 if (val == 1) else 0
                    coordinator.data["require_suspension"] = 0 if (val == 1) else 1
                    coordinator.data["charging"] = (val == 1)
                await api.set_charging(val == 1)
                await coordinator.async_request_refresh()
            except ValueError:
                pass

        async def _handle_victron_max_current(msg):
            try:
                val = float(msg.payload)
                _LOGGER.info("Victron Cerbo GX requested MaxCurrent: %.1f A", val)
                coordinator.set_victron_max_current(val)
                new_opts = dict(entry.options)
                new_opts["victron_max_current"] = val
                hass.config_entries.async_update_entry(entry, options=new_opts)
                await coordinator.async_request_refresh()
            except ValueError:
                pass

        try:
            unsub1 = await mqtt.async_subscribe(hass, f"{topic_base}/set/SetCurrent", _handle_victron_set_current)
            unsub2 = await mqtt.async_subscribe(hass, f"{topic_base}/set/StartStop", _handle_victron_start_stop)
            unsub3 = await mqtt.async_subscribe(hass, f"{topic_base}/set/Mode", _handle_victron_mode)
            unsub4 = await mqtt.async_subscribe(hass, f"{topic_base}/set/AutoStart", _handle_victron_autostart)
            unsub5 = await mqtt.async_subscribe(hass, f"{topic_base}/set/MaxCurrent", _handle_victron_max_current)
            hass.data[DOMAIN][entry.entry_id]["unsubs"].extend([unsub1, unsub2, unsub3, unsub4, unsub5])
            _LOGGER.info("Subscribed to Victron MQTT commands on %s/set/#", topic_base)
        except Exception as err:
            _LOGGER.warning("Could not subscribe to Victron MQTT topics: %s", err)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id, {})
        for unsub in data.get("unsubs", []):
            unsub()
        api = data.get("api")
        if api:
            await api.close()
    return unload_ok

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options updates in-place without tearing down platforms or disconnecting API."""
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not data or "coordinator" not in data:
        await hass.config_entries.async_reload(entry.entry_id)
        return

    coordinator: JuiceBoxDataUpdateCoordinator = data["coordinator"]
    coordinator.options = dict(entry.data)
    if entry.options:
        coordinator.options.update(entry.options)

    coordinator.auto_start_on_plugin = bool(
        coordinator.options.get(CONF_AUTO_START_ON_PLUGIN, DEFAULT_AUTO_START_ON_PLUGIN)
    )
    coordinator.victron_mode = int(coordinator.options.get("victron_mode", 0))
    coordinator.solar_min_battery_soc = float(
        coordinator.options.get(CONF_SOLAR_MIN_BATTERY_SOC, DEFAULT_SOLAR_MIN_BATTERY_SOC)
    )
    coordinator.solar_cloud_tolerance_min = float(
        coordinator.options.get(CONF_SOLAR_CLOUD_TOLERANCE_MIN, DEFAULT_SOLAR_CLOUD_TOLERANCE_MIN)
    )
    coordinator.user_max_current = float(
        coordinator.options.get(CONF_USER_MAX_CURRENT, DEFAULT_USER_MAX_CURRENT)
    )
    await coordinator.async_request_refresh()
