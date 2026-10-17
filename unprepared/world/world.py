"""Live world state built from a :class:`LevelDefinition`, plus the town-level AI:
alarms and guard responses, investigations, trespass, curfews, shopkeeping and justice.
"""
from __future__ import annotations

import dataclasses
import random
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from ..config import GameSettings, DEFAULT_SETTINGS
from ..core import dialogue
from ..core.daynight import DayNightCycle
from ..core.math3d import BoundingBox3D, Vector3D, ray_intersects_box
from ..entities import AIState, Door, Item, NPC, Player, SkillType, TheftReport
from ..entities.inventory import add_item
from ..systems import commerce, justice
from ..systems import progression
from ..systems.stealth import roll, sneak_chance
from .fixtures import generate_fixtures, is_lit_by_fixture
from .inn import InnState
from .level import AreaDef, BuildingDef, Container, LevelDefinition, LightDef, Prop, RoadDef, Station, Wall
from .navigation import NavGrid
from .tower import STEP_UP, StairDef

Notify = Optional[Callable[[str], None]]

NPC_HALF_WIDTH, NPC_HEIGHT, NPC_LYING_THICKNESS = 0.4, 1.8, 0.5


@dataclass
class Relocation:
    """A request to move the player somewhere else (thrown out of a house, into a cell...).
    The presentation layer may delay ``apply`` until the screen has faded to black."""
    position: Vector3D
    yaw: Optional[float]
    reason: str
    applied: bool = False

    def apply(self, player: Player) -> None:
        player.position = Vector3D(self.position.x, player.position.y, self.position.z)
        if self.yaw is not None:
            player.rotation_y = self.yaw
            player.rotation_x = 0.0
        self.applied = True


class WorldClock:
    """Simulated time of day. ``time_scale`` simulated minutes pass per real second."""

    def __init__(self, start_hour: int = 7, time_scale: float = 2.5, minutes_per_hour: float = 60.0):
        self.hour = start_hour
        self.minute_accumulator = 0.0
        self.time_scale = time_scale
        self.minutes_per_hour = minutes_per_hour

    def advance(self, delta_time: float) -> bool:
        """Advance by ``delta_time`` real seconds; returns True when the hour ticked over."""
        self.minute_accumulator += delta_time * self.time_scale
        if self.minute_accumulator >= self.minutes_per_hour:
            self.minute_accumulator = 0.0
            self.hour = (self.hour + 1) % 24
            return True
        return False

    @property
    def fractional_hour(self) -> float:
        """Hour of day as a float (e.g. 7.5 = 07:30) - drives the sun and moon."""
        return self.hour + min(self.minute_accumulator, self.minutes_per_hour) / self.minutes_per_hour


