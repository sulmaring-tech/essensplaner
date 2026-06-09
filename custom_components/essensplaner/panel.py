"""Register the Essensplaner sidebar panel."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN, LOGGER, PANEL_JS_URL, PANEL_URL_PATH

_PANEL_REGISTERED = "panel_registered"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register the Essensplaner web panel once."""
    if hass.data.setdefault(DOMAIN, {}).get(_PANEL_REGISTERED):
        return

    www_dir = Path(__file__).parent / "www"
    if not (www_dir / "panel.js").is_file():
        LOGGER.error("Panel JS not found at %s", www_dir / "panel.js")
        return

    await hass.http.async_register_static_paths(
        [StaticPathConfig(f"/{PANEL_URL_PATH}", str(www_dir), False)]
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
    )

    hass.data[DOMAIN][_PANEL_REGISTERED] = True
    LOGGER.info("Essensplaner panel registered at /%s", PANEL_URL_PATH)
