"""Modelled props: things that are more than a textured box - the town well, the
smith's forge, the inn's bread oven and the signs hung beside shop doors.

Each ``draw_*`` fills the footprint of the prop it is given (``Prop.kind`` picks
the function in :mod:`scene`), so the level only states *where* a structure stands
and how big it is; the modelling lives here.
"""
from __future__ import annotations

import math
from typing import Callable, Sequence, Tuple

from OpenGL.GL import (GL_QUADS, GL_TEXTURE_2D, GL_TRIANGLE_FAN, glBegin, glBindTexture, glDisable, glEnable, glEnd,
                       glNormal3f, glPopMatrix, glPushMatrix, glRotatef, glTexCoord2f, glTranslatef, glVertex3f)

from ..core.math3d import Vector3D
from .models import flame_scale
from .primitives import draw_textured_box

Material = Callable[..., None]
SEGMENTS = 18


# ----------------------------------------------------------------------------- round things
def draw_ring(cx: float, cz: float, r_in: float, r_out: float, y0: float, y1: float, side_tex: int, top_tex: int,
              inner_tex: int = None, tile: float = 1.0, segments: int = SEGMENTS) -> None:
    """A hollow cylinder (a well's wall): outer face, inner face and the flat rim on top."""
    inner_tex = side_tex if inner_tex is None else inner_tex
    glEnable(GL_TEXTURE_2D)
    step = 2.0 * math.pi / segments
    for radius, tex, outward in ((r_out, side_tex, 1.0), (r_in, inner_tex, -1.0)):
        glBindTexture(GL_TEXTURE_2D, tex)
        glBegin(GL_QUADS)
        for i in range(segments):
            a0, a1 = i * step, (i + 1) * step
            x0, z0, x1, z1 = cx + radius * math.cos(a0), cz + radius * math.sin(a0), cx + radius * math.cos(a1), cz + radius * math.sin(a1)
            u0, u1 = (a0 * radius) / tile, (a1 * radius) / tile
            nx, nz = outward * math.cos((a0 + a1) / 2), outward * math.sin((a0 + a1) / 2)
            glNormal3f(nx, 0.0, nz)
            order = ((x0, z0, u0), (x1, z1, u1)) if outward > 0 else ((x1, z1, u1), (x0, z0, u0))
            (ax, az, au), (bx, bz, bu) = order
            glTexCoord2f(au, y0 / tile); glVertex3f(ax, y0, az)
            glTexCoord2f(bu, y0 / tile); glVertex3f(bx, y0, bz)
            glTexCoord2f(bu, y1 / tile); glVertex3f(bx, y1, bz)
            glTexCoord2f(au, y1 / tile); glVertex3f(ax, y1, az)
        glEnd()
    glBindTexture(GL_TEXTURE_2D, top_tex)
    glBegin(GL_QUADS)
    glNormal3f(0.0, 1.0, 0.0)
    for i in range(segments):
        a0, a1 = i * step, (i + 1) * step
        for (ra, a) in ((r_in, a0), (r_out, a0), (r_out, a1), (r_in, a1)):
            x, z = cx + ra * math.cos(a), cz + ra * math.sin(a)
            glTexCoord2f((x - cx) / tile, (z - cz) / tile); glVertex3f(x, y1, z)
    glEnd()
    glDisable(GL_TEXTURE_2D)


def draw_disc(cx: float, y: float, cz: float, radius: float, tex: int, tile: float = 1.0, segments: int = SEGMENTS) -> None:
    """A flat textured disc facing up (the water in the well)."""
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, tex)
    glBegin(GL_TRIANGLE_FAN)
    glNormal3f(0.0, 1.0, 0.0)
    glTexCoord2f(0.5, 0.5); glVertex3f(cx, y, cz)
    for i in range(segments + 1):
        a = i * 2.0 * math.pi / segments
        x, z = cx + radius * math.cos(a), cz + radius * math.sin(a)
        glTexCoord2f(0.5 + 0.5 * math.cos(a) * radius / tile, 0.5 + 0.5 * math.sin(a) * radius / tile)
        glVertex3f(x, y, z)
    glEnd()
    glDisable(GL_TEXTURE_2D)


def draw_gable_roof(cx: float, cz: float, half_x: float, half_z: float, eave_y: float, ridge_y: float, tex: int,
                    tile: float = 1.0) -> None:
    """A small pitched roof with its ridge running along x (two slopes, two gable triangles)."""
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, tex)
    glBegin(GL_QUADS)
    for side in (-1.0, 1.0):
        z_eave = cz + side * half_z
        ny, nz = half_z, side * (ridge_y - eave_y)
        m = math.hypot(ny, nz) or 1.0
        glNormal3f(0.0, ny / m, nz / m)
        corners = ((cx - half_x, eave_y, z_eave), (cx + half_x, eave_y, z_eave), (cx + half_x, ridge_y, cz), (cx - half_x, ridge_y, cz))
        if side < 0:
            corners = corners[::-1]
        for (x, y, z), (u, v) in zip(corners, ((0.0, 0.0), (2 * half_x / tile, 0.0), (2 * half_x / tile, 1.0), (0.0, 1.0))):
            glTexCoord2f(u, v); glVertex3f(x, y, z)
    glEnd()
    glDisable(GL_TEXTURE_2D)


