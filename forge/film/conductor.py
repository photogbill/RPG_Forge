"""A conductor's hands, made from a song's beat map (BUILD 43 part 4a) — so he conducts the actual track, in time.

    make(beatmap, acting=None, fps=30, lead=0.10, start=None, end=None) -> track
    check(track, beatmap) -> list of problems                           (the test: the ictus where the beat is, minus the lead)
    draw(track, beatmap, png)                                           the baton's path, a panel a bar, for looking at

What it does, in the order a conductor thinks it:
  * **The pattern for the meter**: down-left-right-up in four, down-right-up in three, down-up in two, down in one. The
    beat map says the meter of every bar. When the beats come faster than a conductor would beat them (an interval under
    0.45 s) he beats the bar in half - four in two, three in one - as conductors do at 150; when they come slower than
    one a second, he subdivides (a small rebound between beats).
  * **The ictus a little before the sound** (`lead`, a tenth of a second): an orchestra plays just behind the stick.
  * **Size follows loudness**: the beat map's loudness at each beat sets the pattern's size - small for the hushed strings,
    full arms for a refrain - eased so it does not jump from beat to beat.
  * **The rebound**: the hand falls into each ictus and bounces off it; between beats it travels along a curve that is
    slow at the top and fast into the next point.
  * **The left hand** rests at the chest and moves only when it has something to say: it cues an entrance (rises and
    points at the section a beat ahead and holds through it), closes for a cut-off (a small circle ending in a fist), and
    holds a fermata with the right.
  * **His acting**, on top (all optional, from the cue sheet's `conductor` beats):
        raise   {at}                 the baton goes up and everything waits (the house goes quiet)
        late    {from, to}           eyes on the stage: still in time, but late on the ictus
        freeze  {from, to}           he stops dead, the baton hanging, eyes on the stage, while the orchestra plays on
        oversize{from, to, size}     he remembers himself and conducts a size too big, every downbeat a flourish
        cue     {at, to, deg}        the left hand cues a section (deg: where it sits, 0 straight ahead, + to his right)
        nod     {at, to?}            a nod (to the stage, to a section)
        look    {from, to, yaw, pitch}  where his eyes are
        lean    {from, to}           he leans into the downbeats (a waltz)
        cutoff  {at}                 the left hand closes: everything stops
        fist    {at}                 the fist closes and stays closed
        hold    {from, to}           a fermata: both hands still, high
        rise    {at}                 he raises the orchestra (both arms up, palms up) - the curtain call
        rest    {from}               arms down: the number is over

The track is per frame, in metres, in the conductor's own space: x to his right, y forward (towards the orchestra),
z up, measured from a point between his shoulders. `forge/threed/blender/key_conductor.py` puts it on a body.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

# where each beat of a pattern lands on the conducting plane, as (x, z) in units of the pattern's size
# (x: + to the conductor's right; z: + up). Standard patterns, seen from behind him.
PATTERNS = {
    1: [(0.0, -1.0)],
    2: [(0.0, -1.0), (0.15, -0.2)],
    3: [(0.0, -1.0), (0.85, -0.55), (0.15, -0.15)],
    4: [(0.0, -1.0), (-0.8, -0.6), (0.85, -0.6), (0.1, -0.15)],
}
PLANE = (0.0, 0.32, -0.12)       # the centre of the conducting plane from the point between his shoulders (y forward)
LEFT_REST = (-0.22, 0.20, -0.30)  # the left hand at rest, near the chest
SIZE_MIN, SIZE_MAX = 0.10, 0.34   # the pattern's half-size in metres, pianissimo to fortissimo
MERGE_UNDER = 0.45                # beats closer than this are beaten in half
SUBDIVIDE_OVER = 1.0              # beats further apart than this are subdivided
ACT_KINDS = ("raise", "late", "freeze", "oversize", "cue", "nod", "look", "lean", "cutoff", "fist", "hold", "rise", "rest")


def _lerp(a, b, u):
    return tuple(a[i] + (b[i] - a[i]) * u for i in range(len(a)))


def _bez(p0, c0, c1, p1, u):
    v = 1.0 - u
    return tuple(v * v * v * p0[i] + 3 * v * v * u * c0[i] + 3 * v * u * u * c1[i] + u * u * u * p1[i] for i in range(3))


def _ease_inout(u):
    return u * u * (3 - 2 * u)


def _conduct_points(bm: dict) -> list[dict]:
    """The ictus points he beats: the beat map's beats, merged in half when fast, with their place in his pattern."""
    beats = [b for b in (bm.get("beats") or []) if b.get("bar", 0) > 0]
    if not beats:
        return []
    meters = {}
    for s in (bm.get("by_hand") or {}).get("meter") or bm.get("meter") or []:
        meters[int(s.get("from_bar", 1))] = int(s.get("beats_per_bar", 4))

    def meter_of(bar):
        m = 4
        for k in sorted(meters):
            if bar >= k:
                m = meters[k]
        return m

    out = []
    for i, b in enumerate(beats):
        m = meter_of(b["bar"])
        nxt = beats[i + 1]["t"] if i + 1 < len(beats) else b["t"] + 60.0 / max(b.get("bpm") or 120, 1)
        ibi = nxt - b["t"]
        beaten = m
        keep = True
        if ibi < MERGE_UNDER:
            if m == 4:
                beaten, keep = 2, b["beat"] in (1, 3)
            elif m == 3:
                beaten, keep = 1, b["beat"] == 1
            elif m == 2:
                beaten, keep = 1, b["beat"] == 1
            elif m == 6:
                beaten, keep = 2, b["beat"] in (1, 4)
        if not keep:
            continue
        if beaten == m:
            pos = (b["beat"] - 1) % len(PATTERNS.get(m, PATTERNS[4]))
        elif beaten == 2:
            pos = 0 if b["beat"] == 1 else 1
        else:
            pos = 0
        out.append({"t": float(b["t"]), "loud": float(b.get("loud", 0.5)), "bar": b["bar"], "beat": b["beat"],
                    "pattern": beaten if beaten in PATTERNS else 4, "pos": pos, "down": bool(b.get("down"))})
    # each point knows its duration (to the next point)
    for i, p in enumerate(out):
        p["dur"] = (out[i + 1]["t"] - p["t"]) if i + 1 < len(out) else 60.0 / 80.0
    return out


