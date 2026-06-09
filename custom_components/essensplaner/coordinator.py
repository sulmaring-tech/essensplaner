"""Data update coordinators for Essensplaner."""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    LOGGER,
    UPDATE_INTERVAL_MEALPLAN,
    UPDATE_INTERVAL_SHOPPING,
    UPDATE_INTERVAL_STATISTICS,
)
from .models import MealplanEntry, ShoppingItem, ShoppingList, Statistics
from .storage import EssensplanerStore

@dataclass
class ShoppingListData:
    """Shopping list with items."""

    shopping_list: ShoppingList
    items: list[ShoppingItem]


@dataclass
class EssensplanerRuntimeData:
    """Runtime data for config entry."""

    store: EssensplanerStore
    mealplan_coordinator: EssensplanerMealplanCoordinator
    shoppinglist_coordinator: EssensplanerShoppingListCoordinator
    statistics_coordinator: EssensplanerStatisticsCoordinator


type EssensplanerConfigEntry = ConfigEntry[EssensplanerRuntimeData]


class EssensplanerDataUpdateCoordinator[_DataT](DataUpdateCoordinator[_DataT]):
    """Base coordinator."""

    config_entry: EssensplanerConfigEntry
    _name: str
    _update_interval_seconds: int

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: EssensplanerConfigEntry,
        store: EssensplanerStore,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name=f"Essensplaner {self._name}",
            update_interval=timedelta(seconds=self._update_interval_seconds),
        )
        self.store = store

    @abstractmethod
    async def _async_update_data(self) -> _DataT:
        """Fetch data."""


class EssensplanerMealplanCoordinator(
    EssensplanerDataUpdateCoordinator[dict[str, list[MealplanEntry]]]
):
    """Meal plan coordinator."""

    _name = "mealplan"
    _update_interval_seconds = UPDATE_INTERVAL_MEALPLAN

    async def _async_update_data(self) -> dict[str, list[MealplanEntry]]:
        return self.store.mealplans_by_type()


class EssensplanerShoppingListCoordinator(
    EssensplanerDataUpdateCoordinator[dict[str, ShoppingListData]]
):
    """Shopping list coordinator."""

    _name = "shopping_list"
    _update_interval_seconds = UPDATE_INTERVAL_SHOPPING

    async def _async_update_data(self) -> dict[str, ShoppingListData]:
        result: dict[str, ShoppingListData] = {}
        for shopping_list in self.store.get_shopping_lists():
            items = self.store.get_shopping_items(shopping_list.id)
            result[shopping_list.id] = ShoppingListData(
                shopping_list=shopping_list, items=items
            )
        return result


class EssensplanerStatisticsCoordinator(
    EssensplanerDataUpdateCoordinator[Statistics]
):
    """Statistics coordinator."""

    _name = "statistics"
    _update_interval_seconds = UPDATE_INTERVAL_STATISTICS

    async def _async_update_data(self) -> Statistics:
        return self.store.get_statistics()
