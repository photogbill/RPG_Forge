"""Sprite intake (Night 4, F1): a character sheet from any outside tool → the game's sprite contract.

William makes his character sheets himself (in an outside image tool, fed the lyrics) and bulk-edits them; the forge's
job is to cut, align and pack them. A sheet may have any grid (or none), uneven cells, any backdrop — flat colour,
white, a checkerboard painted into the picture, or real alpha — and labels printed between the rows.

    detect(img)            → backdrop, figures (numbered in reading order), dropped label/speck blobs
    guess_mapping(figs)    → which figure is which facing/frame (a GUESS — the mapping file is where a person fixes it)
    build(img, mapping)    → normalised frames: one scale, feet on one baseline, centred on the feet
    pack(frames)           → sheet.png (the contract: one row of 8 facings S,SW,W,NW,N,NE,E,SE, cell 144×216)
                             + anim.png (rows = facings, columns = frames) when there is more than one frame
    edge_report(...)       → halo colour, cut-off limbs, figures touching their cell

The mapping file (`<sheet>.intake.json`) is the hand-editable truth: the first run writes the forge's best guess and a
numbered contact sheet; a person changes the `facing` / `frame` of any numbered figure (or `skip`s it), optionally
edits a `bbox`, and reruns. Mirrored facings are filled by flipping only when the file lists them in `mirror`.

No learned matting model is used: none with a commercial-clean licence is on file, and the flat / checkerboard /
alpha cases are handled exactly by keying. (If one is added later it must be registered in models/models.json
with commercial_ok true first.)
"""
from __future__ import annotations
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from . import cc

log = logging.getLogger("forge.intake")

FACINGS = ("S", "SW", "W", "NW", "N", "NE", "E", "SE")     # the game's order: 0 = S … 7 = SE (Player.direction_index)
CELL = (144, 216)
OPPOSITE = {"W": "E", "E": "W", "NW": "NE", "NE": "NW", "SW": "SE", "SE": "SW", "S": "S", "N": "N"}
GUESS_ROWS = {8: FACINGS, 5: ("S", "SW", "W", "NW", "N"), 4: ("S", "W", "E", "N"), 3: ("S", "W", "N"), 2: ("S", "N"),
              1: ("S",)}
GUESS_SINGLE = {8: FACINGS, 5: ("S", "SW", "W", "NW", "N"), 4: ("S", "W", "N", "E"), 3: ("S", "W", "N"), 2: ("S", "N"),
                1: ("S",)}


class IntakeError(ValueError):
    pass


# ------------------------------------------------------------------ backdrop
def _border(rgb: np.ndarray, w: int = 3) -> np.ndarray:
    return np.concatenate([rgb[:w].reshape(-1, 3), rgb[-w:].reshape(-1, 3), rgb[:, :w].reshape(-1, 3),
                           rgb[:, -w:].reshape(-1, 3)]).astype(np.int32)


