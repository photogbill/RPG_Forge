"""Reading a voice recording (BUILD 71): WAV with the standard library; OGG, FLAC or MP3 through ffmpeg when it is on
this computer (a voice tool's own folder first, then PATH). numpy only."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

from .. import config as cfgmod


def ffmpeg() -> str | None:
    for p in (cfgmod.ROOT / "tools" / "ffmpeg").rglob("ffmpeg*") if (cfgmod.ROOT / "tools" / "ffmpeg").exists() else []:
        if p.is_file() and p.stem == "ffmpeg":
            return str(p)
    return shutil.which("ffmpeg")


def to_wav(src: Path, dst: Path, rate: int = 16000) -> Path:
    """Any recording → mono 16-bit WAV at `rate` (ffmpeg); a WAV already right is copied."""
    src, dst = Path(src), Path(dst)
    ff = ffmpeg()
    if ff is None:
        if src.suffix.lower() != ".wav":
            raise RuntimeError(f"{src.name}: only WAV can be read without ffmpeg — save it as WAV, or put ffmpeg in tools/ffmpeg")
        shutil.copyfile(src, dst)
        return dst
    r = subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", str(rate), "-sample_fmt", "s16", str(dst)],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg could not read {src.name}: {r.stderr[-300:]}")
    return dst


def read(path: Path) -> tuple[np.ndarray, int]:
    """(mono float samples -1..1, sample rate)."""
    path = Path(path)
    if path.suffix.lower() != ".wav":
        with tempfile.TemporaryDirectory() as d:
            return read(to_wav(path, Path(d) / "x.wav"))
    with wave.open(str(path), "rb") as w:
        n, ch, sw, rate = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(n)
    dt = {1: np.uint8, 2: "<i2", 4: "<i4"}[sw]
    a = np.frombuffer(raw, dtype=dt).astype(np.float64)
    a = (a - 128) / 128 if sw == 1 else a / float(2 ** (8 * sw - 1))
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, rate


def write_wav(path: Path, samples: np.ndarray, rate: int = 16000) -> Path:
    a = np.clip(np.asarray(samples, dtype=np.float64), -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((a * 32767).astype("<i2").tobytes())
    return Path(path)


def envelope(samples: np.ndarray, rate: int, step: float = 0.02) -> np.ndarray:
    """The waveform as one peak a step (for the bench's drawing)."""
    k = max(1, int(rate * step))
    n = len(samples) // k
    return np.abs(samples[:n * k]).reshape(n, k).max(1) if n else np.zeros(0)
