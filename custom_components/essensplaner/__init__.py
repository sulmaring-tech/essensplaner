"""The Essensplaner integration."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import CONF_HOUSEHOLD_NAME, DOMAIN
from .coordinator import (
    EssensplanerConfigEntry,
    EssensplanerMealplanCoordinator,
    EssensplanerRuntimeData,
    EssensplanerShoppingListCoordinator,
    EssensplanerStatisticsCoordinator,
)
from .panel import async_register_panel
from .services import async_setup_services
from .storage import EssensplanerStore

PLATFORMS: list[Platform] = [Platform.CALENDAR, Platform.SENSOR, Platform.TODO]

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Essensplaner."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: EssensplanerConfigEntry) -> bool:
    """Set up Essensplaner from config entry."""
    store = EssensplanerStore(hass, entry.entry_id)
    await store.async_load()

    device_registry = dr.async_get(hass)
    assert entry.unique_id
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.unique_id)},
        name=entry.data.get(CONF_HOUSEHOLD_NAME, "Essensplaner"),
        entry_type=DeviceEntryType.SERVICE,
        manufacturer="Essensplaner",
        model="Rezept- & Essensplaner",
    )

    mealplan_coordinator = EssensplanerMealplanCoordinator(hass, entry, store)
    shoppinglist_coordinator = EssensplanerShoppingListCoordinator(hass, entry, store)
    statistics_coordinator = EssensplanerStatisticsCoordinator(hass, entry, store)

    await mealplan_coordinator.async_config_entry_first_refresh()
    await shoppinglist_coordinator.async_config_entry_first_refresh()
    await statistics_coordinator.async_config_entry_first_refresh()

    entry.runtime_data = EssensplanerRuntimeData(
        store=store,
        mealplan_coordinator=mealplan_coordinator,
        shoppinglist_coordinator=shoppinglist_coordinator,
        statistics_coordinator=statistics_coordinator,
    )

    await async_register_panel(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EssensplanerConfigEntry) -> bool:
    """Unload config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
