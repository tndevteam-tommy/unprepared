"""Minimal 3D math used by the simulation and renderer (no numpy dependency)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class Vector3D:
    x: float
    y: float
    z: float

    def distance_to(self, other: "Vector3D") -> float:
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2 + (self.z - other.z) ** 2)

    def copy(self) -> "Vector3D":
        return Vector3D(self.x, self.y, self.z)

    def offset(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> "Vector3D":
        return Vector3D(self.x + dx, self.y + dy, self.z + dz)

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "z": self.z}

    @staticmethod
    def from_dict(d: dict) -> "Vector3D":
        return Vector3D(d["x"], d["y"], d["z"])


@dataclass
class BoundingBox3D:
    min_point: Vector3D
    max_point: Vector3D

    def intersects(self, other: "BoundingBox3D") -> bool:
        return (
            self.min_point.x <= other.max_point.x and self.max_point.x >= other.min_point.x and
            self.min_point.y <= other.max_point.y and self.max_point.y >= other.min_point.y and
            self.min_point.z <= other.max_point.z and self.max_point.z >= other.min_point.z
        )

    @property
    def center(self) -> Vector3D:
        return Vector3D((self.min_point.x + self.max_point.x) / 2, (self.min_point.y + self.max_point.y) / 2,
                        (self.min_point.z + self.max_point.z) / 2)

    @staticmethod
    def around(center: Vector3D, half_x: float, height: float, half_z: float, base_y: float = 0.0) -> "BoundingBox3D":
        """Box centred on ``center`` in X/Z and standing on ``center.y + base_y``."""
        return BoundingBox3D(
            Vector3D(center.x - half_x, center.y + base_y, center.z - half_z),
            Vector3D(center.x + half_x, center.y + base_y + height, center.z + half_z),
        )


def ray_intersects_box(ray_origin: Vector3D, ray_target: Vector3D, box: BoundingBox3D) -> bool:
    """Segment/AABB slab test: True if the segment origin->target crosses ``box``."""
    dir_x = ray_target.x - ray_origin.x
    dir_y = ray_target.y - ray_origin.y
    dir_z = ray_target.z - ray_origin.z
    tmin, tmax = 0.0, 1.0

    for origin, d, bmin, bmax in (
        (ray_origin.x, dir_x, box.min_point.x, box.max_point.x),
        (ray_origin.y, dir_y, box.min_point.y, box.max_point.y),
        (ray_origin.z, dir_z, box.min_point.z, box.max_point.z),
    ):
        if abs(d) < 1e-6:
            if origin < bmin or origin > bmax:
                return False
        else:
            ood = 1.0 / d
            t1 = (bmin - origin) * ood
            t2 = (bmax - origin) * ood
            if t1 > t2:
                t1, t2 = t2, t1
            if t1 > tmin:
                tmin = t1
            if t2 < tmax:
                tmax = t2
            if tmin > tmax:
                return False
    return tmax >= tmin and tmin <= 1.0 and tmax >= 0.0


def ray_box_distance(origin: Vector3D, direction: Tuple[float, float, float], box: BoundingBox3D,
                     max_distance: float = float("inf")) -> Optional[float]:
    """Distance along the (unit) ``direction`` from ``origin`` to the first point inside ``box``,
    or None if the ray misses it within ``max_distance``. An origin already inside returns 0."""
    tmin, tmax = 0.0, max_distance
    for o, d, bmin, bmax in ((origin.x, direction[0], box.min_point.x, box.max_point.x),
                             (origin.y, direction[1], box.min_point.y, box.max_point.y),
                             (origin.z, direction[2], box.min_point.z, box.max_point.z)):
        if abs(d) < 1e-9:
            if o < bmin or o > bmax:
                return None
            continue
        t1, t2 = (bmin - o) / d, (bmax - o) / d
        if t1 > t2:
            t1, t2 = t2, t1
        tmin, tmax = max(tmin, t1), min(tmax, t2)
        if tmin > tmax:
            return None
    return tmin


def view_direction(yaw_degrees: float, pitch_degrees: float) -> Tuple[float, float, float]:
    """Unit vector the camera looks along for the given yaw (Y axis) and pitch."""
    yaw = math.radians(yaw_degrees)
    pitch = math.radians(pitch_degrees)
    return (
        math.cos(pitch) * math.sin(yaw),
        math.sin(pitch),
        -math.cos(pitch) * math.cos(yaw),
    )


def yaw_basis(yaw_degrees: float) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """Ground-plane (x, z) forward and right vectors for a yaw angle."""
    yaw = math.radians(yaw_degrees)
    forward = (math.sin(yaw), -math.cos(yaw))
    right = (math.cos(yaw), math.sin(yaw))
    return forward, right


def normalized(x: float, y: float, z: float) -> Tuple[float, float, float, float]:
    """Return (nx, ny, nz, magnitude); the vector is left untouched if magnitude is 0."""
    mag = math.sqrt(x * x + y * y + z * z)
    if mag > 0:
        return x / mag, y / mag, z / mag, mag
    return x, y, z, mag
