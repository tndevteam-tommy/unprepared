"""Stations the player uses with [E]: mines (tool -> item) and crafting stations (anvil: ore -> lockpicks).

Smithing follows the common progression rule: a novice often ruins the ore
(``smithing_base_chance`` at level 1, climbing with every level) and gets a
single pick when it works; the yield per ore grows linearly with the skill up to
``lockpicks_max`` at ``lockpicks_max_level``. Both outcomes teach - failure less -
and every reward shrinks as the skill grows.
"""
from __future__ import annotations

import random
from typing import Callable, Optional

from ..config import GameSettings
from ..entities import Item, Player, SkillType
from ..entities.inventory import find_item, take_item
from . import progression
from .stealth import roll

Notify = Optional[Callable[[str], None]]


def smithing_chance(player: Player, settings: GameSettings) -> float:
    return progression.success_chance(player.skills.level(SkillType.SMITHING), settings.crafting.smithing_base_chance,
                                      settings.progression)


def smithing_yield(player: Player, settings: GameSettings) -> int:
    c = settings.crafting
    return progression.scaled_yield(player.skills.level(SkillType.SMITHING), c.lockpicks_min, c.lockpicks_max,
                                    c.lockpicks_max_level)


def station_prompt(station, player: Player, settings: Optional[GameSettings] = None) -> str:
    d = station.definition
    if d.yields is not None:
        if d.requires_item_id and find_item(player.inventory, d.requires_item_id) is None:
            return f"[{d.label}: needs {d.tool_label}]"
        return f"[E] Mine {d.yields.name} from the {d.label}"
    if d.consumes is not None:
        item_id, count = d.consumes
        have = find_item(player.inventory, item_id)
        if have is None or have.quantity < count:
            return f"[{d.label}: needs {d.consumes_label}]"
        if settings is not None:
            n = smithing_yield(player, settings)
            return f"[E] Forge {d.produces.name}s ({d.consumes_label}; up to {n} at your skill)"
        return f"[E] Forge {d.produces.name}s ({d.consumes_label})"
    return f"[E] Use {d.label}"


def use_station(player: Player, station, settings: GameSettings, notify: Notify = None,
                rng: Optional[random.Random] = None) -> Optional[Item]:
    """Mine one unit or craft one batch; returns what the player gained (None if they could not,
    or the forging failed)."""
    d = station.definition
    rng = rng or random.Random()
    if d.yields is not None:
        if d.requires_item_id and find_item(player.inventory, d.requires_item_id) is None:
            if notify:
                notify(f"You need {d.tool_label} to work the {d.label.lower()}.")
            return None
        unit = d.yields.build()
        unit.quantity = 1
        unit.owner = Item.PLAYER_OWNER
        player.add_item(unit)
        station.uses += 1
        progression.grant(player, SkillType.SMITHING, settings.skill_rewards.mining, notify=notify, s=settings.progression)
        if notify:
            notify(f"Mined {unit.name} from the {d.label.lower()}.")
        return unit
    if d.consumes is not None:
        item_id, count = d.consumes
        have = find_item(player.inventory, item_id)
        if have is None or have.quantity < count:
            if notify:
                notify(f"You need {d.consumes_label} to use the {d.label.lower()}. Mine some with a pickaxe.")
            return None
        take_item(player.inventory, have, count)
        station.uses += 1
        if not roll(rng, smithing_chance(player, settings)):
            progression.grant(player, SkillType.SMITHING, settings.skill_rewards.smithing_fail, notify=notify,
                              s=settings.progression)
            if notify:
                notify(f"The metal cracks on the {d.label.lower()} - the ore is ruined. You learn from the mistake.")
            return None
        batch = d.produces.build()
        batch.quantity = smithing_yield(player, settings)
        batch.owner = Item.PLAYER_OWNER
        player.add_item(batch)
        progression.grant(player, SkillType.SMITHING, settings.skill_rewards.smithing, 1.0 + 0.1 * (batch.quantity - 1),
                          notify=notify, s=settings.progression)
        if notify:
            notify(f"Forged {batch.quantity} {batch.name}{'s' if batch.quantity != 1 else ''} from {d.consumes_label.lower()}!")
        return batch
    return None
