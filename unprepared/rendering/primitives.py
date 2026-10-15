"""Immediate-mode drawing primitives."""
from __future__ import annotations

import math
from typing import Optional, Tuple

from OpenGL.GL import (GL_COMPILE, GL_QUADS, GL_TEXTURE_2D, GL_TRIANGLE_STRIP, glBegin, glBindTexture, glCallList,
                       glColor4f, glDisable, glEnable, glEnd, glEndList, glGenLists, glNewList, glNormal3f, glPopMatrix,
                       glPushMatrix, glRotatef, glScalef, glTexCoord2f, glTranslatef, glVertex2f, glVertex3f)

from ..core.math3d import BoundingBox3D, Vector3D
from ..entities import Door

DEFAULT_TILE = 2.0     # world units per texture repeat on tiled boxes


def draw_textured_box(min_pt: Vector3D, max_pt: Vector3D, texture_id: int, tile: Optional[float] = DEFAULT_TILE) -> None:
    """Axis-aligned box. With ``tile`` the texture repeats every ``tile`` units so long
    walls are not stretched; ``tile=None`` maps the whole texture once per face."""
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, texture_id)
    x1, y1, z1 = min_pt.x, min_pt.y, min_pt.z
    x2, y2, z2 = max_pt.x, max_pt.y, max_pt.z
    sx, sy, sz = x2 - x1, y2 - y1, z2 - z1

    def uv(a: float, b: float) -> Tuple[float, float]:
        return (a / tile, b / tile) if tile else (1.0 if a else 0.0, 1.0 if b else 0.0)

    faces = (
        ((0.0, 0.0, 1.0), ((x1, y1, z2), (x2, y1, z2), (x2, y2, z2), (x1, y2, z2)), (sx, sy)),
        ((0.0, 0.0, -1.0), ((x2, y1, z1), (x1, y1, z1), (x1, y2, z1), (x2, y2, z1)), (sx, sy)),
        ((-1.0, 0.0, 0.0), ((x1, y1, z1), (x1, y1, z2), (x1, y2, z2), (x1, y2, z1)), (sz, sy)),
        ((1.0, 0.0, 0.0), ((x2, y1, z2), (x2, y1, z1), (x2, y2, z1), (x2, y2, z2)), (sz, sy)),
        ((0.0, 1.0, 0.0), ((x1, y2, z2), (x2, y2, z2), (x2, y2, z1), (x1, y2, z1)), (sx, sz)),
        ((0.0, -1.0, 0.0), ((x1, y1, z1), (x2, y1, z1), (x2, y1, z2), (x1, y1, z2)), (sx, sz)),
    )
    glBegin(GL_QUADS)
    for normal, vertices, (w, h) in faces:
        glNormal3f(*normal)
        corners = ((0.0, 0.0), (w, 0.0), (w, h), (0.0, h))
        for (u, v), vert in zip(corners, vertices):
            glTexCoord2f(*uv(u, v))
            glVertex3f(*vert)
    glEnd()
    glDisable(GL_TEXTURE_2D)


def draw_box(box: BoundingBox3D, texture_id: int, tile: Optional[float] = DEFAULT_TILE) -> None:
    draw_textured_box(box.min_point, box.max_point, texture_id, tile)


def draw_fronted_box(box: BoundingBox3D, front_texture_id: int, side_texture_id: int, front: Tuple[float, float],
                     side_tile: Optional[float] = 1.0) -> None:
    """A box whose *front* face (the one facing ``front`` = (dx, dz), e.g. into the room) shows
    ``front_texture_id`` once, while the top and the other sides show plain ``side_texture_id``
    - shelves and chests look like furniture, not like the same picture on every face."""
    mn, mx = box.min_point, box.max_point
    fx, fz = front
    normal = (0.0, 0.0, 1.0 if fz >= 0 else -1.0) if abs(fz) >= abs(fx) else (1.0 if fx >= 0 else -1.0, 0.0, 0.0)
    x1, y1, z1, x2, y2, z2 = mn.x, mn.y, mn.z, mx.x, mx.y, mx.z
    sx, sy, sz = x2 - x1, y2 - y1, z2 - z1
    faces = (
        ((0.0, 0.0, 1.0), ((x1, y1, z2), (x2, y1, z2), (x2, y2, z2), (x1, y2, z2)), (sx, sy)),
        ((0.0, 0.0, -1.0), ((x2, y1, z1), (x1, y1, z1), (x1, y2, z1), (x2, y2, z1)), (sx, sy)),
        ((-1.0, 0.0, 0.0), ((x1, y1, z1), (x1, y1, z2), (x1, y2, z2), (x1, y2, z1)), (sz, sy)),
        ((1.0, 0.0, 0.0), ((x2, y1, z2), (x2, y1, z1), (x2, y2, z1), (x2, y2, z2)), (sz, sy)),
        ((0.0, 1.0, 0.0), ((x1, y2, z2), (x2, y2, z2), (x2, y2, z1), (x1, y2, z1)), (sx, sz)),
        ((0.0, -1.0, 0.0), ((x1, y1, z1), (x2, y1, z1), (x2, y1, z2), (x1, y1, z2)), (sx, sz)),
    )
    glEnable(GL_TEXTURE_2D)
    for n, vertices, (w, h) in faces:
        is_front = n == normal
        glBindTexture(GL_TEXTURE_2D, front_texture_id if is_front else side_texture_id)
        glBegin(GL_QUADS)
        glNormal3f(*n)
        for (u, v), vert in zip(((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)), vertices):
            if is_front or not side_tile:
                glTexCoord2f(1.0 if u else 0.0, 1.0 if v else 0.0)
            else:
                glTexCoord2f(u / side_tile, v / side_tile)
            glVertex3f(*vert)
        glEnd()
    glDisable(GL_TEXTURE_2D)


