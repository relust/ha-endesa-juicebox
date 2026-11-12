"""Switch platform for Endesa X JuiceBox."""
import logging
from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_AUTO_START_ON_PLUGIN, DEFAULT_AUTO_START_ON_PLUGIN, DOMAIN
from .coordinator import JuiceBoxDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up JuiceBox switch entities."""
    coordinator: JuiceBoxDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([
        JuiceBoxChargingSwitch(coordinator, entry),
        JuiceBoxAutoStartSwitch(coordinator, entry),
    ])


class JuiceBoxChargingSwitch(CoordinatorEntity[JuiceBoxDataUpdateCoordinator], SwitchEntity):
    """Switch to start or pause/stop EV charging in real time."""

    _attr_has_entity_name = True
    _attr_translation_key = "charging"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:power"

    def __init__(self, coordinator: JuiceBoxDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_charging"

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
        allow_start = data.get("allow_start", 1)
        require_suspension = data.get("require_suspension", 0)
        return (allow_start == 1) and (require_suspension == 0)

    async def async_turn_on(self, **kwargs) -> None:
        """Start charging (requires vehicle to be connected)."""
        data = self.coordinator.data or {}
        if not data.get("connected", False):
            raise HomeAssistantError("Cannot start charging: No electric vehicle is physically connected to the station!")

        _LOGGER.info("Starting JuiceBox charging")
        success = await self.coordinator.api.set_charging(True)
        if success:
            if self.coordinator.data:
                self.coordinator.data["allow_start"] = 1
                self.coordinator.data["require_suspension"] = 0
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Pause or stop charging."""
        _LOGGER.info("Pausing/Stopping JuiceBox charging")
        success = await self.coordinator.api.set_charging(False)
        if success:
            if self.coordinator.data:
                self.coordinator.data["allow_start"] = 0
                self.coordinator.data["require_suspension"] = 1
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()


class JuiceBoxAutoStartSwitch(CoordinatorEntity[JuiceBoxDataUpdateCoordinator], SwitchEntity):
    """Switch to toggle automatic start on cable plug-in (Plug & Charge)."""

    _attr_has_entity_name = True
    _attr_translation_key = "auto_start_on_plugin"
    _attr_icon = "mdi:ev-plug-type2"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: JuiceBoxDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_auto_start_on_plugin"

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
        return bool(self.coordinator.auto_start_on_plugin)

    async def async_turn_on(self, **kwargs) -> None:
        """Enable auto-start on plug-in."""
        _LOGGER.info("Enabling JuiceBox Auto-Start on plug-in")
        self.coordinator.set_auto_start(True)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Disable auto-start on plug-in."""
        _LOGGER.info("Disabling JuiceBox Auto-Start on plug-in")
        self.coordinator.set_auto_start(False)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
