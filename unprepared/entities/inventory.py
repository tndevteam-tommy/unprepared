"""Helpers for item lists (player, NPC and container inventories).

Inventories stay plain ``List[Item]`` so saves and existing code keep working;
these functions add stack-aware insertion and removal.
"""
from __future__ import annotations

from typing import List, Optional

from .items import Item


def add_item(inventory: List[Item], item: Item) -> Item:
    """Insert ``item``, merging it into an existing compatible stack. Returns the stack it ended up in."""
    if item.stackable:
        for existing in inventory:
            if existing.same_stack(item):
                existing.quantity += item.quantity
                return existing
    inventory.append(item)
    return item


def take_item(inventory: List[Item], item: Item, count: int = 1) -> Optional[Item]:
    """Remove ``count`` units of ``item`` (which must be in ``inventory``); returns the removed units as
    an Item, or None if ``item`` is not there. A stack reduced to zero is removed from the list."""
    if item not in inventory:
        return None
    if item.stackable and item.quantity > count:
        return item.split(count)
    inventory.remove(item)
    return item


def find_item(inventory: List[Item], item_id: str) -> Optional[Item]:
    return next((i for i in inventory if i.id == item_id), None)


def total_quantity(inventory: List[Item]) -> int:
    return sum(i.quantity for i in inventory)
