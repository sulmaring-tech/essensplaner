"""Constants for the Essensplaner integration."""

import logging
from enum import StrEnum

DOMAIN = "essensplaner"

LOGGER = logging.getLogger(__package__)

STORAGE_VERSION = 1
STORAGE_KEY = "essensplaner.{entry_id}"

CONF_HOUSEHOLD_NAME = "household_name"
OPTION_DEFAULT_SHOPPING_LIST_ID = "default_shopping_list_id"
OPTION_RECIPES_PER_ROW = "recipes_per_row"
OPTION_VISIBLE_MEAL_TYPES = "visible_meal_types"
OPTION_WEEK_START = "week_start"
OPTION_DEFAULT_WEEK = "default_week"
OPTION_RECIPE_SORT = "recipe_sort"
OPTION_TILE_SIZE = "tile_size"
OPTION_SHOW_RECIPE_IMAGES = "show_recipe_images"
OPTION_SUGGEST_MEAL_TAGS_ON_IMPORT = "suggest_meal_tags_on_import"

DEFAULT_RECIPES_PER_ROW = 5
MIN_RECIPES_PER_ROW = 2
MAX_RECIPES_PER_ROW = 8

WEEK_START_MONDAY = "monday"
WEEK_START_SUNDAY = "sunday"
DEFAULT_WEEK_CURRENT = "current"

RECIPE_SORT_NAME = "name"
RECIPE_SORT_UPDATED = "updated"
RECIPE_SORT_LAST_PLANNED = "last_planned"

TILE_SIZE_COMPACT = "compact"
TILE_SIZE_LARGE = "large"

ATTR_START_DATE = "start_date"
ATTR_END_DATE = "end_date"
ATTR_RECIPE_ID = "recipe_id"
ATTR_URL = "url"
ATTR_INCLUDE_TAGS = "include_tags"
ATTR_ENTRY_TYPE = "entry_type"
ATTR_NOTE_TITLE = "note_title"
ATTR_NOTE_TEXT = "note_text"
ATTR_SEARCH_TERMS = "search_terms"
ATTR_RESULT_LIMIT = "result_limit"
ATTR_LIST_ID = "list_id"
ATTR_NAME = "name"
ATTR_DESCRIPTION = "description"
ATTR_INGREDIENTS = "ingredients"
ATTR_INSTRUCTIONS = "instructions"
ATTR_TAGS = "tags"
ATTR_CATEGORIES = "categories"
ATTR_COOKBOOK_ID = "cookbook_id"
ATTR_START_TIME = "start_time"
ATTR_END_TIME = "end_time"
ATTR_IMAGE_URL = "image_url"
ATTR_SERVINGS = "servings"
ATTR_QUERY = "query"
ATTR_LIMIT = "limit"

SERVICE_SEARCH_RECIPES_ONLINE = "search_recipes_online"

DEFAULT_SHOPPING_LIST_NAME = "Einkaufsliste"

UPDATE_INTERVAL_MEALPLAN = 3600
UPDATE_INTERVAL_SHOPPING = 300
UPDATE_INTERVAL_STATISTICS = 900


class MealplanEntryType(StrEnum):
    """Meal plan entry types (compatible with Mealie)."""

    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SIDE = "side"
    DESSERT = "dessert"
    DRINK = "drink"
    SNACK = "snack"


DEFAULT_VISIBLE_MEAL_TYPES: tuple[str, ...] = (
    MealplanEntryType.BREAKFAST,
    MealplanEntryType.LUNCH,
    MealplanEntryType.DINNER,
)


MEALPLAN_ENTRY_TYPES = list(MealplanEntryType)

DASHBOARD_MEAL_TYPES: tuple[MealplanEntryType, ...] = (
    MealplanEntryType.BREAKFAST,
    MealplanEntryType.LUNCH,
    MealplanEntryType.DINNER,
)

MEAL_TYPE_LABELS: dict[str, str] = {
    MealplanEntryType.BREAKFAST: "Frühstück",
    MealplanEntryType.LUNCH: "Mittagessen",
    MealplanEntryType.DINNER: "Abendessen",
    MealplanEntryType.SIDE: "Beilage",
    MealplanEntryType.DESSERT: "Dessert",
    MealplanEntryType.DRINK: "Getränk",
    MealplanEntryType.SNACK: "Snack",
}

MEAL_TYPE_ICONS: dict[str, str] = {
    MealplanEntryType.BREAKFAST: "mdi:coffee",
    MealplanEntryType.LUNCH: "mdi:silverware-fork-knife",
    MealplanEntryType.DINNER: "mdi:food-turkey",
    MealplanEntryType.SIDE: "mdi:food-variant",
    MealplanEntryType.DESSERT: "mdi:cupcake",
    MealplanEntryType.DRINK: "mdi:glass-cocktail",
    MealplanEntryType.SNACK: "mdi:cookie",
}

SERVICE_GET_MEALPLAN = "get_mealplan"
SERVICE_GET_RECIPE = "get_recipe"
SERVICE_GET_RECIPES = "get_recipes"
SERVICE_IMPORT_RECIPE = "import_recipe"
SERVICE_CREATE_RECIPE = "create_recipe"
SERVICE_DELETE_RECIPE = "delete_recipe"
SERVICE_SET_MEALPLAN = "set_mealplan"
SERVICE_SET_RANDOM_MEALPLAN = "set_random_mealplan"
SERVICE_GET_SHOPPING_LIST_ITEMS = "get_shopping_list_items"
SERVICE_ADD_RECIPE_TO_SHOPPING_LIST = "add_recipe_to_shopping_list"
SERVICE_GET_COOKBOOKS = "get_cookbooks"
SERVICE_UPDATE_RECIPE = "update_recipe"
SERVICE_CREATE_COOKBOOK = "create_cookbook"
SERVICE_DELETE_COOKBOOK = "delete_cookbook"
SERVICE_ADD_RECIPE_TO_COOKBOOK = "add_recipe_to_cookbook"
SERVICE_REMOVE_RECIPE_FROM_COOKBOOK = "remove_recipe_from_cookbook"
SERVICE_CLEAR_MEALPLAN = "clear_mealplan"

PANEL_URL_PATH = "essensplaner"
PANEL_STATIC_PATH = "/essensplaner_static"
PANEL_JS_URL = "/essensplaner_static/panel.js"
LOVELACE_CARD_URL = "/essensplaner_static/today-mealplan-card.js"
