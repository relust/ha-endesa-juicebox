"""Number platform for Endesa X JuiceBox (Amperage slider and Solar settings)."""
import asyncio
import logging
from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_SOLAR_CLOUD_TOLERANCE_MIN,
    CONF_SOLAR_MIN_BATTERY_SOC,
    CONF_USER_MAX_CURRENT,
    DEFAULT_SOLAR_CLOUD_TOLERANCE_MIN,
    DEFAULT_SOLAR_MIN_BATTERY_SOC,
    DEFAULT_USER_MAX_CURRENT,
    DOMAIN,
)
from .coordinator import JuiceBoxDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up JuiceBox number entities."""
    coordinator: JuiceBoxDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([
        JuiceBoxCurrentNumber(coordinator, entry),
        JuiceBoxSolarMinSocNumber(coordinator, entry),
        JuiceBoxSolarToleranceNumber(coordinator, entry),
    ])


class JuiceBoxCurrentNumber(CoordinatorEntity[JuiceBoxDataUpdateCoordinator], NumberEntity):
    """Slider to change max charging current in real time without restart."""

    _attr_has_entity_name = True
    _attr_translation_key = "charging_current"
    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_native_min_value = 6.0
    _attr_native_max_value = 32.0
    _attr_native_step = 1.0
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, coordinator: JuiceBoxDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_charging_current"

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
    def native_value(self) -> float:
        return float(self.coordinator.user_max_current)

    async def async_set_native_value(self, value: float) -> None:
        val = round(value, 1)
        _LOGGER.info("Setting JuiceBox current limit to %.1f A", val)
        self.coordinator.set_user_max_current(val)
        new_opts = dict(self._entry.options)
        new_opts[CONF_USER_MAX_CURRENT] = val
        self.hass.config_entries.async_update_entry(self._entry, options=new_opts)
        
        if self.coordinator.victron_mode == 0:
            success = await self.coordinator.api.set_current(val)
            if success and self.coordinator.data:
                self.coordinator.data["imax_a"] = val
        
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()


class JuiceBoxSolarMinSocNumber(CoordinatorEntity[JuiceBoxDataUpdateCoordinator], NumberEntity):
    """Slider to set minimum house battery SoC required before EV charges from solar."""

    _attr_has_entity_name = True
    _attr_translation_key = "solar_min_battery_soc"
    _attr_device_class = NumberDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = 20.0
    _attr_native_max_value = 100.0
    _attr_native_step = 5.0
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:battery-charging-high"

    def __init__(self, coordinator: JuiceBoxDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_solar_min_battery_soc"

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
    def native_value(self) -> float:
        return float(self.coordinator.solar_min_battery_soc)

    async def async_set_native_value(self, value: float) -> None:
        val = round(value, 1)
        _LOGGER.info("Setting Solar Min House Battery SoC to %.0f%%", val)
        self.coordinator.set_solar_min_battery_soc(val)
        new_opts = dict(self._entry.options)
        new_opts[CONF_SOLAR_MIN_BATTERY_SOC] = val
        self.hass.config_entries.async_update_entry(self._entry, options=new_opts)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()


class JuiceBoxSolarToleranceNumber(CoordinatorEntity[JuiceBoxDataUpdateCoordinator], NumberEntity):
    """Slider to set cloud tolerance grace time in minutes before pausing charging."""

    _attr_has_entity_name = True
    _attr_translation_key = "solar_cloud_tolerance"
    _attr_native_unit_of_measurement = "min"
    _attr_native_min_value = 1.0
    _attr_native_max_value = 15.0
    _attr_native_step = 1.0
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:weather-partly-cloudy"

    def __init__(self, coordinator: JuiceBoxDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_solar_cloud_tolerance"

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
    def native_value(self) -> float:
        return float(self.coordinator.solar_cloud_tolerance_min)

    async def async_set_native_value(self, value: float) -> None:
        val = round(value, 0)
        _LOGGER.info("Setting Solar Cloud Tolerance to %.0f min", val)
        self.coordinator.set_solar_cloud_tolerance(val)
        new_opts = dict(self._entry.options)
        new_opts[CONF_SOLAR_CLOUD_TOLERANCE_MIN] = val
        self.hass.config_entries.async_update_entry(self._entry, options=new_opts)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
