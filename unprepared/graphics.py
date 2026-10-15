"""User-adjustable graphics settings with High/Medium/Low presets.

Unlike :mod:`unprepared.config` (frozen tuning constants) these are *mutable*
and persisted to ``graphics.json`` next to the save file. The renderer reads
them every frame, so the options menu can change them live.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from typing import Dict, Optional

PRESETS: Dict[str, dict] = {
    "high": dict(shaders=True, mipmaps=True, stars=True, sky_bodies=True, star_count=400, ground_cells=20,
                 object_fade=1.0, character_fade=1.0, torch_lights=8, roofs=True),
    "medium": dict(shaders=True, mipmaps=True, stars=True, sky_bodies=True, star_count=160, ground_cells=10,
                   object_fade=0.7, character_fade=0.8, torch_lights=4, roofs=True),
    "low": dict(shaders=False, mipmaps=False, stars=False, sky_bodies=True, star_count=0, ground_cells=4,
                object_fade=0.45, character_fade=0.6, torch_lights=2, roofs=True),
}
QUALITY_ORDER = ("low", "medium", "high")


@dataclass
class GraphicsSettings:
    quality: str = "high"
    auto_quality: bool = True           # pick the preset from a start-up benchmark
    fov: float = 60.0                   # vertical field of view, degrees
    object_fade: float = 1.0            # fraction of the far plane beyond which world objects are not drawn
    character_fade: float = 1.0         # same for NPCs
    contrast: float = 1.0
    shaders: bool = True
    mipmaps: bool = True
    stars: bool = True
    sky_bodies: bool = True
    star_count: int = 400
    ground_cells: int = 20
    torch_lights: int = 8
    roofs: bool = True
    show_perf_overlay: bool = False
    detected_renderer: str = ""
    benchmark_ms: float = 0.0
    _version: int = field(default=1, repr=False)

    # --- presets ---------------------------------------------------------------
    def apply_preset(self, name: str) -> None:
        for key, value in PRESETS[name].items():
            setattr(self, key, value)
        self.quality = name

    def next_quality(self, step: int = 1) -> str:
        idx = (QUALITY_ORDER.index(self.quality) + step) % len(QUALITY_ORDER)
        self.apply_preset(QUALITY_ORDER[idx])
        self.auto_quality = False
        return self.quality

    # --- derived -----------------------------------------------------------------
    def object_draw_distance(self, far_plane: float) -> float:
        return far_plane * max(0.1, min(1.0, self.object_fade))

    def character_draw_distance(self, far_plane: float) -> float:
        return far_plane * max(0.1, min(1.0, self.character_fade))

    # --- persistence -------------------------------------------------------------
    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if not k.startswith("_")}

    @classmethod
    def from_dict(cls, data: dict) -> "GraphicsSettings":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known and not k.startswith("_")})

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> Optional["GraphicsSettings"]:
        if not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                return cls.from_dict(json.load(f))
        except (OSError, ValueError, TypeError):
            return None


def graphics_settings_path(save_file: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(save_file)) or ".", "graphics.json")
