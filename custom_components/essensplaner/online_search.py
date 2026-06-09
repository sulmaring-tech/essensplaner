"""Online recipe search for inspiration and import."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import quote

from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

CHEFKOCH_BASE = "https://www.chefkoch.de"
USER_AGENT = (
    "Mozilla/5.0 (compatible; Essensplaner/1.0; +https://github.com/sulmaring-tech/essensplaner)"
)


@dataclass
class OnlineRecipeSearchResult:
    """Recipe found via online search."""

    title: str
    url: str
    image_url: str | None = None
    source: str = "chefkoch"

    def to_dict(self) -> dict[str, str | None]:
        """Return API-friendly dict."""
        return {
            "title": self.title,
            "url": self.url,
            "image_url": self.image_url,
            "source": self.source,
        }


def _parse_chefkoch_search(html: str, limit: int) -> list[OnlineRecipeSearchResult]:
    """Parse Chefkoch search result page."""
    soup = BeautifulSoup(html, "html.parser")
    results: list[OnlineRecipeSearchResult] = []
    seen_urls: set[str] = set()

    for card in soup.select("div.ds-recipe-card"):
        link = card.find("a", href=True)
        heading = card.find("h3")
        if not link or not heading:
            continue

        title = heading.get_text(strip=True)
        href = link["href"].split("#")[0]
        if href.startswith("/"):
            href = f"{CHEFKOCH_BASE}{href}"
        if href in seen_urls or "/rezept" not in href:
            continue

        image = card.find("img")
        image_url = None
        if image:
            image_url = image.get("src") or image.get("data-src")

        seen_urls.add(href)
        results.append(
            OnlineRecipeSearchResult(
                title=title,
                url=href,
                image_url=image_url,
                source="chefkoch",
            )
        )
        if len(results) >= limit:
            break

    return results


async def async_search_recipes_online(
    hass: HomeAssistant, query: str, limit: int = 12
) -> list[dict[str, str | None]]:
    """Search Chefkoch for recipes matching the query."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    query = query.strip()
    if len(query) < 2:
        raise ValueError("Suchbegriff muss mindestens 2 Zeichen lang sein")

    limit = max(1, min(limit, 24))
    search_url = f"{CHEFKOCH_BASE}/rs/s0/{quote(query)}/Rezepte.html"
    session = async_get_clientsession(hass)
    headers = {"User-Agent": USER_AGENT}

    async with session.get(search_url, headers=headers) as response:
        response.raise_for_status()
        html = await response.text()

    return [item.to_dict() for item in _parse_chefkoch_search(html, limit)]