def draw_ground(texture_id: int, half_size: float = 50.0, repeat: float = 10.0, cells: int = 20) -> None:
    """Ground plane split into a grid of quads (keeps fog/lighting interpolation smooth)."""
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, texture_id)
    step = 2.0 * half_size / cells
    tex_step = repeat / cells
    glBegin(GL_QUADS)
    glNormal3f(0.0, 1.0, 0.0)
    for i in range(cells):
        x0 = -half_size + i * step
        x1 = x0 + step
        u0, u1 = i * tex_step, (i + 1) * tex_step
        for j in range(cells):
            z0 = -half_size + j * step
            z1 = z0 + step
            v0, v1 = j * tex_step, (j + 1) * tex_step
            glTexCoord2f(u0, v0); glVertex3f(x0, 0.0, z0)
            glTexCoord2f(u1, v0); glVertex3f(x1, 0.0, z0)
            glTexCoord2f(u1, v1); glVertex3f(x1, 0.0, z1)
            glTexCoord2f(u0, v1); glVertex3f(x0, 0.0, z1)
    glEnd()
    glDisable(GL_TEXTURE_2D)


def draw_door_leaf(width: float, height: float, thickness: float, texture_id: int) -> None:
    """A door leaf hinged at the local origin, spanning +x. The texture's handle side is
    the far edge (+x) on *both* faces, i.e. the back face shows the mirror image of the
    front - as a real door does - and the edges pick up the matching strip."""
    half = thickness / 2.0
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, texture_id)
    glBegin(GL_QUADS)
    # front (+z): u runs hinge -> handle left to right
    glNormal3f(0.0, 0.0, 1.0)
    glTexCoord2f(0, 0); glVertex3f(0.0, 0.0, half)
    glTexCoord2f(1, 0); glVertex3f(width, 0.0, half)
    glTexCoord2f(1, 1); glVertex3f(width, height, half)
    glTexCoord2f(0, 1); glVertex3f(0.0, height, half)
    # back (-z): the same u at the same x, so the handle stays on the far edge (mirrored view)
    glNormal3f(0.0, 0.0, -1.0)
    glTexCoord2f(1, 0); glVertex3f(width, 0.0, -half)
    glTexCoord2f(0, 0); glVertex3f(0.0, 0.0, -half)
    glTexCoord2f(0, 1); glVertex3f(0.0, height, -half)
    glTexCoord2f(1, 1); glVertex3f(width, height, -half)
    # hinge edge (x = 0) and handle edge (x = width): thin strips from the matching texture column
    eu = thickness / width
    glNormal3f(-1.0, 0.0, 0.0)
    glTexCoord2f(0, 0); glVertex3f(0.0, 0.0, -half)
    glTexCoord2f(eu, 0); glVertex3f(0.0, 0.0, half)
    glTexCoord2f(eu, 1); glVertex3f(0.0, height, half)
    glTexCoord2f(0, 1); glVertex3f(0.0, height, -half)
    glNormal3f(1.0, 0.0, 0.0)
    glTexCoord2f(1, 0); glVertex3f(width, 0.0, half)
    glTexCoord2f(1 - eu, 0); glVertex3f(width, 0.0, -half)
    glTexCoord2f(1 - eu, 1); glVertex3f(width, height, -half)
    glTexCoord2f(1, 1); glVertex3f(width, height, half)
    # top edge
    glNormal3f(0.0, 1.0, 0.0)
    glTexCoord2f(0, 1); glVertex3f(0.0, height, half)
    glTexCoord2f(1, 1); glVertex3f(width, height, half)
    glTexCoord2f(1, 1 - eu); glVertex3f(width, height, -half)
    glTexCoord2f(0, 1 - eu); glVertex3f(0.0, height, -half)
    glEnd()
    glDisable(GL_TEXTURE_2D)


BAR_SPACING, BAR_SIZE = 0.32, 0.07


