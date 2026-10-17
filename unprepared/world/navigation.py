"""Grid-based navigation for NPCs.

The level's static geometry (walls, props) is rasterised once into a boolean
occupancy grid on the X/Z plane, inflated by the agent radius so paths keep
clear of corners.  Doors are overlaid per query: a doorway is passable for an
agent that can open it (or when it already stands open).  Paths are found
with A* on 8-connected cells (no corner cutting) and then simplified with a
line-of-sight string-pull so NPCs walk straight where they can.
"""
from __future__ import annotations

import heapq
import math
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from ..config import NavigationSettings
from ..core.math3d import BoundingBox3D, Vector3D
from ..entities import Door

Cell = Tuple[int, int]
_NEIGHBOURS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))


HEAD_HEIGHT = 1.9      # obstacles starting above this are walked under


class NavGrid:
    def __init__(self, obstacles: Iterable[BoundingBox3D], settings: NavigationSettings = NavigationSettings(),
                 walls: Iterable[BoundingBox3D] = ()):
        """``obstacles`` block movement; ``walls`` (a subset) are additionally treated as
        impassable when snapping a start/goal that lies inside furniture to free space."""
        self.settings = settings
        self.cell = settings.cell_size
        self.min_x, self.min_z, self.max_x, self.max_z = settings.bounds
        self.cols = int(math.ceil((self.max_x - self.min_x) / self.cell))
        self.rows = int(math.ceil((self.max_z - self.min_z) / self.cell))
        self.static_blocked = np.zeros((self.cols, self.rows), dtype=bool)
        self.wall_mask = np.zeros((self.cols, self.rows), dtype=bool)
        for box in obstacles:
            if box.min_point.y < HEAD_HEIGHT:          # a lintel or a window piece up a wall is no obstacle on the ground
                self._rasterise(self.static_blocked, box, inflate=settings.agent_radius)
        for box in walls:
            if box.min_point.y < HEAD_HEIGHT:
                self._rasterise(self.wall_mask, box, inflate=settings.agent_radius)

    # ------------------------------------------------------------------ grid <-> world
    def to_cell(self, x: float, z: float) -> Cell:
        ix = int((x - self.min_x) / self.cell)
        iz = int((z - self.min_z) / self.cell)
        return (min(max(ix, 0), self.cols - 1), min(max(iz, 0), self.rows - 1))

    def to_world(self, cell: Cell, y: float = 0.0) -> Vector3D:
        return Vector3D(self.min_x + (cell[0] + 0.5) * self.cell, y, self.min_z + (cell[1] + 0.5) * self.cell)

    def _rasterise(self, grid: np.ndarray, box: BoundingBox3D, inflate: float = 0.0) -> None:
        x0, z0 = self.to_cell(box.min_point.x - inflate, box.min_point.z - inflate)
        x1, z1 = self.to_cell(box.max_point.x + inflate, box.max_point.z + inflate)
        grid[x0:x1 + 1, z0:z1 + 1] = True

    def occupancy(self, doors: Sequence[Door] = (), can_open: Optional[Callable[[Door], bool]] = None) -> np.ndarray:
        """Static obstacles plus every door this agent cannot pass."""
        grid = self.static_blocked.copy()
        for door in doors:
            passable = door.is_open or (can_open is not None and can_open(door))
            if not passable:
                self._rasterise(grid, door.get_bounding_box())
        return grid

    def is_blocked(self, x: float, z: float, grid: Optional[np.ndarray] = None) -> bool:
        ix, iz = self.to_cell(x, z)
        return bool((self.static_blocked if grid is None else grid)[ix, iz])

    def nearest_free(self, cell: Cell, grid: np.ndarray, max_radius: int = 8) -> Optional[Cell]:
        """Closest free cell to ``cell``, reached by crossing furniture (a bed the NPC lies on)
        but never by going through a wall - so a bed against a wall snaps to the room, not outside."""
        if not grid[cell]:
            return cell
        frontier: List[Tuple[float, int, Cell]] = [(0.0, 0, cell)]
        seen = {cell}
        counter = 1
        while frontier:
            cost, _, current = heapq.heappop(frontier)
            if not grid[current]:
                return current
            if cost > max_radius * 2:
                break
            for dx, dz in _NEIGHBOURS:
                nb = (current[0] + dx, current[1] + dz)
                if nb in seen or not (0 <= nb[0] < self.cols and 0 <= nb[1] < self.rows) or self.wall_mask[nb]:
                    continue
                seen.add(nb)
                heapq.heappush(frontier, (cost + (math.sqrt(2) if dx and dz else 1.0), counter, nb))
                counter += 1
        return None

    # ------------------------------------------------------------------ search
    def find_path(self, start: Vector3D, goal: Vector3D, doors: Sequence[Door] = (),
                  can_open: Optional[Callable[[Door], bool]] = None) -> List[Vector3D]:
        """World-space waypoints from ``start`` to ``goal`` (excluding start, ending exactly
        at ``goal``). Empty if no route exists."""
        grid = self.occupancy(doors, can_open)
        s = self.nearest_free(self.to_cell(start.x, start.z), grid)
        g = self.nearest_free(self.to_cell(goal.x, goal.z), grid)
        if s is None or g is None:
            return []
        cells = self._astar(s, g, grid)
        if cells is None:
            return []
        cells = self._string_pull(cells, grid)
        waypoints = [self.to_world(c, goal.y) for c in cells[1:]]
        if waypoints:
            waypoints[-1] = Vector3D(goal.x, goal.y, goal.z)
        else:
            waypoints = [Vector3D(goal.x, goal.y, goal.z)]
        return waypoints

    def _astar(self, start: Cell, goal: Cell, grid: np.ndarray) -> Optional[List[Cell]]:
        def h(c: Cell) -> float:
            dx, dz = abs(c[0] - goal[0]), abs(c[1] - goal[1])
            return (dx + dz) + (math.sqrt(2) - 2) * min(dx, dz)

        open_heap: List[Tuple[float, int, Cell]] = [(h(start), 0, start)]
        came_from = {start: None}
        g_score = {start: 0.0}
        counter = 1
        while open_heap:
            _, _, current = heapq.heappop(open_heap)
            if current == goal:
                path = []
                while current is not None:
                    path.append(current)
                    current = came_from[current]
                return path[::-1]
            cx, cz = current
            for dx, dz in _NEIGHBOURS:
                nx, nz = cx + dx, cz + dz
                if not (0 <= nx < self.cols and 0 <= nz < self.rows) or grid[nx, nz]:
                    continue
                if dx and dz and (grid[cx + dx, cz] or grid[cx, cz + dz]):
                    continue    # no cutting corners through blocked cells
                tentative = g_score[current] + (math.sqrt(2) if dx and dz else 1.0)
                nb = (nx, nz)
                if tentative < g_score.get(nb, float("inf")):
                    g_score[nb] = tentative
                    came_from[nb] = current
                    heapq.heappush(open_heap, (tentative + h(nb), counter, nb))
                    counter += 1
        return None

    def _line_clear(self, a: Cell, b: Cell, grid: np.ndarray) -> bool:
        """True if a straight walk between the centres of ``a`` and ``b`` touches only
        free cells (diagonal squeezes between two blocked cells count as blocked)."""
        steps = max(1, int(4 * max(abs(b[0] - a[0]), abs(b[1] - a[1]))))
        prev = a
        for i in range(1, steps + 1):
            t = i / steps
            cx = int(math.floor(a[0] + 0.5 + (b[0] - a[0]) * t))
            cz = int(math.floor(a[1] + 0.5 + (b[1] - a[1]) * t))
            cx, cz = min(max(cx, 0), self.cols - 1), min(max(cz, 0), self.rows - 1)
            if grid[cx, cz]:
                return False
            if cx != prev[0] and cz != prev[1] and (grid[prev[0], cz] or grid[cx, prev[1]]):
                return False
            prev = (cx, cz)
        return True

    def _string_pull(self, cells: List[Cell], grid: np.ndarray) -> List[Cell]:
        if len(cells) <= 2:
            return cells
        result = [cells[0]]
        anchor = 0
        i = 2
        while i < len(cells):
            if not self._line_clear(cells[anchor], cells[i], grid):
                result.append(cells[i - 1])
                anchor = i - 1
            i += 1
        result.append(cells[-1])
        return result
