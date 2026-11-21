"""One number of a filmed set piece as data, checked and resolved to seconds (BUILD 43 part 4).

A cue sheet is a JSON file the game keeps (never in the forge). It says, on the song's own clock, who stands on which
mark, which move plays, the path between marks, which camera with what lens, the props that fly, the conductor's acting,
and the sounds that sit on a frame. `check()` finds what is wrong without running Blender; `resolve()` turns every
"when" into seconds for the renderer (`forge/threed/blender/cue_render.py`).

    {
      "number": "duel_a", "title": "...", "track": "<song file>", "beat_map": "<its beat map>",
      "place": "<the place's name>", "fps": 24, "from": 0.0, "to": "crash_end",
      "cast": {"sarah": {"body": "<id>", "as": "the keeper"}, ...},
      "moments": {"crash": {"t": 120.51, "measured": "hit_7", "by_ear": false}, ...},
      "beats":     [{"at": <when>, "who": "sarah", "do": "go", "to": "<mark>", "dur": 1.5, "move": "Jog_Fwd_Loop"}, ...],
      "props":     [{"at": <when>, "do": "throw", "prop": "<id>", "from": "count", "to": "count", "height_m": 11.0}, ...],
      "camera":    [{"at": <when>, "shot": "wide_house", "pos": "<mark>"|[x,y,z], "look_at": "sarah", "lens": 35}, ...],
      "conductor": [{"at": <when>, "do": "raise"}, {"from": <when>, "to": <when>, "do": "freeze"}, ...],
      "sfx":       [{"at": <when>, "sound": "<id>", "layer": "crowd"}]
    }

A <when> is any of: a number (seconds); {"t": s}; {"bar": n, "beat": b}; a moment's name (a string); {"moment": name};
each may carry "offset" (seconds, + later). Moments are named in the sheet ("crash") or measured in the beat map
("hit_7", "silence_2", "segment_4", "hold_1_end", "first_beat").

The rules it enforces (BUILD 43):
  * nobody lands a blow: an `attack` aimed at a person must say `"misses": true` or `"parried_by": <who>`; `hit` and
    `strike` may only be aimed at things (a sandbag), never at a person;
  * a throw goes up and comes down as a body would (height and time agree with gravity, within a quarter), the top of
    its arc lands on a strong beat (a warning, with the nearest strong beat), and it is caught by somebody;
  * stage for distance: a close shot of a singing face is allowed once in the whole film and only marked
    `"test_closeup": true` (✦ b43-faces, "stage for distance, test one close-up");
  * the conductor is in at least one shot of every number in which he conducts (✦ 2026-11-14 22:52, "prominent");
  * every who is in the cast, every mark is a mark, every move is in the moves vocabulary (when one is handed in),
    every when falls inside the song, and nobody is told to be in two places at once.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from . import beatmap as bmod

G = 9.81
VERBS = ("place", "go", "play", "face", "look", "attack", "parry", "hit", "strike", "take", "throw", "catch", "bow",
         "climb", "swing", "fall", "rise", "sing", "stance", "hide", "show", "burst", "drop", "note")
TARGETS_NEVER_PEOPLE = ("hit", "strike")
FRAMINGS = ("wide", "full", "medium", "close", "extreme_close", "insert")


class SheetError(ValueError):
    pass


def silent_map(length: float) -> dict:
    """A beat map for a sheet with no song (a beat with no music: the coin in the wings): only its length."""
    return {"duration": float(length), "beats": [], "bars": [], "silences": [], "hits": [], "holds": [], "segments": [],
            "meter": [], "by_hand": {}}


def beat_map_for(sheet: dict, folder=None) -> dict:
    """The sheet's beat map: its file (relative to the sheet's folder), or a silent one when it has no song."""
    if not sheet.get("track"):
        if not sheet.get("length"):
            raise SheetError("a sheet with no track needs a length (seconds)")
        return silent_map(float(sheet["length"]))
    rel = sheet.get("beat_map")
    if not rel:
        raise SheetError("the sheet names no beat map (make one: python -m forge film beatmap <track>)")
    base = Path(folder) if folder else Path(sheet.get("_path", ".")).parent
    p = Path(rel) if Path(rel).is_absolute() else base / rel
    if not p.exists():
        raise SheetError(f"its beat map is not made yet: {p}")
    return bmod.read(p)


def load(path) -> dict:
    p = Path(path)
    sheet = json.loads(p.read_text(encoding="utf-8"))
    sheet["_path"] = str(p)
    return sheet


def _moment_table(sheet: dict, bm: dict) -> dict:
    table = bmod.moments(bm)
    for name, spec in (sheet.get("moments") or {}).items():
        if isinstance(spec, (int, float)):
            table[name] = float(spec)
        elif isinstance(spec, dict):
            if "t" in spec:
                table[name] = float(spec["t"]) + float(spec.get("offset", 0.0))
            elif "measured" in spec and spec["measured"] in table:
                table[name] = float(table[spec["measured"]]) + float(spec.get("offset", 0.0))
            elif "bar" in spec:
                table[name] = bmod.bar_time(bm, int(spec["bar"]), float(spec.get("beat", 1))) + float(spec.get("offset", 0.0))
    return table


def when(at, bm: dict, table: dict) -> float:
    """Seconds for a <when>."""
    off = 0.0
    if isinstance(at, (int, float)):
        return float(at)
    if isinstance(at, str):
        if at not in table:
            raise SheetError(f"no moment called '{at}' (named: {', '.join(sorted(k for k in table if not k[-1:].isdigit()))[:300]})")
        return float(table[at])
    if not isinstance(at, dict):
        raise SheetError(f"'{at}' is not a time, a bar, or a moment")
    off = float(at.get("offset", 0.0))
    if "t" in at:
        return float(at["t"]) + off
    if "bar" in at:
        return bmod.bar_time(bm, int(at["bar"]), float(at.get("beat", 1))) + off
    if "moment" in at:
        return when(at["moment"], bm, table) + off
    raise SheetError(f"'{at}' says neither t, bar nor moment")


def throw_times(height_m: float) -> float:
    """Seconds from the hand to the top of the arc for a throw that climbs height_m (and the same back down)."""
    return math.sqrt(2.0 * max(0.0, height_m) / G)


def fit_throw(bm: dict, catch_t: float, want_h: float, lo_h: float | None = None, hi_h: float | None = None) -> dict | None:
    """A throw caught at catch_t whose top lands on a strong beat: the strong beat before the catch that gives a height
    nearest want_h (within lo_h..hi_h, by default 0.6x..1.6x of it). Returns {throw, apex, height_m, up} or None."""
    lo_h = want_h * 0.6 if lo_h is None else lo_h
    hi_h = want_h * 1.6 if hi_h is None else hi_h
    best = None
    for b in bm.get("beats") or []:
        B = float(b["t"])
        if B >= catch_t or not bmod.strong(bm, B, tol=0.001):
            continue
        up = catch_t - B
        h = 0.5 * G * up * up
        if lo_h <= h <= hi_h and (best is None or abs(h - want_h) < abs(best["height_m"] - want_h)):
            best = {"throw": round(B - up, 3), "apex": round(B, 3), "height_m": round(h, 2), "up": round(up, 3)}
    return best


def check(sheet: dict, bm: dict, marks: dict | None = None, moves: set | None = None,
          singers: set | None = None) -> tuple[list[str], list[str]]:
    """(errors, warnings). Errors stop a render; warnings are for a person to look at."""
    errors, warns = [], []
    cast = sheet.get("cast") or {}
    dur = float(bm.get("duration") or 0)
    try:
        table = _moment_table(sheet, bm)
    except Exception as e:  # noqa: BLE001
        return [f"moments: {e}"], []
    t_from = 0.0
    t_to = dur
    try:
        t_from = when(sheet.get("from", 0.0), bm, table)
        t_to = when(sheet.get("to", dur), bm, table)
    except SheetError as e:
        errors.append(f"from/to: {e}")
    if t_to <= t_from:
        errors.append(f"the sheet ends ({t_to:.2f}) before it starts ({t_from:.2f})")

    def W(at, where):
        try:
            t = when(at, bm, table)
        except (SheetError, ValueError) as e:
            errors.append(f"{where}: {e}")
            return None
        if t < -1e-6 or t > dur + 0.05:
            errors.append(f"{where}: {t:.2f} s is outside the song (0–{dur:.1f})")
        return t

    def Wb(entry, where):
        """An entry's time: its "at" plus the entry's own "offset" (an offset may sit beside "at" or inside it)."""
        t = W(entry.get("at"), where)
        return None if t is None else t + float(entry.get("offset", 0.0))

    def mark_ok(m, where):
        if marks is None or m is None:
            return
        if isinstance(m, str) and m not in marks:
            errors.append(f"{where}: no mark called '{m}'")

    busy = {}       # who -> list of (t0, t1, what) for moves that take time
    for i, b in enumerate(sheet.get("beats") or []):
        where = f"beat {i + 1} ({b.get('who')}, {b.get('do')})"
        t = Wb(b, where)
        who, do = b.get("who"), b.get("do")
        if who not in cast:
            errors.append(f"{where}: '{who}' is not in the cast")
        if do not in VERBS:
            errors.append(f"{where}: no verb '{do}' (verbs: {', '.join(VERBS)})")
        if do in ("place", "go"):
            mark_ok(b.get("mark") or b.get("to"), where)
        if b.get("move") and moves is not None and b["move"] not in moves:
            errors.append(f"{where}: no move called '{b['move']}' in the library or the keyed moves")
        tgt = b.get("at_who") or b.get("target")
        if do == "attack" and tgt in cast and not (b.get("misses") or b.get("parried_by")):
            errors.append(f"{where}: an attack on {tgt} must miss or be parried — nobody lands a blow")
        if do in TARGETS_NEVER_PEOPLE and tgt in cast:
            errors.append(f"{where}: '{do}' is for things, never a person — nobody lands a blow")
        if do == "go" and t is not None:
            d = b.get("dur")
            if d is None and b.get("until") is not None:
                t2 = W(b.get("until"), where + " until")
                d = (t2 - t) if t2 is not None else None
            if d is None or d <= 0:
                errors.append(f"{where}: a 'go' needs a dur or an until")
            else:
                busy.setdefault(who, []).append((t, t + d, where))
    for who, spans in busy.items():
        spans.sort()
        for (a0, a1, wa), (b0, b1, wb) in zip(spans, spans[1:]):
            if b0 < a1 - 1e-3:
                errors.append(f"{who} is told to be in two places at once: {wa} runs to {a1:.2f}, {wb} starts at {b0:.2f}")

    throws = []
    for i, p in enumerate(sheet.get("props") or []):
        where = f"prop {i + 1} ({p.get('do')} {p.get('prop')})"
        t = Wb(p, where)
        if p.get("do") == "throw" and t is not None:
            h = float(p.get("height_m", 0))
            up = p.get("up")
            want = throw_times(h)
            if up is not None and abs(float(up) - want) > 0.25 * want:
                errors.append(f"{where}: a throw {h:.1f} m high takes {want:.2f} s to the top, not {float(up):.2f}")
            apex = t + (float(up) if up is not None else want)
            if (bm.get("beats") or []) and p.get("on_beat", True) and not bmod.strong(bm, apex, tol=0.08):
                nb = _nearest_strong(bm, apex)
                warns.append(f"{where}: the top of the arc ({apex:.2f}) is not on a strong beat"
                             + (f" — the nearest is {nb:.2f}; throw at {t + nb - apex:.2f}" if nb is not None else ""))
            throws.append((p.get("prop"), t, apex + (float(up) if up is not None else want), where))
            if p.get("by") not in cast and p.get("from") not in cast:
                errors.append(f"{where}: thrown by whom? ('by' must be in the cast)")
        if p.get("do") == "catch":
            if p.get("by") not in cast:
                errors.append(f"{where}: caught by whom? ('by' must be in the cast)")
    for prop, t_throw, land, where in throws:
        caught = [c for c in (sheet.get("props") or []) if c.get("do") == "catch" and c.get("prop") == prop]
        tc = sorted(x for x in (Wb(c, "catch") for c in caught) if x is not None and x > t_throw)
        if not tc:
            errors.append(f"{where}: nobody catches it")
        elif abs(tc[0] - land) >= 0.25:
            warns.append(f"{where}: it comes down at {land:.2f}; the catch is at {tc[0]:.2f}")

    shots = sheet.get("camera") or []
    if not shots:
        errors.append("no camera: a number needs at least one shot")
    else:
        t_first = min((x for x in (Wb(c, "camera") for c in shots) if x is not None), default=None)
        if t_first is not None and t_first > t_from + 0.05:
            errors.append(f"the first shot starts at {t_first:.2f}, after the number does ({t_from:.2f})")
    closeups = 0
    for i, c in enumerate(shots):
        where = f"camera {i + 1} ({c.get('shot')})"
        Wb(c, where)
        if c.get("framing") and c["framing"] not in FRAMINGS:
            errors.append(f"{where}: framing '{c['framing']}' is not one of {', '.join(FRAMINGS)}")
        if not c.get("lens"):
            errors.append(f"{where}: a shot needs a lens (mm)")
        mark_ok(c.get("pos") if isinstance(c.get("pos"), str) else None, where)
        subj = c.get("focus") or c.get("look_at")
        if c.get("framing") in ("close", "extreme_close") and singers and subj in singers:
            if c.get("test_closeup"):
                closeups += 1
            else:
                errors.append(f"{where}: a close shot of {subj} singing — stage for distance (the one test close-up says test_closeup)")
    if closeups > 1:
        errors.append(f"{closeups} test close-ups in one number: the film has one")
    if sheet.get("conductor"):
        cond = next((k for k, v in cast.items() if v.get("role") == "conductor"), "conductor")
        if not any(cond in (c.get("look_at"), c.get("focus")) or cond in (c.get("with") or []) for c in shots):
            warns.append(f"the conductor conducts here but no shot has him in it ('{cond}' in look_at, focus or with)")
        for i, a in enumerate(sheet["conductor"]):
            for k in ("at", "from", "to"):
                if k in a:
                    W(a[k], f"conductor {i + 1} ({a.get('do')})")
    for i, s in enumerate(sheet.get("sfx") or []):
        Wb(s, f"sfx {i + 1} ({s.get('sound')})")
    return errors, warns


def _nearest_strong(bm: dict, t: float) -> float | None:
    best = None
    for b in bm.get("beats") or []:
        if bmod.strong(bm, b["t"], tol=0.001) and (best is None or abs(b["t"] - t) < abs(best - t)):
            best = b["t"]
    return best


def resolve(sheet: dict, bm: dict, marks: dict | None = None) -> dict:
    """The renderer's timeline: every when in seconds (on the song's clock), sorted, with the window to render."""
    table = _moment_table(sheet, bm)
    dur = float(bm["duration"])
    t_from = when(sheet.get("from", 0.0), bm, table)
    t_to = when(sheet.get("to", dur), bm, table)

    def W(at):
        return round(when(at, bm, table), 4)

    def Wb(entry):
        return round(when(entry["at"], bm, table) + float(entry.get("offset", 0.0)), 4)

    out = {"number": sheet.get("number"), "title": sheet.get("title"), "track": sheet.get("track"),
           "fps": int(sheet.get("fps", 24)), "from": round(t_from, 4), "to": round(t_to, 4), "duration": dur,
           "place": sheet.get("place"), "cast": sheet.get("cast") or {}, "marks": marks or {},
           "moments": {k: round(v, 4) for k, v in table.items() if not k.startswith(("segment_", "hit_", "hold_", "silence_"))},
           "tracks": {}, "props": [], "camera": [], "conductor": [], "sfx": []}
    for b in sheet.get("beats") or []:
        e = {k: v for k, v in b.items() if k not in ("at", "until", "offset")}
        e["t"] = Wb(b)
        if b.get("until") is not None:
            e["dur"] = round(W(b["until"]) - e["t"], 4)
        out["tracks"].setdefault(b["who"], []).append(e)
    for who in out["tracks"]:
        out["tracks"][who].sort(key=lambda e: e["t"])
    for p in sheet.get("props") or []:
        e = {k: v for k, v in p.items() if k not in ("at", "offset")}
        e["t"] = Wb(p)
        if p.get("do") == "throw":
            e.setdefault("up", round(throw_times(float(p.get("height_m", 0))), 4))
        out["props"].append(e)
    for c in sheet.get("camera") or []:
        e = {k: v for k, v in c.items() if k not in ("at", "offset")}
        e["t"] = Wb(c)
        out["camera"].append(e)
    for a in sheet.get("conductor") or []:
        e = {k: v for k, v in a.items() if k not in ("at", "from", "to", "offset")}
        for k in ("at", "from", "to"):
            if k in a:
                e[k] = W(a[k]) + (float(a.get("offset", 0.0)) if k == "at" else 0.0)
        out["conductor"].append(e)
    for s in sheet.get("sfx") or []:
        e = {k: v for k, v in s.items() if k not in ("at", "offset")}
        e["t"] = Wb(s)
        out["sfx"].append(e)
    for k in ("props", "camera", "sfx"):
        out[k].sort(key=lambda e: e["t"])
    out["conductor"].sort(key=lambda e: e.get("at", e.get("from", 0.0)))
    return out


def report(sheet: dict, bm: dict, marks=None, moves=None, singers=None) -> str:
    """A plain report a person can read: errors, warnings, and the beats in time order with their seconds."""
    errs, warns = check(sheet, bm, marks, moves, singers)
    lines = [f"{sheet.get('number')} — {sheet.get('title', '')}", ""]
    lines += [f"ERROR  {e}" for e in errs] + [f"look   {w}" for w in warns]
    if not errs:
        tl = resolve(sheet, bm, marks)
        lines.append("")
        lines.append(f"renders {tl['from']:.2f} → {tl['to']:.2f} s at {tl['fps']} fps")
        rows = []
        for who, evs in tl["tracks"].items():
            rows += [(e["t"], f"{who:12} {e['do']:8} " + ", ".join(f"{k}={v}" for k, v in e.items() if k not in ('t', 'do', 'who', 'why'))) for e in evs]
        rows += [(c["t"], f"{'camera':12} {c.get('shot', '')}  {c.get('framing', '')} {c.get('lens', '')}mm → {c.get('look_at', '')}") for c in tl["camera"]]
        rows += [(p["t"], f"{'prop':12} {p['do']} {p.get('prop')}") for p in tl["props"]]
        rows += [(a.get("at", a.get("from", 0)), f"{'conductor':12} {a['do']}") for a in tl["conductor"]]
        for t, r in sorted(rows):
            lines.append(f"{int(t // 60)}:{t % 60:05.2f}  {r}")
    return "\n".join(lines)