def backdrop(img: Image.Image, key=None, tolerance: int = 30) -> dict:
    """What the figures stand on: {"kind": "alpha" | "flat" | "checker", "keys": [[r,g,b], …], "tolerance": t}."""
    rgba = np.asarray(img.convert("RGBA"))
    a = rgba[..., 3]
    if (a < 128).mean() > 0.05:
        return {"kind": "alpha", "keys": [], "tolerance": tolerance}
    if key is not None:
        return {"kind": "flat", "keys": [list(map(int, key))], "tolerance": tolerance}
    b = _border(rgba[..., :3])
    q = (b // 16) * 16 + 8
    codes = q[:, 0] * 65536 + q[:, 1] * 256 + q[:, 2]
    uniq, counts = np.unique(codes, return_counts=True)
    order = np.argsort(-counts)
    share = counts[order] / counts.sum()
    if len(order) >= 2 and share[0] + share[1] > 0.85 and share[1] > 0.2:
        cols = []
        for k in order[:2]:
            sel = b[codes == uniq[k]]
            cols.append(np.median(sel, axis=0))
        c0, c1 = cols
        grey = all(float(c.max() - c.min()) < 30 for c in cols)
        if grey and float(np.abs(c0 - c1).sum()) > 24:
            return {"kind": "checker", "keys": [[int(v) for v in c0], [int(v) for v in c1]], "tolerance": tolerance}
    med = np.median(b, axis=0)
    share = float((np.abs(b - med).sum(axis=1) <= tolerance * 3).mean())
    kind = "flat" if share >= 0.6 else "busy"
    return {"kind": kind, "keys": [[int(v) for v in med]], "tolerance": tolerance, "border_match": round(share, 3)}


def _near(rgb: np.ndarray, keys, tol: int) -> np.ndarray:
    rgb = rgb.astype(np.int32)
    m = np.zeros(rgb.shape[:2], dtype=bool)
    for k in keys:
        m |= np.abs(rgb - np.asarray(k, dtype=np.int32)).sum(axis=2) <= tol * 3
    return m


# W10 (wiring day): see-through gaps on JPEG sheets — the suite's rule, proven on William's three Gemini sheets (it
# finds exactly the 14 arm gaps and nothing in a face or the reactor glow, whose medians are ≥ 25).
POCKET_MIN_AREA = 120          # px; an eye white or a glint is smaller, or not this close to the backdrop colour
POCKET_MEDIAN = 8              # median distance to the backdrop colour (sum over r, g, b)
POCKET_SHARE = 0.75            # share of its pixels within 15 of the backdrop colour
POCKET_TALL = 0.08             # at least this share of a figure's height: an arm's gap is long, an eye is not


def foreground(img: Image.Image, bd: dict, holes=None, auto_pockets: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """(fg bool mask, alpha uint8). Flat / checker: the backdrop is what is near a key colour AND connected to the
    sheet's border (so a white eye inside a face survives), plus enclosed pockets that are plainly backdrop too
    (a checker pocket holding both checker colours; a flat pocket with almost no shading).

    W10 — flat backdrops, see-through gaps (JPEG noise defeats the 'almost no shading' test):
      holes=None and auto_pockets: also clear every enclosed near-key pocket that passes POCKET_* (no person has
                                   decided yet — the .bat on a fresh sheet).
      holes=[[x, y], …]:           a person decided (the suite's mapping): clear exactly the near-key pocket under
                                   each point and nothing more — a gap they kept as figure stays (an empty list keeps
                                   them all).
      auto_pockets=False:          neither (detect() uses this, so the suite can still offer the gaps to the person)."""
    rgba = np.asarray(img.convert("RGBA"))
    if bd["kind"] == "alpha":
        a = rgba[..., 3].copy()
        return a > 16, a
    rgb = rgba[..., :3]
    near = _near(rgb, bd["keys"], int(bd["tolerance"]))
    lab, n = cc.label(near, 4)
    h, w = near.shape
    edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    bg = np.isin(lab, edge[edge > 0])
    # enclosed pockets (between an arm and the body, between the legs). A checker pocket is recognised by holding
    # both checker colours; a flat pocket must have almost no shading AND be a real share of a figure (≥ 1.5 % of
    # the largest figure's box) — the white of an eye or a tooth is flat too, but small.
    min_pocket = max(24, int(h * w * 0.0004))
    if bd["kind"] == "flat":
        flab, fn = cc.label(~bg, 8)
        fb = cc.boxes(flab, fn)
        if fb:
            biggest = max(fb, key=lambda b: b["area"])["bbox"]
            min_pocket = max(min_pocket, int(0.015 * (biggest[2] - biggest[0]) * (biggest[3] - biggest[1])))
    for bx in cc.boxes(lab, n):
        if bx["area"] < min_pocket or bx["id"] in edge:
            continue
        x0, y0, x1, y1 = bx["bbox"]
        sel = lab[y0:y1, x0:x1] == bx["id"]
        px = rgb[y0:y1, x0:x1][sel].astype(np.int32)
        if bd["kind"] == "checker":
            k0, k1 = (np.asarray(k) for k in bd["keys"][:2])
            d0 = np.abs(px - k0).sum(axis=1); d1 = np.abs(px - k1).sum(axis=1)
            share0 = float((d0 < d1).mean())
            if 0.2 < share0 < 0.8:
                bg[y0:y1, x0:x1] |= sel
        elif float(px.std(axis=0).max()) < 3.0:
            bg[y0:y1, x0:x1] |= sel
    if bd["kind"] in ("flat", "checker") and holes is not None:
        for pt in holes:
            x, y = int(pt[0]), int(pt[1])
            if 0 <= x < w and 0 <= y < h and near[y, x] and lab[y, x] > 0:
                bg |= lab == lab[y, x]
    elif bd["kind"] == "flat" and auto_pockets:
        for bx in pockets(rgb, bd, near, lab, n, edge, ~bg):
            bg |= lab == bx
    fg = ~bg
    alpha = np.where(fg, 255, 0).astype(np.uint8)
    return fg, alpha


def pockets(rgb: np.ndarray, bd: dict, near: np.ndarray, lab: np.ndarray, n: int, edge, fg: np.ndarray) -> list[int]:
    """Label ids of the enclosed near-key pockets still counted as figure that pass the POCKET_* rule (W10)."""
    flab, fn = cc.label(fg, 8)
    fb = cc.boxes(flab, fn)
    if not fb:
        return []
    big = max(b["area"] for b in fb)
    h_ref = max(_h(b["bbox"]) for b in fb if b["area"] >= 0.25 * big)
    key = np.asarray(bd["keys"][0], dtype=np.int32)
    out = []
    for bx in cc.boxes(lab, n):
        if bx["id"] in edge or bx["area"] < POCKET_MIN_AREA:
            continue
        x0, y0, x1, y1 = bx["bbox"]
        if (y1 - y0) < POCKET_TALL * h_ref:
            continue
        sel = lab[y0:y1, x0:x1] == bx["id"]
        if not fg[y0:y1, x0:x1][sel].any():
            continue
        d = np.abs(rgb[y0:y1, x0:x1][sel].astype(np.int32) - key).sum(axis=1)
        if float(np.median(d)) <= POCKET_MEDIAN and float((d <= 15).mean()) >= POCKET_SHARE:
            out.append(int(bx["id"]))
    return out


def decontaminate(img: Image.Image, fg: np.ndarray, bd: dict) -> Image.Image:
    """RGBA with the 1-px rim against a FLAT backdrop un-blended from the key colour (soft edge, no light halo).
    Checker and alpha sheets are returned as cut (a checker rim has no single key to remove)."""
    rgba = np.asarray(img.convert("RGBA")).copy()
    if bd["kind"] == "alpha":
        return Image.fromarray(rgba, "RGBA")
    rgba[..., 3] = np.where(fg, 255, 0)
    if bd["kind"] != "flat":
        return Image.fromarray(rgba, "RGBA")
    key = np.asarray(bd["keys"][0], dtype=np.float64)
    bgm = ~fg
    rim = fg & (np.roll(bgm, 1, 0) | np.roll(bgm, -1, 0) | np.roll(bgm, 1, 1) | np.roll(bgm, -1, 1))
    ys, xs = np.nonzero(rim)
    if len(ys):
        c = rgba[ys, xs, :3].astype(np.float64)
        # how far from the key, against the largest distance the pixel could be: the rim is a mix of figure and key
        dist = np.abs(c - key).sum(axis=1)
        a = np.clip(dist / max(1.0, 3 * 255 * 0.35), 0.25, 1.0)
        un = np.clip((c - (1 - a)[:, None] * key) / a[:, None], 0, 255)
        rgba[ys, xs, :3] = un.astype(np.uint8)
        rgba[ys, xs, 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


# ------------------------------------------------------------------ figures
def _union(a, b):
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def _gap(a, b) -> float:
    dx = max(0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0, max(a[1], b[1]) - min(a[3], b[3]))
    return float(max(dx, dy))


def _h(b):
    return b[3] - b[1]


def _w(b):
    return b[2] - b[0]


def text_lines(smalls: list[dict]) -> set[int]:
    """Ids of small components that sit in a row of ≥ 3 similar-height neighbours with tight spacing — printed words."""
    out: set[int] = set()
    by = sorted(smalls, key=lambda s: (s["bbox"][1] + s["bbox"][3]) / 2)
    used = set()
    for s in by:
        if s["id"] in used:
            continue
        line = [s]
        for t in by:
            if t is s or t["id"] in used:
                continue
            a, b = s["bbox"], t["bbox"]
            ov = min(a[3], b[3]) - max(a[1], b[1])
            hs = max(1, min(_h(a), _h(b)))
            if ov >= 0.5 * hs and max(_h(a), _h(b)) <= 3.0 * hs:
                line.append(t)
        line.sort(key=lambda s_: s_["bbox"][0])
        # split the line where the spacing opens up (> 1.6 × the letter height)
        chunk = [line[0]]
        chunks = []
        for t in line[1:]:
            prev = chunk[-1]["bbox"]
            hh = max(_h(prev), _h(t["bbox"]), 1)
            if t["bbox"][0] - prev[2] <= 1.6 * hh:
                chunk.append(t)
            else:
                chunks.append(chunk); chunk = [t]
        chunks.append(chunk)
        for ch in chunks:
            if len(ch) >= 3:
                out |= {c["id"] for c in ch}
                used |= {c["id"] for c in ch}
    return out


def detect(img: Image.Image, key=None, tolerance: int = 30) -> dict:
    """Find the figures. Returns {"backdrop", "size", "figures": [{n, bbox, area, row, col}], "dropped": [...]}"""
    img = img.convert("RGBA")
    bd = backdrop(img, key, tolerance)
    if bd["kind"] == "busy":
        raise IntakeError(f"the backdrop is not one flat colour, a checkerboard or transparent (only "
                          f"{bd['border_match']:.0%} of the sheet's border matches one colour) — this looks like a "
                          "picture, not a sheet. Put the figures on a plain background (or give `key` = the backdrop "
                          "colour) and run it again")
    fg, _alpha = foreground(img, bd, auto_pockets=False)   # raw: the suite offers the see-through gaps to the person
    lab, n = cc.label(fg, 8)
    comps = cc.boxes(lab, n)
    if not comps:
        raise IntakeError("nothing found on the sheet — is the backdrop the same colour as the figures?")
    big = max(c["area"] for c in comps)
    h_ref = max(_h(c["bbox"]) for c in comps if c["area"] >= 0.25 * big)
    cores = [c for c in comps if _h(c["bbox"]) >= 0.4 * h_ref and c["area"] >= 0.03 * big]
    smalls = [c for c in comps if c not in cores]
    words = text_lines([s for s in smalls if _h(s["bbox"]) < 0.3 * h_ref])
    figs = [{"bbox": list(c["bbox"]), "area": c["area"], "parts": [c["id"]]} for c in cores]
    # cores that belong together (a weapon or a strand of hair drawn apart from the body): overlapping columns, small gap
    merged = True
    while merged:
        merged = False
        for i in range(len(figs)):
            for j in range(i + 1, len(figs)):
                a, b = figs[i]["bbox"], figs[j]["bbox"]
                xo = min(a[2], b[2]) - max(a[0], b[0])
                yo = min(a[3], b[3]) - max(a[1], b[1])
                same_cols = xo >= 0.5 * min(_w(a), _w(b))
                same_rows = yo >= 0.5 * min(_h(a), _h(b))
                close = _gap(a, b) <= 0.04 * h_ref
                inside = (b[0] >= a[0] and b[2] <= a[2] and b[1] >= a[1] and b[3] <= a[3]) or \
                         (a[0] >= b[0] and a[2] <= b[2] and a[1] >= b[1] and a[3] <= b[3])
                if inside or (close and (same_cols or (same_rows and xo > -0.02 * h_ref))) and \
                        not (same_rows and xo <= 0 and _gap(a, b) > 0.01 * h_ref):
                    figs[i] = {"bbox": _union(a, b), "area": figs[i]["area"] + figs[j]["area"],
                               "parts": figs[i]["parts"] + figs[j]["parts"]}
                    figs.pop(j)
                    merged = True
                    break
            if merged:
                break
    dropped = []
    gap = 0.06 * h_ref
    for s in smalls:
        if s["id"] in words:
            dropped.append({"what": "label", "bbox": s["bbox"], "area": s["area"]})
            continue
        best, bd_ = None, 1e18
        for f in figs:
            g = _gap(s["bbox"], f["bbox"])
            if g < bd_:
                best, bd_ = f, g
        if best is not None and bd_ <= gap:
            best["bbox"] = _union(best["bbox"], s["bbox"])
            best["area"] += s["area"]
            best["parts"].append(s["id"])
        else:
            dropped.append({"what": "speck" if s["area"] < 0.002 * big else "stray blob", "bbox": s["bbox"], "area": s["area"]})
    # words merged into one label box per line, for the contact sheet
    dropped = _merge_labels(dropped)
    rows = order_rows(figs)
    out = []
    k = 1
    for r, row in enumerate(rows, 1):
        for c, f in enumerate(row, 1):
            out.append({"n": k, "bbox": f["bbox"], "area": f["area"], "row": r, "col": c, "parts": f["parts"]})
            k += 1
    log.info("intake detect: %d figure(s) in %d row(s), backdrop %s, dropped %d blob(s)", len(out), len(rows), bd["kind"], len(dropped))
    return {"backdrop": bd, "size": list(img.size), "figures": out, "dropped": dropped, "h_ref": int(h_ref),
            "_labels": lab, "_fg": fg}


def _merge_labels(dropped: list[dict]) -> list[dict]:
    labels = [d for d in dropped if d["what"] == "label"]
    rest = [d for d in dropped if d["what"] != "label"]
    groups: list[dict] = []
    for d in sorted(labels, key=lambda d: (d["bbox"][1], d["bbox"][0])):
        for g in groups:
            a, b = g["bbox"], d["bbox"]
            if min(a[3], b[3]) - max(a[1], b[1]) > 0 and _gap(a, b) <= 2 * max(_h(a), _h(b)):
                g["bbox"] = _union(a, b); g["area"] += d["area"]; g["letters"] += 1
                break
        else:
            groups.append({"what": "label", "bbox": list(d["bbox"]), "area": d["area"], "letters": 1})
    return groups + rest


def order_rows(figs: list[dict]) -> list[list[dict]]:
    """Reading order: rows by vertical overlap (≥ half the smaller height), left to right within a row."""
    rows: list[dict] = []
    for f in sorted(figs, key=lambda f: f["bbox"][1]):
        b = f["bbox"]
        for r in rows:
            ov = min(r["span"][1], b[3]) - max(r["span"][0], b[1])
            if ov >= 0.5 * min(_h(b), r["span"][1] - r["span"][0]):
                r["items"].append(f)
                r["span"] = [min(r["span"][0], b[1]), max(r["span"][1], b[3])]
                break
        else:
            rows.append({"span": [b[1], b[3]], "items": [f]})
    rows.sort(key=lambda r: r["span"][0])
    return [sorted(r["items"], key=lambda f: (f["bbox"][0] + f["bbox"][2]) / 2) for r in rows]


# ------------------------------------------------------------------ mapping
def guess_mapping(det: dict) -> dict:
    figs = det["figures"]
    rows: dict[int, list[dict]] = {}
    for f in figs:
        rows.setdefault(f["row"], []).append(f)
    counts = [len(v) for _, v in sorted(rows.items())]
    nrows = len(counts)
    entries = [{"n": f["n"], "bbox": f["bbox"], "bbox_found": list(f["bbox"]), "facing": None, "frame": 0} for f in figs]
    by_n = {e["n"]: e for e in entries}
    why, conf = "no layout recognised — set each figure's facing by hand", "none"
    if nrows > 1 and len(set(counts)) == 1 and nrows in GUESS_ROWS and counts[0] >= 2:
        order = GUESS_ROWS[nrows]
        for r, (_, row) in enumerate(sorted(rows.items())):
            for c, f in enumerate(row):
                by_n[f["n"]].update(facing=order[r], frame=c)
        why = f"{nrows} rows × {counts[0]}: each row one facing ({', '.join(order)}), frames left to right"
        conf = "medium" if nrows in (8, 4) else "low"
    elif nrows > 1 and len(set(counts)) == 1 and counts[0] == 8:
        for r, (_, row) in enumerate(sorted(rows.items())):
            for c, f in enumerate(row):
                by_n[f["n"]].update(facing=FACINGS[c], frame=r)
        why = f"{nrows} rows × 8: each column one facing in the game's order, each row one frame"
        conf = "low"
    elif len(figs) in GUESS_SINGLE:
        order = GUESS_SINGLE[len(figs)]
        for f, fc in zip(sorted(figs, key=lambda f: f["n"]), order):
            by_n[f["n"]].update(facing=fc, frame=0)
        why = f"{len(figs)} figure(s): taken as {', '.join(order)} in reading order"
        conf = "medium" if len(figs) == 8 else "low"
    return {"guess": why, "confidence": conf, "figures": entries}


EDIT_ME = ("Fix the guess here, then run the intake again. For each numbered figure (numbers are on numbers.png): "
           "facing = one of S SW W NW N NE E SE (or null to leave it out), frame = 0, 1, 2 … within that facing, "
           "skip = true to drop it, flip = true to mirror that one figure. bbox may be widened if a limb was cut. "
           "mirror = [\"W→E\"] fills a facing that has no figure from its opposite — only if the character is "
           "symmetric (a holster on one hip makes a flipped sprite wrong).")


def sha1(p: Path) -> str:
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def new_mapping(sheet: Path, det: dict, character: str, variant: str | None) -> dict:
    g = guess_mapping(det)
    return {"sheet": str(sheet), "sheet_sha1": sha1(sheet), "character": character, "variant": variant,
            "made": datetime.now().isoformat(timespec="seconds"), "checked_by_person": False,
            "guess": g["guess"], "confidence": g["confidence"], "edit_me": EDIT_ME,
            "backdrop": {k: v for k, v in det["backdrop"].items()}, "mirror": [], "figures": g["figures"],
            "dropped": [{"what": d["what"], "bbox": d["bbox"]} for d in det["dropped"]]}


# ------------------------------------------------------------------ cutting and normalising
def cut(rgba: Image.Image, fg: np.ndarray, bbox, bd: dict, found_bbox=None) -> tuple[Image.Image, dict]:
    """One figure from the cut-out sheet inside bbox: drop blobs that are not part of it (a neighbour's elbow, a
    speck), tight-crop, and say where a limb may really be cut off.

    W10 (wiring day): detected boxes are drawn tight round the figure, so every figure touches every side of its own
    box — that is not news. A side is reported only where the figure touches it AND the box meets the sheet's edge
    there ("left (sheet edge)"), or a person narrowed the box there ("left (box narrowed)" — `found_bbox` is the box
    detection drew; a mapping made before wiring day has none, and then only sheet edges are reported)."""
    x0, y0, x1, y1 = [int(v) for v in bbox]
    W, H = rgba.size
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
    if x1 <= x0 or y1 <= y0:
        raise IntakeError(f"bbox {bbox} is empty or outside the sheet ({W}×{H})")
    crop = rgba.crop((x0, y0, x1, y1))
    m = fg[y0:y1, x0:x1].copy()
    lab, n = cc.label(m, 8)
    info = {"touches_box": [], "dropped_blobs": 0}
    if n > 1:
        bx = cc.boxes(lab, n)
        big = max(b["area"] for b in bx)
        keep = {b["id"] for b in bx if b["area"] >= 0.02 * big}
        info["dropped_blobs"] = n - len(keep)
        m = np.isin(lab, list(keep))
    a = np.asarray(crop).copy()
    a[..., 3] = np.where(m, a[..., 3], 0)
    ys, xs = np.nonzero(a[..., 3] > 16)
    if len(xs) == 0:
        raise IntakeError(f"bbox {bbox}: nothing opaque inside")
    tx0, ty0, tx1, ty1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    bw, bh = x1 - x0, y1 - y0
    fb = [int(v) for v in found_bbox] if found_bbox else None
    for side, touches, at_edge, narrowed in (
            ("left", tx0 <= 0, x0 <= 0, bool(fb) and x0 > fb[0]),
            ("top", ty0 <= 0, y0 <= 0, bool(fb) and y0 > fb[1]),
            ("right", tx1 >= bw, x1 >= W, bool(fb) and x1 < fb[2]),
            ("bottom", ty1 >= bh, y1 >= H, bool(fb) and y1 < fb[3])):
        if touches and at_edge:
            info["touches_box"].append(f"{side} (sheet edge)")
        elif touches and narrowed:
            info["touches_box"].append(f"{side} (box narrowed)")
    fig = Image.fromarray(a, "RGBA").crop((int(tx0), int(ty0), int(tx1), int(ty1)))
    return fig, info


def feet_x(fig: Image.Image, share: float = 0.08) -> float:
    """Horizontal centre of the feet: the opaque pixels in the bottom `share` of the figure (a sword or a cape
    sticking out to one side must not move the character off its cell centre)."""
    a = np.asarray(fig)[..., 3] > 16
    h = a.shape[0]
    band = a[max(0, int(h * (1 - share)) - 1):]
    xs = np.nonzero(band)[1]
    if len(xs) == 0:
        xs = np.nonzero(a)[1]
    return float((xs.min() + xs.max()) / 2.0) if len(xs) else fig.width / 2.0


def halo(fig: Image.Image, bd: dict) -> dict | None:
    """The colour of the figure's outer rim; flagged when it is close to the backdrop (a light fringe)."""
    a = np.asarray(fig)
    m = a[..., 3] > 16
    out = ~m
    rim = m & (np.roll(out, 1, 0) | np.roll(out, -1, 0) | np.roll(out, 1, 1) | np.roll(out, -1, 1))
    if not rim.any():
        return None
    c = a[..., :3][rim].astype(np.float64).mean(axis=0)
    rec = {"rim_colour": "#%02x%02x%02x" % tuple(int(v) for v in c)}
    if bd.get("keys"):
        d = min(float(np.abs(c - np.asarray(k)).sum()) for k in bd["keys"])
        rec["like_backdrop"] = d < 3 * 45
        rec["distance"] = round(d, 1)
    return rec


def place(fig: Image.Image, k: float, cell, baseline: int) -> tuple[Image.Image, dict]:
    cw, ch = int(cell[0]), int(cell[1])
    nw, nh = max(1, int(round(fig.width * k))), max(1, int(round(fig.height * k)))
    f = fig.resize((nw, nh), Image.LANCZOS)
    fx = feet_x(fig) * k
    x = int(round(cw / 2 - fx))
    y = ch - baseline - nh
    tile = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    sx0, sy0 = max(0, -x), max(0, -y)
    dx, dy = max(0, x), max(0, y)
    src = f.crop((sx0, sy0, nw, nh))
    src = src.crop((0, 0, min(src.width, cw - dx), min(src.height, ch - dy)))
    if src.width > 0 and src.height > 0:
        tile.alpha_composite(src, (dx, dy))
    notes = []
    if nw > cw or x < 0 or x + nw > cw:
        notes.append(f"figure {nw}px wide does not fit the {cw}px cell around its feet — cut at the side")
    elif x <= 1 or x + nw >= cw - 1:
        notes.append("figure touches the cell's side")
    if y <= 1:
        notes.append("figure touches the cell's top" if y >= 0 else "figure taller than the cell — head cut")
    return tile, {"size": [nw, nh], "x": x, "y": y, "notes": notes}


def build(img: Image.Image, det_or_fg, mapping: dict, cell=CELL, figure_height: float = 0.92, baseline: int = 6,
          scale: str = "uniform") -> dict:
    """mapping → {"frames": {facing: [tile, …]}, "figures": [per-figure record], "scale": k, "warnings": [...]}"""
    img = img.convert("RGBA")
    bd = mapping.get("backdrop") or backdrop(img)
    fg = det_or_fg if isinstance(det_or_fg, np.ndarray) else foreground(img, bd)[0]
    clean = decontaminate(img, fg, bd)
    cw, ch = int(cell[0]), int(cell[1])
    target_h = int(round(ch * float(figure_height)))
    used, recs, warnings = [], [], []
    for e in mapping.get("figures") or []:
        if e.get("skip") or not e.get("facing"):
            recs.append({"n": e.get("n"), "used": False, "why": "skip" if e.get("skip") else "no facing given"})
            continue
        fc = str(e["facing"]).upper()
        if fc not in FACINGS:
            raise IntakeError(f"figure {e.get('n')}: facing '{e['facing']}' — use one of {' '.join(FACINGS)}")
        fig, info = cut(clean, fg, e["bbox"], bd, e.get("bbox_found"))
        if e.get("flip"):
            fig = ImageOps.mirror(fig)
        used.append((e, fc, int(e.get("frame") or 0), fig, info))
    if not used:
        raise IntakeError("the mapping assigns no figure to a facing — edit the mapping file")
    heights = [u[3].height for u in used]
    standing = [u[3].height for u in used if u[2] == 0] or heights
    ref = float(np.median(standing))
    k_uniform = target_h / ref
    k_uniform = min(k_uniform, (ch - baseline - 1) / max(heights))
    frames: dict[str, dict[int, Image.Image]] = {}
    for e, fc, fr, fig, info in used:
        k = k_uniform if scale == "uniform" else target_h / fig.height
        tile, pl = place(fig, k, cell, baseline)
        if fr in frames.get(fc, {}):
            warnings.append(f"figure {e.get('n')}: {fc} frame {fr} is given twice — the later one wins")
        frames.setdefault(fc, {})[fr] = tile
        h = halo(fig, bd)
        rec = {"n": e.get("n"), "used": True, "facing": fc, "frame": fr, "flip": bool(e.get("flip")),
               "source_size": [fig.width, fig.height], "placed": pl, "halo": h,
               "cut_off": [s for s in info["touches_box"]], "dropped_blobs": info["dropped_blobs"]}
        recs.append(rec)
    mirrored = []
    for spec in mapping.get("mirror") or []:
        import re
        parts = re.split(r"\s*(?:→|->|>)\s*", str(spec).upper())
        if len(parts) != 2 or parts[0] not in FACINGS or parts[1] not in FACINGS:
            raise IntakeError(f"mirror '{spec}': write it like \"W→E\" with facings from {' '.join(FACINGS)}")
        src, dst = parts
        if dst in frames:
            warnings.append(f"mirror {spec}: {dst} already has its own figures — not overwritten")
            continue
        if src not in frames:
            warnings.append(f"mirror {spec}: {src} has no figure to flip")
            continue
        frames[dst] = {i: ImageOps.mirror(t) for i, t in frames[src].items()}
        mirrored.append(f"{src}→{dst}")
    out = {f: [frames[f][i] for i in sorted(frames[f])] for f in FACINGS if f in frames}
    gaps = {f: sorted(set(range(max(frames[f]) + 1)) - set(frames[f])) for f in frames if frames[f]}
    for f, g in gaps.items():
        if g:
            warnings.append(f"{f}: frame number(s) {g} missing — the frames that exist were packed in order")
    return {"frames": out, "figures": recs, "scale": round(k_uniform, 4), "mirrored": mirrored, "warnings": warnings,
            "missing": [f for f in FACINGS if f not in out], "cell": [cw, ch], "baseline_y": ch - baseline,
            "figure_height": target_h}


def pack(built: dict) -> tuple[Image.Image, Image.Image | None]:
    """sheet.png — the contract: one row, eight facings in the game's order, frame 0 of each (empty cell where a
    facing is missing). anim.png — rows = the eight facings, columns = frames — only when any facing has > 1 frame."""
    cw, ch = built["cell"]
    frames = built["frames"]
    sheet = Image.new("RGBA", (cw * 8, ch), (0, 0, 0, 0))
    for i, f in enumerate(FACINGS):
        if f in frames:
            sheet.alpha_composite(frames[f][0], (i * cw, 0))
    most = max((len(v) for v in frames.values()), default=1)
    if most <= 1:
        return sheet, None
    anim = Image.new("RGBA", (cw * most, ch * 8), (0, 0, 0, 0))
    for r, f in enumerate(FACINGS):
        for c, t in enumerate(frames.get(f, [])):
            anim.alpha_composite(t, (c * cw, r * ch))
    return sheet, anim


# ------------------------------------------------------------------ pictures for a person
def _font(size: int):
    from ..ops.sheet import _font as f
    return f(size)


def numbers_sheet(img: Image.Image, det: dict, mapping: dict | None = None, max_side: int = 1600) -> Image.Image:
    """The sheet with every found figure boxed and numbered (and its current facing/frame), labels in red."""
    base = Image.new("RGBA", img.size, (60, 60, 66, 255))
    base.alpha_composite(img.convert("RGBA"))
    k = min(1.0, max_side / max(img.size))
    im = base.convert("RGB").resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    fsize = max(14, int(min(im.size) * 0.03))
    f = _font(fsize)
    ents = {e["n"]: e for e in (mapping or {}).get("figures", [])}
    figs = (mapping or {}).get("figures") or det["figures"]
    for fig in figs:
        x0, y0, x1, y1 = [v * k for v in fig["bbox"]]
        e = ents.get(fig["n"], {})
        on = e.get("facing") and not e.get("skip")
        col = (40, 200, 90) if on else (230, 170, 40)
        d.rectangle([x0, y0, x1, y1], outline=col, width=max(2, fsize // 8))
        tag = f"{fig['n']}" + (f" {e['facing']}·{e.get('frame', 0)}" if on else (" skip" if e.get("skip") else " ?"))
        tw = d.textlength(tag, font=f) if hasattr(d, "textlength") else len(tag) * fsize * 0.6
        d.rectangle([x0, y0, x0 + tw + 8, y0 + fsize + 6], fill=(0, 0, 0))
        d.text((x0 + 4, y0 + 2), tag, fill=col, font=f)
    for dr in det.get("dropped", []):
        if dr["what"] != "label":
            continue
        x0, y0, x1, y1 = [v * k for v in dr["bbox"]]
        d.rectangle([x0, y0, x1, y1], outline=(220, 60, 60), width=2)
    return im


def edge_report_md(built: dict, mapping: dict, sheet_path: str) -> str:
    L = [f"# Intake edge report — {Path(sheet_path).name}", "",
         f"Character `{mapping.get('character')}` variant `{mapping.get('variant') or '-'}` · backdrop "
         f"{mapping.get('backdrop', {}).get('kind')} · scale {built['scale']} · cell {built['cell'][0]}×{built['cell'][1]}", ""]
    if built["missing"]:
        L.append(f"**Missing facings:** {', '.join(built['missing'])}" + (" (mirror them in the mapping file only if "
                 "the character is symmetric)" if built["missing"] else ""))
    if built["mirrored"]:
        L.append(f"**Filled by flipping:** {', '.join(built['mirrored'])}")
    for w in built["warnings"]:
        L.append(f"- ⚠ {w}")
    L += ["", "| # | facing·frame | halo | cut off | in its cell |", "|---|---|---|---|---|"]
    for r in built["figures"]:
        if not r.get("used"):
            L.append(f"| {r['n']} | — ({r['why']}) | | | |")
            continue
        h = r.get("halo") or {}
        hal = f"{h.get('rim_colour', '')}" + (" **like the backdrop**" if h.get("like_backdrop") else "")
        L.append(f"| {r['n']} | {r['facing']}·{r['frame']}{' (flipped)' if r['flip'] else ''} | {hal} | "
                 f"{', '.join(r['cut_off']) or 'no'} | {'; '.join(r['placed']['notes']) or 'ok'} |")
    return "\n".join(L) + "\n"
