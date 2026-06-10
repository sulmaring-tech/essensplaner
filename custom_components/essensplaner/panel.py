"""Register the Essensplaner sidebar panel."""

from __future__ import annotations

from pathlib import Path

import voluptuous as vol

from homeassistant.components import panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback

from .const import (
    DOMAIN,
    LOVELACE_CARD_URLS,
    LOGGER,
    MAX_RECIPES_PER_ROW,
    MIN_RECIPES_PER_ROW,
    OPTION_DEFAULT_SHOPPING_LIST_ID,
    OPTION_DEFAULT_WEEK,
    OPTION_RECIPES_PER_ROW,
    OPTION_RECIPE_SORT,
    OPTION_SHOW_RECIPE_IMAGES,
    OPTION_SUGGEST_MEAL_TAGS_ON_IMPORT,
    OPTION_TILE_SIZE,
    OPTION_VISIBLE_MEAL_TYPES,
    OPTION_WEEK_START,
    PANEL_JS_URL,
    PANEL_STATIC_PATH,
    PANEL_URL_PATH,
)
from .meal_times import meal_times_to_api, merge_meal_times_from_api
from .panel_options import merge_panel_options, panel_options_to_api
from .panel_stats import get_panel_statistics
from .shopping_targets import (
    is_valid_target,
    normalize_stored_target,
    shopping_lists_for_panel,
)
from .online_search import async_search_recipes_online
from .recipe_importer import async_preview_recipe_from_url

_PANEL_REGISTERED = "panel_registered"
_STATIC_REGISTERED = "static_registered"
_LOVELACE_CARD_REGISTERED = "lovelace_card_registered"
_WS_REGISTERED = "ws_registered"
_PANEL_WS_VERSION = 6
_PANEL_WS_VERSION_KEY = "panel_ws_version"


def _panel_entries(hass: HomeAssistant) -> list[dict[str, str]]:
    """Return config entries for the panel."""
    return [
        {"entry_id": entry.entry_id, "title": entry.title}
        for entry in hass.config_entries.async_entries(DOMAIN)
    ]


