"""Services for Essensplaner."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components.todo import DOMAIN as TODO_DOMAIN
from homeassistant.const import ATTR_CONFIG_ENTRY_ID, ATTR_DATE
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, service
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_CATEGORIES,
    ATTR_COOKBOOK_ID,
    ATTR_DESCRIPTION,
    ATTR_END_DATE,
    ATTR_ENTRY_TYPE,
    ATTR_INCLUDE_TAGS,
    ATTR_INGREDIENTS,
    ATTR_INSTRUCTIONS,
    ATTR_LIST_ID,
    ATTR_NAME,
    ATTR_NOTE_TEXT,
    ATTR_NOTE_TITLE,
    ATTR_RECIPE_ID,
    ATTR_RESULT_LIMIT,
    ATTR_SEARCH_TERMS,
    ATTR_START_DATE,
    ATTR_TAGS,
    ATTR_URL,
    DOMAIN,
    MEALPLAN_ENTRY_TYPES,
    SERVICE_ADD_RECIPE_TO_SHOPPING_LIST,
    SERVICE_CREATE_RECIPE,
    SERVICE_DELETE_RECIPE,
    SERVICE_ADD_RECIPE_TO_COOKBOOK,
    SERVICE_CLEAR_MEALPLAN,
    SERVICE_CREATE_COOKBOOK,
    SERVICE_DELETE_COOKBOOK,
    SERVICE_GET_COOKBOOKS,
    SERVICE_GET_MEALPLAN,
    SERVICE_GET_RECIPE,
    SERVICE_GET_RECIPES,
    SERVICE_GET_SHOPPING_LIST_ITEMS,
    SERVICE_IMPORT_RECIPE,
    SERVICE_REMOVE_RECIPE_FROM_COOKBOOK,
    SERVICE_SET_MEALPLAN,
    SERVICE_SET_RANDOM_MEALPLAN,
    SERVICE_UPDATE_RECIPE,
)
from .coordinator import EssensplanerConfigEntry
from .models import Ingredient, Recipe
from .recipe_importer import async_import_recipe_from_url
from .utils import generate_id, unique_slug

SERVICE_GET_MEALPLAN_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): str,
        vol.Optional(ATTR_START_DATE): cv.date,
        vol.Optional(ATTR_END_DATE): cv.date,
    }
)

SERVICE_GET_RECIPE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): str,
        vol.Required(ATTR_RECIPE_ID): str,
    }
)

SERVICE_GET_RECIPES_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): str,
        vol.Optional(ATTR_SEARCH_TERMS): str,
        vol.Optional(ATTR_RESULT_LIMIT): vol.All(vol.Coerce(int), vol.Range(min=1, max=500)),
    }
)

SERVICE_IMPORT_RECIPE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): str,
        vol.Required(ATTR_URL): cv.url,
        vol.Optional(ATTR_INCLUDE_TAGS): bool,
    }
)

SERVICE_CREATE_RECIPE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): str,
        vol.Required(ATTR_NAME): str,
        vol.Optional(ATTR_DESCRIPTION): str,
        vol.Optional(ATTR_INGREDIENTS): [str],
        vol.Optional(ATTR_INSTRUCTIONS): [str],
        vol.Optional(ATTR_TAGS): [str],
        vol.Optional(ATTR_CATEGORIES): [str],
    }
)

SERVICE_DELETE_RECIPE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): str,
        vol.Required(ATTR_RECIPE_ID): str,
    }
)

SERVICE_SET_RANDOM_MEALPLAN_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): str,
        vol.Required(ATTR_DATE): cv.date,
        vol.Required(ATTR_ENTRY_TYPE): vol.In(MEALPLAN_ENTRY_TYPES),
    }
)

SERVICE_SET_MEALPLAN_SCHEMA = vol.Any(
    vol.Schema(
        {
            vol.Required(ATTR_CONFIG_ENTRY_ID): str,
            vol.Required(ATTR_DATE): cv.date,
            vol.Required(ATTR_ENTRY_TYPE): vol.In(MEALPLAN_ENTRY_TYPES),
            vol.Required(ATTR_RECIPE_ID): str,
        }
    ),
    vol.Schema(
        {
            vol.Required(ATTR_CONFIG_ENTRY_ID): str,
            vol.Required(ATTR_DATE): cv.date,
            vol.Required(ATTR_ENTRY_TYPE): vol.In(MEALPLAN_ENTRY_TYPES),
            vol.Required(ATTR_NOTE_TITLE): str,
            vol.Optional(ATTR_NOTE_TEXT): str,
        }
    ),
)

SERVICE_ADD_RECIPE_TO_SHOPPING_LIST_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): str,
        vol.Required(ATTR_RECIPE_ID): str,
        vol.Optional(ATTR_LIST_ID): str,
    }
)

SERVICE_GET_COOKBOOKS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): str,
    }
)

SERVICE_UPDATE_RECIPE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): str,
        vol.Required(ATTR_RECIPE_ID): str,
        vol.Optional(ATTR_NAME): str,
        vol.Optional(ATTR_DESCRIPTION): str,
        vol.Optional(ATTR_INGREDIENTS): [str],
        vol.Optional(ATTR_INSTRUCTIONS): [str],
        vol.Optional(ATTR_TAGS): [str],
        vol.Optional(ATTR_CATEGORIES): [str],
    }
)

SERVICE_CREATE_COOKBOOK_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): str,
        vol.Required(ATTR_NAME): str,
        vol.Optional(ATTR_DESCRIPTION): str,
    }
)

SERVICE_DELETE_COOKBOOK_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): str,
        vol.Required(ATTR_COOKBOOK_ID): str,
    }
)

SERVICE_ADD_RECIPE_TO_COOKBOOK_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): str,
        vol.Required(ATTR_COOKBOOK_ID): str,
        vol.Required(ATTR_RECIPE_ID): str,
    }
)

SERVICE_REMOVE_RECIPE_FROM_COOKBOOK_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): str,
        vol.Required(ATTR_COOKBOOK_ID): str,
        vol.Required(ATTR_RECIPE_ID): str,
    }
)

SERVICE_CLEAR_MEALPLAN_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): str,
        vol.Required(ATTR_DATE): cv.date,
        vol.Required(ATTR_ENTRY_TYPE): vol.In(MEALPLAN_ENTRY_TYPES),
    }
)


def _get_entry(call: ServiceCall) -> EssensplanerConfigEntry:
    """Get config entry from service call."""
    return service.async_get_config_entry(call.hass, DOMAIN, call.data[ATTR_CONFIG_ENTRY_ID])


async def _async_get_mealplan(call: ServiceCall) -> ServiceResponse:
    """Get meal plan for date range."""
    entry = _get_entry(call)
    start_date = call.data.get(ATTR_START_DATE, dt_util.now().date())
    end_date = call.data.get(ATTR_END_DATE, dt_util.now().date())
    if end_date < start_date:
        raise ServiceValidationError("end_date must not be before start_date")

    store = entry.runtime_data.store
    mealplans = store.get_mealplans(start_date, end_date)
    result = []
    for mealplan in mealplans:
        recipe = store.data.recipes.get(mealplan.recipe_id) if mealplan.recipe_id else None
        result.append(mealplan.to_service_dict(recipe))
    return {"mealplan": result}


async def _async_get_recipe(call: ServiceCall) -> ServiceResponse:
    """Get single recipe."""
    entry = _get_entry(call)
    recipe_id = call.data[ATTR_RECIPE_ID]
    store = entry.runtime_data.store
    recipe = store.find_recipe(recipe_id)
    if not recipe:
        raise ServiceValidationError(f"Recipe not found: {recipe_id}")
    return {"recipe": recipe.to_dict()}


async def _async_get_recipes(call: ServiceCall) -> ServiceResponse:
    """Search recipes."""
    entry = _get_entry(call)
    search = call.data.get(ATTR_SEARCH_TERMS)
    limit = call.data.get(ATTR_RESULT_LIMIT, 10)
    recipes = entry.runtime_data.store.search_recipes(search, limit)
    return {"recipes": [r.to_dict() for r in recipes]}


async def _async_import_recipe(call: ServiceCall) -> ServiceResponse:
    """Import recipe from URL."""
    entry = _get_entry(call)
    url = call.data[ATTR_URL]
    include_tags = call.data.get(ATTR_INCLUDE_TAGS, False)
    store = entry.runtime_data.store

    try:
        recipe = await async_import_recipe_from_url(call.hass, url, include_tags)
        existing_slugs = {r.slug for r in store.data.recipes.values()}
        recipe.slug = unique_slug(recipe.name, existing_slugs)
        recipe = await store.async_add_recipe(recipe)
    except Exception as err:
        raise ServiceValidationError(f"Could not import recipe: {err}") from err

    await _async_refresh_all(entry)
    if call.return_response:
        return {"recipe": recipe.to_dict()}
    return None


async def _async_create_recipe(call: ServiceCall) -> ServiceResponse:
    """Create recipe manually."""
    entry = _get_entry(call)
    store = entry.runtime_data.store
    name = call.data[ATTR_NAME]
    recipe_id = generate_id()
    slugs = {r.slug for r in store.data.recipes.values()}
    recipe = Recipe(
        id=recipe_id,
        slug=unique_slug(name, slugs),
        name=name,
        description=call.data.get(ATTR_DESCRIPTION),
        ingredients=[Ingredient(name=i) for i in call.data.get(ATTR_INGREDIENTS, [])],
        instructions=call.data.get(ATTR_INSTRUCTIONS, []),
        tags=call.data.get(ATTR_TAGS, []),
        categories=call.data.get(ATTR_CATEGORIES, []),
    )
    recipe = await store.async_add_recipe(recipe)
    await _async_refresh_all(entry)
    if call.return_response:
        return {"recipe": recipe.to_dict()}
    return None


async def _async_delete_recipe(call: ServiceCall) -> ServiceResponse:
    """Delete recipe."""
    entry = _get_entry(call)
    deleted = await entry.runtime_data.store.async_delete_recipe(call.data[ATTR_RECIPE_ID])
    if not deleted:
        raise ServiceValidationError(f"Recipe not found: {call.data[ATTR_RECIPE_ID]}")
    await _async_refresh_all(entry)
    return None


async def _async_set_mealplan(call: ServiceCall) -> ServiceResponse:
    """Set meal plan entry."""
    entry = _get_entry(call)
    store = entry.runtime_data.store
    try:
        mealplan = await store.async_set_mealplan(
            call.data[ATTR_DATE],
            call.data[ATTR_ENTRY_TYPE],
            recipe_id=call.data.get(ATTR_RECIPE_ID),
            note_title=call.data.get(ATTR_NOTE_TITLE),
            note_text=call.data.get(ATTR_NOTE_TEXT),
        )
    except ValueError as err:
        raise ServiceValidationError(str(err)) from err

    recipe = store.data.recipes.get(mealplan.recipe_id) if mealplan.recipe_id else None
    await _async_refresh_all(entry)
    if call.return_response:
        return {"mealplan": mealplan.to_service_dict(recipe)}
    return None


async def _async_clear_mealplan(call: ServiceCall) -> ServiceResponse:
    """Clear a meal plan slot."""
    entry = _get_entry(call)
    await entry.runtime_data.store.async_clear_mealplan(
        call.data[ATTR_DATE],
        call.data[ATTR_ENTRY_TYPE],
    )
    await _async_refresh_all(entry)
    return None


async def _async_set_random_mealplan(call: ServiceCall) -> ServiceResponse:
    """Set random meal plan."""
    entry = _get_entry(call)
    store = entry.runtime_data.store
    try:
        mealplan = await store.async_set_random_mealplan(
            call.data[ATTR_DATE], call.data[ATTR_ENTRY_TYPE]
        )
    except ValueError as err:
        raise ServiceValidationError(str(err)) from err

    recipe = store.data.recipes.get(mealplan.recipe_id) if mealplan.recipe_id else None
    await _async_refresh_all(entry)
    if call.return_response:
        return {"mealplan": mealplan.to_service_dict(recipe)}
    return None


async def _async_add_recipe_to_shopping_list(call: ServiceCall) -> ServiceResponse:
    """Add recipe ingredients to shopping list."""
    entry = _get_entry(call)
    store = entry.runtime_data.store
    try:
        items = await store.async_add_recipe_ingredients_to_list(
            call.data[ATTR_RECIPE_ID],
            call.data.get(ATTR_LIST_ID),
        )
    except ValueError as err:
        raise ServiceValidationError(str(err)) from err

    await entry.runtime_data.shoppinglist_coordinator.async_refresh()
    return {"items": [i.to_dict() for i in items]}


async def _async_get_cookbooks(call: ServiceCall) -> ServiceResponse:
    """Get all cookbooks."""
    entry = _get_entry(call)
    store = entry.runtime_data.store
    cookbooks = []
    for cookbook in store.data.cookbooks.values():
        data = cookbook.to_dict()
        data["recipes"] = [
            store.data.recipes[rid].to_dict()
            for rid in cookbook.recipe_ids
            if rid in store.data.recipes
        ]
        cookbooks.append(data)
    return {"cookbooks": cookbooks}


async def _async_update_recipe(call: ServiceCall) -> ServiceResponse:
    """Update an existing recipe."""
    entry = _get_entry(call)
    store = entry.runtime_data.store
    recipe = store.find_recipe(call.data[ATTR_RECIPE_ID])
    if not recipe:
        raise ServiceValidationError(f"Recipe not found: {call.data[ATTR_RECIPE_ID]}")

    if ATTR_NAME in call.data:
        recipe.name = call.data[ATTR_NAME]
    if ATTR_DESCRIPTION in call.data:
        recipe.description = call.data[ATTR_DESCRIPTION]
    if ATTR_INGREDIENTS in call.data:
        recipe.ingredients = [Ingredient(name=i) for i in call.data[ATTR_INGREDIENTS]]
    if ATTR_INSTRUCTIONS in call.data:
        recipe.instructions = call.data[ATTR_INSTRUCTIONS]
    if ATTR_TAGS in call.data:
        recipe.tags = call.data[ATTR_TAGS]
    if ATTR_CATEGORIES in call.data:
        recipe.categories = call.data[ATTR_CATEGORIES]

    recipe = await store.async_add_recipe(recipe)
    await _async_refresh_all(entry)
    return {"recipe": recipe.to_dict()}


async def _async_create_cookbook(call: ServiceCall) -> ServiceResponse:
    """Create a cookbook."""
    entry = _get_entry(call)
    cookbook = await entry.runtime_data.store.async_create_cookbook(
        call.data[ATTR_NAME],
        call.data.get(ATTR_DESCRIPTION),
    )
    await _async_refresh_all(entry)
    return {"cookbook": cookbook.to_dict()}


async def _async_delete_cookbook(call: ServiceCall) -> ServiceResponse:
    """Delete a cookbook."""
    entry = _get_entry(call)
    deleted = await entry.runtime_data.store.async_delete_cookbook(
        call.data[ATTR_COOKBOOK_ID]
    )
    if not deleted:
        raise ServiceValidationError(
            f"Cookbook not found: {call.data[ATTR_COOKBOOK_ID]}"
        )
    await _async_refresh_all(entry)
    return None


async def _async_add_recipe_to_cookbook(call: ServiceCall) -> ServiceResponse:
    """Add recipe to cookbook."""
    entry = _get_entry(call)
    store = entry.runtime_data.store
    try:
        cookbook = await store.async_add_recipe_to_cookbook(
            call.data[ATTR_COOKBOOK_ID],
            call.data[ATTR_RECIPE_ID],
        )
    except ValueError as err:
        raise ServiceValidationError(str(err)) from err
    await _async_refresh_all(entry)
    return {"cookbook": cookbook.to_dict()}


async def _async_remove_recipe_from_cookbook(call: ServiceCall) -> ServiceResponse:
    """Remove recipe from cookbook."""
    entry = _get_entry(call)
    store = entry.runtime_data.store
    try:
        cookbook = await store.async_remove_recipe_from_cookbook(
            call.data[ATTR_COOKBOOK_ID],
            call.data[ATTR_RECIPE_ID],
        )
    except ValueError as err:
        raise ServiceValidationError(str(err)) from err
    await _async_refresh_all(entry)
    return {"cookbook": cookbook.to_dict()}


async def _async_refresh_all(entry: EssensplanerConfigEntry) -> None:
    """Refresh all coordinators."""
    await entry.runtime_data.mealplan_coordinator.async_refresh()
    await entry.runtime_data.statistics_coordinator.async_refresh()


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register services."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_MEALPLAN,
        _async_get_mealplan,
        schema=SERVICE_GET_MEALPLAN_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_RECIPE,
        _async_get_recipe,
        schema=SERVICE_GET_RECIPE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_RECIPES,
        _async_get_recipes,
        schema=SERVICE_GET_RECIPES_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_RECIPE,
        _async_import_recipe,
        schema=SERVICE_IMPORT_RECIPE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_RECIPE,
        _async_create_recipe,
        schema=SERVICE_CREATE_RECIPE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_RECIPE,
        _async_delete_recipe,
        schema=SERVICE_DELETE_RECIPE_SCHEMA,
        supports_response=SupportsResponse.NONE,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_MEALPLAN,
        _async_set_mealplan,
        schema=SERVICE_SET_MEALPLAN_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_RANDOM_MEALPLAN,
        _async_set_random_mealplan,
        schema=SERVICE_SET_RANDOM_MEALPLAN_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_MEALPLAN,
        _async_clear_mealplan,
        schema=SERVICE_CLEAR_MEALPLAN_SCHEMA,
        supports_response=SupportsResponse.NONE,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_RECIPE_TO_SHOPPING_LIST,
        _async_add_recipe_to_shopping_list,
        schema=SERVICE_ADD_RECIPE_TO_SHOPPING_LIST_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_COOKBOOKS,
        _async_get_cookbooks,
        schema=SERVICE_GET_COOKBOOKS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_RECIPE,
        _async_update_recipe,
        schema=SERVICE_UPDATE_RECIPE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_COOKBOOK,
        _async_create_cookbook,
        schema=SERVICE_CREATE_COOKBOOK_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_COOKBOOK,
        _async_delete_cookbook,
        schema=SERVICE_DELETE_COOKBOOK_SCHEMA,
        supports_response=SupportsResponse.NONE,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_RECIPE_TO_COOKBOOK,
        _async_add_recipe_to_cookbook,
        schema=SERVICE_ADD_RECIPE_TO_COOKBOOK_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_RECIPE_FROM_COOKBOOK,
        _async_remove_recipe_from_cookbook,
        schema=SERVICE_REMOVE_RECIPE_FROM_COOKBOOK_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_GET_SHOPPING_LIST_ITEMS,
        entity_domain=TODO_DOMAIN,
        schema=None,
        func="async_get_shopping_list_items",
        supports_response=SupportsResponse.ONLY,
    )
