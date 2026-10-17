"""Crime and punishment: what guards hold against the player, fines, the jail.

A guard that catches up with a *wanted* player charges them: stolen goods go
back to their owners, the fine for every remembered crime is paid in gold -
or, if the player cannot pay, served in jail (one day per ``gold_per_jail_day``
of unpaid fine). The prisoner keeps one lockpick; everything else - tagged as
the player's own property - waits in the jail's confiscation lockbox until the
sentence is served (or they break out, which is a crime of its own).

The jail itself is level data (:class:`~unprepared.world.level.JailDef`): the
barred cell door, the lockbox, the two areas, the cell spot and the jailer.
While a prisoner is inside the cell door is *sealed* - no NPC opens it, whatever
keys it carries - and the jailer never goes in to "check". On release (at
``release_hour`` of the last day) the bars and the lockbox are unlocked, the
jailer stands at the post until the ex-prisoner has left the jail house, and
the lockbox is locked again behind them.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, List, Optional

from ..config import JusticeSettings
from ..core.math3d import Vector3D
from ..entities import AIState, Item, Player
from ..entities.inventory import add_item

if TYPE_CHECKING:  # pragma: no cover
    from ..entities import NPC
    from ..world.world import World

Notify = Optional[Callable[[str], None]]


def fine_for(crime: str, settings: JusticeSettings) -> float:
    return dict(settings.fines).get(crime, settings.default_fine)


@dataclass
class JailState:
    """Live jail bookkeeping; the static part comes from the level's ``JailDef``."""
    cell_door_id: str = "cell_door"
    storage_name: str = "jail_storage"
    cell_area: str = "the jail cell"
    jail_area: str = "the jail"
    cell_spot: Vector3D = None
    jailer: Optional[str] = None
    post: Optional[Vector3D] = None
    present: bool = True                        # False: this level has no jail at all
    sentence_end_day: Optional[int] = None      # None: not serving
    escaped: bool = False
    grace_until: float = 0.0                    # world.elapsed until which a released prisoner may linger
    released: bool = False                      # between release and the ex-prisoner leaving the jail house

    @classmethod
    def from_def(cls, jail_def) -> "JailState":
        if jail_def is None:
            return cls(cell_spot=Vector3D(0.0, 0.0, 0.0), present=False)
        return cls(cell_door_id=jail_def.cell_door_id, storage_name=jail_def.storage, cell_area=jail_def.cell_area,
                   jail_area=jail_def.jail_area, cell_spot=Vector3D(*jail_def.cell_spot), jailer=jail_def.jailer,
                   post=Vector3D(*jail_def.post) if jail_def.post else None)

    @property
    def serving(self) -> bool:
        return self.sentence_end_day is not None

    @property
    def sealed(self) -> bool:
        """A prisoner is inside: the cell stays shut to everyone."""
        return self.serving and not self.escaped

    def days_left(self, day_count: int) -> int:
        return max(0, (self.sentence_end_day or day_count) - day_count)

    def to_dict(self) -> dict:
        return {"sentence_end_day": self.sentence_end_day, "escaped": self.escaped, "grace_until": self.grace_until,
                "released": self.released}

    def load_dict(self, data: dict) -> None:
        self.sentence_end_day = data.get("sentence_end_day")
        self.escaped = data.get("escaped", False)
        self.grace_until = data.get("grace_until", 0.0)
        self.released = data.get("released", False)


def outstanding_fine(world: "World") -> float:
    """Total fine across every guard's active memories (the same crime counted once)."""
    seen = set()
    total = 0.0
    for guard in world.npcs:
        if not guard.is_guard:
            continue
        for memory in guard.active_memories(world.day_count):
            key = (memory.crime, memory.day)
            if key not in seen:
                seen.add(key)
                total += memory.fine
    return total


def return_stolen_goods(world: "World", player: Player, notify: Notify = None) -> List[Item]:
    """Stolen items in the player's pockets go back to their owners (unknown origin: the confiscation lockbox)."""
    returned = []
    for item in [i for i in player.inventory if i.is_stolen]:
        player.inventory.remove(item)
        item.is_stolen = False
        item.owner = None
        owner_inventory = world.owner_inventory_for(item)
        add_item(owner_inventory, item)
        returned.append(item)
    if returned and notify:
        notify(f"Returned to their owners: {', '.join(i.display_name for i in returned)}.")
    return returned


def charge_player(world: "World", guard: "NPC", player: Player, notify: Notify = None) -> str:
    """The guard settles the player's account. Returns 'paid', 'jailed', 'warned' or 'nothing'.

    The player is made to face the guard and any screen they had open is closed
    (``World.player_caught``). Caught somewhere they have no business being, they
    are also shown the door."""
    fine = outstanding_fine(world)
    if fine <= 0:
        return "nothing"
    crimes = sorted({m.crime for g in world.npcs if g.is_guard for m in g.active_memories(world.day_count)})
    world.player_caught(guard)
    return_stolen_goods(world, player, notify)
    if player.gold >= fine:
        player.gold -= fine
        if notify:
            notify(f"({guard.name}): \"{', '.join(crimes)} - that's {fine:.0f} gold in fines. Pay up.\" You pay {fine:.0f}g.")
        _clear_memories(world)
        world.evict_if_trespassing(player, guard, notify)
        return "paid"
    if not world.jail.present:
        if notify:
            notify(f"({guard.name}): \"{', '.join(crimes)} - {fine:.0f} gold, and you can't pay. "
                   f"I'll take what you've got. Consider this your only warning.\"")
        player.gold = 0.0
        _clear_memories(world)
        world.evict_if_trespassing(player, guard, notify)
        return "warned"
    days = int(math.ceil((fine - player.gold) / world.settings.justice.gold_per_jail_day))
    days = max(world.settings.justice.min_jail_days, min(world.settings.justice.max_jail_days, days))
    if notify:
        notify(f"({guard.name}): \"{', '.join(crimes)} - {fine:.0f} gold, and you can't pay. "
               f"It's {days} day{'s' if days != 1 else ''} in the cells for you.\"")
    imprison(world, player, days, notify)
    _clear_memories(world)
    return "jailed"