def _spans(acting, kind):
    return [a for a in (acting or []) if a.get("do") == kind]


def _in(t, spans):
    for a in spans:
        if float(a.get("from", a.get("at", 0))) <= t < float(a.get("to", 1e9)):
            return a
    return None


def make(bm: dict, acting: list | None = None, fps: int = 30, lead: float = 0.10, start: float | None = None,
         end: float | None = None) -> dict:
    """The conductor's track for a whole number. `acting` is the cue sheet's conductor beats, resolved to seconds."""
    acting = sorted(acting or [], key=lambda a: float(a.get("at", a.get("from", 0.0))))
    for a in acting:
        if a.get("do") not in ACT_KINDS:
            raise ValueError(f"the conductor has no '{a.get('do')}' (he can: {', '.join(ACT_KINDS)})")
    pts = _conduct_points(bm)
    dur = float(bm.get("duration") or (pts[-1]["t"] + 2 if pts else 10))
    t0 = float(start if start is not None else 0.0)
    t1 = float(end if end is not None else dur)
    n = int(math.ceil((t1 - t0) * fps)) + 1
    lates, freezes, overs, leans, holds = (_spans(acting, k) for k in ("late", "freeze", "oversize", "lean", "hold"))
    looks = _spans(acting, "look")
    raises = [float(a["at"]) for a in _spans(acting, "raise")]
    rests = [float(a.get("from", a.get("at"))) for a in _spans(acting, "rest")]
    rises = [float(a["at"]) for a in _spans(acting, "rise")]
    cues = _spans(acting, "cue")
    cutoffs = [float(a["at"]) for a in _spans(acting, "cutoff")]
    fists = [float(a["at"]) for a in _spans(acting, "fist")]
    nods = _spans(acting, "nod")

    # smoothed size per ictus
    sizes = []
    s_prev = None
    for p in pts:
        s = SIZE_MIN + (SIZE_MAX - SIZE_MIN) * max(0.0, min(1.0, p["loud"]))
        s_prev = s if s_prev is None else (0.65 * s_prev + 0.35 * s)
        sizes.append(s_prev)

    def ictus_pos(i):
        p = pts[i]
        pat = PATTERNS[p["pattern"]]
        x, z = pat[p["pos"] % len(pat)]
        s = sizes[i]
        ov = _in(p["t"], overs)
        if ov:
            s *= float(ov.get("size", 1.55))
        return (PLANE[0] + x * s, PLANE[1], PLANE[2] + z * s), s

    # the times he actually beats: lead before the sound, or late when his eyes are on the stage
    def ictus_time(i):
        t = pts[i]["t"]
        if _in(t, lates):
            return t + 0.12
        return t - lead

    right, left, fist_v, head, torso, events = [], [], [], [], [], []
    idx = 0
    for f in range(n):
        t = t0 + f / fps
        # --- the right hand
        while idx + 1 < len(pts) and ictus_time(idx + 1) <= t:
            idx += 1
        rh = None
        before = not pts or t < ictus_time(0)
        if before:
            # before the first beat: down at rest, or up and waiting if he has raised the baton
            r_at = next((r for r in raises if r <= t), None)
            if r_at is not None:
                u = _ease_inout(min(1.0, (t - r_at) / 1.0))
                rh = _lerp((0.12, 0.18, -0.40), (0.06, 0.30, 0.18), u)
            else:
                rh = (0.12, 0.18, -0.40)
            if pts and ictus_time(0) - t < 60.0 / 80.0:      # the preparatory beat: a lift into the first ictus
                p0, _ = ictus_pos(0)
                u = 1.0 - (ictus_time(0) - t) / (60.0 / 80.0)
                top = (p0[0], p0[1], p0[2] + 0.45)
                start_pt = rh
                rh = _bez(start_pt, (start_pt[0], start_pt[1], start_pt[2] + 0.1), top, p0, _ease_inout(u))
        else:
            a_i = idx
            b_i = min(idx + 1, len(pts) - 1)
            pa, sa = ictus_pos(a_i)
            pb, sb = ictus_pos(b_i)
            ta, tb = ictus_time(a_i), ictus_time(b_i)
            if b_i == a_i or tb <= ta:
                rh = pa
            else:
                u = max(0.0, min(1.0, (t - ta) / (tb - ta)))
                k = 0.55
                uu = u + k * math.sin(2 * math.pi * u) / (2 * math.pi)        # fast out of the ictus and into the next
                reb = 0.55 * sa + 0.05
                if pts[a_i]["dur"] > SUBDIVIDE_OVER:                         # slow: a small extra rebound mid-beat
                    reb *= 0.7
                    sub = math.sin(2 * math.pi * u) * 0.04 * sa / max(sa, 1e-3)
                else:
                    sub = 0.0
                c0 = (pa[0] + (pb[0] - pa[0]) * 0.15, pa[1] + 0.03, pa[2] + reb)
                c1 = (pb[0], pb[1] + 0.02, pb[2] + reb * 0.65)
                rh = _bez(pa, c0, c1, pb, uu)
                rh = (rh[0], rh[1], rh[2] + sub)
                ov = _in(pts[a_i]["t"], overs)
                if ov and pts[a_i]["down"]:                                  # a flourish on each downbeat
                    w = math.sin(math.pi * u)
                    rh = (rh[0] + 0.06 * w * math.cos(4 * math.pi * u), rh[1] + 0.04 * w, rh[2] + 0.06 * w * math.sin(4 * math.pi * u))
        fr = _in(t, freezes)
        if fr:
            k_in = min(1.0, (t - float(fr["from"])) / 0.35)                 # the baton sinks in a third of a second
            hang = (0.14, 0.24, -0.34)
            rh = _lerp(rh, hang, _ease_inout(k_in))
        hd = _in(t, holds)
        if hd:
            rh = (PLANE[0] + 0.05, PLANE[1] + 0.02, PLANE[2] + 0.30)
        last_rest = max([r for r in rests if r <= t], default=None)
        if last_rest is not None:
            u = _ease_inout(min(1.0, (t - last_rest) / 1.2))
            rh = _lerp(rh, (0.18, 0.12, -0.55), u)
        last_rise = max([r for r in rises if r <= t], default=None)
        if last_rise is not None and (last_rest is None or last_rise > last_rest):
            u = _ease_inout(min(1.0, (t - last_rise) / 0.8))
            rh = _lerp(rh, (0.38, 0.30, 0.42), u)

        # --- the left hand
        lh = LEFT_REST
        cue = next((c for c in cues if float(c["at"]) - 0.55 <= t <= float(c["at"]) + float(c.get("hold", 1.2))), None)
        if cue:
            ang = math.radians(float(cue.get("deg", -30.0)))
            aim = (0.45 * math.sin(ang), 0.30 + 0.25 * math.cos(ang), 0.05)
            u = (t - (float(cue["at"]) - 0.55)) / 0.55
            if u < 1.0:
                lh = _lerp(LEFT_REST, aim, _ease_inout(max(0.0, u)))
            else:
                back = (t - float(cue["at"])) / float(cue.get("hold", 1.2))
                lh = aim if back < 0.75 else _lerp(aim, LEFT_REST, _ease_inout((back - 0.75) / 0.25))
        cut = next((c for c in cutoffs if c - 0.6 <= t <= c + 0.5), None)
        closed = 0.0
        if cut is not None:
            u = (t - (cut - 0.6)) / 0.6
            if u <= 1.0:
                ang = 2 * math.pi * u
                lh = (-0.25 + 0.08 * math.cos(ang), 0.32, 0.10 + 0.08 * math.sin(ang))
            else:
                lh = (-0.25 + 0.08, 0.32, 0.10)
                closed = 1.0
        if any(t >= x for x in fists):
            closed = 1.0
        if hd:
            lh = (-0.30, 0.30, 0.22)
        if fr:
            lh = _lerp(lh, (-0.18, 0.16, -0.40), _ease_inout(min(1.0, (t - float(fr["from"])) / 0.35)))
        if last_rise is not None and (last_rest is None or last_rise > last_rest):
            lh = _lerp(lh, (-0.38, 0.30, 0.42), _ease_inout(min(1.0, (t - last_rise) / 0.8)))
        if last_rest is not None:
            lh = _lerp(lh, (-0.18, 0.12, -0.55), _ease_inout(min(1.0, (t - last_rest) / 1.2)))

        # --- the head and the body
        yaw, pitch = 0.0, -8.0                      # eyes on the score / the players
        lk = _in(t, looks)
        if lk:
            yaw, pitch = float(lk.get("yaw", 0.0)), float(lk.get("pitch", 12.0))
        if fr or _in(t, lates):                     # eyes up, on the stage
            yaw, pitch = (float(lk.get("yaw", 0.0)) if lk else 0.0), 16.0
        if cue:
            yaw = float(cue.get("deg", -30.0)) * 0.6
        nd = next((x for x in nods if float(x["at"]) <= t <= float(x["at"]) + 0.5), None)
        if nd:
            pitch -= 14.0 * math.sin(math.pi * (t - float(nd["at"])) / 0.5)
            if nd.get("deg") is not None:
                yaw = float(nd["deg"]) * 0.6
        lean_f, sway = 0.0, 0.0
        if not before and pts:
            p = pts[idx]
            if _in(t, leans) and p["down"]:
                u = (t - ictus_time(idx)) / max(p["dur"], 1e-3)
                lean_f = 6.0 * math.sin(math.pi * min(1.0, u))
            sway = 1.5 * math.sin(2 * math.pi * ((t - ictus_time(idx)) / max(p["dur"], 1e-3)) * 0.5) if p["pattern"] == 3 else 0.0
            ov = _in(p["t"], overs)
            if ov:
                lean_f += 3.0
        right.append([round(v, 4) for v in rh])
        left.append([round(v, 4) for v in lh])
        fist_v.append(closed)
        head.append([round(yaw, 2), round(pitch, 2)])
        torso.append([round(lean_f, 2), round(sway, 2)])
    ictus = [{"t": round(ictus_time(i), 3), "beat_t": round(p["t"], 3), "bar": p["bar"], "beat": p["beat"],
              "pattern": p["pattern"], "pos": p["pos"], "size": round(sizes[i], 3),
              "late": bool(_in(p["t"], lates)), "frozen": bool(_in(ictus_time(i), freezes))}
             for i, p in enumerate(pts) if t0 <= ictus_time(i) <= t1]
    return {"_about": "A conductor's track (forge.film.conductor): per frame, metres in his own space - x to his right, "
                      "y towards the orchestra, z up - from the point between his shoulders. head = [yaw, pitch] degrees, "
                      "torso = [lean forward, sway] degrees.",
            "fps": fps, "start": t0, "frames": n, "lead": lead, "right": right, "left": left, "left_fist": fist_v,
            "head": head, "torso": torso, "ictus": ictus, "acting": acting}


