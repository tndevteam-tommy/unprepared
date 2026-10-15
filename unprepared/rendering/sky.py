"""Sky: the sun and moon discs and a star field that fades in after dusk."""
from __future__ import annotations

import math
import random
from typing import List, Tuple

from OpenGL.GL import (GL_BLEND, GL_DEPTH_TEST, GL_ONE, GL_ONE_MINUS_SRC_ALPHA, GL_POINTS, GL_SRC_ALPHA, glBegin,
                       glBlendFunc, glColor4f, glDepthMask, glDisable, glEnable, glEnd, glNormal3f, glPointSize,
                       glVertex3f)

SUN_GLOW_SCALE = 4.0        # halo diameter relative to the sun disc

from .atmosphere import Atmosphere
from .lighting import Camera
from .primitives import draw_billboard

Vec3 = Tuple[float, float, float]


def make_star_field(count: int, seed: int = 11) -> List[Tuple[Vec3, float]]:
    """Unit directions on the upper hemisphere with a brightness each (deterministic)."""
    rng = random.Random(seed)
    stars = []
    for _ in range(count):
        z = rng.uniform(0.05, 1.0)                      # elevation
        a = rng.uniform(0.0, 2.0 * math.pi)
        r = math.sqrt(1.0 - z * z)
        stars.append(((math.cos(a) * r, z, math.sin(a) * r), rng.uniform(0.35, 1.0)))
    return stars


def draw_sky_bodies(atm: Atmosphere, camera: Camera, textures, material, settings, show_bodies: bool = True,
                    stars=(), star_alpha: float = 0.0, shader=None) -> None:
    """Draw before the world with depth writes off, so buildings occlude the discs and stars."""
    glDisable(GL_DEPTH_TEST)
    glDepthMask(False)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    d = settings.sky_distance
    if stars and star_alpha > 0.0:
        material(color=(1.0, 1.0, 1.0), emission=(1.0, 1.0, 1.0), textured=False, fog=0.0)
        if shader is not None:
            shader.set_alpha(star_alpha)
        glPointSize(2.0)
        glBegin(GL_POINTS)
        glNormal3f(0.0, -1.0, 0.0)
        for (dx, dy, dz), brightness in stars:
            if shader is None:
                glColor4f(brightness, brightness, brightness, star_alpha)
            glVertex3f(camera.eye[0] + dx * d, camera.eye[1] + dy * d, camera.eye[2] + dz * d)
        glEnd()
        if shader is not None:
            shader.set_alpha(1.0)
    if show_bodies:
        for direction, key, size, visible in ((atm.sun_dir, "sun", settings.sun_disc_size, atm.sun_elevation > -0.12),
                                              (atm.moon_dir, "moon", settings.moon_disc_size, -atm.sun_elevation > -0.12)):
            if not visible:
                continue
            center = (camera.eye[0] + direction[0] * d, camera.eye[1] + direction[1] * d, camera.eye[2] + direction[2] * d)
            glow = (1.0, 0.95, 0.8) if key == "sun" else (0.55, 0.6, 0.75)
            if key == "sun":
                # additive halo behind the disc, fading with the sun's height so dawn/dusk glow warm and wide
                strength = 0.35 + 0.65 * max(0.0, min(1.0, (atm.sun_elevation + 0.12) / 0.5))
                glBlendFunc(GL_SRC_ALPHA, GL_ONE)
                material(color=(1.0, 1.0, 1.0), emission=(strength, strength * 0.9, strength * 0.7), textured=True, fog=0.0)
                draw_billboard(center, camera.side, camera.up, size * SUN_GLOW_SCALE, textures["sun_glow"])
                glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            material(color=(1.0, 1.0, 1.0), emission=glow, textured=True, fog=0.0)
            draw_billboard(center, camera.side, camera.up, size, textures[key])
    material(textured=True)
    glDisable(GL_BLEND)
    glDepthMask(True)
    glEnable(GL_DEPTH_TEST)
