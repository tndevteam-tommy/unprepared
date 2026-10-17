"""What the townsfolk wear.

An :class:`Outfit` is plain data the renderer dresses an NPC model with: a tinted
tunic and legs, an optional apron (cloth for the innkeeper, leather for the
smith), something on the head (the watch's iron helmet, a cap, a scarf, a hood)
and an optional sash. Level data may give an NPC an explicit outfit; otherwise
:func:`outfit_for` picks one from the person's role, with the colours varied per
name so no two neighbours dress alike.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import Optional, Tuple

Color = Tuple[float, float, float]

APRON_KINDS = ("cloth", "leather")
HAT_KINDS = ("helmet", "cap", "scarf", "hood", "coif")


@dataclass(frozen=True)
class Outfit:
    tunic: Color = (0.55, 0.45, 0.7)        # tint over the woven cloth texture
    legs: Color = (0.35, 0.30, 0.28)
    armor: bool = False                     # a steel breastplate (the watch's uniform) instead of a tunic
    apron: Optional[str] = None             # "cloth" | "leather"
    hat: Optional[str] = None               # "helmet" | "cap" | "scarf" | "hood" | "coif"
    hat_color: Color = (0.35, 0.3, 0.25)
    sash: Optional[Color] = None            # a band across the chest (a merchant's finery)
    hair: Color = (0.31, 0.2, 0.1)

    def __post_init__(self):
        if self.apron is not None and self.apron not in APRON_KINDS:
            raise ValueError(f"unknown apron {self.apron!r}")
        if self.hat is not None and self.hat not in HAT_KINDS:
            raise ValueError(f"unknown hat {self.hat!r}")


# A small wardrobe of dyes: wool and linen in the colours a town like this can afford.
DYES: Tuple[Color, ...] = (
    (0.55, 0.45, 0.70), (0.62, 0.30, 0.28), (0.30, 0.45, 0.62), (0.42, 0.55, 0.35), (0.70, 0.60, 0.40),
    (0.50, 0.38, 0.30), (0.35, 0.35, 0.45), (0.72, 0.52, 0.55), (0.46, 0.58, 0.58), (0.60, 0.50, 0.25),
)
HAIRS: Tuple[Color, ...] = ((0.31, 0.2, 0.1), (0.12, 0.1, 0.08), (0.6, 0.45, 0.2), (0.55, 0.55, 0.55), (0.45, 0.25, 0.12))
LEG_CLOTHS: Tuple[Color, ...] = ((0.35, 0.30, 0.28), (0.28, 0.28, 0.33), (0.42, 0.35, 0.25), (0.25, 0.22, 0.2))

GUARD_UNIFORM = Outfit(tunic=(0.8, 0.22, 0.2), legs=(0.25, 0.25, 0.3), armor=True, hat="helmet", hat_color=(0.6, 0.62, 0.66))


def _pick(options, key: str, salt: int = 0):
    return options[(zlib.crc32(key.encode("utf-8")) + salt) % len(options)]


def outfit_for(name: str, role: str = "", is_guard: bool = False) -> Outfit:
    """A fitting outfit for the role, with colours chosen by name (stable across runs)."""
    if is_guard or role in ("guard", "jailer"):
        return GUARD_UNIFORM
    tunic, legs, hair = _pick(DYES, name), _pick(LEG_CLOTHS, name, 3), _pick(HAIRS, name, 5)
    if role == "innkeeper":
        return Outfit(tunic=tunic, legs=legs, apron="cloth", hat="coif", hat_color=(0.92, 0.9, 0.85), hair=hair)
    if role == "smith":
        return Outfit(tunic=(0.45, 0.4, 0.38), legs=(0.3, 0.27, 0.25), apron="leather", hair=hair)
    if role == "shopkeeper":
        return Outfit(tunic=tunic, legs=legs, sash=(0.85, 0.7, 0.25), hat="cap", hat_color=_pick(DYES, name, 7), hair=hair)
    if role == "tailor":
        return Outfit(tunic=(0.72, 0.52, 0.55), legs=(0.33, 0.3, 0.4), sash=(0.3, 0.45, 0.62), hair=hair)
    if role == "fence":
        return Outfit(tunic=(0.22, 0.2, 0.24), legs=(0.18, 0.17, 0.2), hat="hood", hat_color=(0.2, 0.18, 0.22), hair=hair)
    if role == "widow":
        return Outfit(tunic=(0.25, 0.22, 0.28), legs=(0.2, 0.18, 0.2), hat="scarf", hat_color=(0.2, 0.2, 0.24), hair=hair)
    if role == "elder":
        return Outfit(tunic=tunic, legs=legs, hat="cap", hat_color=(0.4, 0.33, 0.25), hair=(0.75, 0.75, 0.75))
    if role == "cook":
        return Outfit(tunic=tunic, legs=legs, apron="cloth", hat="scarf", hat_color=(0.85, 0.8, 0.7), hair=hair)
    if role == "porter":
        return Outfit(tunic=(0.5, 0.38, 0.3), legs=legs, apron="leather", hair=hair)
    return Outfit(tunic=tunic, legs=legs, hair=hair)
