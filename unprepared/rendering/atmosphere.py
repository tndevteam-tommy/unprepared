"""Time-of-day atmosphere: sun/moon directions, sky and fog colours, light intensities.

Everything is a smooth function of the fractional hour so the sun and moon
glide across the sky and the light changes gradually rather than in steps.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

from ..config import LightingSettings

Vec3 = Tuple[float, float, float]


def _lerp(a: Vec3, b: Vec3, t: float) -> Vec3:
    t = max(0.0, min(1.0, t))
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def _normalize(v: Vec3) -> Vec3:
    m = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / m, v[1] / m, v[2] / m)


def sun_direction(hour: float) -> Vec3:
    """Unit vector towards the sun: rises in the east (+x) at 06:00, peaks at noon, sets west at 18:00."""
    angle = (hour - 6.0) / 12.0 * math.pi
    return _normalize((math.cos(angle), math.sin(angle), 0.25))


def moon_direction(hour: float) -> Vec3:
    return sun_direction((hour + 12.0) % 24.0)


@dataclass(frozen=True)
class Atmosphere:
    sun_dir: Vec3
    sun_color: Vec3
    moon_dir: Vec3
    moon_color: Vec3
    ambient: Vec3
    sky_color: Vec3
    fog_color: Vec3
    fog_density: float
    sun_elevation: float      # sin of the sun's elevation: +1 noon, -1 midnight
    daylight: float           # 0..1 how much of the sun's light reaches the ground
    star_alpha: float = 0.0   # 0..1 how visible the stars are


def compute_atmosphere(hour: float, s: LightingSettings) -> Atmosphere:
    sun = sun_direction(hour)
    moon = moon_direction(hour)
    elevation = sun[1]
    daylight = max(0.0, min(1.0, (elevation + 0.18) / 0.45))        # dawn/dusk ramp starts before sunrise
    twilight = max(0.0, 1.0 - abs(elevation) / 0.3)                  # 1 at the horizon, 0 away from it
    night = max(0.0, min(1.0, (-elevation - 0.05) / 0.3))

    sky = _lerp(s.sky_night, s.sky_day, daylight)
    sky = _lerp(sky, s.sky_dusk, twilight * 0.8)
    fog_color = _lerp(sky, s.fog_tint, 0.25 * daylight)      # by night the fog is the sky's own dark blue
    fog_density = s.fog_density_day + (s.fog_density_night - s.fog_density_day) * night

    sun_color = tuple(c * max(0.0, min(1.0, (elevation + 0.05) / 0.3)) for c in _lerp(s.sun_color_horizon, s.sun_color_noon, max(0.0, elevation * 1.5)))
    moon_color = tuple(c * night for c in s.moon_color)
    ambient = _lerp(s.ambient_night, s.ambient_day, daylight)
    star_alpha = max(0.0, min(1.0, (-elevation - 0.02) / 0.2))          # fade in after sunset, out before sunrise
    return Atmosphere(sun, sun_color, moon, moon_color, ambient, sky, fog_color, fog_density, elevation, daylight, star_alpha)
