"""Headless game simulation.

``Game`` owns all mutable state (world, player, UI mode, mini-game and
transfer sessions) and exposes an *action API* (``interact()``,
``toggle_torch()``, ``transfer_confirm()`` ...) plus a per-frame ``update()``.
It imports neither pygame nor OpenGL, so the complete gameplay can be driven
and verified from plain unit tests; the ``input`` package merely translates
pygame events into these calls and the ``rendering`` package only reads from it.
"""
from __future__ import annotations

import random
from enum import Enum
from typing import Optional

from dataclasses import dataclass
from typing import Callable

from .config import DEFAULT_SETTINGS, GameSettings
from .core.messages import MessageLog, stdout_echo
from .entities import Player
from .systems import (ContainerPolicy, InteractionTarget, LockpickMinigame, LockpickOutcome, MoveIntent,
                      MovementResult, NPCAction, PickpocketPolicy, TradePolicy, TransferResult, TransferSession,
                      apply_movement, find_interaction_target, lockpick_tolerance, lockpick_wobble, noise_multiplier,
                      use_station)
from .entities import AIState
from .world import LevelDefinition, SaveManager, World, get_level
from .world.world import Relocation


class GameMode(Enum):
    EXPLORE = "explore"
    TRADE = "trade"            # transfer session with a merchant
    PICKPOCKET = "pickpocket"  # transfer session with a victim's pockets
    CONTAINER = "container"    # transfer session with a shelf / chest
    LOCKPICK = "lockpick"
    CONFIRM = "confirm"        # a yes/no question is on screen


@dataclass
class Confirmation:
    """A question the HUD shows until the player answers (Enter = yes, Esc = no, or a third key)."""
    text: str
    on_yes: Callable[[], None]
    on_no: Optional[Callable[[], None]] = None
    yes_label: str = "[ENTER] Yes"
    no_label: str = "[ESC] No"
    alt_label: Optional[str] = None          # text for the third option, if any
    on_alt: Optional[Callable[[], None]] = None


class ScreenFade:
    """A fade to black and back around a relocation (thrown out of a house, into a cell).

    ``alpha`` is the blackness the HUD draws (0 clear .. 1 black). The pending move is
    applied the moment the screen is fully black, so the player sees where they were,
    the world goes dark, and it comes back where they now are. Input is frozen meanwhile.
    """
    OUT_SECONDS = 0.6
    HOLD_SECONDS = 0.2
    IN_SECONDS = 0.7

    def __init__(self, on_black: Callable[[], None], delay: float = 0.0, out_seconds: Optional[float] = None,
                 hold_seconds: Optional[float] = None, in_seconds: Optional[float] = None, reason: str = "relocation"):
        self.time = 0.0
        self.delay = delay                  # seconds the screen stays clear (and frozen) before fading
        self.on_black = on_black
        self.applied = False
        self.done = False
        self.reason = reason
        if out_seconds is not None:
            self.OUT_SECONDS = out_seconds
        if hold_seconds is not None:
            self.HOLD_SECONDS = hold_seconds
        if in_seconds is not None:
            self.IN_SECONDS = in_seconds

    @property
    def alpha(self) -> float:
        t = self.time - self.delay
        if t <= 0.0:
            return 0.0
        if t < self.OUT_SECONDS:
            return t / self.OUT_SECONDS
        if t < self.OUT_SECONDS + self.HOLD_SECONDS:
            return 1.0
        t -= self.OUT_SECONDS + self.HOLD_SECONDS
        return max(0.0, 1.0 - t / self.IN_SECONDS)

    @property
    def black(self) -> bool:
        return self.time - self.delay >= self.OUT_SECONDS

    def update(self, delta_time: float) -> None:
        self.time += delta_time
        if not self.applied and self.black:
            self.applied = True
            self.on_black()
        if self.time - self.delay >= self.OUT_SECONDS + self.HOLD_SECONDS + self.IN_SECONDS:
            self.done = True


