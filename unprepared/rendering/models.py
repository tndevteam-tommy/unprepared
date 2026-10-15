"""Composite models: NPC bodies with heads, eyes and torches; the player's held torch."""
from __future__ import annotations

import math
from typing import Callable, Tuple

from OpenGL.GL import glPopMatrix, glPushMatrix, glRotatef, glTranslatef

from ..core.math3d import BoundingBox3D, Vector3D
from .primitives import draw_box, draw_sphere, draw_textured_box

Material = Callable[..., None]   # material(color=(r,g,b), emission=(r,g,b), textured=bool, fog=float)

BODY_HALF_X, BODY_HALF_Z, BODY_HEIGHT = 0.34, 0.2, 1.3
HEAD_HALF, HEAD_BASE = 0.2, 1.34
EYE_Y = HEAD_BASE + 0.26
EYE_RADIUS, PUPIL_RADIUS = 0.065, 0.035
EYE_SPACING = 0.095


def npc_texture_key(npc) -> str:
    return "guard" if npc.is_guard else "npc"


def draw_npc(npc, textures, material: Material, body_box: BoundingBox3D, time: float) -> None:
    """Upright NPCs get a body, a head with eyes looking along ``facing_yaw`` and (at
    night) a torch; sleeping NPCs are drawn lying flat on their bed."""
    tex_body = textures[npc_texture_key(npc)]
    if npc.is_asleep:
        draw_sleeping(npc, body_box, tex_body, textures["skin"], material)
        return
    p = npc.position
    glPushMatrix()
    glTranslatef(p.x, p.y, p.z)
    glRotatef(-npc.facing_yaw, 0.0, 1.0, 0.0)        # local -z is the NPC's front
    material(textured=True)
    draw_textured_box(Vector3D(-BODY_HALF_X, 0.0, -BODY_HALF_Z), Vector3D(BODY_HALF_X, BODY_HEIGHT, BODY_HALF_Z), tex_body, tile=None)
    draw_textured_box(Vector3D(-HEAD_HALF, HEAD_BASE, -HEAD_HALF), Vector3D(HEAD_HALF, HEAD_BASE + 2 * HEAD_HALF, HEAD_HALF),
                      textures["skin"], tile=None)
    # eyes on the front face of the head (local -z), pupils a touch further forward
    material(color=(1.0, 1.0, 1.0), textured=False)
    for sx in (-EYE_SPACING, EYE_SPACING):
        draw_sphere((sx, EYE_Y, -HEAD_HALF), EYE_RADIUS)
    material(color=(0.05, 0.05, 0.07), textured=False)
    for sx in (-EYE_SPACING, EYE_SPACING):
        draw_sphere((sx, EYE_Y, -HEAD_HALF - EYE_RADIUS * 0.75), PUPIL_RADIUS)
    if npc.has_torch:
        draw_torch((BODY_HALF_X + 0.12, 0.95, -0.05), textures, material, time, phase=hash(npc.name) % 7)
    glPopMatrix()


def draw_sleeping(npc, body_box: BoundingBox3D, tex_body: int, tex_skin: int, material: Material) -> None:
    """Lying pose: the body box from the world plus a head at one end (eyes closed)."""
    material(textured=True)
    b = body_box
    along_x = (b.max_point.x - b.min_point.x) >= (b.max_point.z - b.min_point.z)
    head = 0.42
    if along_x:
        body = BoundingBox3D(Vector3D(b.min_point.x + head, b.min_point.y, b.min_point.z), b.max_point)
        head_box = BoundingBox3D(Vector3D(b.min_point.x, b.min_point.y, b.min_point.z + 0.05),
                                 Vector3D(b.min_point.x + head, b.max_point.y, b.max_point.z - 0.05))
    else:
        body = BoundingBox3D(Vector3D(b.min_point.x, b.min_point.y, b.min_point.z + head), b.max_point)
        head_box = BoundingBox3D(Vector3D(b.min_point.x + 0.05, b.min_point.y, b.min_point.z),
                                 Vector3D(b.max_point.x - 0.05, b.max_point.y, b.min_point.z + head))
    draw_box(body, tex_body, tile=None)
    draw_box(head_box, tex_skin, tile=None)