def _panel_settings(hass: HomeAssistant, entry) -> dict:
    """Return panel configuration for an entry."""
    runtime = getattr(entry, "runtime_data", None)
    if runtime is None:
        raise RuntimeError("Essensplaner is not fully loaded")
    store = runtime.store
    store.ensure_shopping_lists()
    shopping_lists = shopping_lists_for_panel(hass, entry)
    default_list_id = normalize_stored_target(
        entry.options.get(OPTION_DEFAULT_SHOPPING_LIST_ID), store
    )
    if not default_list_id and shopping_lists:
        default_list_id = shopping_lists[0]["id"]
    return {
        "meal_times": meal_times_to_api(entry.options),
        "shopping_lists": shopping_lists,
        "default_shopping_list_id": default_list_id,
        **panel_options_to_api(store, entry.options),
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
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(_PANEL_WS_VERSION_KEY) == _PANEL_WS_VERSION:
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
        try:
            store = entry.runtime_data.store
            if not store.get_shopping_lists():
                store.ensure_shopping_lists()
                await store._async_save()
            settings = _panel_settings(hass, entry)
        except Exception as err:  # noqa: BLE001
            LOGGER.exception("Panel settings failed")
            connection.send_error(msg["id"], "settings_failed", str(err))
            return
        connection.send_result(msg["id"], settings)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/get_statistics",
            vol.Required("entry_id"): str,
        }
    )
    @websocket_api.async_response
    async def ws_get_statistics(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        entry = _get_config_entry(hass, msg["entry_id"])
        if entry is None:
            connection.send_error(msg["id"], "not_found", "Config entry not found")
            return
        try:
            stats = get_panel_statistics(entry.runtime_data.store)
        except Exception as err:  # noqa: BLE001
            LOGGER.exception("Panel statistics failed")
            connection.send_error(msg["id"], "statistics_failed", str(err))
            return
        connection.send_result(msg["id"], stats)

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
        list_id = msg["list_id"]
        if not is_valid_target(hass, entry, list_id):
            connection.send_error(msg["id"], "not_found", "Shopping list not found")
            return
        options = dict(entry.options)
        options[OPTION_DEFAULT_SHOPPING_LIST_ID] = list_id
        hass.config_entries.async_update_entry(entry, options=options)
        connection.send_result(msg["id"], _panel_settings(hass, entry))

    @websocket_api.require_admin
    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/set_recipes_per_row",
            vol.Required("entry_id"): str,
            vol.Required("columns"): vol.All(
                vol.Coerce(int), vol.Range(min=MIN_RECIPES_PER_ROW, max=MAX_RECIPES_PER_ROW)
            ),
        }
    )
    @websocket_api.async_response
    async def ws_set_recipes_per_row(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        entry = _get_config_entry(hass, msg["entry_id"])
        if entry is None:
            connection.send_error(msg["id"], "not_found", "Config entry not found")
            return
        options = dict(entry.options)
        options[OPTION_RECIPES_PER_ROW] = msg["columns"]
        hass.config_entries.async_update_entry(entry, options=options)
        connection.send_result(msg["id"], _panel_settings(hass, entry))

    @websocket_api.require_admin
    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/set_panel_options",
            vol.Required("entry_id"): str,
            vol.Optional(OPTION_RECIPES_PER_ROW): vol.All(
                vol.Coerce(int), vol.Range(min=MIN_RECIPES_PER_ROW, max=MAX_RECIPES_PER_ROW)
            ),
            vol.Optional(OPTION_VISIBLE_MEAL_TYPES): [str],
            vol.Optional(OPTION_WEEK_START): str,
            vol.Optional(OPTION_DEFAULT_WEEK): str,
            vol.Optional(OPTION_RECIPE_SORT): str,
            vol.Optional(OPTION_TILE_SIZE): str,
            vol.Optional(OPTION_SHOW_RECIPE_IMAGES): bool,
            vol.Optional(OPTION_SUGGEST_MEAL_TAGS_ON_IMPORT): bool,
        }
    )
    @websocket_api.async_response
    async def ws_set_panel_options(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        entry = _get_config_entry(hass, msg["entry_id"])
        if entry is None:
            connection.send_error(msg["id"], "not_found", "Config entry not found")
            return
        updates = {
            key: msg[key]
            for key in (
                OPTION_RECIPES_PER_ROW,
                OPTION_VISIBLE_MEAL_TYPES,
                OPTION_WEEK_START,
                OPTION_DEFAULT_WEEK,
                OPTION_RECIPE_SORT,
                OPTION_TILE_SIZE,
                OPTION_SHOW_RECIPE_IMAGES,
                OPTION_SUGGEST_MEAL_TAGS_ON_IMPORT,
            )
            if key in msg
        }
        if not updates:
            connection.send_error(msg["id"], "invalid_options", "No options provided")
            return
        options = merge_panel_options(entry.options, updates)
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
    websocket_api.async_register_command(hass, ws_get_statistics)
    websocket_api.async_register_command(hass, ws_set_meal_times)
    websocket_api.async_register_command(hass, ws_set_default_shopping_list)
    websocket_api.async_register_command(hass, ws_set_recipes_per_row)
    websocket_api.async_register_command(hass, ws_set_panel_options)
    websocket_api.async_register_command(hass, ws_search_recipes_online)
    websocket_api.async_register_command(hass, ws_preview_recipe_url)
    hass.data[DOMAIN][_WS_REGISTERED] = True
    hass.data[DOMAIN][_PANEL_WS_VERSION_KEY] = _PANEL_WS_VERSION


async def _async_register_static(hass: HomeAssistant, www_dir: Path) -> None:
    """Serve panel and Lovelace card JS from /essensplaner_static."""
    if hass.data.setdefault(DOMAIN, {}).get(_STATIC_REGISTERED):
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_STATIC_PATH, str(www_dir), False)]
    )
    hass.data[DOMAIN][_STATIC_REGISTERED] = True


async def _async_register_lovelace_card(hass: HomeAssistant) -> None:
    """Add Essensplaner Lovelace card resources if missing."""

    async def _register() -> None:
        from homeassistant.components.lovelace.const import DOMAIN as LOVELACE_DOMAIN

        lovelace_data = hass.data.get(LOVELACE_DOMAIN)
        if lovelace_data is None:
            return

        resources = lovelace_data.resources
        await resources.async_get_info()
        existing_urls = [item.get("url", "") for item in resources.async_items()]
        for url in LOVELACE_CARD_URLS:
            if any(url in existing for existing in existing_urls):
                continue
            await resources.async_create_item({"res_type": "module", "url": url})
            LOGGER.info("Lovelace card resource registered: %s", url)

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
