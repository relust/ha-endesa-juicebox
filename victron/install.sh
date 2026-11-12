#!/bin/bash
# Installer script for Endesa X JuiceBox Victron Cerbo GX D-Bus driver
# Run on Cerbo GX as root:
# curl -sSL https://raw.githubusercontent.com/relust/ha-endesa-juicebox/main/victron/install.sh | bash

set -e

DRIVER_DIR="/data/etc/dbus-mqtt-ev-charger"
REPO_URL="https://raw.githubusercontent.com/relust/ha-endesa-juicebox/main/victron"

echo "=== Installing Endesa X JuiceBox Victron D-Bus Driver ==="

# 1. If base mr-manuel package is not installed yet, install it to set up service daemons
if [ ! -d "$DRIVER_DIR/service" ]; then
    echo "Installing base dbus-mqtt-ev-charger service..."
    wget -O /tmp/download_dbus-mqtt-ev-charger.sh https://raw.githubusercontent.com/mr-manuel/venus-os_dbus-mqtt-ev-charger/master/download.sh
    bash /tmp/download_dbus-mqtt-ev-charger.sh
fi

# 2. Deploy our enhanced dbus-mqtt-ev-charger.py with safe D-Bus setpoint handling & session sync
echo "Deploying enhanced dbus-mqtt-ev-charger.py with safe type casting & session sync..."
wget -O "$DRIVER_DIR/dbus-mqtt-ev-charger.py" "$REPO_URL/dbus-mqtt-ev-charger.py"
chmod +x "$DRIVER_DIR/dbus-mqtt-ev-charger.py"

# 3. Create config.ini if it doesn't exist
if [ ! -f "$DRIVER_DIR/config.ini" ]; then
    echo "Creating config.ini template..."
    wget -O "$DRIVER_DIR/config.ini" "$REPO_URL/config.sample.ini"
    echo "IMPORTANT: Please edit $DRIVER_DIR/config.ini to configure your Home Assistant MQTT broker IP and credentials!"
fi

# 4. Restart service
if [ -f "$DRIVER_DIR/restart.sh" ]; then
    echo "Restarting service..."
    bash "$DRIVER_DIR/restart.sh"
fi

echo "=== Installation complete! ==="
