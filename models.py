import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional

class AIState(Enum):
    SLEEPING = 1
    PATROL = 2
    SHOPKEEPING = 3
    INVESTIGATING = 4
    REPORTING = 5
    ALERT_GUARDS = 6

class SkillType(Enum):
    SNEAK = "Sneak"
    LOCKPICKING = "Lockpicking"
    PICKPOCKET = "Pickpocket"
    SMITHING = "Smithing"

@dataclass
class Vector3D:
    x: float
    y: float
    z: float

    def distance_to(self, other: 'Vector3D') -> float:
        return math.sqrt((self.x - other.x)**2 + (self.y - other.y)**2 + (self.z - other.z)**2)

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "z": self.z}

    @staticmethod
    def from_dict(d: dict) -> 'Vector3D':
        return Vector3D(d["x"], d["y"], d["z"])

@dataclass
class BoundingBox3D:
    min_point: Vector3D
    max_point: Vector3D

    def intersects(self, other: 'BoundingBox3D') -> bool:
        return (
            self.min_point.x <= other.max_point.x and self.max_point.x >= other.min_point.x and
            self.min_point.y <= other.max_point.y and self.max_point.y >= other.min_point.y and
            self.min_point.z <= other.max_point.z and self.max_point.z >= other.min_point.z
        )

def ray_intersects_box(ray_origin: Vector3D, ray_target: Vector3D, box: BoundingBox3D) -> bool:
    dir_x = ray_target.x - ray_origin.x
    dir_y = ray_target.y - ray_origin.y
    dir_z = ray_target.z - ray_origin.z
    tmin, tmax = 0.0, 1.0

    for origin, d, bmin, bmax in [
        (ray_origin.x, dir_x, box.min_point.x, box.max_point.x),
        (ray_origin.y, dir_y, box.min_point.y, box.max_point.y),
        (ray_origin.z, dir_z, box.min_point.z, box.max_point.z)
    ]:
        if abs(d) < 1e-6:
            if origin < bmin or origin > bmax:
                return False
        else:
            ood = 1.0 / d
            t1 = (bmin - origin) * ood
            t2 = (bmax - origin) * ood
            if t1 > t2: t1, t2 = t2, t1
            if t1 > tmin: tmin = t1
            if t2 < tmax: tmax = t2
            if tmin > tmax:
                return False
    return tmax >= tmin and tmin <= 1.0 and tmax >= 0.0

@dataclass
class Item:
    id: str
    name: str
    value: float = 50.0
    is_stolen: bool = False
    noise_modifier: float = 0.0
    is_key: bool = False
    key_door_id: Optional[str] = None
    is_lockpick: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "value": self.value,
            "is_stolen": self.is_stolen, "noise_modifier": self.noise_modifier,
            "is_key": self.is_key, "key_door_id": self.key_door_id, "is_lockpick": self.is_lockpick
        }

    @staticmethod
    def from_dict(d: dict) -> 'Item':
        return Item(
            id=d["id"], name=d["name"], value=d.get("value", 50.0),
            is_stolen=d.get("is_stolen", False), noise_modifier=d.get("noise_modifier", 0.0),
            is_key=d.get("is_key", False), key_door_id=d.get("key_door_id"),
            is_lockpick=d.get("is_lockpick", False)
        )

@dataclass
class Door:
    door_id: str
    hinge_position: Vector3D
    width: float = 3.0
    height: float = 3.5
    thickness: float = 0.2
    is_locked: bool = True
    is_open: bool = False
    key_id: str = "shop_key"
    angle: float = 0.0

    def get_bounding_box(self) -> BoundingBox3D:
        return BoundingBox3D(
            Vector3D(self.hinge_position.x, self.hinge_position.y, self.hinge_position.z - 0.5),
            Vector3D(self.hinge_position.x + self.width, self.hinge_position.y + self.height, self.hinge_position.z + 0.5)
        )

