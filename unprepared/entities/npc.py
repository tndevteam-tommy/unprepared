from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Sequence, Tuple

from ..config import NPCSettings, PerceptionSettings
from ..core.daynight import DayNightCycle
from ..core.math3d import BoundingBox3D, Vector3D, ray_intersects_box
from .door import Door
from .inventory import add_item, take_item
from .items import Item
from .player import Player

if TYPE_CHECKING:  # pragma: no cover
    from ..world.world import World

Notify = Optional[Callable[[str], None]]


class AIState(Enum):
    SLEEPING = 1
    PATROL = 2
    SHOPKEEPING = 3
    INVESTIGATING = 4   # walking to where a noise came from / looking around
    REPORTING = 5       # a citizen crying for the guards
    ALERT_GUARDS = 6    # a guard who has seen a crime and is after the player
    TRAVELING = 7       # walking to the location of the current schedule task
    EATING = 8
    GUARDING = 9        # standing post (guard house / tower / jail), awake and watchful
    RESPONDING = 10     # a guard running to a cry for help
    FOLLOWING = 11      # a guard tailing a skulking player
    IDLE = 12           # at a task location but unable to do it (no food...)
    WAITING = 13        # standing awake, watching the player, until they leave (a jailer after a
    #                     release, a resident who has asked a late guest to go)


ALARMED_STATES = (AIState.REPORTING, AIState.ALERT_GUARDS)
BUSY_STATES = (AIState.INVESTIGATING, AIState.REPORTING, AIState.ALERT_GUARDS, AIState.RESPONDING, AIState.FOLLOWING,
               AIState.WAITING)


@dataclass
class TheftReport:
    """A shopkeeper's report that goods went missing from an area."""
    reporter: str
    area: str
    day: int
    items: Dict[str, int]        # item id -> missing quantity
    names: Dict[str, str]        # item id -> display name


@dataclass
class Sighting:
    """A guard's memory of the player acting suspiciously somewhere."""
    area: str
    day: int


@dataclass
class CrimeMemory:
    """What a guard holds against the player. Reported (unseen) crimes fade in days,
    crimes the guard saw with their own eyes last for weeks."""
    crime: str
    day: int
    witnessed: bool
    expires_day: int
    fine: float

    def active(self, day: int) -> bool:
        return day < self.expires_day


@dataclass
class ScheduleTask:
    """One block of an NPC's daily routine.

    The NPC walks to ``target_pos`` (path-finding through doors it can open),
    then adopts ``target_state``. Door bookkeeping lets residents/shopkeepers
    open up on arrival and lock up when they leave:

    * ``unlock_doors`` - unlocked (left as they are otherwise) when the NPC arrives
    * ``open_doors``   - unlocked and opened when the NPC arrives
    * ``close_doors``  - closed (left unlocked) when the NPC arrives
    * ``lock_doors``   - locked and closed when the NPC arrives (locking up for the night)
    * ``lock_doors_on_departure`` - locked once the NPC has walked out through them

    ``patrol_points`` turns the task into a round: after arriving the NPC keeps
    walking from point to point (pausing briefly at each) until the task ends.
    ``food_container`` names a container (a table) to eat from during EATING tasks.
    """
    start_hour: int
    end_hour: int
    target_pos: Vector3D
    target_state: AIState
    action_text: str
    unlock_doors: Tuple[str, ...] = ()
    close_doors: Tuple[str, ...] = ()
    lock_doors: Tuple[str, ...] = ()
    lock_doors_on_departure: Tuple[str, ...] = ()
    depart_text: Optional[str] = None
    patrol_points: Tuple[Vector3D, ...] = ()
    open_doors: Tuple[str, ...] = ()
    facing: Optional[float] = None   # yaw to turn to on arrival (0 = -z, 90 = +x); None keeps the walking direction
    food_container: Optional[str] = None

    def covers(self, hour: int) -> bool:
        return self.start_hour <= hour < self.end_hour


@dataclass
class DoorPassage:
    """A door this NPC opened (or owns) and has to shut again once it is through."""
    door_id: str
    lock: bool               # lock it again after closing
    entry_side: int = 0      # sign of (z - hinge z) when the NPC reached the door; 0 = unknown
    passed: bool = False


PendingLock = DoorPassage   # backwards-compatible alias


