"""The plan's grid, its seeded randomness, and the geometry the generator and the checks share."""
from __future__ import annotations
import hashlib, random
from collections import deque
from dataclasses import dataclass

from . import tiles as T


def rng_for(*parts) -> random.Random:
    """A Random seeded from the parts' text — the same parts give the same numbers on every computer."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return random.Random(int(h[:16], 16))


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def x2(self) -> int:          # exclusive
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h

    @property
    def cx(self) -> int:
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        return self.y + self.h // 2

    def cells(self):
        for yy in range(self.y, self.y2):
            for xx in range(self.x, self.x2):
                yield xx, yy

    def border(self):
        for xx in range(self.x, self.x2):
            yield xx, self.y
            if self.h > 1:
                yield xx, self.y2 - 1
        for yy in range(self.y + 1, self.y2 - 1):
            yield self.x, yy
            if self.w > 1:
                yield self.x2 - 1, yy

    def grow(self, n: int) -> "Rect":
        return Rect(self.x - n, self.y - n, self.w + 2 * n, self.h + 2 * n)

    def overlaps(self, o: "Rect") -> bool:
        return self.x < o.x2 and o.x < self.x2 and self.y < o.y2 and o.y < self.y2

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x2 and self.y <= y < self.y2

    def as_list(self) -> list:
        return [self.x, self.y, self.w, self.h]


class Grid:
    def __init__(self, w: int, h: int, fill: str = T.GROUND):
        self.w, self.h = w, h
        self.c = [[fill] * w for _ in range(h)]

    def copy(self) -> "Grid":
        g = Grid(self.w, self.h)
        g.c = [row[:] for row in self.c]
        return g

    def ok(self, x: int, y: int) -> bool:
        return 0 <= x < self.w and 0 <= y < self.h

    def get(self, x: int, y: int, default: str = T.ROCK) -> str:
        return self.c[y][x] if self.ok(x, y) else default

    def set(self, x: int, y: int, t: str) -> None:
        if self.ok(x, y):
            self.c[y][x] = t

    def fill(self, r: Rect, t: str, only: set | frozenset | None = None) -> None:
        for x, y in r.cells():
            if self.ok(x, y) and (only is None or self.c[y][x] in only):
                self.c[y][x] = t

    def outline(self, r: Rect, t: str) -> None:
        for x, y in r.border():
            self.set(x, y, t)

    def line(self, x0: int, y0: int, x1: int, y1: int, t: str, width: int = 1, only=None) -> None:
        """An axis-aligned L (horizontal first) of the given width."""
        sx = 1 if x1 >= x0 else -1
        for x in range(x0, x1 + sx, sx):
            for k in range(width):
                if only is None or self.get(x, y0 + k) in only:
                    self.set(x, y0 + k, t)
        sy = 1 if y1 >= y0 else -1
        for y in range(y0, y1 + sy, sy):
            for k in range(width):
                if only is None or self.get(x1 + k, y) in only:
                    self.set(x1 + k, y, t)

    def border_wall(self, t: str = T.WALL) -> None:
        self.outline(Rect(0, 0, self.w, self.h), t)

    def walkable(self, x: int, y: int) -> bool:
        return self.ok(x, y) and self.c[y][x] in T.WALKABLE

    def n4(self, x: int, y: int):
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if self.ok(nx, ny):
                yield nx, ny

    def flood(self, start: tuple[int, int]) -> set:
        """Every walkable cell reachable from start (4-way)."""
        if not self.walkable(*start):
            return set()
        seen = {start}
        q = deque([start])
        while q:
            x, y = q.popleft()
            for n in self.n4(x, y):
                if n not in seen and self.walkable(*n):
                    seen.add(n)
                    q.append(n)
        return seen

    def path(self, a: tuple[int, int], goal_fn, passable) -> list | None:
        """Shortest 4-way path from a to the first cell where goal_fn is true, through cells passable(x, y)."""
        prev = {a: None}
        q = deque([a])
        while q:
            p = q.popleft()
            if goal_fn(*p) and p != a:
                out = []
                while p is not None:
                    out.append(p)
                    p = prev[p]
                return out[::-1]
            for n in self.n4(*p):
                if n not in prev and (passable(*n) or goal_fn(*n)):
                    prev[n] = p
                    q.append(n)
        return None

    def sees(self, a: tuple[int, int], b: tuple[int, int], extra_clear: set | None = None) -> bool:
        """Line of sight from a to b (Bresenham); walls, roofs and rock block it. The end cells don't count."""
        (x0, y0), (x1, y1) = a, b
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        x, y = x0, y0
        while (x, y) != (x1, y1):
            if (x, y) != a and self.get(x, y) in T.SIGHT_BLOCKING and not (extra_clear and (x, y) in extra_clear):
                return False
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy
        return True

    def count(self, t: str) -> int:
        return sum(row.count(t) for row in self.c)

    def rows(self) -> list[list[str]]:
        return [row[:] for row in self.c]

    def mirror_x(self) -> None:
        """Copy the left half onto the right half, mirrored."""
        for y in range(self.h):
            for x in range(self.w // 2):
                self.c[y][self.w - 1 - x] = self.c[y][x]
