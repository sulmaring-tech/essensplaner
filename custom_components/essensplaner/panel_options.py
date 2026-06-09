"""Panel UI options stored on the config entry."""

from __future__ import annotations

from typing import Any

from .const import (
    DEFAULT_RECIPES_PER_ROW,
    DEFAULT_VISIBLE_MEAL_TYPES,
    DEFAULT_WEEK_CURRENT,
    MAX_RECIPES_PER_ROW,
    MEALPLAN_ENTRY_TYPES,
    MIN_RECIPES_PER_ROW,
    MealplanEntryType,
    OPTION_DEFAULT_WEEK,
    OPTION_RECIPES_PER_ROW,
    OPTION_RECIPE_SORT,
    OPTION_SHOW_RECIPE_IMAGES,
    OPTION_SUGGEST_MEAL_TAGS_ON_IMPORT,
    OPTION_TILE_SIZE,
    OPTION_VISIBLE_MEAL_TYPES,
    OPTION_WEEK_START,
    RECIPE_SORT_LAST_PLANNED,
    RECIPE_SORT_NAME,
    RECIPE_SORT_UPDATED,
    TILE_SIZE_COMPACT,
    TILE_SIZE_LARGE,
    WEEK_START_MONDAY,
    WEEK_START_SUNDAY,
)
from .storage import EssensplanerStore

_VALID_WEEK_STARTS = {WEEK_START_MONDAY, WEEK_START_SUNDAY}
_VALID_DEFAULT_WEEKS = {DEFAULT_WEEK_CURRENT, "next"}
_VALID_RECIPE_SORTS = {RECIPE_SORT_NAME, RECIPE_SORT_UPDATED, RECIPE_SORT_LAST_PLANNED}
_VALID_TILE_SIZES = {TILE_SIZE_COMPACT, TILE_SIZE_LARGE}


def recipe_last_planned_dates(store: EssensplanerStore) -> dict[str, str]:
    """Return the latest meal plan date per recipe id."""
    dates: dict[str, str] = {}
    for mealplan in store.data.mealplans:
        if not mealplan.recipe_id:
            continue
        previous = dates.get(mealplan.recipe_id)
        if previous is None or mealplan.date > previous:
            dates[mealplan.recipe_id] = mealplan.date
    return dates


def _recipes_per_row(options: dict[str, Any]) -> int:
    raw = options.get(OPTION_RECIPES_PER_ROW, DEFAULT_RECIPES_PER_ROW)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_RECIPES_PER_ROW
    return max(MIN_RECIPES_PER_ROW, min(MAX_RECIPES_PER_ROW, value))


def _visible_meal_types(options: dict[str, Any]) -> list[str]:
    raw = options.get(OPTION_VISIBLE_MEAL_TYPES)
    if not isinstance(raw, list):
        return list(DEFAULT_VISIBLE_MEAL_TYPES)
    visible = [entry_type for entry_type in raw if entry_type in MEALPLAN_ENTRY_TYPES]
    if MealplanEntryType.SIDE in raw:
        for side_type in (MealplanEntryType.SIDE_LUNCH, MealplanEntryType.SIDE_DINNER):
            if side_type not in visible:
                visible.append(side_type)
    return visible or list(DEFAULT_VISIBLE_MEAL_TYPES)


def _week_start(options: dict[str, Any]) -> str:
    value = options.get(OPTION_WEEK_START, WEEK_START_MONDAY)
    return value if value in _VALID_WEEK_STARTS else WEEK_START_MONDAY


def _default_week(options: dict[str, Any]) -> str:
    value = options.get(OPTION_DEFAULT_WEEK, DEFAULT_WEEK_CURRENT)
    return value if value in _VALID_DEFAULT_WEEKS else DEFAULT_WEEK_CURRENT


def _recipe_sort(options: dict[str, Any]) -> str:
    value = options.get(OPTION_RECIPE_SORT, RECIPE_SORT_NAME)
    return value if value in _VALID_RECIPE_SORTS else RECIPE_SORT_NAME


