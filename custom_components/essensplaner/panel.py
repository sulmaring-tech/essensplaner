"""Register the Essensplaner sidebar panel."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PANEL_JS_URL, PANEL_URL_PATH

_PANEL_REGISTERED = "panel_registered"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register the Essensplaner web panel once."""
    if hass.data.setdefault(DOMAIN, {}).get(_PANEL_REGISTERED):
        return

    www_dir = Path(__file__).parent / "www"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(f"/{PANEL_URL_PATH}", str(www_dir), False)]
    )

    frontend.async_register_built_in_panel(
        component="custom",
        sidebar_title="Essensplaner",
        sidebar_icon="mdi:food",
        frontend_url_path=PANEL_URL_PATH,
        config={
            "_panel_custom": {
                "name": "panel-essensplaner",
                "js_url": PANEL_JS_URL,
                "embed_iframe": False,
            }
        },
        require_admin=False,
    )

    hass.data[DOMAIN][_PANEL_REGISTERED] = True
