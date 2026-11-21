"""A DTED Level 0 reader (BUILD 77 part 1) — the forge's own, numpy only.

A cell is one degree square, named by its south-west corner (`w078/n38.dt0`, either case), loose in a folder or inside a
zip (read straight from it; nothing is unpacked). Its layout (MIL-PRF-89020B):

    UHL   80 bytes   "UHL1", origin longitude and latitude (DDDMMSSH), the post spacing in tenths of a second, the
                     number of longitude lines and of posts on each
    DSI  648 bytes   among much else, the product level ("DTED0" at byte 59)
    ACC 2700 bytes
    then one record a longitude line, west to east: 0xAA, block count (3), longitude count (2), latitude count (2),
                     the posts south to north as big-endian 16-bit SIGN-AND-MAGNITUDE (not two's complement), and a
                     4-byte checksum: the sum of every byte of the record before it.

The null post is -32767; it is kept as null (NaN), never as a pit. The spacing is read from each cell's own header (it
widens with latitude in DTED's zones). Every record's checksum is verified; a bad cell is reported and skipped. Only
Level 0 is read: a Level 1 or 2 file is skipped and reported, never read.
"""
from __future__ import annotations

import io
import math
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

HEADER = 80 + 648 + 2700
NULL = -32767
CELL_RE = re.compile(r"(?:^|/)([ew])(\d{3})/([ns])(\d{2})\.dt([012])$", re.I)
M_PER_DEG_LAT = 110_574.0
M_PER_DEG_LON_EQ = 111_320.0


class DtedError(ValueError):
    pass


def sign_magnitude(raw: np.ndarray) -> np.ndarray:
    """Big-endian 16-bit sign-and-magnitude words (uint16) as signed heights: the top bit is the sign."""
    raw = raw.astype(np.int32)
    mag = raw & 0x7FFF
    return np.where(raw & 0x8000, -mag, mag)


def to_sign_magnitude(h: np.ndarray) -> np.ndarray:
    """The inverse (for tests and for writing synthetic cells)."""
    h = np.asarray(h, dtype=np.int32)
    return (np.where(h < 0, 0x8000, 0) | np.abs(h)).astype(">u2")


def _dms(s: str) -> float:
    """DDDMMSSH (longitude) or DDMMSSH (latitude) to signed degrees."""
    s = s.strip()
    hemi = s[-1].upper()
    digits = s[:-1]
    d, m, sec = int(digits[:-4]), int(digits[-4:-2]), int(digits[-2:])
    v = d + m / 60 + sec / 3600
    return -v if hemi in "WS" else v


@dataclass
class Cell:
    lat0: float                 # south edge
    lon0: float                 # west edge
    dlat_s: float               # post spacing in arc-seconds, north-south
    dlon_s: float               # ... east-west
    grid: np.ndarray            # [n_lon, n_lat] metres, NaN where null; [0, 0] is the south-west post
    level: int = 0
    name: str = ""
    nulls: int = 0

    @property
    def n_lon(self) -> int:
        return self.grid.shape[0]

    @property
    def n_lat(self) -> int:
        return self.grid.shape[1]

    def height(self, lat: float, lon: float) -> float | None:
        """Bilinear between the four posts round the point; nulls left out (None when all four are null)."""
        fx = (lon - self.lon0) * 3600.0 / self.dlon_s
        fy = (lat - self.lat0) * 3600.0 / self.dlat_s
        if fx < -1e-9 or fy < -1e-9 or fx > self.n_lon - 1 + 1e-9 or fy > self.n_lat - 1 + 1e-9:
            return None
        i0, j0 = min(int(math.floor(fx)), self.n_lon - 2), min(int(math.floor(fy)), self.n_lat - 2)
        tx, ty = fx - i0, fy - j0
        corners = [(self.grid[i0, j0], (1 - tx) * (1 - ty)), (self.grid[i0 + 1, j0], tx * (1 - ty)),
                   (self.grid[i0, j0 + 1], (1 - tx) * ty), (self.grid[i0 + 1, j0 + 1], tx * ty)]
        good = [(h, w) for h, w in corners if not np.isnan(h)]
        if not good:
            return None
        sw = sum(w for _, w in good)
        if sw <= 1e-12:
            return float(np.mean([h for h, _ in good]))
        return float(sum(h * w for h, w in good) / sw)


