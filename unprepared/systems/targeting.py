"""Work out what the player is looking at and what [E] would do.

Prompts depend on the player's stance: crouching is the *theft* stance - it is
the only way to pick locks or pockets (and why NPCs find it suspicious).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence, Union

from ..config import InteractionSettings
from ..core.math3d import BoundingBox3D, Vector3D, normalized, ray_box_distance, ray_intersects_box, view_direction
from ..entities import Door, NPC, Player


class TargetKind(Enum):
    DOOR = "door"
    NPC = "npc"
    CONTAINER = "container"
    STATION = "station"


class NPCAction(Enum):
    TALK = "talk"
    TRADE = "trade"
    PICKPOCKET = "pickpocket"
    TOO_FAR_TO_PICKPOCKET = "too_far"


@dataclass
class InteractionTarget:
    kind: TargetKind
    obj: Union[Door, NPC, object]
    prompt: str
    npc_action: Optional[NPCAction] = None

    @property
    def is_door(self) -> bool:
        return self.kind is TargetKind.DOOR

    @property
    def is_npc(self) -> bool:
        return self.kind is TargetKind.NPC

    @property
    def is_container(self) -> bool:
        return self.kind is TargetKind.CONTAINER

    @property
    def is_station(self) -> bool:
        return self.kind is TargetKind.STATION


def door_prompt(door: Door, player: Player) -> str:
    if not door.is_locked:
        return f"[E] {'Close Door' if door.is_open else 'Open Door'}"
    if player.has_key_for(door.door_id):
        return "[E] Unlock with Key"
    if player.is_crouching and player.has_lockpick():
        return "[E] Pick Lock"
    if player.is_crouching:
        return "[Locked] (no lockpick)"
    return "[Locked]"


def npc_action(npc: NPC, player: Player, settings: InteractionSettings) -> NPCAction:
    if player.is_crouching:
        if player.position.distance_to(npc.position) <= settings.pickpocket_range:
            return NPCAction.PICKPOCKET
        return NPCAction.TOO_FAR_TO_PICKPOCKET
    return NPCAction.TRADE if npc.is_open_for_business else NPCAction.TALK


def npc_prompt(npc: NPC, action: NPCAction) -> str:
    return {
        NPCAction.TRADE: f"[E] Talk / Trade with {npc.name}",
        NPCAction.TALK: f"[E] Talk to {npc.name}",
        NPCAction.PICKPOCKET: f"[E] Pickpocket {npc.name}",
        NPCAction.TOO_FAR_TO_PICKPOCKET: f"[Sneak closer to pickpocket {npc.name}]",
    }[action]


def container_prompt(container, player: Player) -> str:
    if getattr(container, "is_locked", False):
        if container.key_id and player.has_key_for(container.key_id):
            return f"[E] Unlock {container.label} with Key"
        if player.is_crouching and player.has_lockpick():
            return f"[E] Pick the {container.label} lock"
        if player.is_crouching:
            return f"[{container.label}: Locked] (no lockpick)"
        return f"[{container.label}: Locked]"
    return f"[E] Search {container.label}"


def resource_prompt(station, player: Player, settings=None) -> str:
    from .crafting import station_prompt
    return station_prompt(station, player, settings)


def _alignment(cam, view_dir, tx: float, ty: float, tz: float) -> float:
    """cos(angle) between the view direction and the direction to (tx, ty, tz); -1 if coincident."""
    dx, dy, dz, mag = normalized(tx - cam.x, ty - cam.y, tz - cam.z)
    if mag <= 0:
        return -1.0
    return view_dir[0] * dx + view_dir[1] * dy + view_dir[2] * dz


def _inflate(box: BoundingBox3D, amount: float) -> BoundingBox3D:
    return BoundingBox3D(Vector3D(box.min_point.x - amount, box.min_point.y - amount, box.min_point.z - amount),
                         Vector3D(box.max_point.x + amount, box.max_point.y + amount, box.max_point.z + amount))


def find_interaction_target(player: Player, doors: Sequence[Door], npcs: Sequence[NPC],
                            settings: InteractionSettings, containers: Sequence = (),
                            occluders: Sequence = (), resources: Sequence = (), game_settings=None) -> Optional[InteractionTarget]:
    """What the crosshair is on, else the best candidate inside the aim cone.

    1. **Crosshair ray.** A ray from the camera along the view direction is cast against
       the solid box of every door leaf, container, station and NPC in range. If it hits
       something before any wall (or closed door leaf) gets in the way, that is the target -
       however close the player stands and whichever part of the object is under the
       crosshair. This is what makes doors work from any angle and distance.
    2. **Aim cone.** Otherwise, among the candidates in range, inside the aim cone and not
       hidden behind an occluder, the one closest to the centre of the view wins. Doors are
       aimed at the middle of their doorway (the gap the walls leave for them) and only
       count when the player faces the doorway, not a door glimpsed edge-on along its wall.
       Closed door leaves also hide what is behind them.
    """
    view_dir = view_direction(player.rotation_y, player.rotation_x)
    cam = player.eye_position
    off_x, off_y = settings.door_aim_offset
    threshold = settings.aim_dot_threshold
    closed_leaves = [door.collider() for door in doors if door.blocks_sight]

    def make(kind: TargetKind, obj) -> InteractionTarget:
        if kind is TargetKind.DOOR:
            return InteractionTarget(kind, obj, door_prompt(obj, player))
        if kind is TargetKind.CONTAINER:
            return InteractionTarget(kind, obj, container_prompt(obj, player))
        if kind is TargetKind.STATION:
            return InteractionTarget(kind, obj, resource_prompt(obj, player, game_settings))
        action = npc_action(obj, player, settings)
        return InteractionTarget(kind, obj, npc_prompt(obj, action), action)

    # -- 1. crosshair ray -------------------------------------------------------------
    max_reach = max(settings.door_range, settings.npc_range, settings.container_range)
    blocker_distance = min((d for d in (ray_box_distance(cam, view_dir, box, max_reach) for box in occluders)
                            if d is not None), default=float("inf"))
    best_hit = None
    candidates = _ray_candidates(player, doors, npcs, containers, resources, settings) if settings.crosshair_ray else ()
    for kind, obj, box, reach in candidates:
        if cam.distance_to(_box_center(box)) > reach + 2.0:
            continue
        t = ray_box_distance(cam, view_dir, _inflate(box, 0.05), reach)
        if t is None:
            continue
        if t >= blocker_distance - 1e-6:
            continue
        if kind is not TargetKind.DOOR and any(_hits_before(cam, view_dir, leaf, t) for leaf in closed_leaves):
            continue                         # something behind a shut door
        if best_hit is None or t < best_hit[0]:
            best_hit = (t, kind, obj)
    if best_hit is not None:
        return make(best_hit[1], best_hit[2])

    # -- 2. aim cone ------------------------------------------------------------------
    def hidden(x: float, y: float, z: float, through_doors: bool = True) -> bool:
        target = Vector3D(x, y, z)
        if any(ray_intersects_box(cam, target, box) for box in occluders):
            return True
        return through_doors and any(ray_intersects_box(cam, target, leaf) for leaf in closed_leaves)

    best: Optional[InteractionTarget] = None
    best_dot = threshold

    for door in doors:
        h = door.hinge_position
        if cam.distance_to(h) <= settings.door_range:
            facing = view_dir[2] * (1.0 if h.z > cam.z else -1.0)
            if settings.door_facing_min > 0.0 and facing < settings.door_facing_min:
                continue
            dot = _alignment(cam, view_dir, h.x + off_x, h.y + off_y, h.z)
            if dot > best_dot and not hidden(h.x + off_x, h.y + off_y, h.z, through_doors=False):
                best, best_dot = make(TargetKind.DOOR, door), dot

    for container in containers:
        c = container.center
        if cam.distance_to(c) <= settings.container_range:
            dot = _alignment(cam, view_dir, c.x, c.y, c.z)
            if dot > best_dot and not hidden(c.x, c.y, c.z):
                best, best_dot = make(TargetKind.CONTAINER, container), dot

    for node in resources:
        c = node.center
        if cam.distance_to(c) <= settings.container_range:
            dot = _alignment(cam, view_dir, c.x, c.y, c.z)
            if dot > best_dot and not hidden(c.x, c.y, c.z):
                best, best_dot = make(TargetKind.STATION, node), dot

    for npc in npcs:
        p = npc.position
        if cam.distance_to(p) <= settings.npc_range:
            dot = _alignment(cam, view_dir, p.x, p.y + settings.npc_aim_height, p.z)
            if dot > best_dot and not hidden(p.x, p.y + settings.npc_aim_height, p.z):
                best, best_dot = make(TargetKind.NPC, npc), dot

    return best


def _hits_before(cam, view_dir, box, t: float) -> bool:
    d = ray_box_distance(cam, view_dir, box, t)
    return d is not None and d < t - 1e-6


def _box_center(box: BoundingBox3D) -> Vector3D:
    return Vector3D((box.min_point.x + box.max_point.x) / 2, (box.min_point.y + box.max_point.y) / 2,
                    (box.min_point.z + box.max_point.z) / 2)


def _ray_candidates(player, doors, npcs, containers, resources, settings):
    """(kind, object, solid box, reach) for everything the crosshair ray may hit."""
    for door in doors:
        yield TargetKind.DOOR, door, door.collider(), settings.door_range
    for container in containers:
        yield TargetKind.CONTAINER, container, container, settings.container_range
    for node in resources:
        yield TargetKind.STATION, node, node, settings.container_range
    for npc in npcs:
        p = npc.position
        body = BoundingBox3D.around(p, 0.9, 0.8, 0.9) if npc.is_asleep else BoundingBox3D.around(p, 0.35, 1.75, 0.35)
        yield TargetKind.NPC, npc, body, settings.npc_range
