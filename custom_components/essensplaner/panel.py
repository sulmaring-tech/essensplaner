"""Register the Essensplaner sidebar panel."""

from __future__ import annotations

from pathlib import Path

import voluptuous as vol

from homeassistant.components import panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.todo import DOMAIN as TODO_DOMAIN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    LOVELACE_CARD_URL,
    LOGGER,
    OPTION_DEFAULT_SHOPPING_LIST_ID,
    PANEL_JS_URL,
    PANEL_STATIC_PATH,
    PANEL_URL_PATH,
)
from .meal_times import meal_times_to_api, merge_meal_times_from_api
from .online_search import async_search_recipes_online
from .recipe_importer import async_preview_recipe_from_url

_PANEL_REGISTERED = "panel_registered"
_STATIC_REGISTERED = "static_registered"
_LOVELACE_CARD_REGISTERED = "lovelace_card_registered"
_WS_REGISTERED = "ws_registered"


def _panel_entries(hass: HomeAssistant) -> list[dict[str, str]]:
    """Return config entries for the panel."""
    return [
        {"entry_id": entry.entry_id, "title": entry.title}
        for entry in hass.config_entries.async_entries(DOMAIN)
    ]


def _shopping_lists_for_panel(hass: HomeAssistant, entry) -> list[dict[str, str | None]]:
    """Return shopping lists with linked todo entity ids."""
    store = entry.runtime_data.store
    entity_registry = er.async_get(hass)
    unique_id = entry.unique_id
    result: list[dict[str, str | None]] = []
    for shopping_list in store.get_shopping_lists():
        entity_id = None
        if unique_id:
            entity_id = entity_registry.async_get_entity_id(
                TODO_DOMAIN, DOMAIN, f"{unique_id}_{shopping_list.id}"
            )
        result.append(
            {
                "id": shopping_list.id,
                "name": shopping_list.name,
                "entity_id": entity_id,
            }
        )
    return result


def _panel_settings(hass: HomeAssistant, entry) -> dict:
    """Return panel configuration for an entry."""
    shopping_lists = _shopping_lists_for_panel(hass, entry)
    default_list_id = entry.options.get(OPTION_DEFAULT_SHOPPING_LIST_ID)
    if not default_list_id and shopping_lists:
        default_list_id = shopping_lists[0]["id"]
    return {
        "meal_times": meal_times_to_api(entry.options),
        "shopping_lists": shopping_lists,
        "default_shopping_list_id": default_list_id,
    }


def _get_config_entry(hass: HomeAssistant, entry_id: str):
    """Return Essensplaner config entry or None."""
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        return None
    return entry


@callback
def async_setup_frontend(hass: HomeAssistant) -> None:
    """Register panel websocket commands."""
    _async_register_ws(hass)


