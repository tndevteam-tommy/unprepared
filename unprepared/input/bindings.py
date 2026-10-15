"""Key bindings. Keys are pygame key constants; kept in one place so they can be remapped."""
from __future__ import annotations

from dataclasses import dataclass

import pygame


@dataclass(frozen=True)
class KeyBindings:
    # movement (polled)
    move_forward: int = pygame.K_w
    move_backward: int = pygame.K_s
    strafe_left: int = pygame.K_a
    strafe_right: int = pygame.K_d
    sprint: int = pygame.K_LSHIFT
    # one-shot actions
    escape: int = pygame.K_ESCAPE
    quick_save: int = pygame.K_F5
    quick_load: int = pygame.K_F9
    interact: int = pygame.K_e
    toggle_torch: int = pygame.K_1
    toggle_crouch: int = pygame.K_LCTRL
    wait: int = pygame.K_t
    debug_overlay: int = pygame.K_F3
    # transfer menus (trade / pickpocket / containers)
    menu_up: int = pygame.K_UP
    menu_down: int = pygame.K_DOWN
    menu_confirm: int = pygame.K_RETURN
    menu_switch: int = pygame.K_TAB
    # lockpicking
    pick_left: int = pygame.K_LEFT
    pick_right: int = pygame.K_RIGHT
    pick_attempt: int = pygame.K_SPACE
    # yes / no questions (Enter / Esc work too)
    confirm_yes: int = pygame.K_y
    confirm_no: int = pygame.K_n

    def controls_help(self) -> list:
        """Lines shown in the HUD controls panel (movement, mouse look and ESC are assumed known)."""
        return [
            "CONTROLS:",
            "[Shift] Sprint   [Ctrl] Crouch",
            "[E] Use / Talk / Trade / Search",
            "Crouch + [E]  Pick Lock / Pockets",
            "[1] Torch   [T] Wait an Hour",
            "[Up/Down] Scroll Inventory",
            "[F5] Quick Save   [F9] Quick Load",
            "[F3] Performance Stats",
        ]


DEFAULT_BINDINGS = KeyBindings()
