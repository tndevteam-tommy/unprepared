"""Skill checks that scale with the player's level: sneaking, pickpocketing, stealing, lockpicking.

Every check is a roll against a chance from :mod:`progression` (``success_chance``):
a base chance at level 1 that climbs towards certainty with every level. The RNG
is injected so scripted runs stay deterministic.
"""
from __future__ import annotations

import random

from ..config import ProgressionSettings, StealthSettings
from ..entities import NPC, Player, SkillType
from .progression import DEFAULT as DEFAULT_PROGRESSION
from .progression import success_chance


def clamp(x: float, lo: float = 0.05, hi: float = 0.98) -> float:
    return max(lo, min(hi, x))


def sneak_chance(player: Player, npc: NPC, s: StealthSettings, visibility: float = 0.0,
                 p: ProgressionSettings = DEFAULT_PROGRESSION) -> float:
    """Odds one sneak roll keeps the player out of ``npc``'s mind. Guards are sharper and
    daylight (``visibility``) hurts - but an elite sneak is nearly invisible at noon in front of a guard."""
    level = player.skills.level(SkillType.SNEAK)
    base = s.sneak_base_chance - (s.sneak_guard_penalty if npc.is_guard else 0.0) \
        - s.sneak_daylight_penalty * max(0.0, min(1.0, visibility))
    return success_chance(level, base, p)


def pickpocket_chance(player: Player, victim: NPC, s: StealthSettings,
                      p: ProgressionSettings = DEFAULT_PROGRESSION) -> float:
    level = player.skills.level(SkillType.PICKPOCKET)
    base = s.pickpocket_base_chance
    if victim.is_asleep:
        base += s.pickpocket_asleep_bonus
    if victim.is_guard:
        base -= s.pickpocket_guard_penalty
    return success_chance(level, base, p)


def stealing_chance(player: Player, s: StealthSettings, p: ProgressionSettings = DEFAULT_PROGRESSION) -> float:
    """Odds that lifting something from a shelf in plain view goes unnoticed."""
    return success_chance(player.skills.level(SkillType.STEALING), s.stealing_base_chance, p)


def lockpick_tolerance(player: Player, lock_difficulty: int, s: StealthSettings) -> float:
    level = player.skills.level(SkillType.LOCKPICKING)
    tolerance = s.lockpick_base_tolerance * (1.0 + s.lockpick_per_level * (level - 1)) / max(1, lock_difficulty)
    return max(s.lockpick_min_tolerance, min(s.lockpick_max_tolerance, tolerance))


def lockpick_wobble(player: Player, lock_difficulty: int, s: StealthSettings) -> float:
    """Degrees the pick wanders: unsteady at low skill, steady hands at high skill."""
    level = player.skills.level(SkillType.LOCKPICKING)
    return max(0.0, (s.lockpick_wobble_base + s.lockpick_wobble_per_difficulty * (lock_difficulty - 1))
               - s.lockpick_wobble_per_level * (level - 1))


def noise_multiplier(player: Player, s: StealthSettings) -> float:
    """Sneak skill makes the player quieter."""
    level = player.skills.level(SkillType.SNEAK)
    return max(0.3, 1.0 - s.sneak_noise_per_level * (level - 1))


def roll(rng: random.Random, chance: float) -> bool:
    return rng.random() < chance