class NPC:
    EYE_HEIGHT = 1.6
    TARGET_HEIGHT = 1.2      # the player's chest: low furniture (counters, tables) does not hide them
    SEARCH_SECONDS = 20.0    # how long a responding guard looks around before giving up
    FOLLOW_SECONDS = 12.0    # how long a guard keeps tailing a player who stopped skulking
    BODY_RADIUS = 0.4        # personal space: NPCs never walk into each other or the player
    CROWD_TOLERANCE = 2.0    # within this of the goal a blocked NPC is happy to stop where it stands
    BLOCKED_PATIENCE = 3.0   # seconds of being blocked before settling for "near enough"
    BLOCKED_GIVE_UP = 8.0    # seconds of being blocked anywhere before abandoning the walk

    def __init__(self, name: str, is_guard: bool, is_fence: bool, can_trade: bool, home_pos: Vector3D,
                 settings: Optional[PerceptionSettings] = None, npc_settings: Optional[NPCSettings] = None,
                 faction: Optional[str] = None):
        self.settings = settings or PerceptionSettings()
        self.npc_settings = npc_settings or NPCSettings()
        self.name = name
        self.faction = faction if faction is not None else ("guards" if is_guard else None)
        self.is_guard = is_guard
        self.is_fence = is_fence
        self.can_trade = can_trade
        self.position = home_pos
        self.home_position = home_pos.copy()
        self.state = AIState.SLEEPING
        self.suspicion_meter = 0.0
        self.has_torch = False
        self.schedule: List[ScheduleTask] = []
        self.inventory: List[Item] = []
        self.view_distance = self.settings.guard_view_distance if is_guard else self.settings.civilian_view_distance
        # routine / movement
        self.current_task: Optional[ScheduleTask] = None
        self.path: List[Vector3D] = []
        self.pending_locks: List[DoorPassage] = []
        self.patrol_index = 0
        self.patrol_wait = 0.0
        self.facing_yaw = 180.0          # direction the NPC looks (degrees; 0 = -z, 90 = +x)
        self.blocked_timer = 0.0         # seconds spent unable to step forward (someone in the way)
        self.gold = 0.0                  # coins in the purse (stolen by pickpockets, spent on purchases)
        self.base_gold = 0.0             # topped back up to this every restock cycle
        self.last_gold_restock_day = 0
        # crime bookkeeping
        self.crimes_witnessed = 0
        self.sightings: List[Sighting] = []
        self.known_thefts: List[TheftReport] = []
        self.pending_confrontations: List[TheftReport] = []
        self.crime_memories: List[CrimeMemory] = []
        # alarm / investigation
        self.goal: Optional[Vector3D] = None       # where an investigating/responding guard is heading
        self.search_timer = 0.0
        self.follow_timer = 0.0
        self.heard_noise_at: Optional[Vector3D] = None
        self.clock = 0.0                 # seconds of perception time, for cooldowns
        self.last_scold: Dict[str, float] = {}     # warning kind -> when it was last said
        self.warning_grace_until = 0.0   # suspicion cannot reach the alarm before this (time to comply)
        # asking a late guest to leave
        self.curfew_asks = 0
        self.curfew_ask_timer = 0.0
        self.waiting_for: Optional[str] = None     # why the NPC is WAITING ("release", "curfew")
        # shopkeeping / household
        self.shop_containers: List[str] = []
        self.restock_days = 3
        self.restock_tiers: list = []
        self.base_stock: list = []
        self.base_inventory: list = []
        self.inventory_reset_days = 1
        self.last_inventory_reset_day = 0
        self.expected_stock: Dict[str, int] = {}
        self.expected_names: Dict[str, str] = {}
        self.last_restock_day = 0
        self.hungry = False
        # stealth bookkeeping
        self.sneak_check_timer = 0.0
        self.sneak_unnoticed_until = 0.0
        self.sneak_hidden = False        # set by the world while a successful sneak roll is in effect

    # ------------------------------------------------------------------ identity
    @property
    def role(self) -> str:
        if self.is_guard:
            return "Guard"
        if self.is_fence:
            return "Fence"
        return "Merchant"

    @property
    def title(self) -> str:
        return self.name

    @property
    def is_alarmed(self) -> bool:
        return self.state in ALARMED_STATES

    @property
    def is_busy(self) -> bool:
        return self.state in BUSY_STATES

    @property
    def is_asleep(self) -> bool:
        return self.state is AIState.SLEEPING

    @property
    def is_patrolling(self) -> bool:
        return (self.state is AIState.PATROL and self.current_task is not None
                and bool(self.current_task.patrol_points))

    @property
    def is_open_for_business(self) -> bool:
        return self.can_trade and self.state is AIState.SHOPKEEPING

    @property
    def is_shopkeeper(self) -> bool:
        return self.can_trade and not self.is_fence

    @property
    def stock(self) -> List[Item]:
        """Items this NPC offers for sale from its own pockets (never keys or other ``for_sale=False`` items)."""
        return [item for item in self.inventory if item.for_sale]

    @property
    def forward(self) -> Tuple[float, float]:
        """Unit (x, z) vector the NPC faces."""
        rad = math.radians(self.facing_yaw)
        return math.sin(rad), -math.cos(rad)

    def faces(self, target: Vector3D) -> bool:
        """True if ``target`` lies inside the NPC's field of view (in front of it)."""
        dx, dz = target.x - self.position.x, target.z - self.position.z
        dist = math.hypot(dx, dz)
        if dist < 1e-6:
            return True
        fx, fz = self.forward
        return (fx * dx + fz * dz) / dist >= math.cos(math.radians(self.settings.view_half_angle_degrees))

    def turn_towards(self, target: Vector3D) -> None:
        dx, dz = target.x - self.position.x, target.z - self.position.z
        if dx or dz:
            self.facing_yaw = math.degrees(math.atan2(dx, -dz)) % 360.0

    def has_line_of_sight(self, target: Vector3D, walls: Sequence[BoundingBox3D]) -> bool:
        eye = Vector3D(self.position.x, self.position.y + self.EYE_HEIGHT, self.position.z)
        aim = Vector3D(target.x, target.y + self.TARGET_HEIGHT, target.z)
        return not any(ray_intersects_box(eye, aim, wall) for wall in walls)

    def can_see(self, target: Vector3D, blockers: Sequence[BoundingBox3D]) -> bool:
        """Awake, within view distance, inside the field of view and not behind a wall."""
        return (not self.is_asleep and self.position.distance_to(target) <= self.view_distance
                and self.faces(target) and self.has_line_of_sight(target, blockers))

    # ------------------------------------------------------------------ doors & keys
    def has_key_for(self, door: Door) -> bool:
        return any(item.opens(door.door_id) for item in self.inventory)

    def owns(self, door: Door) -> bool:
        return door.owned_by(self.name, self.faction)

    def can_open(self, door: Door) -> bool:
        """Anyone can open an unlocked door; a locked one needs the key - even its owner.
        A *sealed* gate (a prisoner behind the bars) is never opened by an NPC."""
        if door.sealed:
            return False
        return (not door.is_locked) or self.has_key_for(door)

    def can_lock(self, door: Door) -> bool:
        return self.has_key_for(door)

    # ------------------------------------------------------------------ memory
    def remember_sighting(self, area: str, day: int) -> None:
        if not any(s.area == area and s.day == day for s in self.sightings):
            self.sightings.append(Sighting(area, day))
            del self.sightings[:-12]

    def learn_theft(self, report: TheftReport) -> None:
        """Guards hear a shopkeeper's report; if they saw the player lurking there, they will confront them."""
        self.known_thefts.append(report)
        if any(s.area == report.area and report.day - s.day <= 2 for s in self.sightings):
            self.pending_confrontations.append(report)

    def remember_crime(self, crime: str, day: int, witnessed: bool, fine: float, rng=None) -> CrimeMemory:
        """Hold a crime against the player; unseen (reported) crimes fade in 3-5 days, witnessed in 3-5 weeks."""
        span = (rng.randint(21, 35) if rng else 28) if witnessed else (rng.randint(3, 5) if rng else 4)
        memory = CrimeMemory(crime, day, witnessed, day + span, fine)
        self.crime_memories.append(memory)
        return memory

    def active_memories(self, day: int) -> List[CrimeMemory]:
        self.crime_memories = [m for m in self.crime_memories if m.active(day)]
        return list(self.crime_memories)

    def forget_crimes(self) -> None:
        self.crime_memories.clear()
        self.pending_confrontations.clear()

    def raise_alarm(self, notify_callback: Notify, guard_line: str, citizen_line: str) -> None:
        self.path = []
        self.patrol_wait = 0.0
        if self.is_guard:
            self.state = AIState.ALERT_GUARDS
            if notify_callback:
                notify_callback(guard_line)
        else:
            self.state = AIState.REPORTING
            if notify_callback:
                notify_callback(citizen_line)

    # ------------------------------------------------------------------ daily routine
    def task_for(self, hour: int) -> Optional[ScheduleTask]:
        for task in self.schedule:
            if task.covers(hour):
                return task
        return None

    def update_schedule(self, current_hour: int, notify_callback: Notify = None, world: Optional["World"] = None,
                        doors: bool = True) -> None:
        """Switch to the task covering ``current_hour`` (unless too suspicious or busy to care).
        ``doors=False`` adopts the task without its door side effects - used when a save is
        loaded, so a door the player unlocked is not relocked by an NPC merely *resuming* its
        task. (Torches are lit by the world wherever it is dark, not by the hour.)"""
        task = self.task_for(current_hour)
        if task is None or self.suspicion_meter >= self.settings.schedule_override_threshold or self.is_busy:
            return
        if task is not self.current_task:
            self.begin_task(task, world, notify_callback, doors=doors)
        elif self.state not in (AIState.TRAVELING, task.target_state):
            # Calmed down after an alarm/investigation: resume the routine.
            self.begin_task(task, world, notify_callback, doors=doors)

    def resume_routine(self, world: "World", notify_callback: Notify = None) -> None:
        """Drop whatever interrupted the NPC and go back to the current task."""
        self.goal = None
        self.search_timer = 0.0
        self.follow_timer = 0.0
        task = self.task_for(world.clock.hour)
        self.current_task = None
        if task is not None:
            self.begin_task(task, world, notify_callback)
        else:
            self.state = AIState.IDLE

    def begin_task(self, task: ScheduleTask, world: Optional["World"] = None, notify_callback: Notify = None,
                   doors: bool = True) -> None:
        previous = self.current_task
        self.current_task = task
        if previous is not task:
            self.patrol_index = 0
        self.path = world.find_path(self, task.target_pos) if world is not None else []
        if previous is not None and previous is not task:
            for door_id in previous.lock_doors_on_departure:
                self._add_passage(door_id, lock=True)
            if world is not None:
                world.on_task_left(self, previous, task)
        if not self.path or self.position.distance_to(task.target_pos) <= self.npc_settings.arrival_tolerance:
            self.path = []
            if world is not None and self.position.distance_to(task.target_pos) > self.npc_settings.arrival_tolerance:
                # No route (a locked door we have no key for): wait where we are, grumbling.
                self.state = AIState.IDLE
                if notify_callback:
                    notify_callback(f"({self.name}): \"I can't get in... where is my key?!\"")
                return
            self.arrive(world, notify_callback, doors=doors)
        else:
            self.state = AIState.TRAVELING
            if task.depart_text and notify_callback:
                notify_callback(f"({self.name}): \"{task.depart_text}\"")

    def arrive(self, world: Optional["World"] = None, notify_callback: Notify = None, doors: bool = True) -> None:
        task = self.current_task
        if task is None:
            return
        self.state = task.target_state
        self.patrol_wait = 0.0
        if task.facing is not None:
            self.facing_yaw = task.facing
        if world is not None and doors:
            for door_id in task.unlock_doors:
                door = world.find_door(door_id)
                if door is not None and self.can_lock(door):
                    door.is_locked = False
            for door_id in task.open_doors:
                door = world.find_door(door_id)
                if door is not None and self.can_open(door):
                    door.unlock_and_open()
            for door_id in task.close_doors:
                door = world.find_door(door_id)
                if door is not None:
                    door.is_open = False
            for door_id in task.lock_doors:
                door = world.find_door(door_id)
                if door is not None and self.can_lock(door):
                    door.lock_and_close()
        if task.target_state is AIState.EATING:
            self._eat(world, notify_callback, task)
        elif notify_callback:
            notify_callback(f"({self.name}): \"{task.action_text}\"")
        if world is not None:
            world.on_task_arrived(self, task)

    def _eat(self, world: Optional["World"], notify_callback: Notify, task: ScheduleTask) -> None:
        """Meals consume one food unit from the NPC's own pockets or the table it sits at."""
        sources = []
        if world is not None and task.food_container:
            container = world.find_container(task.food_container)
            if container is not None:
                sources.append(container.inventory)     # what is on the table first, then the pockets
        sources.append(self.inventory)
        for source in sources:
            for item in source:
                if item.is_food:
                    take_item(source, item, 1)
                    if source is self.inventory and item.id in self.expected_stock:
                        self.expected_stock[item.id] = max(0, self.expected_stock[item.id] - 1)   # eating stock is not theft
                    self.hungry = False
                    if notify_callback:
                        notify_callback(f"({self.name}): \"{task.action_text}\"")
                    return
        self.hungry = True
        self.state = AIState.IDLE
        if notify_callback:
            notify_callback(f"({self.name}): \"There's nothing to eat! Has someone been at the food?\"")

    # ------------------------------------------------------------------ movement
    def go_to(self, world: "World", target: Vector3D, state: AIState) -> bool:
        """Leave the routine to walk somewhere (investigate / respond). False if unreachable."""
        path = world.find_path(self, target)
        self.goal = target.copy()
        self.path = path
        self.state = state
        self.patrol_wait = 0.0
        return bool(path)

    def update_movement(self, delta_time: float, world: "World", notify_callback: Notify = None) -> None:
        """Walk along the current path, operating doors on the way; call every frame.

        Other NPCs and the player are solid: a step into somebody is refused (a sidestep
        is tried first). Being blocked near the goal counts as arriving - a crowd of
        guards converging on one spot stands *around* it instead of inside each other -
        and being blocked anywhere for long enough abandons the walk.
        """
        start = self.position.copy()
        if self.is_patrolling and not self.path:
            self._advance_patrol(world, delta_time)
        moving_states = (AIState.TRAVELING, AIState.RESPONDING, AIState.INVESTIGATING, AIState.FOLLOWING, AIState.WAITING)
        if (self.state in moving_states or self.is_patrolling) and self.path:
            remaining = self.npc_settings.move_speed * delta_time * (1.6 if self.state is AIState.RESPONDING else 1.0)
            bodies = world.bodies_near(self) if hasattr(world, "bodies_near") else []
            # somebody already overlapping us (spawned on the same spot) must not pin us down
            bodies = [b for b in bodies if not self._crowded(self.position.x, self.position.z, [b])]
            blocked = False
            while remaining > 0 and self.path:
                target = self.path[0]
                dx, dz = target.x - self.position.x, target.z - self.position.z
                dist = (dx * dx + dz * dz) ** 0.5
                if dist > 1e-6:
                    self.facing_yaw = math.degrees(math.atan2(dx, -dz)) % 360.0
                if dist <= remaining or dist <= self.npc_settings.arrival_tolerance:
                    step_x, step_z = target.x, target.z
                    cost = dist
                else:
                    step_x = self.position.x + dx / dist * remaining
                    step_z = self.position.z + dz / dist * remaining
                    cost = remaining
                if bodies and self._crowded(step_x, step_z, bodies):
                    side = self._sidestep(dx, dz, dist, remaining, bodies)
                    if side is None:
                        blocked = True
                        break
                    self.position.x, self.position.z = side
                    remaining = 0
                    continue
                self.position.x, self.position.z = step_x, step_z
                remaining -= cost
                if cost == dist:
                    self.path.pop(0)
            if blocked:
                self.blocked_timer += delta_time
                goal = self.path[-1] if self.path else None
                near_goal = goal is not None and self.position.distance_to(goal) <= self.CROWD_TOLERANCE
                if near_goal and self.blocked_timer >= self.BLOCKED_PATIENCE:
                    self.path = []                     # near enough: stand here
                    self.blocked_timer = 0.0
                elif self.blocked_timer >= self.BLOCKED_GIVE_UP:
                    self.path = []
                    self.blocked_timer = 0.0
                    if self.state is AIState.TRAVELING:
                        self.state = AIState.IDLE      # try again on the next hour tick
                        self._touch_doors(world, start, self.position)
                        self._process_pending_locks(world)
                        return
            else:
                self.blocked_timer = 0.0
            self._touch_doors(world, start, self.position)
            if not self.path and self.state is AIState.TRAVELING:
                self.arrive(world, notify_callback)
        elif self.state is AIState.TRAVELING:
            self.arrive(world, notify_callback)
        self._process_pending_locks(world)

    def _crowded(self, x: float, z: float, bodies) -> bool:
        """Would standing at (x, z) overlap another body? ``bodies`` are (x, z, radius)."""
        for bx, bz, radius in bodies:
            if math.hypot(x - bx, z - bz) < radius + self.BODY_RADIUS:
                return True
        return False

    def _sidestep(self, dx: float, dz: float, dist: float, step: float, bodies):
        """Try stepping to either side of the blocked direction; the free spot or None."""
        if dist <= 1e-6:
            return None
        px, pz = -dz / dist, dx / dist               # perpendicular
        for sign in (1.0, -1.0):
            cx = self.position.x + (dx / dist * 0.3 + px * sign) * step
            cz = self.position.z + (dz / dist * 0.3 + pz * sign) * step
            if not self._crowded(cx, cz, bodies):
                return cx, cz
        return None

    def _advance_patrol(self, world: "World", delta_time: float) -> None:
        """Pause at the current waypoint, then plan the walk to the next one."""
        points = self.current_task.patrol_points
        self.patrol_wait += delta_time
        if self.patrol_wait < self.npc_settings.patrol_pause:
            return
        self.patrol_wait = 0.0
        self.patrol_index = (self.patrol_index + 1) % len(points)
        self.path = world.find_path(self, points[self.patrol_index])

    def _door_region(self, door: Door) -> BoundingBox3D:
        return _inflate(door.get_bounding_box(), self.npc_settings.door_operate_reach)

    def _add_passage(self, door_id: str, lock: bool) -> DoorPassage:
        for passage in self.pending_locks:
            if passage.door_id == door_id:
                passage.lock = passage.lock or lock
                return passage
        passage = DoorPassage(door_id, lock)
        self.pending_locks.append(passage)
        return passage

    def _will_pass_through(self, door: Door) -> bool:
        """True if the upcoming path crosses the door's plane inside the doorway."""
        points = [self.position, *self.path[:3]]
        return any(_crosses_door_line(door, a, b) for a, b in zip(points, points[1:]))

    def _touch_doors(self, world: "World", start: Vector3D, end: Vector3D) -> None:
        """Open a closed door the NPC is about to walk through (if it has the right to) and
        remember to shut it again. A door the NPC *owns* is always shut and locked behind
        it - even if somebody else left it open; a door it merely opened is closed again and
        relocked if it was locked. Walking past an open door changes nothing."""
        for door in world.doors:
            region = self._door_region(door)
            if not (_contains_xz(region, end) or _segment_crosses_xz(region, start, end)):
                continue
            if not self._will_pass_through(door):
                continue
            if not door.is_open:
                if not self.can_open(door):
                    continue
                was_locked = door.is_locked
                door.unlock_and_open()
                if not door.auto_closes:
                    continue                     # bars stay as they were left: open and unlocked
                passage = self._add_passage(door.door_id, lock=was_locked and self.can_lock(door))
            elif door.auto_closes and self.owns(door) and self.can_lock(door):
                passage = self._add_passage(door.door_id, lock=True)
            else:
                continue
            passage.passed = True
            if passage.entry_side == 0:
                passage.entry_side = _side_of(door, start)

    def _process_pending_locks(self, world: "World") -> None:
        """Shut (and lock) doors the NPC walked through once it is clear of them."""
        for passage in list(self.pending_locks):
            door = world.find_door(passage.door_id)
            if door is None:
                self.pending_locks.remove(passage)
                continue
            if _contains_xz(self._door_region(door), self.position):
                passage.passed = True
                continue
            if self.position.distance_to(door.center) > self.npc_settings.door_lock_clearance:
                went_through = passage.entry_side == 0 or _side_of(door, self.position) != passage.entry_side
                if went_through or not passage.passed:
                    if passage.lock and self.can_lock(door):
                        door.lock_and_close()
                    else:
                        door.is_open = False
                self.pending_locks.remove(passage)

    # ------------------------------------------------------------------ perception
    def hearing_radius_for(self, noise: float) -> float:
        return noise * self.settings.hearing_radius_per_noise

    def evaluate_perception(self, player: Player, ambient_light: float, is_moving: bool, is_sprinting: bool,
                            walls: Sequence[BoundingBox3D], simulated_hour: int, notify_callback: Notify = None,
                            delta_time: float = 1.0 / 60.0, trespassing: bool = False,
                            noise_attenuation: float = 1.0) -> None:
        """Update suspicion for one frame of ``delta_time`` seconds.

        Hearing only wakes sleepers and makes NPCs look/investigate (they cannot tell
        who is out there); only *seeing* the player misbehaving raises the suspicion
        that ends in an alarm. ``noise_attenuation`` is what the walls let through
        (1.0 when player and NPC share a room or are both outside). Fences ignore
        skulking - only a theft from them counts. Warnings are rate-limited
        (``scold``) and open a grace window before the alarm can go off.
        """
        s = self.settings
        self.clock += delta_time
        if self.is_fence or self.is_asleep and not is_moving:
            self._decay(delta_time)
            return
        is_daytime = DayNightCycle.is_daytime(simulated_hour)
        dark_and_unlit = not is_daytime and not player.has_lit_torch
        is_acting_suspicious = player.is_crouching or (dark_and_unlit and is_moving) or trespassing

        p_noise = player.get_noise_level(is_moving, is_sprinting) * max(0.0, min(1.0, noise_attenuation))
        dist = self.position.distance_to(player.position)
        if is_moving and dist <= self.hearing_radius_for(p_noise) and not self.sneak_hidden:
            if self.is_asleep:
                if p_noise > s.wake_noise_threshold:
                    self.state = AIState.INVESTIGATING
                    self.heard_noise_at = player.position.copy()
                    if notify_callback:
                        notify_callback(f"({self.name} woke up!): \"Who's there?! Making all that noise!\"")
            elif is_acting_suspicious:
                self.heard_noise_at = player.position.copy()

        if not is_acting_suspicious:
            self._decay(delta_time)
            return
        if self.is_asleep:
            return

        effective_view_dist = self.view_distance * (
            s.torch_view_multiplier if self.has_torch else max(s.min_light_view_multiplier, ambient_light))
        p_vis = player.get_visibility(ambient_light)
        if self.has_torch and dist <= s.torch_light_reach:
            p_vis = max(p_vis, s.torch_lit_visibility)      # the NPC's own torch lights up whoever is close
        seen = (dist <= effective_view_dist and self.faces(player.position) and not self.sneak_hidden
                and self.has_line_of_sight(player.position, walls) and (p_vis > s.min_visibility_to_notice or trespassing))
        if seen:
            gain = (p_vis / max(dist, 1.0)) * s.seen_suspicion_gain
            if trespassing:
                gain += s.trespass_suspicion_gain
                self.scold("trespass", f"({self.name}): \"Hey! You've no business in here. Out!\"", notify_callback,
                           player=player)
            if dark_and_unlit and self.is_guard:
                self.scold("torch", f"({self.name}): \"It's the law to carry a lit torch after dark. Light one, now!\"",
                           notify_callback, player=player)
            self.suspicion_meter += gain * delta_time
            if self.suspicion_meter >= s.schedule_override_threshold:
                self.turn_towards(player.position)
                if self.is_guard:
                    self.scold("skulking", f"({self.name}): \"You there! What are you skulking about for?\"",
                               notify_callback, player=player)
            if self.in_warning_grace:
                self.suspicion_meter = min(self.suspicion_meter, s.alarm_threshold - 1.0)
        else:
            self._decay(delta_time * 0.5)

        if self.suspicion_meter >= s.alarm_threshold and not self.is_alarmed and seen:
            self.raise_alarm(
                notify_callback,
                f"({self.title}): \"Halt right there, criminal scum!\"",
                f"({self.title}): \"Guards! Help! A criminal is committing crimes!\"",
            )

    def _decay(self, delta_time: float) -> None:
        if self.suspicion_meter > 0:
            self.suspicion_meter = max(0.0, self.suspicion_meter - self.settings.suspicion_decay * delta_time)

    def scold(self, kind: str, line: str, notify_callback: Notify, grace: bool = True,
              player: Optional[Player] = None) -> bool:
        """Say ``line`` unless the same kind of warning was given within ``scold_cooldown``.
        A warning opens a grace window: suspicion may climb but cannot trigger the alarm
        until it has passed, giving the player time to do as they are told. A guard's
        dressing-down is delivered to the player's face (``player`` turns towards them)."""
        last = self.last_scold.get(kind)
        if last is not None and self.clock - last < self.settings.scold_cooldown:
            return False
        self.last_scold[kind] = self.clock
        if grace:
            self.warning_grace_until = max(self.warning_grace_until, self.clock + self.settings.warning_grace)
        if notify_callback:
            notify_callback(line)
        if player is not None and self.is_guard:
            player.face_towards(self.position)
        return True

    @property
    def in_warning_grace(self) -> bool:
        return self.clock < self.warning_grace_until

    # ------------------------------------------------------------------ waiting on the player
    def wait_for(self, reason: str, target: Optional[Vector3D] = None) -> None:
        """Stand still, awake, watching ``target`` until the world says the wait is over."""
        self.path = []
        self.goal = None
        self.patrol_wait = 0.0
        self.state = AIState.WAITING
        self.waiting_for = reason
        if target is not None:
            self.turn_towards(target)

    def stop_waiting(self, world: "World", notify_callback: Notify = None) -> None:
        self.waiting_for = None
        self.curfew_asks = 0
        self.curfew_ask_timer = 0.0
        self.resume_routine(world, notify_callback)

    def witness_crime(self, crime_name: str, player_pos: Vector3D, walls: Sequence[BoundingBox3D],
                      notify_callback: Notify = None) -> bool:
        if self.state == AIState.SLEEPING:
            return False
        dist = self.position.distance_to(player_pos)
        if dist <= self.view_distance and self.faces(player_pos):
            blocked = (not self.has_line_of_sight(player_pos, walls)) if hasattr(walls, "__iter__") else False
            if not blocked:
                self.crimes_witnessed += 1
                self.raise_alarm(
                    notify_callback,
                    f"({self.title} witnessed {crime_name}!): \"{self.guard_callout()}\"",
                    f"({self.title} witnessed {crime_name}!): \"Thief! Guards!\"",
                )
                return True
        return False

    GUARD_CALLOUTS = (
        "Caught you red-handed!",
        "Again?! Stop right there, thief!",
        "That's enough! One more and you're coming with me!",
        "You're under arrest the moment I get my hands on you!",
    )

    def guard_callout(self) -> str:
        """Escalating line for the n-th crime this guard has seen (the last line repeats)."""
        return self.GUARD_CALLOUTS[min(self.crimes_witnessed, len(self.GUARD_CALLOUTS)) - 1]

    # ------------------------------------------------------------------ dialogue
    def greeting(self) -> str:
        if self.state is AIState.SLEEPING:
            return f"({self.name}): \"Zzz... (fast asleep)\""
        if self.is_guard:
            return f"({self.name} [Guard]): \"Keep your nose clean, traveler. Move along.\""
        if self.is_fence:
            return f"({self.name} [Fence]): \"Got stolen goods? I'll buy them off you, no questions asked.\""
        if self.can_trade and not self.is_open_for_business:
            return f"({self.name} [Merchant]): \"The shop is closed right now. Come back during opening hours.\""
        return f"({self.name} [Merchant]): \"Welcome to my shop! Take a look at my wares.\""

    def interact(self, notify_callback: Notify = None) -> None:
        if notify_callback:
            notify_callback(self.greeting())

    # ------------------------------------------------------------------ inventory upkeep
    def reset_inventory(self, day: int) -> List[Item]:
        """Replace missing personal items (keys, rations) from the base inventory. Returns what was restored."""
        restored: List[Item] = []
        have = {item.id: item for item in self.inventory}
        for item_def in self.base_inventory:
            current = have.get(item_def.id)
            if current is None:
                unit = item_def.build()
                add_item(self.inventory, unit)
                restored.append(unit)
            elif item_def.stackable and current.quantity < item_def.quantity:
                unit = item_def.build()
                unit.quantity = item_def.quantity - current.quantity
                add_item(self.inventory, unit)
                restored.append(unit)
        if self.is_fence:
            for item in self.inventory:
                item.is_stolen = False
        self.last_inventory_reset_day = day
        return restored

    # ------------------------------------------------------------------ persistence
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "position": self.position.to_dict(),
            "suspicion_meter": self.suspicion_meter,
            "state": self.state.value,
            "has_torch": self.has_torch,
            "inventory": [item.to_dict() for item in self.inventory],
            "crimes_witnessed": self.crimes_witnessed,
            "facing_yaw": self.facing_yaw,
            "gold": self.gold,
            "last_gold_restock_day": self.last_gold_restock_day,
            "expected_stock": dict(self.expected_stock),
            "expected_names": dict(self.expected_names),
            "last_restock_day": self.last_restock_day,
            "last_inventory_reset_day": self.last_inventory_reset_day,
            "sightings": [{"area": s.area, "day": s.day} for s in self.sightings],
            "known_thefts": [_report_to_dict(r) for r in self.known_thefts],
            "pending_confrontations": [_report_to_dict(r) for r in self.pending_confrontations],
            "crime_memories": [{"crime": m.crime, "day": m.day, "witnessed": m.witnessed, "expires_day": m.expires_day,
                                "fine": m.fine} for m in self.crime_memories],
        }

    def load_dict(self, data: dict) -> None:
        self.position = Vector3D.from_dict(data["position"])
        self.suspicion_meter = data.get("suspicion_meter", 0.0)
        state = data.get("state", 1)
        self.state = AIState(state) if state in {s.value for s in AIState} else AIState.SLEEPING
        if self.is_busy:
            self.state = AIState.IDLE            # interrupted activities are not resumed from a save
        self.has_torch = data.get("has_torch", self.has_torch)
        if "inventory" in data:
            self.inventory = [Item.from_dict(i) for i in data["inventory"]]
        self.crimes_witnessed = data.get("crimes_witnessed", 0)
        self.facing_yaw = data.get("facing_yaw", self.facing_yaw)
        self.gold = float(data.get("gold", self.gold))
        self.last_gold_restock_day = data.get("last_gold_restock_day", self.last_gold_restock_day)
        if "expected_stock" in data:
            self.expected_stock = dict(data["expected_stock"])
        self.expected_names = dict(data.get("expected_names", self.expected_names))
        self.last_restock_day = data.get("last_restock_day", self.last_restock_day)
        self.last_inventory_reset_day = data.get("last_inventory_reset_day", self.last_inventory_reset_day)
        self.sightings = [Sighting(s["area"], s["day"]) for s in data.get("sightings", [])]
        self.known_thefts = [_report_from_dict(r) for r in data.get("known_thefts", [])]
        self.pending_confrontations = [_report_from_dict(r) for r in data.get("pending_confrontations", [])]
        self.crime_memories = [CrimeMemory(m["crime"], m["day"], m["witnessed"], m["expires_day"], m.get("fine", 0.0))
                               for m in data.get("crime_memories", [])]
        # Routine is re-planned from the loaded position by ``World.resync_schedules``.
        self.current_task = None
        self.path = []
        self.pending_locks = []
        self.goal = None


