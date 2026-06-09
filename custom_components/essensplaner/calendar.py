"""Calendar platform for Essensplaner."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import MEALPLAN_ENTRY_TYPES, MealplanEntryType
from .coordinator import EssensplanerConfigEntry, EssensplanerMealplanCoordinator
from .entity import EssensplanerEntity
from .meal_times import mealplan_to_datetimes
from .models import MealplanEntry, Recipe

PARALLEL_UPDATES = 0


def _get_event_from_mealplan(
    mealplan: MealplanEntry,
    recipe: Recipe | None,
    options: dict,
) -> CalendarEvent:
    """Create timed calendar event from meal plan."""
    name = mealplan.title or "Kein Rezept"
    description = mealplan.description
    if recipe:
        name = recipe.name
        description = recipe.description
    start, end = mealplan_to_datetimes(mealplan, options)
    return CalendarEvent(
        start=start,
        end=end,
        summary=name,
        description=description,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EssensplanerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up calendar entities."""
    coordinator = entry.runtime_data.mealplan_coordinator
    async_add_entities(
        EssensplanerMealplanCalendarEntity(coordinator, entry_type)
        for entry_type in MEALPLAN_ENTRY_TYPES
    )


class EssensplanerMealplanCalendarEntity(EssensplanerEntity, CalendarEntity):
    """Calendar entity for a meal type."""

    def __init__(
        self,
        coordinator: EssensplanerMealplanCoordinator,
        entry_type: MealplanEntryType,
    ) -> None:
        """Initialize calendar entity."""
        super().__init__(coordinator, entry_type.value)
        self._entry_type = entry_type.value
        self._attr_translation_key = entry_type.value

    @property
    def _options(self) -> dict:
        """Return config entry options for meal times."""
        return self.coordinator.config_entry.options

    def _get_recipe(self, recipe_id: str | None) -> Recipe | None:
        """Resolve recipe for meal plan entry."""
        if not recipe_id:
            return None
        return self.coordinator.store.data.recipes.get(recipe_id)

    @property
    def event(self) -> CalendarEvent | None:
        """Return next upcoming event."""
        mealplans = self.coordinator.data.get(self._entry_type, [])
        now = dt_util.now()
        upcoming: list[tuple[datetime, MealplanEntry]] = []
        for mealplan in mealplans:
            start, end = mealplan_to_datetimes(mealplan, self._options)
            if end >= now:
                upcoming.append((start, mealplan))
        if not upcoming:
            return None
        _, plan = min(upcoming, key=lambda item: item[0])
        return _get_event_from_mealplan(plan, self._get_recipe(plan.recipe_id), self._options)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return events in range."""
        mealplans = self.coordinator.store.get_mealplans(
            start_date.date(), end_date.date()
        )
        events: list[CalendarEvent] = []
        for mealplan in mealplans:
            if mealplan.entry_type != self._entry_type:
                continue
            event_start, event_end = mealplan_to_datetimes(mealplan, self._options)
            if event_end < start_date or event_start > end_date:
                continue
            recipe = self._get_recipe(mealplan.recipe_id)
            events.append(_get_event_from_mealplan(mealplan, recipe, self._options))
        return events