def read_cell(data: bytes, name: str = "") -> Cell:
    """One cell from its bytes. Raises DtedError (a bad header, a bad checksum, a level that isn't 0)."""
    if len(data) < HEADER + 12 or data[:4] != b"UHL1":
        raise DtedError(f"{name}: not a DTED cell (no UHL header)")
    uhl = data[:80].decode("ascii", "replace")
    lon0, lat0 = _dms(uhl[4:12]), _dms(uhl[12:20])
    dlon_s, dlat_s = int(uhl[20:24]) / 10.0, int(uhl[24:28]) / 10.0
    n_lon, n_lat = int(uhl[47:51]), int(uhl[51:55])
    dsi = data[80:80 + 648]
    if dsi[:3] != b"DSI":
        raise DtedError(f"{name}: no DSI header")
    m = re.search(rb"DTED(\d)", dsi[59:64])
    level = int(m.group(1)) if m else -1
    if level != 0:
        raise DtedError(f"{name}: DTED level {level} — only Level 0 is read")
    rec = 12 + 2 * n_lat
    need = HEADER + n_lon * rec
    if len(data) < need:
        raise DtedError(f"{name}: cut short ({len(data)} bytes, {need} needed)")
    body = np.frombuffer(data, dtype=np.uint8, count=n_lon * rec, offset=HEADER).reshape(n_lon, rec)
    if not (body[:, 0] == 0xAA).all():
        raise DtedError(f"{name}: a record does not start with its sentinel")
    want = body[:, rec - 4:].astype(np.uint32)
    want = (want[:, 0] << 24) | (want[:, 1] << 16) | (want[:, 2] << 8) | want[:, 3]
    got = body[:, :rec - 4].astype(np.uint64).sum(axis=1).astype(np.uint32)
    bad = np.nonzero(want != got)[0]
    if len(bad):
        raise DtedError(f"{name}: checksum wrong on {len(bad)} record(s) (first: longitude line {int(bad[0])})")
    raw = body[:, 8:8 + 2 * n_lat].copy().view(">u2").reshape(n_lon, n_lat)
    h = sign_magnitude(raw).astype(np.float64)
    nulls = int((h == NULL).sum())
    h[h == NULL] = np.nan
    return Cell(lat0=lat0, lon0=lon0, dlat_s=dlat_s, dlon_s=dlon_s, grid=h, level=level, name=name, nulls=nulls)


def write_cell(path: Path, lat0: int, lon0: int, heights: np.ndarray, level: int = 0, spacing_s=(30.0, 30.0),
               corrupt_record: int | None = None) -> Path:
    """A synthetic cell (for the tests): heights [n_lon, n_lat] in metres (NaN = null)."""
    n_lon, n_lat = heights.shape

    def dms(v, lon):
        h = ("E" if v >= 0 else "W") if lon else ("N" if v >= 0 else "S")
        v = abs(v)
        return f"{int(v):03d}0000{h}"              # DDDMMSSH for both (the real header pads latitude to three)
    uhl = (f"UHL1{dms(lon0, True)}{dms(lat0, False)}{int(spacing_s[1] * 10):04d}{int(spacing_s[0] * 10):04d}"
           f"0012U  {'':12}{n_lon:04d}{n_lat:04d}0{'':24}")
    assert len(uhl) == 80, len(uhl)
    dsi = bytearray(b" " * 648)
    dsi[:4] = b"DSIU"
    dsi[59:64] = f"DTED{level}".encode()
    acc = b"ACC" + b" " * 2697
    out = io.BytesIO()
    out.write(uhl.encode("ascii"))
    out.write(bytes(dsi))
    out.write(acc)
    h = np.where(np.isnan(heights), NULL, np.round(heights)).astype(np.int32)
    for i in range(n_lon):
        rec = bytearray()
        rec += b"\xaa" + i.to_bytes(3, "big") + i.to_bytes(2, "big") + (0).to_bytes(2, "big")
        rec += to_sign_magnitude(h[i]).tobytes()
        cs = sum(rec) & 0xFFFFFFFF
        if corrupt_record == i:
            cs ^= 1
        rec += cs.to_bytes(4, "big")
        out.write(bytes(rec))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out.getvalue())
    return path


def cell_key(lat: float, lon: float) -> tuple[int, int]:
    return int(math.floor(lat)), int(math.floor(lon))


