# Victron Venus OS (Cerbo GX) Setup Guide & Enhanced Driver

This folder contains the complete setup guide, configuration template, and **enhanced D-Bus driver** to expose the **Endesa X / Enel X JuiceBox** natively on **Victron Venus OS (Cerbo GX, Ekrano GX, Raspberry Pi)** as an official EV Charging Station device.

---

## Why this Enhanced Driver is Included

If you install the stock upstream `mr-manuel/venus-os_dbus-mqtt-ev-charger` driver, you will encounter several critical issues:
1. **Control Snap-Back (Type Error Crashes):** When touching the current slider or Start/Stop toggle in the Victron Remote Console / Touch 50/70, the upstream driver's text-formatting callbacks crash with `TypeError: must be real number, not str`. Because the D-Bus callback crashes, the Victron UI immediately snaps the slider/switch back to its previous position.
2. **Missing Session Energy & Duration:** The upstream driver does not properly format `/Session/Energy` and `/Session/Time` on D-Bus, resulting in empty or blank (`--`) session metrics in the Victron UI.
3. **Missing Setpoint Topic Propagation:** Changes made in the Victron UI (such as switching from Manual to Auto mode, or adjusting current) were not reliably published to Home Assistant's `/set` topics.

### What our enhanced `dbus-mqtt-ev-charger.py` fixes:
* **Safe Type Casting:** All text formatters (`_a`, `_n`, `_s`, `_w`, `_kwh`) use robust error handling and type casting (`float`/`int`) so D-Bus `SetValue` calls never crash.
* **Instant Bi-Directional Synchronization:** In `_handlechangedvalue`, any change from the Victron screen (`/SetCurrent`, `/Mode`, `/StartStop`, `/AutoStart`) is immediately type-cast and published via MQTT to Home Assistant (`venus-os/evcharger/set/...`).
* **Active Session Stats:** `/Session/Energy` and `/Session/Time` are fully registered with native Victron formatting, displaying live kWh and time directly on your screens and VRM Portal.

---

## Architecture Overview

```
 ┌──────────────────────┐                     ┌──────────────────────────────┐
 │   Endesa X JuiceBox  │ <── HTTP / WS ────> │   Home Assistant             │
 │   192.168.0.173      │                     │   custom_components/         │
 └──────────────────────┘                     │   endesa_juicebox            │
                                              └──────────────┬───────────────┘
                                                             │
                  ┌──────────────────────────────────────────┴─────────────────────────┐
                  │ Direct Modbus TCP (Port 502)             │ Virtual EVCS via MQTT   │
                  ▼                                          ▼                         │
 ┌──────────────────────────────────┐       ┌──────────────────────────────────────────┴┐
 │   Victron Cerbo GX (Venus OS)    │ <───> │  dbus-mqtt-ev-charger.py (this folder)    │
 │   192.168.0.135:502 / 1883       │       │  (Native EVCS UI on Touch 50/70 & VRM)    │
 └──────────────────────────────────┘       └───────────────────────────────────────────┘
```

---

## Installation on Cerbo GX (1-Command Install)

SSH into your Cerbo GX / Venus OS device as `root` and run:

```bash
wget -O - https://raw.githubusercontent.com/relust/ha-endesa-juicebox/main/victron/install.sh | bash
```

This script:
1. Installs the base service environment from `mr-manuel`.
2. Replaces `dbus-mqtt-ev-charger.py` with our enhanced, bug-fixed version from this repository.
3. Sets up the configuration template at `/data/etc/dbus-mqtt-ev-charger/config.ini`.
4. Automatically restarts the service.

---

## Configuration

Edit `/data/etc/dbus-mqtt-ev-charger/config.ini`:

```bash
nano /data/etc/dbus-mqtt-ev-charger/config.ini
```

Set your Home Assistant MQTT broker IP and credentials (see [`config.sample.ini`](config.sample.ini)):

```ini
[MQTT]
broker_address = 192.168.0.143
broker_port = 1883
username = homeassistant
password = your_mosquitto_password
topic = venus-os/evcharger
```

Restart the service:
```bash
/data/etc/dbus-mqtt-ev-charger/restart.sh
```

---

## Verification

Check the driver logs:
```bash
tail -f /var/log/dbus-mqtt-ev-charger/current
```

The charger will appear immediately in your **Remote Console**, **Touch 50/70**, and **VRM Portal** under the native **EV Charging Station** menu with full bi-directional control, live session metrics, and real-time solar surplus charging!
