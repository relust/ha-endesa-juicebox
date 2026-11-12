"""Constants for the Endesa X JuiceBox integration."""

DOMAIN = "endesa_juicebox"
DEFAULT_NAME = "JuiceBox"
DEFAULT_PASSWORD = "000000"
DEFAULT_SCAN_INTERVAL = 3

CONF_ENABLE_VICTRON_MQTT = "enable_victron_mqtt"
CONF_VICTRON_TOPIC = "victron_topic"
DEFAULT_VICTRON_TOPIC = "venus-os/evcharger"

CONF_AUTO_START_ON_PLUGIN = "auto_start_on_plugin"
DEFAULT_AUTO_START_ON_PLUGIN = False

CONF_SOLAR_MIN_BATTERY_SOC = "solar_min_battery_soc"
DEFAULT_SOLAR_MIN_BATTERY_SOC = 80.0

CONF_SOLAR_CLOUD_TOLERANCE_MIN = "solar_cloud_tolerance_min"
DEFAULT_SOLAR_CLOUD_TOLERANCE_MIN = 3.0

CONF_USER_MAX_CURRENT = "user_max_current"
DEFAULT_USER_MAX_CURRENT = 16.0
