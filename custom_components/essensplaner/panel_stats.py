"""Statistics payload for the Essensplaner panel."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from .const import DASHBOARD_MEAL_TYPES, MEAL_TYPE_ICONS, MEAL_TYPE_LABELS
from .storage import EssensplanerStore


def get_panel_statistics(store: EssensplanerStore) -> dict[str, Any]:
    """Return extended statistics for the panel UI."""
    data = store.data
    today = dt_util.now().date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    base = data.compute_statistics().to_dict()
    recipes = list(data.recipes.values())
    week_plans = store.get_mealplans(week_start, week_end)
    today_plans = store.get_mealplans(today, today)

    def is_planned(mealplan) -> bool:
        return bool(mealplan.recipe_id or mealplan.title)

    planned_week = sum(1 for mealplan in week_plans if is_planned(mealplan))
    planned_today = sum(1 for mealplan in today_plans if is_planned(mealplan))
    week_slots = 7 * len(DASHBOARD_MEAL_TYPES)

    mealplan_by_type: list[dict[str, Any]] = []
    for entry_type in DASHBOARD_MEAL_TYPES:
        count = sum(
            1
            for mealplan in week_plans
            if mealplan.entry_type == entry_type and is_planned(mealplan)
        )
        mealplan_by_type.append(
            {
                "id": entry_type,
                "label": MEAL_TYPE_LABELS.get(entry_type, entry_type),
                "icon": MEAL_TYPE_ICONS.get(entry_type, "mdi:food"),
                "count": count,
                "max": 7,
            }
        )

    shopping_items = list(data.shopping_items.values())
    open_items = sum(1 for item in shopping_items if not item.checked)
    done_items = sum(1 for item in shopping_items if item.checked)

    tag_counts: Counter[str] = Counter()
    meal_tag_counts = {entry_type: 0 for entry_type in DASHBOARD_MEAL_TYPES}
    with_image = 0
    with_instructions = 0
    total_ingredients = 0

    for recipe in recipes:
        if recipe.image_url:
            with_image += 1
        if recipe.instructions:
            with_instructions += 1
        total_ingredients += len(recipe.ingredients)
        for tag in recipe.tags:
            tag_counts[tag] += 1
            if tag in meal_tag_counts:
                meal_tag_counts[tag] += 1

    recipe_plan_counts: Counter[str] = Counter()
    for mealplan in week_plans:
        if not mealplan.recipe_id:
            continue
        recipe = data.recipes.get(mealplan.recipe_id)
        name = recipe.name if recipe else mealplan.title or "Unbekannt"
        recipe_plan_counts[name] += 1

    return {
        **base,
        "mealplan_today": planned_today,
        "mealplan_today_total": len(DASHBOARD_MEAL_TYPES),
        "mealplan_week_planned": planned_week,
        "mealplan_week_slots": week_slots,
        "mealplan_week_percent": round((planned_week / week_slots) * 100)
        if week_slots
        else 0,
        "mealplan_by_type": mealplan_by_type,
        "shopping_lists": len(data.shopping_lists),
        "shopping_items_open": open_items,
        "shopping_items_done": done_items,
        "shopping_items_total": len(shopping_items),
        "recipes_with_image": with_image,
        "recipes_with_instructions": with_instructions,
        "recipes_avg_ingredients": round(total_ingredients / len(recipes), 1)
        if recipes
        else 0,
        "recipes_by_meal_tag": [
            {
                "id": entry_type,
                "label": MEAL_TYPE_LABELS.get(entry_type, entry_type),
                "icon": MEAL_TYPE_ICONS.get(entry_type, entry_type),
                "count": meal_tag_counts[entry_type],
            }
            for entry_type in DASHBOARD_MEAL_TYPES
        ],
        "top_tags": [
            {"name": name, "count": count}
            for name, count in tag_counts.most_common(8)
        ],
        "top_planned_recipes": [
            {"name": name, "count": count}
            for name, count in recipe_plan_counts.most_common(5)
        ],
    }
