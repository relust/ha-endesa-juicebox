"""Binary sensor platform for Endesa X JuiceBox."""
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import JuiceBoxDataUpdateCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up JuiceBox binary sensors."""
    coordinator: JuiceBoxDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([JuiceBoxConnectedBinarySensor(coordinator, entry)])


class JuiceBoxConnectedBinarySensor(CoordinatorEntity[JuiceBoxDataUpdateCoordinator], BinarySensorEntity):
    """Binary sensor indicating if the EV is physically connected to the charger."""

    _attr_has_entity_name = True
    _attr_translation_key = "vehicle_connected"
    _attr_device_class = BinarySensorDeviceClass.PLUG

    def __init__(self, coordinator: JuiceBoxDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_vehicle_connected"

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
    def is_on(self) -> bool:
        data = self.coordinator.data or {}
        return data.get("connected", False)