# ---------------------------------------------------------------------- helpers
def _report_to_dict(r: TheftReport) -> dict:
    return {"reporter": r.reporter, "area": r.area, "day": r.day, "items": dict(r.items), "names": dict(r.names)}


def _report_from_dict(d: dict) -> TheftReport:
    return TheftReport(d["reporter"], d["area"], d["day"], dict(d.get("items", {})), dict(d.get("names", {})))


def _inflate(box: BoundingBox3D, amount: float) -> BoundingBox3D:
    return BoundingBox3D(Vector3D(box.min_point.x - amount, box.min_point.y, box.min_point.z - amount),
                         Vector3D(box.max_point.x + amount, box.max_point.y, box.max_point.z + amount))


def _contains_xz(box: BoundingBox3D, p: Vector3D) -> bool:
    return box.min_point.x <= p.x <= box.max_point.x and box.min_point.z <= p.z <= box.max_point.z


def _side_of(door: Door, p: Vector3D) -> int:
    return 1 if p.z >= door.hinge_position.z else -1


def _crosses_door_line(door: Door, a: Vector3D, b: Vector3D) -> bool:
    """Does segment a->b cross the doorway line (z = hinge z, x within the door width)?"""
    h = door.hinge_position
    if (a.z - h.z) * (b.z - h.z) > 0 or a.z == b.z:
        return False
    t = (h.z - a.z) / (b.z - a.z)
    x = a.x + (b.x - a.x) * t
    return h.x - 0.3 <= x <= h.x + door.width + 0.3


def _segment_crosses_xz(box: BoundingBox3D, a: Vector3D, b: Vector3D) -> bool:
    flat = BoundingBox3D(Vector3D(box.min_point.x, -1e9, box.min_point.z), Vector3D(box.max_point.x, 1e9, box.max_point.z))
    return ray_intersects_box(Vector3D(a.x, 0.0, a.z), Vector3D(b.x, 0.0, b.z), flat)