@callback
def _async_register_ws(hass: HomeAssistant) -> None:
    """Register websocket commands for the panel."""
    if hass.data.setdefault(DOMAIN, {}).get(_WS_REGISTERED):
        return

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/config_entries"})
    @websocket_api.async_response
    async def ws_config_entries(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        connection.send_result(msg["id"], _panel_entries(hass))

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/get_meal_times",
            vol.Required("entry_id"): str,
        }
    )
    @websocket_api.async_response
    async def ws_get_meal_times(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        entry = _get_config_entry(hass, msg["entry_id"])
        if entry is None:
            connection.send_error(msg["id"], "not_found", "Config entry not found")
            return
        connection.send_result(msg["id"], meal_times_to_api(entry.options))

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/get_panel_settings",
            vol.Required("entry_id"): str,
        }
    )
    @websocket_api.async_response
    async def ws_get_panel_settings(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        entry = _get_config_entry(hass, msg["entry_id"])
        if entry is None:
            connection.send_error(msg["id"], "not_found", "Config entry not found")
            return
        connection.send_result(msg["id"], _panel_settings(hass, entry))

    @websocket_api.require_admin
    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/set_meal_times",
            vol.Required("entry_id"): str,
            vol.Required("meal_times"): {
                str: vol.Schema(
                    {
                        vol.Required("start"): str,
                        vol.Required("end"): str,
                    }
                )
            },
        }
    )
    @websocket_api.async_response
    async def ws_set_meal_times(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        entry = _get_config_entry(hass, msg["entry_id"])
        if entry is None:
            connection.send_error(msg["id"], "not_found", "Config entry not found")
            return
        try:
            options = merge_meal_times_from_api(entry.options, msg["meal_times"])
        except ValueError as err:
            connection.send_error(msg["id"], "invalid_times", str(err))
            return
        hass.config_entries.async_update_entry(entry, options=options)
        connection.send_result(msg["id"], meal_times_to_api(options))

    @websocket_api.require_admin
    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/set_default_shopping_list",
            vol.Required("entry_id"): str,
            vol.Required("list_id"): str,
        }
    )
    @websocket_api.async_response
    async def ws_set_default_shopping_list(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        entry = _get_config_entry(hass, msg["entry_id"])
        if entry is None:
            connection.send_error(msg["id"], "not_found", "Config entry not found")
            return
        store = entry.runtime_data.store
        list_id = msg["list_id"]
        if list_id not in {lst.id for lst in store.get_shopping_lists()}:
            connection.send_error(msg["id"], "not_found", "Shopping list not found")
            return
        options = dict(entry.options)
        options[OPTION_DEFAULT_SHOPPING_LIST_ID] = list_id
        hass.config_entries.async_update_entry(entry, options=options)
        connection.send_result(msg["id"], _panel_settings(hass, entry))

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/search_recipes_online",
            vol.Required("query"): str,
            vol.Optional("limit"): vol.All(vol.Coerce(int), vol.Range(min=1, max=24)),
        }
    )
    @websocket_api.async_response
    async def ws_search_recipes_online(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        try:
            results = await async_search_recipes_online(
                hass, msg["query"], msg.get("limit", 12)
            )
        except ValueError as err:
            connection.send_error(msg["id"], "invalid_query", str(err))
            return
        except Exception as err:
            connection.send_error(msg["id"], "search_failed", str(err))
            return
        connection.send_result(msg["id"], {"results": results})

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/preview_recipe_url",
            vol.Required("url"): str,
        }
    )
    @websocket_api.async_response
    async def ws_preview_recipe_url(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        url = msg["url"].strip()
        if not url:
            connection.send_error(msg["id"], "invalid_url", "URL fehlt")
            return
        try:
            recipe = await async_preview_recipe_from_url(hass, url)
        except Exception as err:
            connection.send_error(msg["id"], "preview_failed", str(err))
            return
        connection.send_result(msg["id"], {"recipe": recipe.to_dict()})

    websocket_api.async_register_command(hass, ws_config_entries)
    websocket_api.async_register_command(hass, ws_get_meal_times)
    websocket_api.async_register_command(hass, ws_get_panel_settings)
    websocket_api.async_register_command(hass, ws_set_meal_times)
    websocket_api.async_register_command(hass, ws_set_default_shopping_list)
    websocket_api.async_register_command(hass, ws_search_recipes_online)
    websocket_api.async_register_command(hass, ws_preview_recipe_url)
    hass.data[DOMAIN][_WS_REGISTERED] = True


async def _async_register_static(hass: HomeAssistant, www_dir: Path) -> None:
    """Serve panel and Lovelace card JS from /essensplaner_static."""
    if hass.data.setdefault(DOMAIN, {}).get(_STATIC_REGISTERED):
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_STATIC_PATH, str(www_dir), False)]
    )
    hass.data[DOMAIN][_STATIC_REGISTERED] = True


async def _async_register_lovelace_card(hass: HomeAssistant) -> None:
    """Add the today-mealplan Lovelace card resource if missing."""
    if hass.data.setdefault(DOMAIN, {}).get(_LOVELACE_CARD_REGISTERED):
        return

    async def _register() -> None:
        from homeassistant.components.lovelace.const import DOMAIN as LOVELACE_DOMAIN

        lovelace_data = hass.data.get(LOVELACE_DOMAIN)
        if lovelace_data is None:
            return

        resources = lovelace_data.resources
        await resources.async_get_info()
        for item in resources.async_items():
            if "today-mealplan-card.js" in item.get("url", ""):
                hass.data[DOMAIN][_LOVELACE_CARD_REGISTERED] = True
                return

        await resources.async_create_item(
            {"res_type": "module", "url": LOVELACE_CARD_URL}
        )
        hass.data[DOMAIN][_LOVELACE_CARD_REGISTERED] = True
        LOGGER.info("Lovelace card resource registered: %s", LOVELACE_CARD_URL)

    if "lovelace" in hass.config.components:
        await _register()
        return

    @callback
    def _on_component_loaded(event) -> None:
        if event.data.get("component") != "lovelace":
            return
        hass.async_create_task(_register())

    hass.bus.async_listen_once("component_loaded", _on_component_loaded)


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register the Essensplaner web panel once."""
    _async_register_ws(hass)

    entries = _panel_entries(hass)
    hass.data.setdefault(DOMAIN, {})["panel_entries"] = entries

    www_dir = Path(__file__).parent / "www"
    if not (www_dir / "panel.js").is_file():
        LOGGER.error("Panel JS not found at %s", www_dir / "panel.js")
        return

    # Static files must NOT share the frontend_url_path or /essensplaner returns 403.
    await _async_register_static(hass, www_dir)
    await _async_register_lovelace_card(hass)

    if hass.data[DOMAIN].get(_PANEL_REGISTERED):
        return

    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name="panel-essensplaner",
        sidebar_title="Essensplaner",
        sidebar_icon="mdi:food",
        js_url=PANEL_JS_URL,
        embed_iframe=False,
        require_admin=False,
        config={"entries": entries},
    )

    hass.data[DOMAIN][_PANEL_REGISTERED] = True
    LOGGER.info(
        "Essensplaner panel registered at /%s (static: %s)",
        PANEL_URL_PATH,
        PANEL_STATIC_PATH,
    )
