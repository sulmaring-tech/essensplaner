"""Shopping list targets (Essensplaner internal and external todo lists)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from homeassistant.components.todo import DOMAIN as TODO_DOMAIN
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN, LOGGER, OPTION_DEFAULT_SHOPPING_LIST_ID
from .models import Ingredient, Recipe

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import EssensplanerConfigEntry
    from .storage import EssensplanerStore

TARGET_ESSENSPLANER = "essensplaner"
TARGET_TODO = "todo"
TARGET_BRING = "bring"  # legacy alias for TARGET_TODO


@dataclass(frozen=True)
class ShoppingTarget:
    """Resolved shopping list target."""

    source: Literal["essensplaner", "todo"]
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


def _normalize_target_prefix(value: str) -> str:
    """Map legacy bring targets to generic todo targets."""
    if value.startswith(f"{TARGET_BRING}:"):
        return f"{TARGET_TODO}:{value[len(TARGET_BRING) + 1:]}"
    return value


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
    return _normalize_target_prefix(value)


def parse_encoded_target(value: str) -> tuple[str, str]:
    """Split encoded target into source and id."""
    value = _normalize_target_prefix(value)
    source, _, target_id = value.partition(":")
    if not target_id:
        raise ValueError(f"Invalid shopping list target: {value}")
    return source, target_id


def _todo_registry_entries(entity_registry: er.EntityRegistry) -> list[er.RegistryEntry]:
    """Return all todo entities from the entity registry."""
    entries_for_domain = getattr(er, "async_entries_for_domain", None)
    if callable(entries_for_domain):
        return list(entries_for_domain(entity_registry, TODO_DOMAIN))
    return [
        entry
        for entry in entity_registry.entities.values()
        if entry.domain == TODO_DOMAIN
    ]


def _todo_entity_display_name(
    hass: HomeAssistant,
    entity_entry: er.RegistryEntry,
    device_registry: dr.DeviceRegistry,
) -> str:
    """Return a user-facing name for a todo entity."""
    if entity_entry.device_id:
        device = device_registry.async_get(entity_entry.device_id)
        if device is not None:
            if device.name_by_user:
                return device.name_by_user
            if device.name:
                return device.name

    state = hass.states.get(entity_entry.entity_id)
    if state is not None:
        if state.name:
            return state.name
        friendly_name = state.attributes.get("friendly_name")
        if friendly_name:
            return str(friendly_name)

    return (
        entity_entry.name
        or entity_entry.original_name
        or entity_entry.entity_id
    )


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
                TODO_DOMAIN, DOMAIN, f"{unique_id}_{shopping_list.id}"
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


def _all_todo_entity_ids(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> set[str]:
    """Return all known todo entity ids from registry and state machine."""
    entity_ids = set(hass.states.entity_ids(TODO_DOMAIN))
    for entity_entry in _todo_registry_entries(entity_registry):
        entity_ids.add(entity_entry.entity_id)
    return entity_ids


def _external_todo_targets(
    hass: HomeAssistant,
    excluded_entity_ids: set[str],
) -> list[dict[str, Any]]:
    """Return HA todo entities not already listed by Essensplaner storage."""
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    result: list[dict[str, Any]] = []

    for entity_id in sorted(_all_todo_entity_ids(hass, entity_registry)):
        if entity_id in excluded_entity_ids:
            continue
        entity_entry = entity_registry.async_get(entity_id)
        if entity_entry is not None:
            name = _todo_entity_display_name(hass, entity_entry, device_registry)
            source = entity_entry.platform or TARGET_TODO
        else:
            state = hass.states.get(entity_id)
            name = state.name if state is not None else entity_id
            source = TARGET_TODO
        result.append(
            {
                "id": encode_target(TARGET_TODO, entity_id),
                "name": name,
                "entity_id": entity_id,
                "source": source,
            }
        )

    LOGGER.debug("Found %d external todo list(s)", len(result))
    return sorted(result, key=lambda item: (item["source"], item["name"].casefold()))


def shopping_lists_for_panel(
    hass: HomeAssistant, entry: EssensplanerConfigEntry
) -> list[dict[str, Any]]:
    """Return all selectable shopping list targets."""
    result = _essensplaner_targets(hass, entry)
    excluded = {
        item["entity_id"]
        for item in result
        if item.get("entity_id")
    }
    try:
        result.extend(_external_todo_targets(hass, excluded))
    except Exception as err:  # noqa: BLE001
        LOGGER.warning("External todo lists could not be loaded: %s", err)
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

    if source == TARGET_TODO:
        return ShoppingTarget(
            source=TARGET_TODO,
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
    encoded = _normalize_target_prefix(encoded)
    try:
        source, target_id = parse_encoded_target(encoded)
    except ValueError:
        return False

    if source == TARGET_ESSENSPLANER:
        return target_id in entry.runtime_data.store.data.shopping_lists

    if source == TARGET_TODO:
        entity_registry = er.async_get(hass)
        if entity_registry.async_get(target_id) is not None:
            return True
        return hass.states.get(target_id) is not None

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
