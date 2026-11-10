"""`kit check` — is this scene kit safe to approve? (Night 3, G5)

    python -m forge kit check <job-id> [--map <id>] [--game turing_accords]
        → pass / warn / fail per line, out/<id>/check.json and check.png

A kit can look right and be wrong. Checked, each with a plain reason:
  slots     all six files present; each at the size wanted.json asks for (the painting's size when the map is unknown;
            _back may be wider by the overscan)
  normals   decodes to unit-ish vectors; mean direction faces the camera ("up" in tangent space, z ≥ 0.6); not flat
            (some x/y variation); no banding — the comb test: a smooth surface fills its histogram, terraces leave
            evenly spaced empty bins
  depth     uses most of its range (p1–p99 ≥ 35 % of full scale); near at the bottom of the frame more than at the
            top (ground plane where the game expects it); the share of the frame that reads as ground is plausible
  emissive  share of the frame that glows; warn over 15 % ("this will glow like a billboard")
  layers    _back has no holes (no transparency, no magenta); the over-plane covers a plausible share (warn > 40 %)
  map       when the game's map file is readable: walk rings, doors and spawns drawn over the painting, and a warning
            for any door/spawn whose neighbourhood in the depth map is far from the ground plane there
`approve --set` runs this first and refuses on a *fail* (never on a *warn*).
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import config as cfgmod

SLOTS = {"_main": "scene.png", "_n": "scene_n.png", "_e": "scene_e.png", "_back": "scene_back.png",
         "_over": "scene_over.png", "_depth": "scene_depth.png"}
PASS, WARN, FAIL = "pass", "warn", "fail"
COL = {PASS: (70, 180, 90), WARN: (230, 170, 50), FAIL: (220, 60, 60)}


def _line(check, status, msg, **data):
    return {"check": check, "status": status, "message": msg, **data}


def _arr16(img: Image.Image) -> np.ndarray:
    a = np.asarray(img)
    if a.dtype == np.uint8:
        a = a[..., 0] if a.ndim == 3 else a
        return a.astype(np.float64) / 255.0
    return a.astype(np.float64) / 65535.0


def comb_score(channel: np.ndarray, lo_q: float = 2, hi_q: float = 98) -> float:
    """Fraction of empty histogram bins inside the populated range — 0 for a smooth surface, high for terraces."""
    v = channel.astype(np.int64).ravel()
    lo, hi = np.percentile(v, lo_q), np.percentile(v, hi_q)
    if hi - lo < 8:
        return 0.0
    h = np.bincount(v, minlength=256)[int(lo):int(hi) + 1]
    return float((h == 0).mean())


def check_normals(img: Image.Image) -> list[dict]:
    a = np.asarray(img.convert("RGB"), dtype=np.float64)
    v = a / 127.5 - 1.0
    out = []
    mean = v.reshape(-1, 3).mean(axis=0)
    z = float(mean[2])
    out.append(_line("normals.facing", PASS if z >= 0.6 else (WARN if z >= 0.3 else FAIL),
                     f"mean normal z = {z:.2f} (faces the camera when ≥ 0.6)" + ("" if z >= 0.3 else " — inverted or not a normal map?"),
                     mean=[round(float(x), 3) for x in mean]))
    sxy = float(v[..., :2].std())
    out.append(_line("normals.flat", PASS if sxy >= 0.04 else WARN, f"x/y variation {sxy:.3f}" + ("" if sxy >= 0.04 else " — nearly flat: lights will show no shape")))
    comb = max(comb_score(a[..., 0]), comb_score(a[..., 1]))
    out.append(_line("normals.banding", PASS if comb < 0.25 else (WARN if comb < 0.5 else FAIL),
                     f"histogram comb {comb:.2f}" + ("" if comb < 0.25 else " — terraces: the depth was 8-bit or over-sharpened (contour lines under lights)")))
    return out


def ground_mask(depth: np.ndarray) -> np.ndarray:
    """Pixels whose depth falls smoothly toward the top of the frame — a receding floor. Cheap, good enough to spot a
    floor the depth model read as a wall."""
    gy = np.zeros_like(depth)
    gy[1:-1] = depth[2:] - depth[:-2]           # positive: nearer below
    gx = np.zeros_like(depth)
    gx[:, 1:-1] = depth[:, 2:] - depth[:, :-2]
    return (gy > 0.0005) & (np.abs(gx) < gy * 2.5)


def check_depth(d: np.ndarray) -> tuple[list[dict], np.ndarray]:
    out = []
    p1, p99 = np.percentile(d, 1), np.percentile(d, 99)
    span = float(p99 - p1)
    out.append(_line("depth.range", PASS if span >= 0.35 else (WARN if span >= 0.15 else FAIL),
                     f"uses {span:.0%} of its range (p1–p99)" + ("" if span >= 0.35 else " — flat depth: parallax and lights will read wrong")))
    h = d.shape[0]
    bot, top = float(d[int(h * 0.8):].mean()), float(d[:int(h * 0.2)].mean())
    out.append(_line("depth.ground", PASS if bot > top else FAIL,
                     f"bottom of frame {bot:.2f} vs top {top:.2f} (white = near; the floor should be nearer at the bottom)"
                     + ("" if bot > top else " — inverted, or the floor read as a wall")))
    g = ground_mask(d)
    share = float(g[int(h * 0.5):].mean())
    out.append(_line("depth.ground_share", PASS if share >= 0.15 else WARN,
                     f"{share:.0%} of the lower half reads as receding ground" + ("" if share >= 0.15 else " — little floor found; check spawns sit on floor")))
    return out, g


def check_emissive(img: Image.Image, limit: float = 0.15) -> list[dict]:
    a = np.asarray(img.convert("RGB"), dtype=np.int16)
    share = float((a.max(axis=2) > 24).mean())
    return [_line("emissive.share", PASS if share <= limit else WARN,
                  f"{share:.1%} of the frame glows" + ("" if share <= limit else " — over 15 %: this will glow like a billboard"))]


def check_layers(back: Image.Image | None, over: Image.Image | None) -> list[dict]:
    out = []
    if back is not None:
        a = np.asarray(back.convert("RGBA"))
        holes = float((a[..., 3] < 250).mean())
        mag = float(((a[..., 0] > 245) & (a[..., 1] < 10) & (a[..., 2] > 245)).mean())
        bad = holes + mag
        out.append(_line("layers.back_holes", PASS if bad < 0.0005 else (WARN if bad < 0.01 else FAIL),
                         f"back plane holes {bad:.2%}" + ("" if bad < 0.0005 else " — the camera slide will show gaps")))
    if over is not None:
        a = np.asarray(over.convert("RGBA"))
        share = float((a[..., 3] > 8).mean())
        out.append(_line("layers.over_share", PASS if share <= 0.4 else WARN,
                         f"over plane covers {share:.0%}" + ("" if share <= 0.4 else " — the walk-behind plane covers too much; the player will vanish")))
    return out


# ------------------------------------------------------------------ the game's map (tolerant reader)
def map_points(m: dict, scale: float) -> dict:
    """Walk rings (polygons), doors and spawns from a map file, in painting pixels. Reads `walk`/`walk_rings`/
    `walkable` (polygons of [x, y]), `doors`, `spawns`/`spawn` (lists of [x, y] or {x, y}), in map pixels; or `rows`
    with 'D' (door) and 'S'/'@' (spawn) tiles. Unknown keys are ignored."""
    ts = int(m.get("tile_size") or 32)
    def pt(p):
        if isinstance(p, dict):
            x, y = p.get("x"), p.get("y")
            if p.get("tile") or (isinstance(x, int) and isinstance(y, int) and p.get("unit") == "tile"):
                x, y = (x + 0.5) * ts, (y + 0.5) * ts
        else:
            x, y = p[0], p[1]
        return (float(x) * scale, float(y) * scale)
    rings = []
    for key in ("walk", "walk_rings", "walkable", "walk_polygons"):
        for poly in m.get(key) or []:
            pts = poly.get("points") if isinstance(poly, dict) else poly
            if pts and len(pts) >= 3:
                rings.append([pt(p) for p in pts])
    doors = [pt(p) for p in (m.get("doors") or []) if p is not None]
    spawns = [pt(p) for k in ("spawns", "spawn") for p in ((m.get(k) if isinstance(m.get(k), list) else [m.get(k)]) or []) if p]
    for r, row in enumerate(m.get("rows") or []):
        for c, ch in enumerate(row):
            if ch == "D":
                doors.append(((c + 0.5) * ts * scale, (r + 0.5) * ts * scale))
            elif ch in ("S", "@"):
                spawns.append(((c + 0.5) * ts * scale, (r + 0.5) * ts * scale))
    return {"rings": rings, "doors": doors, "spawns": spawns}


def map_scale(m: dict, painting_size) -> float:
    ts = int(m.get("tile_size") or 32)
    cols = max((len(r) for r in m.get("rows") or []), default=0)
    if m.get("width"):
        return painting_size[0] / float(m["width"])
    return painting_size[0] / float(cols * ts) if cols else 3.0


def check_points(pts: dict, ground: np.ndarray, size) -> list[dict]:
    out = []
    W, H = size
    for kind in ("doors", "spawns"):
        for i, (x, y) in enumerate(pts[kind]):
            xi, yi = int(x), int(y)
            if not (0 <= xi < W and 0 <= yi < H):
                out.append(_line(f"map.{kind[:-1]}{i}", FAIL, f"{kind[:-1]} {i} at ({xi}, {yi}) is outside the painting"))
                continue
            r = max(6, int(min(W, H) * 0.02))
            # feet: look just below the point
            win = ground[max(0, yi - r // 2):min(H, yi + r), max(0, xi - r):min(W, xi + r)]
            share = float(win.mean()) if win.size else 0.0
            out.append(_line(f"map.{kind[:-1]}{i}", PASS if share >= 0.25 else WARN,
                             f"{kind[:-1]} {i} at ({xi}, {yi}): {share:.0%} of its footing reads as floor"
                             + ("" if share >= 0.25 else " — may be standing on painted furniture or a wall")))
    return out


def _read_map(cfg: dict, game: str, map_id: str) -> dict | None:
    try:
        g = cfgmod.game_config(cfg, game)
        root = Path(g.get("game_root") or "")
        p = root / "project" / "data" / "maps" / f"{map_id}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except (OSError, ValueError):
        return None


def wanted_size(cfg: dict, game: str, name: str):
    try:
        from .manifest import load_wanted
        raw = load_wanted(cfg, game).get("items", [])
        items = raw if isinstance(raw, dict) else {i["name"]: i for i in raw}
        it = items.get(name)
        return tuple(it["target_size"]) if it and it.get("target_size") else None
    except (FileNotFoundError, ValueError, KeyError):
        return None


def check(cfg: dict, kit_dir: Path, map_id: str | None = None, game: str = "turing_accords", map_data: dict | None = None) -> dict:
    kit_dir = Path(kit_dir)
    lines = []
    paths = {k: kit_dir / f for k, f in SLOTS.items()}
    present = {k: p for k, p in paths.items() if p.exists()}
    missing = [SLOTS[k] for k in SLOTS if k not in present]
    lines.append(_line("slots.present", PASS if not missing else FAIL,
                       "all six slot files present" if not missing else f"missing: {', '.join(missing)}"))
    if "_main" not in present:
        return {"kit": str(kit_dir), "lines": lines, "verdict": FAIL}
    paint = Image.open(present["_main"]).convert("RGB")
    want = wanted_size(cfg, game, f"scenes/{map_id}") if map_id else None
    W, H = want or paint.size
    lines.append(_line("slots.size._main", PASS if paint.size == (W, H) else FAIL,
                       f"scene.png {paint.size[0]}x{paint.size[1]}" + ("" if paint.size == (W, H) else f" — wanted.json asks {W}x{H}")))
    for k in ("_n", "_e", "_over", "_depth"):
        if k in present:
            s = Image.open(present[k]).size
            lines.append(_line(f"slots.size.{k}", PASS if s == paint.size else FAIL,
                               f"{SLOTS[k]} {s[0]}x{s[1]}" + ("" if s == paint.size else f" — must match the painting {paint.size[0]}x{paint.size[1]}")))
    if "_back" in present:
        s = Image.open(present["_back"]).size
        ok = s[1] == paint.size[1] and s[0] >= paint.size[0] and (s[0] - paint.size[0]) % 2 == 0
        lines.append(_line("slots.size._back", PASS if ok else FAIL, f"scene_back.png {s[0]}x{s[1]}"
                           + ("" if ok else " — must be the painting's height and at least its width (+ overscan each side)")))
    ground = None
    if "_n" in present:
        lines += check_normals(Image.open(present["_n"]))
    if "_depth" in present:
        d = _arr16(Image.open(present["_depth"]))
        if d.shape[::-1] != paint.size:
            d = np.asarray(Image.fromarray(d.astype(np.float32)).resize(paint.size, Image.BILINEAR), dtype=np.float64)
        dl, ground = check_depth(d)
        lines += dl
    if "_e" in present:
        lines += check_emissive(Image.open(present["_e"]))
    lines += check_layers(Image.open(present["_back"]) if "_back" in present else None,
                          Image.open(present["_over"]) if "_over" in present else None)
    pts = None
    m = map_data if map_data is not None else (_read_map(cfg, game, map_id) if map_id else None)
    if m is not None:
        pts = map_points(m, map_scale(m, paint.size))
        if ground is not None:
            lines += check_points(pts, ground, paint.size)
        lines.append(_line("map.read", PASS, f"map {map_id}: {len(pts['rings'])} walk ring(s), {len(pts['doors'])} door(s), "
                           f"{len(pts['spawns'])} spawn(s) drawn"))
    elif map_id:
        lines.append(_line("map.read", WARN, f"map {map_id} not readable (game folder not connected, or no such map) — walk rings not checked"))
    verdict = FAIL if any(l["status"] == FAIL for l in lines) else (WARN if any(l["status"] == WARN for l in lines) else PASS)
    rep = {"kit": str(kit_dir), "map": map_id, "verdict": verdict, "lines": lines}
    _picture(paint, lines, pts, kit_dir / "check.png", verdict)
    (kit_dir / "check.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
    return rep


def _picture(paint: Image.Image, lines, pts, dest: Path, verdict: str) -> None:
    from .review_compact import font
    k = min(1.0, 1400 / paint.width)
    im = paint.resize((int(paint.width * k), int(paint.height * k)), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    if pts:
        for ring in pts["rings"]:
            d.line([(x * k, y * k) for x, y in ring + ring[:1]], fill=(90, 220, 255), width=3)
        for x, y in pts["doors"]:
            d.rectangle([x * k - 9, y * k - 14, x * k + 9, y * k + 14], outline=(255, 210, 60), width=3)
        for x, y in pts["spawns"]:
            d.ellipse([x * k - 9, y * k - 9, x * k + 9, y * k + 9], outline=(255, 80, 200), width=3)
    f = font(16)
    lh = 22
    panel = Image.new("RGB", (im.width, lh * (len(lines) + 2) + 10), (22, 22, 27))
    pd = ImageDraw.Draw(panel)
    pd.text((10, 6), f"kit check: {verdict.upper()}", fill=COL[verdict], font=font(20))
    for i, l in enumerate(lines):
        y = 6 + lh * (i + 1) + 6
        pd.ellipse([10, y + 4, 22, y + 16], fill=COL[l["status"]])
        pd.text((30, y), f"{l['check']}: {l['message']}"[:160], fill=(230, 230, 236), font=f)
    out = Image.new("RGB", (im.width, im.height + panel.height))
    out.paste(im, (0, 0))
    out.paste(panel, (0, im.height))
    out.save(dest, "PNG")