class SkillTree:
    def __init__(self):
        self.skills: Dict[SkillType, Dict[str, float]] = {
            skill: {"level": 1, "xp": 0.0, "xp_needed": 100.0} for skill in SkillType
        }

    def add_xp(self, skill: SkillType, amount: float, notify_callback=None):
        data = self.skills[skill]
        data["xp"] += amount
        if data["xp"] >= data["xp_needed"]:
            data["level"] += 1
            data["xp"] -= data["xp_needed"]
            data["xp_needed"] *= 1.25
            msg = f"SKILL UP! Your {skill.value} skill increased to Level {data['level']}!"
            if notify_callback:
                notify_callback(msg)

    def to_dict(self) -> dict:
        return {skill.value: data for skill, data in self.skills.items()}

    def load_dict(self, data_dict: dict):
        for skill in SkillType:
            if skill.value in data_dict:
                self.skills[skill] = data_dict[skill.value]

@dataclass
class ScheduleTask:
    start_hour: int
    end_hour: int
    target_pos: Vector3D
    target_state: AIState
    action_text: str

class Player:
    def __init__(self, start_pos: Vector3D):
        self.position = start_pos
        self.rotation_y = 0.0
        self.rotation_x = 0.0
        self.is_crouching = False
        self.has_lit_torch = False
        self.gold = 50.0
        self.inventory: List[Item] = [
            Item("lockpick_1", "Iron Lockpick", value=5.0, noise_modifier=0.0, is_lockpick=True),
            Item("soft_shoes", "Soft Leather Boots", value=30.0, noise_modifier=-0.05),
            Item("stolen_goblet", "Stolen Silver Goblet", value=120.0, is_stolen=True)
        ]
        self.skills = SkillTree()

    def get_noise_level(self, is_moving: bool, is_sprinting: bool) -> float:
        if not is_moving:
            return 0.0
        base_speed = 3.0 if is_sprinting else 1.5
        crouch_mod = 0.3 if self.is_crouching else 1.0
        clothing_noise = sum(item.noise_modifier for item in self.inventory)
        return max(0.1, base_speed * crouch_mod * (1.0 + clothing_noise))

    def get_visibility(self, ambient_light: float) -> float:
        torch_light = 0.9 if self.has_lit_torch else 0.0
        stance_mod = 0.4 if self.is_crouching else 1.0
        return (ambient_light + torch_light) * stance_mod

    def to_dict(self) -> dict:
        return {
            "position": self.position.to_dict(),
            "gold": self.gold,
            "has_lit_torch": self.has_lit_torch,
            "is_crouching": self.is_crouching,
            "inventory": [item.to_dict() for item in self.inventory],
            "skills": self.skills.to_dict()
        }

    def load_dict(self, data: dict):
        self.position = Vector3D.from_dict(data["position"])
        self.gold = data.get("gold", 25.0)
        self.has_lit_torch = data.get("has_lit_torch", False)
        self.is_crouching = data.get("is_crouching", False)
        self.inventory = [Item.from_dict(i) for i in data.get("inventory", [])]
        if "skills" in data:
            self.skills.load_dict(data["skills"])