def _clear_memories(world: "World") -> None:
    for guard in world.npcs:
        if guard.is_guard:
            guard.forget_crimes()
            guard.suspicion_meter = 0.0


def confiscate(world: "World", player: Player) -> Optional[Item]:
    """Move the player's belongings (minus one lockpick) into the lockbox, tagged as theirs.
    Returns the lockpick they keep, if any."""
    jail = world.jail
    storage = world.find_container(jail.storage_name)
    kept_pick = None
    for item in list(player.inventory):
        if item.is_lockpick and kept_pick is None:
            kept_pick = item.split(1) if item.stackable and item.quantity > 1 else item
            if kept_pick is item:
                continue
        player.inventory.remove(item)
        item.owner = Item.PLAYER_OWNER
        if storage is not None:
            add_item(storage.inventory, item)
    player.inventory = [kept_pick] if kept_pick is not None else []
    return kept_pick


def imprison(world: "World", player: Player, days: int, notify: Notify = None) -> None:
    """Lock the player in the cell for ``days`` days: gold and belongings confiscated,
    cell sealed, lockbox locked. The move itself goes through ``World.relocate_player``
    so the presentation can fade to black around it."""
    jail = world.jail
    player.gold = 0.0
    confiscate(world, player)
    storage = world.find_container(jail.storage_name)
    if storage is not None:
        storage.lock_and_close()
    door = world.find_door(jail.cell_door_id)
    if door is not None:
        door.lock_and_close()
        door.sealed = True
    jail.sentence_end_day = world.day_count + days
    jail.escaped = False
    jail.released = False
    player.is_crouching = False
    player.has_lit_torch = False
    world.relocate_player(Vector3D(jail.cell_spot.x, player.position.y, jail.cell_spot.z), yaw=180.0, reason="jailed")
    if notify:
        notify(f"You are thrown in the cell. Your belongings are locked in the confiscation lockbox; "
               f"release in {days} day{'s' if days != 1 else ''}. (You still have one lockpick...)")


def release(world: "World", player: Player, notify: Notify = None) -> None:
    """Time served: open the bars and the lockbox; the jailer waits until the player has gone."""
    jail = world.jail
    jail.sentence_end_day = None
    jail.escaped = False
    jail.released = True
    jail.grace_until = world.elapsed + world.settings.justice.release_grace
    door = world.find_door(jail.cell_door_id)
    if door is not None:
        door.sealed = False
        door.is_locked = False
        door.is_open = True
    storage = world.find_container(jail.storage_name)
    if storage is not None:
        storage.unlock_and_open()
    jailer = world.find_npc(jail.jailer) if jail.jailer else None
    if jailer is not None:
        jailer.wait_for("release", player.position)
        if jail.post is not None and jailer.position.distance_to(jail.post) > 1.0:
            jailer.go_to(world, jail.post, AIState.WAITING)      # walk to the post and watch from there
    who = jailer.name if jailer is not None else "Jailer"
    if notify:
        notify(f"({who}): \"Your time is served. Collect your things from the lockbox and get out.\"")


def end_release(world: "World", notify: Notify = None) -> None:
    """The ex-prisoner has left (or overstayed): lock the lockbox again and let the jailer go back to work."""
    jail = world.jail
    jail.released = False
    jail.grace_until = 0.0
    storage = world.find_container(jail.storage_name)
    if storage is not None:
        storage.lock_and_close()
    jailer = world.find_npc(jail.jailer) if jail.jailer else None
    if jailer is not None and jailer.state is AIState.WAITING and jailer.waiting_for == "release":
        jailer.stop_waiting(world, None)


def update_jail(world: "World", player: Player, notify: Notify = None) -> None:
    """Called every hour tick: release when the day and hour come, or raise the alarm on a jailbreak."""
    jail = world.jail
    if not jail.serving:
        return
    if world.day_count >= jail.sentence_end_day and world.clock.hour >= world.settings.justice.release_hour:
        release(world, player, notify)
        return
    check_jailbreak(world, player, notify)


def check_jailbreak(world: "World", player: Player, notify: Notify = None) -> bool:
    """A serving prisoner outside the jail has broken out: unseal the cell and declare the crime."""
    jail = world.jail
    if not jail.serving or jail.escaped:
        return False
    if world.area_of(player.position) in (jail.cell_area, jail.jail_area):
        return False
    jail.escaped = True
    door = world.find_door(jail.cell_door_id)
    if door is not None:
        door.sealed = False
    if notify:
        notify("You have broken out of jail! The guards will not forget this.")
    # the empty cell is where the alarm is raised: the guards in earshot of the jail come running there
    world.declare_crime("Jailbreak", jail.cell_spot.copy(), witnessed=False, reporter=jail.jailer or "the jailer")
    jail.sentence_end_day = None
    return True
