"""Unprepared - a rogue-like stealth & theft RPG.

Package layout
--------------
core/       pure helpers: 3D math, message log, day/night cycle
entities/   game objects: Item, Door, Player, NPC, SkillTree
world/      level data, World container, save/load
systems/    gameplay rules operating on entities (movement, trading, ...)
game.py     the headless simulation: state + action API (no pygame/OpenGL)
input/      pygame event -> Game action translation
rendering/  OpenGL presentation of a Game
app.py      window creation and the main loop
"""
__version__ = "0.2.0"
