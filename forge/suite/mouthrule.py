"""The mouth rule, once, in the suite (BUILD 71): the same rule as the game's MouthModel (BUILD 61), line for line — which
shape is showing at a time, the 60 ms blend between shapes, the fallbacks for a face drawn with few mouths. One file of
cases (tests/fixtures/mouth/cases.json) is read by the suite's test and by the game's unit test, so the two cannot drift.

Rhubarb's nine shapes: A closed (P B M) · B a little open · C open (EH, AE) · D wide (AA) · E rounded (AO, ER) ·
F puckered (UW, OW, W) · G teeth on the lip (F, V) · H the tongue (L) · X at rest.
"""
from __future__ import annotations

SHAPES = ["A", "B", "C", "D", "E", "F", "G", "H", "X"]
REST = "X"
FALLBACK = {"G": "B", "H": "C", "X": "A", "E": "C", "F": "B", "D": "C"}
BLEND_SEC = 0.06
DESCRIBE = {"A": "closed — P, B, M", "B": "a little open — most consonants", "C": "open — EH, AE", "D": "wide — AA",
            "E": "rounded — AO, ER", "F": "puckered — UW, OW, W", "G": "teeth on the lower lip — F, V", "H": "the tongue — L",
            "X": "at rest"}


def parse(data) -> list[dict]:
    rows = []
    if isinstance(data, dict):
        for c in data.get("mouthCues") or []:
            if isinstance(c, dict):
                rows.append({"t": float(c.get("start", 0.0)), "end": float(c.get("end", -1.0)), "shape": str(c.get("value", REST)).upper()})
    elif isinstance(data, list):
        for c in data:
            if isinstance(c, (list, tuple)) and len(c) >= 2:
                rows.append({"t": float(c[0]), "end": -1.0, "shape": str(c[1]).upper()})
            elif isinstance(c, dict):
                rows.append({"t": float(c.get("t", c.get("start", 0.0))), "end": float(c.get("end", -1.0)),
                             "shape": str(c.get("shape", c.get("value", REST))).upper()})
    rows = [r for r in rows if r["shape"] in SHAPES and r["t"] >= 0.0]
    rows.sort(key=lambda r: r["t"])
    for i, r in enumerate(rows):
        nxt = rows[i + 1]["t"] if i + 1 < len(rows) else -1.0
        if nxt >= 0.0 and (r["end"] < 0.0 or r["end"] > nxt):
            r["end"] = nxt
        elif nxt < 0.0 and r["end"] < r["t"]:
            r["end"] = r["t"] + 0.2
    return rows


def duration(track: list[dict]) -> float:
    return float(track[-1]["end"]) if track else 0.0


def _index_at(track: list[dict], t: float) -> int:
    if not track or t < track[0]["t"] or t >= duration(track):
        return -1
    lo, hi = 0, len(track) - 1
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        if track[mid]["t"] <= t:
            lo = mid
        else:
            hi = mid - 1
    return lo


def shape_at(track: list[dict], t: float) -> str:
    i = _index_at(track, t)
    return track[i]["shape"] if i >= 0 else REST


def blend_at(track: list[dict], t: float, blend: float = BLEND_SEC) -> dict:
    i = _index_at(track, t)
    if i < 0:
        after_end = bool(track) and t >= duration(track)
        prev = track[-1]["shape"] if after_end else REST
        since = t - duration(track) if after_end else 0.0
        if after_end and prev != REST and blend > 0.0 and since < blend:
            return {"from": prev, "to": REST, "w": min(1.0, max(0.0, since / blend))}
        return {"from": REST, "to": REST, "w": 1.0}
    shape = track[i]["shape"]
    before = track[i - 1]["shape"] if i > 0 else REST
    into = t - track[i]["t"]
    if blend <= 0.0 or before == shape or into >= blend:
        return {"from": shape, "to": shape, "w": 1.0}
    return {"from": before, "to": shape, "w": min(1.0, max(0.0, into / blend))}


def frame_for(shape: str, available) -> str:
    av = set(available)
    if not av:
        return ""
    s, guard = shape, 0
    while s not in av and s in FALLBACK and guard < 8:
        s, guard = FALLBACK[s], guard + 1
    if s in av:
        return s
    return "A" if "A" in av else sorted(av)[0]


def lane(track: list[dict], step: float = 1 / 30, offset: float = 0.0, blend: float = BLEND_SEC, available=None) -> list[dict]:
    """What the face shows frame by frame (the bench draws this; the server works it out): `offset` moves the mouth
    against its sound (negative = the mouth leads)."""
    out = []
    n = int((duration(track) + 0.3) / step) + 1
    for k in range(max(n, 1)):
        t = k * step
        b = blend_at(track, t - offset, blend)
        row = {"t": round(t, 4), **b}
        if available is not None:
            row["frame_from"], row["frame_to"] = frame_for(b["from"], available), frame_for(b["to"], available)
        out.append(row)
    return out
