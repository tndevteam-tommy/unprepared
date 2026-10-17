"""Per-frame lighting state: the atmosphere (sun/moon/sky/fog) plus every torch.

With GLSL available the values go to the lighting shader; otherwise the
fixed-function lights and ``glFog`` are configured to approximate the same look.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from OpenGL.GL import (GL_AMBIENT, GL_CONSTANT_ATTENUATION, GL_DIFFUSE, GL_EXP2, GL_FOG, GL_FOG_COLOR, GL_FOG_DENSITY,
                       GL_FOG_END, GL_FOG_MODE, GL_FOG_START, GL_LINEAR, GL_LIGHT0, GL_LIGHT1, GL_LIGHT2, GL_LIGHT3, GL_LIGHT4, GL_LIGHT5, GL_LIGHT6,
                       GL_LIGHT7, GL_LIGHT_MODEL_AMBIENT, GL_LINEAR_ATTENUATION, GL_POSITION, GL_QUADRATIC_ATTENUATION,
                       glDisable, glEnable, glFogf, glFogfv, glFogi, glLightModelfv, glLightf, glLightfv)

from ..config import LightingSettings
from ..core.math3d import Vector3D
from .atmosphere import Atmosphere, compute_atmosphere
from .shaders import LightingShader

Vec3 = Tuple[float, float, float]
FIXED_LIGHTS = (GL_LIGHT2, GL_LIGHT3, GL_LIGHT4, GL_LIGHT5, GL_LIGHT6, GL_LIGHT7)


@dataclass(frozen=True)
class PointLight:
    position: Vec3        # world space
    color: Vec3
    range: float
    bounds: Optional[Tuple[float, float, float, float]] = None   # (min_x, min_z, max_x, max_z) it may not leave


class Camera:
    """View basis for the frame (used to move lights into eye space and to face billboards)."""

    def __init__(self, eye: Vec3, view_matrix: Sequence[float]):
        self.eye = eye
        m = view_matrix
        self.side = (m[0], m[4], m[8])
        self.up = (m[1], m[5], m[9])
        self.back = (m[2], m[6], m[10])          # -forward

    def to_eye_point(self, p: Vec3) -> Vec3:
        d = (p[0] - self.eye[0], p[1] - self.eye[1], p[2] - self.eye[2])
        return self.to_eye_dir(d)

    def to_eye_dir(self, d: Vec3) -> Vec3:
        return (self.side[0] * d[0] + self.side[1] * d[1] + self.side[2] * d[2],
                self.up[0] * d[0] + self.up[1] * d[1] + self.up[2] * d[2],
                self.back[0] * d[0] + self.back[1] * d[1] + self.back[2] * d[2])

    def inverse_view_matrix(self) -> List[float]:
        """Column-major eye -> world: world = R^T * eye + eye_position."""
        s, u, b, e = self.side, self.up, self.back, self.eye
        return [s[0], s[1], s[2], 0.0,
                u[0], u[1], u[2], 0.0,
                b[0], b[1], b[2], 0.0,
                e[0], e[1], e[2], 1.0]


class LightingRig:
    def __init__(self, settings: LightingSettings, shader: Optional[LightingShader] = None):
        self.settings = settings
        self.shader = shader
        self.atmosphere: Optional[Atmosphere] = None
        self.point_lights: List[PointLight] = []
        self.max_lights = 8

    # --- gathering ------------------------------------------------------------------
    def flicker(self, time: float, phase: float = 0.0) -> float:
        s = self.settings.torch_flicker
        return 1.0 - s + s * (0.5 + 0.5 * math.sin(time * 11.0 + phase) * math.cos(time * 5.3 + phase * 0.7))

    @staticmethod
    def _room_bounds(world, position) -> Optional[Tuple[float, float, float, float]]:
        """A light inside a building is confined to its footprint (walls do not let light through)."""
        building = world.building_at(position) if hasattr(world, "building_at") else None
        if building is None:
            return None
        (x1, z1), (x2, z2) = building.min_xz, building.max_xz
        inset = 0.45                          # the walls are 0.5 thick: light reaches their inner faces only
        return (x1 + inset, z1 + inset, x2 - inset, z2 - inset)

    def gather(self, game) -> List[PointLight]:
        """Every lit torch and indoor fixture in the world as a point light."""
        s, time, world = self.settings, game.world.elapsed, game.world
        lights: List[PointLight] = []
        player = game.player
        if player.has_lit_torch:
            e = player.eye_position
            k = self.flicker(time)
            lights.append(PointLight((e.x, e.y - 0.3, e.z), tuple(c * k for c in s.torch_color), s.player_torch_range,
                                     self._room_bounds(world, player.position)))
        eye = player.position
        npc_lights = []
        for idx, npc in enumerate(world.npcs):
            if npc.has_torch and not npc.is_asleep:
                p, k = npc.position, self.flicker(time, idx * 1.7)
                npc_lights.append((p.distance_to(eye), PointLight((p.x, p.y + s.npc_torch_height + 0.3, p.z),
                                                                   tuple(c * k for c in s.torch_color), s.torch_range,
                                                                   self._room_bounds(world, p))))
        for idx, fixture in enumerate(getattr(world, "fixtures", ())):
            fx, fy, fz = fixture.position
            k = self.flicker(time, idx * 2.3 + 0.9) if fixture.kind == "candle" else 0.85 + 0.15 * self.flicker(time, idx)
            color = s.fire_color if fixture.kind == "fire" else s.candle_color if fixture.kind == "candle" else s.lantern_color
            dist = ((fx - eye.x) ** 2 + (fy - eye.y) ** 2 + (fz - eye.z) ** 2) ** 0.5
            npc_lights.append((dist + (2.0 if fixture.kind == "candle" else 0.0),
                               PointLight((fx, fy + 0.15, fz), tuple(c * k for c in color), fixture.range,
                                          self._room_bounds(world, Vector3D(fx, fy, fz)))))
        npc_lights.sort(key=lambda entry: entry[0])          # the nearest lights get the slots
        lights += [light for _, light in npc_lights]
        self.point_lights = lights[:max(0, self.max_lights)]
        return self.point_lights

    # --- applying ---------------------------------------------------------------------
    def begin_frame(self, game, camera: Camera, fog_far: float = 0.0) -> Atmosphere:
        """Light the frame. ``fog_far`` is the draw distance: beyond it nothing is drawn, so the
        fog is made to close in just before it (on low settings this hides the clipping)."""
        atm = compute_atmosphere(game.world.clock.fractional_hour, self.settings)
        self.atmosphere = atm
        lights = self.gather(game)
        if self.shader is not None:
            self.shader.use()
            self.shader.set_fog_far(fog_far)
            self.shader.set_atmosphere(camera.to_eye_dir(atm.sun_dir), atm.sun_color, camera.to_eye_dir(atm.moon_dir),
                                       atm.moon_color, atm.ambient, atm.fog_color, atm.fog_density)
            self.shader.set_inverse_view(camera.inverse_view_matrix())
            self.shader.set_point_lights([(camera.to_eye_point(l.position), l.color, l.range, l.bounds) for l in lights])
            self.shader.set_material()
        else:
            self._apply_fixed_function(atm, lights, fog_far)
        return atm

    def end_frame(self) -> None:
        if self.shader is not None:
            self.shader.stop()
        else:
            glDisable(GL_FOG)

    @staticmethod
    def distance_fog_wins(fog_density: float, fog_far: float) -> bool:
        """Whether the draw-distance fog closes in before the weather's own haze would."""
        if fog_far <= 0.0:
            return False
        haze_reach = 1.2 / max(fog_density, 1e-6)       # where exp2 fog has swallowed ~75% of a thing
        return fog_far < haze_reach

    def _apply_fixed_function(self, atm: Atmosphere, lights: Sequence[PointLight], fog_far: float = 0.0) -> None:
        glLightModelfv(GL_LIGHT_MODEL_AMBIENT, [*atm.ambient, 1.0])
        glEnable(GL_LIGHT0)
        glLightfv(GL_LIGHT0, GL_POSITION, [*atm.sun_dir, 0.0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [*atm.sun_color, 1.0])
        glLightfv(GL_LIGHT0, GL_AMBIENT, [0.0, 0.0, 0.0, 1.0])
        glEnable(GL_LIGHT1)
        glLightfv(GL_LIGHT1, GL_POSITION, [*atm.moon_dir, 0.0])
        glLightfv(GL_LIGHT1, GL_DIFFUSE, [*atm.moon_color, 1.0])
        for slot, light in zip(FIXED_LIGHTS, list(lights) + [None] * len(FIXED_LIGHTS)):
            if light is None:
                glDisable(slot)
                continue
            glEnable(slot)
            glLightfv(slot, GL_POSITION, [*light.position, 1.0])
            glLightfv(slot, GL_DIFFUSE, [*light.color, 1.0])
            glLightf(slot, GL_CONSTANT_ATTENUATION, 1.0)
            glLightf(slot, GL_LINEAR_ATTENUATION, 2.0 / light.range)
            glLightf(slot, GL_QUADRATIC_ATTENUATION, 4.0 / (light.range * light.range))
        glEnable(GL_FOG)
        glFogfv(GL_FOG_COLOR, [*atm.fog_color, 1.0])
        if self.distance_fog_wins(atm.fog_density, fog_far):
            glFogi(GL_FOG_MODE, GL_LINEAR)           # the fixed pipeline has one fog: use whichever is thicker
            glFogf(GL_FOG_START, fog_far * 0.55)
            glFogf(GL_FOG_END, fog_far)
        else:
            glFogi(GL_FOG_MODE, GL_EXP2)
            glFogf(GL_FOG_DENSITY, atm.fog_density)
