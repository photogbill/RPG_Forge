"""The picture gate (BUILD 40): a look at a body's picture before four minutes go into making the body from it.

The launch-site runs showed three faults that were already in the pictures, which the body step then built faithfully:
a man who was to have one arm drawn with two, a "T-pose" drawn as an A-pose, and two children drawn with cartoon
proportions. This reads the figure's outline (numpy only) and measures:

  pose          the angle of each arm from the vertical, against what was asked: an A-pose about 45 degrees out from
                the body, a T-pose level (90). Seated figures and figures leaning on a cane or a crutch skip it.
  limbs         how many arms stand out from the body, against what the entry expects ({"expects": {"arms": 1}}, or
                read from its words: "one arm", "an amputee").
  proportions   the head's height against the figure's, against the range for the age the words give (a child of nine,
                a teenager, an adult). A cartoon child's head is a quarter of its height; a real nine-year-old's is
                about a sixth.

`judge(picture, entry)` returns {"ok", "lines", "measures"}; on a miss the world queue makes the picture again with a new
seed, up to `tries` times, then holds the thing with the pictures side by side and the reason in plain words. Behind the
Bodies form's "Make the body" it is a warning only — the person stays in charge. Every number is a setting
(forge.json -> threed.gate).
"""
from __future__ import annotations

import re

import numpy as np

from . import raster

DEFAULTS = {
    "a_pose_deg": [32.0, 76.0],      # an A-pose: the hand this far out from straight below the shoulder (37-64 on 30 good pictures)
    "t_pose_deg": [66.0, 115.0],     # a T-pose: level, or near it (the good T-pose measured 69, the A-pose drawn for one 57)
    "arm_min_share": 0.02,           # an arm held out: at least this share of the figure's area stands out beside the body
    "hang_px": 0.035,                # an arm hanging against the body: one side of the trunk this much wider (of the height)
    "hang_rows": 0.6,                # ... in this share of the trunk's rows
    "stump_ratio": 0.65,             # one arm reaching less than this share of the other's reach is a stump, not an arm
                                     # (full arms measured 0.84-1.00 of each other on 40 pictures; a forearm gone is ~0.5)
    "head_ratio": {                  # the head's height over the figure's height, by age band
        "child": [0.135, 0.19],      # a real child of five to twelve: about a sixth (hair included)
        "teen": [0.11, 0.15],        # thirteen to seventeen: about a seventh
        "adult": [0.10, 0.165],      # eighteen and over (a helmet or a cap makes the head a little taller)
    },
    "tries": 3,                      # pictures made again with a new seed before the thing is held
}

NUMBERS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                      "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}


def settings(cfg: dict | None) -> dict:
    s = {**DEFAULTS, "head_ratio": dict(DEFAULTS["head_ratio"])}
    over = ((cfg or {}).get("threed") or {}).get("gate") or {}
    for k, v in over.items():
        if k == "head_ratio" and isinstance(v, dict):
            s["head_ratio"].update(v)
        else:
            s[k] = v
    return s


# ------------------------------------------------------------------------------------------------ what the entry asks
def _number(word: str) -> int | None:
    w = word.lower().replace("‑", "-")
    if w.isdigit():
        return int(w)
    if w in NUMBERS:
        return NUMBERS[w]
    if w in TENS:
        return TENS[w]
    if "-" in w:
        a, _, b = w.partition("-")
        if a in TENS and b in NUMBERS:
            return TENS[a] + NUMBERS[b]
    return None


def age_of(words: str, entry: dict | None = None) -> int | None:
    """The age the words give ("a boy of nine", "a sixteen-year-old girl", "a man of thirty-four"), or the entry's own."""
    if entry and entry.get("age") not in (None, ""):
        try:
            return int(entry["age"])
        except (TypeError, ValueError):
            pass
    t = words or ""
    m = re.search(r"\b([a-z]+(?:-[a-z]+)?|\d{1,2})[- ]year[- ]old\b", t, re.I)
    if m and _number(m.group(1)) is not None:
        return _number(m.group(1))
    m = re.search(r"\b(?:man|woman|boy|girl|child|kid|teen|teenager|person|figure|soldier|sergeant|officer|pilot|airman|"
                  r"corporal|private|lieutenant|captain|farmer|pastor|wife|husband|mother|father|nurse|doctor|refugee|"
                  r"veteran|worker)\s+of\s+([a-z]+(?:-[a-z]+)?|\d{1,2})\b", t, re.I)
    if m and _number(m.group(1)) is not None:
        return _number(m.group(1))
    return None


