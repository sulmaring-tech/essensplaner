"""Shopping list targets (Essensplaner internal and external todo lists)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from homeassistant.components.todo import DOMAIN as TODO_DOMAIN
from homeassistant.helpers import entity_registry as er

from .const import LOGGER, OPTION_DEFAULT_SHOPPING_LIST_ID
from .models import Ingredient, Recipe

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import EssensplanerConfigEntry
    from .storage import EssensplanerStore

TARGET_ESSENSPLANER = "essensplaner"
TARGET_BRING = "bring"
BRING_PLATFORM = "bring"


@dataclass(frozen=True)
class ShoppingTarget:
    """Resolved shopping list target."""

    source: Literal["essensplaner", "bring"]
    target_id: str
    name: str
    entity_id: str | None = None


def format_ingredient_display(ingredient: Ingredient) -> str:
    """Format ingredient for shopping list display."""
    if ingredient.quantity and ingredient.unit:
        return f"{ingredient.quantity:g} {ingredient.unit} {ingredient.name}"
    if ingredient.quantity:
        return f"{ingredient.quantity:g} {ingredient.name}"
    return ingredient.name


def encode_target(source: str, target_id: str) -> str:
    """Encode a target for storage in config options."""
    return f"{source}:{target_id}"


def normalize_stored_target(
    value: str | None, store: EssensplanerStore
) -> str | None:
    """Normalize legacy internal ids and validate format."""
    if not value:
        lists = store.get_shopping_lists()
        if lists:
            return encode_target(TARGET_ESSENSPLANER, lists[0].id)
        return None
    if ":" not in value:
        return encode_target(TARGET_ESSENSPLANER, value)
    return value


def parse_encoded_target(value: str) -> tuple[str, str]:
    """Split encoded target into source and id."""
    source, _, target_id = value.partition(":")
    if not target_id:
        raise ValueError(f"Invalid shopping list target: {value}")
    return source, target_id


def _essensplaner_targets(
    hass: HomeAssistant, entry: EssensplanerConfigEntry
) -> list[dict[str, Any]]:
    """Return Essensplaner shopping lists for the panel."""
    store = entry.runtime_data.store
    entity_registry = er.async_get(hass)
    unique_id = entry.unique_id
    result: list[dict[str, Any]] = []
    for shopping_list in store.get_shopping_lists():
        entity_id = None
        if unique_id:
            entity_id = entity_registry.async_get_entity_id(
                TODO_DOMAIN, entry.domain, f"{unique_id}_{shopping_list.id}"
            )
        result.append(
            {
                "id": encode_target(TARGET_ESSENSPLANER, shopping_list.id),
                "name": shopping_list.name,
                "entity_id": entity_id,
                "source": TARGET_ESSENSPLANER,
            }
        )
    return result


def _bring_display_name(hass: HomeAssistant, entity_id: str, fallback: str) -> str:
    """Return a user-facing name for a Bring todo entity."""
    state = hass.states.get(entity_id)
    if state and state.name:
        return state.name
    return fallback or entity_id


def _bring_registry_entries(entity_registry: er.EntityRegistry) -> list:
    """Return Bring todo entities from the entity registry."""
    entries_for_platform = getattr(er, "async_entries_for_platform", None)
    if callable(entries_for_platform):
        return list(entries_for_platform(entity_registry, BRING_PLATFORM))
    return [
        entry
        for entry in entity_registry.entities.values()
        if entry.platform == BRING_PLATFORM
    ]


def _todo_entity_ids(hass: HomeAssistant) -> list[str]:
    """Return all todo entity ids."""
    return hass.states.entity_ids(TODO_DOMAIN)


def _bring_targets(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Return Bring! todo lists for the panel."""
    entity_registry = er.async_get(hass)
    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    for entity_entry in _bring_registry_entries(entity_registry):
        if entity_entry.domain != TODO_DOMAIN:
            continue
        seen.add(entity_entry.entity_id)
        fallback = entity_entry.name or entity_entry.original_name or entity_entry.entity_id
        result.append(
            {
                "id": encode_target(TARGET_BRING, entity_entry.entity_id),
                "name": _bring_display_name(hass, entity_entry.entity_id, fallback),
                "entity_id": entity_entry.entity_id,
                "source": TARGET_BRING,
            }
        )

    for entity_id in _todo_entity_ids(hass):
        if entity_id in seen:
            continue
        entity_entry = entity_registry.async_get(entity_id)
        if entity_entry is None or entity_entry.platform != BRING_PLATFORM:
            continue
        fallback = entity_entry.name or entity_entry.original_name or entity_id
        result.append(
            {
                "id": encode_target(TARGET_BRING, entity_id),
                "name": _bring_display_name(hass, entity_id, fallback),
                "entity_id": entity_id,
                "source": TARGET_BRING,
            }
        )

    return sorted(result, key=lambda item: item["name"].casefold())


