"""Indoor light fixtures: one wall lantern per room and a candle on every table.

Buildings are dark by day (the ceiling keeps the sun out), so every room gets a
lit lantern and every table a candle - generated from the level geometry so a
new house or a new room is lit without listing anything. A *room* is a named
area whose centre lies inside a building (the shop floor, the space behind the
counter, the jail office, the cell); a building without such areas is one room.
The lantern hangs on the building wall nearest the room's centre that is not the
door wall, a little inside it; candles stand in the middle of table tops.
``World.is_dark_at`` treats a spot indoors as dark when no fixture is within
reach - which is what makes NPCs light their torches only where it is dark.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from ..core.math3d import Vector3D
from .level import AreaDef, BuildingDef, LevelDefinition, LightDef

LANTERN_HEIGHT = 2.9
LANTERN_INSET = 0.75      # walls are 0.5 thick: hang it just inside the inner face
CANDLE_RANGE = 4.5
LANTERN_RANGE = 9.0


def rooms_of(level: LevelDefinition, building: BuildingDef) -> List[AreaDef]:
    (x1, z1), (x2, z2) = building.min_xz, building.max_xz
    rooms = []
    for area in level.areas:
        cx, cz = (area.min_xz[0] + area.max_xz[0]) / 2.0, (area.min_xz[1] + area.max_xz[1]) / 2.0
        if x1 <= cx <= x2 and z1 <= cz <= z2:
            rooms.append(area)
    # drop an area that merely spans the whole building when it has sub-rooms inside it
    inner = [r for r in rooms if not (r.min_xz[0] <= x1 + 0.01 and r.max_xz[0] >= x2 - 0.01
                                      and r.min_xz[1] <= z1 + 0.01 and r.max_xz[1] >= z2 - 0.01)]
    if inner and len(inner) < len(rooms):
        outer = [r for r in rooms if r not in inner]
        # keep the outer area only where its own centre is not already inside an inner room
        for area in outer:
            cx, cz = (area.min_xz[0] + area.max_xz[0]) / 2.0, (area.min_xz[1] + area.max_xz[1]) / 2.0
            if not any(r.contains(cx, cz) for r in inner):
                inner.append(area)
        rooms = inner
    return rooms


def _door_walls(level: LevelDefinition, building: BuildingDef) -> set:
    """Which building walls ("north", "south", "east", "west") carry a door."""
    (x1, z1), (x2, z2) = building.min_xz, building.max_xz
    sides = set()
    for door in level.doors:
        hx, _, hz = door.hinge_position
        if x1 - 0.6 <= hx <= x2 + 0.6:
            if abs(hz - z1) < 0.6:
                sides.add("north")
            elif abs(hz - z2) < 0.6:
                sides.add("south")
        if z1 - 0.6 <= hz <= z2 + 0.6:
            if abs(hx - x1) < 0.6:
                sides.add("west")
            elif abs(hx - x2) < 0.6:
                sides.add("east")
    return sides


def lantern_for_room(level: LevelDefinition, building: BuildingDef, min_xz, max_xz, name: str) -> LightDef:
    """Mount a lantern on the nearest doorless building wall bordering the room."""
    (bx1, bz1), (bx2, bz2) = building.min_xz, building.max_xz
    cx, cz = (min_xz[0] + max_xz[0]) / 2.0, (min_xz[1] + max_xz[1]) / 2.0
    doors = _door_walls(level, building)
    candidates = []     # (distance, side, position, facing into the room)
    if abs(min_xz[1] - bz1) < 0.6:
        candidates.append((cz - bz1, "north", (cx, LANTERN_HEIGHT, bz1 + LANTERN_INSET), 180.0))
    if abs(max_xz[1] - bz2) < 0.6:
        candidates.append((bz2 - cz, "south", (cx, LANTERN_HEIGHT, bz2 - LANTERN_INSET), 0.0))
    if abs(min_xz[0] - bx1) < 0.6:
        candidates.append((cx - bx1, "west", (bx1 + LANTERN_INSET, LANTERN_HEIGHT, cz), 90.0))
    if abs(max_xz[0] - bx2) < 0.6:
        candidates.append((bx2 - cx, "east", (bx2 - LANTERN_INSET, LANTERN_HEIGHT, cz), 270.0))
    if not candidates:      # an inner room touching no outer wall: hang it from its own north edge
        candidates.append((0.0, "north", (cx, LANTERN_HEIGHT, min_xz[1] + LANTERN_INSET), 180.0))
    preferred = [c for c in candidates if c[1] not in doors] or candidates
    preferred.sort(key=lambda c: c[0])
    _, _, pos, facing = preferred[0]
    return LightDef("lantern", pos, facing=facing, room=name, range=LANTERN_RANGE)


def generate_fixtures(level: LevelDefinition, tables: Sequence = ()) -> List[LightDef]:
    """The standing rule: a lantern per room, a candle per table (plus the level's own list)."""
    fixtures: List[LightDef] = list(level.lights)
    if level.auto_lights:
        for building in level.buildings:
            rooms = rooms_of(level, building)
            if rooms:
                for room in rooms:
                    fixtures.append(lantern_for_room(level, building, room.min_xz, room.max_xz, room.name))
            else:
                fixtures.append(lantern_for_room(level, building, building.min_xz, building.max_xz, building.name))
        for table in tables:
            mn, mx = table.min_point, table.max_point
            fixtures.append(LightDef("candle", ((mn.x + mx.x) / 2.0, mx.y, (mn.z + mx.z) / 2.0),
                                     room=getattr(table, "name", ""), range=CANDLE_RANGE))
    return fixtures


def nearest_fixture(fixtures: Sequence[LightDef], position: Vector3D) -> Optional[LightDef]:
    best, best_d = None, float("inf")
    for f in fixtures:
        d = Vector3D(*f.position).distance_to(position)
        if d < best_d:
            best, best_d = f, d
    return best


def is_lit_by_fixture(fixtures: Sequence[LightDef], position: Vector3D) -> bool:
    return any(Vector3D(*f.position).distance_to(position) <= f.range for f in fixtures)
