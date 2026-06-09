"""Persistent storage and business logic for Essensplaner."""

from __future__ import annotations

import asyncio
from datetime import date
from random import choice
from typing import TYPE_CHECKING

from homeassistant.helpers.storage import Store

from .const import DEFAULT_SHOPPING_LIST_NAME, LOGGER, STORAGE_KEY, STORAGE_VERSION
from .models import (
    Cookbook,
    EssensplanerData,
    MealplanEntry,
    Recipe,
    ShoppingItem,
    ShoppingList,
    Statistics,
)
from .utils import generate_id, unique_slug

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


class EssensplanerStore:
    """Manage Essensplaner data persistence."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize store."""
        self.hass = hass
        self.entry_id = entry_id
        self._store = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY.format(entry_id=entry_id),
        )
        self._data = EssensplanerData()
        self._lock = asyncio.Lock()

    @property
    def data(self) -> EssensplanerData:
        """Return current data."""
        return self._data

    async def async_load(self) -> EssensplanerData:
        """Load data from disk."""
        stored = await self._store.async_load()
        if stored:
            self._data = EssensplanerData.from_dict(stored)
        else:
            self._data = self._create_default_data()
            await self._async_save()
        return self._data

    def _create_default_data(self) -> EssensplanerData:
        """Create default household data."""
        list_id = generate_id()
        return EssensplanerData(
            shopping_lists={
                list_id: ShoppingList(id=list_id, name=DEFAULT_SHOPPING_LIST_NAME)
            }
        )

    async def _async_save(self) -> None:
        """Persist data."""
        await self._store.async_save(self._data.to_dict())

    def find_recipe(self, recipe_id: str) -> Recipe | None:
        """Find recipe by id or slug."""
        if recipe_id in self._data.recipes:
            return self._data.recipes[recipe_id]
        for recipe in self._data.recipes.values():
            if recipe.slug == recipe_id:
                return recipe
        return None

    async def async_add_recipe(self, recipe: Recipe) -> Recipe:
        """Add or update a recipe."""
        async with self._lock:
            existing_slugs = {r.slug for r in self._data.recipes.values() if r.id != recipe.id}
            if recipe.slug in existing_slugs:
                recipe.slug = unique_slug(recipe.name, existing_slugs)
            self._data.recipes[recipe.id] = recipe
            await self._async_save()
            return recipe

    async def async_delete_recipe(self, recipe_id: str) -> bool:
        """Delete a recipe."""
        recipe = self.find_recipe(recipe_id)
        if not recipe:
            return False
        async with self._lock:
            del self._data.recipes[recipe.id]
            self._data.mealplans = [
                m for m in self._data.mealplans if m.recipe_id != recipe.id
            ]
            for cookbook in self._data.cookbooks.values():
                if recipe.id in cookbook.recipe_ids:
                    cookbook.recipe_ids.remove(recipe.id)
            await self._async_save()
            return True

    def search_recipes(
        self, search_terms: str | None = None, limit: int = 10
    ) -> list[Recipe]:
        """Search recipes."""
        recipes = list(self._data.recipes.values())
        if search_terms:
            terms = search_terms.lower().split()
            filtered = []
            for recipe in recipes:
                haystack = " ".join(
                    [
                        recipe.name,
                        recipe.description or "",
                        " ".join(recipe.tags),
                        " ".join(recipe.categories),
                        " ".join(i.name for i in recipe.ingredients),
                    ]
                ).lower()
                if all(term in haystack for term in terms):
                    filtered.append(recipe)
            recipes = filtered
        return recipes[:limit]

    def get_mealplans(
        self, start_date: date, end_date: date
    ) -> list[MealplanEntry]:
        """Get meal plans in date range."""
        start = start_date.isoformat()
        end = end_date.isoformat()
        return [
            m for m in self._data.mealplans if start <= m.date <= end
        ]

    async def async_set_mealplan(
        self,
        plan_date: date,
        entry_type: str,
        recipe_id: str | None = None,
        note_title: str | None = None,
        note_text: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> MealplanEntry:
        """Set or replace a meal plan entry."""
        date_str = plan_date.isoformat()
        recipe: Recipe | None = None
        if recipe_id:
            recipe = self.find_recipe(recipe_id)
            if not recipe:
                raise ValueError(f"Recipe not found: {recipe_id}")

        async with self._lock:
            self._data.mealplans = [
                m
                for m in self._data.mealplans
                if not (m.date == date_str and m.entry_type == entry_type)
            ]
            entry = MealplanEntry(
                id=generate_id(),
                date=date_str,
                entry_type=entry_type,
                recipe_id=recipe.id if recipe else None,
                title=note_title or (recipe.name if recipe else None),
                description=note_text or (recipe.description if recipe else None),
                start_time=start_time,
                end_time=end_time,
            )
            self._data.mealplans.append(entry)
            await self._async_save()
            return entry

    async def async_clear_mealplan(self, plan_date: date, entry_type: str) -> bool:
        """Remove a meal plan slot."""
        date_str = plan_date.isoformat()
        async with self._lock:
            before = len(self._data.mealplans)
            self._data.mealplans = [
                m
                for m in self._data.mealplans
                if not (m.date == date_str and m.entry_type == entry_type)
            ]
            if len(self._data.mealplans) == before:
                return False
            await self._async_save()
            return True

    async def async_set_random_mealplan(
        self, plan_date: date, entry_type: str
    ) -> MealplanEntry:
        """Set a random recipe on the meal plan."""
        if not self._data.recipes:
            raise ValueError("No recipes available")
        recipe = choice(list(self._data.recipes.values()))
        return await self.async_set_mealplan(
            plan_date, entry_type, recipe_id=recipe.id
        )

    def get_shopping_lists(self) -> list[ShoppingList]:
        """Return all shopping lists."""
        return list(self._data.shopping_lists.values())

    def get_shopping_items(self, list_id: str) -> list[ShoppingItem]:
        """Return items for a shopping list sorted by position."""
        items = [
            item
            for item in self._data.shopping_items.values()
            if item.list_id == list_id
        ]
        return sorted(items, key=lambda x: x.position)

    async def async_add_shopping_item(
        self,
        list_id: str,
        display: str,
        note: str | None = None,
        quantity: float = 0.0,
        unit: str | None = None,
        is_food: bool = False,
        recipe_id: str | None = None,
    ) -> ShoppingItem:
        """Add item to shopping list."""
        if list_id not in self._data.shopping_lists:
            raise ValueError(f"Shopping list not found: {list_id}")

        items = self.get_shopping_items(list_id)
        position = items[-1].position + 1 if items else 0

        async with self._lock:
            item = ShoppingItem(
                id=generate_id(),
                list_id=list_id,
                display=display,
                note=note or display,
                position=position,
                quantity=quantity,
                unit=unit,
                is_food=is_food,
                recipe_id=recipe_id,
            )
            self._data.shopping_items[item.id] = item
            await self._async_save()
            return item

    async def async_update_shopping_item(self, item: ShoppingItem) -> None:
        """Update shopping item."""
        async with self._lock:
            self._data.shopping_items[item.id] = item
            await self._async_save()

    async def async_delete_shopping_item(self, item_id: str) -> None:
        """Delete shopping item."""
        async with self._lock:
            self._data.shopping_items.pop(item_id, None)
            await self._async_save()

    async def async_add_recipe_ingredients_to_list(
        self, recipe_id: str, list_id: str | None = None
    ) -> list[ShoppingItem]:
        """Add all recipe ingredients to a shopping list."""
        recipe = self.find_recipe(recipe_id)
        if not recipe:
            raise ValueError(f"Recipe not found: {recipe_id}")

        if list_id is None:
            if not self._data.shopping_lists:
                default = self._create_default_data()
                self._data.shopping_lists.update(default.shopping_lists)
            list_id = next(iter(self._data.shopping_lists))

        added: list[ShoppingItem] = []
        for ingredient in recipe.ingredients:
            display = ingredient.name
            if ingredient.quantity and ingredient.unit:
                display = f"{ingredient.quantity:g} {ingredient.unit} {ingredient.name}"
            elif ingredient.quantity:
                display = f"{ingredient.quantity:g} {ingredient.name}"
            item = await self.async_add_shopping_item(
                list_id=list_id,
                display=display,
                note=ingredient.note,
                quantity=ingredient.quantity or 0.0,
                unit=ingredient.unit,
                is_food=True,
                recipe_id=recipe.id,
            )
            added.append(item)
        return added

    async def async_create_cookbook(
        self, name: str, description: str | None = None
    ) -> Cookbook:
        """Create a cookbook."""
        async with self._lock:
            cookbook_id = generate_id()
            slugs = {c.slug for c in self._data.cookbooks.values()}
            cookbook = Cookbook(
                id=cookbook_id,
                name=name,
                slug=unique_slug(name, slugs),
                description=description,
            )
            self._data.cookbooks[cookbook_id] = cookbook
            await self._async_save()
            return cookbook

    async def async_delete_cookbook(self, cookbook_id: str) -> bool:
        """Delete a cookbook."""
        async with self._lock:
            if cookbook_id not in self._data.cookbooks:
                return False
            del self._data.cookbooks[cookbook_id]
            await self._async_save()
            return True

    async def async_add_recipe_to_cookbook(
        self, cookbook_id: str, recipe_id: str
    ) -> Cookbook:
        """Add a recipe to a cookbook."""
        recipe = self.find_recipe(recipe_id)
        if not recipe:
            raise ValueError(f"Recipe not found: {recipe_id}")
        async with self._lock:
            cookbook = self._data.cookbooks.get(cookbook_id)
            if not cookbook:
                raise ValueError(f"Cookbook not found: {cookbook_id}")
            if recipe.id not in cookbook.recipe_ids:
                cookbook.recipe_ids.append(recipe.id)
            await self._async_save()
            return cookbook

    async def async_remove_recipe_from_cookbook(
        self, cookbook_id: str, recipe_id: str
    ) -> Cookbook:
        """Remove a recipe from a cookbook."""
        recipe = self.find_recipe(recipe_id)
        if not recipe:
            raise ValueError(f"Recipe not found: {recipe_id}")
        async with self._lock:
            cookbook = self._data.cookbooks.get(cookbook_id)
            if not cookbook:
                raise ValueError(f"Cookbook not found: {cookbook_id}")
            if recipe.id in cookbook.recipe_ids:
                cookbook.recipe_ids.remove(recipe.id)
            await self._async_save()
            return cookbook

    def get_statistics(self) -> Statistics:
        """Return computed statistics."""
        return self._data.compute_statistics()

    def mealplans_by_type(self) -> dict[str, list[MealplanEntry]]:
        """Group mealplans by entry type."""
        result: dict[str, list[MealplanEntry]] = {}
        for entry in self._data.mealplans:
            result.setdefault(entry.entry_type, []).append(entry)
        return result