class NPC:
    def __init__(self, name: str, is_guard: bool, is_fence: bool, can_trade: bool, home_pos: Vector3D):
        self.name = name
        self.is_guard = is_guard
        self.is_fence = is_fence
        self.can_trade = can_trade
        self.position = home_pos
        self.home_position = home_pos
        self.state = AIState.SLEEPING
        self.suspicion_meter = 0.0
        self.has_torch = False
        self.schedule: List[ScheduleTask] = []
        self.inventory: List[Item] = []
        self.view_distance = 14.0 if is_guard else 8.0

    def update_schedule(self, current_hour: int, notify_callback=None):
        self.has_torch = (current_hour >= 20 or current_hour < 6)

        for task in self.schedule:
            if task.start_hour <= current_hour < task.end_hour:
                if self.state != task.target_state and self.suspicion_meter < 50.0:
                    self.state = task.target_state
                    if notify_callback:
                        notify_callback(f"({self.name}): \"{task.action_text}\"")

    def evaluate_perception(self, player: Player, ambient_light: float, is_moving: bool, is_sprinting: bool, walls: List[BoundingBox3D], simulated_hour: int, notify_callback=None):
        is_daytime = 6 <= simulated_hour < 20
        is_acting_suspicious = player.is_crouching or (not is_daytime and not player.has_lit_torch and is_moving)

        if not is_acting_suspicious:
            if self.suspicion_meter > 0:
                self.suspicion_meter = max(0.0, self.suspicion_meter - 5.0)
            return

        effective_view_dist = self.view_distance * (1.5 if self.has_torch else max(0.4, ambient_light))
        
        p_noise = player.get_noise_level(is_moving, is_sprinting)
        p_vis = player.get_visibility(ambient_light)
        dist = self.position.distance_to(player.position)

        hearing_radius = p_noise * 10.0
        if dist <= hearing_radius:
            if self.state == AIState.SLEEPING:
                if p_noise > 0.8:
                    self.state = AIState.INVESTIGATING
                    if notify_callback:
                        notify_callback(f"({self.name} woke up!): \"Who's there?! Making all that noise!\"")
            else:
                self.suspicion_meter += 10.0

        if dist <= effective_view_dist and self.state != AIState.SLEEPING:
            line_of_sight_blocked = any(ray_intersects_box(self.position, player.position, wall) for wall in walls)
            if not line_of_sight_blocked and p_vis > 0.15:
                self.suspicion_meter += (p_vis / max(dist, 1.0)) * 20.0

        if self.suspicion_meter >= 100.0 and self.state not in (AIState.REPORTING, AIState.ALERT_GUARDS):
            if self.is_guard:
                self.state = AIState.ALERT_GUARDS
                if notify_callback:
                    notify_callback(f"(Guard {self.name}): \"Halt right there, criminal scum! Pay with your blood!\"")
            else:
                self.state = AIState.REPORTING
                if notify_callback:
                    notify_callback(f"(Citizen {self.name}): \"Guards! Help! A criminal is committing crimes!\"")

    def witness_crime(self, crime_name: str, player_pos: Vector3D, walls: List[BoundingBox3D], notify_callback=None) -> bool:
        if self.state == AIState.SLEEPING:
            return False
        dist = self.position.distance_to(player_pos)
        if dist <= self.view_distance:
            blocked = any(ray_intersects_box(self.position, player_pos, wall) for wall in walls) if hasattr(walls, '__iter__') else False
            if not blocked:
                if self.is_guard:
                    self.state = AIState.ALERT_GUARDS
                    if notify_callback:
                        notify_callback(f"(Guard {self.name} witnessed {crime_name}!): \"Caught you red-handed!\"")
                else:
                    self.state = AIState.REPORTING
                    if notify_callback:
                        notify_callback(f"(Citizen {self.name} witnessed {crime_name}!): \"Thief! Guards!\"")
                return True
        return False

    def interact(self, notify_callback=None):
        if notify_callback:
            if self.is_guard:
                notify_callback(f"({self.name} [Guard]): \"Keep your nose clean, traveler. Move along.\"")
            elif self.is_fence:
                notify_callback(f"({self.name} [Fence]): \"Got stolen goods? I'll buy them off you, no questions asked.\"")
            else:
                notify_callback(f"({self.name} [Merchant]): \"Welcome to my shop! Take a look at my wares.\"")

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "position": self.position.to_dict(),
            "suspicion_meter": self.suspicion_meter,
            "state": self.state.value
        }

    def load_dict(self, data: dict):
        self.position = Vector3D.from_dict(data["position"])
        self.suspicion_meter = data.get("suspicion_meter", 0.0)
        self.state = AIState(data.get("state", 1))