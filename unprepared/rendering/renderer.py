"""Top-level renderer: GL context setup plus the per-frame 3D + HUD passes."""
from __future__ import annotations

from typing import Optional

import pygame
from OpenGL.GL import (GL_AMBIENT_AND_DIFFUSE, GL_COLOR_MATERIAL, GL_DEPTH_TEST, GL_FRONT_AND_BACK,
                       GL_LIGHTING, GL_MODELVIEW, GL_MODULATE, GL_PROJECTION, GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE,
                       glColorMaterial, glEnable, glLoadIdentity, glMatrixMode, glTexEnvi, glViewport)

from ..config import GameSettings
from ..graphics import GraphicsSettings
from .camera import apply_perspective
from .hud import HudRenderer
from .lighting import LightingRig
from .scene import SceneRenderer
from .shaders import try_create_lighting_shader
from .text import TextRenderer
from .textures import TextureRegistry


class Renderer:
    """Owns all GL resources. Create *after* the OpenGL window exists."""

    def __init__(self, settings: GameSettings, controls_help: list, use_shaders: bool = True,
                 graphics: Optional[GraphicsSettings] = None):
        self.settings = settings
        self.graphics = graphics or GraphicsSettings(shaders=use_shaders)
        use_shaders = use_shaders and self.graphics.shaders
        w = settings.window
        self.font = pygame.font.SysFont(w.font_name, w.font_size, bold=True)
        self.font_small = pygame.font.SysFont(w.font_name, w.font_small_size)
        self.font_tag = pygame.font.SysFont(w.tag_font_name, w.font_small_size, bold=True)

        self.init_gl()
        self.shader = try_create_lighting_shader() if use_shaders else None

        self.textures = TextureRegistry(settings.asset_dir, mipmaps=self.graphics.mipmaps)
        self.textures.preload()
        self.text = TextRenderer(self.font, self.font_small, font_tag=self.font_tag)
        self.lighting = LightingRig(settings.lighting, self.shader)
        self.scene = SceneRenderer(self.textures, self.lighting, self.shader, self.graphics, w.far_plane)
        self.hud = HudRenderer(self.text, settings.hud_layout(), settings.hud_colors, controls_help)
        self.renderer_name = self._query_renderer_name()
        self._applied_fov = self.graphics.fov

    @staticmethod
    def _query_renderer_name() -> str:
        try:
            from OpenGL.GL import GL_RENDERER, glGetString
            value = glGetString(GL_RENDERER)
            return value.decode() if isinstance(value, bytes) else str(value)
        except Exception:
            return "unknown"

    @property
    def uses_shaders(self) -> bool:
        return self.shader is not None

    def init_gl(self) -> None:
        w = self.settings.window
        glViewport(0, 0, w.width, w.height)
        self.apply_projection()
        glMatrixMode(GL_MODELVIEW)

        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)            # only matters for the fixed-function fallback
        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE)

    def apply_projection(self) -> None:
        w = self.settings.window
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        apply_perspective(self.graphics.fov, w.width / w.height, w.near_plane, w.far_plane)
        glMatrixMode(GL_MODELVIEW)
        self._applied_fov = self.graphics.fov

    def render_frame(self, game) -> None:
        self.render_scene_only(game)
        self.hud.render(game)

    def render_scene_only(self, game) -> None:
        if self.graphics.fov != self._applied_fov:
            self.apply_projection()
        self.hud.fov = self.graphics.fov
        self.scene.render(game)

    def release(self) -> None:
        self.text.clear_cache()
        self.textures.release()
