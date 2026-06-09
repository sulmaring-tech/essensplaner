"""Todo platform for Essensplaner."""

from __future__ import annotations

from homeassistant.components.todo import (
    DOMAIN as TODO_DOMAIN,
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant, ServiceResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import EssensplanerConfigEntry, EssensplanerShoppingListCoordinator
from .entity import EssensplanerEntity
from .models import ShoppingItem

PARALLEL_UPDATES = 0

TODO_STATUS_MAP = {
    False: TodoItemStatus.NEEDS_ACTION,
    True: TodoItemStatus.COMPLETED,
}


def _convert_item(item: ShoppingItem) -> TodoItem:
    """Convert shopping item to TodoItem."""
    return TodoItem(
        summary=item.display,
        uid=item.id,
        status=TODO_STATUS_MAP.get(item.checked, TodoItemStatus.NEEDS_ACTION),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EssensplanerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up todo entities."""
    coordinator = entry.runtime_data.shoppinglist_coordinator
    added_lists: set[str] = set()

    assert entry.unique_id is not None

    def _async_delete_entities(lists: set[str]) -> None:
        entity_registry = er.async_get(hass)
        for list_id in lists:
            entity_id = entity_registry.async_get_entity_id(
                TODO_DOMAIN, DOMAIN, f"{entry.unique_id}_{list_id}"
            )
            if entity_id:
                entity_registry.async_remove(entity_id)

    def _async_entity_listener() -> None:
        received = set(coordinator.data)
        new_lists = received - added_lists
        removed_lists = added_lists - received
        if new_lists:
            async_add_entities(
                EssensplanerShoppingListEntity(coordinator, list_id)
                for list_id in new_lists
            )
            added_lists.update(new_lists)
        if removed_lists:
            _async_delete_entities(removed_lists)
            added_lists.difference_update(removed_lists)

    coordinator.async_add_listener(_async_entity_listener)
    _async_entity_listener()


class EssensplanerShoppingListEntity(EssensplanerEntity, TodoListEntity):
    """Shopping list as todo entity."""

    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.MOVE_TODO_ITEM
    )
    _attr_translation_key = "shopping_list"

    coordinator: EssensplanerShoppingListCoordinator

    def __init__(
        self, coordinator: EssensplanerShoppingListCoordinator, list_id: str
    ) -> None:
        """Initialize todo entity."""
        super().__init__(coordinator, list_id)
        self._list_id = list_id
        self._attr_translation_placeholders = {
            "list_name": coordinator.data[list_id].shopping_list.name,
        }

    @property
    def shopping_list_data(self):
        """Return shopping list data."""
        return self.coordinator.data[self._list_id]

    @property
    def todo_items(self) -> list[TodoItem] | None:
        """Return todo items."""
        return [_convert_item(item) for item in self.shopping_list_data.items]

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Add item."""
        try:
            await self.coordinator.store.async_add_shopping_item(
                self._list_id,
                display=item.summary or "",
            )
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        finally:
            await self.coordinator.async_refresh()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Update item."""
        list_items = self.shopping_list_data.items
        list_item = next((x for x in list_items if x.id == item.uid), None)
        if list_item is None:
            raise HomeAssistantError(f"Item not found: {item.uid}")

        list_item.checked = item.status == TodoItemStatus.COMPLETED
        if item.summary and item.summary.strip() != list_item.display.strip():
            list_item.display = item.summary.strip()
            list_item.note = item.summary.strip()
            list_item.is_food = False

        try:
            await self.coordinator.store.async_update_shopping_item(list_item)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        finally:
            await self.coordinator.async_refresh()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete items."""
        try:
            for uid in uids:
                await self.coordinator.store.async_delete_shopping_item(uid)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        finally:
            await self.coordinator.async_refresh()

    async def async_move_todo_item(
        self, uid: str, previous_uid: str | None = None
    ) -> None:
        """Reorder items."""
        if uid == previous_uid:
            return
        list_items = list(self.shopping_list_data.items)
        item_idx = {itm.id: idx for idx, itm in enumerate(list_items)}
        if uid not in item_idx:
            raise HomeAssistantError(f"Item not found: {uid}")
        if previous_uid and previous_uid not in item_idx:
            raise HomeAssistantError(f"Item not found: {previous_uid}")

        dst_idx = item_idx[previous_uid] + 1 if previous_uid else 0
        src_idx = item_idx[uid]
        src_item = list_items.pop(src_idx)
        if dst_idx > src_idx:
            dst_idx -= 1
        list_items.insert(dst_idx, src_item)

        for position, shopping_item in enumerate(list_items):
            shopping_item.position = position
            await self.coordinator.store.async_update_shopping_item(shopping_item)

        await self.coordinator.async_refresh()

    @property
    def available(self) -> bool:
        """Return availability."""
        return super().available and self._list_id in self.coordinator.data

    async def async_get_shopping_list_items(self) -> ServiceResponse:
        """Return structured shopping list items."""
        data = self.shopping_list_data
        return {
            "name": data.shopping_list.name,
            "items": [item.to_dict() for item in data.items],
        }
