"""Shopkeeping: composite merchant stock, daily stock-taking and periodic restocks.

A shopkeeper sells from its own pockets *and* from the shelves it is attached
to (``NPC.shop_containers``).  When the shop opens and closes the keeper counts
everything and reports anything missing to the guards; every ``restock_days``
days the base stock is topped up and, as the player's level rises, better
(pricier) goods appear on the shelves.
"""
from __future__ import annotations

from typing import Dict, Iterator, List, Optional, TYPE_CHECKING

from ..entities import Item, NPC, TheftReport
from ..entities.inventory import add_item

if TYPE_CHECKING:  # pragma: no cover
    from ..world.world import World


class MerchantStock:
    """The union of a shopkeeper's own inventory and its shelves, usable as an item
    list by the transfer session (iteration, membership, remove, append)."""

    def __init__(self, npc: NPC, world: Optional["World"]):
        self.npc = npc
        self.sources: List[List[Item]] = [npc.inventory]
        if world is not None:
            for name in npc.shop_containers:
                container = world.find_container(name)
                if container is not None:
                    self.sources.append(container.inventory)

    def __iter__(self) -> Iterator[Item]:
        for source in self.sources:
            yield from source

    def __contains__(self, item: Item) -> bool:
        return any(item in source for source in self.sources)

    def __len__(self) -> int:
        return sum(len(source) for source in self.sources)

    def remove(self, item: Item) -> None:
        for source in self.sources:
            if item in source:
                source.remove(item)
                return
        raise ValueError("item not in stock")

    def append(self, item: Item) -> None:
        self.sources[0].append(item)


def count_stock(npc: NPC, world: "World") -> Dict[str, int]:
    """Quantities per item id of everything the shopkeeper has for sale (own + shelves)."""
    counts: Dict[str, int] = {}
    for item in MerchantStock(npc, world):
        if item.for_sale:
            counts[item.id] = counts.get(item.id, 0) + item.quantity
    return counts


def stock_names(npc: NPC, world: "World") -> Dict[str, str]:
    return {item.id: item.name for item in MerchantStock(npc, world)}


def note_sale(npc: NPC, item: Item, delta: int) -> None:
    """Keep the expected stock in step with legitimate trades (so sales are not 'thefts')."""
    if not npc.expected_stock:
        return
    npc.expected_stock[item.id] = max(0, npc.expected_stock.get(item.id, 0) + delta)


def take_stock(npc: NPC, world: "World") -> Optional[TheftReport]:
    """Compare the shelves with the last count; returns a report if goods are missing."""
    current = count_stock(npc, world)
    missing = {iid: qty - current.get(iid, 0) for iid, qty in npc.expected_stock.items() if qty > current.get(iid, 0)}
    names = dict(npc.expected_names)
    names.update(stock_names(npc, world))
    report = None
    if missing and npc.expected_stock:
        report = TheftReport(npc.name, world.area_of(npc.position), world.day_count, missing,
                             {iid: names.get(iid, iid) for iid in missing})
    remember_stock(npc, world)
    return report


def remember_stock(npc: NPC, world: "World") -> None:
    """Snapshot the current stock (quantities and names) as the expectation for the next count."""
    npc.expected_stock = count_stock(npc, world)
    npc.expected_names = stock_names(npc, world)


def restock_due(npc: NPC, world: "World") -> bool:
    return npc.is_shopkeeper and world.day_count - npc.last_restock_day >= npc.restock_days


def restock(npc: NPC, world: "World", player_level: int) -> List[Item]:
    """Top the base stock back up and unlock tiered goods for the player's level. Returns what was added."""
    added: List[Item] = []
    current = count_stock(npc, world)

    def top_up(item_def, target_list):
        have = current.get(item_def.id, 0)
        if have < item_def.quantity:
            unit = item_def.build()
            unit.quantity = item_def.quantity - have
            add_item(target_list, unit)
            current[item_def.id] = item_def.quantity
            added.append(unit)

    for item_def in npc.base_stock:
        top_up(item_def, npc.inventory)
    level_def = world.level
    for cdef in level_def.containers:
        if cdef.name in npc.shop_containers:
            container = world.find_container(cdef.name)
            for item_def in cdef.items:
                top_up(item_def, container.inventory)
    for tier in npc.restock_tiers:
        if player_level >= tier.min_player_level:
            target = npc.inventory
            if tier.container:
                container = world.find_container(tier.container)
                target = container.inventory if container is not None else npc.inventory
            for item_def in tier.items:
                top_up(item_def, target)
    npc.last_restock_day = world.day_count
    remember_stock(npc, world)
    return added
