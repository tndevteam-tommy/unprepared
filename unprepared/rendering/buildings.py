"""Floors and gabled roofs generated from a level's ``BuildingDef`` footprints."""
from __future__ import annotations

from OpenGL.GL import GL_QUADS, GL_TEXTURE_2D, GL_TRIANGLES, glBegin, glBindTexture, glDisable, glEnable, glEnd, glNormal3f, glTexCoord2f, glVertex3f

from ..core.math3d import Vector3D
from .primitives import draw_textured_box

OVERHANG = 0.4
TILE = 2.0


WALL_THICKNESS = 0.5


def draw_floor(building, texture_id: int) -> None:
    """Floorboards inside the walls (inset by the wall thickness so no edge peeks out at the base)."""
    (x1, z1), (x2, z2) = building.min_xz, building.max_xz
    inset = WALL_THICKNESS - 0.02
    draw_textured_box(Vector3D(x1 + inset, 0.0, z1 + inset), Vector3D(x2 - inset, 0.05, z2 - inset), texture_id, tile=TILE)


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


FASCIA = 0.16          # boards around the roof base sealing the seam between roof and ceiling


def draw_fascia(building, texture_id: int) -> None:
    """Boards running around the roof base: they close the slit between the roof planes, the
    gables and the ceiling underneath so no light or sky shows through at the eaves."""
    (x1, z1), (x2, z2) = building.min_xz, building.max_xz
    x1, z1, x2, z2 = x1 - OVERHANG, z1 - OVERHANG, x2 + OVERHANG, z2 + OVERHANG
    base = building.wall_height
    lo, hi = base - 0.22, base + 0.04
    draw_textured_box(Vector3D(x1, lo, z1), Vector3D(x2, hi, z1 + FASCIA), texture_id, tile=1.0)
    draw_textured_box(Vector3D(x1, lo, z2 - FASCIA), Vector3D(x2, hi, z2), texture_id, tile=1.0)
    draw_textured_box(Vector3D(x1, lo, z1), Vector3D(x1 + FASCIA, hi, z2), texture_id, tile=1.0)
    draw_textured_box(Vector3D(x2 - FASCIA, lo, z1), Vector3D(x2, hi, z2), texture_id, tile=1.0)


def draw_roof(building, texture_id: int, fascia_texture_id: int = None) -> None:
    """Two sloped planes meeting at a ridge along the longer axis, closed by triangular gables
    and trimmed with fascia boards."""
    if fascia_texture_id is not None:
        draw_fascia(building, fascia_texture_id)
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
