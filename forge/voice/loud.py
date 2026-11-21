"""The mouth from the sound — the oldest way (BUILD 71 part 2, lane `loud`): the voice's loudness, smoothed, opens the
mouth. Thresholds to shapes A (closed), B, C, D (wide); quiet is X (at rest). Pure numpy; nothing to install, so it works
on any computer on the first day. Writes the same file Rhubarb writes, so the game reads either."""
from __future__ import annotations

import numpy as np

STEPS = [(0.06, "X"), (0.16, "A"), (0.34, "B"), (0.6, "C"), (9.9, "D")]   # loudness (share of the line's loud end) → shape


def cues(samples: np.ndarray, rate: int, frame: float = 0.04, smooth: int = 2, min_len: float = 0.06) -> dict:
    k = max(1, int(rate * frame))
    n = len(samples) // k
    if n == 0:
        return {"metadata": {"duration": 0.0, "method": "loud"}, "mouthCues": []}
    rms = np.sqrt((samples[:n * k].reshape(n, k) ** 2).mean(1))
    if smooth > 0:
        ker = np.ones(2 * smooth + 1) / (2 * smooth + 1)
        rms = np.convolve(np.pad(rms, smooth, mode="edge"), ker, mode="valid")
    top = float(np.percentile(rms, 95)) or 1e-9
    level = rms / top
    shapes = [next(s for th, s in STEPS if v < th) for v in level]
    out, start = [], 0
    for i in range(1, n + 1):
        if i == n or shapes[i] != shapes[start]:
            out.append({"start": round(start * frame, 3), "end": round(i * frame, 3), "value": shapes[start]})
            start = i
    merged = []
    for c in out:                                   # nothing shorter than min_len flickers: it joins the one before
        if merged and (c["end"] - c["start"]) < min_len:
            merged[-1]["end"] = c["end"]
        else:
            merged.append(c)
    return {"metadata": {"duration": round(n * frame, 3), "method": "loud"}, "mouthCues": merged}
