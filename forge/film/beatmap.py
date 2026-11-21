"""A song's beat map: what a conductor, a cue sheet and a camera need to know about when things happen in a track.

    analyse(path, meter=4, bpm_hint=None, sections=None) -> dict      measure a track
    merge_by_hand(new, old) -> dict                                   keep what a person corrected in the old file
    write(bm, path) / read(path)
    draw(bm, path_png, audio=None)                                    the map over the waveform, a row every 30 seconds
    bar_time(bm, bar, beat=1) -> seconds                              where a bar (and a beat in it) falls
    strong(bm, t, tol=0.06) -> bool                                   is t on a strong beat (a downbeat, or the middle of a bar in four)

What is measured (librosa, ISC licence; no model with a non-commercial licence is used):
  * beats: the predominant local pulse (PLP), which follows a tempo that changes - a duel's accelerando - where a single
    global tempo would drift; a steady track gets the dynamic-programming tracker, whose beats sit tighter on a steady grid.
    Which was used is written down (`tempo.method`), and so is how steady the beats are (`checks.grid_ms_median`).
  * the local tempo at every beat, and the loudness at every beat (0 = the quiet end of this track, 1 = its loud end).
  * the meter by section (handed in, from the song's sheet: a march in four, a waltz in three) and the downbeats: for each
    section the phase whose beats carry the most accent and bass is the bar line. A person corrects a bar line by hand.
  * silences (a sudden stop, the silence after the last note), hits (the strongest attacks: a crash of percussion), and
    holds (a long note with nothing new in it: a fermata, a held chord) - the moments a staging is built to land on.

The file keeps a `by_hand` block. Anything a person puts there wins over the measurement on every re-run:
    "by_hand": {"bars": {"57": 91.23}, "moments": {"crash": 88.40}, "meter": [{"from_bar": 1, "beats_per_bar": 3}]}
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path

ABOUT = ("A beat map (forge.film.beatmap). Times in seconds from the start of the track. Correct it by hand under "
         "'by_hand' (bars, moments, meter): a re-run keeps those and measures the rest again.")
HOP = 512
SR = 22050


# ----------------------------------------------------------------------------------------------------------- measuring
def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _spans(mask, times, min_len: float) -> list[dict]:
    """Runs of True in a frame mask, as {from, to} in seconds, at least min_len long."""
    out, start = [], None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        elif not m and start is not None:
            if times[i] - times[start] >= min_len:
                out.append({"from": round(float(times[start]), 3), "to": round(float(times[i]), 3)})
            start = None
    if start is not None and times[-1] - times[start] >= min_len:
        out.append({"from": round(float(times[start]), 3), "to": round(float(times[-1]), 3)})
    return out


def _grid_deviation(beats) -> float:
    """Median distance (ms) of each beat from a straight line through its eight neighbours: how steady the beats are."""
    import numpy as np
    b = np.asarray(beats, dtype=float)
    if len(b) < 9:
        return 0.0
    devs = []
    for i in range(len(b)):
        lo, hi = max(0, i - 4), min(len(b), i + 5)
        idx = np.arange(lo, hi)
        a, c = np.polyfit(idx, b[lo:hi], 1)
        devs.append(abs(b[i] - (a * i + c)))
    return float(np.median(devs) * 1000.0)


def _meter_at(meter: list[dict], beat_index: int, bars_so_far: int) -> int:
    m = 4
    for s in meter:
        if bars_so_far + 1 >= int(s.get("from_bar", 1)):
            m = int(s.get("beats_per_bar", 4))
    return max(1, m)


def analyse(path, meter: int | list = 4, bpm_hint: float | None = None, sections: list | None = None,
            method: str = "auto") -> dict:
    """Measure one track. `meter` is beats a bar for the whole song, or a list of sections
    [{"from_t": seconds, "beats_per_bar": 3}, ...] (a section starts at the first beat at or after from_t).
    `bpm_hint` (from the song's sheet) keeps the tracker off half and double tempo. `method`: auto | plp | dp."""
    import numpy as np
    import librosa

    path = Path(path)
    y, sr = librosa.load(str(path), sr=SR, mono=True)
    dur = float(len(y) / sr)
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP, aggregate=np.median)
    times = librosa.times_like(env, sr=sr, hop_length=HOP)
    lo_t, hi_t = (bpm_hint * 0.7, bpm_hint * 1.45) if bpm_hint else (50.0, 200.0)

    # one global tempo, at the octave the song's sheet asks for (the hint keeps it off half and double time)
    if bpm_hint:
        import scipy.stats
        prior = scipy.stats.uniform(lo_t, hi_t - lo_t)
        tempo_g = float(np.atleast_1d(librosa.feature.tempo(onset_envelope=env, sr=sr, hop_length=HOP, prior=prior))[0])
    else:
        tempo_g = float(np.atleast_1d(librosa.feature.tempo(onset_envelope=env, sr=sr, hop_length=HOP))[0])
    # the two trackers: dynamic programming on that tempo (tight on a steady grid), and the predominant local pulse
    # (follows a tempo that moves)
    _t, beats_dp = librosa.beat.beat_track(onset_envelope=env, sr=sr, hop_length=HOP, bpm=tempo_g, units="frames",
                                           trim=False, tightness=100)
    pulse = librosa.beat.plp(onset_envelope=env, sr=sr, hop_length=HOP, tempo_min=tempo_g * 0.8, tempo_max=tempo_g * 1.35)
    beats_plp = np.flatnonzero(librosa.util.localmax(pulse))
    if len(beats_plp):                       # a pulse peak in near-silence is not a beat
        floor = float(np.percentile(pulse, 20))
        beats_plp = beats_plp[pulse[beats_plp] > floor]
    if method == "dp":
        chosen, how = beats_dp, "dp"
    elif method == "plp":
        chosen, how = beats_plp, "plp"
    else:
        moving = len(beats_plp) > 24 and _tempo_moves(times[beats_plp], tol=0.08)
        chosen, how = (beats_plp, "plp") if (moving or len(beats_dp) < 9) else (beats_dp, "dp")
    bt = times[chosen].astype(float)
    bt = bt[(bt >= 0.0) & (bt <= dur)]

    # loudness at every beat
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=HOP)[0]
    db = 20.0 * np.log10(np.maximum(rms, 1e-6))
    q_lo, q_hi = float(np.percentile(db, 5)), float(np.percentile(db, 98))

    def loud_at(t):
        i0 = int(max(0, (t - 0.05) * sr / HOP)); i1 = int(min(len(db) - 1, (t + 0.15) * sr / HOP))
        v = float(db[i0:i1 + 1].max()) if i1 >= i0 else float(db[min(i0, len(db) - 1)])
        return max(0.0, min(1.0, (v - q_lo) / max(q_hi - q_lo, 1e-3)))

    onset_t = librosa.onset.onset_detect(onset_envelope=env, sr=sr, hop_length=HOP, units="time")
    # bass energy, for the downbeats
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=HOP))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    bass = S[freqs < 180.0].sum(axis=0)
    bass = bass / max(float(bass.max()), 1e-9)
    envn = env / max(float(env.max()), 1e-9)

    def frame_of(t):
        return int(min(len(env) - 1, max(0, round(t * sr / HOP))))

    accent = np.array([envn[frame_of(t)] + 0.6 * bass[min(len(bass) - 1, frame_of(t))] for t in bt]) if len(bt) else np.array([])

    # meter by section, and the downbeat phase in each
    if isinstance(meter, list):
        secs = sorted(meter, key=lambda s: float(s.get("from_t", 0.0)))
    else:
        secs = [{"from_t": 0.0, "beats_per_bar": int(meter)}]
    if sections:
        secs = sorted(sections, key=lambda s: float(s.get("from_t", 0.0)))
    beat_sec = []                                   # section index for every beat
    for t in bt:
        k = 0
        for j, s in enumerate(secs):
            if t + 1e-6 >= float(s.get("from_t", 0.0)):
                k = j
        beat_sec.append(k)
    downs = set()
    meter_out = []
    i = 0
    bars = 0
    while i < len(bt):
        k = beat_sec[i]
        j = i
        while j < len(bt) and beat_sec[j] == k:
            j += 1
        m = max(1, int(secs[k].get("beats_per_bar", 4)))
        seg = accent[i:j]
        best, best_score = 0, -1.0
        for p in range(min(m, max(1, len(seg)))):
            sc = float(seg[p::m].mean()) if len(seg[p::m]) else 0.0
            if sc > best_score + 1e-9:
                best, best_score = p, sc
        # beats before the first downbeat of a section are a pick-up: they belong to the bar before
        meter_out.append({"from_bar": bars + 1, "beats_per_bar": m, "t": round(float(bt[i + best]) if i + best < len(bt) else float(bt[i]), 3),
                          "phase": best})
        for q in range(i + best, j, m):
            downs.add(q)
            bars += 1
        i = j

    beats = []
    bar_list = []
    bar_no, beat_in_bar = 0, 0
    first_down = min(downs) if downs else 0
    for idx, t in enumerate(bt):
        if idx in downs:
            bar_no += 1
            beat_in_bar = 1
            bar_list.append({"bar": bar_no, "t": round(float(t), 3)})
        elif idx < first_down:
            beat_in_bar = 0                          # a pick-up before bar 1
        else:
            beat_in_bar += 1
        prev = bt[idx - 1] if idx else None
        nxt = bt[idx + 1] if idx + 1 < len(bt) else None
        ibi = (nxt - t) if nxt is not None else ((t - prev) if prev is not None else 0.5)
        beats.append({"t": round(float(t), 3), "bpm": round(60.0 / max(ibi, 1e-3), 1), "loud": round(loud_at(t), 3),
                      "onset": bool(len(onset_t) and float(np.min(np.abs(onset_t - t))) <= 0.06),
                      "bar": bar_no if beat_in_bar else 0, "beat": beat_in_bar, "down": idx in downs})
    # smooth the local tempo (a median of five) so one late beat does not read as a tempo change
    raw = [b["bpm"] for b in beats]
    for k2, b in enumerate(beats):
        win = sorted(raw[max(0, k2 - 2):k2 + 3])
        b["bpm"] = round(win[len(win) // 2], 1)

    # silences, hits, holds
    import scipy.ndimage
    around = scipy.ndimage.median_filter(db, size=max(3, int(2.0 * sr / HOP)), mode="nearest")
    loud_near = scipy.ndimage.maximum_filter1d(db, size=max(3, int(1.5 * sr / HOP)), mode="nearest")
    quiet = (db < (q_hi - 35.0)) | ((db < around - 14.0) & (db < loud_near - 20.0))
    silences = _spans(quiet, times, 0.25)
    med = float(np.median(env)); mad = float(np.median(np.abs(env - med))) or 1e-6
    peaks = (librosa.util.peak_pick(env, pre_max=8, post_max=8, pre_avg=40, post_avg=40, delta=6 * mad, wait=20)
             if len(env) > 100 else np.array([], dtype=int))
    hits = []
    for p in peaks:
        jump = float(db[min(len(db) - 1, p + 3)] - db[max(0, p - 6)])
        hits.append({"t": round(float(times[p]), 3), "strength": round(float(env[p] / max(env.max(), 1e-9)), 3),
                     "loud": round(max(0.0, min(1.0, (float(db[min(len(db) - 1, p + 2)]) - q_lo) / max(q_hi - q_lo, 1e-3))), 3),
                     "jump_db": round(jump, 1)})
    hits.sort(key=lambda h: -(h["strength"] + 0.02 * max(0.0, h["jump_db"])))
    hits = sorted(hits[:24], key=lambda h: h["t"])
    # holds: sound sustained but nothing new attacking for at least 1.5 s
    dens = np.zeros_like(env)
    for ot in onset_t:
        dens[frame_of(float(ot))] = 1.0
    win = max(1, int(1.0 * sr / HOP))
    density = np.convolve(dens, np.ones(win), mode="same")
    sustained = (db > (float(np.percentile(db, 50)) - 6.0)) & (density < 0.9)
    holds = _spans(sustained, times, 1.5)

    # sections by what the music is doing (timbre and harmony change): one a ~25 s, each snapped to the nearest bar line
    segments = []
    try:
        feat = np.vstack([librosa.feature.mfcc(y=y, sr=sr, hop_length=HOP, n_mfcc=13),
                          librosa.feature.chroma_stft(y=y, sr=sr, hop_length=HOP)])
        k = int(max(3, min(16, round(dur / 25.0))))
        bounds = librosa.segment.agglomerative(feat, k)
        bt_down = [b["t"] for b in beats if b["down"]] or [b["t"] for b in beats]
        cuts = sorted({min(bt_down, key=lambda x: abs(x - float(times[min(len(times) - 1, int(f))]))) if bt_down else 0.0
                       for f in bounds})
        cuts = [c for c in cuts if c > 0.5] 
        edges = [0.0] + cuts + [dur]
        for a, b in zip(edges[:-1], edges[1:]):
            if b - a < 1.0:
                continue
            i0, i1 = int(a * sr / HOP), int(b * sr / HOP)
            lv = float(np.mean(db[i0:max(i0 + 1, i1)]))
            segments.append({"from": round(a, 3), "to": round(b, 3),
                             "loud": round(max(0.0, min(1.0, (lv - q_lo) / max(q_hi - q_lo, 1e-3))), 3),
                             "bpm": round(_bpm_of([x for x in bt if a <= x < b]), 1)})
    except Exception as e:  # noqa: BLE001  (segments are a help, never a reason to fail)
        segments = [{"from": 0.0, "to": round(dur, 3), "note": f"not measured: {e}"}]

    bpm_all = [b["bpm"] for b in beats] or [0.0]
    sorted_bpm = sorted(bpm_all)
    bm = {
        "_about": ABOUT,
        "track": path.name, "md5": _md5(path), "duration": round(dur, 3),
        "made": time.strftime("%Y-%m-%dT%H:%M:%S"), "by": "forge.film.beatmap (librosa %s)" % librosa.__version__,
        "tempo": {"global_bpm": round(tempo_g, 1), "median_bpm": round(sorted_bpm[len(sorted_bpm) // 2], 1), "min_bpm": round(sorted_bpm[0], 1),
                  "max_bpm": round(sorted_bpm[-1], 1), "method": how, "hint_bpm": bpm_hint,
                  "first_bars_bpm": round(_bpm_of(bt[: 17]), 1), "last_bars_bpm": round(_bpm_of(bt[-17:]), 1)},
        "meter": meter_out,
        "beats": beats, "bars": bar_list,
        "silences": silences, "hits": hits, "holds": holds, "segments": segments,
        "checks": {"beats": len(beats), "bars": len(bar_list),
                   "grid_ms_median": round(_grid_deviation(bt), 1),
                   "onset_share": round(sum(1 for b in beats if b["onset"]) / max(1, len(beats)), 3),
                   "tempo_moves": bool(len(bt) > 8 and _tempo_moves(bt))},
        "by_hand": {},
    }
    return bm


def _bpm_of(ts) -> float:
    import numpy as np
    ts = np.asarray(ts, dtype=float)
    if len(ts) < 2:
        return 0.0
    return float(60.0 / np.median(np.diff(ts)))


def _tempo_moves(ts, tol: float = 0.06) -> bool:
    """True when the tempo of the first quarter and the last quarter of the beats differ by more than 6% - an
    accelerando or a ritardando that a single global tempo would not follow."""
    import numpy as np
    ts = np.asarray(ts, dtype=float)
    n = len(ts)
    if n < 24:
        return False
    q = n // 4
    a = 60.0 / np.median(np.diff(ts[:q])); b = 60.0 / np.median(np.diff(ts[-q:]))
    # also a moving middle: the tempo of any eighth departing from the median by 10%
    med = 60.0 / np.median(np.diff(ts))
    eighths = [60.0 / np.median(np.diff(ts[i:i + max(4, n // 8)])) for i in range(0, n - max(4, n // 8), max(4, n // 8))]
    return bool(abs(a - b) / max(a, 1e-3) > tol or any(abs(e - med) / med > tol + 0.04 for e in eighths))


# --------------------------------------------------------------------------------------------------- by hand, files
def merge_by_hand(new: dict, old: dict | None) -> dict:
    """Keep a person's corrections. `old["by_hand"]` is copied over; bars moved by hand move their downbeats."""
    if not old:
        return new
    bh = dict(old.get("by_hand") or {})
    new["by_hand"] = bh
    for k, t in (bh.get("bars") or {}).items():
        for b in new["bars"]:
            if str(b["bar"]) == str(k):
                b["t"] = float(t)
                b["by_hand"] = True
    return new


def write(bm: dict, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    old = None
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            old = None
    bm = merge_by_hand(bm, old)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(bm, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return path


def read(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------------------------------------ queries
def bar_time(bm: dict, bar: int, beat: float = 1.0) -> float:
    """Seconds at a bar and a beat (1-based; a fraction is between beats). A bar moved by hand is used as moved."""
    bh = (bm.get("by_hand") or {}).get("bars") or {}
    bars = bm.get("bars") or []
    if not bars:
        raise ValueError("this beat map has no bars")
    bar = int(bar)
    if bar < 1 or bar > len(bars) + 1:
        raise ValueError(f"bar {bar} is outside the song (1..{len(bars)})")
    if bar == len(bars) + 1:                  # the bar after the last: the end of the last bar
        return float(bm["duration"])
    t0 = float(bh.get(str(bar), bars[bar - 1]["t"]))
    if beat <= 1.0:
        return t0
    # walk the beats of this bar
    beats = [b for b in bm["beats"] if b.get("bar") == bar]
    whole = int(math.floor(beat))
    frac = beat - whole
    if whole - 1 < len(beats):
        ta = float(beats[whole - 1]["t"]) if whole - 1 >= 0 else t0
        if frac <= 1e-9:
            return ta
        tb = float(beats[whole]["t"]) if whole < len(beats) else bar_time(bm, bar + 1, 1)
        return ta + frac * (tb - ta)
    return bar_time(bm, bar + 1, 1)


def beat_at(bm: dict, t: float) -> dict | None:
    best = None
    for b in bm.get("beats") or []:
        if best is None or abs(b["t"] - t) < abs(best["t"] - t):
            best = b
    return best


def strong(bm: dict, t: float, tol: float = 0.06) -> bool:
    """On a strong beat: a downbeat, or beat 3 of a bar in four (beat 1 only in three and two)."""
    b = beat_at(bm, t)
    if not b or abs(b["t"] - t) > tol:
        return False
    if b.get("down"):
        return True
    m = _meter_of_bar(bm, b.get("bar") or 0)
    return m == 4 and b.get("beat") == 3


def _meter_of_bar(bm: dict, bar: int) -> int:
    m = 4
    for s in (bm.get("by_hand") or {}).get("meter") or bm.get("meter") or []:
        if bar >= int(s.get("from_bar", 1)):
            m = int(s.get("beats_per_bar", 4))
    return m


def moments(bm: dict) -> dict:
    """Named moments a staging can point at, measured: the first and last sound, every silence, the strongest hits.
    A person's `by_hand.moments` wins over these."""
    out = {}
    beats = bm.get("beats") or []
    if beats:
        out["first_beat"] = beats[0]["t"]
        out["last_beat"] = beats[-1]["t"]
    for i, s in enumerate(bm.get("silences") or [], 1):
        out[f"silence_{i}"] = s["from"]
        out[f"silence_{i}_end"] = s["to"]
    hits = sorted(bm.get("hits") or [], key=lambda h: -h["strength"])
    for i, h in enumerate(sorted(hits[:8], key=lambda h: h["t"]), 1):
        out[f"hit_{i}"] = h["t"]
    for i, sg in enumerate(bm.get("segments") or [], 1):
        out[f"segment_{i}"] = sg["from"]
    for i, h in enumerate(bm.get("holds") or [], 1):
        out[f"hold_{i}"] = h["from"]
        out[f"hold_{i}_end"] = h["to"]
    out.update({k: float(v) for k, v in ((bm.get("by_hand") or {}).get("moments") or {}).items()})
    return out


# ------------------------------------------------------------------------------------------------------------ picture
def draw(bm: dict, png, audio=None, row_sec: float = 30.0, width: int = 2400) -> Path:
    """The beat map over the waveform: a row every 30 s; beats thin, bar lines thick with their numbers, loudness in
    orange, silences red, holds green, hits as red triangles, the local tempo as a line along the bottom of each row."""
    import numpy as np
    from PIL import Image, ImageDraw
    dur = float(bm["duration"])
    rows = max(1, int(math.ceil(dur / row_sec)))
    rh = 170
    img = Image.new("RGB", (width, 40 + rows * rh), (250, 248, 244))
    d = ImageDraw.Draw(img)
    t_tempo = bm.get("tempo") or {}
    d.text((10, 8), f"{bm.get('track')}  ·  {dur:.1f} s  ·  {len(bm.get('beats') or [])} beats, {len(bm.get('bars') or [])} bars  ·  "
                    f"{t_tempo.get('median_bpm')} BPM (min {t_tempo.get('min_bpm')}, max {t_tempo.get('max_bpm')}, {t_tempo.get('method')})  ·  "
                    f"steady within {bm.get('checks', {}).get('grid_ms_median')} ms", fill=(30, 30, 30))
    env = None
    if audio is not None:
        try:
            import librosa
            y, sr = librosa.load(str(audio), sr=8000, mono=True)
            env = (y, sr)
        except Exception:  # noqa: BLE001
            env = None
    px_per_s = (width - 60) / row_sec

    def xy(t):
        r = int(t // row_sec)
        return 50 + (t - r * row_sec) * px_per_s, 40 + r * rh

    for r in range(rows):
        y0 = 40 + r * rh
        d.rectangle([50, y0 + 10, width - 10, y0 + rh - 20], outline=(200, 196, 188))
        d.text((6, y0 + 70), f"{int(r * row_sec // 60)}:{int(r * row_sec % 60):02d}", fill=(90, 90, 90))
        if env is not None:
            y, sr = env
            a, b = int(r * row_sec * sr), int(min(len(y), (r + 1) * row_sec * sr))
            seg = y[a:b]
            if len(seg):
                cols = int(min(width - 60, len(seg)))
                chunks = np.array_split(np.abs(seg), cols)
                mid = y0 + 10 + (rh - 30) / 2
                for c, ch in enumerate(chunks):
                    v = float(ch.max()) if len(ch) else 0.0
                    d.line([(50 + c, mid - v * 55), (50 + c, mid + v * 55)], fill=(190, 190, 200))
    for s in bm.get("silences") or []:
        _band(d, xy, s["from"], s["to"], row_sec, rh, (255, 205, 205))
    for s in bm.get("holds") or []:
        _band(d, xy, s["from"], s["to"], row_sec, rh, (205, 240, 205))
    for b in bm.get("beats") or []:
        x, y0 = xy(b["t"])
        if b.get("down"):
            d.line([(x, y0 + 10), (x, y0 + rh - 20)], fill=(30, 70, 200), width=2)
            if b.get("bar", 0) % 4 == 1:
                d.text((x + 2, y0 + 12), str(b["bar"]), fill=(30, 70, 200))
        else:
            d.line([(x, y0 + 30), (x, y0 + rh - 40)], fill=(130, 160, 230), width=1)
        ly = y0 + rh - 22 - b["loud"] * (rh - 40)
        d.ellipse([x - 1.5, ly - 1.5, x + 1.5, ly + 1.5], fill=(230, 130, 30))
        ty = y0 + rh - 22 - max(0.0, min(1.0, (b["bpm"] - 40) / 200.0)) * 30
        d.point((x, ty), fill=(120, 0, 120))
    for h in bm.get("hits") or []:
        x, y0 = xy(h["t"])
        d.polygon([(x - 5, y0 + 2), (x + 5, y0 + 2), (x, y0 + 11)], fill=(210, 30, 30))
    png = Path(png)
    png.parent.mkdir(parents=True, exist_ok=True)
    img.save(png)
    return png


def _band(d, xy, a, b, row_sec, rh, colour):
    t = a
    while t < b - 1e-6:
        r_end = (int(t // row_sec) + 1) * row_sec
        e = min(b, r_end - 1e-6)
        x0, y0 = xy(t)
        x1, _ = xy(e)
        d.rectangle([x0, y0 + 10, x1, y0 + rh - 20], fill=colour)
        t = r_end
