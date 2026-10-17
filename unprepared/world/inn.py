"""The inn: renting a room, and being shown out of it when the rent runs out.

Rooms are bought like goods from the keeper's stock (``rent_night`` / ``rent_week``
service items); buying one calls :meth:`InnState.rent`, which unlocks and opens
the first free room and makes its area trusted for the stay. On every hour tick
:meth:`InnState.update` relocks a room whose rent has expired (after
``checkout_hour`` on the last day) and has the keeper show a lingering guest the
door. Everything static comes from the level's :class:`~.level.InnDef`, so another
town's inn only needs its own definition.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, List, Optional

from ..core.math3d import Vector3D

if TYPE_CHECKING:  # pragma: no cover
    from ..entities import Player
    from .world import World

Notify = Optional[Callable[[str], None]]
RENT_ITEMS = {"rent_night": 1, "rent_week": 7}


@dataclass
class InnState:
    keeper: Optional[str] = None
    area: str = "the inn"
    rooms: List = field(default_factory=list)      # InnRoomDef
    night_price: float = 10.0
    week_price: float = 50.0
    checkout_hour: int = 12
    present: bool = False
    rented_room: Optional[int] = None              # index into rooms
    rent_end_day: Optional[int] = None             # the last day of the stay (checkout at checkout_hour)

    @classmethod
    def from_def(cls, inn_def) -> "InnState":
        if inn_def is None:
            return cls()
        return cls(keeper=inn_def.keeper, area=inn_def.area, rooms=list(inn_def.rooms), night_price=inn_def.night_price,
                   week_price=inn_def.week_price, checkout_hour=inn_def.checkout_hour, present=True)

    # --- queries ----------------------------------------------------------------------
    @property
    def rented_area(self) -> Optional[str]:
        return self.rooms[self.rented_room].area if self.rented_room is not None else None

    @property
    def rented_door_id(self) -> Optional[str]:
        return self.rooms[self.rented_room].door_id if self.rented_room is not None else None

    def is_rented(self, day: int, hour: int) -> bool:
        """Still within the stay: until ``checkout_hour`` on the last day."""
        if self.rented_room is None or self.rent_end_day is None:
            return False
        return day < self.rent_end_day or (day == self.rent_end_day and hour < self.checkout_hour)

    def nights_left(self, day: int) -> int:
        return max(0, (self.rent_end_day or day) - day)

    # --- renting ---------------------------------------------------------------------
    def rent(self, world: "World", player: "Player", nights: int, notify: Notify = None) -> bool:
        """Pay for ``nights`` (extending a current stay); unlocks and opens the room. False if full."""
        keeper = world.find_npc(self.keeper) if self.keeper else None
        extending = self.rented_room is not None
        if not extending:
            if not self.rooms:
                return False
            self.rented_room = 0
            self.rent_end_day = world.day_count + nights
        else:
            self.rent_end_day = max(self.rent_end_day, world.day_count) + nights
        door = world.find_door(self.rented_door_id)
        if door is not None:
            door.is_locked = False
            door.is_open = True
        room = self.rooms[self.rented_room]
        if keeper is not None:
            kind = "rent_more" if extending else ("rent_week" if nights >= 7 else "rent_night")
            keeper.say(keeper.phrase(kind, room=room.area, Room=room.area[:1].upper() + room.area[1:],
                                     nights=self.nights_left(world.day_count)), notify)
        elif notify:
            notify(f"You have {room.area} until noon in {self.nights_left(world.day_count)} day(s).")
        return True

    def end_stay(self, world: "World", notify: Notify = None) -> None:
        door = world.find_door(self.rented_door_id) if self.rented_door_id else None
        if door is not None:
            door.lock_and_close()
        self.rented_room = None
        self.rent_end_day = None

    def update(self, world: "World", player: "Player", notify: Notify = None) -> None:
        """Hour tick: once the rent has run out the room is locked again and a guest still
        inside is shown out by the keeper (the standard eviction, fade and all)."""
        if self.rented_room is None or self.is_rented(world.day_count, world.clock.hour):
            return
        room = self.rooms[self.rented_room]
        keeper = world.find_npc(self.keeper) if self.keeper else None
        if world.area_of(player.position) == room.area:
            if keeper is not None:
                keeper.say(keeper.phrase("rent_over"), notify)
            world.throw_out(player, room.area, by=keeper, line="Your stay is over. You are shown out of the inn.")
        elif notify:
            notify(f"Your rent on {room.area} has run out; the room is locked again.")
        self.end_stay(world, notify)

    # --- persistence -------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {"rented_room": self.rented_room, "rent_end_day": self.rent_end_day}

    def load_dict(self, data: dict) -> None:
        self.rented_room = data.get("rented_room")
        self.rent_end_day = data.get("rent_end_day")


def room_spot(inn: InnState, world: "World") -> Optional[Vector3D]:
    """Where a guest would stand in their rented room (beside the bed)."""
    if inn.rented_room is None:
        return None
    bed = inn.rooms[inn.rented_room].bed
    return Vector3D(bed[0], 0.0, bed[2] + 1.6)