def flame_scale(time: float, phase: float = 0.0) -> float:
    return 1.0 + 0.12 * math.sin(time * 17.0 + phase) + 0.06 * math.sin(time * 29.0 + phase * 1.3)


def draw_torch(origin: Tuple[float, float, float], textures, material: Material, time: float, phase: float = 0.0,
               stick_height: float = 0.45) -> None:
    """A wooden stick with a glowing flame on top (local coordinates)."""
    x, y, z = origin
    material(textured=True)
    draw_textured_box(Vector3D(x - 0.04, y, z - 0.04), Vector3D(x + 0.04, y + stick_height, z + 0.04), textures["torch"], tile=None)
    k = flame_scale(time, phase)
    fh, fw = 0.22 * k, 0.11
    # the flame is emissive and punches through the fog so distant torches show as points of light
    material(emission=(1.0, 0.75, 0.35), textured=True, fog=0.25)
    draw_textured_box(Vector3D(x - fw, y + stick_height, z - fw), Vector3D(x + fw, y + stick_height + fh, z + fw), textures["flame"], tile=None)
    material(textured=True)


def draw_fixture(fixture, textures, material: Material, time: float) -> None:
    """An indoor light: a wall lantern (iron frame on a bracket, flame inside) or a table candle."""
    x, y, z = fixture.position
    phase = (hash(fixture.room) % 11) * 0.6
    k = flame_scale(time, phase)
    if fixture.kind == "candle":
        material(textured=True)
        draw_textured_box(Vector3D(x - 0.035, y, z - 0.035), Vector3D(x + 0.035, y + 0.16, z + 0.035), textures["wax"], tile=None)
        material(emission=(1.0, 0.75, 0.35), textured=True, fog=0.25)
        fh, fw = 0.1 * k, 0.05
        draw_textured_box(Vector3D(x - fw, y + 0.16, z - fw), Vector3D(x + fw, y + 0.16 + fh, z + fw), textures["flame"], tile=None)
        material(textured=True)
        return
    glPushMatrix()
    glTranslatef(x, y, z)
    glRotatef(-fixture.facing, 0.0, 1.0, 0.0)          # local -z points into the room; the wall is behind (+z)
    material(textured=True)
    iron = textures["iron"]
    draw_textured_box(Vector3D(-0.03, -0.02, 0.0), Vector3D(0.03, 0.02, 0.35), iron, tile=None)       # bracket to the wall
    draw_textured_box(Vector3D(-0.13, -0.22, -0.13), Vector3D(0.13, -0.18, 0.13), iron, tile=None)    # base plate
    draw_textured_box(Vector3D(-0.13, 0.16, -0.13), Vector3D(0.13, 0.2, 0.13), iron, tile=None)       # cap
    for sx in (-0.12, 0.1):
        for sz in (-0.12, 0.1):
            draw_textured_box(Vector3D(sx, -0.18, sz), Vector3D(sx + 0.02, 0.16, sz + 0.02), iron, tile=None)   # corner posts
    material(emission=(1.0, 0.78, 0.4), textured=True, fog=0.25)
    fh, fw = 0.2 * k, 0.06
    draw_textured_box(Vector3D(-fw, -0.16, -fw), Vector3D(fw, -0.16 + fh, fw), textures["flame"], tile=None)
    material(textured=True)
    glPopMatrix()


def draw_held_torch(textures, material: Material, time: float) -> None:
    """The player's torch in the lower right of the view (call with an identity modelview)."""
    glPushMatrix()
    glTranslatef(0.42, -0.55, -0.9)
    glRotatef(-18.0, 0.0, 0.0, 1.0)
    glRotatef(12.0, 1.0, 0.0, 0.0)
    draw_torch((0.0, 0.0, 0.0), textures, material, time, phase=0.0, stick_height=0.55)
    glPopMatrix()