# ----------------------------------------------------------------------------- the structures
def draw_well(prop, textures, material: Material, time: float) -> None:
    """A round stone well: a hollow ring you can look down into (water at the bottom), two
    posts carrying a windlass with its rope and bucket, and a little wooden roof over it all."""
    mn, mx = prop.min_point, prop.max_point
    cx, cz = (mn.x + mx.x) / 2, (mn.z + mx.z) / 2
    r_out = min(mx.x - mn.x, mx.z - mn.z) / 2 * 0.8
    r_in = r_out - 0.32
    rim_y = mx.y
    material(textured=True)
    draw_ring(cx, cz, r_in, r_out, mn.y, rim_y, textures["wall"], textures["stone"], textures["stone"], tile=1.2)
    material(color=(0.55, 0.55, 0.6), textured=True)
    draw_ring(cx, cz, r_in - 0.01, r_in, mn.y - 0.02, mn.y + 0.02, textures["stone"], textures["stone"])   # shaft lip
    material(color=(0.7, 0.8, 0.9), emission=(0.02, 0.04, 0.06), textured=True)
    draw_disc(cx, mn.y + 0.5, cz, r_in, textures["water"], tile=2.0 * r_in)            # the water, half way down the shaft
    # posts, crossbeam, windlass and roof
    material(textured=True)
    post_x = r_out + 0.1
    post_top = rim_y + 1.5
    for sx in (-1.0, 1.0):
        draw_textured_box(Vector3D(cx + sx * post_x - 0.08, mn.y, cz - 0.08), Vector3D(cx + sx * post_x + 0.08, post_top, cz + 0.08),
                          textures["wood"], tile=None)
    draw_textured_box(Vector3D(cx - post_x - 0.1, post_top - 0.16, cz - 0.1), Vector3D(cx + post_x + 0.1, post_top, cz + 0.1),
                      textures["wood"], tile=None)                                              # crossbeam
    axle_y = rim_y + 0.95
    draw_textured_box(Vector3D(cx - post_x, axle_y - 0.1, cz - 0.1), Vector3D(cx + post_x, axle_y + 0.1, cz + 0.1),
                      textures["torch"], tile=None)                                             # the windlass drum
    draw_textured_box(Vector3D(cx + post_x + 0.08, axle_y - 0.04, cz - 0.04), Vector3D(cx + post_x + 0.5, axle_y + 0.04, cz + 0.04),
                      textures["wood"], tile=None)                                              # crank
    draw_textured_box(Vector3D(cx + post_x + 0.42, axle_y - 0.04, cz - 0.04), Vector3D(cx + post_x + 0.5, axle_y + 0.4, cz + 0.04),
                      textures["wood"], tile=None)
    material(color=(0.8, 0.72, 0.55), textured=True)
    draw_textured_box(Vector3D(cx - 0.015, rim_y + 0.25, cz - 0.015), Vector3D(cx + 0.015, axle_y, cz + 0.015),
                      textures["cloth"], tile=None)                                             # rope
    material(textured=True)
    draw_textured_box(Vector3D(cx - 0.16, rim_y + 0.02, cz - 0.16), Vector3D(cx + 0.16, rim_y + 0.27, cz + 0.16),
                      textures["torch"], tile=None)                                             # bucket
    roof_half = r_out + 0.45
    draw_gable_roof(cx, cz, roof_half + 0.1, roof_half * 0.8, post_top - 0.1, post_top + 0.55, textures["roof"], tile=2.0)
    material(color=(1.0, 1.0, 1.0), textured=True)


