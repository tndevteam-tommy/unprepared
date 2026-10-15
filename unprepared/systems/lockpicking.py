"""Rotate-the-pick lockpicking mini-game."""
from __future__ import annotations

import math
import random
from enum import Enum
from typing import Callable, Optional

from ..config import LockpickSettings, ProgressionSettings, SkillRewards
from ..entities import Player, SkillType
from . import progression

Notify = Optional[Callable[[str], None]]


class LockpickOutcome(Enum):
    SUCCESS = "success"
    SNAPPED = "snapped"          # pick broke; another one is ready
    OUT_OF_PICKS = "out_of_picks"  # pick broke and it was the last one: mini-game ends


class LockpickMinigame:
    """Holds the pick angle and the current target.

    Every attempt starts with the pick at 0 degrees and (by default) a fresh
    random sweet spot drawn from the supplied RNG, so each lock feels different
    and the player has to search for it.
    """

    def __init__(self, settings: LockpickSettings, rng: Optional[random.Random] = None,
                 rewards: Optional[SkillRewards] = None, progression_settings: Optional[ProgressionSettings] = None):
        self.settings = settings
        self.rng = rng or random.Random()
        self.rewards = rewards
        self.progression = progression_settings or ProgressionSettings()
        self.pick_angle = 0.0
        self.sweet_spot = settings.default_sweet_spot
        self.tolerance = settings.success_tolerance_degrees
        self.fail_xp = 0.0
        self.target = None              # anything lockable: a Door or a locked Container
        self.active = False
        self.wobble_amplitude = 0.0     # degrees the pick wanders either side (shrinks with skill)
        self.wobble_speed = 6.0         # radians per second
        self.time = 0.0

    def begin(self, door, sweet_spot: Optional[float] = None, tolerance: Optional[float] = None,
              fail_xp: float = 0.0, wobble: float = 0.0) -> None:
        """Start picking ``door`` (or any lockable with ``lock_difficulty`` and ``unlock_and_open()``).
        ``tolerance`` (degrees either side of the sweet spot) and ``wobble`` (how far an unsteady
        hand wanders) come from the player's skill vs the lock's difficulty."""
        self.target = door
        self.active = True
        self.tolerance = tolerance if tolerance is not None else self.settings.success_tolerance_degrees
        self.fail_xp = fail_xp
        self.wobble_amplitude = wobble
        self.time = 0.0
        if self.settings.reset_pick_each_attempt:
            self.pick_angle = 0.0
        if sweet_spot is not None:
            self.sweet_spot = sweet_spot
        elif self.settings.random_sweet_spot:
            self.sweet_spot = self.rng.uniform(0.0, 360.0)
        else:
            self.sweet_spot = self.settings.default_sweet_spot

    def cancel(self) -> None:
        self.active = False

    def rotate(self, steps: int) -> float:
        self.pick_angle = (self.pick_angle + steps * self.settings.rotate_step_degrees) % 360.0
        return self.pick_angle

    def update(self, delta_time: float) -> None:
        if self.active:
            self.time += delta_time

    @property
    def wobble(self) -> float:
        """Current offset of the unsteady pick (degrees); zero for a steady hand."""
        if self.wobble_amplitude <= 0.0:
            return 0.0
        t = self.time * self.wobble_speed
        return self.wobble_amplitude * (0.7 * math.sin(t) + 0.3 * math.sin(t * 2.3))

    @property
    def effective_angle(self) -> float:
        """Where the pick actually is right now - this is what [SPACE] tests against the sweet spot."""
        return (self.pick_angle + self.wobble) % 360.0

    @property
    def angle_error(self) -> float:
        diff = abs(self.effective_angle - self.sweet_spot) % 360.0
        return min(diff, 360.0 - diff)

    @property
    def is_aligned(self) -> bool:
        return self.angle_error <= self.tolerance

    @property
    def difficulty(self) -> int:
        return getattr(self.target, "lock_difficulty", 1) if self.target is not None else 1

    @property
    def target_id(self) -> Optional[str]:
        if self.target is None:
            return None
        return getattr(self.target, "door_id", None) or getattr(self.target, "lock_id", None)

    def _reward(self, player: Player, base: float, notify: Notify) -> None:
        if self.rewards is not None:
            progression.grant(player, SkillType.LOCKPICKING, base, notify=notify, s=self.progression)
        else:
            player.skills.add_xp(SkillType.LOCKPICKING, base, notify_callback=notify)

    def attempt(self, player: Player, notify: Notify = None) -> LockpickOutcome:
        if self.is_aligned:
            if self.target is not None:
                self.target.unlock_and_open()
            if notify:
                notify("SUCCESS! Lock successfully bypassed!")
            base = (self.rewards.lockpicking if self.rewards is not None else self.settings.xp_reward) * self.difficulty
            self._reward(player, base, notify)
            self.active = False
            return LockpickOutcome.SUCCESS
        # A miss snaps the pick and ends the attempt: crouch up to the door and try again.
        if self.settings.consume_pick_on_snap:
            player.take_lockpick()
        self.active = False
        if notify:
            notify("SNAP! Your lockpick broke against the mechanism. Try again.")
        if self.fail_xp:
            self._reward(player, self.fail_xp, notify)
        if self.settings.consume_pick_on_snap and not player.has_lockpick():
            if notify:
                notify("That was your last lockpick. Forge more at the anvil.")
            return LockpickOutcome.OUT_OF_PICKS
        return LockpickOutcome.SNAPPED
