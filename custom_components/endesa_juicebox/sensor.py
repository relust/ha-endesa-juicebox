"""Sensor platform for Endesa X JuiceBox EV Charger."""
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import JuiceBoxDataUpdateCoordinator

SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    # Total Active Power (Sum of all phases: P = L1 + L2 + L3)
    SensorEntityDescription(
        key="power",
        translation_key="power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Individual Phase Active Powers (Optional / Diagnostic)
    SensorEntityDescription(
        key="power_l1",
        translation_key="power_l1",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="power_l2",
        translation_key="power_l2",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="power_l3",
        translation_key="power_l3",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    # Phase Currents (Amperes)
    SensorEntityDescription(
        key="current_l1",
        translation_key="current_l1",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="current_l2",
        translation_key="current_l2",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="current_l3",
        translation_key="current_l3",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    # Phase Voltages (Volts)
    SensorEntityDescription(
        key="voltage_l1",
        translation_key="voltage_l1",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="voltage_l2",
        translation_key="voltage_l2",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="voltage_l3",
        translation_key="voltage_l3",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    # Cumulative MID Energy (kWh)
    SensorEntityDescription(
        key="energy",
        translation_key="energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # Session Energy (kWh)
    SensorEntityDescription(
        key="session_energy",
        translation_key="session_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
    ),
    # Nissan Leaf Live Estimated Battery SoC (%)
    SensorEntityDescription(
        key="leaf_live_soc",
        translation_key="leaf_live_soc",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    # Nissan Leaf Live Estimated Range (km)
    SensorEntityDescription(
        key="leaf_live_range",
        translation_key="leaf_live_range",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    # Charging Status (Disconnected / Connected / Charging)
    SensorEntityDescription(
        key="status",
        translation_key="status",
        icon="mdi:ev-station",
    ),
    # Control Pilot Sense Voltage (Volts)
    SensorEntityDescription(
        key="cp_voltage",
        translation_key="cp_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    # Solar Surplus Power (Watts)
    SensorEntityDescription(
        key="solar_surplus",
        translation_key="solar_surplus",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:solar-power-variant",
    ),
    # Solar Auto Status Text
    SensorEntityDescription(
        key="solar_status",
        translation_key="solar_status",
        icon="mdi:solar-power",
    ),
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up JuiceBox sensor entities."""
    coordinator: JuiceBoxDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        JuiceBoxSensor(coordinator, entry, description)
        for description in SENSOR_TYPES
    )


class JuiceBoxSensor(CoordinatorEntity[JuiceBoxDataUpdateCoordinator], SensorEntity):
    """Representation of a JuiceBox sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: JuiceBoxDataUpdateCoordinator,
        entry: ConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.unique_id)},
            name=self._entry.title or "Endesa X JuiceBox",
            manufacturer="Endesa X / Enel X",
            model="JuiceBox Pro 3.01 EU (7.4 kW)",
            sw_version="JB3VUEV01 / JBWeb 0.9.32",
        )

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        key = self.entity_description.key

        if key == "power":
            return data.get("power_w")
        elif key == "power_l1":
            return data.get("power_l1_w")
        elif key == "power_l2":
            return data.get("power_l2_w")
        elif key == "power_l3":
            return data.get("power_l3_w")
        elif key == "current_l1":
            return data.get("current_l1_a")
        elif key == "current_l2":
            return data.get("current_l2_a")
        elif key == "current_l3":
            return data.get("current_l3_a")
        elif key == "voltage_l1":
            return data.get("voltage_l1_v")
        elif key == "voltage_l2":
            return data.get("voltage_l2_v")
        elif key == "voltage_l3":
            return data.get("voltage_l3_v")
        elif key == "energy":
            return data.get("energy_kwh")
        elif key == "session_energy":
            return data.get("session_energy_kwh")
        elif key == "leaf_live_soc":
            return data.get("leaf_live_soc")
        elif key == "leaf_live_range":
            return data.get("leaf_live_range")
        elif key == "cp_voltage":
            return data.get("cp_voltage_v")
        elif key == "status":
            cp_state = data.get("cp_state", 1)
            charging = data.get("charging", False)
            if cp_state == 1:
                return "disconnected"
            elif charging:
                return "charging"
            elif cp_state in (2, 3):
                return "waiting"
            return "unknown"
        elif key == "solar_surplus":
            return data.get("solar_surplus_w", 0.0)
        elif key == "solar_status":
            return data.get("solar_status_text", "Inactiv")

        return data.get(key)
