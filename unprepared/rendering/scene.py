"""Draws the 3D world for the current frame, honouring the graphics settings."""
from __future__ import annotations

from typing import Optional

from OpenGL.GL import (GL_AMBIENT_AND_DIFFUSE, GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, GL_EMISSION, GL_FRONT_AND_BACK,
                       glClear, glClearColor, glColor3f, glLoadIdentity, glMaterialfv)

from ..core.math3d import view_direction
from ..graphics import GraphicsSettings
from .buildings import draw_ceiling, draw_floor, draw_roof
from .camera import apply_look_at, look_at_matrix
from .lighting import Camera, LightingRig
from .models import draw_fixture, draw_held_torch, draw_npc
from .primitives import draw_box, draw_door, draw_fronted_box, draw_ground, draw_table
from .shaders import LightingShader
from .sky import draw_sky_bodies, make_star_field
from .textures import TextureRegistry

PROP_TEXTURES = {"bed": "bed", "table": "wood", "counter": "wood"}
# furniture whose picture belongs on the front only: front texture -> plain texture for top and sides
FRONTED_TEXTURES = {"shelf": "wood", "lockbox": "lockbox_side"}


def room_direction(world, box):
    """(dx, dz) from a box towards the middle of the room it stands in (defaults to +z)."""
    cx, cz = (box.min_point.x + box.max_point.x) / 2.0, (box.min_point.z + box.max_point.z) / 2.0
    building = world.building_at(box.center) if hasattr(world, "building_at") else None
    if building is None:
        return (0.0, 1.0)
    bx = (building.min_xz[0] + building.max_xz[0]) / 2.0
    bz = (building.min_xz[1] + building.max_xz[1]) / 2.0
    return (bx - cx, bz - cz)


def prop_texture_key(prop) -> str:
    for word, key in PROP_TEXTURES.items():
        if word in prop.name:
            return key
    return prop.texture


class SceneRenderer:
    def __init__(self, textures: TextureRegistry, lighting: LightingRig, shader: Optional[LightingShader],
                 graphics: Optional[GraphicsSettings] = None, far_plane: float = 100.0):
        self.textures = textures
        self.lighting = lighting
        self.shader = shader
        self.graphics = graphics or GraphicsSettings()
        self.far_plane = far_plane
        self._stars = None
        self._star_count = -1
        self.drawn_objects = 0           # statistics for the performance overlay
        self.culled_objects = 0

    # --- material abstraction (shader or fixed function) -----------------------------
    def material(self, color=(1.0, 1.0, 1.0), emission=(0.0, 0.0, 0.0), textured: bool = True, fog: float = 1.0) -> None:
        if self.shader is not None:
            self.shader.set_material(color, emission, textured, fog)
        else:
            glColor3f(*color)
            glMaterialfv(GL_FRONT_AND_BACK, GL_EMISSION, [*emission, 1.0])
            glMaterialfv(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE, [*color, 1.0])

    def stars(self):
        if self._star_count != self.graphics.star_count:
            self._stars = make_star_field(self.graphics.star_count)
            self._star_count = self.graphics.star_count
        return self._stars

    # --- frame --------------------------------------------------------------------------
    def camera_for(self, player):
        dir_x, dir_y, dir_z = view_direction(player.rotation_y, player.rotation_x)
        e = player.eye_position
        eye = (e.x, e.y, e.z)
        center = (eye[0] + dir_x, eye[1] + dir_y, eye[2] + dir_z)
        return Camera(eye, look_at_matrix(eye, center, (0.0, 1.0, 0.0))), center

    def _within(self, box, eye, limit: float) -> bool:
        cx = (box.min_point.x + box.max_point.x) / 2 - eye[0]
        cz = (box.min_point.z + box.max_point.z) / 2 - eye[2]
        radius = max(box.max_point.x - box.min_point.x, box.max_point.z - box.min_point.z) / 2
        return (cx * cx + cz * cz) ** 0.5 - radius <= limit

    def render(self, game) -> None:
        world, tex, time, gfx = game.world, self.textures, game.world.elapsed, self.graphics
        camera, center = self.camera_for(game.player)
        self.drawn_objects = self.culled_objects = 0
        object_limit = gfx.object_draw_distance(self.far_plane)
        npc_limit = gfx.character_draw_distance(self.far_plane)

        self.lighting.max_lights = gfx.torch_lights
        atm = self.lighting.begin_frame(game, camera)
        if self.shader is not None:
            self.shader.set_contrast(gfx.contrast)
        glClearColor(*atm.sky_color, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        apply_look_at(camera.eye, center)

        draw_sky_bodies(atm, camera, tex, self.material, self.lighting.settings, show_bodies=gfx.sky_bodies,
                        stars=self.stars() if gfx.stars else (), star_alpha=atm.star_alpha, shader=self.shader)

        self.material(textured=True)
        level = world.level
        draw_ground(tex[level.ground_texture], level.ground_half_size, level.ground_texture_repeat, cells=gfx.ground_cells)

        def draw_if_near(box, texture, tile=2.0):
            if self._within(box, camera.eye, object_limit):
                draw_box(box, texture, tile=tile)
                self.drawn_objects += 1
            else:
                self.culled_objects += 1

        for wall in world.walls:
            draw_if_near(wall, tex[wall.texture])
        for prop in world.props:
            if "table" in prop.name:
                if self._within(prop, camera.eye, object_limit):
                    draw_table(prop, tex[prop_texture_key(prop)])
                    self.drawn_objects += 1
                continue
            draw_if_near(prop, tex[prop_texture_key(prop)], tile=None if "bed" in prop.name else 1.0)
        for container in world.containers:
            kind = getattr(container, "kind", "box")
            if kind == "table" or "table" in container.name:
                if self._within(container, camera.eye, object_limit):
                    draw_table(container, tex[container.texture])
                    self.drawn_objects += 1
                continue
            key = "shelf" if "shelf" in container.name else container.texture
            if key in FRONTED_TEXTURES and self._within(container, camera.eye, object_limit):
                draw_fronted_box(container, tex[key], tex[FRONTED_TEXTURES[key]], room_direction(world, container))
                self.drawn_objects += 1
                continue
            draw_if_near(container, tex[key], tile=None)
        for station in world.stations:
            draw_if_near(station, tex[station.texture], tile=1.5 if station.is_mine else None)
        for lintel in getattr(world, "lintels", ()):
            draw_if_near(lintel, tex[lintel.texture])
        if gfx.roofs:
            for building in level.buildings:
                draw_floor(building, tex[building.floor_texture])
                draw_ceiling(building, tex[building.floor_texture])
                draw_roof(building, tex[building.roof_texture])
        for door in world.doors:
            if self._within(door.collider(), camera.eye, object_limit):
                draw_door(door, tex["door"], bars_texture_id=tex["iron"])
        for fixture in getattr(world, "fixtures", ()):
            fx, fy, fz = fixture.position
            if ((fx - camera.eye[0]) ** 2 + (fz - camera.eye[2]) ** 2) ** 0.5 <= object_limit:
                draw_fixture(fixture, tex, self.material, time)
                self.drawn_objects += 1
        for npc in world.npcs:
            if npc.position.distance_to(game.player.position) <= npc_limit:
                draw_npc(npc, tex, self.material, world.npc_body_box(npc), time)
                self.drawn_objects += 1
            else:
                self.culled_objects += 1

        if game.player.has_lit_torch:
            glLoadIdentity()
            draw_held_torch(tex, self.material, time)

        self.lighting.end_frame()
