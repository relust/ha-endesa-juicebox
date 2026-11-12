"""API client for Endesa X / Enel X JuiceBox EV Charger."""
import asyncio
import base64
import json
import logging
import os
import aiohttp

_LOGGER = logging.getLogger(__name__)

class JuiceBoxAPI:
    """JuiceBox API connection."""

    def __init__(self, host: str, password: str, session: aiohttp.ClientSession | None = None) -> None:
        self.host = host
        self.password = password
        self._session = session
        self._cookie_jar = aiohttp.CookieJar(unsafe=True)
        self._own_session = False
        self._last_cp_state: int = 1
        self._last_cp_voltage: float = 12.0

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(cookie_jar=self._cookie_jar)
            self._own_session = True
        return self._session

    async def close(self) -> None:
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()

    async def login(self) -> bool:
        """Authenticate with the station."""
        try:
            session = await self._get_session()
            url = f"http://{self.host}/index.php"
            data = {"password": self.password}
            async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                return resp.status == 200
        except Exception as err:
            _LOGGER.error("Failed to login to JuiceBox at %s: %s", self.host, err)
            return False

    async def fetch_data(self) -> dict:
        """Fetch all live telemetry and modbus registers."""
        session = await self._get_session()
        data = {
            "power_w": 0.0,
            "power_l1_w": 0.0,
            "power_l2_w": 0.0,
            "power_l3_w": 0.0,
            "current_l1_a": 0.0,
            "current_l2_a": 0.0,
            "current_l3_a": 0.0,
            "voltage_l1_v": 230.0,
            "voltage_l2_v": 0.0,
            "voltage_l3_v": 0.0,
            "energy_kwh": 0.0,
            "cp_state": self._last_cp_state,
            "cp_voltage_v": self._last_cp_voltage,
            "imax_a": 16.0,
            "pmax_w": 3000.0,
            "allow_start": 1,
            "require_suspension": 0,
            "connected": False,
            "charging": False,
        }

        # 1. Fetch Total Energy Meter (MID) values for L1, L2, L3
        try:
            url_tem = f"http://{self.host}/admin/task.php?source=tem"
            async with session.get(url_tem, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                if resp.status == 200:
                    tem_json = await resp.json(content_type=None)
                    for item in tem_json.get("task", []):
                        name = item.get("name", "")
                        val_str = item.get("value", "0.0")
                        try:
                            val = float(val_str)
                        except (ValueError, TypeError):
                            val = 0.0

                        # Power in kW -> converted to W
                        if name == "Active power L1":
                            data["power_l1_w"] = round(val * 1000.0, 1)
                        elif name == "Active power L2":
                            data["power_l2_w"] = round(val * 1000.0, 1)
                        elif name == "Active power L3":
                            data["power_l3_w"] = round(val * 1000.0, 1)
                        # Current in Amperes
                        elif name == "Line current L1":
                            data["current_l1_a"] = round(val, 2)
                        elif name == "Line current L2":
                            data["current_l2_a"] = round(val, 2)
                        elif name == "Line current L3":
                            data["current_l3_a"] = round(val, 2)
                        # Voltage in Volts
                        elif name == "Line voltage L1":
                            data["voltage_l1_v"] = round(val, 1)
                        elif name == "Line voltage L2":
                            data["voltage_l2_v"] = round(val, 1)
                        elif name == "Line voltage L3":
                            data["voltage_l3_v"] = round(val, 1)
                        # Total cumulative energy in kWh
                        elif name == "Energy total":
                            data["energy_kwh"] = round(val, 4)

                    # Total active power: P_total = P_L1 + P_L2 + P_L3
                    data["power_w"] = round(data["power_l1_w"] + data["power_l2_w"] + data["power_l3_w"], 1)

                elif resp.status == 302:
                    await self.login()
        except Exception as err:
            _LOGGER.debug("Error fetching TEM data: %s", err)

        # 2. Fetch Control Pilot (SCK1-CONTROLPILOT)
        try:
            url_cp = f"http://{self.host}/admin/modbus.php?section=SCK1-CONTROLPILOT&table=live&column=9"
            async with session.get(url_cp, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                if resp.status == 200:
                    cp_json = await resp.json(content_type=None)
                    for item in cp_json.get("modbus", []):
                        addr = item.get("address")
                        val = item.get("value")
                        if addr == 1159 and val is not None:
                            try:
                                data["cp_state"] = int(val)
                                self._last_cp_state = int(val)
                            except ValueError:
                                pass
                        elif addr == 1432 and val is not None:
                            try:
                                data["cp_voltage_v"] = round(float(val), 2)
                                self._last_cp_voltage = round(float(val), 2)
                            except ValueError:
                                pass
                elif resp.status == 302:
                    await self.login()
        except Exception as err:
            _LOGGER.debug("Error fetching CP data: %s", err)

        # 3. Fetch Load Manager (LOADMNGR - imax)
        try:
            url_lm = f"http://{self.host}/admin/modbus.php?section=LOADMNGR&table=live&column=9"
            async with session.get(url_lm, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                if resp.status == 200:
                    lm_json = await resp.json(content_type=None)
                    for item in lm_json.get("modbus", []):
                        addr = item.get("address")
                        val = item.get("value")
                        if addr == 1500 and val is not None:
                            try:
                                data["imax_a"] = round(float(val), 1)
                            except ValueError:
                                pass
                        elif addr == 1498 and val is not None:
                            try:
                                data["pmax_w"] = round(float(val), 1)
                            except ValueError:
                                pass
        except Exception as err:
            _LOGGER.debug("Error fetching LM data: %s", err)

        # 4. Fetch Product FSM (PRODUCTFSM - start/stop)
        try:
            url_fsm = f"http://{self.host}/admin/modbus.php?section=PRODUCTFSM&table=live&column=9"
            async with session.get(url_fsm, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                if resp.status == 200:
                    fsm_json = await resp.json(content_type=None)
                    for item in fsm_json.get("modbus", []):
                        addr = item.get("address")
                        val = item.get("value")
                        if addr == 1249 and val is not None:
                            data["allow_start"] = int(val)
                        elif addr == 1252 and val is not None:
                            data["require_suspension"] = int(val)
        except Exception as err:
            _LOGGER.debug("Error fetching FSM data: %s", err)

        # High-level states:
        # IEC 61851 Control Pilot state: 1 = Disconnected (A), 2 = Connected/Standby (B), 3 = Charging (C)
        data["connected"] = data["cp_state"] in (2, 3)
        data["charging"] = (data["cp_state"] == 3) or (data["power_w"] > 50.0)

        return data

    async def _send_ws_commands(self, commands: list[dict]) -> bool:
        """Send raw WebSocket commands to the station's FemtoWS daemon on port 443."""
        try:
            reader, writer = await asyncio.open_connection(self.host, 443)
            key = base64.b64encode(os.urandom(16)).decode()
            req = (
                f"GET / HTTP/1.1\r\n"
                f"Host: {self.host}:443\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                f"Sec-WebSocket-Version: 13\r\n\r\n"
            )
            writer.write(req.encode())
            await writer.drain()
            await asyncio.wait_for(reader.read(4096), timeout=3)

            def make_frame(text: str) -> bytes:
                payload = text.encode("utf-8")
                l = len(payload)
                header = bytearray([0x81])
                if l <= 125:
                    header.append(0x80 | l)
                elif l <= 65535:
                    header.append(0x80 | 126)
                    header.extend(l.to_bytes(2, "big"))
                else:
                    header.append(0x80 | 127)
                    header.extend(l.to_bytes(8, "big"))
                mask = os.urandom(4)
                header.extend(mask)
                masked = bytearray(payload[i] ^ mask[i % 4] for i in range(l))
                return bytes(header + masked)

            # Send navigation page registers.php
            writer.write(make_frame(json.dumps({"group": "nav", "page": "registers.php"})))
            await writer.drain()
            await asyncio.sleep(0.1)

            # Send commands
            for cmd in commands:
                writer.write(make_frame(json.dumps(cmd)))
                await writer.drain()
                await asyncio.sleep(0.2)

            writer.close()
            await writer.wait_closed()
            return True
        except Exception as err:
            _LOGGER.error("Failed to send WebSocket command to %s: %s", self.host, err)
            return False

    async def set_current(self, amps: float) -> bool:
        """Change maximum charging current live in RAM (6.0 to 32.0 A) without reboot."""
        amps = max(6.0, min(32.0, float(amps)))
        _LOGGER.info("Setting JuiceBox charging current to %.1f A", amps)
        pmax = min(7400.0, max(3600.0, amps * 240.0))
        cmds = [
            {"group": "modbus", "cmd": "write", "args": [{"table": "live", "address": "1498", "value": f"{pmax:.1f}"}]},
            {"group": "modbus", "cmd": "write", "args": [{"table": "live", "address": "1500", "value": f"{amps:.1f}"}]},
        ]
        return await self._send_ws_commands(cmds)

    async def set_charging(self, enabled: bool) -> bool:
        """Start or stop/suspend charging immediately without reboot."""
        _LOGGER.info("Setting JuiceBox charging state to %s", enabled)
        if enabled:
            cmds = [
                {"group": "modbus", "cmd": "write", "args": [{"table": "live", "address": "1252", "value": "0"}]},
                {"group": "modbus", "cmd": "write", "args": [{"table": "live", "address": "1249", "value": "1"}]},
            ]
        else:
            cmds = [
                {"group": "modbus", "cmd": "write", "args": [{"table": "live", "address": "1252", "value": "1"}]},
                {"group": "modbus", "cmd": "write", "args": [{"table": "live", "address": "1249", "value": "0"}]},
            ]
        return await self._send_ws_commands(cmds)
