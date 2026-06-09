"""Recipe import from URLs."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from bs4 import BeautifulSoup
from recipe_scrapers import scrape_html
from recipe_scrapers._abstract import AbstractScraper

from .models import Ingredient, Recipe
from .utils import generate_id, unique_slug

MEAL_TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "breakfast": (
        "frühstück",
        "fruehstueck",
        "breakfast",
        "morgen",
        "brunch",
        "müsli",
        "muesli",
        "porridge",
        "pancake",
        "pfannkuchen",
        "omelett",
        "rührei",
        "croissant",
    ),
    "lunch": (
        "mittag",
        "lunch",
        "suppe",
        "salat",
        "bowl",
        "sandwich",
        "brotzeit",
    ),
    "dinner": (
        "abend",
        "dinner",
        "abendessen",
        "hauptgericht",
        "auflauf",
        "curry",
        "pasta",
        "nudeln",
        "grill",
    ),
    "side": (
        "beilage",
        "side dish",
        "kartoffel",
        "reis",
        "gemüsebeilage",
    ),
    "dessert": (
        "dessert",
        "nachtisch",
        "kuchen",
        "torte",
        "muffin",
        "eis",
        "pudding",
        "süß",
        "suess",
    ),
    "drink": (
        "getränk",
        "getraenk",
        "drink",
        "smoothie",
        "shake",
        "cocktail",
        "limonade",
        "tee",
        "kaffee",
    ),
    "snack": (
        "snack",
        "imbiss",
        "fingerfood",
        "plätzchen",
        "keks",
        "cookie",
        "chips",
    ),
}


def suggest_meal_tags_for_recipe(recipe: Recipe) -> list[str]:
    """Suggest meal-type tags from recipe metadata."""
    haystack = " ".join(
        [
            recipe.name or "",
            recipe.description or "",
            " ".join(recipe.categories),
            " ".join(recipe.tags),
        ]
    ).lower()
    suggested: list[str] = []
    for meal_type, keywords in MEAL_TAG_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            suggested.append(meal_type)
    return suggested


if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_INGREDIENT_UNITS = (
    r"g|kg|mg|ml|l|cl|dl|EL|TL|el|tl|Stk\.?|Stück|Stk|Bund|Prise|Pkg\.?|Packung|"
    r"Dose|Becher|Tasse|MS|TL|Spritzer|Würfel|Zehe|Zweig|Scheibe|Handvoll|"
    r"Liter|Gramm|Kilogramm|Milliliter"
)
_CHEFKOCH_NAME_SUFFIX = re.compile(r"\s+von\s+.+$", re.IGNORECASE)
_CHEFKOCH_NAME_JUNK = re.compile(
    r"\s*[-–—]\s*[-–—]?\s*(das Original.*|Rezept von.*)$",
    re.IGNORECASE,
)


def _safe_scrape(callable_fn, default=None):
    """Return scraper field value, ignoring missing optional Schema.org data."""
    try:
        value = callable_fn()
        return default if value is None else value
    except Exception:
        return default


def _parse_qty(value: str) -> float | None:
    """Parse a numeric quantity string."""
    text = value.strip().replace(",", ".")
    if "/" in text:
        parts = text.split("/", 1)
        if len(parts) == 2:
            try:
                return float(parts[0].strip()) / float(parts[1].strip())
            except ValueError:
                return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_ingredient_line(text: str) -> Ingredient:
    """Parse a German ingredient line into structured parts."""
    text = text.strip()
    if not text:
        return Ingredient(name="")

    match = re.match(
        rf"^([\d]+(?:[.,]\d+)?(?:\s*/\s*[\d]+)?)\s*({_INGREDIENT_UNITS})\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    if match:
        qty = _parse_qty(match.group(1))
        return Ingredient(
            name=match.group(3).strip(),
            quantity=qty,
            unit=match.group(2),
        )

    match = re.match(
        r"^([\d]+(?:[.,]\d+)?(?:\s*/\s*[\d]+)?)\s+(.+)$",
        text,
    )
    if match:
        qty = _parse_qty(match.group(1))
        if qty is not None:
            return Ingredient(name=match.group(2).strip(), quantity=qty)

    return Ingredient(name=text)


def parse_ingredient_lines(lines: list[str]) -> list[Ingredient]:
    """Parse multiple ingredient lines."""
    return [parse_ingredient_line(line) for line in lines if line and str(line).strip()]


def normalize_servings(value: Any) -> str | None:
    """Normalize yield/servings to German portion label."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        count = int(value)
    else:
        text = str(value).strip()
        if not text:
            return None
        match = re.search(r"(\d+)", text)
        if not match:
            return text
        count = int(match.group(1))
    if count == 1:
        return "1 Portion"
    return f"{count} Portionen"


def clean_chefkoch_name(name: str | None) -> str:
    """Remove author suffix and Chefkoch title boilerplate."""
    if not name:
        return "Unbenanntes Rezept"
    text = name.strip()
    text = _CHEFKOCH_NAME_SUFFIX.sub("", text).strip()
    text = _CHEFKOCH_NAME_JUNK.sub("", text).strip(" -–—")
    return text or "Unbenanntes Rezept"


