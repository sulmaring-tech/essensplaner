"""Base entity for Essensplaner."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EssensplanerDataUpdateCoordinator


class EssensplanerEntity(CoordinatorEntity[EssensplanerDataUpdateCoordinator]):
    """Base Essensplaner entity."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: EssensplanerDataUpdateCoordinator, key: str
    ) -> None:
        """Initialize entity."""
        super().__init__(coordinator)
        unique_id = coordinator.config_entry.unique_id
        assert unique_id is not None
        self._attr_unique_id = f"{unique_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_id)},
            name=coordinator.config_entry.data.get("household_name", "Essensplaner"),
            manufacturer="Essensplaner",
            model="Rezept- & Essensplaner",
        )
