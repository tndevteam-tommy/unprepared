"""Performance monitoring: per-phase frame timing, FPS, history for the overlay graph,
and the heuristics that pick a graphics preset for the machine.
"""
from __future__ import annotations

import time
from collections import OrderedDict, deque
from contextlib import contextmanager
from typing import Deque, Dict, Iterator, List, Optional, Tuple


class FrameProfiler:
    """Accumulates wall-clock time per named phase of a frame.

        with profiler.phase("update"):
            game.update(...)
        profiler.end_frame()
    """

    def __init__(self, history: int = 240, clock=time.perf_counter):
        self.clock = clock
        self.history_size = history
        self.phase_ms: "OrderedDict[str, float]" = OrderedDict()         # current frame
        self.last_phase_ms: "OrderedDict[str, float]" = OrderedDict()    # last completed frame
        self.avg_phase_ms: Dict[str, float] = {}
        self.frame_history: Deque[float] = deque(maxlen=history)
        self.frames = 0
        self.fps = 0.0
        self._frame_start = clock()
        self._open: List[Tuple[str, float]] = []

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        start = self.clock()
        try:
            yield
        finally:
            self.phase_ms[name] = self.phase_ms.get(name, 0.0) + (self.clock() - start) * 1000.0

    def end_frame(self) -> float:
        """Close the frame; returns its total duration in milliseconds."""
        now = self.clock()
        total_ms = (now - self._frame_start) * 1000.0
        self._frame_start = now
        self.frames += 1
        self.frame_history.append(total_ms)
        self.last_phase_ms = OrderedDict(self.phase_ms)
        for name, ms in self.phase_ms.items():
            prev = self.avg_phase_ms.get(name, ms)
            self.avg_phase_ms[name] = prev * 0.9 + ms * 0.1
        self.phase_ms = OrderedDict()
        if total_ms > 0:
            inst = 1000.0 / total_ms
            self.fps = inst if self.fps == 0.0 else self.fps * 0.9 + inst * 0.1
        return total_ms

    @property
    def average_frame_ms(self) -> float:
        return sum(self.frame_history) / len(self.frame_history) if self.frame_history else 0.0

    @property
    def worst_frame_ms(self) -> float:
        return max(self.frame_history) if self.frame_history else 0.0

    def stats(self) -> dict:
        return {
            "fps": round(self.fps, 1),
            "frame_ms": round(self.average_frame_ms, 2),
            "worst_ms": round(self.worst_frame_ms, 2),
            "frames": self.frames,
            "phases": {name: round(ms, 2) for name, ms in self.avg_phase_ms.items()},
        }

    def reset(self) -> None:
        self.frame_history.clear()
        self.avg_phase_ms.clear()
        self.fps = 0.0
        self.frames = 0
        self._frame_start = self.clock()


SOFTWARE_RENDERERS = ("llvmpipe", "softpipe", "swrast", "mesa offscreen", "microsoft basic render", "gdi generic")


def is_software_renderer(renderer_name: Optional[str]) -> bool:
    name = (renderer_name or "").lower()
    return any(tag in name for tag in SOFTWARE_RENDERERS)


def recommend_quality(frame_ms: float, renderer_name: Optional[str] = None,
                      high_budget_ms: float = 10.0, medium_budget_ms: float = 22.0) -> str:
    """Pick a preset from a measured frame time (of the *high* preset) and the GL renderer string."""
    if is_software_renderer(renderer_name):
        return "low"
    if frame_ms <= high_budget_ms:
        return "high"
    if frame_ms <= medium_budget_ms:
        return "medium"
    return "low"
