"""Composite models: NPC bodies with heads, eyes and torches; the player's held torch."""
from __future__ import annotations

import math
import zlib
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


WAIST = 0.62                    # where the tunic ends and the legs begin
HAT_TOP = HEAD_BASE + 2 * HEAD_HALF


def npc_texture_key(npc) -> str:
    """The body texture: the watch's steel, or undyed cloth that is tinted by the outfit."""
    return "guard" if npc.clothes.armor else "cloth"


def _box(material, textures, key, color, min_pt, max_pt) -> None:
    material(color=color, textured=True)
    draw_textured_box(min_pt, max_pt, textures[key], tile=None)


def draw_outfit(npc, textures, material: Material) -> None:
    """The clothes on an upright model (local space: feet at the origin, front along -z)."""
    o = npc.clothes
    white = (1.0, 1.0, 1.0)
    # legs, then the tunic (or a breastplate) over them
    _box(material, textures, "cloth", o.legs, Vector3D(-BODY_HALF_X, 0.0, -BODY_HALF_Z), Vector3D(BODY_HALF_X, WAIST, BODY_HALF_Z))
    if o.armor:
        _box(material, textures, "guard", white, Vector3D(-BODY_HALF_X, WAIST - 0.04, -BODY_HALF_Z),
             Vector3D(BODY_HALF_X, BODY_HEIGHT, BODY_HALF_Z))
    else:
        _box(material, textures, "cloth", o.tunic, Vector3D(-BODY_HALF_X, WAIST - 0.04, -BODY_HALF_Z),
             Vector3D(BODY_HALF_X, BODY_HEIGHT, BODY_HALF_Z))
        _box(material, textures, "leather", (0.5, 0.4, 0.3), Vector3D(-BODY_HALF_X - 0.01, WAIST - 0.05, -BODY_HALF_Z - 0.01),
             Vector3D(BODY_HALF_X + 0.01, WAIST + 0.05, BODY_HALF_Z + 0.01))                     # belt
    if o.sash is not None:                                                                     # a band across the chest
        _box(material, textures, "cloth", o.sash, Vector3D(-0.1, WAIST + 0.08, -BODY_HALF_Z - 0.015),
             Vector3D(0.12, BODY_HEIGHT - 0.02, -BODY_HALF_Z + 0.02))
    if o.apron is not None:                                                                    # hangs down the front
        key, color = ("leather", white) if o.apron == "leather" else ("cloth", (0.93, 0.9, 0.84))
        _box(material, textures, key, color, Vector3D(-0.26, 0.22, -BODY_HALF_Z - 0.035),
             Vector3D(0.26, BODY_HEIGHT - 0.12, -BODY_HALF_Z + 0.01))
        _box(material, textures, key, color, Vector3D(-0.09, BODY_HEIGHT - 0.12, -BODY_HALF_Z - 0.03),
             Vector3D(0.09, BODY_HEIGHT - 0.02, -BODY_HALF_Z + 0.01))                           # the bib's strap
    # the head, its hair, and whatever is worn on it
    _box(material, textures, "skin", white, Vector3D(-HEAD_HALF, HEAD_BASE, -HEAD_HALF), Vector3D(HEAD_HALF, HAT_TOP, HEAD_HALF))
    if o.hat != "hood":
        _box(material, textures, "cloth", o.hair, Vector3D(-HEAD_HALF - 0.01, HAT_TOP - 0.12, -HEAD_HALF + 0.06),
             Vector3D(HEAD_HALF + 0.01, HAT_TOP + 0.01, HEAD_HALF + 0.01))                        # hair: top and back
    if o.hat == "helmet":                                                                      # a steel kettle helm
        _box(material, textures, "cloth", o.hat_color, Vector3D(-HEAD_HALF - 0.03, HAT_TOP - 0.11, -HEAD_HALF - 0.03),
             Vector3D(HEAD_HALF + 0.03, HAT_TOP + 0.1, HEAD_HALF + 0.03))
        _box(material, textures, "cloth", o.hat_color, Vector3D(-HEAD_HALF - 0.07, HAT_TOP - 0.11, -HEAD_HALF - 0.12),
             Vector3D(HEAD_HALF + 0.07, HAT_TOP - 0.07, HEAD_HALF + 0.07))                        # the brim
        _box(material, textures, "cloth", o.hat_color, Vector3D(-0.03, EYE_Y - 0.06, -HEAD_HALF - 0.03),
             Vector3D(0.03, HAT_TOP - 0.1, -HEAD_HALF + 0.0))                                    # nasal bar
    elif o.hat == "cap":
        _box(material, textures, "cloth", o.hat_color, Vector3D(-HEAD_HALF - 0.03, HAT_TOP - 0.1, -HEAD_HALF - 0.03),
             Vector3D(HEAD_HALF + 0.03, HAT_TOP + 0.07, HEAD_HALF + 0.03))
        _box(material, textures, "cloth", o.hat_color, Vector3D(-HEAD_HALF, HAT_TOP - 0.1, -HEAD_HALF - 0.14),
             Vector3D(HEAD_HALF, HAT_TOP - 0.07, -HEAD_HALF))                                    # peak
    elif o.hat == "scarf":
        _box(material, textures, "cloth", o.hat_color, Vector3D(-HEAD_HALF - 0.03, HEAD_BASE + 0.02, -HEAD_HALF - 0.03),
             Vector3D(HEAD_HALF + 0.03, HAT_TOP + 0.04, HEAD_HALF + 0.06))                        # wrapped round the sides
        _box(material, textures, "skin", white, Vector3D(-HEAD_HALF + 0.02, HEAD_BASE + 0.03, -HEAD_HALF - 0.035),
             Vector3D(HEAD_HALF - 0.02, HAT_TOP - 0.1, -HEAD_HALF - 0.034))                       # the face shows
    elif o.hat == "coif":
        _box(material, textures, "cloth", o.hat_color, Vector3D(-HEAD_HALF - 0.02, HEAD_BASE + 0.05, -HEAD_HALF - 0.02),
             Vector3D(HEAD_HALF + 0.02, HAT_TOP + 0.03, HEAD_HALF + 0.04))
        _box(material, textures, "skin", white, Vector3D(-HEAD_HALF + 0.025, HEAD_BASE + 0.05, -HEAD_HALF - 0.025),
             Vector3D(HEAD_HALF - 0.025, HAT_TOP - 0.06, -HEAD_HALF - 0.024))
    elif o.hat == "hood":
        _box(material, textures, "cloth", o.hat_color, Vector3D(-HEAD_HALF - 0.05, HEAD_BASE - 0.05, -HEAD_HALF - 0.02),
             Vector3D(HEAD_HALF + 0.05, HAT_TOP + 0.09, HEAD_HALF + 0.1))                         # a deep hood
        _box(material, textures, "skin", (0.8, 0.8, 0.8), Vector3D(-HEAD_HALF + 0.03, HEAD_BASE + 0.02, -HEAD_HALF - 0.025),
             Vector3D(HEAD_HALF - 0.03, HAT_TOP - 0.08, -HEAD_HALF - 0.024))                      # the face in shadow
        _box(material, textures, "cloth", o.hat_color, Vector3D(-BODY_HALF_X - 0.02, BODY_HEIGHT - 0.3, -BODY_HALF_Z - 0.02),
             Vector3D(BODY_HALF_X + 0.02, BODY_HEIGHT + 0.02, BODY_HALF_Z + 0.02))                 # cowl over the shoulders
    material(color=white, textured=True)


