"""Data models for Essensplaner."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _to_dict(obj: Any) -> dict[str, Any]:
    """Convert dataclass to dict."""
    return asdict(obj)


@dataclass
class Ingredient:
    """Recipe ingredient."""

    name: str
    quantity: float | None = None
    unit: str | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return dict representation."""
        return _to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Ingredient:
        """Create from dict."""
        return cls(**data)


@dataclass
class Recipe:
    """Recipe model."""

    id: str
    slug: str
    name: str
    description: str | None = None
    ingredients: list[Ingredient] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    image_url: str | None = None
    tags: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    cook_time: int | None = None
    prep_time: int | None = None
    servings: str | None = None
    source_url: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return dict representation."""
        data = _to_dict(self)
        data["ingredients"] = [i.to_dict() for i in self.ingredients]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Recipe:
        """Create from dict."""
        ingredients = [Ingredient.from_dict(i) for i in data.get("ingredients", [])]
        return cls(
            id=data["id"],
            slug=data["slug"],
            name=data["name"],
            description=data.get("description"),
            ingredients=ingredients,
            instructions=data.get("instructions", []),
            image_url=data.get("image_url"),
            tags=data.get("tags", []),
            categories=data.get("categories", []),
            tools=data.get("tools", []),
            cook_time=data.get("cook_time"),
            prep_time=data.get("prep_time"),
            servings=data.get("servings"),
            source_url=data.get("source_url"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class MealplanEntry:
    """Meal plan entry."""

    id: str
    date: str
    entry_type: str
    recipe_id: str | None = None
    title: str | None = None
    description: str | None = None
    start_time: str | None = None
    end_time: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return dict representation."""
        return _to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MealplanEntry:
        """Create from dict."""
        return cls(
            id=data["id"],
            date=data["date"],
            entry_type=data["entry_type"],
            recipe_id=data.get("recipe_id"),
            title=data.get("title"),
            description=data.get("description"),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
        )

    def to_service_dict(
        self,
        recipe: Recipe | None,
        *,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> dict[str, Any]:
        """Return Mealie-compatible service response dict."""
        result: dict[str, Any] = {
            "id": self.id,
            "date": self.date,
            "entry_type": self.entry_type,
            "title": self.title,
            "description": self.description,
            "start_time": start_time,
            "end_time": end_time,
        }
        if recipe:
            result["recipe"] = recipe.to_dict()
        elif self.title:
            result["recipe"] = None
        return result


@dataclass
class ShoppingList:
    """Shopping list."""

    id: str
    name: str

    def to_dict(self) -> dict[str, Any]:
        """Return dict representation."""
        return _to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ShoppingList:
        """Create from dict."""
        return cls(**data)


@dataclass
class ShoppingItem:
    """Shopping list item."""

    id: str
    list_id: str
    display: str
    note: str | None = None
    checked: bool = False
    position: int = 0
    quantity: float = 0.0
    unit: str | None = None
    is_food: bool = False
    recipe_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return dict representation."""
        return _to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ShoppingItem:
        """Create from dict."""
        return cls(**data)


@dataclass
class Cookbook:
    """Cookbook grouping recipes."""

    id: str
    name: str
    slug: str
    description: str | None = None
    recipe_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return dict representation."""
        return _to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Cookbook:
        """Create from dict."""
        return cls(**data)


@dataclass
class Statistics:
    """Household statistics."""

    total_recipes: int = 0
    total_categories: int = 0
    total_tags: int = 0
    total_tools: int = 0
    total_cookbooks: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Return dict representation."""
        return _to_dict(self)


@dataclass
class EssensplanerData:
    """All stored data for one household."""

    recipes: dict[str, Recipe] = field(default_factory=dict)
    mealplans: list[MealplanEntry] = field(default_factory=list)
    shopping_lists: dict[str, ShoppingList] = field(default_factory=dict)
    shopping_items: dict[str, ShoppingItem] = field(default_factory=dict)
    cookbooks: dict[str, Cookbook] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "recipes": {k: v.to_dict() for k, v in self.recipes.items()},
            "mealplans": [m.to_dict() for m in self.mealplans],
            "shopping_lists": {k: v.to_dict() for k, v in self.shopping_lists.items()},
            "shopping_items": {k: v.to_dict() for k, v in self.shopping_items.items()},
            "cookbooks": {k: v.to_dict() for k, v in self.cookbooks.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EssensplanerData:
        """Deserialize from dict."""
        return cls(
            recipes={k: Recipe.from_dict(v) for k, v in data.get("recipes", {}).items()},
            mealplans=[MealplanEntry.from_dict(m) for m in data.get("mealplans", [])],
            shopping_lists={
                k: ShoppingList.from_dict(v) for k, v in data.get("shopping_lists", {}).items()
            },
            shopping_items={
                k: ShoppingItem.from_dict(v) for k, v in data.get("shopping_items", {}).items()
            },
            cookbooks={k: Cookbook.from_dict(v) for k, v in data.get("cookbooks", {}).items()},
        )

    def compute_statistics(self) -> Statistics:
        """Compute statistics from current data."""
        categories: set[str] = set()
        tags: set[str] = set()
        tools: set[str] = set()
        for recipe in self.recipes.values():
            categories.update(recipe.categories)
            tags.update(recipe.tags)
            tools.update(recipe.tools)
        return Statistics(
            total_recipes=len(self.recipes),
            total_categories=len(categories),
            total_tags=len(tags),
            total_tools=len(tools),
            total_cookbooks=len(self.cookbooks),
        )
