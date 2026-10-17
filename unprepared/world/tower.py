"""A watchtower: a hollow square tower with a winding stair inside it, windows in its
walls, lanterns on every turn and a look-out platform with a parapet on top.

:func:`build_tower` turns a footprint into plain level data - walls, props (the
steps, the newel column, the platform), lights and a :class:`StairDef` - so the
level only says where the tower stands, how tall it is and which wall its door is
in. Steps and the platform are *floors*: the player climbs them (``World.floor_height_at``)
and NPCs follow the stair's waypoints (``World.find_path``); nothing else in the
game needs to know about height.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from .level import LightDef, PropDef, WallDef

Vec = Tuple[float, float, float]

STEP_RISE = 0.325            # height gained per step (the player may step up to ``STEP_UP``)
STEP_THICKNESS = 0.3
STEP_WIDTH = 1.6             # from the wall inwards
STEP_UP = 0.5                # the tallest rise a walker can step onto
CORNER = STEP_WIDTH          # a square corner step (the winding bit)
PARAPET = 1.2                # the wall above the platform
WINDOW_W, WINDOW_H = 1.2, 0.8
HEAD_ROOM = 1.75             # clearance a walker needs above a step


@dataclass(frozen=True)
class StairDef:
    """A stair NPCs can climb: ``bottom`` is on the ground at its foot, ``waypoints`` lead up
    it (x, y, z), ``top`` is the spot on the platform; ``region`` (x1, z1, x2, z2) is the
    footprint within which a person with y > 0 is 'up the tower'."""
    name: str
    bottom: Vec
    top: Vec
    waypoints: Tuple[Vec, ...]
    region: Tuple[float, float, float, float]

    def contains(self, x: float, z: float) -> bool:
        x1, z1, x2, z2 = self.region
        return x1 <= x <= x2 and z1 <= z <= z2


@dataclass
class Tower:
    walls: List[WallDef]
    props: List[PropDef]
    lights: List[LightDef]
    stair: StairDef
    platform_y: float
    wall_top: float


def _wall_with_windows(x1: float, z1: float, x2: float, z2: float, top: float, along_x: bool, texture: str,
                       windows: List[float]) -> List[WallDef]:
    """One tower wall split around small openings centred along it at the given heights."""
    if along_x:
        mid = (x1 + x2) / 2
        a1, a2 = mid - WINDOW_W / 2, mid + WINDOW_W / 2
        flank = [WallDef((x1, 0, z1), (a1, top, z2), texture=texture), WallDef((a2, 0, z1), (x2, top, z2), texture=texture)]
        column = lambda y1, y2: WallDef((a1, y1, z1), (a2, y2, z2), texture=texture)   # noqa: E731
    else:
        mid = (z1 + z2) / 2
        a1, a2 = mid - WINDOW_W / 2, mid + WINDOW_W / 2
        flank = [WallDef((x1, 0, z1), (x2, top, a1), texture=texture), WallDef((x1, 0, a2), (x2, top, z2), texture=texture)]
        column = lambda y1, y2: WallDef((x1, y1, a1), (x2, y2, a2), texture=texture)   # noqa: E731
    pieces = list(flank)
    y = 0.0
    for sill in sorted(windows):
        pieces.append(column(y, sill))
        y = sill + WINDOW_H
    pieces.append(column(y, top))
    return pieces


def build_tower(name: str, x1: float, z1: float, x2: float, z2: float, platform_y: float, door_x: float,
                door_width: float = 2.0, wall: float = 0.5, texture: str = "wall", room: str = "") -> Tower:
    """A square tower on the footprint (x1, z1)-(x2, z2) whose door is in its *south* wall (at z2,
    leaf from ``door_x``), the stair winding up anticlockwise from just inside the door."""
    room = room or name
    top = platform_y + PARAPET
    ix1, iz1, ix2, iz2 = x1 + wall, z1 + wall, x2 - wall, z2 - wall          # the interior
    walls: List[WallDef] = []
    levels = [h for h in (4.2, 8.4) if h + WINDOW_H < platform_y - 0.5]      # window sills
    walls += _wall_with_windows(x1, z1, ix1, z2, top, along_x=False, texture=texture, windows=levels)     # west
    walls += _wall_with_windows(ix2, z1, x2, z2, top, along_x=False, texture=texture, windows=levels)     # east
    walls += _wall_with_windows(x1, z1, x2, iz1, top, along_x=True, texture=texture, windows=levels)      # north
    # south wall: the door gap, the lintel above it and the rest up to the parapet
    walls.append(WallDef((x1, 0, iz2), (door_x, top, z2), texture=texture))
    walls.append(WallDef((door_x + door_width, 0, iz2), (x2, top, z2), texture=texture))
    walls.append(WallDef((door_x, 3.5, iz2), (door_x + door_width, top, z2), texture=texture))
    # the winding stair: round the inside of the walls, west wall first (north-bound), corner steps square
    props: List[PropDef] = []
    waypoints: List[Vec] = []
    straight = (ix2 - ix1) - 2 * CORNER
    n_straight = 3
    run = straight / n_straight
    steps_needed = int(round(platform_y / STEP_RISE))
    k = 0

    def add_step(bx1, bz1, bx2, bz2):
        nonlocal k
        top_y = STEP_RISE * (k + 1)
        props.append(PropDef(f"{name}_step_{k}", (bx1, top_y - STEP_THICKNESS, bz1), (bx2, top_y, bz2), texture="wood",
                             kind="step", solid=False))
        waypoints.append(((bx1 + bx2) / 2, top_y, (bz1 + bz2) / 2))
        k += 1

    while k < steps_needed:
        side = (k // (n_straight + 1)) % 4
        i = k % (n_straight + 1)
        if side == 0:                                   # west wall, heading north: straight then the NW corner
            if i < n_straight:
                z_end = iz2 - CORNER - i * run
                add_step(ix1, z_end - run, ix1 + STEP_WIDTH, z_end)
            else:
                add_step(ix1, iz1, ix1 + CORNER, iz1 + CORNER)
        elif side == 1:                                 # north wall, heading east: then the NE corner
            if i < n_straight:
                x_start = ix1 + CORNER + i * run
                add_step(x_start, iz1, x_start + run, iz1 + STEP_WIDTH)
            else:
                add_step(ix2 - CORNER, iz1, ix2, iz1 + CORNER)
        elif side == 2:                                 # east wall, heading south: then the SE corner
            if i < n_straight:
                z_start = iz1 + CORNER + i * run
                add_step(ix2 - STEP_WIDTH, z_start, ix2, z_start + run)
            else:
                add_step(ix2 - CORNER, iz2 - CORNER, ix2, iz2)
        else:                                           # south wall, heading west (over the door): then the SW corner
            if i < n_straight:
                x_end = ix2 - CORNER - i * run
                add_step(x_end - run, iz2 - STEP_WIDTH, x_end, iz2)
            else:
                add_step(ix1, iz2 - CORNER, ix1 + CORNER, iz2)
    # the newel column the stair winds round (solid: nobody falls down the shaft)
    cx, cz = (ix1 + ix2) / 2, (iz1 + iz2) / 2
    core = (ix2 - ix1) / 2 - STEP_WIDTH
    props.append(PropDef(f"{name}_column", (cx - core, 0, cz - core), (cx + core, platform_y, cz + core), texture="wall"))
    # the look-out platform: the interior less the footprints of the top steps, which arrive
    # under it (a walker on them needs head room)
    platform_boxes = [(ix1, iz1, ix2, iz2)]
    for step in props:
        if step.kind == "step" and step.max_point[1] + HEAD_ROOM + STEP_UP > platform_y - STEP_THICKNESS:
            hole = (step.min_point[0], step.min_point[2], step.max_point[0], step.max_point[2])
            platform_boxes = [piece for box in platform_boxes for piece in _subtract(box, hole)]
    for i, (bx1, bz1, bx2, bz2) in enumerate(platform_boxes):
        props.append(PropDef(f"{name}_platform_{i}", (bx1, platform_y - STEP_THICKNESS, bz1), (bx2, platform_y, bz2),
                             texture="wood", kind="floor", solid=False))
    # lanterns on the way up and a brazier-bright lantern on top
    lights: List[LightDef] = []
    for h in (6.8, 11.0):                          # (the ground floor gets the standing room lantern)
        if h < platform_y:
            lights.append(LightDef("lantern", (cx, h, iz1 + 0.35), room=room, facing=180.0, range=6.0))
    lights.append(LightDef("lantern", (ix2 - 0.35, platform_y + 1.9, cz), room=room, facing=270.0, range=7.0))
    # the stair as NPCs see it: its foot just inside the door, then every step, then the platform
    bottom = (door_x + door_width / 2, 0.0, iz2 - 0.8)   # just inside the door, where the stair starts
    top_spot = (cx + core + 0.6, platform_y, cz + 0.2)
    waypoints.append(top_spot)
    stair = StairDef(name, bottom, top_spot, tuple(waypoints), (x1, z1, x2, z2))
    return Tower(walls, props, lights, stair, platform_y, top)


def _subtract(outer: Tuple[float, float, float, float], hole: Tuple[float, float, float, float]) -> List[Tuple[float, float, float, float]]:
    """Rectangles covering ``outer`` minus ``hole`` (the hole clipped to the outer rectangle)."""
    ox1, oz1, ox2, oz2 = outer
    hx1, hz1, hx2, hz2 = max(hole[0], ox1), max(hole[1], oz1), min(hole[2], ox2), min(hole[3], oz2)
    if hx1 >= hx2 or hz1 >= hz2:
        return [outer]
    boxes = []
    if hz1 > oz1:
        boxes.append((ox1, oz1, ox2, hz1))                 # the strip north of the hole
    if hz2 < oz2:
        boxes.append((ox1, hz2, ox2, oz2))                 # south of it
    if hx1 > ox1:
        boxes.append((ox1, hz1, hx1, hz2))                 # west of it
    if hx2 < ox2:
        boxes.append((hx2, hz1, ox2, hz2))                 # east of it
    return boxes