def draw_forge(prop, textures, material: Material, time: float) -> None:
    """The smith's forge: a waist-high stone hearth with a shallow bowl sunk into its top, full
    of glowing coals with several small flames licking up, and a hood/chimney at the back."""
    mn, mx = prop.min_point, prop.max_point
    cx, cz = (mn.x + mx.x) / 2, (mn.z + mx.z) / 2
    top = mn.y + min(mx.y - mn.y, 1.0)
    glPushMatrix()
    glTranslatef(cx, 0.0, cz)
    glRotatef(-prop.facing, 0.0, 1.0, 0.0)
    hx, hz = (mx.x - mn.x) / 2, (mx.z - mn.z) / 2
    material(textured=True)
    # the hearth: four stone walls around the bowl and a stone base, so the bowl is sunk in
    lip = 0.16
    bowl_depth = 0.14
    draw_textured_box(Vector3D(-hx, mn.y, -hz), Vector3D(hx, top - bowl_depth, hz), textures["wall"], tile=1.0)
    for x1, x2, z1, z2 in ((-hx, -hx + lip, -hz, hz), (hx - lip, hx, -hz, hz), (-hx, hx, -hz, -hz + lip), (-hx, hx, hz - lip, hz)):
        draw_textured_box(Vector3D(x1, top - bowl_depth, z1), Vector3D(x2, top, z2), textures["stone"], tile=1.0)
    # the bed of coals in the bowl
    material(color=(1.0, 0.9, 0.85), emission=(0.6, 0.22, 0.06), textured=True, fog=0.5)
    draw_textured_box(Vector3D(-hx + lip, top - bowl_depth, -hz + lip), Vector3D(hx - lip, top - bowl_depth + 0.1, hz - lip),
                      textures["coals"], tile=None)
    # several small flames, each flickering on its own
    material(color=(1.0, 0.78, 0.5), emission=(0.9, 0.55, 0.2), textured=True, fog=0.25)
    for i, (fx, fz) in enumerate(((-0.4, -0.15), (0.05, 0.12), (0.42, -0.08), (-0.15, -0.3), (0.25, 0.28), (-0.3, 0.25), (0.2, -0.3))):
        k = flame_scale(time, i * 1.9)
        fh, fw = 0.16 * k + 0.04 * (i % 3), 0.055
        base = top - bowl_depth + 0.06
        draw_textured_box(Vector3D(fx - fw, base, fz - fw), Vector3D(fx + fw, base + fh, fz + fw), textures["flame"], tile=None)
    # the hood at the back (+z is the back: the front faces -z), narrowing into a chimney
    material(textured=True)
    draw_textured_box(Vector3D(-hx, top, hz - 0.25), Vector3D(hx, top + 0.9, hz), textures["wall"], tile=1.0)
    draw_textured_box(Vector3D(-hx * 0.6, top + 0.9, hz - 0.25), Vector3D(hx * 0.6, top + 1.7, hz), textures["wall"], tile=1.0)
    draw_textured_box(Vector3D(-hx * 0.35, top + 1.7, hz - 0.22), Vector3D(hx * 0.35, top + 2.6, hz - 0.03), textures["stone"], tile=1.0)
    # the bellows: a leather wedge at the side, its nozzle into the coals
    material(color=(1.0, 1.0, 1.0), textured=True)
    draw_textured_box(Vector3D(hx, top - 0.45, -0.25), Vector3D(hx + 0.55, top - 0.15, 0.25), textures["leather"], tile=None)
    draw_textured_box(Vector3D(hx + 0.5, top - 0.4, -0.05), Vector3D(hx + 0.9, top - 0.2, 0.05), textures["wood"], tile=None)
    glPopMatrix()
    material(color=(1.0, 1.0, 1.0), textured=True)