def shopping_lists_for_panel(
    hass: HomeAssistant, entry: EssensplanerConfigEntry
) -> list[dict[str, Any]]:
    """Return all selectable shopping list targets."""
    result = _essensplaner_targets(hass, entry)
    try:
        result.extend(_bring_targets(hass))
    except Exception as err:  # noqa: BLE001
        LOGGER.warning("Bring shopping lists could not be loaded: %s", err)
    return result


def resolve_target(
    value: str | None,
    options: dict[str, Any],
    store: EssensplanerStore,
) -> ShoppingTarget:
    """Resolve configured target to a ShoppingTarget."""
    normalized = normalize_stored_target(
        value or options.get(OPTION_DEFAULT_SHOPPING_LIST_ID), store
    )
    if not normalized:
        raise ValueError("No shopping list configured")

    source, target_id = parse_encoded_target(normalized)
    if source == TARGET_ESSENSPLANER:
        shopping_list = store.data.shopping_lists.get(target_id)
        if shopping_list is None:
            raise ValueError(f"Shopping list not found: {target_id}")
        return ShoppingTarget(
            source=TARGET_ESSENSPLANER,
            target_id=target_id,
            name=shopping_list.name,
        )

    if source == TARGET_BRING:
        return ShoppingTarget(
            source=TARGET_BRING,
            target_id=target_id,
            name=target_id,
            entity_id=target_id,
        )

    raise ValueError(f"Unsupported shopping list source: {source}")


def is_valid_target(
    hass: HomeAssistant, entry: EssensplanerConfigEntry, encoded: str
) -> bool:
    """Return whether encoded target exists."""
    if ":" not in encoded:
        encoded = encode_target(TARGET_ESSENSPLANER, encoded)
    try:
        source, target_id = parse_encoded_target(encoded)
    except ValueError:
        return False

    if source == TARGET_ESSENSPLANER:
        return target_id in entry.runtime_data.store.data.shopping_lists

    if source == TARGET_BRING:
        entity_registry = er.async_get(hass)
        entity = entity_registry.async_get(target_id)
        return (
            entity is not None
            and entity.domain == TODO_DOMAIN
            and entity.platform == BRING_PLATFORM
        )

    return False


async def async_add_recipe_ingredients(
    hass: HomeAssistant,
    entry: EssensplanerConfigEntry,
    recipe: Recipe,
    *,
    encoded_target: str | None = None,
) -> list[dict[str, Any]]:
    """Add recipe ingredients to the configured shopping list target."""
    store = entry.runtime_data.store
    target = resolve_target(encoded_target, entry.options, store)

    if target.source == TARGET_ESSENSPLANER:
        items = await store.async_add_recipe_ingredients_to_list(
            recipe.id,
            target.target_id,
            options=entry.options,
        )
        return [item.to_dict() for item in items]

    added: list[dict[str, Any]] = []
    for ingredient in recipe.ingredients:
        display = format_ingredient_display(ingredient)
        await hass.services.async_call(
            TODO_DOMAIN,
            "add_item",
            {"entity_id": target.entity_id, "item": display},
            blocking=True,
        )
        added.append({"display": display, "entity_id": target.entity_id})
    return added
