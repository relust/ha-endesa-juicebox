# Victron Venus OS (Cerbo GX) Setup Guide

This folder contains the setup guide and configuration template to expose the **Endesa X / Enel X JuiceBox** natively on **Victron Venus OS (Cerbo GX, Ekrano GX, Raspberry Pi)** as an official EV Charging Station device on D-Bus.

---

## Architecture

Home Assistant bridges the JuiceBox charger to Victron Venus OS via MQTT:
1. The **Endesa X JuiceBox** integration in Home Assistant connects to the charger over HTTP/WebSocket.
2. It publishes standard Victron EVCS telemetry to `venus-os/evcharger` on your Home Assistant MQTT broker (Mosquitto).
3. The `dbus-mqtt-ev-charger` driver on Cerbo GX subscribes to this topic and registers the charger as a native service on D-Bus (`com.victronenergy.evcharger.mqtt_evcharger_11`).
4. **Bi-directional Control:**
   - Switching between **Manual Mode (0)** and **Auto Mode (1)** in the Victron Remote Console / GUI-v2 immediately updates the Home Assistant solar regulator.
   - Adjusting current on the Victron slider immediately commands the JuiceBox via WebSocket in sub-seconds.
   - Live Session Energy (`/Session/Energy`) and Duration (`/Session/Time`) are continuously synchronized.

---

## Step 1: Install the Driver on Cerbo GX

SSH into your Cerbo GX / Venus OS device as `root`:

```bash
wget -O - https://raw.githubusercontent.com/mr-manuel/venus-os_dbus-mqtt-ev-charger/master/setup.sh | bash
```

---

## Step 2: Configure MQTT Connection

1. Copy the sample configuration:
   ```bash
   cp /data/etc/dbus-mqtt-ev-charger/config.sample.ini /data/etc/dbus-mqtt-ev-charger/config.ini
   nano /data/etc/dbus-mqtt-ev-charger/config.ini
   ```

2. Set the Home Assistant MQTT broker parameters (see [`config.sample.ini`](config.sample.ini)):
   ```ini
   [MQTT]
   broker_address = <HOME_ASSISTANT_IP>
   broker_port = 1883
   username = <MQTT_USERNAME>
   password = <MQTT_PASSWORD>
   topic = venus-os/evcharger
   ```

3. Restart the driver service:
   ```bash
   /data/etc/dbus-mqtt-ev-charger/restart.sh
   ```

---

## Step 3: Verify D-Bus & Remote Console

Check the live service logs on Cerbo GX:
```bash
tail -f /var/log/dbus-mqtt-ev-charger/current
```

The charger will now appear in your **Remote Console**, **Touch 50/70**, and **VRM Portal** under the native **EV Charging Station** menu with full power flow visualization!
