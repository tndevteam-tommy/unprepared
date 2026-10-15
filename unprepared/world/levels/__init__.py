"""Registry of playable levels."""
from __future__ import annotations

from typing import Callable, Dict, List

from ..level import LevelDefinition
from .town import build_town_level

_LEVELS: Dict[str, Callable[[], LevelDefinition]] = {"town": build_town_level}


def register_level(name: str, factory: Callable[[], LevelDefinition]) -> None:
    _LEVELS[name] = factory


def get_level(name: str = "town") -> LevelDefinition:
    return _LEVELS[name]()


def available_levels() -> List[str]:
    return sorted(_LEVELS)
