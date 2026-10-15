from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from ..core.math3d import BoundingBox3D, Vector3D


class DoorKind(Enum):
    """How a door behaves beyond open/closed/locked.

    * ``LEAF`` - an ordinary solid door: NPCs shut (and relock) it behind themselves.
    * ``BARS`` - a barred gate such as a jail cell: see-through, and *nobody* closes or
      locks it as a side effect of walking through. It only changes state when something
      does so on purpose (the justice system locking a prisoner in, a release opening it,
      the player operating it). That is what keeps a released prisoner - and the jailer
      who let them out - from being shut in together.
    """
    LEAF = "leaf"
    BARS = "bars"


@dataclass
class DoorSchedule:
    """Automatic lock/unlock of a door at fixed hours (for doors nobody owns)."""
    open_hour: int
    close_hour: int
    open_message: Optional[str] = None
    close_message: Optional[str] = None


@dataclass
class Door:
    """A door leaf hinged at ``hinge_position`` that spans +x for ``width`` when closed
    and swings 90 degrees into -z when open.

    ``owners`` lists who is responsible for it: NPC names and/or faction tags
    (e.g. ``"guards"``). Owners shut and lock it behind themselves - but even
    an owner needs the key item for ``door_id`` to lock or unlock it.
    """
    door_id: str
    hinge_position: Vector3D
    width: float = 3.0
    height: float = 3.5
    thickness: float = 0.2
    is_locked: bool = True
    is_open: bool = False
    key_id: str = "shop_key"
    angle: float = 0.0
    schedule: Optional[DoorSchedule] = None
    owners: Tuple[str, ...] = ()
    lock_difficulty: int = 1           # 1 (simple latch) .. 5 (master lock): shrinks the lockpicking sweet spot
    kind: DoorKind = DoorKind.LEAF
    sealed: bool = False               # BARS only: a prisoner is inside - no NPC opens it, whatever keys it has

    @property
    def is_bars(self) -> bool:
        return self.kind is DoorKind.BARS

    @property
    def blocks_sight(self) -> bool:
        """Closed leaves hide what is behind them; bars never do."""
        return not self.is_open and not self.is_bars

    @property
    def auto_closes(self) -> bool:
        """Whether NPCs shut this door behind themselves (never for bars)."""
        return not self.is_bars

    @property
    def owner(self) -> Optional[str]:
        return self.owners[0] if self.owners else None

    def owned_by(self, name: str, faction: Optional[str] = None) -> bool:
        return name in self.owners or (faction is not None and faction in self.owners)

    # --- geometry -------------------------------------------------------------------
    def get_bounding_box(self) -> BoundingBox3D:
        """The doorway region (leaf when closed, plus a little slack either side)."""
        h = self.hinge_position
        return BoundingBox3D(Vector3D(h.x, h.y, h.z - 0.5), Vector3D(h.x + self.width, h.y + self.height, h.z + 0.5))

    @property
    def center(self) -> Vector3D:
        h = self.hinge_position
        return Vector3D(h.x + self.width / 2.0, h.y, h.z)

    def collider(self) -> BoundingBox3D:
        """Solid box of the leaf in its current pose (closed: across the doorway; open: folded into -z)."""
        h, half = self.hinge_position, self.thickness / 2.0
        if self.is_open:
            return BoundingBox3D(Vector3D(h.x - half, h.y, h.z - self.width), Vector3D(h.x + half, h.y + self.height, h.z + half))
        return BoundingBox3D(Vector3D(h.x, h.y, h.z - half), Vector3D(h.x + self.width, h.y + self.height, h.z + half))

    # --- state ------------------------------------------------------------------------
    def toggle(self) -> bool:
        """Open/close an unlocked door; returns the new ``is_open`` state."""
        self.is_open = not self.is_open
        return self.is_open

    def unlock_and_open(self) -> None:
        self.is_locked = False
        self.is_open = True

    def lock_and_close(self) -> None:
        self.is_locked = True
        self.is_open = False

    def apply_schedule(self, hour: int) -> Optional[str]:
        """Apply the door's schedule for ``hour``; returns a message to show, if any."""
        if self.schedule is None:
            return None
        if hour == self.schedule.open_hour:
            self.unlock_and_open()
            return self.schedule.open_message
        if hour == self.schedule.close_hour:
            self.lock_and_close()
            return self.schedule.close_message
        return None

    # --- persistence ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {"door_id": self.door_id, "is_locked": self.is_locked, "is_open": self.is_open, "sealed": self.sealed}

    def load_dict(self, data: dict) -> None:
        self.is_locked = data.get("is_locked", self.is_locked)
        self.is_open = data.get("is_open", self.is_open)
        self.sealed = data.get("sealed", self.sealed)
