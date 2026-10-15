"""How every skill grows and pays out - one rule for all of them.

* **Rewards shrink with level.** ``xp_reward(level, base, magnitude)`` is
  ``base * magnitude / (1 + level_decay * (level - 1))``: a fresh character is
  showered with XP and an elite one grinds for scraps. ``magnitude`` carries
  what the deed was worth - the value of the item lifted, the difficulty of the
  lock, whether the victim was awake.
* **Odds climb smoothly.** ``success_chance(level, base)`` is
  ``1 - (1 - base) * chance_decay ** (level - 1)``: it never reaches 1 but an
  elite (50+) thief is near enough invisible, infallible and unstoppable.
* **Value teaches.** ``value_xp(gold)`` turns an item's worth into a reward
  magnitude (capped, with a sliver for junk).

Used by sneaking, pickpocketing, stealing, lockpicking, bartering and smithing.
"""
from __future__ import annotations

from ..config import ProgressionSettings
from ..entities import Player, SkillType

DEFAULT = ProgressionSettings()


def level_factor(level: int, s: ProgressionSettings = DEFAULT) -> float:
    return 1.0 / (1.0 + s.level_decay * (max(1, level) - 1))


def xp_reward(level: int, base: float, magnitude: float = 1.0, s: ProgressionSettings = DEFAULT) -> float:
    return max(0.0, base * magnitude) * level_factor(level, s)


def success_chance(level: int, base_chance: float, s: ProgressionSettings = DEFAULT) -> float:
    base = max(s.chance_floor, min(s.chance_ceiling, base_chance))
    chance = 1.0 - (1.0 - base) * (s.chance_decay ** (max(1, level) - 1))
    return max(s.chance_floor, min(s.chance_ceiling, chance))


def value_xp(value: float, s: ProgressionSettings = DEFAULT) -> float:
    """Reward (before the level factor) for handling an item worth ``value`` gold."""
    return max(s.value_xp_floor, min(s.value_xp_cap, max(0.0, value) * s.value_xp_rate))


def grant(player: Player, skill: SkillType, base: float, magnitude: float = 1.0, notify=None,
          s: ProgressionSettings = DEFAULT) -> float:
    """Give the player the level-scaled reward for ``skill``; returns the XP actually granted."""
    amount = xp_reward(player.skills.level(skill), base, magnitude, s)
    if amount > 0:
        player.skills.add_xp(skill, amount, notify_callback=notify)
    return amount


def scaled_yield(level: int, low: int, high: int, max_level: int) -> int:
    """Linear ramp from ``low`` at level 1 to ``high`` at ``max_level`` (and beyond)."""
    if max_level <= 1:
        return high
    t = max(0.0, min(1.0, (max(1, level) - 1) / (max_level - 1)))
    return int(low + (high - low) * t + 1e-9)
