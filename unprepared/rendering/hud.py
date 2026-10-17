"""2D overlay: status bar, prompts, panels, trade menu and lockpicking mini-game."""
from __future__ import annotations

import math

from OpenGL.GL import (GL_BLEND, GL_DEPTH_TEST, GL_EMISSION, GL_FRONT_AND_BACK, GL_LIGHTING, GL_LINES, GL_LINE_LOOP,
                       GL_MODELVIEW, GL_ONE_MINUS_SRC_ALPHA, GL_POINTS, GL_PROJECTION, GL_SRC_ALPHA, GL_TRIANGLES, glBegin,
                       glBlendFunc, glColor3f, glColor4f, glDisable, glEnable, glEnd, glLineWidth, glLoadIdentity,
                       glMaterialfv, glMatrixMode, glOrtho, glPointSize, glPopMatrix, glPushMatrix, glVertex2f)

from ..config import HudColors, HudLayout
from ..core.math3d import view_direction
from ..systems import Side
from .camera import project
from .primitives import fill_rect_2d
from .text import TextRenderer


def wrap_text(text: str, max_width: int, measure) -> list:
    """Greedy word wrap using ``measure(str) -> (w, h)``; over-long words are split."""
    lines, current = [], ""
    for word in text.split(" "):
        candidate = word if not current else f"{current} {word}"
        if measure(candidate)[0] <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        while measure(word)[0] > max_width and len(word) > 1:    # split a word that never fits
            cut = len(word)
            while cut > 1 and measure(word[:cut])[0] > max_width:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        current = word
    if current or not lines:
        lines.append(current)
    return lines