@dataclass
class Library:
    """Every Level 0 cell a folder holds, loose or inside zips; cells read on demand and kept."""
    root: Path
    index: dict = field(default_factory=dict)          # (lat, lon) -> (zip path or None, member or file path)
    skipped: list = field(default_factory=list)        # (name, why)
    bad: list = field(default_factory=list)
    _cache: dict = field(default_factory=dict)
    _zips: dict = field(default_factory=dict)

    @classmethod
    def open(cls, root) -> "Library":
        lib = cls(Path(root))
        if not lib.root.exists():
            return lib
        files = [lib.root] if lib.root.is_file() else sorted(lib.root.rglob("*"))
        for p in files:
            if p.is_file() and p.suffix.lower() == ".zip":
                with zipfile.ZipFile(p) as z:
                    for n in z.namelist():
                        lib._add(n, (p, n))
            elif p.is_file():
                lib._add(p.as_posix(), (None, p))
        return lib

    def _add(self, name: str, where) -> None:
        m = CELL_RE.search(name)
        if not m:
            return
        ew, lon, ns, lat, level = m.groups()
        if level != "0":
            self.skipped.append((name, f"DTED level {level} — only Level 0 is read"))
            return
        key = (int(lat) * (1 if ns.lower() == "n" else -1), int(lon) * (1 if ew.lower() == "e" else -1))
        self.index.setdefault(key, where)

    @property
    def found(self) -> bool:
        return bool(self.index)

    def summary(self) -> dict:
        return {"root": str(self.root), "cells": len(self.index), "skipped": len(self.skipped), "bad": len(self.bad),
                "zips": sorted({str(z) for z, _ in self.index.values() if z is not None})}

    def cell(self, lat_i: int, lon_i: int) -> Cell | None:
        key = (lat_i, lon_i)
        if key in self._cache:
            return self._cache[key]
        where = self.index.get(key)
        c = None
        if where is not None:
            zp, member = where
            try:
                if zp is None:
                    data = Path(member).read_bytes()
                else:
                    z = self._zips.get(zp) or zipfile.ZipFile(zp)
                    self._zips[zp] = z
                    data = z.read(member)
                c = read_cell(data, str(member))
            except DtedError as e:
                self.bad.append((str(member), str(e)))
                c = None
        self._cache[key] = c
        return c

    def height_at(self, lat: float, lon: float) -> tuple[float | None, str | None]:
        """The height at a point (bilinear, nulls ignored) and the cell that answered — None where there is no cell
        (DTED has no sea: open ocean has no cells)."""
        c = self.cell(*cell_key(lat, lon))
        if c is None:
            return None, None
        return c.height(lat, lon), c.name

    def window(self, south: float, west: float, north: float, east: float, posts: int = 512,
               sea: float | None = 0.0) -> dict:
        """A height grid over the window, cells stitched, resampled to square metres at the window's centre (so it is not
        stretched east–west). `posts` is the longer side. Returns {"h" [rows, cols] north at the top, NaN where no data
        (filled with `sea` when it is a number), "m_per_post", "size_m", "cells", "missing"}."""
        if not (north > south and east > west):
            raise DtedError("a window needs north > south and east > west")
        latc = (south + north) / 2
        w_m = (east - west) * M_PER_DEG_LON_EQ * math.cos(math.radians(latc))
        h_m = (north - south) * M_PER_DEG_LAT
        step = max(w_m, h_m) / max(posts - 1, 1)
        nx, ny = max(2, int(round(w_m / step)) + 1), max(2, int(round(h_m / step)) + 1)
        lons = np.linspace(west, east, nx)
        lats = np.linspace(north, south, ny)
        H = np.full((ny, nx), np.nan)
        used, missing = set(), set()
        for la_i in range(int(math.floor(south)), int(math.floor(north - 1e-12)) + 1):
            for lo_i in range(int(math.floor(west)), int(math.floor(east - 1e-12)) + 1):
                c = self.cell(la_i, lo_i)
                rows = np.nonzero((lats >= la_i) & (lats <= la_i + 1))[0]
                cols = np.nonzero((lons >= lo_i) & (lons <= lo_i + 1))[0]
                if not len(rows) or not len(cols):
                    continue
                if c is None:
                    missing.add((la_i, lo_i))
                    continue
                used.add(c.name)
                fx = (lons[cols] - c.lon0) * 3600.0 / c.dlon_s
                fy = (lats[rows] - c.lat0) * 3600.0 / c.dlat_s
                H[np.ix_(rows, cols)] = _bilinear(c.grid, fx, fy)
        if sea is not None:
            H = np.where(np.isnan(H), float(sea), H)
        return {"h": H, "m_per_post": step, "size_m": {"width": round(w_m), "height": round(h_m)}, "cells": sorted(used),
                "missing": sorted(missing), "lats": lats, "lons": lons,
                "window": {"south": south, "west": west, "north": north, "east": east}}


def _bilinear(grid: np.ndarray, fx: np.ndarray, fy: np.ndarray) -> np.ndarray:
    """grid [n_lon, n_lat] sampled at fractional (fx along longitude, fy along latitude) — out [len(fy), len(fx)], nulls
    left out of each average."""
    nlon, nlat = grid.shape
    fx = np.clip(fx, 0, nlon - 1)
    fy = np.clip(fy, 0, nlat - 1)
    i0 = np.minimum(np.floor(fx).astype(int), nlon - 2)
    j0 = np.minimum(np.floor(fy).astype(int), nlat - 2)
    tx = (fx - i0)[None, :]
    ty = (fy - j0)[:, None]
    g = np.nan_to_num(grid)
    v = (~np.isnan(grid)).astype(np.float64)
    def at(di, dj, a):
        return a[(i0 + di)[None, :], (j0 + dj)[:, None]]
    w = [(1 - tx) * (1 - ty), tx * (1 - ty), (1 - tx) * ty, tx * ty]
    num = sum(wk * at(di, dj, g) * at(di, dj, v) for wk, (di, dj) in zip(w, ((0, 0), (1, 0), (0, 1), (1, 1))))
    den = sum(wk * at(di, dj, v) for wk, (di, dj) in zip(w, ((0, 0), (1, 0), (0, 1), (1, 1))))
    out = np.where(den > 1e-12, num / np.maximum(den, 1e-12), np.nan)
    return out
