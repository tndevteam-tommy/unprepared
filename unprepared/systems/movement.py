"""First-person ground movement."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..config import PlayerSettings
from ..core.math3d import BoundingBox3D, yaw_basis
from ..entities import Player
from .collision import move_with_collision


@dataclass(frozen=True)
class MoveIntent:
    forward: bool = False
    backward: bool = False
    left: bool = False
    right: bool = False
    sprint: bool = False

    @property
    def any(self) -> bool:
        return self.forward or self.backward or self.left or self.right


@dataclass(frozen=True)
class MovementResult:
    is_moving: bool = False
    is_sprinting: bool = False


def apply_movement(player: Player, intent: MoveIntent, delta_time: float, settings: PlayerSettings,
                   colliders: Sequence[BoundingBox3D] = ()) -> MovementResult:
    """Move ``player`` on the ground plane according to ``intent``, sliding along ``colliders``.

    ``is_moving`` reports whether a movement key was held; ``is_sprinting`` only
    when actually moving with the sprint key held.
    """
    if not intent.any:
        return MovementResult(False, False)

    move_speed = settings.walk_speed * delta_time
    is_sprinting = False
    if player.is_crouching:
        move_speed *= settings.crouch_speed_multiplier    # sneaking is slow (and there is no crouch-sprint)
    elif intent.sprint:
        move_speed *= settings.sprint_multiplier
        is_sprinting = True

    (forward_x, forward_z), (right_x, right_z) = yaw_basis(player.rotation_y)
    dx = dz = 0.0
    if intent.forward:
        dx += forward_x * move_speed
        dz += forward_z * move_speed
    if intent.backward:
        dx -= forward_x * move_speed
        dz -= forward_z * move_speed
    if intent.left:
        dx -= right_x * move_speed
        dz -= right_z * move_speed
    if intent.right:
        dx += right_x * move_speed
        dz += right_z * move_speed
    move_with_collision(player, dx, dz, colliders)
    return MovementResult(True, is_sprinting)