def draw_oven(prop, textures, material: Material, time: float) -> None:
    """The inn's bread oven: a stone box with an arched mouth in the front, the fire set well
    back inside it and a shelf in front of the mouth where pots and loaves are set to warm."""
    mn, mx = prop.min_point, prop.max_point
    cx, cz = (mn.x + mx.x) / 2, (mn.z + mx.z) / 2
    hx, hz, top = (mx.x - mn.x) / 2, (mx.z - mn.z) / 2, mx.y
    glPushMatrix()
    glTranslatef(cx, 0.0, cz)
    glRotatef(-prop.facing, 0.0, 1.0, 0.0)
    material(textured=True)
    mouth_w, mouth_h, sill = 0.55, 0.6, 0.45
    front = -hz
    # the body: a floor slab, two cheeks either side of the mouth, the lintel above it and the back
    draw_textured_box(Vector3D(-hx, mn.y, front), Vector3D(hx, mn.y + sill, hz), textures["wall"], tile=1.0)        # hearth slab
    draw_textured_box(Vector3D(-hx, mn.y + sill, front), Vector3D(-mouth_w, top, hz), textures["wall"], tile=1.0)   # left cheek
    draw_textured_box(Vector3D(mouth_w, mn.y + sill, front), Vector3D(hx, top, hz), textures["wall"], tile=1.0)     # right cheek
    draw_textured_box(Vector3D(-mouth_w, mn.y + sill + mouth_h, front), Vector3D(mouth_w, top, hz), textures["wall"], tile=1.0)  # lintel
    draw_textured_box(Vector3D(-mouth_w, mn.y + sill, front + 1.0), Vector3D(mouth_w, top, hz), textures["stone"], tile=1.0)      # the back
    # inside the mouth: a dark floor, the fire at the back of the chamber
    material(color=(0.45, 0.42, 0.4), textured=True)
    draw_textured_box(Vector3D(-mouth_w, mn.y + sill - 0.02, front + 0.02), Vector3D(mouth_w, mn.y + sill + 0.02, front + 1.0),
                      textures["stone"], tile=1.0)
    material(color=(1.0, 0.9, 0.85), emission=(0.6, 0.22, 0.06), textured=True, fog=0.5)
    draw_textured_box(Vector3D(-mouth_w + 0.08, mn.y + sill + 0.02, front + 0.6), Vector3D(mouth_w - 0.08, mn.y + sill + 0.08, front + 0.98),
                      textures["coals"], tile=None)
    material(color=(1.0, 0.78, 0.5), emission=(0.9, 0.55, 0.2), textured=True, fog=0.25)
    for i, fx in enumerate((-0.25, 0.0, 0.25)):
        k = flame_scale(time, 0.7 + i * 2.1)
        fh, fw = 0.3 * k, 0.1
        draw_textured_box(Vector3D(fx - fw, mn.y + sill + 0.06, front + 0.72), Vector3D(fx + fw, mn.y + sill + 0.06 + fh, front + 0.9),
                          textures["flame"], tile=None)
    # a stone shelf in front of the mouth with a pot and a couple of loaves warming on it
    material(color=(1.0, 1.0, 1.0), textured=True)
    draw_textured_box(Vector3D(-hx, mn.y + sill - 0.08, front - 0.45), Vector3D(hx, mn.y + sill, front + 0.02), textures["stone"], tile=1.0)
    material(color=(0.25, 0.25, 0.28), textured=True)
    draw_textured_box(Vector3D(-0.55, mn.y + sill, front - 0.38), Vector3D(-0.25, mn.y + sill + 0.22, front - 0.08), textures["stone"], tile=None)  # pot
    material(color=(0.78, 0.6, 0.35), textured=True)
    for lx in (0.05, 0.35):
        draw_textured_box(Vector3D(lx, mn.y + sill, front - 0.35), Vector3D(lx + 0.24, mn.y + sill + 0.12, front - 0.12), textures["cloth"], tile=None)  # loaves
    # the flue on top
    material(color=(1.0, 1.0, 1.0), textured=True)
    draw_textured_box(Vector3D(-0.25, top, hz - 0.6), Vector3D(0.25, top + 0.7, hz - 0.1), textures["stone"], tile=1.0)
    glPopMatrix()
    material(color=(1.0, 1.0, 1.0), textured=True)


def draw_sign(prop, textures, material: Material, time: float) -> None:
    """A shop sign hung from an iron bracket beside a door: the board carries the trade's device
    (``prop.texture``: sign_smith, sign_store, ...) on both faces."""
    mn, mx = prop.min_point, prop.max_point
    cx, cz = (mn.x + mx.x) / 2, (mn.z + mx.z) / 2
    hx, hz = (mx.x - mn.x) / 2, (mx.z - mn.z) / 2
    glPushMatrix()
    glTranslatef(cx, 0.0, cz)
    glRotatef(-prop.facing, 0.0, 1.0, 0.0)          # the board's face looks along -z
    material(textured=True)
    board = textures[prop.texture]
    draw_textured_box(Vector3D(-hx, mn.y, -0.04), Vector3D(hx, mx.y, 0.04), board, tile=None)
    material(color=(0.25, 0.25, 0.28), textured=True)
    draw_textured_box(Vector3D(-hx - 0.05, mx.y, -0.05), Vector3D(hx + 0.05, mx.y + 0.06, 0.05), textures["stone"], tile=None)   # the rail
    draw_textured_box(Vector3D(-0.04, mx.y, hz - 0.06), Vector3D(0.04, mx.y + 0.06, hz + 0.3), textures["stone"], tile=None)     # bracket arm
    draw_textured_box(Vector3D(-0.04, mx.y - 0.4, hz + 0.22), Vector3D(0.04, mx.y + 0.06, hz + 0.3), textures["stone"], tile=None)  # wall plate
    for sx in (-hx + 0.12, hx - 0.12):
        draw_textured_box(Vector3D(sx - 0.012, mx.y - 0.02, -0.012), Vector3D(sx + 0.012, mx.y + 0.02, 0.012), textures["stone"], tile=None)
    glPopMatrix()
    material(color=(1.0, 1.0, 1.0), textured=True)


DRAWERS = {"well": draw_well, "forge": draw_forge, "oven": draw_oven, "sign": draw_sign}


def footprint_center(prop) -> Tuple[float, float, float]:
    mn, mx = prop.min_point, prop.max_point
    return ((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, (mn.z + mx.z) / 2)


__all__: Sequence[str] = ("DRAWERS", "draw_well", "draw_forge", "draw_oven", "draw_sign", "draw_ring", "draw_disc",
                          "draw_gable_roof")
