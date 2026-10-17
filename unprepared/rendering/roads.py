"""Cobbled paving: a textured rectangle just above the ground with edge strips whose
texture fades to transparent, so the stones blend into the grass instead of ending
in a hard line."""
from __future__ import annotations

from OpenGL.GL import (GL_BLEND, GL_ONE_MINUS_SRC_ALPHA, GL_QUADS, GL_SRC_ALPHA, GL_TEXTURE_2D, glBegin, glBindTexture,
                       glBlendFunc, glDepthMask, glDisable, glEnable, glEnd, glNormal3f, glTexCoord2f, glVertex3f)

ROAD_Y = 0.02
EDGE = 0.9          # width of the blended border
TILE = 2.0          # world units per texture repeat


def _quad(x1, z1, x2, z2, u_scale, v_inner_outer=None):
    """Flat quad with repeating u along x (or z for edge strips) and either repeating v or a
    fixed (inner, outer) v pair for the fading edge texture."""
    glNormal3f(0.0, 1.0, 0.0)
    if v_inner_outer is None:
        glTexCoord2f(x1 / TILE, z1 / TILE); glVertex3f(x1, ROAD_Y, z1)
        glTexCoord2f(x2 / TILE, z1 / TILE); glVertex3f(x2, ROAD_Y, z1)
        glTexCoord2f(x2 / TILE, z2 / TILE); glVertex3f(x2, ROAD_Y, z2)
        glTexCoord2f(x1 / TILE, z2 / TILE); glVertex3f(x1, ROAD_Y, z2)


def _edge(a1, a2, inner, outer, along_x: bool) -> None:
    """Strip between ``inner`` and ``outer`` (the coordinate across the road), from a1 to a2 along it.
    v = 0 (opaque) at the inner side, v = 1 (transparent) at the outer side."""
    glNormal3f(0.0, 1.0, 0.0)
    if along_x:
        glTexCoord2f(a1 / TILE, 0.0); glVertex3f(a1, ROAD_Y, inner)
        glTexCoord2f(a2 / TILE, 0.0); glVertex3f(a2, ROAD_Y, inner)
        glTexCoord2f(a2 / TILE, 1.0); glVertex3f(a2, ROAD_Y, outer)
        glTexCoord2f(a1 / TILE, 1.0); glVertex3f(a1, ROAD_Y, outer)
    else:
        glTexCoord2f(a1 / TILE, 0.0); glVertex3f(inner, ROAD_Y, a1)
        glTexCoord2f(a2 / TILE, 0.0); glVertex3f(inner, ROAD_Y, a2)
        glTexCoord2f(a2 / TILE, 1.0); glVertex3f(outer, ROAD_Y, a2)
        glTexCoord2f(a1 / TILE, 1.0); glVertex3f(outer, ROAD_Y, a1)


def draw_roads(roads, textures, material) -> None:
    if not roads:
        return
    material(textured=True)
    glEnable(GL_TEXTURE_2D)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glDepthMask(False)
    for road in roads:
        (x1, z1), (x2, z2) = road.min_xz, road.max_xz
        e = min(EDGE, (x2 - x1) / 3.0, (z2 - z1) / 3.0)
        glBindTexture(GL_TEXTURE_2D, textures[road.texture])
        glBegin(GL_QUADS)
        _quad(x1 + e, z1 + e, x2 - e, z2 - e, TILE)
        glEnd()
        glBindTexture(GL_TEXTURE_2D, textures[road.texture + "_edge"])
        glBegin(GL_QUADS)
        _edge(x1, x2, z1 + e, z1, along_x=True)          # north edge fades towards -z
        _edge(x1, x2, z2 - e, z2, along_x=True)          # south
        _edge(z1 + e, z2 - e, x1 + e, x1, along_x=False)  # west
        _edge(z1 + e, z2 - e, x2 - e, x2, along_x=False)  # east
        glEnd()
    glDepthMask(True)
    glDisable(GL_BLEND)
    glDisable(GL_TEXTURE_2D)
