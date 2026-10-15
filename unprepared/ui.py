"""Keyboard-driven menus: the start screen, the pause menu and graphics options.

Menus are pure data + callbacks; ``HudRenderer.draw_menu`` draws them and the
app routes key presses to :meth:`Menu.handle`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class MenuItem:
    label: str
    action: Optional[Callable[[], None]] = None          # Enter
    adjust: Optional[Callable[[int], None]] = None        # Left/Right with -1/+1
    value: Optional[Callable[[], str]] = None             # text shown on the right
    enabled: Callable[[], bool] = lambda: True
    note: str = ""

    def display_value(self) -> str:
        return self.value() if self.value else ""


@dataclass
class Menu:
    title: str
    items: List[MenuItem] = field(default_factory=list)
    cursor: int = 0
    subtitle: str = ""
    footer: str = "[UP/DOWN] select   [LEFT/RIGHT] adjust   [ENTER] confirm   [ESC] back"
    visible_rows: int = 10               # long lists (saves) scroll
    scroll: int = 0

    def move(self, delta: int) -> int:
        if self.items:
            self.cursor = (self.cursor + delta) % len(self.items)
        return self.cursor

    def visible(self):
        """(first index, items shown) keeping the cursor inside the window."""
        max_scroll = max(0, len(self.items) - self.visible_rows)
        first = min(self.scroll, max_scroll)
        if self.cursor < first:
            first = self.cursor
        elif self.cursor >= first + self.visible_rows:
            first = self.cursor - self.visible_rows + 1
        self.scroll = max(0, min(first, max_scroll))
        return self.scroll, self.items[self.scroll:self.scroll + self.visible_rows]

    @property
    def current(self) -> Optional[MenuItem]:
        return self.items[self.cursor] if self.items else None

    def activate(self) -> None:
        item = self.current
        if item is not None and item.enabled():
            if item.action:
                item.action()
            elif item.adjust:
                item.adjust(+1)

    def adjust(self, delta: int) -> None:
        item = self.current
        if item is not None and item.enabled() and item.adjust:
            item.adjust(delta)


def slider_text(value: float, low: float, high: float, width: int = 12, suffix: str = "") -> str:
    """'[####......] 60' style slider for a value in [low, high]."""
    t = 0.0 if high <= low else max(0.0, min(1.0, (value - low) / (high - low)))
    filled = int(round(t * width))
    return "[" + "#" * filled + "." * (width - filled) + f"] {value:g}{suffix}"