def _tile_size(options: dict[str, Any]) -> str:
    value = options.get(OPTION_TILE_SIZE, TILE_SIZE_COMPACT)
    return value if value in _VALID_TILE_SIZES else TILE_SIZE_COMPACT


def _show_recipe_images(options: dict[str, Any]) -> bool:
    raw = options.get(OPTION_SHOW_RECIPE_IMAGES, True)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.lower() not in {"0", "false", "no", "off"}
    return bool(raw)


def _suggest_meal_tags_on_import(options: dict[str, Any]) -> bool:
    raw = options.get(OPTION_SUGGEST_MEAL_TAGS_ON_IMPORT, True)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.lower() not in {"0", "false", "no", "off"}
    return bool(raw)


def panel_options_to_api(store: EssensplanerStore, options: dict[str, Any]) -> dict[str, Any]:
    """Return normalized panel options for the UI."""
    return {
        "recipes_per_row": _recipes_per_row(options),
        "visible_meal_types": _visible_meal_types(options),
        "week_start": _week_start(options),
        "default_week": _default_week(options),
        "recipe_sort": _recipe_sort(options),
        "tile_size": _tile_size(options),
        "show_recipe_images": _show_recipe_images(options),
        "suggest_meal_tags_on_import": _suggest_meal_tags_on_import(options),
        "recipe_last_planned": recipe_last_planned_dates(store),
    }


def suggest_meal_tags_on_import_enabled(entry) -> bool:
    """Return whether meal tags should be suggested on import."""
    return _suggest_meal_tags_on_import(entry.options)


def merge_panel_options(
    current: dict[str, Any], updates: dict[str, Any]
) -> dict[str, Any]:
    """Merge validated panel option updates into config entry options."""
    options = dict(current)

    if OPTION_RECIPES_PER_ROW in updates:
        options[OPTION_RECIPES_PER_ROW] = _recipes_per_row(
            {OPTION_RECIPES_PER_ROW: updates[OPTION_RECIPES_PER_ROW]}
        )

    if OPTION_VISIBLE_MEAL_TYPES in updates:
        visible = _visible_meal_types(
            {OPTION_VISIBLE_MEAL_TYPES: updates[OPTION_VISIBLE_MEAL_TYPES]}
        )
        options[OPTION_VISIBLE_MEAL_TYPES] = visible

    if OPTION_WEEK_START in updates:
        value = updates[OPTION_WEEK_START]
        options[OPTION_WEEK_START] = (
            value if value in _VALID_WEEK_STARTS else WEEK_START_MONDAY
        )

    if OPTION_DEFAULT_WEEK in updates:
        value = updates[OPTION_DEFAULT_WEEK]
        options[OPTION_DEFAULT_WEEK] = (
            value if value in _VALID_DEFAULT_WEEKS else DEFAULT_WEEK_CURRENT
        )

    if OPTION_RECIPE_SORT in updates:
        value = updates[OPTION_RECIPE_SORT]
        options[OPTION_RECIPE_SORT] = (
            value if value in _VALID_RECIPE_SORTS else RECIPE_SORT_NAME
        )

    if OPTION_TILE_SIZE in updates:
        value = updates[OPTION_TILE_SIZE]
        options[OPTION_TILE_SIZE] = (
            value if value in _VALID_TILE_SIZES else TILE_SIZE_COMPACT
        )

    if OPTION_SHOW_RECIPE_IMAGES in updates:
        options[OPTION_SHOW_RECIPE_IMAGES] = bool(updates[OPTION_SHOW_RECIPE_IMAGES])

    if OPTION_SUGGEST_MEAL_TAGS_ON_IMPORT in updates:
        options[OPTION_SUGGEST_MEAL_TAGS_ON_IMPORT] = bool(
            updates[OPTION_SUGGEST_MEAL_TAGS_ON_IMPORT]
        )

    return options
