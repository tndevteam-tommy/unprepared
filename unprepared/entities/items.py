from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Item:
    id: str
    name: str
    value: float = 50.0
    is_stolen: bool = False
    noise_modifier: float = 0.0
    is_key: bool = False
    key_door_id: Optional[str] = None
    is_lockpick: bool = False
    for_sale: bool = True          # False: owned but never offered in a merchant's stock (e.g. shop keys)
    stackable: bool = False        # identical small items merge into one stack
    quantity: int = 1
    is_food: bool = False          # NPCs eat these at meal times
    owner: Optional[str] = None    # "player": the player's own property (taking it back is never theft)
    category: str = "goods"        # what kind of thing it is (specialist merchants trade only some categories)

    PLAYER_OWNER = "player"

    @property
    def is_players(self) -> bool:
        return self.owner == Item.PLAYER_OWNER

    @property
    def display_name(self) -> str:
        """'Fresh Bread (3)' for stacks of more than one, else just the name."""
        return f"{self.name} ({self.quantity})" if self.stackable and self.quantity > 1 else self.name

    def same_stack(self, other: "Item") -> bool:
        return (self.stackable and other.stackable and self.id == other.id and self.name == other.name
                and self.value == other.value and self.is_stolen == other.is_stolen and self.is_food == other.is_food
                and self.owner == other.owner)

    def split(self, count: int = 1) -> "Item":
        """Take ``count`` units off this stack as a new Item (quantity of this one shrinks)."""
        count = max(1, min(count, self.quantity))
        self.quantity -= count
        return Item(self.id, self.name, self.value, self.is_stolen, self.noise_modifier, self.is_key, self.key_door_id,
                    self.is_lockpick, self.for_sale, self.stackable, count, self.is_food, self.owner, self.category)

    def opens(self, door_id: str) -> bool:
        return self.is_key and self.key_door_id == door_id

    def sell_value(self, stolen_multiplier: float = 0.5) -> float:
        return self.value * stolen_multiplier if self.is_stolen else self.value

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "value": self.value,
            "is_stolen": self.is_stolen, "noise_modifier": self.noise_modifier,
            "is_key": self.is_key, "key_door_id": self.key_door_id, "is_lockpick": self.is_lockpick,
            "for_sale": self.for_sale, "stackable": self.stackable, "quantity": self.quantity, "is_food": self.is_food,
            "owner": self.owner, "category": self.category,
        }

    @staticmethod
    def from_dict(d: dict) -> "Item":
        return Item(
            id=d["id"], name=d["name"], value=d.get("value", 50.0),
            is_stolen=d.get("is_stolen", False), noise_modifier=d.get("noise_modifier", 0.0),
            is_key=d.get("is_key", False), key_door_id=d.get("key_door_id"),
            is_lockpick=d.get("is_lockpick", False), for_sale=d.get("for_sale", True),
            stackable=d.get("stackable", False), quantity=d.get("quantity", 1), is_food=d.get("is_food", False),
            owner=d.get("owner"), category=d.get("category", "goods"),
        )
