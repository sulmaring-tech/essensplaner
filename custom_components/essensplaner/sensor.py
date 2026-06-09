"""Sensor platform for Essensplaner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from homeassistant.util import dt as dt_util

from .const import DASHBOARD_MEAL_TYPES, MEAL_TYPE_ICONS, MEAL_TYPE_LABELS
from .coordinator import (
    EssensplanerConfigEntry,
    EssensplanerMealplanCoordinator,
    EssensplanerStatisticsCoordinator,
)
from .entity import EssensplanerEntity
from .meal_times import get_configured_meal_times, resolve_meal_slot_times
from .models import MealplanEntry, Recipe, Statistics

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class EssensplanerSensorDescription(SensorEntityDescription):
    """Sensor description."""

    value_fn: Callable[[Statistics], StateType]


SENSOR_TYPES: tuple[EssensplanerSensorDescription, ...] = (
    EssensplanerSensorDescription(
        key="recipes",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda s: s.total_recipes,
    ),
    EssensplanerSensorDescription(
        key="categories",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda s: s.total_categories,
    ),
    EssensplanerSensorDescription(
        key="tags",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda s: s.total_tags,
    ),
    EssensplanerSensorDescription(
        key="tools",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda s: s.total_tools,
    ),
    EssensplanerSensorDescription(
        key="cookbooks",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda s: s.total_cookbooks,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EssensplanerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    statistics_coordinator = entry.runtime_data.statistics_coordinator
    mealplan_coordinator = entry.runtime_data.mealplan_coordinator
    async_add_entities(
        [
            *(
                EssensplanerStatisticSensor(statistics_coordinator, description)
                for description in SENSOR_TYPES
            ),
            EssensplanerTodayMealplanSensor(mealplan_coordinator),
        ]
    )


class EssensplanerStatisticSensor(EssensplanerEntity, SensorEntity):
    """Statistics sensor."""

    entity_description: EssensplanerSensorDescription
    coordinator: EssensplanerStatisticsCoordinator

    def __init__(
        self,
        coordinator: EssensplanerStatisticsCoordinator,
        description: EssensplanerSensorDescription,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key

    @property
    def native_value(self) -> StateType:
        """Return sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)


def _meal_slot_dict(
    entry_type: str,
    mealplan: MealplanEntry | None,
    recipe: Recipe | None,
    options: dict,
) -> dict[str, str | bool | None]:
    """Build dashboard-friendly meal slot dict."""
    if mealplan:
        start_time, end_time = resolve_meal_slot_times(mealplan, options)
        if recipe:
            name = recipe.name
            image_url = recipe.image_url
            recipe_id = recipe.id
        else:
            name = mealplan.title
            image_url = None
            recipe_id = mealplan.recipe_id
        planned = bool(name)
    else:
        start_time, end_time = get_configured_meal_times(options)[entry_type]
        name = None
        image_url = None
        recipe_id = None
        planned = False

    return {
        "entry_type": entry_type,
        "label": MEAL_TYPE_LABELS.get(entry_type, entry_type),
        "icon": MEAL_TYPE_ICONS.get(entry_type, "mdi:food"),
        "name": name,
        "image_url": image_url,
        "recipe_id": recipe_id,
        "start_time": start_time,
        "end_time": end_time,
        "planned": planned,
    }


class EssensplanerTodayMealplanSensor(EssensplanerEntity, SensorEntity):
    """Today's meal plan for dashboard cards."""

    coordinator: EssensplanerMealplanCoordinator

    def __init__(self, coordinator: EssensplanerMealplanCoordinator) -> None:
        """Initialize today's meal plan sensor."""
        super().__init__(coordinator, "mealplan_today")
        self._attr_translation_key = "mealplan_today"
        self._attr_icon = "mdi:calendar-today"

    def _today_meals(self) -> list[dict[str, str | bool | None]]:
        """Return meal slots for today."""
        today = dt_util.now().date()
        options = self.coordinator.config_entry.options
        plans = {
            mealplan.entry_type: mealplan
            for mealplan in self.coordinator.store.get_mealplans(today, today)
        }
        meals: list[dict[str, str | bool | None]] = []
        for entry_type in DASHBOARD_MEAL_TYPES:
            mealplan = plans.get(entry_type)
            recipe = None
            if mealplan and mealplan.recipe_id:
                recipe = self.coordinator.store.data.recipes.get(mealplan.recipe_id)
            meals.append(_meal_slot_dict(entry_type, mealplan, recipe, options))
        return meals

    @property
    def native_value(self) -> StateType:
        """Return count of planned meals today."""
        return sum(1 for meal in self._today_meals() if meal["planned"])

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return structured meal plan for Lovelace cards."""
        today = dt_util.now().date()
        meals = self._today_meals()
        weekday_names = (
            "Montag",
            "Dienstag",
            "Mittwoch",
            "Donnerstag",
            "Freitag",
            "Samstag",
            "Sonntag",
        )
        return {
            "date": today.isoformat(),
            "date_label": (
                f"{weekday_names[today.weekday()]}, "
                f"{today.strftime('%d.%m.%Y')}"
            ),
            "meals": meals,
            "breakfast": meals[0] if len(meals) > 0 else None,
            "lunch": meals[1] if len(meals) > 1 else None,
            "dinner": meals[2] if len(meals) > 2 else None,
        }