class HudRenderer:
    def __init__(self, text: TextRenderer, layout: HudLayout, colors: HudColors, controls_help: list):
        self.text = text
        self.layout = layout
        self.colors = colors
        self.controls_help = controls_help
        self.fov = 60.0                  # kept in step with the renderer's projection (for speech bubbles)

    # ------------------------------------------------------------------ frame
    def render(self, game) -> None:
        self._begin_2d()
        self._draw_speech_bubbles(game)
        self._draw_status_bar(game)
        if game.interaction_prompt and game.in_explore_mode:
            self._draw_prompt(game.interaction_prompt)
        self._draw_crosshair()
        self._draw_controls_panel()
        self._draw_inventory_panel(game)
        self._draw_log_panel(game)
        if game.in_transfer:
            self._draw_transfer_menu(game)
        if game.in_lockpicking:
            self._draw_lockpick_minigame(game)
        if getattr(game, "confirmation", None) is not None:
            self._draw_confirmation(game.confirmation)
        self.draw_fade(getattr(game, "fade_alpha", 0.0))
        self._end_2d()

    # ------------------------------------------------------------------ speech bubbles
    BUBBLE_MAX_WIDTH = 280
    BUBBLE_HEAD_HEIGHT = 2.05            # world units above an NPC's feet where the bubble points

    def _draw_speech_bubbles(self, game) -> None:
        """Word-wrapped bubbles above the heads of speakers the player can hear (``Game.speech_bubbles``),
        kept inside the window; when two would overlap the later one is nudged upwards."""
        speakers = game.speech_bubbles() if hasattr(game, "speech_bubbles") else []
        if not speakers:
            return
        player = game.player
        eye = player.eye_position
        dx, dy, dz = view_direction(player.rotation_y, player.rotation_x)
        center = (eye.x + dx, eye.y + dy, eye.z + dz)
        w, h = self.layout.width, self.layout.height
        measure = lambda t: self.text.measure(t, self.text.font_small)   # noqa: E731
        placed = []
        items = []
        for npc, speech in speakers:
            head = (npc.position.x, npc.position.y + self.BUBBLE_HEAD_HEIGHT, npc.position.z)
            hit = project(head, (eye.x, eye.y, eye.z), center, self.fov, w / h, w, h)
            if hit is None:
                continue
            items.append((hit[2], hit[0], hit[1], npc, speech))
        items.sort(key=lambda it: -it[0])            # far speakers first, near ones drawn on top
        for depth, sx, sy, npc, speech in items:
            lines = wrap_text(speech.text, self.BUBBLE_MAX_WIDTH - 24, measure)
            line_h = measure("Ag")[1] + 2
            bw = max(measure(line)[0] for line in [npc.name, *lines]) + 24
            bh = 12 + line_h * (len(lines) + 1)      # the name on its own line, then the text
            x1 = int(max(6, min(w - bw - 6, sx - bw / 2)))
            y1 = int(sy - bh - 14)
            y1 = max(self.layout.top_bar_height + 6, min(h - bh - 6, y1))
            for _ in range(8):                        # slide up out of any bubble already drawn
                if not any(x1 < px2 and x1 + bw > px1 and y1 < py2 and y1 + bh > py1 for px1, py1, px2, py2 in placed):
                    break
                y1 -= bh + 6
            y1 = max(self.layout.top_bar_height + 6, y1)
            placed.append((x1, y1, x1 + bw, y1 + bh))
            fill_rect_2d(x1, y1, x1 + bw, y1 + bh, self.colors.bubble)
            fill_rect_2d(x1 + 2, y1 + 2, x1 + bw - 2, y1 + bh - 2, self.colors.bubble_fill)
            tip_x = int(max(x1 + 12, min(x1 + bw - 12, sx)))
            if y1 + bh + 12 <= sy:                    # a little tail towards the speaker
                glBegin(GL_TRIANGLES)
                glColor4f(*self.colors.bubble_fill)
                glVertex2f(tip_x - 7, y1 + bh - 2); glVertex2f(tip_x + 7, y1 + bh - 2); glVertex2f(tip_x, y1 + bh + 10)
                glEnd()
            self.text.draw(npc.name, x1 + 12, y1 + 6, self.text.font_small, self.colors.bubble_name)
            for idx, line in enumerate(lines):
                self.text.draw(line, x1 + 12, y1 + 6 + line_h * (idx + 1), self.text.font_small, self.colors.bubble_text)

    def draw_fade(self, alpha: float) -> None:
        """Black overlay for scene transitions (0 = clear, 1 = fully black)."""
        if alpha > 0.0:
            fill_rect_2d(0, 0, self.layout.width, self.layout.height, (0.0, 0.0, 0.0, min(1.0, alpha)))

    def _draw_confirmation(self, question) -> None:
        c, t = self.colors, self.text
        w = self.layout.width
        lines = wrap_text(question.text, 460, lambda s: t.measure(s, t.font))
        options = "   ".join(o for o in (question.yes_label, question.alt_label, question.no_label) if o)
        panel_w, panel_h = 520, 70 + 28 * len(lines) + 30
        x1, y1 = (w - panel_w) // 2, self.layout.prompt_y - panel_h // 2 - 40
        fill_rect_2d(x1, y1, x1 + panel_w, y1 + panel_h, c.modal_panel)
        y = y1 + 20
        for line in lines:
            t.draw(line, x1 + 30, y, t.font, c.gold)
            y += 28
        t.draw(options, x1 + 30, y + 12, t.font_small, c.white)

    # ------------------------------------------------------------------ GL state
    def _begin_2d(self) -> None:
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, self.layout.width, self.layout.height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        # Reset material emission & colour state left over from the 3D pass.
        glMaterialfv(GL_FRONT_AND_BACK, GL_EMISSION, [0.0, 0.0, 0.0, 1.0])
        glColor4f(1.0, 1.0, 1.0, 1.0)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    def _end_2d(self) -> None:
        glDisable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()

    # ------------------------------------------------------------------ widgets
    def _draw_status_bar(self, game) -> None:
        c, t, player = self.colors, self.text, game.player
        fill_rect_2d(0, 0, self.layout.width, self.layout.top_bar_height, c.top_bar)
        t.draw(f"Time: {game.world.simulated_hour:02d}:00", 20, 10, t.font_small, c.white)
        t.draw(f"Gold: {player.gold:.1f}g", 160, 10, t.font_small, c.gold)
        t.draw(f"Torch [1]: {'ON' if player.has_lit_torch else 'OFF'}", 280, 10, t.font_small,
               c.torch_on if player.has_lit_torch else c.white)
        t.draw(f"Stance [Ctrl]: {'Crouching' if player.is_crouching else 'Standing'}", 460, 10, t.font_small,
               c.crouch_on if player.is_crouching else c.white)

    def _draw_prompt(self, prompt: str) -> None:
        c = self.colors
        color = c.danger if "Locked" in prompt else c.prompt
        pw, ph = self.text.measure(prompt, self.text.font)
        px = self.layout.center[0] - (pw // 2)
        py = self.layout.prompt_y
        fill_rect_2d(px - 12, py - 6, px + pw + 12, py + ph + 6, c.prompt_panel)
        self.text.draw(prompt, px, py, self.text.font, color)

    def _draw_crosshair(self) -> None:
        cx, cy = self.layout.center
        glLineWidth(2.0)
        glBegin(GL_LINES)
        glColor3f(1.0, 1.0, 1.0)
        glVertex2f(cx - 6, cy); glVertex2f(cx + 6, cy)
        glVertex2f(cx, cy - 6); glVertex2f(cx, cy + 6)
        glEnd()

    def _draw_controls_panel(self) -> None:
        x1, y1, x2, y2 = self.layout.controls_panel
        y2 = max(y2, y1 + 20 + 22 * len(self.controls_help))     # never clip: grow with the list
        fill_rect_2d(x1, y1, x2, y2, self.colors.panel)
        for idx, line in enumerate(self.controls_help):
            color = self.colors.gold if idx == 0 else self.colors.white
            self.text.draw(line, x1 + 10, y1 + 10 + idx * 22, self.text.font_small, color)

    def _draw_item_text(self, text: str, x: float, y: float, item, color, font=None) -> None:
        """Item row: stolen items get a bold red '(S)' tag in front and red text."""
        font = font or self.text.font_small
        if item.is_stolen:
            w, _ = self.text.draw("(S) ", x, y, self.text.font_tag, self.colors.stolen_tag)
            x += w
            color = self.colors.danger
        self.text.draw(text, x, y, font, color)

    def _draw_inventory_panel(self, game) -> None:
        x1, y1, x2, y2 = self.layout.inventory_panel
        c = self.colors
        fill_rect_2d(x1, y1, x2, y2, c.panel)
        first, items = game.visible_inventory()
        total = len(game.player.inventory)
        title = "PLAYER INVENTORY:" if total <= self.layout.max_inventory_rows else \
            f"PLAYER INVENTORY ({first + 1}-{first + len(items)} of {total}):"
        self.text.draw(title, x1 + 10, y1 + 10, self.text.font_small, c.gold)
        for idx, item in enumerate(items):
            self._draw_item_text(f"{item.display_name} ({item.value}g)", x1 + 10, y1 + 40 + idx * 20, item, c.white)
        if first > 0:
            self.text.draw("^ more", x2 - 60, y1 + 10, self.text.font_small, c.scroll_hint)
        if first + len(items) < total:
            self.text.draw("v more", x2 - 60, y2 - 24, self.text.font_small, c.scroll_hint)

    def _draw_log_panel(self, game) -> None:
        x1, y1, x2, y2 = self.layout.log_panel
        c = self.colors
        fill_rect_2d(x1, y1, x2, y2, c.panel)
        self.text.draw("WORLD DIALOGUE & EVENTS:", x1 + 10, y1 + 10, self.text.font_small, c.log_title)
        width = x2 - x1 - 20
        measure = lambda t: self.text.measure(t, self.text.font_small)   # noqa: E731
        lines = []
        for msg in game.messages.messages:
            lines.extend(wrap_text(msg, width, measure))
        for idx, line in enumerate(lines[-self.layout.max_log_rows:]):
            self.text.draw(line, x1 + 10, y1 + 40 + idx * self.layout.log_line_height, self.text.font_small, c.white)

    def _draw_transfer_menu(self, game) -> None:
        """Two-column item exchange (trade / pickpocket / container); Tab switches the active column."""
        x1, y1, x2, y2 = self.layout.trade_panel
        c, t, session = self.colors, self.text, game.transfer
        policy = session.policy
        fill_rect_2d(x1, y1, x2, y2, c.modal_panel)

        t.draw(policy.title, x1 + 28, y1 + 16, t.font, c.gold)
        t.draw(policy.help_text, x1 + 28, y1 + 51, t.font_small, c.white)

        row_h = 25
        rows_y = y1 + 140                      # headings at +96, scroll hints on their own line at +116
        session.visible_rows = max(1, (y2 - 20 - rows_y) // row_h)
        col_w = 280
        for side, col_x in ((Side.LEFT, x1 + 28), (Side.RIGHT, x1 + 308)):
            active = session.side is side
            label = policy.left_label if side is Side.LEFT else policy.right_label
            t.draw(("> " if active else "  ") + label, col_x, y1 + 96, t.font_small, c.selected if active else c.trade_heading)
            first, rows = session.visible(side)
            total = len(session.rows(side))
            for idx, item in enumerate(rows):
                selected = active and session.selection[side] == first + idx
                prefix = "> " if selected else "  "
                self._draw_item_text(f"{prefix}{session.row_text(item, side)}", col_x + 10, rows_y + idx * row_h, item,
                                     c.selected if selected else c.white)
            # scroll hints get their own line under the heading, flush with the column's right edge
            if first > 0:
                hint = f"^ {first} more"
                t.draw(hint, col_x + col_w - t.measure(hint, t.font_small)[0], y1 + 116, t.font_small, c.scroll_hint)
            if first + len(rows) < total:
                hint = f"v {total - first - len(rows)} more"
                t.draw(hint, col_x + col_w - t.measure(hint, t.font_small)[0], y2 - 22, t.font_small, c.scroll_hint)

    def _draw_lockpick_minigame(self, game) -> None:
        x1, y1, x2, y2 = self.layout.lockpick_panel
        c, t, lp = self.colors, self.text, game.lockpicking
        fill_rect_2d(x1, y1, x2, y2, c.lockpick_panel)

        t.draw("LOCKPICKING MINI-GAME", x1 + 53, y1 + 16, t.font, c.gold)
        t.draw("Rotate pick with [LEFT / RIGHT] arrows", x1 + 23, y1 + 56, t.font_small, c.white)
        t.draw("Press [SPACE] when the pick is on the spot", x1 + 33, y1 + 86, t.font_small, c.white)
        if lp.wobble_amplitude > 0:
            t.draw(f"Unsteady hands: the pick wanders {lp.wobble_amplitude:.0f} deg", x1 + 43, y1 + 106, t.font_small, c.scroll_hint)

        center_x, center_y = self.layout.lockpick_center
        radius = self.layout.lockpick_radius
        is_aligned = lp.is_aligned
        glow = (1.0, 0.9, 0.1) if is_aligned else (0.4, 0.4, 0.5)

        # Lock cylinder ring
        glLineWidth(6.0 if is_aligned else 3.0)
        glBegin(GL_LINE_LOOP)
        for i in range(36):
            rad = math.radians(i * 10)
            glColor3f(*glow)
            glVertex2f(center_x + math.cos(rad) * radius, center_y + math.sin(rad) * radius)
        glEnd()

        # Sweet spot marker
        sweet_rad = math.radians(lp.sweet_spot)
        glPointSize(10.0)
        glBegin(GL_POINTS)
        glColor3f(1.0, 0.8, 0.0)
        glVertex2f(center_x + math.cos(sweet_rad) * radius, center_y + math.sin(sweet_rad) * radius)
        glEnd()

        # Pick needle (drawn where the unsteady hand actually holds it)
        glLineWidth(5.0)
        glBegin(GL_LINES)
        rad = math.radians(lp.effective_angle)
        glColor3f(*((0.9, 0.6, 0.1) if is_aligned else (0.8, 0.8, 0.8)))
        glVertex2f(center_x, center_y)
        glVertex2f(center_x + math.cos(rad) * radius, center_y + math.sin(rad) * radius)
        glEnd()

        if is_aligned:
            t.draw("SWEET SPOT FOUND! Press [SPACE]!", x1 + 53, y1 + 351, t.font_small, c.sweet_spot_text)


# ----------------------------------------------------------------------------- menus & overlays
class MenuRenderer:
    """Draws ``ui.Menu`` screens and the performance overlay with the HUD's text renderer."""

    def __init__(self, text: TextRenderer, layout: HudLayout, colors: HudColors):
        self.text = text
        self.layout = layout
        self.colors = colors

    def _begin(self) -> None:
        HudRenderer._begin_2d(self)          # same ortho/state setup

    def _end(self) -> None:
        HudRenderer._end_2d(self)

    def draw_menu(self, menu, dim: bool = True) -> None:
        c, t = self.colors, self.text
        w, h = self.layout.width, self.layout.height
        self._begin()
        if dim:
            fill_rect_2d(0, 0, w, h, (0.0, 0.0, 0.0, 0.55))
        first, rows = menu.visible()
        total = len(menu.items)
        panel_w, panel_h = 560, 120 + 34 * max(1, len(rows)) + (30 if menu.subtitle else 0)
        x1, y1 = (w - panel_w) // 2, max(40, (h - panel_h) // 2)
        fill_rect_2d(x1, y1, x1 + panel_w, y1 + panel_h, c.modal_panel)
        t.draw(menu.title, x1 + 30, y1 + 22, t.font, c.gold)
        if first > 0:
            t.draw(f"^ {first} more", x1 + panel_w - 110, y1 + 26, t.font_small, c.scroll_hint)
        y = y1 + 62
        if menu.subtitle:
            t.draw(menu.subtitle, x1 + 30, y, t.font_small, c.scroll_hint)
            y += 30
        for offset, item in enumerate(rows):
            idx = first + offset
            selected = idx == menu.cursor
            color = c.selected if selected else (c.white if item.enabled() else c.scroll_hint)
            t.draw(("> " if selected else "  ") + item.label, x1 + 30, y, t.font_small, color)
            value = item.display_value()
            if value:
                t.draw(value, x1 + 300, y, t.font_small, color)
            y += 34
        if first + len(rows) < total:
            t.draw(f"v {total - first - len(rows)} more", x1 + panel_w - 110, y1 + panel_h - 30, t.font_small, c.scroll_hint)
        t.draw(menu.footer, x1 + 30, y1 + panel_h - 30, t.font_small, c.scroll_hint)
        self._end()

    def draw_perf_overlay(self, profiler, lines_extra=()) -> None:
        c, t = self.colors, self.text
        self._begin()
        x1, y1, x2 = 360, 55, 710
        stats = profiler.stats()
        rows = [f"FPS {stats['fps']:.0f}   frame {stats['frame_ms']:.1f} ms   worst {stats['worst_ms']:.1f} ms"]
        rows += [f"  {name:<10} {ms:6.2f} ms" for name, ms in stats["phases"].items()]
        rows += list(lines_extra)
        height = 40 + 18 * len(rows) + 50
        fill_rect_2d(x1, y1, x2, y1 + height, (0.0, 0.0, 0.0, 0.7))
        t.draw("PERFORMANCE  [F3]", x1 + 10, y1 + 8, t.font_small, c.gold)
        for idx, row in enumerate(rows):
            t.draw(row, x1 + 10, y1 + 30 + idx * 18, t.font_small, c.white)
        # frame-time graph: one bar per frame, 33 ms full height
        gx, gy, gh = x1 + 10, y1 + height - 10, 40
        history = list(profiler.frame_history)[-(x2 - x1 - 20):]
        glLineWidth(1.0)
        glBegin(GL_LINES)
        for i, ms in enumerate(history):
            bar = min(gh, gh * ms / 33.3)
            glColor3f(0.3, 0.9, 0.3) if ms <= 16.7 else glColor3f(0.95, 0.6, 0.2) if ms <= 33.3 else glColor3f(0.95, 0.2, 0.2)
            glVertex2f(gx + i, gy)
            glVertex2f(gx + i, gy - bar)
        glEnd()
        self._end()
