"""Meal slot times for calendar display."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from .const import MEALPLAN_ENTRY_TYPES, MealplanEntryType
from .models import MealplanEntry

DEFAULT_MEAL_TIMES: dict[str, tuple[str, str]] = {
    MealplanEntryType.BREAKFAST: ("07:00", "08:00"),
    MealplanEntryType.LUNCH: ("12:00", "13:00"),
    MealplanEntryType.DINNER: ("18:00", "19:30"),
    MealplanEntryType.SIDE: ("12:00", "12:30"),
    MealplanEntryType.DESSERT: ("19:30", "20:00"),
    MealplanEntryType.DRINK: ("10:00", "10:15"),
    MealplanEntryType.SNACK: ("15:00", "15:30"),
}


def meal_time_option_key(entry_type: str, part: str) -> str:
    """Return config option key for a meal slot time."""
    return f"{entry_type}_{part}"


def parse_time_value(value: str | time) -> tuple[int, int]:
    """Parse HH:MM or HH:MM:SS (or time object) to hour and minute."""
    if isinstance(value, time):
        return value.hour, value.minute
    parts = str(value).split(":")
    return int(parts[0]), int(parts[1])


def format_time_value(value: str | time) -> str:
    """Normalize a time to HH:MM."""
    hour, minute = parse_time_value(value)
    return f"{hour:02d}:{minute:02d}"


def get_configured_meal_times(options: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Resolve meal slot times from config entry options."""
    result: dict[str, tuple[str, str]] = {}
    for entry_type in MEALPLAN_ENTRY_TYPES:
        default_start, default_end = DEFAULT_MEAL_TIMES[entry_type]
        start = options.get(meal_time_option_key(entry_type, "start"), default_start)
        end = options.get(meal_time_option_key(entry_type, "end"), default_end)
        result[entry_type] = (format_time_value(start), format_time_value(end))
    return result


def resolve_meal_slot_times(
    mealplan: MealplanEntry, options: dict[str, Any]
) -> tuple[str, str]:
    """Return start/end time strings for a meal plan entry."""
    if mealplan.start_time and mealplan.end_time:
        return (
            format_time_value(mealplan.start_time),
            format_time_value(mealplan.end_time),
        )
    return get_configured_meal_times(options)[mealplan.entry_type]


def normalize_meal_time_option_values(user_input: dict[str, Any]) -> dict[str, str]:
    """Store meal time option values as HH:MM strings."""
    return {key: format_time_value(value) for key, value in user_input.items()}


def meal_times_to_api(options: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Return meal times for API consumers."""
    return {
        entry_type: {"start": start, "end": end}
        for entry_type, (start, end) in get_configured_meal_times(options).items()
    }


def merge_meal_times_from_api(
    current: dict[str, Any], meal_times: dict[str, dict[str, str]]
) -> dict[str, str]:
    """Merge meal time updates into config entry options."""
    options = dict(current)
    for entry_type, slot in meal_times.items():
        if entry_type not in MEALPLAN_ENTRY_TYPES or not isinstance(slot, dict):
            continue
        start = slot.get("start")
        end = slot.get("end")
        if start is None or end is None:
            continue
        start_fmt = format_time_value(start)
        end_fmt = format_time_value(end)
        start_m = parse_time_value(start_fmt)[0] * 60 + parse_time_value(start_fmt)[1]
        end_m = parse_time_value(end_fmt)[0] * 60 + parse_time_value(end_fmt)[1]
        if end_m <= start_m:
            raise ValueError(f"End time must be after start time for {entry_type}")
        options[meal_time_option_key(entry_type, "start")] = start_fmt
        options[meal_time_option_key(entry_type, "end")] = end_fmt
    return options


def mealplan_to_datetimes(
    mealplan: MealplanEntry, options: dict[str, Any]
) -> tuple[datetime, datetime]:
    """Convert meal plan entry to localized start/end datetimes."""
    plan_date = date.fromisoformat(mealplan.date)
    tz = dt_util.get_default_time_zone()
    start_str, end_str = resolve_meal_slot_times(mealplan, options)
    start_h, start_m = parse_time_value(start_str)
    end_h, end_m = parse_time_value(end_str)
    start = datetime.combine(plan_date, time(start_h, start_m), tzinfo=tz)
    end = datetime.combine(plan_date, time(end_h, end_m), tzinfo=tz)
    if end <= start:
        end = start + timedelta(hours=1)
    return start, end
