"""Projection / view helpers implemented in plain OpenGL (no GLU dependency).

GLU is deprecated and frequently missing on modern Linux and macOS installs;
these functions build the exact same matrices Mesa's ``gluPerspective`` and
``gluLookAt`` do.
"""
from __future__ import annotations

import math
from typing import List, Tuple

from OpenGL.GL import glMultMatrixd, glMultMatrixf, glTranslated


def perspective_matrix(fovy_degrees: float, aspect: float, z_near: float, z_far: float) -> List[float]:
    """Column-major 4x4 perspective matrix (identical maths to Mesa GLU)."""
    radians = fovy_degrees / 2.0 * math.pi / 180.0
    delta_z = z_far - z_near
    sine = math.sin(radians)
    if delta_z == 0 or sine == 0 or aspect == 0:
        raise ValueError("degenerate perspective parameters")
    cot = math.cos(radians) / sine
    m = [0.0] * 16
    m[0] = cot / aspect
    m[5] = cot
    m[10] = -(z_far + z_near) / delta_z
    m[11] = -1.0
    m[14] = -2.0 * z_near * z_far / delta_z
    return m


def look_at_matrix(eye: Tuple[float, float, float], center: Tuple[float, float, float],
                   up: Tuple[float, float, float]) -> List[float]:
    """Column-major rotation part of a look-at view matrix (translation applied separately)."""
    fx, fy, fz = center[0] - eye[0], center[1] - eye[1], center[2] - eye[2]
    mag = math.sqrt(fx * fx + fy * fy + fz * fz)
    fx, fy, fz = fx / mag, fy / mag, fz / mag
    ux, uy, uz = up
    sx, sy, sz = fy * uz - fz * uy, fz * ux - fx * uz, fx * uy - fy * ux
    mag = math.sqrt(sx * sx + sy * sy + sz * sz)
    sx, sy, sz = sx / mag, sy / mag, sz / mag
    upx, upy, upz = sy * fz - sz * fy, sz * fx - sx * fz, sx * fy - sy * fx
    return [sx, upx, -fx, 0.0,
            sy, upy, -fy, 0.0,
            sz, upz, -fz, 0.0,
            0.0, 0.0, 0.0, 1.0]


def apply_perspective(fovy_degrees: float, aspect: float, z_near: float, z_far: float) -> None:
    glMultMatrixd(perspective_matrix(fovy_degrees, aspect, z_near, z_far))


def apply_look_at(eye, center, up=(0.0, 1.0, 0.0)) -> None:
    glMultMatrixf(look_at_matrix(eye, center, up))
    glTranslated(-eye[0], -eye[1], -eye[2])