class World:
    def __init__(self, level: LevelDefinition, settings: GameSettings = DEFAULT_SETTINGS, notify_callback: Notify = None):
        self.level = level
        self.settings = settings
        self.notify = notify_callback
        self.clock = WorldClock(settings.time.start_hour, settings.time.time_scale, settings.time.minutes_per_hour)
        self.daynight = DayNightCycle(settings.lighting.ambient_day_level, settings.lighting.ambient_night_level)
        self.walls: List[Wall] = [w.build() for w in level.walls]
        self.props: List[Prop] = [p.build() for p in level.props]
        self.containers: List[Container] = [c.build() for c in level.containers]
        # what each household keeps on its table: the food it started with, bought back in every few days
        self.pantries: Dict[str, List[Item]] = {c.name: [i.build() for i in c.items if i.is_food]
                                                for c in level.containers if c.kind == "table"}
        self.stations: List[Station] = [s.build() for s in level.stations]
        self.doors: List[Door] = [d.build() for d in level.doors]
        self.npcs: List[NPC] = [n.build(settings.perception, settings.npc) for n in level.npcs]
        self.anvil_position = Vector3D(*level.anvil_position)
        self.nav = NavGrid(self.static_obstacles(), dataclasses.replace(settings.navigation, bounds=level.bounds),
                           walls=self.walls)
        self.lintels: List[Wall] = self._build_lintels()
        self.stairs: List[StairDef] = list(level.stairs)
        self.floors: List[Prop] = [p for p in self.props if p.kind in ("step", "floor")]   # walkable surfaces above the ground
        self.fixtures: List[LightDef] = generate_fixtures(level, self.tables())
        self.roads: List[RoadDef] = self._build_roads()
        self.day_count = 0              # days elapsed since the game began
        self.elapsed = 0.0              # real seconds simulated
        self.player: Optional[Player] = None
        self.rng = random.Random(settings.random_seed)
        self.theft_reports: List[TheftReport] = []
        self.jail = justice.JailState.from_def(level.jail)
        self.inn = InnState.from_def(level.inn)
        self.conversations: list = []
        self.recent_topics: list = []               # openers used lately (kept short) so gossip varies
        self._chat_clock = 0.0
        # presentation hooks (set by Game): deferred relocations and "you have been caught" events
        self.relocation_handler: Optional[Callable[[Relocation], None]] = None
        self.caught_handler: Optional[Callable[[NPC], None]] = None
        self.relocations_in_flight: List[Relocation] = []
        for npc in self.npcs:
            npc.rng = self.rng                    # one seeded RNG for every phrasing and roll
        self.resync_schedules(announce=False, teleport=True)
        for npc in self.npcs:
            if npc.is_shopkeeper:
                commerce.remember_stock(npc, self)

    # --- convenience ---------------------------------------------------------------
    @property
    def simulated_hour(self) -> int:
        return self.clock.hour

    @simulated_hour.setter
    def simulated_hour(self, value: int) -> None:
        self.clock.hour = value

    @property
    def ambient_light(self) -> float:
        return self.daynight.ambient_light(self.clock.hour)

    @property
    def anvil_box(self) -> Optional[Station]:
        return self.find_station("anvil")

    def spawn_player(self) -> Player:
        lvl = self.level
        self.player = Player(Vector3D(*lvl.player_spawn), gold=lvl.player_gold,
                             inventory=[i.build() for i in lvl.player_inventory], settings=self.settings.player)
        for item in self.player.inventory:
            if not item.is_stolen:
                item.owner = item.PLAYER_OWNER
        return self.player

    @property
    def player_level(self) -> int:
        return self.player.level if self.player is not None else 1

    def find_area(self, name: str) -> Optional[AreaDef]:
        return next((a for a in self.level.areas if a.name == name), None)

    def area_def_at(self, position: Vector3D) -> Optional[AreaDef]:
        for area in self.level.areas:
            if area.contains(position.x, position.z):
                return area
        return None

    def area_of(self, position: Vector3D) -> str:
        area = self.area_def_at(position)
        return area.name if area is not None else self.level.default_area

    # --- indoors / outdoors -------------------------------------------------------------
    def building_at(self, position: Vector3D, include_open: bool = False) -> Optional[BuildingDef]:
        """The walled building whose footprint contains ``position`` (None outdoors). Roofs on
        posts (``open_sides``) only count when ``include_open`` is set."""
        for building in self.level.buildings:
            if building.open_sides and not include_open:
                continue
            (x1, z1), (x2, z2) = building.min_xz, building.max_xz
            if x1 <= position.x <= x2 and z1 <= position.z <= z2:
                return building
        return None

    def is_indoors(self, position: Vector3D) -> bool:
        return self.building_at(position) is not None

    def same_room(self, a: Vector3D, b: Vector3D) -> bool:
        """Both outdoors, or both inside the same building."""
        return self.building_at(a) is self.building_at(b)

    def tables(self) -> List[BoundingBox3D]:
        """Every table-shaped prop or container (they get candles)."""
        found: List[BoundingBox3D] = [p for p in self.props if "table" in p.name]
        found += [c for c in self.containers if getattr(c, "kind", "") == "table" or "table" in c.name]
        return found

    def is_dark_at(self, position: Vector3D) -> bool:
        """The torch rule, kept simple: outdoors it is dark whenever the sun is down or nearly so
        (``DayNightCycle.is_torch_time``, about 17:30-06:30) - no outdoor light changes that;
        indoors it is dark only where no lantern or candle reaches."""
        if self.is_indoors(position):
            return not is_lit_by_fixture(self.fixtures, position)
        return DayNightCycle.is_torch_time(self.clock.fractional_hour)

    def same_chamber(self, a: Vector3D, b: Vector3D) -> bool:
        """Both outdoors, or in the same building with no wall or shut door between them: the
        inn's hall and a guest room behind a closed door are *not* the same chamber, the shop
        floor and the space behind the counter are."""
        building = self.building_at(a)
        if building is not self.building_at(b):
            return False
        if building is None:
            return True
        pa, pb = Vector3D(a.x, 1.0, a.z), Vector3D(b.x, 1.0, b.z)
        return not any(ray_intersects_box(pa, pb, box) for box in self.walls_of(building))

    def walls_of(self, building: BuildingDef) -> List[BoundingBox3D]:
        """Wall segments and shut door leaves inside a building's footprint (interior partitions)."""
        (x1, z1), (x2, z2) = building.min_xz, building.max_xz
        boxes = [w for w in self.walls if w.min_point.x < x2 and w.max_point.x > x1 and w.min_point.z < z2 and w.max_point.z > z1]
        boxes += [d.collider() for d in self.doors if not d.is_open and not d.is_bars
                  and x1 <= d.hinge_position.x <= x2 and z1 <= d.hinge_position.z <= z2]
        return boxes

    def noise_attenuation(self, source: Vector3D, listener: Vector3D) -> float:
        """How much of a noise made at ``source`` reaches ``listener``: everything within the
        same chamber or open air, a fraction (``wall_noise_attenuation``) through walls -
        the walls of a building and the partitions and shut doors inside it alike."""
        return 1.0 if self.same_chamber(source, listener) else self.settings.perception.wall_noise_attenuation

    def exit_of(self, area_name: str) -> Optional[Vector3D]:
        """A spot just outside the door of a named building area (None for open areas).
        An area without a door of its own (a back room, the space behind a counter) uses
        the door of the building it is part of."""
        area = self.find_area(area_name)
        if area is None:
            return None
        centre = Vector3D((area.min_xz[0] + area.max_xz[0]) / 2.0, 0.0, (area.min_xz[1] + area.max_xz[1]) / 2.0)
        building = self.building_at(centre)
        if building is None:
            return None                                   # open ground: nothing to be thrown out of
        (x1, z1), (x2, z2) = building.min_xz, building.max_xz
        cz = (z1 + z2) / 2.0
        for door in self.doors:
            h = door.hinge_position
            if x1 - 0.6 <= h.x <= x2 + 0.6 and z1 - 0.6 <= h.z <= z2 + 0.6:
                outward = 1.0 if h.z >= cz else -1.0
                spot = Vector3D(h.x + door.width / 2.0, 0.0, h.z + outward * 2.0)
                if self.building_at(spot) is not building:
                    return spot
        return None

    def waiting_spot_for(self, target: Vector3D) -> Optional[Vector3D]:
        """Where to wait for a building that is shut: just outside its door."""
        return self.exit_of(self.area_of(target))

    def find_door(self, door_id: str) -> Optional[Door]:
        return next((d for d in self.doors if d.door_id == door_id), None)

    def find_npc(self, name: str) -> Optional[NPC]:
        return next((n for n in self.npcs if n.name == name), None)

    def find_container(self, name: str) -> Optional[Container]:
        return next((c for c in self.containers if c.name == name), None)

    def find_station(self, name: str) -> Optional[Station]:
        return next((s for s in self.stations if s.name == name), None)

    def npcs_within(self, position: Vector3D, radius: float) -> List[NPC]:
        return [npc for npc in self.npcs if position.distance_to(npc.position) <= radius]

    def guards(self) -> List[NPC]:
        return [n for n in self.npcs if n.is_guard]

    def merchant_stock(self, npc: NPC) -> commerce.MerchantStock:
        return commerce.MerchantStock(npc, self)

    def owner_inventory_for(self, item):
        """Where a stolen item belongs: the container or NPC whose base stock lists its id,
        else the confiscation lockbox."""
        for cdef in self.level.containers:
            if any(i.id == item.id for i in cdef.items):
                container = self.find_container(cdef.name)
                if container is not None:
                    return container.inventory
        for npc in self.npcs:
            if any(i.id == item.id for i in npc.base_inventory) or any(
                    i.id == item.id for tier in npc.restock_tiers for i in tier.items):
                return npc.inventory
        chest = self.find_container(self.jail.storage_name)
        return chest.inventory if chest is not None else self.npcs[0].inventory

    # --- geometry ------------------------------------------------------------------
    def static_obstacles(self) -> List[BoundingBox3D]:
        """Everything solid that never moves: walls, props (bar decoration), containers and stations."""
        return [*self.walls, *(p for p in self.props if p.solid), *self.containers, *self.stations]

    def _build_lintels(self) -> List[Wall]:
        """Beams filling the gap between every door top and the ceiling. Purely visual:
        above head height, so they are neither colliders nor navigation obstacles."""
        lintels = []
        for door in self.doors:
            h = door.hinge_position
            building = self.building_at(Vector3D(h.x + door.width / 2.0, 0.0, h.z - 0.3)) or \
                self.building_at(Vector3D(h.x + door.width / 2.0, 0.0, h.z + 0.3))
            top = building.wall_height if building is not None else door.height + 0.5
            if top <= door.height:
                continue
            texture = "building"
            for wall in self.walls:          # match the neighbouring wall's look
                if wall.min_point.z - 0.3 <= h.z <= wall.max_point.z + 0.3 and (
                        abs(wall.max_point.x - h.x) < 0.6 or abs(wall.min_point.x - (h.x + door.width)) < 0.6):
                    texture = wall.texture
                    break
            half = 0.25
            lintels.append(Wall(BoundingBox3D(Vector3D(h.x, door.height, h.z - half),
                                              Vector3D(h.x + door.width, top, h.z + half)), texture))
        return lintels

    def _build_roads(self) -> List[RoadDef]:
        """The level's paving plus a doorstep for every door that stands back from it."""
        roads = list(self.level.roads)
        for door in self.doors:
            h = door.hinge_position
            cx = h.x + door.width / 2.0
            best, best_gap = None, None
            for road in self.level.roads:
                (x1, z1), (x2, z2) = road.min_xz, road.max_xz
                if not (x1 <= cx <= x2):
                    continue
                if z1 <= h.z <= z2:
                    best, best_gap = None, 0.0        # the door opens straight onto the paving
                    break
                gap = z1 - h.z if h.z < z1 else h.z - z2
                if best_gap is None or gap < best_gap:
                    best, best_gap = road, gap
            if best is not None and best_gap > 0.05:
                (x1, z1), (x2, z2) = best.min_xz, best.max_xz
                za, zb = (h.z, z1) if h.z < z1 else (z2, h.z)
                roads.append(RoadDef((h.x - 0.5, za), (h.x + door.width + 0.5, zb), best.texture))
        return roads

    def body_circles(self, exclude: Optional[NPC] = None) -> List[Tuple[float, float, float, float]]:
        """(x, z, radius, y) of every awake NPC (and the player) somebody could bump into."""
        bodies = []
        for npc in self.npcs:
            if npc is exclude or npc.is_asleep:
                continue
            bodies.append((npc.position.x, npc.position.z, NPC.BODY_RADIUS, npc.position.y))
        if self.player is not None:
            bodies.append((self.player.position.x, self.player.position.z, self.settings.player.collision_radius,
                           self.player.position.y))
        return bodies

    def bodies_near(self, npc: NPC, radius: float = 6.0) -> List[Tuple[float, float, float]]:
        """(x, z, radius) of the people an NPC could bump into: close by and on the same level
        (somebody up the tower is no obstacle to somebody at its foot)."""
        p = npc.position
        return [(x, z, r) for x, z, r, y in self.body_circles(exclude=npc)
                if (x - p.x) ** 2 + (z - p.z) ** 2 <= radius * radius and abs(y - p.y) < 1.5]

    def npc_colliders(self) -> List[BoundingBox3D]:
        """Upright NPC bodies as boxes the player cannot walk through (sleepers are on beds, which already block)."""
        return [BoundingBox3D.around(n.position, NPC.BODY_RADIUS, NPC_HEIGHT, NPC.BODY_RADIUS)
                for n in self.npcs if not n.is_asleep]

    def colliders(self, include_npcs: bool = True, walker_y: Optional[float] = None) -> List[BoundingBox3D]:
        """Everything the player collides with right now (static geometry, door leaves, people).
        Steps and platforms (``floors``) are solid too - except the ones a walker standing at
        ``walker_y`` could step onto, which the floor rule handles instead."""
        boxes = [*self.static_obstacles(), *(door.collider() for door in self.doors)]
        y = self.player.position.y if walker_y is None and self.player is not None else (walker_y or 0.0)
        boxes.extend(f for f in self.floors if f.max_point.y > y + STEP_UP)
        if include_npcs:
            boxes.extend(self.npc_colliders())
        return boxes

    def floor_height_at(self, x: float, z: float, current_y: float) -> float:
        """The floor under (x, z) for somebody standing at ``current_y``: the highest step or
        platform there that is no more than a step up (``STEP_UP``), else the ground."""
        best = 0.0
        for f in self.floors:
            if f.min_point.x <= x <= f.max_point.x and f.min_point.z <= z <= f.max_point.z:
                top = f.max_point.y
                if top <= current_y + STEP_UP and top > best:
                    best = top
        return best

    def stair_under(self, position: Vector3D) -> Optional[StairDef]:
        """The stair somebody up a tower (y > 0 inside its footprint) is on."""
        if position.y <= 0.05:
            return None
        return next((st for st in self.stairs if st.contains(position.x, position.z)), None)

    def stair_to(self, goal: Vector3D) -> Optional[StairDef]:
        """The stair that leads to ``goal`` (a spot up a tower)."""
        if goal.y <= 0.05:
            return None
        return next((st for st in self.stairs if st.contains(goal.x, goal.z)), None)

    def push_out_of_doors(self, player: Player) -> bool:
        """If a door leaf was swung into the player, shove them clear of it (never trap them)."""
        moved = False
        for door in self.doors:
            leaf = door.collider()
            box = player.collision_box()
            if not box.intersects(leaf):
                continue
            r = self.settings.player.collision_radius + 0.05
            if door.is_open:      # leaf lies along z at the hinge: push sideways in x
                if player.position.x >= door.hinge_position.x:
                    player.position.x = leaf.max_point.x + r
                else:
                    player.position.x = leaf.min_point.x - r
            else:                 # leaf lies along x at the hinge z: push in z
                if player.position.z >= door.hinge_position.z:
                    player.position.z = leaf.max_point.z + r
                else:
                    player.position.z = leaf.min_point.z - r
            moved = True
        return moved

    def sight_blockers(self) -> List[BoundingBox3D]:
        """Geometry that blocks line of sight: static obstacles, steps and platforms (nobody sees
        through a floor) plus closed door leaves (bars are see-through)."""
        return [*self.static_obstacles(), *self.floors, *(door.collider() for door in self.doors if door.blocks_sight)]

    def prop_under(self, position: Vector3D) -> Optional[BoundingBox3D]:
        """The prop/container whose footprint contains ``position`` (a bed an NPC lies on), if any."""
        for box in (*self.props, *self.containers):
            if box.min_point.x <= position.x <= box.max_point.x and box.min_point.z <= position.z <= box.max_point.z:
                return box
        return None

    def npc_body_box(self, npc: NPC) -> BoundingBox3D:
        """The NPC's body volume: upright normally, lying flat (on top of its bed) while asleep."""
        p = npc.position
        if not npc.is_asleep:
            return BoundingBox3D.around(p, NPC_HALF_WIDTH, NPC_HEIGHT, NPC_HALF_WIDTH)
        bed = self.prop_under(p)
        base_y = bed.max_point.y if bed is not None else p.y
        along_x = bed is None or (bed.max_point.x - bed.min_point.x) >= (bed.max_point.z - bed.min_point.z)
        half_len, half_w = NPC_HEIGHT / 2.0, NPC_HALF_WIDTH
        hx, hz = (half_len, half_w) if along_x else (half_w, half_len)
        return BoundingBox3D(Vector3D(p.x - hx, base_y, p.z - hz), Vector3D(p.x + hx, base_y + NPC_LYING_THICKNESS, p.z + hz))

    def find_path(self, npc: NPC, goal: Vector3D) -> List[Vector3D]:
        """A walk from the NPC to ``goal``: over the navigation grid on the ground, with the
        stair waypoints spliced in to get down from (or up) a tower."""
        here = self.stair_under(npc.position)
        there = self.stair_to(goal)
        path: List[Vector3D] = []
        start = npc.position
        if here is not None:
            if there is here:
                return self._stair_path(here, npc.position, goal)
            path += self._stair_path(here, npc.position, Vector3D(*here.bottom))
            start = Vector3D(*here.bottom)
        if there is not None:
            ground = self.nav.find_path(start, Vector3D(*there.bottom), self.doors, npc.can_open)
            if not ground and start.distance_to(Vector3D(*there.bottom)) > self.settings.npc.arrival_tolerance:
                return []
            return path + ground + self._stair_path(there, Vector3D(*there.bottom), goal)
        ground = self.nav.find_path(start, goal, self.doors, npc.can_open)
        if here is not None and not ground and start.distance_to(goal) > self.settings.npc.arrival_tolerance:
            return []
        return path + ground

    @staticmethod
    def _stair_path(stair: StairDef, start: Vector3D, goal: Vector3D) -> List[Vector3D]:
        """Waypoints along a stair between two of its points (up or down)."""
        points = [Vector3D(*stair.bottom), *(Vector3D(*p) for p in stair.waypoints)]

        def nearest(p: Vector3D) -> int:
            return min(range(len(points)), key=lambda i: points[i].distance_to(p))

        a, b = nearest(start), nearest(goal)
        leg = points[a:b + 1] if a <= b else points[b:a + 1][::-1]
        if goal.distance_to(points[b]) > 0.3:
            leg = leg + [goal.copy()]
        return [p.copy() for p in leg]

    # --- trust ----------------------------------------------------------------------
    def area_trusts_player(self, area: AreaDef) -> bool:
        """Is the player a welcome guest here (outside curfew hours)? Explicitly via
        ``trusted_by``, or - the standing rule - because a fence owns the place: a fence's
        house is always open to the player by day, and nobody, guards included, objects."""
        if area.curfew_active(self.clock.hour):
            return False
        if area.trusted_by:
            return True
        if self.inn.rented_area == area.name and self.inn.is_rented(self.day_count, self.clock.hour):
            return True                                   # a paying guest's room
        owner = self.find_npc(area.owner) if area.owner else None
        return owner is not None and owner.is_fence

    @property
    def beds(self) -> List[Prop]:
        return [p for p in self.props if p.is_bed]

    def player_may_sleep_in(self, bed: Prop) -> bool:
        """The player's own bed (``owner == "player"``) or the bed of the inn room they are renting."""
        if bed.owner == Item.PLAYER_OWNER:
            return True
        inn = self.inn
        if inn.rented_room is None or not inn.is_rented(self.day_count, self.clock.hour):
            return False
        bx, _, bz = inn.rooms[inn.rented_room].bed
        return bed.min_point.x <= bx <= bed.max_point.x and bed.min_point.z <= bz <= bed.max_point.z

    def is_complimentary(self, container: Container, item: Item) -> bool:
        """Food and drink in the inn are on the house for a paying guest."""
        inn = self.inn
        return (inn.present and inn.keeper is not None and container.owner == inn.keeper and item.is_food
                and inn.is_rented(self.day_count, self.clock.hour))

    def note_complimentary(self, container: Container, item: Item) -> None:
        """A free meal taken: keep the keeper's stock count in step so it is not a theft to be
        discovered at the next stock-take."""
        keeper = self.find_npc(self.inn.keeper) if self.inn.keeper else None
        if keeper is not None and container.name in keeper.shop_containers:
            commerce.note_sale(keeper, item, -1)

    def is_trespassing(self, player: Player, npc: NPC) -> bool:
        """Would ``npc`` object to where the player stands right now?"""
        area = self.area_def_at(player.position)
        if area is None or not area.restricted or area.is_open_to_public(self.clock.hour):
            return False
        if self.area_trusts_player(area) or npc.name in area.trusted_by:
            return False
        if area.name in (self.jail.cell_area, self.jail.jail_area):
            if self.jail.sealed:
                return False                          # a prisoner belongs in the cell
            if self.jail.released or self.elapsed < self.jail.grace_until:
                return False                          # just released: collecting their things
        responsible = area.owner in (npc.name, npc.faction)
        return responsible or npc.is_guard

    def player_unwelcome_at(self, position: Vector3D) -> Optional[AreaDef]:
        """The restricted area the player has no business in at ``position`` (None if fine)."""
        area = self.area_def_at(position)
        if area is None or not area.restricted or area.is_open_to_public(self.clock.hour):
            return None
        if area.name in (self.jail.cell_area, self.jail.jail_area) and (
                self.jail.sealed or self.jail.released or self.elapsed < self.jail.grace_until):
            return None
        if self.area_trusts_player(area):
            return None
        return area

    # --- relocation (thrown out / jailed) -----------------------------------------------
    def relocate_player(self, position: Vector3D, yaw: Optional[float] = None, reason: str = "") -> Relocation:
        """Move the player, via the presentation's handler (fade to black) when one is installed."""
        request = Relocation(position.copy(), yaw, reason)
        if self.relocation_handler is not None:
            self.relocations_in_flight.append(request)
            self.relocation_handler(request)
        elif self.player is not None:
            request.apply(self.player)
        return request

    @property
    def relocating(self) -> bool:
        """A relocation has been requested but not applied yet (the screen is fading)."""
        self.relocations_in_flight = [r for r in self.relocations_in_flight if not r.applied]
        return bool(self.relocations_in_flight)

    def player_caught(self, by: NPC) -> None:
        """An NPC has the player bang to rights: the player turns to face them and whatever
        screen they had open (a mini-game, somebody's pockets) is closed by the game."""
        if self.player is not None:
            self.player.hold_attention(by.position, self.settings.justice.caught_freeze_seconds)
        if self.caught_handler is not None:
            self.caught_handler(by)

    def throw_out(self, player: Player, area_name: str, by: Optional[NPC] = None, line: Optional[str] = None) -> bool:
        """The standard eviction: out of the building's door, facing away from it."""
        exit_pos = self.exit_of(area_name)
        if exit_pos is None:
            return False
        if by is not None:
            self.player_caught(by)
        if line and self.notify:
            self.notify(line)
        yaw = None
        area = self.find_area(area_name)
        if area is not None:
            cz = (area.min_xz[1] + area.max_xz[1]) / 2.0
            yaw = 180.0 if exit_pos.z > cz else 0.0     # face away from the door
        self.relocate_player(exit_pos, yaw=yaw, reason="evicted")
        return True

    def evict_if_trespassing(self, player: Player, guard: NPC, notify: Notify = None) -> bool:
        """Caught somewhere they should not be: the guard shows them the door as well."""
        area = self.player_unwelcome_at(player.position)
        if area is None:
            return False
        return self.throw_out(player, area.name, by=guard,
                              line=f"({guard.name}): \"And you've no business in {area.name}. Out!\" You are thrown out.")

    # --- simulation ---------------------------------------------------------------
    def resync_schedules(self, announce: bool = True, teleport: bool = False, doors: bool = True) -> None:
        """Put every NPC on the task for the current hour. ``doors=False`` (loading a save) keeps
        every door exactly as saved: NPCs resume their tasks without re-applying lock/unlock effects."""
        notify = self.notify if announce else None
        for npc in self.npcs:
            task = npc.task_for(self.clock.hour)
            if teleport and task is not None:
                self._replay_day_until(npc, self.clock.hour)
                npc.position = task.target_pos.copy()
            npc.update_schedule(self.clock.hour, notify, world=self, doors=doors)

    def _replay_day_until(self, npc: NPC, hour: int) -> None:
        """Apply the door side effects of every task the NPC has already completed today,
        including locking its own doors behind it whenever it moved between areas."""
        tasks = sorted(npc.schedule, key=lambda t: t.start_hour)
        for idx, task in enumerate(tasks):
            if task.end_hour > hour:
                continue
            for door_id in task.unlock_doors:
                door = self.find_door(door_id)
                if door is not None:
                    door.is_locked = False
            for door_id in task.open_doors:
                door = self.find_door(door_id)
                if door is not None:
                    door.unlock_and_open()
            for door_id in task.close_doors:
                door = self.find_door(door_id)
                if door is not None:
                    door.is_open = False
            for door_id in (*task.lock_doors, *task.lock_doors_on_departure):
                door = self.find_door(door_id)
                if door is not None:
                    door.lock_and_close()
            following = tasks[idx + 1] if idx + 1 < len(tasks) else None
            if following is not None and self.building_at(task.target_pos, True) is not self.building_at(following.target_pos, True):
                for door in self.doors:               # leaving the building: its owner locks up behind itself
                    if door.auto_closes and npc.owns(door) and npc.can_lock(door):
                        door.lock_and_close()

    def update_time(self, delta_time: float) -> bool:
        """Advance the clock; on a new hour apply door schedules and NPC schedules."""
        self.elapsed += delta_time
        if not self.clock.advance(delta_time):
            return False
        hour = self.clock.hour
        for npc in self.npcs:
            npc.time = self.elapsed                 # so anything said on the hour is timed right
        if hour == 0:
            self.day_count += 1
            self._daily_upkeep()
        for door in self.doors:
            msg = door.apply_schedule(hour)
            if msg and self.notify:
                self.notify(msg)
        if self.notify:
            self.notify(f"Time Update: {hour:02d}:00 hours")
        for npc in self.npcs:
            npc.update_schedule(hour, self.notify, world=self)
        if self.player is not None:
            justice.update_jail(self, self.player, self.notify)
            self.inn.update(self, self.player, self.notify)
        return True

    def _daily_upkeep(self) -> None:
        """Midnight: NPCs replace missing personal items (a guard requisitions a new key) and,
        every restock cycle, top their purses back up to their usual amount."""
        for npc in self.npcs:
            if self.day_count - npc.last_inventory_reset_day >= npc.inventory_reset_days:
                restored = npc.reset_inventory(self.day_count)
                if restored and self.notify and any(i.is_key for i in restored):
                    self.notify(f"({npc.name}) has been issued a new key.")
            if self.day_count - npc.last_gold_restock_day >= npc.restock_days:
                npc.gold = max(npc.gold, npc.base_gold)
                npc.last_gold_restock_day = self.day_count
        if self.day_count % max(1, self.settings.economy.pantry_restock_days) == 0:
            self._restock_pantries()

    def _restock_pantries(self) -> None:
        """Households buy provisions: every kitchen table is topped back up to the food it started with."""
        for container in self.containers:
            for stock in self.pantries.get(container.name, ()):
                have = next((i for i in container.inventory if i.id == stock.id), None)
                if have is None:
                    add_item(container.inventory, dataclasses.replace(stock))
                elif have.quantity < stock.quantity:
                    have.quantity = stock.quantity

    def wait_hours(self, hours: float, step: float = 0.5) -> None:
        """Pass time quickly (the player stands still); NPCs keep living their routines."""
        for _ in range(int(hours * (self.clock.minutes_per_hour / self.clock.time_scale) / step)):
            self.update_time(step)
            self.update_npcs(step)

    def wait_until(self, hour: int, step: float = 0.5) -> None:
        """Pass time until the clock next strikes ``hour`` (a full day if it is that hour already)."""
        steps = 0
        limit = int(25 * (self.clock.minutes_per_hour / self.clock.time_scale) / step)
        while steps < limit:
            ticked = self.update_time(step)
            self.update_npcs(step)
            steps += 1
            if ticked and self.clock.hour == hour:
                break
        self.clock.minute_accumulator = 0.0

    def update_npcs(self, delta_time: float) -> None:
        for npc in self.npcs:
            if not npc.is_asleep and not npc.path:
                self._get_out_of_bed(npc)
            npc.update_movement(delta_time, self, self.notify)
            self._tick_ai(npc, delta_time)
            npc.has_torch = not npc.is_asleep and self.is_dark_at(npc.position)     # lit wherever it is dark
        self._tick_talk(delta_time)
        if self.player is not None:
            self.push_out_of_doors(self.player)
            self._tick_jail()
            self._tick_curfews(delta_time)

    def _get_out_of_bed(self, npc: NPC) -> None:
        """An awake NPC standing on a bed (just woken) steps off it to the nearest free spot."""
        under = self.prop_under(npc.position)
        if under is None or "bed" not in getattr(under, "name", ""):
            return
        cell = self.nav.nearest_free(self.nav.to_cell(npc.position.x, npc.position.z), self.nav.static_blocked)
        if cell is not None:
            spot = self.nav.to_world(cell, npc.position.y)
            npc.position.x, npc.position.z = spot.x, spot.z

    # --- jail house ----------------------------------------------------------------
    def _tick_jail(self) -> None:
        jail = self.jail
        if self.relocating:
            return                                   # the player is on their way somewhere; judge them on arrival
        if jail.serving:
            justice.check_jailbreak(self, self.player, self.notify)
        elif jail.released:
            left = self.area_of(self.player.position) not in (jail.cell_area, jail.jail_area)
            if left or self.elapsed >= jail.grace_until:
                justice.end_release(self, self.notify)

    # --- town AI ----------------------------------------------------------------------
    def _tick_ai(self, npc: NPC, delta_time: float) -> None:
        """Investigations, alarm responses and tailing: what an NPC does off its routine."""
        npc.retry_blocked_task(self, delta_time, self.notify)
        if npc.state is AIState.INVESTIGATING:
            if npc.heard_noise_at is not None and npc.goal is None and npc.is_guard:
                self._investigate(npc, npc.heard_noise_at)
                npc.heard_noise_at = None
            if not npc.path:
                npc.search_timer += delta_time
                if (npc.goal is not None and npc.search_timer > 3.0
                        and npc.suspicion_meter < self.settings.perception.schedule_override_threshold):
                    # nothing found here: have a look around (a guard with a suspect in view keeps
                    # watching them instead - see _watch_and_follow)
                    npc.turn_towards(Vector3D(npc.position.x + 1, 0, npc.position.z))
                if npc.search_timer >= npc.SEARCH_SECONDS * 0.5:
                    npc.resume_routine(self, self.notify)
        elif npc.state is AIState.RESPONDING and npc.report_to is not None:
            self._go_and_take_report(npc, delta_time)
        elif npc.state is AIState.RESPONDING:
            if not npc.path:
                npc.search_timer += delta_time
                if npc.search_timer >= npc.SEARCH_SECONDS:
                    if npc.search_timer - delta_time < npc.SEARCH_SECONDS:
                        npc.say(npc.phrase("gone"), self.notify)
                    npc.resume_routine(self, self.notify)
        elif npc.state is AIState.FOLLOWING:
            npc.follow_timer += delta_time
            if npc.follow_timer >= npc.FOLLOW_SECONDS:
                npc.resume_routine(self, self.notify)
        elif npc.state is AIState.ALERT_GUARDS:
            npc.search_timer += delta_time
            if npc.search_timer >= npc.SEARCH_SECONDS:
                npc.resume_routine(self, self.notify)
        elif npc.state is AIState.REPORTING:
            npc.search_timer += delta_time
            if npc.search_timer >= npc.SEARCH_SECONDS * 0.5:
                npc.resume_routine(self, self.notify)
        elif npc.state is AIState.WAITING:
            if self.player is not None and not npc.path:
                npc.turn_towards(self.player.position)
            if npc.waiting_for == "release" and not self.jail.released:
                npc.stop_waiting(self, self.notify)
        elif npc.is_guard and npc.heard_noise_at is not None and npc.state in (AIState.PATROL, AIState.GUARDING):
            where = npc.heard_noise_at
            npc.heard_noise_at = None
            if self._noise_from_cell(where):
                npc.scold("cell_noise", "cell_noise", self.notify, grace=False)
            else:
                self._investigate(npc, where)
                npc.say(npc.phrase("investigate"), self.notify)
        else:
            npc.heard_noise_at = None
        self._ambient_chatter(npc, delta_time)

    def _noise_from_cell(self, where: Vector3D) -> bool:
        """A sealed prisoner rattling about is never a reason to open the cell."""
        return self.jail.sealed and self.area_of(where) == self.jail.cell_area

    def _investigate(self, npc: NPC, where: Vector3D) -> None:
        if self._noise_from_cell(where):
            return
        npc.go_to(self, where, AIState.INVESTIGATING)

    def report_crime_to_witnesses(self, crime_name: str, player_pos: Vector3D) -> List[NPC]:
        """Let every NPC try to witness a crime; witnesses raise the alarm. Returns them."""
        blockers = self.sight_blockers()
        witnesses = [npc for npc in self.npcs if npc.witness_crime(crime_name, player_pos, blockers, self.notify)]
        if witnesses:
            self.declare_crime(crime_name, player_pos.copy(), witnessed=True,
                               reporter=witnesses[0].name, witnesses=witnesses)
        return witnesses

    def declare_crime(self, crime: str, location: Vector3D, witnessed: bool, reporter: str,
                      witnesses: Optional[List[NPC]] = None) -> None:
        """A crime became known: guards who saw it remember it for weeks, the others hear the
        cry for help (if they are close enough to), remember it for days and come running."""
        fine = justice.fine_for(crime, self.settings.justice)
        witnesses = witnesses or []
        reporting = self.find_npc(reporter)
        for witness in [*witnesses, *([reporting] if reporting is not None else [])]:
            witness.remember_sighting(self.area_of(location), self.day_count)
        for guard in self.guards():
            saw_it = guard in witnesses
            if not saw_it and not self.can_hear_cry(guard, location):
                continue
            guard.remember_crime(crime, self.day_count, saw_it, fine, self.rng)
            if not saw_it:
                self._send_guard(guard, location)
        if self.player is not None:
            self.player.crimes_witnessed += len(witnesses)

    def can_hear_cry(self, npc: NPC, location: Vector3D) -> bool:
        """A shout for the guards carries ``shout_radius`` in the open, less through walls. A
        look-out up a tower is in the open air, whatever the footprint below him says."""
        s = self.settings.perception
        in_the_open = self.same_room(location, npc.position) or (npc.position.y > 2.0 and not self.is_indoors(location))
        reach = s.shout_radius * (1.0 if in_the_open else s.shout_wall_attenuation)
        return npc.position.distance_to(location) <= reach

    def _send_guard(self, guard: NPC, location: Vector3D) -> None:
        if guard.state is AIState.RESPONDING or self.jail.sealed and guard.name == self.jail.jailer:
            return
        was_asleep = guard.is_asleep
        guard.end_conversation()
        guard.state = AIState.GUARDING
        guard.search_timer = 0.0
        guard.go_to(self, location, AIState.RESPONDING)
        guard.say(guard.phrase("cry_response"), self.notify, log_prefix=f"{guard.name} woke up" if was_asleep else None)

    def update_perception(self, player: Player, is_moving: bool, is_sprinting: bool, delta_time: float = 0.0) -> None:
        ambient = self.ambient_light
        blockers = self.sight_blockers()
        sneaking = player.is_crouching and is_moving
        if sneaking and delta_time > 0:
            self._sneak_practice(player, delta_time, blockers)
        for npc in self.npcs:
            if npc.is_fence:
                continue
            npc.sneak_hidden = npc.sneak_unnoticed_until > self.elapsed
            self._shopkeeper_watches(npc, player, blockers)
            visible = npc.can_see(player.position, blockers, NPC.chest_height(player))
            if sneaking and visible:
                self._sneak_check(npc, player, delta_time, ambient)
            npc.sneak_hidden = npc.sneak_unnoticed_until > self.elapsed
            trespassing = self.is_trespassing(player, npc) and visible and not npc.sneak_hidden
            was_alarmed = npc.is_alarmed
            npc.evaluate_perception(player, ambient, is_moving, is_sprinting, blockers, self.clock.hour,
                                    notify_callback=self.notify, delta_time=delta_time, trespassing=trespassing,
                                    noise_attenuation=self.noise_attenuation(player.position, npc.position))
            if npc.is_alarmed and not was_alarmed:
                crime = "Trespassing" if trespassing else "Skulking about"
                self.declare_crime(crime, player.position.copy(), witnessed=npc.is_guard, reporter=npc.name,
                                   witnesses=[npc] if npc.is_guard else [])
                if npc.is_guard:
                    npc.search_timer = 0.0
            self._watch_and_follow(npc, player, visible and not npc.sneak_hidden, sneaking)
            if npc.suspicion_meter >= self.settings.perception.schedule_override_threshold:
                # anyone who has taken notice remembers where (a shopkeeper tells the guards about it later)
                npc.remember_sighting(self.area_of(player.position), self.day_count)
            if npc.is_guard and visible and not npc.sneak_hidden and not npc.is_asleep:
                self._guard_sees_player(npc, player)

    def sneak_xp_rate(self, player: Player, blockers=None) -> float:
        """Sneak XP per second for crouch-moving right now (before the level factor): a trickle
        alone, more near every person who has not noticed you - sleepers and backs turned at the
        "behind" rate, right under an awake nose at the "in front" rate, guards x1.5 - and
        nothing from anyone already on to you."""
        s = self.settings.stealth
        blockers = self.sight_blockers() if blockers is None else blockers
        rate = 0.0
        for npc in self.npcs:
            dist = npc.position.distance_to(player.position)
            if dist > s.sneak_xp_range:
                continue
            if npc.suspicion_meter >= self.settings.perception.schedule_override_threshold:
                continue
            if npc.is_asleep:
                if not self.same_room(npc.position, player.position):
                    continue
                npc_rate = s.sneak_xp_behind
            else:
                if not npc.has_line_of_sight(player.position, blockers, NPC.chest_height(player)):
                    continue
                npc_rate = s.sneak_xp_in_front if npc.faces(player.position) else s.sneak_xp_behind
            if npc.is_guard:
                npc_rate *= s.sneak_xp_guard_multiplier
            rate += npc_rate
        return rate if rate > 0.0 else s.sneak_xp_alone

    def _sneak_practice(self, player: Player, delta_time: float, blockers) -> None:
        """Sneak XP while crouch-moving (``sneak_xp_rate``); rewards shrink with level like every skill."""
        progression.grant(player, SkillType.SNEAK, self.sneak_xp_rate(player, blockers) * delta_time,
                          notify=self.notify, s=self.settings.progression)

    def _shopkeeper_watches(self, npc: NPC, player: Player, blockers) -> None:
        """A shopkeeper at work keeps an eye on anyone on the premises - turning to follow
        them around the shop - unless a successful sneak roll keeps the player out of mind."""
        if not (npc.is_shopkeeper and npc.state is AIState.SHOPKEEPING) or npc.sneak_hidden:
            return
        here, there = self.area_def_at(npc.position), self.area_def_at(player.position)
        if here is None or there is None or here.owner != npc.name or there.owner != npc.name:
            return
        if (player.position.distance_to(npc.position) <= npc.view_distance
                and npc.has_line_of_sight(player.position, blockers, NPC.chest_height(player))):
            npc.turn_towards(player.position)

    def _watch_and_follow(self, npc: NPC, player: Player, visible: bool, sneaking: bool) -> None:
        """Guards turn to watch a skulking player and tail them if they keep it up."""
        if not visible:
            return
        if npc.is_guard and npc.suspicion_meter >= self.settings.perception.schedule_override_threshold:
            npc.turn_towards(player.position)
            if sneaking and npc.state in (AIState.PATROL, AIState.GUARDING, AIState.FOLLOWING):
                if npc.state is not AIState.FOLLOWING or (npc.goal is None or npc.goal.distance_to(player.position) > 1.5):
                    npc.go_to(self, player.position, AIState.FOLLOWING)
                npc.follow_timer = 0.0

    def _guard_sees_player(self, guard: NPC, player: Player) -> None:
        """A guard with something against the player settles it on sight; responding guards
        stop running once they have the player in view."""
        if guard.state is AIState.RESPONDING:
            guard.path = []
            guard.turn_towards(player.position)
        if guard.pending_confrontations:
            self._confront(guard, player)
        if guard.active_memories(self.day_count) and guard.state is not AIState.SLEEPING:
            if self.jail.sealed or self.relocating:
                return
            outcome = justice.charge_player(self, guard, player, self.notify)
            if outcome != "nothing":
                for g in self.guards():
                    if g.state in (AIState.RESPONDING, AIState.ALERT_GUARDS, AIState.FOLLOWING, AIState.INVESTIGATING):
                        g.resume_routine(self, None)

    # --- stealth checks -------------------------------------------------------------
    def _sneak_check(self, npc: NPC, player: Player, delta_time: float, ambient: float) -> None:
        """Once a second while an NPC watches the crouching player, roll Sneak: success hides the
        player from that NPC for the next second, failure makes the NPC notice."""
        s = self.settings.stealth
        npc.sneak_check_timer += delta_time
        if npc.sneak_check_timer < s.sneak_check_interval:
            return
        npc.sneak_check_timer = 0.0
        rewards = self.settings.skill_rewards
        guard_mult = s.sneak_xp_guard_multiplier if npc.is_guard else 1.0
        if roll(self.rng, sneak_chance(player, npc, s, player.get_visibility(ambient), self.settings.progression)):
            npc.sneak_unnoticed_until = self.elapsed + s.sneak_check_interval + 1e-6
            progression.grant(player, SkillType.SNEAK, rewards.sneak_success, guard_mult, notify=self.notify,
                              s=self.settings.progression)
        else:
            npc.sneak_unnoticed_until = 0.0
            npc.suspicion_meter += s.sneak_fail_suspicion
            progression.grant(player, SkillType.SNEAK, rewards.sneak_fail, guard_mult, notify=self.notify,
                              s=self.settings.progression)
            npc.scold("skulking", "skulking_citizen" if not npc.is_guard else "skulking", self.notify, player=player)

    def _confront(self, guard: NPC, player: Player) -> None:
        """A guard who saw the player lurking where goods went missing calls them out - and takes the goods back."""
        report = guard.pending_confrontations.pop(0)
        names = ", ".join(report.names.values())
        recovered = [item for item in list(player.inventory) if item.id in report.items]
        self.player_caught(guard)
        # his own sighting, or the shopkeeper's description passed on when he took the report
        seen = ("You! You were skulking around" if self.saw_someone(guard, report)
                else f"You! {dialogue.short_name(self.find_npc(report.reporter)) if self.find_npc(report.reporter) else report.reporter}"
                     f" says you were poking about")
        if recovered:
            for item in recovered:
                player.inventory.remove(item)
                item.is_stolen = False
                item.owner = None
                keeper = self.find_npc(report.reporter)
                (keeper.inventory if keeper is not None else guard.inventory).append(item)
            player.crimes_witnessed += 1
            guard.crimes_witnessed += 1
            guard.remember_crime("Theft", self.day_count, True, justice.fine_for("Theft", self.settings.justice), self.rng)
            guard.say(f"{seen} {report.area} when {names} went missing. Hand it over!", None)
            if self.notify:
                self.notify(f"({guard.name}): \"{seen} {report.area} when {names} went missing. "
                            f"Hand it over!\" The goods are returned to {report.reporter}.")
        else:
            guard.say(f"{seen} {report.area} before {names} went missing. I've got my eye on you.", self.notify)

    # --- curfews: a welcome guest is still shown the door at night ---------------------------
    def _tick_curfews(self, delta_time: float) -> None:
        if self.relocating:
            return
        player = self.player
        area = self.area_def_at(player.position)
        hour = self.clock.hour
        for npc in self.npcs:
            if npc.state is AIState.WAITING and npc.waiting_for == "curfew":
                here = self.area_def_at(npc.position)
                if area is None or area is not here or not area.curfew_active(hour):
                    npc.stop_waiting(self, None)           # the guest left (or morning came)
                    continue
                npc.curfew_ask_timer += delta_time
                if npc.curfew_ask_timer >= self.settings.justice.curfew_ask_interval:
                    npc.curfew_ask_timer = 0.0
                    npc.curfew_asks += 1
                    if npc.curfew_asks >= self.settings.justice.curfew_asks_before_eviction:
                        npc.say(npc.phrase("leave_now"), self.notify)
                        self.throw_out(player, area.name, by=npc, line="You are shown the door.")
                        npc.stop_waiting(self, None)
                    else:
                        npc.say(npc.phrase("leave_again"), self.notify)
                continue
            if area is None or not area.curfew_active(hour) or area.owner not in (npc.name, npc.faction):
                continue
            if self.area_def_at(npc.position) is not area or npc.is_asleep or npc.is_alarmed or npc.state in (
                    AIState.RESPONDING, AIState.ALERT_GUARDS, AIState.WAITING):
                continue
            npc.wait_for("curfew", player.position)
            npc.curfew_asks = 1
            npc.curfew_ask_timer = 0.0
            npc.say(npc.phrase("leave_late"), self.notify)

    # --- talk: conversations and ambient chatter ------------------------------------------
    CHAT_RANGE = 4.5              # how close two people must be to strike up a conversation (across a table)
    MAX_CONVERSATIONS = 2
    CHAT_CHECK_INTERVAL = 1.0

    def _tick_talk(self, delta_time: float) -> None:
        """Play out running conversations a line at a time and, now and then, start new ones
        between people who have stopped near each other."""
        for conv in list(self.conversations):
            self._advance_conversation(conv)
        self._chat_clock += delta_time
        if self._chat_clock < self.CHAT_CHECK_INTERVAL:
            return
        self._chat_clock = 0.0
        if len(self.conversations) >= self.MAX_CONVERSATIONS:
            return
        free = [n for n in self.npcs if n.conversation is None and n.is_sociable and n.next_chat_time <= self.elapsed]
        for i, a in enumerate(free):
            for b in free[i + 1:]:
                if a.conversation is not None or b.conversation is not None:
                    continue
                if a.position.distance_to(b.position) > self.CHAT_RANGE or not self.same_room(a.position, b.position):
                    continue
                chance = 0.35
                if a.is_guard or b.is_guard:
                    chance = 0.12                                  # the watch has less time for gossip
                if self.player is not None and self._chat_near_player() and \
                        min(a.position.distance_to(self.player.position), b.position.distance_to(self.player.position)) < 16.0:
                    continue                                       # one conversation within earshot at a time
                if not roll(self.rng, chance):
                    continue
                self.start_conversation(a, b)
                if len(self.conversations) >= self.MAX_CONVERSATIONS:
                    return

    def _chat_near_player(self) -> bool:
        for conv in self.conversations:
            if any(n.position.distance_to(self.player.position) < 16.0 for n in conv.participants):
                return True
        return False

    def start_conversation(self, a: NPC, b: NPC, exchanges: Optional[int] = None) -> dialogue.Conversation:
        conv = dialogue.build_conversation(a, b, self.clock.hour, self.rng, exchanges, recent=self.recent_topics)
        for speaker, text in conv.lines[2:-2]:
            self.recent_topics.append(text)
        del self.recent_topics[:-12]
        return self._begin_conversation(conv)

    def _begin_conversation(self, conv: dialogue.Conversation) -> dialogue.Conversation:
        """Both parties stop, turn to face each other and the lines start after a beat."""
        conv.next_line_at = self.elapsed + 0.8
        for npc, other in ((conv.a, conv.b), (conv.b, conv.a)):
            npc.conversation = conv
            npc.chat_pause = True
            npc.turn_towards(other.position)
        self.conversations.append(conv)
        return conv

    def _conversation_broken(self, conv: dialogue.Conversation) -> bool:
        if conv.official:
            return any(n.is_asleep or n.is_alarmed for n in conv.participants)
        return any(not n.is_sociable for n in conv.participants)       # somebody has better things to do

    def _advance_conversation(self, conv) -> None:
        if not conv.finished and self._conversation_broken(conv):
            conv.finished = True
        if not conv.finished and self.elapsed >= conv.next_line_at:
            if conv.index >= len(conv.lines):
                conv.finished = True
            else:
                speaker, text = conv.lines[conv.index]
                speaker.say(text, self.notify if conv.logged else None)   # gossip is a bubble only, never logged
                conv.index += 1
                conv.next_line_at = self.elapsed + 2.8 + 0.04 * len(text)
        if conv.finished:
            for npc in conv.participants:
                if npc.conversation is conv:
                    npc.conversation = None
                npc.chat_pause = False
                npc.next_chat_time = self.elapsed + self.rng.uniform(90.0, 200.0)
            if conv in self.conversations:
                self.conversations.remove(conv)
            if conv.on_finish is not None:
                callback, conv.on_finish = conv.on_finish, None
                callback()

    AMBIENT_LINES = {AIState.SHOPPING: "shopping", AIState.DRINKING: "drinking", AIState.CLEANING: "cleaning"}
    WORKING_LINES = {"smith": "working_smith", "cook": "working_kitchen", "innkeeper": "working_kitchen",
                     "porter": "working_porter"}

    def _ambient_chatter(self, npc: NPC, delta_time: float) -> None:
        """A word now and then from people going about their business: a customer haggling (and
        paying the merchant a few coins), a drinker calling for another, the smith's hammer."""
        if npc.conversation is not None or npc.is_asleep:
            return
        kind = self.AMBIENT_LINES.get(npc.state)
        if npc.state is AIState.WORKING:
            kind = self.WORKING_LINES.get(npc.role_tag)
        if kind is None:
            return
        npc.chatter_timer -= delta_time
        if npc.chatter_timer > 0.0:
            return
        npc.chatter_timer = self.rng.uniform(35.0, 80.0)
        npc.say(npc.phrase(kind))                                      # bubble only
        if npc.state is AIState.SHOPPING:
            merchant = next((m for m in self.npcs if m.can_trade and m is not npc and m.is_open_for_business
                             and m.position.distance_to(npc.position) <= 6.0), None)
            if merchant is not None and npc.gold >= 2.0:
                spent = min(npc.gold, float(self.rng.randint(2, 6)))
                npc.gold -= spent                                  # a simulated purchase: coin changes hands
                merchant.gold += spent

    # --- shopkeeping -------------------------------------------------------------------
    def on_task_arrived(self, npc: NPC, task) -> None:
        if npc.is_shopkeeper and task.target_state is AIState.SHOPKEEPING:
            self._open_shop(npc)

    def on_task_left(self, npc: NPC, previous, next_task) -> None:
        if (npc.is_shopkeeper and previous.target_state is AIState.SHOPKEEPING
                and self.area_of(next_task.target_pos) not in (self.area_of(previous.target_pos), "behind the counter", "the shop")):
            self._take_stock(npc, "closing up")

    def _open_shop(self, npc: NPC) -> None:
        self._take_stock(npc, "opening up")
        if commerce.restock_due(npc, self):
            added = commerce.restock(npc, self, self.player_level)
            if added and self.notify:
                self.notify(f"({npc.name}): \"Fresh stock in! {', '.join(i.display_name for i in added[:4])}"
                            f"{'...' if len(added) > 4 else ''}\"")

    def _take_stock(self, npc: NPC, when: str) -> None:
        report = commerce.take_stock(npc, self)
        if report is None:
            return
        self.report_theft(report, when)

    def report_theft(self, report: TheftReport, when: str = "") -> None:
        """A shopkeeper finds goods missing and shouts for the guards. Every guard within
        earshot comes running and takes the report from the shopkeeper face to face
        (``_go_and_take_report``); one who saw the player lurking there earlier - or is told
        the shopkeeper did - will confront them."""
        self.theft_reports.append(report)
        missing = self.missing_goods_text(report)
        reporter = self.find_npc(report.reporter)
        if reporter is not None:
            reporter.say(f"Thieves! {missing} missing from {report.area}! Guards!", self.notify,
                         log_prefix=f"{report.reporter}, {when}")
        elif self.notify:
            self.notify(f"({report.reporter}, {when}): \"Thieves! {missing} missing from {report.area}! Guards!\"")
        where = reporter.position if reporter is not None else None
        for guard in self.guards():
            guard.learn_theft(report)
            if where is not None and self.can_hear_cry(guard, where):
                self._send_guard(guard, where)
                if guard.state is AIState.RESPONDING:
                    guard.report_to = report
                    guard.report_timer = 0.0

    @staticmethod
    def missing_goods_text(report: TheftReport) -> str:
        return ", ".join(f"{name} x{report.items[iid]}" for iid, name in report.names.items())

    @staticmethod
    def saw_someone(npc: NPC, report: TheftReport) -> bool:
        """Did this person notice somebody skulking about the area the goods went from lately?"""
        return any(s.area == report.area and report.day - s.day <= 2 for s in npc.sightings)

    REPORT_PATIENCE = 90.0            # seconds a guard keeps trying to reach a shopkeeper to take the report

    def _go_and_take_report(self, guard: NPC, delta_time: float) -> None:
        """A responding guard makes for the shopkeeper who raised the alarm (following if they
        have moved on) and, once beside them, takes the report in a face-to-face exchange;
        both go back to what they were doing afterwards."""
        report = guard.report_to
        reporter = self.find_npc(report.reporter)
        guard.report_timer += delta_time
        if reporter is None or reporter.is_asleep or guard.report_timer > self.REPORT_PATIENCE:
            guard.resume_routine(self, self.notify)
            return
        if guard.position.distance_to(reporter.position) <= self.CHAT_RANGE and self.same_room(guard.position, reporter.position):
            guard.path = []
            self._take_report(guard, reporter, report)
        elif not guard.path or (guard.goal is not None and guard.goal.distance_to(reporter.position) > 2.0):
            guard.go_to(self, reporter.position, AIState.RESPONDING)      # the shopkeeper has moved on: follow

    def _take_report(self, guard: NPC, reporter: NPC, report: TheftReport) -> None:
        guard.report_to = None
        guard.state = AIState.GUARDING
        reporter.end_conversation()
        guard_saw, merchant_saw = self.saw_someone(guard, report), self.saw_someone(reporter, report)
        conv = dialogue.build_report_exchange(guard, reporter, self.missing_goods_text(report), report.area,
                                              guard_saw, merchant_saw, self.rng)

        def done() -> None:
            if merchant_saw and report not in guard.pending_confrontations:
                guard.pending_confrontations.append(report)        # the shopkeeper's lead is his now
            guard.resume_routine(self, self.notify)

        conv.on_finish = done
        self._begin_conversation(conv)
