"""Register the Essensplaner sidebar panel."""

from __future__ import annotations

from pathlib import Path

import voluptuous as vol

from homeassistant.components import panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, LOGGER, PANEL_JS_URL, PANEL_STATIC_PATH, PANEL_URL_PATH
from .meal_times import meal_times_to_api, merge_meal_times_from_api
from .online_search import async_search_recipes_online

_PANEL_REGISTERED = "panel_registered"
_WS_REGISTERED = "ws_registered"


def _panel_entries(hass: HomeAssistant) -> list[dict[str, str]]:
    """Return config entries for the panel."""
    return [
        {"entry_id": entry.entry_id, "title": entry.title}
        for entry in hass.config_entries.async_entries(DOMAIN)
    ]


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

    websocket_api.async_register_command(hass, ws_config_entries)
    websocket_api.async_register_command(hass, ws_get_meal_times)
    websocket_api.async_register_command(hass, ws_set_meal_times)
    websocket_api.async_register_command(hass, ws_search_recipes_online)
    hass.data[DOMAIN][_WS_REGISTERED] = True


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register the Essensplaner web panel once."""
    _async_register_ws(hass)

    entries = _panel_entries(hass)
    if hass.data.setdefault(DOMAIN, {}).get(_PANEL_REGISTERED):
        hass.data[DOMAIN]["panel_entries"] = entries
        return

    www_dir = Path(__file__).parent / "www"
    if not (www_dir / "panel.js").is_file():
        LOGGER.error("Panel JS not found at %s", www_dir / "panel.js")
        return

    # Static files must NOT share the frontend_url_path or /essensplaner returns 403.
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_STATIC_PATH, str(www_dir), False)]
    )

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