def band(age: int | None) -> str | None:
    if age is None:
        return None
    return "child" if age <= 12 else ("teen" if age <= 17 else "adult")


def expectations(entry: dict) -> dict:
    """What the picture should show: pose (a | t), arms (1 | 2), seated, carried object, age band — from the entry's
    fields first, then its words (and the pose words that go with it)."""
    words = " ".join(str(entry.get(k) or "") for k in ("words", "prompt", "always"))
    low = words.lower()
    exp = dict(entry.get("expects") or {})
    if "pose" not in exp:
        exp["pose"] = "t" if re.search(r"\bt[- ]pose\b", low) else "a"
    if "arms" not in exp:
        exp["arms"] = 1 if re.search(r"\b(one arm|only one arm|an amputee|arm is missing|arm ends|missing (?:his|her|their) "
                                     r"(?:left|right) arm|no (?:left|right) arm)\b", low) else 2
    seated = bool(entry.get("seated")) or bool(re.search(r"\b(wheelchair|sitting|seated)\b", low))
    carried = entry.get("carried_object") or (re.search(r"\b(cane|crutch|walking stick|walker)\b", low) or [None])[0]
    exp.setdefault("seated", seated)
    exp.setdefault("carried_object", carried)
    age = age_of(words, entry)
    exp.setdefault("age", age)
    exp.setdefault("band", band(age))
    return exp


# ------------------------------------------------------------------------------------------------ what the picture shows
def figure(picture, size: int = 512) -> np.ndarray:
    from .checks import picture_mask
    if not hasattr(picture, "convert"):
        from PIL import Image
        picture = Image.open(picture)
        picture.load()
    m = picture_mask(picture, size)
    m = raster.closing(m, 2)
    return largest(m)


