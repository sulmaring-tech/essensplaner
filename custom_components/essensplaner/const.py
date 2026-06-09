"""Constants for the Essensplaner integration."""

import logging
from enum import StrEnum

DOMAIN = "essensplaner"

LOGGER = logging.getLogger(__package__)

STORAGE_VERSION = 1
STORAGE_KEY = "essensplaner.{entry_id}"

CONF_HOUSEHOLD_NAME = "household_name"

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


MEALPLAN_ENTRY_TYPES = list(MealplanEntryType)

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
