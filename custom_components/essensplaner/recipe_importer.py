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
    name = scraper.title() or "Unbenanntes Rezept"
    ingredients_raw = scraper.ingredients() or []
    instructions_raw = scraper.instructions_list() or []
    if not instructions_raw and scraper.instructions():
        instructions_raw = [
            s.strip() for s in scraper.instructions().split("\n") if s.strip()
        ]

    ingredients = [_parse_ingredient(i) for i in ingredients_raw]
    recipe_id = generate_id()
    slug = unique_slug(name, set())

    return Recipe(
        id=recipe_id,
        slug=slug,
        name=name,
        description=scraper.description(),
        ingredients=ingredients,
        instructions=instructions_raw,
        image_url=scraper.image(),
        servings=str(scraper.yields()) if scraper.yields() else None,
        cook_time=scraper.cook_time(),
        prep_time=scraper.prep_time(),
        source_url=url,
        categories=[scraper.category()] if scraper.category() else [],
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
