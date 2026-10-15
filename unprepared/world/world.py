"""Live world state built from a :class:`LevelDefinition`, plus the town-level AI:
alarms and guard responses, investigations, trespass, curfews, shopkeeping and justice.
"""
from __future__ import annotations

import dataclasses
import random
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from ..config import GameSettings, DEFAULT_SETTINGS
from ..core.daynight import DayNightCycle
from ..core.math3d import BoundingBox3D, Vector3D
from ..entities import AIState, Door, NPC, Player, SkillType, TheftReport
from ..systems import commerce, justice
from ..systems import progression
from ..systems.stealth import roll, sneak_chance
from .fixtures import generate_fixtures, is_lit_by_fixture
from .level import AreaDef, BuildingDef, Container, LevelDefinition, LightDef, Prop, Station, Wall
from .navigation import NavGrid

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
        self.stations: List[Station] = [s.build() for s in level.stations]
        self.doors: List[Door] = [d.build() for d in level.doors]
        self.npcs: List[NPC] = [n.build(settings.perception, settings.npc) for n in level.npcs]
        self.anvil_position = Vector3D(*level.anvil_position)
        self.nav = NavGrid(self.static_obstacles(), dataclasses.replace(settings.navigation, bounds=level.bounds),
                           walls=self.walls)
        self.lintels: List[Wall] = self._build_lintels()
        self.fixtures: List[LightDef] = generate_fixtures(level, self.tables())
        self.day_count = 0              # days elapsed since the game began
        self.elapsed = 0.0              # real seconds simulated
        self.player: Optional[Player] = None
        self.rng = random.Random(settings.random_seed)
        self.theft_reports: List[TheftReport] = []
        self.jail = justice.JailState.from_def(level.jail)
        # presentation hooks (set by Game): deferred relocations and "you have been caught" events
        self.relocation_handler: Optional[Callable[[Relocation], None]] = None
        self.caught_handler: Optional[Callable[[NPC], None]] = None
        self.relocations_in_flight: List[Relocation] = []
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
    def building_at(self, position: Vector3D) -> Optional[BuildingDef]:
        """The roofed building whose footprint contains ``position`` (None outdoors)."""
        for building in self.level.buildings:
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
        """Dark enough for a torch: night-time outdoors, or indoors out of reach of every fixture."""
        if self.is_indoors(position):
            return not is_lit_by_fixture(self.fixtures, position)
        return DayNightCycle.is_torch_time(self.clock.hour)

    def noise_attenuation(self, source: Vector3D, listener: Vector3D) -> float:
        """How much of a noise made at ``source`` reaches ``listener``: everything within the
        same room or open air, a fraction (``wall_noise_attenuation``) through walls."""
        return 1.0 if self.same_room(source, listener) else self.settings.perception.wall_noise_attenuation

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
        """Everything solid that never moves: walls, props, containers and stations."""
        return [*self.walls, *self.props, *self.containers, *self.stations]

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

    def body_circles(self, exclude: Optional[NPC] = None) -> List[Tuple[float, float, float]]:
        """(x, z, radius) of every awake NPC (and the player) somebody could bump into."""
        bodies = []
        for npc in self.npcs:
            if npc is exclude or npc.is_asleep:
                continue
            bodies.append((npc.position.x, npc.position.z, NPC.BODY_RADIUS))
        if self.player is not None:
            bodies.append((self.player.position.x, self.player.position.z, self.settings.player.collision_radius))
        return bodies

    def bodies_near(self, npc: NPC, radius: float = 6.0) -> List[Tuple[float, float, float]]:
        p = npc.position
        return [b for b in self.body_circles(exclude=npc) if (b[0] - p.x) ** 2 + (b[1] - p.z) ** 2 <= radius * radius]

    def npc_colliders(self) -> List[BoundingBox3D]:
        """Upright NPC bodies as boxes the player cannot walk through (sleepers are on beds, which already block)."""
        return [BoundingBox3D.around(n.position, NPC.BODY_RADIUS, NPC_HEIGHT, NPC.BODY_RADIUS)
                for n in self.npcs if not n.is_asleep]

    def colliders(self, include_npcs: bool = True) -> List[BoundingBox3D]:
        """Everything the player collides with right now (static geometry, door leaves, people)."""
        boxes = [*self.static_obstacles(), *(door.collider() for door in self.doors)]
        if include_npcs:
            boxes.extend(self.npc_colliders())
        return boxes

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
        """Geometry that blocks line of sight: static obstacles plus closed door leaves (bars are see-through)."""
        return [*self.static_obstacles(), *(door.collider() for door in self.doors if door.blocks_sight)]

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
        return self.nav.find_path(npc.position, goal, self.doors, npc.can_open)

    # --- trust ----------------------------------------------------------------------
    def area_trusts_player(self, area: AreaDef) -> bool:
        """Is the player a welcome guest here (outside curfew hours)? Explicitly via
        ``trusted_by``, or - the standing rule - because a fence owns the place: a fence's
        house is always open to the player by day, and nobody, guards included, objects."""
        if area.curfew_active(self.clock.hour):
            return False
        if area.trusted_by:
            return True
        owner = self.find_npc(area.owner) if area.owner else None
        return owner is not None and owner.is_fence

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
            self.player.face_towards(by.position)
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
            if following is not None and self.area_of(task.target_pos) != self.area_of(following.target_pos):
                for door in self.doors:               # leaving the building: its owner locks up behind itself
                    if door.auto_closes and npc.owns(door) and npc.can_lock(door):
                        door.lock_and_close()

    def update_time(self, delta_time: float) -> bool:
        """Advance the clock; on a new hour apply door schedules and NPC schedules."""
        self.elapsed += delta_time
        if not self.clock.advance(delta_time):
            return False
        hour = self.clock.hour
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

    def wait_hours(self, hours: int, step: float = 0.5) -> None:
        """Pass time quickly (the player stands still); NPCs keep living their routines."""
        for _ in range(int(hours * (self.clock.minutes_per_hour / self.clock.time_scale) / step)):
            self.update_time(step)
            self.update_npcs(step)

    def update_npcs(self, delta_time: float) -> None:
        for npc in self.npcs:
            npc.update_movement(delta_time, self, self.notify)
            self._tick_ai(npc, delta_time)
            npc.has_torch = not npc.is_asleep and self.is_dark_at(npc.position)     # lit wherever it is dark
        if self.player is not None:
            self.push_out_of_doors(self.player)
            self._tick_jail()
            self._tick_curfews(delta_time)

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
        if npc.state is AIState.INVESTIGATING:
            if npc.heard_noise_at is not None and npc.goal is None and npc.is_guard:
                self._investigate(npc, npc.heard_noise_at)
                npc.heard_noise_at = None
            if not npc.path:
                npc.search_timer += delta_time
                if npc.goal is not None and npc.search_timer > 3.0:
                    npc.turn_towards(Vector3D(npc.position.x + 1, 0, npc.position.z))
                if npc.search_timer >= npc.SEARCH_SECONDS * 0.5:
                    npc.resume_routine(self, self.notify)
        elif npc.state is AIState.RESPONDING:
            if not npc.path:
                npc.search_timer += delta_time
                if npc.search_timer >= npc.SEARCH_SECONDS:
                    if self.notify and npc.search_timer - delta_time < npc.SEARCH_SECONDS:
                        self.notify(f"({npc.name}): \"Gone... but I'll know that face when I see it.\"")
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
                npc.scold("cell_noise", f"({npc.name}): \"Keep it down in there!\"", self.notify, grace=False)
            else:
                self._investigate(npc, where)
                if self.notify:
                    self.notify(f"({npc.name}): \"What was that? I'd better take a look.\"")
        else:
            npc.heard_noise_at = None

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
        """A shout for the guards carries ``shout_radius`` in the open, less through walls."""
        s = self.settings.perception
        reach = s.shout_radius * (1.0 if self.same_room(location, npc.position) else s.shout_wall_attenuation)
        return npc.position.distance_to(location) <= reach

    def _send_guard(self, guard: NPC, location: Vector3D) -> None:
        if guard.state is AIState.RESPONDING or self.jail.sealed and guard.name == self.jail.jailer:
            return
        was_asleep = guard.is_asleep
        guard.state = AIState.GUARDING
        guard.search_timer = 0.0
        guard.go_to(self, location, AIState.RESPONDING)
        if self.notify:
            self.notify(f"({guard.name}{' woke up' if was_asleep else ''}): \"A cry for help! On my way!\"")

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
            visible = npc.can_see(player.position, blockers)
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
            if npc.is_guard and npc.suspicion_meter >= self.settings.perception.schedule_override_threshold:
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
                if not npc.has_line_of_sight(player.position, blockers):
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
                and npc.has_line_of_sight(player.position, blockers)):
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
            npc.scold("skulking", f"({npc.name}): \"Hey! What are you skulking about for?\"", self.notify, player=player)

    def _confront(self, guard: NPC, player: Player) -> None:
        """A guard who saw the player lurking where goods went missing calls them out - and takes the goods back."""
        report = guard.pending_confrontations.pop(0)
        names = ", ".join(report.names.values())
        recovered = [item for item in list(player.inventory) if item.id in report.items]
        self.player_caught(guard)
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
            if self.notify:
                self.notify(f"({guard.name}): \"You! You were skulking around {report.area} when {names} went missing. "
                            f"Hand it over!\" The goods are returned to {report.reporter}.")
        elif self.notify:
            self.notify(f"({guard.name}): \"I saw you around {report.area} before {names} went missing. "
                        f"I've got my eye on you.\"")

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
                        self.throw_out(player, area.name, by=npc,
                                       line=f"({npc.name}): \"Right, that's it. Out!\" You are shown the door.")
                        npc.stop_waiting(self, None)
                    elif self.notify:
                        self.notify(f"({npc.name}): \"I said it's late. Off with you, I'm not asking again.\"")
                continue
            if area is None or not area.curfew_active(hour) or area.owner not in (npc.name, npc.faction):
                continue
            if self.area_def_at(npc.position) is not area or npc.is_asleep or npc.is_alarmed or npc.state in (
                    AIState.RESPONDING, AIState.ALERT_GUARDS, AIState.WAITING):
                continue
            npc.wait_for("curfew", player.position)
            npc.curfew_asks = 1
            npc.curfew_ask_timer = 0.0
            if self.notify:
                self.notify(f"({npc.name}): \"It's late. Time for you to go - I want to turn in.\"")

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
        earshot comes to take the report; a guard who saw the player lurking there earlier
        notes it and will confront them."""
        self.theft_reports.append(report)
        missing = ", ".join(f"{name} x{report.items[iid]}" for iid, name in report.names.items())
        if self.notify:
            self.notify(f"({report.reporter}, {when}): \"Thieves! {missing} missing from {report.area}! Guards!\"")
        reporter = self.find_npc(report.reporter)
        where = reporter.position if reporter is not None else None
        for guard in self.guards():
            guard.learn_theft(report)
            if where is not None and self.can_hear_cry(guard, where):
                self._send_guard(guard, where)
                if self.notify:
                    seen = any(s.area == report.area and report.day - s.day <= 2 for s in guard.sightings)
                    if seen:
                        self.notify(f"({guard.name}): \"Missing goods in {report.area}? I saw someone skulking "
                                    f"about there. I'll have a word with them.\"")
                    else:
                        self.notify(f"({guard.name}): \"I'll take the report. Did you see anyone suspicious?\"")