class Game:
    def __init__(self, level: Optional[LevelDefinition] = None, settings: GameSettings = DEFAULT_SETTINGS,
                 save_file: Optional[str] = None, messages: Optional[MessageLog] = None):
        self.settings = settings
        self.messages = messages or MessageLog(settings.max_log_messages,
                                               echo=stdout_echo if settings.echo_messages_to_stdout else None)
        self.world = World(level or get_level("town"), settings, notify_callback=self.messages.add)
        self.player: Player = self.world.spawn_player()
        self.saves = SaveManager(save_file or settings.save_file, notify_callback=self.messages.add)
        self.rng = random.Random(settings.random_seed)
        self.world.rng = self.rng           # one RNG for every gameplay roll (seedable for scripted runs)
        # The lock mini-game draws its sweet spots from a stream of its own so that scripted runs can
        # predict them (the town's idle chatter would otherwise shuffle the world RNG unpredictably).
        self.lockpick_rng = random.Random(settings.random_seed)

        self.lockpicking = LockpickMinigame(settings.lockpick, rng=self.lockpick_rng, rewards=settings.skill_rewards,
                                            progression_settings=settings.progression)
        self.transfer: Optional[TransferSession] = None
        self.transfer_mode: GameMode = GameMode.EXPLORE
        self.target: Optional[InteractionTarget] = None
        self.confirmation: Optional[Confirmation] = None
        self.fade: Optional[ScreenFade] = None
        self.pending_relocations: list = []
        self.world.relocation_handler = self._on_relocation
        self.world.caught_handler = self._on_caught

        self.running = True
        self.movement = MovementResult()
        self.frame_count = 0
        self.inventory_scroll = 0           # first visible row of the inventory panel

        if self.world.level.intro_message:
            self.messages.add(self.world.level.intro_message)

    # ------------------------------------------------------------------ queries
    @property
    def mode(self) -> GameMode:
        if self.confirmation is not None:
            return GameMode.CONFIRM
        if self.lockpicking.active:
            return GameMode.LOCKPICK
        if self.transfer is not None:
            return self.transfer_mode
        return GameMode.EXPLORE

    @property
    def in_transition(self) -> bool:
        """A fade to black is running: the player is frozen until it has played out."""
        return self.fade is not None

    @property
    def frozen(self) -> bool:
        """Controls locked: just caught by a guard (a moment to take it in), or mid-fade."""
        return self.player.frozen or self.fade is not None

    @property
    def fade_alpha(self) -> float:
        return self.fade.alpha if self.fade is not None else 0.0

    @property
    def in_lockpicking(self) -> bool:
        return self.lockpicking.active

    @property
    def in_transfer(self) -> bool:
        return self.transfer is not None

    @property
    def in_trade_menu(self) -> bool:
        return self.transfer is not None and self.transfer_mode is GameMode.TRADE

    @property
    def active_merchant(self):
        return self.transfer.policy.merchant if self.in_trade_menu else None

    @property
    def mouse_captured(self) -> bool:
        """Whether the window should hide+grab the mouse (free look). Released in menus or after quitting."""
        return self.running and self.transfer is None and self.confirmation is None

    @property
    def accepts_free_look(self) -> bool:
        return self.transfer is None and not self.lockpicking.active and self.confirmation is None and not self.frozen

    @property
    def in_explore_mode(self) -> bool:
        return self.mode is GameMode.EXPLORE

    @property
    def interaction_prompt(self) -> Optional[str]:
        return self.target.prompt if self.target else None

    @property
    def ambient_light(self) -> float:
        return self.world.ambient_light

    # ------------------------------------------------------------------ per-frame
    def update(self, delta_time: float, move_intent: MoveIntent = MoveIntent()) -> None:
        """Advance the simulation one frame. Call after all input actions for the frame."""
        self.frame_count += 1
        self.player.update_stance(delta_time)
        self.player.noise_skill_multiplier = noise_multiplier(self.player, self.settings.stealth)
        self.lockpicking.update(delta_time)
        self.player.update_turning(delta_time)
        if self.fade is not None:
            self.fade.update(delta_time)
            if self.fade.done:
                self.fade = None
        if self.accepts_free_look:
            self.movement = apply_movement(self.player, move_intent, delta_time, self.settings.player,
                                           self.world.colliders())
            p = self.player.position
            p.y = self.world.floor_height_at(p.x, p.z, p.y)          # up or down the steps under our feet
        else:
            self.movement = MovementResult()

        self.world.update_time(delta_time)
        self.world.update_npcs(delta_time)
        self.world.update_perception(self.player, self.movement.is_moving, self.movement.is_sprinting, delta_time)
        self.target = find_interaction_target(self.player, self.world.doors, self.world.npcs,
                                              self.settings.interaction, self.world.containers, self.world.walls,
                                              self.world.stations, self.settings,
                                              beds=self.world.beds, may_sleep_in=self.world.player_may_sleep_in)

    # ------------------------------------------------------------------ speech bubbles
    HEAR_RADIUS = 12.0          # how far away talk can be made out
    FACING_DOT = 0.3            # cos(~72 deg): the speaker must be roughly in front of the player

    def speech_bubbles(self):
        """(npc, Speech) for everyone currently talking whom the player can hear - close enough
        and roughly in front of them (you hear people you face, even through a wall). The HUD
        draws these above the speakers' heads; the log keeps every line regardless."""
        from .core.math3d import view_direction
        now = self.world.elapsed
        p = self.player.position
        vx, _, vz = view_direction(self.player.rotation_y, 0.0)
        out = []
        for npc in self.world.npcs:
            speech = npc.current_speech(now)
            if speech is None:
                continue
            dx, dz = npc.position.x - p.x, npc.position.z - p.z
            dist = (dx * dx + dz * dz) ** 0.5
            if dist > self.HEAR_RADIUS:
                continue
            if dist > 1e-6 and (vx * dx + vz * dz) / dist < self.FACING_DOT:
                continue
            out.append((npc, speech))
        return out

    # ------------------------------------------------------------------ relocation & being caught
    def _on_relocation(self, request: Relocation) -> None:
        """The world wants the player somewhere else: fade to black, move them, fade back in.
        Being marched off to jail waits a couple of seconds first so the sentence sinks in."""
        self.close_screens()
        self.pending_relocations.append(request)
        if self.fade is None:
            delay = self.settings.justice.jail_fade_delay if request.reason == "jailed" else 0.0
            self.fade = ScreenFade(self._apply_relocations, delay=delay)
        elif self.fade.applied:
            self._apply_relocations()                  # already black: apply straight away

    def _apply_relocations(self) -> None:
        for request in self.pending_relocations:
            request.apply(self.player)
        self.pending_relocations.clear()
        self.world.push_out_of_doors(self.player)

    def _on_caught(self, npc) -> None:
        """An NPC has the player bang to rights: every mini-game / pocket screen closes (the
        world has already locked the controls and started the turn towards them)."""
        self.close_screens()

    def close_screens(self) -> None:
        """Shut the lockpicking mini-game, any transfer screen and any question."""
        if self.lockpicking.active:
            self.lockpicking.cancel()
        if self.transfer is not None:
            self.close_transfer()
        self.confirmation = None

    # ------------------------------------------------------------------ confirmations
    def ask(self, text: str, on_yes: Callable[[], None], on_no: Optional[Callable[[], None]] = None,
            yes_label: str = "[ENTER] Yes", no_label: str = "[ESC] No",
            alt_label: Optional[str] = None, on_alt: Optional[Callable[[], None]] = None) -> Confirmation:
        self.confirmation = Confirmation(text, on_yes, on_no, yes_label, no_label, alt_label, on_alt)
        return self.confirmation

    def confirm_yes(self) -> bool:
        if self.confirmation is None:
            return False
        question, self.confirmation = self.confirmation, None
        question.on_yes()
        return True

    def confirm_no(self) -> bool:
        if self.confirmation is None:
            return False
        question, self.confirmation = self.confirmation, None
        if question.on_no:
            question.on_no()
        return True

    def confirm_alt(self) -> bool:
        if self.confirmation is None or self.confirmation.on_alt is None:
            return False
        question, self.confirmation = self.confirmation, None
        question.on_alt()
        return True

    # ------------------------------------------------------------------ global actions
    def request_quit(self) -> None:
        self.running = False

    def escape(self) -> bool:
        """ESC: back out of the current screen (a question, the mini-game, a transfer).
        Returns False when there was nothing to back out of - the app then opens its pause menu."""
        if self.confirmation is not None:
            self.confirm_no()
        elif self.lockpicking.active:
            self.lockpicking.cancel()
        elif self.transfer is not None:
            self.close_transfer()
        else:
            return False
        return True

    def look(self, dx_pixels: float, dy_pixels: float) -> None:
        if self.accepts_free_look:
            self.player.look(dx_pixels, dy_pixels)

    # The following world actions are only available while exploring (not inside menus).
    def save_game(self, path: Optional[str] = None) -> bool:
        if not self.in_explore_mode or self.frozen:
            return False
        self.saves.save(self.world, self.player, path)
        return True

    def load_game(self, path: Optional[str] = None) -> bool:
        if not self.in_explore_mode:
            return False
        self.close_screens()
        self.fade = None
        self.player.freeze_timer = 0.0
        self.player.turn_target = None
        self.pending_relocations.clear()
        return self.saves.load(self.world, self.player, path)

    def toggle_torch(self) -> Optional[bool]:
        if not self.in_explore_mode:
            return None
        self.player.has_lit_torch = not self.player.has_lit_torch
        self.messages.add(f"Torch is now {'LIT' if self.player.has_lit_torch else 'EXTINGUISHED'}.")
        return self.player.has_lit_torch

    def toggle_crouch(self) -> Optional[bool]:
        if not self.in_explore_mode:
            return None
        self.player.is_crouching = not self.player.is_crouching
        self.messages.add(f"Stance: {'Crouching' if self.player.is_crouching else 'Standing'}.")
        return self.player.is_crouching

    def wait(self, hours: int = 1) -> bool:
        """[T]: pass an hour standing still (NPCs carry on with their day). A prisoner is
        first asked whether to wait out the whole sentence instead."""
        if self.confirmation is not None and self.confirmation.on_alt is not None:
            return self.confirm_alt()                    # [T] again inside the jail question: just the hour
        if not self.in_explore_mode or self.frozen:
            return False
        jail = self.world.jail
        if jail.sealed and jail.days_left(self.world.day_count) >= 0:
            days = jail.days_left(self.world.day_count)
            self.ask(f"Wait out your sentence ({days} day{'s' if days != 1 else ''} left)?",
                     on_yes=self.wait_out_sentence, on_no=None, yes_label="[ENTER] Serve it all",
                     no_label="[ESC] Cancel", alt_label="[T] Just one hour", on_alt=lambda: self._wait_hours(1))
            return True
        return self._wait_hours(hours)

    def _wait_hours(self, hours: int) -> bool:
        self.messages.add(f"You wait for {hours} hour{'s' if hours != 1 else ''}...")
        self.world.wait_hours(hours)
        self.update(0.0)
        return True

    def wait_out_sentence(self, max_hours: int = 24 * 15) -> int:
        """Pass time hour by hour until the prisoner is released (or breaks out). Returns hours waited."""
        self.messages.add("You settle down to wait out your sentence...")
        waited = 0
        while self.world.jail.sealed and waited < max_hours:
            self.world.wait_hours(1)
            waited += 1
        self.update(0.0)
        return waited

    def report_crime(self, crime_name: str):
        """Let the NPCs try to witness a crime the player is committing right now. Returns the witnesses."""
        return self.world.report_crime_to_witnesses(crime_name, self.player.position)

    # ------------------------------------------------------------------ interaction
    def interact(self) -> None:
        """[E]: close an open menu, otherwise act on the current target.
        Ignored during the lockpicking mini-game."""
        if self.transfer is not None:
            self.close_transfer()
            return
        if self.lockpicking.active or self.confirmation is not None or self.frozen or self.target is None:
            return
        if self.target.is_door:
            self._interact_door(self.target.obj)
        elif self.target.is_container:
            self._interact_container(self.target.obj)
        elif self.target.is_station:
            use_station(self.player, self.target.obj, self.settings, self.messages.add, rng=self.rng)
        elif self.target.is_npc:
            self._interact_npc(self.target.obj, self.target.npc_action)
        elif self.target.is_bed:
            self.sleep_until_morning(self.target.obj)

    # ------------------------------------------------------------------ sleeping
    WAKE_HOUR = 6

    def sleep_until_morning(self, bed=None) -> bool:
        """Sleep in a bed that is the player's (their own, or the room they are renting): the
        screen fades slowly to black, the night passes (the town lives on), and it is 06:00
        when it comes back. The same for every bed the player may use."""
        if bed is not None and not self.world.player_may_sleep_in(bed):
            self.messages.add("That is not your bed.")
            return False
        if self.fade is not None:
            return False
        self.close_screens()
        self.messages.add("You settle down to sleep...")
        self.fade = ScreenFade(self._sleep_through_the_night, out_seconds=1.8, hold_seconds=0.8, in_seconds=1.4, reason="sleep")
        return True

    def hours_until_morning(self) -> float:
        hours = (self.WAKE_HOUR - self.world.clock.fractional_hour) % 24.0
        return hours if hours > 0.05 else 24.0

    def _sleep_through_the_night(self) -> None:
        self.world.wait_until(self.WAKE_HOUR)
        self.messages.add(f"You wake at {self.world.clock.hour:02d}:00, rested.")

    def _interact_container(self, container) -> None:
        if not getattr(container, "is_locked", False):
            self.open_container(container)
        elif container.key_id and self.player.has_key_for(container.key_id):
            container.unlock_and_open()
            self.messages.add(f"Unlocked the {container.label.lower()} with your key.")
        elif self.player.is_crouching and self.player.has_lockpick():
            self._begin_lockpicking(container, f"Started lockpicking the {container.label.lower()} "
                                               f"(lock difficulty {container.lock_difficulty}).", "Lockpicking a lockbox")
        elif self.player.is_crouching:
            self.messages.add(f"The {container.label.lower()} is locked! You need a key or a lockpick.")
        else:
            self.messages.add(f"The {container.label.lower()} is locked. Crouch to pick it, or find the key.")

    def _begin_lockpicking(self, lockable, message: str, crime: str) -> None:
        tolerance = lockpick_tolerance(self.player, lockable.lock_difficulty, self.settings.stealth)
        wobble = lockpick_wobble(self.player, lockable.lock_difficulty, self.settings.stealth)
        self.lockpicking.begin(lockable, tolerance=tolerance, fail_xp=self.settings.skill_rewards.lockpicking_fail,
                               wobble=wobble)
        self.report_crime(crime)
        self.messages.add(message)

    def _interact_door(self, door) -> None:
        if not door.is_locked:
            door.toggle()
            self.world.push_out_of_doors(self.player)
        elif self.player.has_key_for(door.door_id):
            door.is_locked = False
            self.messages.add("Unlocked the door with your key.")
        elif self.player.is_crouching and self.player.has_lockpick():
            self._begin_lockpicking(door, f"Started lockpicking mini-game on door (lock difficulty {door.lock_difficulty}).",
                                    "Lockpicking a door")
        elif self.player.is_crouching:
            self.messages.add("Door is locked! You need a key or a lockpick.")
        else:
            self.messages.add("Door is locked. Crouch to pick it, or find the key.")

    def _interact_npc(self, npc, action: Optional[NPCAction]) -> None:
        if action is NPCAction.PICKPOCKET:
            self.open_pickpocket(npc)
        elif action is NPCAction.TOO_FAR_TO_PICKPOCKET:
            self.messages.add(f"Sneak closer to pick {npc.name}'s pockets.")
        else:
            if not npc.is_asleep:
                npc.turn_towards(self.player.position)
            npc.interact(notify_callback=self.messages.add, hour=self.world.simulated_hour)
            if action is NPCAction.TRADE:
                self.open_trade(npc)

    # ------------------------------------------------------------------ transfer sessions
    def open_trade(self, merchant) -> TransferSession:
        policy = TradePolicy(merchant, self.player, self.settings.economy, notify=self.messages.add,
                             rewards=self.settings.skill_rewards, progression_settings=self.settings.progression,
                             on_service=self._buy_service, on_refused_stolen=self._merchant_reports_fencing)
        return self._open_transfer(self.world.merchant_stock(merchant), policy, GameMode.TRADE)

    def _merchant_reports_fencing(self, merchant) -> None:
        """An honest merchant offered stolen goods shouts for the guards: they come running and
        hold it against you (a reported crime - only the merchant saw it)."""
        self.world.declare_crime("Fencing stolen goods", self.player.position.copy(), witnessed=False, reporter=merchant.name)

    def _buy_service(self, item) -> bool:
        """Service items in a merchant's stock: a room at the inn for a night or a week."""
        from .world.inn import RENT_ITEMS
        nights = RENT_ITEMS.get(item.id)
        if nights is None or not self.world.inn.present:
            return False
        return self.world.inn.rent(self.world, self.player, nights, self.messages.add)

    def open_pickpocket(self, victim) -> TransferSession:
        """Opening the pockets is itself a crime bystanders may witness."""
        self.report_crime("Pickpocketing")
        policy = PickpocketPolicy(victim, self.player, self.settings.skill_rewards, notify=self.messages.add,
                                  report_crime=self.report_crime, rng=self.rng, stealth=self.settings.stealth,
                                  on_caught=self._pickpocket_caught, economy=self.settings.economy,
                                  progression_settings=self.settings.progression)
        return self._open_transfer(victim.inventory, policy, GameMode.PICKPOCKET)

    def _pickpocket_caught(self, victim) -> None:
        """A fumbled pickpocket: the victim wakes up, throws the player out of their place and raises the alarm."""
        if victim.is_asleep:
            victim.state = AIState.INVESTIGATING
            self.messages.add(f"({victim.name} woke up!): \"Hey! Get your hands off me!\"")
        self.world.player_caught(victim)
        area = self.world.area_of(victim.position)
        if area == self.world.area_of(self.player.position) and area != self.world.level.default_area:
            self.world.throw_out(self.player, area, by=victim,
                                 line=f"({victim.name}): \"Out! Get out of {area}!\" You are thrown out.")
        victim.raise_alarm(self.messages.add,
                           f"({victim.title}): \"A thief! Hands where I can see them!\"",
                           f"({victim.title}): \"Thief! Guards, a pickpocket!\"")
        self.report_crime("Pickpocketing")

    def open_container(self, container) -> TransferSession:
        policy = ContainerPolicy(container, self.player, notify=self.messages.add, report_crime=self.report_crime,
                                 rewards=self.settings.skill_rewards, stealth=self.settings.stealth, rng=self.rng,
                                 progression_settings=self.settings.progression,
                                 complimentary=lambda item: self.world.is_complimentary(container, item),
                                 on_complimentary=lambda item: self.world.note_complimentary(container, item))
        return self._open_transfer(container.inventory, policy, GameMode.CONTAINER)

    def _open_transfer(self, left_items, policy, mode: GameMode) -> TransferSession:
        self.transfer = TransferSession(left_items, self.player.inventory, policy)
        self.transfer_mode = mode
        return self.transfer

    def close_transfer(self) -> None:
        self.transfer = None
        self.transfer_mode = GameMode.EXPLORE

    def transfer_switch_side(self) -> None:
        if self.transfer:
            self.transfer.switch_side()

    def transfer_select_previous(self) -> None:
        if self.transfer:
            self.transfer.move_selection(-1)

    def transfer_select_next(self) -> None:
        if self.transfer:
            self.transfer.move_selection(+1)

    # Up/Down: move the menu cursor inside a transfer screen, scroll the inventory panel otherwise.
    def cursor_up(self) -> None:
        if self.transfer:
            self.transfer.move_selection(-1)
        elif self.in_explore_mode:
            self.scroll_inventory(-1)

    def cursor_down(self) -> None:
        if self.transfer:
            self.transfer.move_selection(+1)
        elif self.in_explore_mode:
            self.scroll_inventory(+1)

    def scroll_inventory(self, delta: int) -> int:
        rows = self.settings.hud_layout().max_inventory_rows
        max_scroll = max(0, len(self.player.inventory) - rows)
        self.inventory_scroll = max(0, min(max_scroll, self.inventory_scroll + delta))
        return self.inventory_scroll

    def visible_inventory(self):
        """(first row index, items shown) for the inventory panel, clamped to the current inventory size."""
        rows = self.settings.hud_layout().max_inventory_rows
        max_scroll = max(0, len(self.player.inventory) - rows)
        self.inventory_scroll = min(self.inventory_scroll, max_scroll)
        return self.inventory_scroll, self.player.inventory[self.inventory_scroll:self.inventory_scroll + rows]

    def transfer_confirm(self) -> Optional[TransferResult]:
        if self.confirmation is not None:
            self.confirm_yes()
            return None
        if not self.transfer:
            return None
        result = self.transfer.confirm()
        if result.close_session:
            self.close_transfer()
        return result

    # ------------------------------------------------------------------ lockpicking
    def lockpick_rotate(self, steps: int) -> None:
        if self.lockpicking.active:
            self.lockpicking.rotate(steps)

    def lockpick_attempt(self) -> Optional[LockpickOutcome]:
        if not self.lockpicking.active:
            return None
        return self.lockpicking.attempt(self.player, notify=self.messages.add)

    # ------------------------------------------------------------------ debugging aid
    def snapshot(self) -> dict:
        """Plain-data view of the full game state (used by tests and tooling)."""
        p = self.player
        return {
            "frame": self.frame_count,
            "running": self.running,
            "mode": self.mode.value,
            "hour": self.world.simulated_hour,
            "minute_accumulator": round(self.world.clock.minute_accumulator, 9),
            "player": {
                "pos": (round(p.position.x, 9), round(p.position.y, 9), round(p.position.z, 9)),
                "yaw": round(p.rotation_y, 9), "pitch": round(p.rotation_x, 9),
                "eye": round(p.current_eye_height, 6),
                "gold": round(p.gold, 9), "torch": p.has_lit_torch, "crouch": p.is_crouching,
                "inventory": [(i.id, i.quantity, i.is_stolen) for i in p.inventory],
                "skills": {k.value: dict(v) for k, v in p.skills.skills.items()},
                "crimes_witnessed": p.crimes_witnessed,
            },
            "npcs": [{"name": n.name, "state": n.state.name, "suspicion": round(n.suspicion_meter, 9),
                      "torch": n.has_torch, "inventory": [(i.id, i.quantity) for i in n.inventory], "gold": round(n.gold, 6),
                      "pos": (round(n.position.x, 6), round(n.position.y, 6), round(n.position.z, 6)),
                      "waypoints": len(n.path), "crimes": n.crimes_witnessed} for n in self.world.npcs],
            "doors": [{"id": d.door_id, "locked": d.is_locked, "open": d.is_open, "sealed": d.sealed} for d in self.world.doors],
            "containers": [{"name": c.name, "locked": c.is_locked, "inventory": [(i.id, i.quantity) for i in c.inventory]}
                           for c in self.world.containers],
            "jail": self.world.jail.to_dict(),
            "transfer": {"mode": self.transfer_mode.value, "side": self.transfer.side.value,
                         "selection": dict((s.value, v) for s, v in self.transfer.selection.items()),
                         "title": self.transfer.policy.title} if self.transfer else None,
            "lockpick": {"angle": self.lockpicking.pick_angle, "sweet_spot": self.lockpicking.sweet_spot,
                         "target": self.lockpicking.target_id},
            "confirmation": self.confirmation.text if self.confirmation else None,
            "fade": round(self.fade_alpha, 3),
            "frozen": self.frozen,
            "prompt": self.interaction_prompt,
            "messages": self.messages.messages,
            "moving": self.movement.is_moving, "sprinting": self.movement.is_sprinting,
            "mouse_captured": self.mouse_captured,
        }
