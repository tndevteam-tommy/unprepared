"""Time-of-day rules shared by lighting, perception and NPC schedules.

The sun rises at 06:00 and sets at 18:00 (``sun_direction``); night is
20:00-06:00 for the *rules* (ambient light, suspicion of sneaking in the dark,
the torch law), with a dusk phase 18:00-20:00 and 05:00-06:00. NPCs light their
torches by the actual light rather than the clock: whenever the sun is low
enough (``is_torch_time``, from about 17:30 to 06:30), which is when the street
gets too dark to see by.
"""
from __future__ import annotations

import math
from enum import Enum
from typing import Tuple

SUNRISE, SUNSET = 6.0, 18.0
TORCH_SUN_ELEVATION = 0.13      # sin(elevation) below which NPCs want a torch outdoors (sun less than ~7.5 deg up)


def sun_angle(hour: float) -> float:
    """0 at sunrise, pi at sunset, 2*pi at the next sunrise."""
    hour %= 24.0
    if SUNRISE <= hour < SUNSET:
        return (hour - SUNRISE) / (SUNSET - SUNRISE) * math.pi
    since_set = (hour - SUNSET) % 24.0
    return math.pi + since_set / (24.0 - (SUNSET - SUNRISE)) * math.pi


def sun_direction(hour: float) -> Tuple[float, float, float]:
    """Unit vector towards the sun: rises in the east (+x), peaks at midday, sets in the west."""
    angle = sun_angle(hour)
    v = (math.cos(angle), math.sin(angle), 0.25)
    m = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (v[0] / m, v[1] / m, v[2] / m)


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

    @staticmethod
    def is_torch_time(hour: float) -> bool:
        """Too dark outdoors to do without a torch: the sun is down or nearly so (a fractional
        hour gives the exact moment; the integer hour the rule at the top of that hour)."""
        return sun_direction(hour)[1] < TORCH_SUN_ELEVATION

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