def clean_chefkoch_description(
    description: str | None, recipe_name: str | None = None
) -> str | None:
    """Keep only the recipe description without ratings and UI hints."""
    if not description:
        return None
    text = re.split(r"\s+Über\s+\d+\s+(?:Bewertungen|Kommentare)", description, 1)[0]
    text = re.split(r"\s+Mit\s+▶", text, 1)[0]
    text = re.split(r"\s+und für beliebt befunden", text, 1, flags=re.IGNORECASE)[0]
    text = re.sub(r"\s+", " ", text).strip(" .-–—")
    if recipe_name:
        prefix = f"{recipe_name} - "
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix) :].strip()
    return text or None


def _json_ld_recipes(html: str) -> list[dict[str, Any]]:
    """Extract Recipe objects from JSON-LD blocks."""
    soup = BeautifulSoup(html, "html.parser")
    recipes: list[dict[str, Any]] = []
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            recipes.extend(
                item for item in data if isinstance(item, dict) and item.get("@type") == "Recipe"
            )
        elif isinstance(data, dict):
            if data.get("@type") == "Recipe":
                recipes.append(data)
            graph = data.get("@graph")
            if isinstance(graph, list):
                recipes.extend(
                    item for item in graph if isinstance(item, dict) and item.get("@type") == "Recipe"
                )
    return recipes


def _chefkoch_ingredients_from_html(html: str) -> list[str] | None:
    """Read ingredient lines from Chefkoch JSON-LD."""
    for recipe in _json_ld_recipes(html):
        raw = recipe.get("recipeIngredient") or recipe.get("ingredients") or []
        if not raw:
            continue
        lines = [str(item).strip() for item in raw if str(item).strip()]
        if lines:
            return lines
    return None


def _chefkoch_meta_from_html(html: str) -> dict[str, Any]:
    """Extract name, description and yield from Chefkoch page metadata."""
    meta: dict[str, Any] = {}
    soup = BeautifulSoup(html, "html.parser")

    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        meta["description"] = og_desc["content"].strip()

    for recipe in _json_ld_recipes(html):
        if recipe.get("name"):
            meta["name"] = str(recipe["name"]).strip()
        if recipe.get("description") and "description" not in meta:
            meta["description"] = str(recipe["description"]).strip()
        if recipe.get("recipeYield"):
            meta["yield"] = recipe["recipeYield"]
        break

    return meta


def _apply_chefkoch_cleanup(html: str, recipe: Recipe) -> Recipe:
    """Normalize Chefkoch-specific title, description, portions and ingredients."""
    meta = _chefkoch_meta_from_html(html)
    name = clean_chefkoch_name(meta.get("name") or recipe.name)
    recipe.name = name

    description = meta.get("description") or recipe.description
    recipe.description = clean_chefkoch_description(description, name)

    ingredient_lines = _chefkoch_ingredients_from_html(html)
    if ingredient_lines:
        recipe.ingredients = parse_ingredient_lines(ingredient_lines)

    yield_value = meta.get("yield") or recipe.servings
    recipe.servings = normalize_servings(yield_value)
    return recipe


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

    ingredients = parse_ingredient_lines(ingredients_raw)
    recipe_id = generate_id()
    slug = unique_slug(name, set())
    yields_value = _safe_scrape(scraper.yields)
    category = _safe_scrape(scraper.category)

    recipe = Recipe(
        id=recipe_id,
        slug=slug,
        name=name,
        description=_safe_scrape(scraper.description),
        ingredients=ingredients,
        instructions=instructions_raw,
        image_url=_safe_scrape(scraper.image),
        servings=normalize_servings(yields_value) if yields_value else None,
        cook_time=_safe_scrape(scraper.cook_time),
        prep_time=_safe_scrape(scraper.prep_time),
        source_url=url,
        categories=[category] if category else [],
    )

    if "chefkoch.de" in url:
        recipe = _apply_chefkoch_cleanup(html, recipe)
        recipe.slug = unique_slug(recipe.name, set())

    return recipe


async def _async_fetch_recipe_html(hass: HomeAssistant, url: str) -> str:
    """Download recipe page HTML."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    session = async_get_clientsession(hass)
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.text()


async def async_preview_recipe_from_url(hass: HomeAssistant, url: str) -> Recipe:
    """Fetch and scrape a recipe from URL without saving."""
    html = await _async_fetch_recipe_html(hass, url)
    return await hass.async_add_executor_job(_scrape_recipe, url, html)


async def async_import_recipe_from_url(
    hass: HomeAssistant, url: str, include_tags: bool = False, *, suggest_meal_tags: bool = False
) -> Recipe:
    """Fetch and scrape a recipe from URL."""
    recipe = await async_preview_recipe_from_url(hass, url)

    if include_tags and recipe.categories:
        recipe.tags = list(recipe.categories)

    if suggest_meal_tags:
        existing = set(recipe.tags)
        for tag in suggest_meal_tags_for_recipe(recipe):
            if tag not in existing:
                recipe.tags.append(tag)
                existing.add(tag)

    return recipe
