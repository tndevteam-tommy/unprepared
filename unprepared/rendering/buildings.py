"""Floors and gabled roofs generated from a level's ``BuildingDef`` footprints."""
from __future__ import annotations

from OpenGL.GL import GL_QUADS, GL_TEXTURE_2D, GL_TRIANGLES, glBegin, glBindTexture, glDisable, glEnable, glEnd, glNormal3f, glTexCoord2f, glVertex3f

from ..core.math3d import Vector3D
from .primitives import draw_textured_box

OVERHANG = 0.4
TILE = 2.0


def draw_floor(building, texture_id: int) -> None:
    (x1, z1), (x2, z2) = building.min_xz, building.max_xz
    draw_textured_box(Vector3D(x1, 0.0, z1), Vector3D(x2, 0.05, z2), texture_id, tile=TILE)


def draw_ceiling(building, texture_id: int) -> None:
    """The underside of the roof: a flat textured ceiling at wall height, facing down into the
    rooms. It spans the roof's whole base (overhang included) so there is no gap at the eaves."""
    (x1, z1), (x2, z2) = building.min_xz, building.max_xz
    x1, z1, x2, z2 = x1 - OVERHANG, z1 - OVERHANG, x2 + OVERHANG, z2 + OVERHANG
    y = building.wall_height - 0.02
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, texture_id)
    glBegin(GL_QUADS)
    glNormal3f(0.0, -1.0, 0.0)
    glTexCoord2f(0, 0); glVertex3f(x1, y, z1)
    glTexCoord2f((x2 - x1) / TILE, 0); glVertex3f(x2, y, z1)
    glTexCoord2f((x2 - x1) / TILE, (z2 - z1) / TILE); glVertex3f(x2, y, z2)
    glTexCoord2f(0, (z2 - z1) / TILE); glVertex3f(x1, y, z2)
    glEnd()
    glDisable(GL_TEXTURE_2D)


def draw_roof(building, texture_id: int) -> None:
    """Two sloped planes meeting at a ridge along the longer axis, closed by triangular gables."""
    (x1, z1), (x2, z2) = building.min_xz, building.max_xz
    x1, z1, x2, z2 = x1 - OVERHANG, z1 - OVERHANG, x2 + OVERHANG, z2 + OVERHANG
    base = building.wall_height
    top = base + building.roof_height
    along_x = (x2 - x1) >= (z2 - z1)
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, texture_id)
    if along_x:
        mid = (z1 + z2) / 2.0
        half = (z2 - z1) / 2.0
        n = (0.0, half, building.roof_height)
        length = (x2 - x1) / TILE
        slope = (half * half + building.roof_height ** 2) ** 0.5 / TILE
        glBegin(GL_QUADS)
        glNormal3f(0.0, n[2], n[1])                                   # south slope faces +z
        glTexCoord2f(0, 0); glVertex3f(x1, base, z2)
        glTexCoord2f(length, 0); glVertex3f(x2, base, z2)
        glTexCoord2f(length, slope); glVertex3f(x2, top, mid)
        glTexCoord2f(0, slope); glVertex3f(x1, top, mid)
        glNormal3f(0.0, n[2], -n[1])                                  # north slope faces -z
        glTexCoord2f(0, 0); glVertex3f(x2, base, z1)
        glTexCoord2f(length, 0); glVertex3f(x1, base, z1)
        glTexCoord2f(length, slope); glVertex3f(x1, top, mid)
        glTexCoord2f(0, slope); glVertex3f(x2, top, mid)
        glEnd()
        glBegin(GL_TRIANGLES)                                         # gable ends
        for gx, nx in ((x1, -1.0), (x2, 1.0)):
            glNormal3f(nx, 0.0, 0.0)
            glTexCoord2f(0, 0); glVertex3f(gx, base, z1)
            glTexCoord2f(1, 0); glVertex3f(gx, base, z2)
            glTexCoord2f(0.5, 1); glVertex3f(gx, top, mid)
        glEnd()
    else:
        mid = (x1 + x2) / 2.0
        half = (x2 - x1) / 2.0
        n = (half, building.roof_height)
        length = (z2 - z1) / TILE
        slope = (half * half + building.roof_height ** 2) ** 0.5 / TILE
        glBegin(GL_QUADS)
        glNormal3f(n[1], n[0], 0.0)                                   # east slope faces +x
        glTexCoord2f(0, 0); glVertex3f(x2, base, z1)
        glTexCoord2f(length, 0); glVertex3f(x2, base, z2)
        glTexCoord2f(length, slope); glVertex3f(mid, top, z2)
        glTexCoord2f(0, slope); glVertex3f(mid, top, z1)
        glNormal3f(-n[1], n[0], 0.0)                                  # west slope faces -x
        glTexCoord2f(0, 0); glVertex3f(x1, base, z2)
        glTexCoord2f(length, 0); glVertex3f(x1, base, z1)
        glTexCoord2f(length, slope); glVertex3f(mid, top, z1)
        glTexCoord2f(0, slope); glVertex3f(mid, top, z2)
        glEnd()
        glBegin(GL_TRIANGLES)
        for gz, nz in ((z1, -1.0), (z2, 1.0)):
            glNormal3f(0.0, 0.0, nz)
            glTexCoord2f(0, 0); glVertex3f(x1, base, gz)
            glTexCoord2f(1, 0); glVertex3f(x2, base, gz)
            glTexCoord2f(0.5, 1); glVertex3f(mid, top, gz)
        glEnd()
    glDisable(GL_TEXTURE_2D)
