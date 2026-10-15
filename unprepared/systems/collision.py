"""Axis-separated box collision for the player against static/door colliders.

Movement is resolved per axis (x then z) so the player slides along walls
instead of sticking to them.
"""
from __future__ import annotations

import math
from typing import Sequence, Tuple

from ..core.math3d import BoundingBox3D, Vector3D
from ..entities import Player


def _blocked(player: Player, candidate: Vector3D, colliders: Sequence[BoundingBox3D]) -> bool:
    box = player.collision_box(candidate)
    return any(box.intersects(c) for c in colliders)


MAX_SUBSTEP = 0.2   # world units; smaller than any wall thickness so fast moves cannot tunnel


def move_with_collision(player: Player, dx: float, dz: float, colliders: Sequence[BoundingBox3D]) -> Tuple[float, float]:
    """Move the player by (dx, dz) as far as the colliders allow; returns the actual delta.

    The move is split into sub-steps of at most ``MAX_SUBSTEP`` and resolved per
    axis, so the player slides along walls and never passes through thin ones."""
    if not colliders:
        player.position.x += dx
        player.position.z += dz
        return dx, dz
    # Anything already overlapping the player (an NPC that squeezed past, a relocation into a
    # crowd) must never pin them down: it is ignored for this move so they can step clear.
    here = player.collision_box()
    colliders = [c for c in colliders if not here.intersects(c)]
    if not colliders:
        player.position.x += dx
        player.position.z += dz
        return dx, dz
    start_x, start_z = player.position.x, player.position.z
    steps = max(1, int(math.ceil(max(abs(dx), abs(dz)) / MAX_SUBSTEP)))
    step_x, step_z = dx / steps, dz / steps
    x_free, z_free = bool(dx), bool(dz)
    for _ in range(steps):
        if not x_free and not z_free:
            break
        if x_free:
            candidate = Vector3D(player.position.x + step_x, player.position.y, player.position.z)
            if _blocked(player, candidate, colliders):
                x_free = False
            else:
                player.position.x = candidate.x
        if z_free:
            candidate = Vector3D(player.position.x, player.position.y, player.position.z + step_z)
            if _blocked(player, candidate, colliders):
                z_free = False
            else:
                player.position.z = candidate.z
    return player.position.x - start_x, player.position.z - start_z