def check(track: dict, bm: dict, tol: float = 0.025) -> list[str]:
    """Problems, or []: every ictus he beats (not late, not frozen) lands `lead` before its beat, and his right hand is at
    the lowest point of its fall within a frame of the ictus. Late ictus land after the beat; frozen ones are not beaten."""
    probs = []
    fps = track["fps"]
    t0 = track.get("start", 0.0)
    r = track["right"]
    for ic in track["ictus"]:
        want = ic["beat_t"] + (0.12 if ic["late"] else -track["lead"])
        if abs(ic["t"] - want) > tol:
            probs.append(f"bar {ic['bar']} beat {ic['beat']}: ictus at {ic['t']:.3f}, wanted {want:.3f}")
        if ic["frozen"]:
            continue
        f = int(round((ic["t"] - t0) * fps))
        if 1 <= f < len(r) - 1:
            z = r[f][2]
            # the hand is at (or within 2 cm of) a low point of its path at the ictus
            lo = min(r[max(0, f - 2)][2], r[min(len(r) - 1, f + 2)][2])
            if z > lo + 0.02:
                probs.append(f"bar {ic['bar']} beat {ic['beat']}: the hand is not at the bottom of its fall ({z:.3f} vs {lo:.3f})")
    return probs


def write(track: dict, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(track, separators=(",", ":")), encoding="utf-8")
    return path