def largest(m: np.ndarray) -> np.ndarray:
    """The largest connected part of a mask (4-connected), numpy only."""
    lab = np.zeros(m.shape, np.int32)
    ys, xs = np.nonzero(m)
    if not len(ys):
        return m
    best, best_n, cur = None, 0, 0
    seen = np.zeros(m.shape, bool)
    for y0, x0 in zip(ys[:: max(1, len(ys) // 400)], xs[:: max(1, len(ys) // 400)]):
        if seen[y0, x0]:
            continue
        cur += 1
        reach = np.zeros(m.shape, bool)
        reach[y0, x0] = True
        while True:
            grown = raster.dilate(reach, 1) & m
            if (grown == reach).all():
                break
            reach = grown
        seen |= reach
        n = int(reach.sum())
        if n > best_n:
            best, best_n = reach, n
        if best_n > 0.5 * len(ys):
            break
    _ = lab
    return best if best is not None else m


def measure(picture, size: int = 512) -> dict:
    """The figure's height; its head's height and width; the trunk's width; and for each side, how much stands out
    beside the trunk (an arm held out, or an arm hanging that widens one side only) and the angle from the shoulder to
    the hand, from the vertical (0 hanging, 45 an A-pose, 90 level)."""
    m = figure(picture, size)
    ys, xs = np.nonzero(m)
    if len(ys) < 500:
        return {"found": False}
    top, bot = int(ys.min()), int(ys.max())
    H = bot - top + 1
    widths = m.sum(1)
    # the head: from the top down to the neck (the narrowest row between the head's widest row and the shoulders)
    zone = widths[top: top + int(H * 0.30)].astype(np.float64)
    hw_row = int(np.argmax(zone[: max(3, int(H * 0.13))]))
    hw = float(zone[hw_row])
    sh = None
    for r in range(hw_row + 1, len(zone)):
        if zone[r] > 1.8 * hw:               # the shoulders have begun
            sh = r
            break
    if sh is None:
        sh = len(zone) - 1
    neck = int(np.argmin(zone[hw_row: sh + 1])) + hw_row
    head_h = neck + 1
    hrows = (ys >= top) & (ys <= top + neck)
    cx = float(xs[hrows].mean())             # the head sits over the body's middle, whatever the arms do
    c = int(round(cx))

    def run(row):
        r = m[row]
        if not r[c]:
            return None
        l = c
        while l > 0 and r[l - 1]:
            l -= 1
        rr = c
        while rr < len(r) - 1 and r[rr + 1]:
            rr += 1
        return l, rr

    rows = []
    for row in range(top + sh, top + int(H * 0.60)):
        if row > top + int(H * 0.35) and not m[row, c]:
            break                            # the legs have parted: below here is legs, not arms
        rows.append(row)
    runs = {row: run(row) for row in rows}
    trunk_rows = [row for row in range(top + int(H * 0.30), top + int(H * 0.46)) if runs.get(row)]
    wl = np.array([cx - runs[r][0] for r in trunk_rows]) if trunk_rows else np.array([H * 0.12])
    wr = np.array([runs[r][1] - cx for r in trunk_rows]) if trunk_rows else np.array([H * 0.12])
    half = float(min(np.median(wl), np.median(wr)))
    margin = 0.02 * H
    area = float(len(ys))
    arms = {}
    for side, sgn in (("left", -1), ("right", 1)):
        pts = []
        for row in rows:
            rr = runs.get(row)
            xr = np.nonzero(m[row])[0]
            if rr and row < top + int(H * 0.30):
                # above the trunk band an arm held level is joined to the shoulders: what lies well beyond the trunk counts
                out = xr[(xr < rr[0]) | (xr > rr[1]) | (np.abs(xr - cx) > half + 2 * margin)]
            else:
                out = xr[(xr < rr[0]) | (xr > rr[1])] if rr else xr
            out = out[(out < cx - half - margin)] if side == "left" else out[(out > cx + half + margin)]
            pts += [(x, row) for x in out]
        # an arm hanging against the body: that side of the trunk wider than the other, row after row
        ws = wl if side == "left" else wr
        wo = wr if side == "left" else wl
        hanging = float(np.mean((ws - wo) > float(DEFAULTS["hang_px"]) * H)) if len(ws) else 0.0
        share = len(pts) / area
        angle, reach, tip_angle = None, 0.0, None
        if len(pts) > 30:
            P = np.asarray(pts, np.float64)
            shoulder = np.array([cx + sgn * half, top + sh])
            reach = float(np.hypot(*(P - shoulder).T).max() / H)      # how far the arm reaches from the shoulder
            far = P[np.abs(P[:, 0] - cx) > half + 0.06 * H]          # the outer part of the arm, clear of the shoulder
            # the hand's drop below the shoulder joint: the outermost point of the arm against the joint
            tip = P[int(np.argmax(np.abs(P[:, 0] - cx)))]
            joint = np.array([cx + sgn * half, top + sh + 0.04 * H])
            tip_angle = float(np.degrees(np.arctan2(abs(tip[0] - joint[0]), tip[1] - joint[1])))
            P = far if len(far) > 30 else P
            C = P - P.mean(0)
            w, v = np.linalg.eigh(C.T @ C)
            d = v[:, -1]
            angle = float(np.degrees(np.arctan2(abs(d[0]), abs(d[1]))))
        # the pose is read from the hand's drop below the shoulder joint ("angle"); the arm's long axis ("axis") is kept
        # for the record — on the 40 pictures of 2026-11-14 the axis could not tell a steep A-pose from a drooping T-pose
        arms[side] = {"share": round(share, 4), "angle": None if tip_angle is None else round(tip_angle, 1),
                      "axis": None if angle is None else round(angle, 1),
                      "hanging": round(hanging, 2), "reach": round(reach, 3)}
    return {"found": True, "height_px": H, "head_px": head_h, "head_ratio": round(head_h / H, 3),
            "head_width_ratio": round(hw / H, 3), "head_to_trunk": round(hw / max(2 * half, 1), 3),
            "shoulder_ratio": round(sh / H, 3), "trunk_px": round(2 * half, 1), "arms": arms}


def judge(picture, entry: dict, cfg: dict | None = None) -> dict:
    s = settings(cfg)
    exp = expectations(entry)
    mz = measure(picture)
    if not mz.get("found"):
        return {"ok": True, "skipped": True, "lines": ["Picture gate: the figure couldn't be told from the background — not checked."],
                "measures": mz, "expects": exp}
    lines, ok = [], True
    held = [k for k, a in mz["arms"].items() if a["share"] >= float(s["arm_min_share"])]
    hanging = [k for k, a in mz["arms"].items() if k not in held and a.get("hanging", 0) >= float(s["hang_rows"])]
    present = held + hanging
    stump = None
    if exp["arms"] == 1 and len(held) == 2:
        r = {k: mz["arms"][k].get("reach") or 0.0 for k in held}
        lo_k = min(r, key=r.get)
        if r[lo_k] < float(s["stump_ratio"]) * max(r.values()):
            stump = lo_k                       # the shorter one is a stump: one arm, as asked
            present = [k for k in held if k != lo_k]
    # limbs
    if exp["arms"] == 1 and len(present) >= 2:
        ok = False
        lines.append("Picture gate — limbs: two arms stand out from the body; the words ask for one. Made again.")
    elif exp["arms"] == 2 and len(present) < 2 and not exp["seated"] and not exp["carried_object"]:
        ok = False
        lines.append("Picture gate — limbs: " + ("no arm stands clear of the body (held against the sides, or not there)"
                                                 if not present else "only one arm stands clear of the body")
                     + "; the words ask for two. Made again.")
    else:
        lines.append(f"Picture gate — limbs: {len(present)} arm{'s' if len(present) != 1 else ''}"
                     + (f" and a stump on the {stump}" if stump else "") + ", as asked.")
    # pose
    if exp["seated"] or exp["carried_object"]:
        lines.append("Picture gate — pose: " + ("seated" if exp["seated"] else f"leaning on a {exp['carried_object']}") +
                     " — the arms' angle isn't checked.")
    else:
        angles = [mz["arms"][k]["angle"] for k in held if mz["arms"][k]["angle"] is not None]
        angles += [0.0 for k in hanging]          # an arm hanging against the body is at about 0 degrees
        lo, hi = s["t_pose_deg"] if exp["pose"] == "t" else s["a_pose_deg"]
        name = "a T-pose (level)" if exp["pose"] == "t" else "an A-pose (about 45°)"
        said = " and ".join("hanging at the side" if a < 12 else f"at {a:.0f}°" for a in angles)
        bad = [a for a in angles if not lo <= a <= hi]
        if angles and bad:
            ok = False
            lines.append(f"Picture gate — pose: the arm{'s are' if len(angles) > 1 else ' is'} {said} "
                         f"(from the body's line); {name} was asked ({lo:.0f}–{hi:.0f}°). Made again.")
        else:
            lines.append("Picture gate — pose: the arms are " + (said or "not to be measured") + f", {name} as asked.")
    # proportions
    if exp["band"]:
        lo, hi = s["head_ratio"][exp["band"]]
        r = mz["head_ratio"]
        who = {"child": f"a child of {exp['age']}", "teen": f"a teenager of {exp['age']}", "adult": "an adult"}[exp["band"]]
        if not lo <= r <= hi:
            ok = False
            lines.append(f"Picture gate — proportions: the head is {r * 100:.0f}% of the figure's height (1 in {1 / r:.1f}); for "
                         f"{who} it is {lo * 100:.0f}–{hi * 100:.0f}%" + (" — cartoon proportions" if r > hi else "") + ". Made again.")
        else:
            lines.append(f"Picture gate — proportions: the head is 1 in {1 / r:.1f} of the figure, right for {who}.")
    return {"ok": ok, "lines": lines, "measures": mz, "expects": exp}


def side_by_side(pictures: list, notes: list[str], out, size: int = 320):
    """The tries side by side with why each missed, for the person to look at when the gate holds a thing."""
    from PIL import Image, ImageDraw
    from .checks import _font
    font, plain = _font(13)
    W = Image.new("RGB", (size * max(1, len(pictures)), size + 22 + 17 * max(1, len(notes))), (24, 24, 30))
    d = ImageDraw.Draw(W)
    for i, p in enumerate(pictures):
        im = Image.open(p) if not hasattr(p, "convert") else p
        W.paste(im.convert("RGB").resize((size, size)), (i * size, 0))
        d.text((i * size + 6, size + 3), plain(f"try {i + 1}"), fill=(200, 200, 200), font=font)
    for j, n in enumerate(notes):
        d.text((6, size + 22 + 17 * j), plain(n[:220]), fill=(255, 150, 140), font=font)
    W.save(out)
    return out
