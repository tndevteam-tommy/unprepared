from __future__ import annotations

from enum import Enum
from typing import Callable, Dict, Optional


class SkillType(Enum):
    SNEAK = "Sneak"
    LOCKPICKING = "Lockpicking"
    PICKPOCKET = "Pickpocket"
    STEALING = "Stealing"        # lifting goods from shelves, tables and chests
    BARTER = "Barter"            # buying and selling
    SMITHING = "Smithing"


class SkillTree:
    """Per-skill level and experience.

    The XP needed for the next level grows *linearly* (``BASE_XP_NEEDED`` +
    ``XP_PER_LEVEL`` per level gained) so that elite levels (50+) stay reachable;
    the slow-down at high levels comes from the rewards themselves shrinking with
    level (``systems/progression.py``), not from an exploding curve.
    """
    BASE_XP_NEEDED = 100.0
    XP_PER_LEVEL = 30.0

    def __init__(self):
        self.skills: Dict[SkillType, Dict[str, float]] = {
            skill: {"level": 1, "xp": 0.0, "xp_needed": self.xp_needed_for(1)} for skill in SkillType
        }

    @classmethod
    def xp_needed_for(cls, level: int) -> float:
        return cls.BASE_XP_NEEDED + cls.XP_PER_LEVEL * (max(1, int(level)) - 1)

    def level(self, skill: SkillType) -> int:
        return int(self.skills[skill]["level"])

    def progress(self, skill: SkillType) -> float:
        """0..1 fraction of the way to the next level."""
        data = self.skills[skill]
        return max(0.0, min(1.0, data["xp"] / data["xp_needed"])) if data["xp_needed"] > 0 else 0.0

    def add_xp(self, skill: SkillType, amount: float, notify_callback: Optional[Callable[[str], None]] = None) -> int:
        """Add XP; returns how many levels were gained (a large grant can level several times)."""
        if amount <= 0:
            return 0
        data = self.skills[skill]
        data["xp"] += amount
        gained = 0
        while data["xp"] >= data["xp_needed"]:
            data["level"] += 1
            data["xp"] -= data["xp_needed"]
            data["xp_needed"] = self.xp_needed_for(data["level"])
            gained += 1
            if notify_callback:
                notify_callback(f"SKILL UP! Your {skill.value} skill increased to Level {data['level']}!")
        return gained

    def to_dict(self) -> dict:
        return {skill.value: data for skill, data in self.skills.items()}

    def load_dict(self, data_dict: dict) -> None:
        """Load saved skills; the XP requirement is recomputed from the level so saves made
        under an older curve pick up the current one."""
        for skill in SkillType:
            if skill.value in data_dict:
                saved = dict(data_dict[skill.value])
                level = int(saved.get("level", 1))
                needed = self.xp_needed_for(level)
                self.skills[skill] = {"level": level, "xp": float(saved.get("xp", 0.0)), "xp_needed": needed}
