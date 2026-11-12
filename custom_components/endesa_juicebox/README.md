# Endesa X / Enel X JuiceBox Home Assistant Integration

Custom Home Assistant component for local control and telemetry of **Endesa X / Enel X JuiceBox Pro 3.01 (Waybox EU)** EV chargers.

## Features
- **100% Local Control:** No cloud or external internet connection required.
- **Dynamic Current Slider (6A - 32A):** Instant sub-second current modulation via WebSocket directly in MCU RAM without restarting the station.
- **Start / Stop Switch:** Safely start or pause charging (with vehicle-connection safety guard).
- **Vehicle Connection Detection:** Real-time IEC 61851 Control Pilot sensing (knows when the car is plugged in even when not charging).
- **MID Energy Meter Telemetry:** Live Power (W), Line Current (A), Voltage (V), and Total Energy (kWh) compatible with Home Assistant Energy Dashboard.
- **Victron Cerbo GX Integration:** Automatic two-way MQTT bridge to Victron Venus OS (`mr-manuel/venus-os_dbus-mqtt-ev-charger`) for solar surplus charging.

## Installation
1. Copy the `endesa_juicebox` folder into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. In Home Assistant, go to **Settings** > **Devices & Services** > **Add Integration** and search for **Endesa X JuiceBox**.
4. Enter the charger's IP address and Web Manager password (default: `000000`).
