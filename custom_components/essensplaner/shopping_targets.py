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
TARGET_BRING = "bring"
BRING_DOMAIN = "bring"
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


def _is_bring_todo_entity(hass: HomeAssistant, entity_entry: er.RegistryEntry) -> bool:
    """Return whether a registry entry is a Bring todo list."""
    if entity_entry.domain != TODO_DOMAIN:
        return False
    if entity_entry.platform == BRING_PLATFORM:
        return True
    if not entity_entry.config_entry_id:
        return False
    config_entry = hass.config_entries.async_get_entry(entity_entry.config_entry_id)
    return config_entry is not None and config_entry.domain == BRING_DOMAIN


def _bring_entity_display_name(
    hass: HomeAssistant,
    entity_entry: er.RegistryEntry,
    device_registry: dr.DeviceRegistry,
) -> str:
    """Return a user-facing name for a Bring todo entity."""
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


def _append_bring_target(
    hass: HomeAssistant,
    entity_id: str,
    name: str,
    *,
    result: list[dict[str, Any]],
    seen: set[str],
) -> None:
    """Append a Bring target if not already present."""
    if entity_id in seen:
        return
    seen.add(entity_id)
    result.append(
        {
            "id": encode_target(TARGET_BRING, entity_id),
            "name": name,
            "entity_id": entity_id,
            "source": TARGET_BRING,
        }
    )


def _bring_targets(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Return Bring! todo lists for the panel."""
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    entries_for_domain = getattr(er, "async_entries_for_domain", None)
    if callable(entries_for_domain):
        todo_entries = entries_for_domain(entity_registry, TODO_DOMAIN)
    else:
        todo_entries = [
            entry
            for entry in entity_registry.entities.values()
            if entry.domain == TODO_DOMAIN
        ]

    for entity_entry in todo_entries:
        if not _is_bring_todo_entity(hass, entity_entry):
            continue
        _append_bring_target(
            hass,
            entity_entry.entity_id,
            _bring_entity_display_name(hass, entity_entry, device_registry),
            result=result,
            seen=seen,
        )

    entries_for_device = getattr(dr, "async_entries_for_device", None)
    for device in device_registry.devices.values():
        if not any(identifier[0] == BRING_DOMAIN for identifier in device.identifiers):
            continue
        device_name = device.name_by_user or device.name
        if callable(entries_for_device):
            device_entities = entries_for_device(device_registry, device.id)
        else:
            device_entities = [
                entry
                for entry in entity_registry.entities.values()
                if entry.device_id == device.id
            ]
        for entity_entry in device_entities:
            if entity_entry.domain != TODO_DOMAIN:
                continue
            _append_bring_target(
                hass,
                entity_entry.entity_id,
                device_name
                or _bring_entity_display_name(hass, entity_entry, device_registry),
                result=result,
                seen=seen,
            )

    for entity_id in hass.states.entity_ids(TODO_DOMAIN):
        if entity_id in seen:
            continue
        entity_entry = entity_registry.async_get(entity_id)
        if entity_entry is None or not _is_bring_todo_entity(hass, entity_entry):
            continue
        _append_bring_target(
            hass,
            entity_id,
            _bring_entity_display_name(hass, entity_entry, device_registry),
            result=result,
            seen=seen,
        )

    if not result and hass.config_entries.async_entries(BRING_DOMAIN):
        LOGGER.info(
            "Bring integration is configured but no todo list entities were found. "
            "Enable Bring todo entities under Settings → Entities."
        )
    else:
        LOGGER.debug("Found %d Bring shopping list(s)", len(result))
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
        return entity is not None and _is_bring_todo_entity(hass, entity)

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
