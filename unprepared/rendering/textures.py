"""Texture loading for the renderer.

Textures are 128x128 tileable PNGs in ``assets/textures`` produced by the
tooling in ``tools/textures`` (``python tools/textures/gen_textures.py``).
A missing file is replaced by a loud magenta placeholder. Uploads use mipmaps
so distant ground/walls do not shimmer.
"""
from __future__ import annotations

import os
from typing import Dict, List

import pygame
from OpenGL.GL import (GL_GENERATE_MIPMAP, GL_LINEAR, GL_LINEAR_MIPMAP_LINEAR, GL_REPEAT, GL_RGBA, GL_TEXTURE_2D,
                       GL_TEXTURE_MAG_FILTER, GL_TEXTURE_MIN_FILTER, GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T, GL_TRUE,
                       GL_UNSIGNED_BYTE, glBindTexture, glDeleteTextures, glGenTextures, glTexImage2D, glTexParameteri)

SIZE = 128
DEFAULT_TEXTURE_KEYS = ("ground", "building", "wall", "guard", "npc", "wood", "bed", "shelf", "door", "ore", "skin",
                        "flame", "sun", "sun_glow", "moon", "stone", "torch", "roof", "roof_slate", "iron", "lockbox",
                        "lockbox_side", "wax")


def placeholder_surface(key: str = "") -> pygame.Surface:
    """Loud magenta tile that makes a missing texture obvious."""
    surf = pygame.Surface((SIZE, SIZE))
    surf.fill((255, 0, 255))
    return surf



# ----------------------------------------------------------------------------- GL upload
def upload_surface(surface: pygame.Surface, mipmap: bool = False, repeat: bool = True) -> int:
    """Upload a pygame surface as a GL_TEXTURE_2D; returns the texture id."""
    image_data = pygame.image.tostring(surface, "RGBA", True)
    width, height = surface.get_size()
    texture_id = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, texture_id)
    if mipmap:
        glTexParameteri(GL_TEXTURE_2D, GL_GENERATE_MIPMAP, GL_TRUE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
    else:
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    wrap = GL_REPEAT
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, wrap)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, wrap)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, image_data)
    return texture_id


class TextureRegistry:
    """Maps texture keys ("wall", "npc", ...) to GL texture ids, loading lazily from ``asset_dir``."""

    def __init__(self, asset_dir: str, mipmaps: bool = True):
        self.asset_dir = asset_dir
        self.mipmaps = mipmaps
        self._ids: Dict[str, int] = {}
        self.missing: List[str] = []        # keys that fell back to the placeholder

    def path_for(self, key: str) -> str:
        return os.path.join(self.asset_dir, f"{key}.png")

    def load(self, key: str) -> int:
        path = self.path_for(key)
        if os.path.exists(path):
            surface = pygame.image.load(path)
        else:
            surface = placeholder_surface(key)
            self.missing.append(key)
        # ``upload_surface`` hands GL the rows bottom-up, so the image's top ends up at v = 1:
        # the top of the picture is the top of the wall / box it is painted on.
        self._ids[key] = upload_surface(surface, mipmap=self.mipmaps)
        return self._ids[key]

    def preload(self, keys=DEFAULT_TEXTURE_KEYS) -> None:
        for key in keys:
            self.load(key)

    def get(self, key: str) -> int:
        tex = self._ids.get(key)
        if tex is None:
            tex = self.load(key)
        return tex

    __getitem__ = get

    def release(self) -> None:
        if self._ids:
            glDeleteTextures(list(self._ids.values()))
            self._ids.clear()
