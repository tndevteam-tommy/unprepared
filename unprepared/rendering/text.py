"""Text drawing via pygame font surfaces uploaded as GL textures, with a small cache.

The original re-created and deleted a GL texture for every string every frame;
caching by (text, font, colour) produces pixel-identical output while avoiding
~20 texture uploads per frame.
"""
from __future__ import annotations

from typing import Dict, Tuple

import pygame
from OpenGL.GL import (GL_QUADS, GL_TEXTURE_2D, glBegin, glBindTexture, glColor4f, glDeleteTextures, glDisable,
                       glEnable, glEnd, glTexCoord2f, glVertex2f)

from .textures import upload_surface

RGB = Tuple[int, int, int]


class TextRenderer:
    def __init__(self, font: pygame.font.Font, font_small: pygame.font.Font, cache_size: int = 256,
                 font_tag: pygame.font.Font = None):
        self.font = font
        self.font_small = font_small
        self.font_tag = font_tag or font_small
        self.cache_size = cache_size
        self._cache: Dict[tuple, Tuple[int, int, int]] = {}   # key -> (texture id, w, h)

    def measure(self, text: str, font=None) -> Tuple[int, int]:
        return (font or self.font).size(text)

    def _texture_for(self, text: str, font: pygame.font.Font, color: RGB) -> Tuple[int, int, int]:
        key = (text, id(font), color)
        entry = self._cache.get(key)
        if entry is None:
            if len(self._cache) >= self.cache_size:
                self.clear_cache()
            surf = font.render(text, True, color)
            w, h = surf.get_size()
            entry = (upload_surface(surf), w, h)
            self._cache[key] = entry
        return entry

    def draw(self, text: str, x: float, y: float, font=None, color: RGB = (255, 255, 255)) -> Tuple[int, int]:
        """Draw ``text`` with its top-left corner at (x, y); returns the rendered (w, h)."""
        tex, w, h = self._texture_for(text, font or self.font, color)
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, tex)
        # Force white so the texture colour is not modulated by the current colour.
        glColor4f(1.0, 1.0, 1.0, 1.0)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 1); glVertex2f(x, y)
        glTexCoord2f(1, 1); glVertex2f(x + w, y)
        glTexCoord2f(1, 0); glVertex2f(x + w, y + h)
        glTexCoord2f(0, 0); glVertex2f(x, y + h)
        glEnd()
        glDisable(GL_TEXTURE_2D)
        return w, h

    def clear_cache(self) -> None:
        if self._cache:
            glDeleteTextures([tex for tex, _, _ in self._cache.values()])
            self._cache.clear()
