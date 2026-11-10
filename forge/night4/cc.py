"""Connected components on a boolean mask — numpy + Python only (the Windows venv has no scipy).

Run-length labelling: each row is cut into runs of True; runs in neighbouring rows that touch are joined with a
union-find. Fast enough for a 2048×2048 sprite sheet (a few hundred thousand runs at worst)."""
from __future__ import annotations
import numpy as np


def runs(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(row, start, end) of every run of True; end is exclusive."""
    m = np.asarray(mask, dtype=bool)
    h, w = m.shape
    pad = np.zeros((h, w + 2), dtype=np.int8)
    pad[:, 1:-1] = m
    d = np.diff(pad, axis=1)
    ys, xs = np.nonzero(d == 1)
    ye, xe = np.nonzero(d == -1)
    # np.nonzero walks row-major, so starts and ends pair up in order
    return ys.astype(np.int64), xs.astype(np.int64), xe.astype(np.int64)


def label(mask: np.ndarray, connectivity: int = 8) -> tuple[np.ndarray, int]:
    """Label image (int32, 0 = background, 1..n) and n."""
    m = np.asarray(mask, dtype=bool)
    h, w = m.shape
    ry, rx0, rx1 = runs(m)
    n = len(ry)
    lab = np.zeros((h, w), dtype=np.int32)
    if n == 0:
        return lab, 0
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    grow = 1 if connectivity == 8 else 0
    row_start = np.searchsorted(ry, np.arange(h + 1))
    for y in range(1, h):
        a0, a1 = row_start[y - 1], row_start[y]
        b0, b1 = row_start[y], row_start[y + 1]
        if a0 == a1 or b0 == b1:
            continue
        i, j = a0, b0
        while i < a1 and j < b1:
            # runs i (row above) and j (this row) touch if their spans overlap (± 1 for diagonals)
            if rx0[i] < rx1[j] + grow and rx0[j] < rx1[i] + grow:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[max(ri, rj)] = min(ri, rj)
            if rx1[i] < rx1[j]:
                i += 1
            else:
                j += 1
    roots = np.fromiter((find(i) for i in range(n)), dtype=np.int64, count=n)
    uniq, ids = np.unique(roots, return_inverse=True)
    ids = ids.astype(np.int32) + 1
    for k in range(n):
        lab[ry[k], rx0[k]:rx1[k]] = ids[k]
    return lab, int(len(uniq))


def boxes(lab: np.ndarray, n: int) -> list[dict]:
    """[{id, bbox [x0,y0,x1,y1] (exclusive), area}] for labels 1..n."""
    if n == 0:
        return []
    ys, xs = np.nonzero(lab)
    ls = lab[ys, xs]
    area = np.bincount(ls, minlength=n + 1)
    x0 = np.full(n + 1, 1 << 30); y0 = np.full(n + 1, 1 << 30)
    x1 = np.full(n + 1, -1); y1 = np.full(n + 1, -1)
    np.minimum.at(x0, ls, xs); np.minimum.at(y0, ls, ys)
    np.maximum.at(x1, ls, xs); np.maximum.at(y1, ls, ys)
    return [{"id": i, "bbox": [int(x0[i]), int(y0[i]), int(x1[i]) + 1, int(y1[i]) + 1], "area": int(area[i])}
            for i in range(1, n + 1)]