def draw_npc(npc, textures, material: Material, body_box: BoundingBox3D, time: float) -> None:
    """Upright NPCs get a dressed body, a head with eyes looking along ``facing_yaw`` and (at
    night) a torch; sleeping NPCs are drawn lying flat on their bed."""
    if npc.is_asleep:
        draw_sleeping(npc, body_box, textures, material)
        return
    p = npc.position
    glPushMatrix()
    glTranslatef(p.x, p.y, p.z)
    glRotatef(-npc.facing_yaw, 0.0, 1.0, 0.0)        # local -z is the NPC's front
    draw_outfit(npc, textures, material)
    # eyes on the front face of the head (local -z), pupils a touch further forward
    material(color=(1.0, 1.0, 1.0), textured=False)
    for sx in (-EYE_SPACING, EYE_SPACING):
        draw_sphere((sx, EYE_Y, -HEAD_HALF - 0.01), EYE_RADIUS)
    material(color=(0.05, 0.05, 0.07), textured=False)
    for sx in (-EYE_SPACING, EYE_SPACING):
        draw_sphere((sx, EYE_Y, -HEAD_HALF - 0.01 - EYE_RADIUS * 0.75), PUPIL_RADIUS)
    if npc.has_torch:
        draw_torch((BODY_HALF_X + 0.12, 0.95, -0.05), textures, material, time, phase=zlib.crc32(npc.name.encode("utf-8")) % 7)
    glPopMatrix()


def draw_sleeping(npc, body_box: BoundingBox3D, textures, material: Material) -> None:
    """Lying pose: the body box from the world (in the tunic's colour) plus a head at one end."""
    o = npc.clothes
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
    material(color=(1.0, 1.0, 1.0) if o.armor else o.tunic, textured=True)
    draw_box(body, textures[npc_texture_key(npc)], tile=None)
    material(color=(1.0, 1.0, 1.0), textured=True)
    draw_box(head_box, textures["skin"], tile=None)


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
    phase = (zlib.crc32(fixture.room.encode("utf-8")) % 11) * 0.6      # per-room phase (stable across runs)
    k = flame_scale(time, phase)
    if fixture.kind == "fire":
        return                      # a light only: the forge / oven it burns in draws its own coals and flames
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