def draw_bars(width: float, height: float, thickness: float, texture_id: int) -> None:
    """A barred gate hinged at the local origin: top and bottom rails with vertical rods."""
    half = thickness / 2.0
    rail = 0.12
    draw_textured_box(Vector3D(0.0, 0.0, -half), Vector3D(width, rail, half), texture_id, tile=None)
    draw_textured_box(Vector3D(0.0, height - rail, -half), Vector3D(width, height, half), texture_id, tile=None)
    draw_textured_box(Vector3D(0.0, height * 0.5 - rail / 2, -half), Vector3D(width, height * 0.5 + rail / 2, half),
                      texture_id, tile=None)
    count = max(2, int(width / BAR_SPACING))
    for i in range(count + 1):
        x = min(width - BAR_SIZE, i * width / count)
        draw_textured_box(Vector3D(x, rail, -BAR_SIZE / 2), Vector3D(x + BAR_SIZE, height - rail, BAR_SIZE / 2),
                          texture_id, tile=None)


def draw_door(door: Door, texture_id: int, open_angle: float = 90.0, bars_texture_id: Optional[int] = None) -> None:
    glPushMatrix()
    glTranslatef(door.hinge_position.x, door.hinge_position.y, door.hinge_position.z)
    if door.is_open:
        glRotatef(open_angle, 0.0, 1.0, 0.0)
    if getattr(door, "is_bars", False):
        draw_bars(door.width, door.height, door.thickness, bars_texture_id if bars_texture_id is not None else texture_id)
    else:
        draw_door_leaf(door.width, door.height, door.thickness, texture_id)
    glPopMatrix()


TABLE_TOP, TABLE_LEG = 0.12, 0.14


def draw_table(box: BoundingBox3D, texture_id: int) -> None:
    """A four-legged table filling ``box``: a slab on top and a leg inset at each corner."""
    mn, mx = box.min_point, box.max_point
    top_y = mx.y - TABLE_TOP
    draw_textured_box(Vector3D(mn.x, top_y, mn.z), mx, texture_id, tile=1.0)
    inset = 0.08
    for lx in (mn.x + inset, mx.x - inset - TABLE_LEG):
        for lz in (mn.z + inset, mx.z - inset - TABLE_LEG):
            draw_textured_box(Vector3D(lx, mn.y, lz), Vector3D(lx + TABLE_LEG, top_y, lz + TABLE_LEG), texture_id, tile=None)


def fill_rect_2d(x1: float, y1: float, x2: float, y2: float, color) -> None:
    """Axis-aligned filled rectangle in the current (orthographic) 2D projection."""
    glBegin(GL_QUADS)
    glColor4f(*color)
    glVertex2f(x1, y1); glVertex2f(x2, y1); glVertex2f(x2, y2); glVertex2f(x1, y2)
    glEnd()


_sphere_list: Optional[int] = None


def _build_unit_sphere(slices: int = 12, stacks: int = 8) -> int:
    lst = glGenLists(1)
    glNewList(lst, GL_COMPILE)
    for i in range(stacks):
        lat0 = math.pi * (-0.5 + i / stacks)
        lat1 = math.pi * (-0.5 + (i + 1) / stacks)
        y0, r0 = math.sin(lat0), math.cos(lat0)
        y1, r1 = math.sin(lat1), math.cos(lat1)
        glBegin(GL_TRIANGLE_STRIP)
        for j in range(slices + 1):
            lng = 2 * math.pi * j / slices
            x, z = math.cos(lng), math.sin(lng)
            glNormal3f(x * r1, y1, z * r1)
            glVertex3f(x * r1, y1, z * r1)
            glNormal3f(x * r0, y0, z * r0)
            glVertex3f(x * r0, y0, z * r0)
        glEnd()
    glEndList()
    return lst


def draw_sphere(center: Tuple[float, float, float], radius: float) -> None:
    """Untextured sphere (colour comes from the current material/shader colour)."""
    global _sphere_list
    if _sphere_list is None:
        _sphere_list = _build_unit_sphere()
    glPushMatrix()
    glTranslatef(*center)
    glScalef(radius, radius, radius)
    glCallList(_sphere_list)
    glPopMatrix()


def draw_billboard(center: Tuple[float, float, float], right: Tuple[float, float, float],
                   up: Tuple[float, float, float], size: float, texture_id: int) -> None:
    """Camera-facing textured quad (``right``/``up`` are the camera's basis vectors)."""
    h = size / 2.0
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, texture_id)
    glBegin(GL_QUADS)
    glNormal3f(-right[1] * up[2] + right[2] * up[1], -right[2] * up[0] + right[0] * up[2], -right[0] * up[1] + right[1] * up[0])
    for (u, v), (sx, sy) in zip(((0, 0), (1, 0), (1, 1), (0, 1)), ((-h, -h), (h, -h), (h, h), (-h, h))):
        glTexCoord2f(u, v)
        glVertex3f(center[0] + right[0] * sx + up[0] * sy, center[1] + right[1] * sx + up[1] * sy,
                   center[2] + right[2] * sx + up[2] * sy)
    glEnd()
    glDisable(GL_TEXTURE_2D)
