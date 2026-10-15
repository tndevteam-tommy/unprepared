"""Pygame window, screens (start menu / playing / pause / graphics options) and the main loop.

Everything here is glue between pygame and ``Game``; the game never knows a
menu exists.
"""
from __future__ import annotations

import sys
from enum import Enum
from typing import Optional

import pygame
from pygame.locals import DOUBLEBUF, OPENGL

from .config import DEFAULT_SETTINGS, GameSettings
from .game import Game
from .graphics import GraphicsSettings, graphics_settings_path
from .input import DEFAULT_BINDINGS, KeyBindings, PygameInputController
from .perf import FrameProfiler, recommend_quality
from .rendering import Renderer
from .rendering.hud import MenuRenderer
from .ui import Menu, MenuItem, slider_text
from .world import LevelDefinition


class Screen(Enum):
    START = "start"
    PLAYING = "playing"
    PAUSE = "pause"
    GRAPHICS = "graphics"
    SAVE = "save"          # pick a slot to save into
    LOAD = "load"          # pick a save to load
    CONFIRM = "confirm"    # a yes/no question (overwrite a save, exit to menu)


class PygameApp:
    BENCHMARK_FRAMES = 40

    def __init__(self, settings: GameSettings = DEFAULT_SETTINGS, level: Optional[LevelDefinition] = None,
                 bindings: KeyBindings = DEFAULT_BINDINGS, save_file: Optional[str] = None,
                 graphics: Optional[GraphicsSettings] = None, skip_menu: bool = False, auto_quality: bool = True):
        self.settings = settings
        self.level = level
        self.save_file = save_file or settings.save_file
        pygame.init()
        pygame.font.init()
        w = settings.window
        self.screen_surface = pygame.display.set_mode((w.width, w.height), DOUBLEBUF | OPENGL)
        pygame.display.set_caption(w.title)

        self.graphics_path = graphics_settings_path(self.save_file)
        self.graphics = graphics or GraphicsSettings.load(self.graphics_path) or GraphicsSettings()
        self.profiler = FrameProfiler()
        self._mouse_captured: Optional[bool] = None
        self.game = Game(level=level, settings=settings, save_file=self.save_file)
        self.input = PygameInputController(bindings)
        self.renderer = Renderer(settings, bindings.controls_help(), graphics=self.graphics)
        self.menus = MenuRenderer(self.renderer.text, settings.hud_layout(), settings.hud_colors)
        self.clock = pygame.time.Clock()
        self.screen = Screen.PLAYING if skip_menu else Screen.START
        self.in_session = skip_menu            # a game is underway (menus return to it instead of a fresh one)
        self.menu: Optional[Menu] = None
        self._load_return = Screen.START
        self._confirm_cancel = self.open_pause_menu
        self.quit_requested = False
        self.graphics.detected_renderer = self.renderer.renderer_name
        if auto_quality and self.graphics.auto_quality:
            self.auto_configure_quality()
        if not skip_menu:
            self.open_start_menu()
        self._sync_mouse_capture()

    # ------------------------------------------------------------------ quality detection
    def benchmark(self, frames: int = BENCHMARK_FRAMES) -> float:
        """Render the current scene ``frames`` times with the *high* preset; returns the average ms."""
        previous = self.graphics.to_dict()
        self.graphics.apply_preset("high")
        self.rebuild_renderer()
        profiler = FrameProfiler()
        for _ in range(frames):
            self.renderer.render_scene_only(self.game)
            pygame.display.flip()
            profiler.end_frame()
        self.graphics = GraphicsSettings.from_dict(previous)
        self.renderer.graphics = self.graphics
        self.rebuild_renderer()
        return profiler.average_frame_ms

    def auto_configure_quality(self) -> str:
        ms = self.benchmark()
        quality = recommend_quality(ms, self.renderer.renderer_name)
        self.graphics.apply_preset(quality)
        self.graphics.auto_quality = True
        self.graphics.benchmark_ms = round(ms, 2)
        self.rebuild_renderer()
        self.graphics.save(self.graphics_path)
        return quality

    def rebuild_renderer(self) -> None:
        """Recreate GL resources after a change that needs it (shaders / mipmaps toggled)."""
        self.renderer.release()
        self.renderer = Renderer(self.settings, self.input.bindings.controls_help(), graphics=self.graphics)
        self.menus = MenuRenderer(self.renderer.text, self.settings.hud_layout(), self.settings.hud_colors)
        self.renderer.graphics = self.graphics

    # ------------------------------------------------------------------ menus
    @property
    def saves(self):
        return self.game.saves

    def open_start_menu(self) -> None:
        self.screen = Screen.START
        self.in_session = False
        items = []
        latest = self.saves.latest()
        if latest is not None:
            items.append(MenuItem("Continue", self.continue_game, value=lambda: latest.label))
        items += [
            MenuItem("New Game", self.new_game),
            MenuItem("Load Game", self.open_load_menu, enabled=self.saves.has_saves,
                     note="" if latest else "(no saves yet)"),
            MenuItem("Graphics Settings", self.open_graphics_menu),
            MenuItem("Exit", self.request_quit),
        ]
        self.menu = Menu("UNPREPARED", items, subtitle="A rogue-like of stealth and theft",
                         footer="[UP/DOWN] select   [ENTER] confirm")

    def open_pause_menu(self) -> None:
        self.screen = Screen.PAUSE
        self.menu = Menu("PAUSED", [
            MenuItem("Resume", self.resume),
            MenuItem("Save Game", self.open_save_menu),
            MenuItem("Load Game", self.open_load_menu, enabled=self.saves.has_saves),
            MenuItem("Graphics Settings", self.open_graphics_menu),
            MenuItem("Exit to Menu", self.confirm_exit_to_menu),
        ], footer="[UP/DOWN] select   [ENTER] confirm   [ESC] resume")

    def _save_rows(self):
        return self.saves.list_saves()

    def open_save_menu(self) -> None:
        """Scrollable list of saves, newest first, defaulting to [New Save]; picking an old one asks first."""
        self.screen = Screen.SAVE
        items = [MenuItem("[New Save]", self.save_to_new_slot)]
        for info in self._save_rows():
            items.append(MenuItem(info.name, lambda info=info: self.confirm_overwrite(info), value=lambda info=info: info.label))
        self.menu = Menu("SAVE GAME", items, footer="[UP/DOWN] select   [ENTER] save here   [ESC] back")

    def open_load_menu(self) -> None:
        """Scrollable list of saves, newest first."""
        self._load_return = self.screen
        self.screen = Screen.LOAD
        items = [MenuItem(info.name, lambda info=info: self.load_from(info.path), value=lambda info=info: info.label)
                 for info in self._save_rows()]
        if not items:
            items.append(MenuItem("(no saves yet)", enabled=lambda: False))
        self.menu = Menu("LOAD GAME", items, footer="[UP/DOWN] select   [ENTER] load   [ESC] back")

    def open_confirm(self, title: str, question: str, on_yes, on_no, yes_label: str = "Yes", no_label: str = "No") -> None:
        self.screen = Screen.CONFIRM
        self._confirm_cancel = on_no
        self.menu = Menu(title, [MenuItem(no_label, on_no), MenuItem(yes_label, on_yes)], subtitle=question,
                         footer="[UP/DOWN] select   [ENTER] confirm   [ESC] back")

    def confirm_overwrite(self, info) -> None:
        self.open_confirm("OVERWRITE SAVE?", f"Replace \"{info.name}\" ({info.label})?",
                          on_yes=lambda: self.save_to(info.path), on_no=self.open_save_menu, yes_label="Yes, overwrite")

    def confirm_exit_to_menu(self) -> None:
        self.open_confirm("EXIT TO MENU?", "Unsaved progress will be lost.", on_yes=self.exit_to_menu,
                          on_no=self.open_pause_menu, yes_label="Exit without saving", no_label="Back")

    def open_graphics_menu(self) -> None:
        g = self.graphics
        self._graphics_return = self.screen
        self.screen = Screen.GRAPHICS

        def set_quality(delta):
            g.next_quality(delta)
            self.rebuild_renderer()

        def adjust(attr, low, high, step, rebuild=False):
            def f(delta):
                setattr(g, attr, round(max(low, min(high, getattr(g, attr) + delta * step)), 2))
                g.auto_quality = False
                if rebuild:
                    self.rebuild_renderer()
            return f

        def toggle(attr, rebuild=False):
            def f(delta=1):
                setattr(g, attr, not getattr(g, attr))
                g.auto_quality = False
                if rebuild:
                    self.rebuild_renderer()
            return f

        self.menu = Menu("GRAPHICS SETTINGS", [
            MenuItem("Quality preset", adjust=set_quality, value=lambda: f"< {g.quality.upper()} >" + ("  (auto)" if g.auto_quality else "")),
            MenuItem("Field of view", adjust=adjust("fov", 50.0, 100.0, 2.0), value=lambda: slider_text(g.fov, 50, 100, suffix=" deg")),
            MenuItem("Object fade distance", adjust=adjust("object_fade", 0.3, 1.0, 0.05), value=lambda: slider_text(g.object_fade, 0.3, 1.0)),
            MenuItem("Character fade distance", adjust=adjust("character_fade", 0.3, 1.0, 0.05), value=lambda: slider_text(g.character_fade, 0.3, 1.0)),
            MenuItem("Contrast", adjust=adjust("contrast", 0.6, 1.6, 0.05), value=lambda: slider_text(g.contrast, 0.6, 1.6)),
            MenuItem("Shader lighting", adjust=toggle("shaders", rebuild=True), value=lambda: "ON" if g.shaders else "OFF (fixed-function)"),
            MenuItem("Stars", adjust=toggle("stars"), value=lambda: "ON" if g.stars else "OFF"),
            MenuItem("Roofs & floors", adjust=toggle("roofs"), value=lambda: "ON" if g.roofs else "OFF"),
            MenuItem("Performance overlay", adjust=toggle("show_perf_overlay"), value=lambda: "ON" if g.show_perf_overlay else "OFF"),
            MenuItem("Re-detect best settings", self.auto_configure_quality, value=lambda: f"({g.detected_renderer[:28]}, {g.benchmark_ms} ms)"),
            MenuItem("Back", self.close_graphics_menu),
        ], subtitle=f"Renderer: {self.renderer.renderer_name[:48]}")

    def close_graphics_menu(self) -> None:
        self.graphics.save(self.graphics_path)
        if self._graphics_return is Screen.START:
            self.open_start_menu()
        else:
            self.open_pause_menu()

    def _back(self) -> None:
        """ESC inside a sub-menu: one level up."""
        if self.screen is Screen.GRAPHICS:
            self.close_graphics_menu()
        elif self.screen is Screen.SAVE:
            self.open_pause_menu()
        elif self.screen is Screen.LOAD:
            self.open_start_menu() if self._load_return is Screen.START else self.open_pause_menu()
        elif self.screen is Screen.CONFIRM:
            self._confirm_cancel()
        elif self.screen is Screen.PAUSE:
            self.resume()

    # ------------------------------------------------------------------ actions
    def new_game(self) -> None:
        self.game = Game(level=self.level, settings=self.settings, save_file=self.save_file)
        self.resume()

    def continue_game(self) -> None:
        latest = self.saves.latest()
        if latest is not None:
            self.load_from(latest.path)

    def load_game(self) -> None:
        """Load the newest save (kept for callers that do not pick a slot)."""
        self.continue_game()

    def load_from(self, path: str) -> None:
        if not self.in_session:
            self.game = Game(level=self.level, settings=self.settings, save_file=self.save_file)
        if self.game.load_game(path) or self.game.saves.load(self.game.world, self.game.player, path):
            self.resume()

    def save_game(self) -> None:
        """Quick-save to the default file and resume."""
        self.save_to(None)

    def save_to(self, path) -> None:
        self.game.saves.save(self.game.world, self.game.player, path)
        self.resume()

    def save_to_new_slot(self) -> None:
        self.game.saves.save_new(self.game.world, self.game.player)
        self.resume()

    def exit_to_menu(self) -> None:
        """Back to the start screen; the world keeps rendering behind it, nothing is saved."""
        self.open_start_menu()

    def resume(self) -> None:
        self.screen = Screen.PLAYING
        self.in_session = True
        self.menu = None
        self.clock.tick()                      # drop the time spent in the menu
        self._sync_mouse_capture()

    def request_quit(self) -> None:
        self.quit_requested = True
        self.game.request_quit()

    # ------------------------------------------------------------------ loop
    @property
    def running(self) -> bool:
        return not self.quit_requested

    def _sync_mouse_capture(self) -> None:
        captured = self.screen is Screen.PLAYING and self.game.mouse_captured
        if captured != self._mouse_captured:
            pygame.mouse.set_visible(not captured)
            pygame.event.set_grab(captured)
            self._mouse_captured = captured

    def _process_menu_events(self) -> None:
        b = self.input.bindings
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.request_quit()
            elif event.type == pygame.KEYDOWN and self.menu is not None:
                if event.key == b.menu_up:
                    self.menu.move(-1)
                elif event.key == b.menu_down:
                    self.menu.move(+1)
                elif event.key == pygame.K_LEFT:
                    self.menu.adjust(-1)
                elif event.key == pygame.K_RIGHT:
                    self.menu.adjust(+1)
                elif event.key in (b.menu_confirm, pygame.K_KP_ENTER):
                    self.menu.activate()
                elif event.key == b.escape:
                    self._back()
                elif event.key == b.debug_overlay:
                    self.graphics.show_perf_overlay = not self.graphics.show_perf_overlay

    def _process_game_events(self) -> None:
        """Playing: ESC opens the pause menu, F3 toggles the overlay; everything else goes to the game."""
        b = self.input.bindings
        pending = []
        for event in pygame.event.get():
            if event.type == pygame.KEYDOWN and event.key == b.escape and self.game.in_explore_mode:
                self.open_pause_menu()
                return
            if event.type == pygame.KEYDOWN and event.key == b.debug_overlay:
                self.graphics.show_perf_overlay = not self.graphics.show_perf_overlay
                continue
            pending.append(event)
        self.input.process_events(self.game, pending)
        if not self.game.running:
            self.quit_requested = True

    def step(self) -> None:
        """Run exactly one frame: input -> simulation -> render -> present."""
        with self.profiler.phase("input"):
            delta_time = self.clock.tick(self.settings.window.target_fps) / 1000.0
            if self.screen is Screen.PLAYING:
                self._process_game_events()
            else:
                self._process_menu_events()
            self._sync_mouse_capture()
        with self.profiler.phase("update"):
            if self.screen is Screen.PLAYING:
                self.game.update(delta_time, self.input.poll_movement())
        with self.profiler.phase("render3d"):
            self.renderer.render_scene_only(self.game)
        with self.profiler.phase("hud"):
            if self.screen is Screen.PLAYING:
                self.renderer.hud.render(self.game)
            if self.menu is not None:
                self.menus.draw_menu(self.menu, dim=True)
            if self.graphics.show_perf_overlay:
                scene = self.renderer.scene
                self.menus.draw_perf_overlay(self.profiler, [
                    f"quality {self.graphics.quality}  shaders {'on' if self.renderer.uses_shaders else 'off'}",
                    f"objects drawn {scene.drawn_objects}  culled {scene.culled_objects}  lights {len(self.renderer.lighting.point_lights)}",
                    f"renderer {self.renderer.renderer_name[:40]}",
                ])
        with self.profiler.phase("flip"):
            pygame.display.flip()
        self.profiler.end_frame()

    def run(self) -> None:
        while self.running:
            self.step()
        self._sync_mouse_capture()

    def shutdown(self) -> None:
        self.graphics.save(self.graphics_path)
        pygame.quit()


def main(argv=None) -> None:
    app = PygameApp()
    try:
        app.run()
    finally:
        app.shutdown()
    sys.exit()
