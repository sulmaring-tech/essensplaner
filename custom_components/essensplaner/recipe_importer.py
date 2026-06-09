"""Recipe import from URLs."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from recipe_scrapers import scrape_html
from recipe_scrapers._abstract import AbstractScraper

from .models import Ingredient, Recipe
from .utils import generate_id, unique_slug

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def _safe_scrape(callable_fn, default=None):
    """Return scraper field value, ignoring missing optional Schema.org data."""
    try:
        value = callable_fn()
        return default if value is None else value
    except Exception:
        return default


def _parse_ingredient(text: str) -> Ingredient:
    """Parse ingredient string into structured parts."""
    text = text.strip()
    match = re.match(
        r"^([\d.,/]+)\s*([a-zA-ZäöüÄÖÜß]+)?\s+(.+)$",
        text,
    )
    if match:
        qty_str, unit, name = match.groups()
        try:
            qty = float(qty_str.replace(",", "."))
        except ValueError:
            return Ingredient(name=text)
        return Ingredient(name=name.strip(), quantity=qty, unit=unit)
    return Ingredient(name=text)


def _scrape_recipe(url: str, html: str) -> Recipe:
    """Scrape recipe from HTML."""
    scraper: AbstractScraper = scrape_html(html, org_url=url)
    name = _safe_scrape(scraper.title) or "Unbenanntes Rezept"
    ingredients_raw = _safe_scrape(scraper.ingredients, []) or []
    instructions_raw = _safe_scrape(scraper.instructions_list, []) or []
    if not instructions_raw:
        instructions_text = _safe_scrape(scraper.instructions)
        if instructions_text:
            instructions_raw = [
                s.strip() for s in instructions_text.split("\n") if s.strip()
            ]

    ingredients = [_parse_ingredient(i) for i in ingredients_raw]
    recipe_id = generate_id()
    slug = unique_slug(name, set())
    yields_value = _safe_scrape(scraper.yields)
    category = _safe_scrape(scraper.category)

    return Recipe(
        id=recipe_id,
        slug=slug,
        name=name,
        description=_safe_scrape(scraper.description),
        ingredients=ingredients,
        instructions=instructions_raw,
        image_url=_safe_scrape(scraper.image),
        servings=str(yields_value) if yields_value else None,
        cook_time=_safe_scrape(scraper.cook_time),
        prep_time=_safe_scrape(scraper.prep_time),
        source_url=url,
        categories=[category] if category else [],
    )


async def async_import_recipe_from_url(
    hass: HomeAssistant, url: str, include_tags: bool = False
) -> Recipe:
    """Fetch and scrape a recipe from URL."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    session = async_get_clientsession(hass)
    async with session.get(url) as response:
        response.raise_for_status()
        html = await response.text()

    recipe = await hass.async_add_executor_job(_scrape_recipe, url, html)

    if include_tags and recipe.categories:
        recipe.tags = list(recipe.categories)

    return recipe
