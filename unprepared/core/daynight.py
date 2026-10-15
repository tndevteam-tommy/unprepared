"""Time-of-day rules shared by lighting, perception and NPC schedules.

Night is 20:00-06:00 for every rule (ambient light, NPC torches, suspicion of
sneaking in the dark); the sky additionally has a dusk phase 18:00-20:00 and
05:00-06:00.
"""
from __future__ import annotations

import math
from enum import Enum
from typing import Tuple


class DayPhase(Enum):
    DAY = "day"
    DUSK = "dusk"
    NIGHT = "night"


class DayNightCycle:
    def __init__(self, ambient_day: float = 1.0, ambient_night: float = 0.1):
        self.ambient_day = ambient_day
        self.ambient_night = ambient_night

    def ambient_light(self, hour: int) -> float:
        return self.ambient_night if self.is_night(hour) else self.ambient_day

    @staticmethod
    def is_night(hour: int) -> bool:
        return hour >= 20 or hour < 6

    @classmethod
    def is_daytime(cls, hour: int) -> bool:
        """Used by NPC perception to decide whether sneaking in the dark is suspicious."""
        return not cls.is_night(hour)

    @classmethod
    def is_torch_time(cls, hour: int) -> bool:
        """Hours during which NPCs carry lit torches."""
        return cls.is_night(hour)

    @staticmethod
    def phase(hour: int) -> DayPhase:
        if 6 <= hour < 18:
            return DayPhase.DAY
        if 18 <= hour < 20 or 5 <= hour < 6:
            return DayPhase.DUSK
        return DayPhase.NIGHT

    @staticmethod
    def sun_position(hour: float, orbit_radius: float = 50.0, z: float = 20.0) -> Tuple[float, float, float]:
        angle = (hour / 24.0) * 2.0 * math.pi
        return math.cos(angle) * orbit_radius, math.sin(angle) * orbit_radius, z
