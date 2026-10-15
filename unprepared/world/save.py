"""Save-game persistence.

Version 2 added the clock minutes, player orientation, door states and NPC
inventories/torches; version 3 containers, item stacks and crime counters;
version 4 the jail; version 5 NPC purses, container locks, item ownership and a
``meta`` block so the save menus can list saves without loading them. Older
files still load (missing fields keep their current values).

Saves live in two places: the *quick save* file (``filename``, F5/F9) and the
``saves/`` directory next to it, one file per named save. ``list_saves`` returns
both, newest first, for the Save / Load / Continue menus.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

from ..entities import Player
from .world import World

Notify = Optional[Callable[[str], None]]

SAVE_VERSION = 5


@dataclass(frozen=True)
class SaveInfo:
    path: str
    label: str            # "Day 3 09:00 - 120g - 2024-05-01 12:33"
    modified: float       # mtime (seconds since the epoch)
    quick: bool = False   # the F5 quick-save file

    @property
    def name(self) -> str:
        return "Quick Save" if self.quick else os.path.splitext(os.path.basename(self.path))[0]


class SaveManager:
    def __init__(self, filename: str = "savegame.json", notify_callback: Notify = None):
        self.filename = filename
        self.notify = notify_callback

    @property
    def save_dir(self) -> str:
        base = os.path.dirname(os.path.abspath(self.filename))
        return os.path.join(base, "saves")

    # ------------------------------------------------------------------ (de)serialisation
    @staticmethod
    def serialize(world: World, player: Player) -> dict:
        return {
            "version": SAVE_VERSION,
            "meta": {
                "day": world.day_count, "hour": world.simulated_hour, "gold": round(player.gold, 1),
                "level": player.level, "saved_at": time.time(),
            },
            "simulated_hour": world.simulated_hour,
            "minute_accumulator": world.clock.minute_accumulator,
            "day_count": world.day_count,
            "elapsed": world.elapsed,
            "player": player.to_dict(),
            "npcs": [npc.to_dict() for npc in world.npcs],
            "doors": [door.to_dict() for door in world.doors],
            "containers": [c.to_dict() for c in world.containers],
            "jail": world.jail.to_dict(),
        }

    @staticmethod
    def apply(save_data: dict, world: World, player: Player) -> None:
        world.simulated_hour = save_data.get("simulated_hour", 7)
        world.clock.minute_accumulator = save_data.get("minute_accumulator", 0.0)
        world.day_count = save_data.get("day_count", 0)
        world.elapsed = save_data.get("elapsed", 0.0)
        player.load_dict(save_data["player"])
        npc_data_map = {n["name"]: n for n in save_data.get("npcs", [])}
        for npc in world.npcs:
            if npc.name in npc_data_map:
                npc.load_dict(npc_data_map[npc.name])
        door_data_map = {d["door_id"]: d for d in save_data.get("doors", [])}
        for door in world.doors:
            if door.door_id in door_data_map:
                door.load_dict(door_data_map[door.door_id])
        container_map = {c["name"]: c for c in save_data.get("containers", [])}
        for container in world.containers:
            if container.name in container_map:
                container.load_dict(container_map[container.name])
        world.jail.load_dict(save_data.get("jail", {}))
        if save_data.get("version", 1) < 5:
            for item in player.inventory:          # pre-ownership saves: what you carry (unstolen) is yours
                if not item.is_stolen and item.owner is None:
                    item.owner = item.PLAYER_OWNER
        world.resync_schedules(announce=False, doors=False)      # doors stay exactly as saved

    # ------------------------------------------------------------------ files
    @staticmethod
    def describe(path: str) -> str:
        """Human-readable label for a save file (reads only the small ``meta`` block when present)."""
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return os.path.basename(path)
        meta = data.get("meta") or {"day": data.get("day_count", 0), "hour": data.get("simulated_hour", 0),
                                    "gold": data.get("player", {}).get("gold", 0.0), "saved_at": os.path.getmtime(path)}
        stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(meta.get("saved_at", os.path.getmtime(path))))
        return f"Day {meta.get('day', 0) + 1} {int(meta.get('hour', 0)):02d}:00 - {float(meta.get('gold', 0.0)):.0f}g - {stamp}"

    def list_saves(self) -> List[SaveInfo]:
        """Every save (quick save + ``saves/*.json``), newest first."""
        found: List[SaveInfo] = []
        if os.path.exists(self.filename):
            found.append(SaveInfo(os.path.abspath(self.filename), self.describe(self.filename),
                                  os.path.getmtime(self.filename), quick=True))
        if os.path.isdir(self.save_dir):
            for name in os.listdir(self.save_dir):
                if name.lower().endswith(".json"):
                    path = os.path.join(self.save_dir, name)
                    found.append(SaveInfo(path, self.describe(path), os.path.getmtime(path)))
        found.sort(key=lambda info: info.modified, reverse=True)
        return found

    def latest(self) -> Optional[SaveInfo]:
        saves = self.list_saves()
        return saves[0] if saves else None

    def has_saves(self) -> bool:
        return bool(self.list_saves())

    def new_save_path(self) -> str:
        """A fresh, unused file name in the saves directory."""
        os.makedirs(self.save_dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = os.path.join(self.save_dir, f"save-{stamp}.json")
        n = 1
        while os.path.exists(path):
            n += 1
            path = os.path.join(self.save_dir, f"save-{stamp}-{n}.json")
        return path

    # ------------------------------------------------------------------ save / load
    def save(self, world: World, player: Player, path: Optional[str] = None) -> str:
        """Write the game to ``path`` (default: the quick-save file). Returns the path written."""
        path = path or self.filename
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.serialize(world, player), f, indent=4)
        if self.notify:
            self.notify("Game state saved successfully!" if path == self.filename
                        else f"Game saved to {os.path.basename(path)}.")
        return path

    def save_new(self, world: World, player: Player) -> str:
        return self.save(world, player, self.new_save_path())

    def load(self, world: World, player: Player, path: Optional[str] = None) -> bool:
        path = path or self.filename
        if not os.path.exists(path):
            if self.notify:
                self.notify("No save file found!")
            return False
        with open(path, "r") as f:
            save_data = json.load(f)
        self.apply(save_data, world, player)
        if self.notify:
            self.notify("Game state loaded successfully!")
        return True