def draw(track: dict, png, seconds: float = 12.0, start: float | None = None) -> Path:
    """The baton's path seen from behind him, one panel a bar, for the first `seconds` from `start`: each panel shows
    the bar's ictus as numbered dots. And under them the height of the hand over time with the beats marked."""
    from PIL import Image, ImageDraw
    fps = track["fps"]
    t0 = track.get("start", 0.0) if start is None else start
    ictus = [ic for ic in track["ictus"] if t0 <= ic["t"] <= t0 + seconds]
    bars = sorted({ic["bar"] for ic in ictus})[:12]
    W, PW = 1800, 300
    rows = max(1, math.ceil(len(bars) / 6))
    img = Image.new("RGB", (W, rows * PW + 260), (250, 248, 244))
    d = ImageDraw.Draw(img)
    r = track["right"]
    for k, bar in enumerate(bars):
        ox, oy = (k % 6) * PW, (k // 6) * PW
        d.rectangle([ox + 4, oy + 4, ox + PW - 4, oy + PW - 4], outline=(200, 196, 188))
        d.text((ox + 10, oy + 8), f"bar {bar}", fill=(40, 40, 40))
        ics = [ic for ic in ictus if ic["bar"] == bar]
        if not ics:
            continue
        ts = track.get("start", 0.0)
        f0 = int((ics[0]["t"] - ts) * fps)
        nxt = [ic for ic in track["ictus"] if ic["bar"] > bar]
        f1 = int(((nxt[0]["t"] if nxt else ics[-1]["t"] + 0.6) - ts) * fps)
        pts = [(ox + PW / 2 + r[f][0] * 380, oy + PW / 2 - (r[f][2] - PLANE[2]) * 380) for f in range(max(0, f0), min(len(r), f1))]
        if len(pts) > 1:
            d.line(pts, fill=(30, 70, 200), width=2)
        for n_, ic in enumerate(ics, 1):
            f = int(round((ic["t"] - ts) * fps))
            if 0 <= f < len(r):
                x, y = ox + PW / 2 + r[f][0] * 380, oy + PW / 2 - (r[f][2] - PLANE[2]) * 380
                d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=(210, 30, 30))
                d.text((x + 6, y - 6), str(n_), fill=(210, 30, 30))
    oy = rows * PW + 20
    d.text((10, oy), f"height of the right hand, {seconds:.0f} s from {t0:.1f} s; red lines: the ictus; grey: the beats", fill=(40, 40, 40))
    f_a, f_b = int((t0 - track.get("start", 0.0)) * fps), int((t0 + seconds - track.get("start", 0.0)) * fps)
    seg = r[max(0, f_a):min(len(r), f_b)]
    if seg:
        xs = [10 + i * (W - 20) / max(1, len(seg) - 1) for i in range(len(seg))]
        ys = [oy + 200 - (p[2] + 0.6) * 160 for p in seg]
        d.line(list(zip(xs, ys)), fill=(30, 70, 200), width=2)
        for ic in track["ictus"]:
            if t0 <= ic["t"] <= t0 + seconds:
                x = 10 + (ic["t"] - t0) * fps * (W - 20) / max(1, len(seg) - 1)
                d.line([(x, oy + 30), (x, oy + 230)], fill=(210, 30, 30))
                xb = 10 + (ic["beat_t"] - t0) * fps * (W - 20) / max(1, len(seg) - 1)
                d.line([(xb, oy + 30), (xb, oy + 230)], fill=(170, 170, 170))
    png = Path(png)
    png.parent.mkdir(parents=True, exist_ok=True)
    img.save(png)
    return png
