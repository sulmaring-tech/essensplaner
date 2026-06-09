"""Register the Essensplaner sidebar panel."""

from __future__ import annotations

from pathlib import Path

import voluptuous as vol

from homeassistant.components import panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, LOGGER, PANEL_JS_URL, PANEL_STATIC_PATH, PANEL_URL_PATH

_PANEL_REGISTERED = "panel_registered"
_WS_REGISTERED = "ws_registered"


def _panel_entries(hass: HomeAssistant) -> list[dict[str, str]]:
    """Return config entries for the panel."""
    return [
        {"entry_id": entry.entry_id, "title": entry.title}
        for entry in hass.config_entries.async_entries(DOMAIN)
    ]


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

    websocket_api.async_register_command(hass, ws_config_entries)
    hass.data[DOMAIN][_WS_REGISTERED] = True


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register the Essensplaner web panel once."""
    _async_register_ws(hass)

    if hass.data.setdefault(DOMAIN, {}).get(_PANEL_REGISTERED):
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
        config={"entries": _panel_entries(hass)},
    )

    hass.data[DOMAIN][_PANEL_REGISTERED] = True
    LOGGER.info(
        "Essensplaner panel registered at /%s (static: %s)",
        PANEL_URL_PATH,
        PANEL_STATIC_PATH,
    )
