"""Translate pygame events and key state into ``Game`` actions.

Mode gating (e.g. ignoring mouse-look while trading) lives in ``Game`` itself so
it is covered by the headless tests; this layer stays a thin mapping.
"""
from __future__ import annotations

import pygame

from ..game import Game
from ..systems import MoveIntent
from .bindings import DEFAULT_BINDINGS, KeyBindings


class PygameInputController:
    def __init__(self, bindings: KeyBindings = DEFAULT_BINDINGS):
        self.bindings = bindings

    def process_events(self, game: Game, events=None) -> None:
        for event in (pygame.event.get() if events is None else events):
            if event.type == pygame.QUIT:
                game.request_quit()
            elif event.type == pygame.MOUSEMOTION:
                dx, dy = event.rel
                game.look(dx, dy)
            elif event.type == pygame.KEYDOWN:
                self._handle_keydown(game, event.key)

    def _handle_keydown(self, game: Game, key: int) -> None:
        b = self.bindings
        # Global actions - available in every mode (matching the original prototype).
        if key == b.escape:
            game.escape()
        elif key == b.quick_save:
            game.save_game()
        elif key == b.quick_load:
            game.load_game()
        elif key == b.interact:
            game.interact()
        elif key == b.toggle_torch:
            game.toggle_torch()
        elif key == b.toggle_crouch:
            game.toggle_crouch()
        elif key == b.wait:
            game.wait()
        elif key == b.confirm_yes:
            game.confirm_yes()
        elif key == b.confirm_no:
            game.confirm_no()

        # Mode-specific actions. ``Game`` ignores them when the mode is not active.
        if key == b.menu_up:
            game.cursor_up()
        elif key == b.menu_down:
            game.cursor_down()
        elif key == b.menu_confirm:
            game.transfer_confirm()
        elif key == b.menu_switch:
            game.transfer_switch_side()
        elif key == b.pick_left:
            game.lockpick_rotate(-1)
        elif key == b.pick_right:
            game.lockpick_rotate(+1)
        elif key == b.pick_attempt:
            game.lockpick_attempt()

    def poll_movement(self) -> MoveIntent:
        keys = pygame.key.get_pressed()
        b = self.bindings
        return MoveIntent(
            forward=bool(keys[b.move_forward]),
            backward=bool(keys[b.move_backward]),
            left=bool(keys[b.strafe_left]),
            right=bool(keys[b.strafe_right]),
            sprint=bool(keys[b.sprint]),
        )
