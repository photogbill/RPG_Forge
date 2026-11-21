"""A pretend engine (for the tests, and to try the bench with no engine at all): it writes a tone that rises and falls
with the syllables of the line. No model, no download, nothing to install."""
from __future__ import annotations

import re
import time
from pathlib import Path

import numpy as np

from .. import audio

INFO = {"name": "Pretend (a tone)", "version": "1", "licence": {"code": "MIT", "weights": "MIT", "bundles": "MIT"},
        "languages": ["any"], "card": "no", "can": ["preset", "seed"], "online": False, "watermark": None,
        "install": "nothing — it is part of the forge"}


def installed() -> bool:
    return True


def speak(text: str, voice: dict, out_wav: Path, seed: int = 1, device: str = "cpu") -> dict:
    t0 = time.time()
    syl = max(1, len(re.findall(r"[aeiouy]+", text.lower())))
    rate, per = 16000, 0.18
    rng = np.random.default_rng(seed)
    t = np.arange(int(rate * per * syl + rate * 0.25)) / rate
    env = np.zeros_like(t)
    timing = []
    for k in range(syl):
        a, b = 0.12 + k * per, 0.12 + k * per + per * 0.7
        m = (t >= a) & (t < b)
        env[m] = np.sin(np.pi * (t[m] - a) / (b - a)) * (0.6 + 0.4 * rng.random())
        timing.append({"start": round(a, 3), "end": round(b, 3)})
    audio.write_wav(out_wav, 0.5 * env * np.sin(2 * np.pi * 180 * t), rate)
    return {"ok": True, "seconds": round(time.time() - t0, 2), "device": "cpu", "timing": timing}
