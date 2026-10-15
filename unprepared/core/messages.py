"""Bounded in-game message/dialogue log (replaces the old module-level global)."""
from __future__ import annotations

from typing import Callable, List, Optional


class MessageLog:
    def __init__(self, max_messages: int = 6, echo: Optional[Callable[[str], None]] = None):
        self.max_messages = max_messages
        self._messages: List[str] = []
        self._echo = echo

    def add(self, msg: str) -> None:
        self._messages.append(msg)
        while len(self._messages) > self.max_messages:
            self._messages.pop(0)
        if self._echo:
            self._echo(msg)

    # Allow the log itself to be used as a ``notify_callback``.
    __call__ = add

    @property
    def messages(self) -> List[str]:
        return list(self._messages)

    def last(self, count: int) -> List[str]:
        return self._messages[-count:] if count > 0 else []

    def clear(self) -> None:
        self._messages.clear()

    def __len__(self) -> int:
        return len(self._messages)

    def __iter__(self):
        return iter(self._messages)


def stdout_echo(msg: str) -> None:
    print(f"[HUD / DIALOGUE] {msg}")
