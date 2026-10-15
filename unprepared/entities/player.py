from __future__ import annotations

import math
from typing import Iterable, List, Optional

from ..config import PlayerSettings
from ..core.math3d import BoundingBox3D, Vector3D
from .inventory import add_item, take_item
from .items import Item
from .skills import SkillTree


class Player:
    def __init__(self, start_pos: Vector3D, gold: float = 50.0, inventory: Optional[Iterable[Item]] = None,
                 settings: Optional[PlayerSettings] = None):
        self.settings = settings or PlayerSettings()
        self.position = start_pos
        self.rotation_y = 0.0   # yaw, degrees
        self.rotation_x = 0.0   # pitch, degrees
        self.is_crouching = False
        self.has_lit_torch = False
        self.gold = gold
        self.inventory: List[Item] = list(inventory) if inventory is not None else []
        self.skills = SkillTree()
        self.current_eye_height = self.settings.eye_height   # animates between standing/crouching
        self.crimes_witnessed = 0                            # times an NPC caught the player in the act

    # --- queries -----------------------------------------------------------
    @property
    def level(self) -> int:
        """Overall character level: every two skill levels gained is one character level."""
        gained = sum(self.skills.level(skill) - 1 for skill in self.skills.skills)
        return 1 + gained // 2

    @property
    def target_eye_height(self) -> float:
        return self.settings.crouch_eye_height if self.is_crouching else self.settings.eye_height

    @property
    def eye_position(self) -> Vector3D:
        return Vector3D(self.position.x, self.position.y + self.current_eye_height, self.position.z)

    def update_stance(self, delta_time: float) -> float:
        """Move the camera height towards the stance's eye height; returns the new height."""
        target = self.target_eye_height
        step = self.settings.stance_transition_speed * delta_time
        if self.current_eye_height < target:
            self.current_eye_height = min(target, self.current_eye_height + step)
        elif self.current_eye_height > target:
            self.current_eye_height = max(target, self.current_eye_height - step)
        return self.current_eye_height

    def has_key_for(self, door_id: str) -> bool:
        return any(item.opens(door_id) for item in self.inventory)

    def has_lockpick(self) -> bool:
        return any(item.is_lockpick for item in self.inventory)

    def take_lockpick(self) -> Optional[Item]:
        """Remove and return one lockpick from the inventory (None if there is none)."""
        for item in self.inventory:
            if item.is_lockpick:
                return take_item(self.inventory, item, 1)
        return None

    def add_item(self, item: Item) -> Item:
        return add_item(self.inventory, item)

    def collision_box(self, position: Optional[Vector3D] = None) -> BoundingBox3D:
        p = position or self.position
        s = self.settings
        return BoundingBox3D(
            Vector3D(p.x - s.collision_radius, p.y - s.collision_foot_depth, p.z - s.collision_radius),
            Vector3D(p.x + s.collision_radius, p.y + s.collision_head_height, p.z + s.collision_radius),
        )

    noise_skill_multiplier = 1.0      # set by the game from the Sneak skill (quieter with practice)

    def get_noise_level(self, is_moving: bool, is_sprinting: bool) -> float:
        if not is_moving:
            return 0.0
        s = self.settings
        base_speed = s.noise_sprint if is_sprinting else s.noise_walk
        crouch_mod = s.noise_crouch_multiplier if self.is_crouching else 1.0
        clothing_noise = sum(item.noise_modifier for item in self.inventory)
        return max(s.noise_floor, base_speed * crouch_mod * (1.0 + clothing_noise) * self.noise_skill_multiplier)

    def get_visibility(self, ambient_light: float) -> float:
        s = self.settings
        torch_light = s.visibility_torch_bonus if self.has_lit_torch else 0.0
        stance_mod = s.visibility_crouch_multiplier if self.is_crouching else 1.0
        return (ambient_light + torch_light) * stance_mod

    # --- mutations ----------------------------------------------------------
    def face_towards(self, target: Vector3D) -> None:
        """Snap the view to look at ``target`` (level pitch) - used when an NPC confronts the player."""
        dx, dz = target.x - self.position.x, target.z - self.position.z
        if dx or dz:
            self.rotation_y = math.degrees(math.atan2(dx, -dz)) % 360.0
        self.rotation_x = 0.0

    def look(self, dx_pixels: float, dy_pixels: float) -> None:
        s = self.settings
        self.rotation_y += dx_pixels * s.mouse_sensitivity
        self.rotation_x -= dy_pixels * s.mouse_sensitivity
        self.rotation_x = max(-s.max_pitch, min(s.max_pitch, self.rotation_x))

    # --- persistence ---------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "position": self.position.to_dict(),
            "rotation_y": self.rotation_y,
            "rotation_x": self.rotation_x,
            "gold": self.gold,
            "has_lit_torch": self.has_lit_torch,
            "is_crouching": self.is_crouching,
            "inventory": [item.to_dict() for item in self.inventory],
            "skills": self.skills.to_dict(),
            "crimes_witnessed": self.crimes_witnessed,
        }

    def load_dict(self, data: dict) -> None:
        self.position = Vector3D.from_dict(data["position"])
        self.rotation_y = data.get("rotation_y", self.rotation_y)
        self.rotation_x = data.get("rotation_x", self.rotation_x)
        self.gold = data.get("gold", self.gold)
        self.has_lit_torch = data.get("has_lit_torch", False)
        self.is_crouching = data.get("is_crouching", False)
        self.inventory = [Item.from_dict(i) for i in data.get("inventory", [])]
        if "skills" in data:
            self.skills.load_dict(data["skills"])
        self.crimes_witnessed = data.get("crimes_witnessed", 0)
        self.current_eye_height = self.target_eye_height
