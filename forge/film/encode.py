"""Rendered frames and their song into a file to watch or upload (ffmpeg), and a film's numbers joined in order.

    frames_to_film(frames_dir, out, audio=None, fps=24, audio_from=0.0, audio_to=None, mode="preview", muffled=False)
    join(parts, out, mode="final")                       numbers in order, one file (each part already has its sound)
    command(...) -> list                                 the ffmpeg command, for a test or a person to read

Two modes. `preview`: H.264 at CRF 23, preset veryfast, 1080p or what the frames are - quick to make and to look at.
`final`: H.264 High at CRF 16, preset slow, yuv420p, AAC 320k, +faststart - YouTube's recommended upload (William's
standard for this film is "the very picture of refinement"; slow is the price of that and only the final pays it).
`muffled` puts the sound through a low-pass and a little room, as a song heard through a closet door.
Nothing here names a game.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

MODES = {
    "preview": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"],
    "final": ["-c:v", "libx264", "-profile:v", "high", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
              "-movflags", "+faststart"],
}
AUDIO = {"preview": ["-c:a", "aac", "-b:a", "192k"], "final": ["-c:a", "aac", "-b:a", "320k", "-ar", "48000"]}
MUFFLE = "lowpass=f=650,highpass=f=90,aecho=0.8:0.7:22:0.25,volume=0.85"


def ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def _pattern(frames_dir: Path) -> tuple[str, int]:
    """The frames' file pattern and the first frame's number (Blender writes 0001.png …, or name_0001.png)."""
    pngs = sorted(Path(frames_dir).glob("*.png"))
    if not pngs:
        raise FileNotFoundError(f"no frames in {frames_dir}")
    stem = pngs[0].stem
    digits = len(stem) - len(stem.rstrip("0123456789"))
    if digits == 0:
        raise ValueError(f"the frames in {frames_dir} are not numbered ({pngs[0].name})")
    prefix = stem[:-digits]
    return str(Path(frames_dir) / f"{prefix}%0{digits}d.png"), int(stem[-digits:])


def command(frames_dir, out, audio=None, fps: int = 24, audio_from: float = 0.0, audio_to: float | None = None,
            mode: str = "preview", muffled: bool = False) -> list[str]:
    if mode not in MODES:
        raise ValueError(f"mode is preview or final, not '{mode}'")
    pat, first = _pattern(Path(frames_dir))
    cmd = [ffmpeg() or "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-framerate", str(fps),
           "-start_number", str(first), "-i", pat]
    if audio:
        cmd += ["-ss", f"{float(audio_from):.3f}"]
        if audio_to is not None:
            cmd += ["-to", f"{float(audio_to):.3f}"]
        cmd += ["-i", str(audio)]
    cmd += MODES[mode]
    if audio:
        if muffled:
            cmd += ["-af", MUFFLE]
        cmd += AUDIO[mode] + ["-map", "0:v:0", "-map", "1:a:0", "-shortest"]
    cmd += [str(out)]
    return cmd


def frames_to_film(frames_dir, out, audio=None, fps: int = 24, audio_from: float = 0.0, audio_to: float | None = None,
                   mode: str = "preview", muffled: bool = False) -> dict:
    if not ffmpeg():
        return {"ok": False, "error": "ffmpeg was not found (the forge's install puts it on the PATH; or install it)"}
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = command(frames_dir, out, audio, fps, audio_from, audio_to, mode, muffled)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        return {"ok": False, "error": (r.stderr or "")[-800:], "cmd": cmd}
    return {"ok": True, "out": str(out), "bytes": out.stat().st_size, "cmd": cmd}


def join(parts: list, out, mode: str = "final") -> dict:
    """Join numbers already encoded (same size and rate) into one film, re-encoding once so the joins are clean."""
    if not ffmpeg():
        return {"ok": False, "error": "ffmpeg was not found"}
    parts = [Path(p) for p in parts]
    missing = [str(p) for p in parts if not p.exists()]
    if missing:
        return {"ok": False, "error": "not made yet: " + ", ".join(missing)}
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    lst = out.with_suffix(".parts.txt")
    lst.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts), encoding="utf-8")
    cmd = [ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst)]
    cmd += MODES[mode] + AUDIO[mode] + [str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        return {"ok": False, "error": (r.stderr or "")[-800:], "cmd": cmd}
    return {"ok": True, "out": str(out), "bytes": out.stat().st_size, "parts": len(parts)}


def click_track(bm: dict, out, t_from: float = 0.0, t_to: float | None = None, sr: int = 48000) -> Path:
    """A click on every beat (a higher one on each bar line) from t_from to t_to, as a WAV starting at t_from: a silent
    preview's metronome, so the movement can be judged against the beat without the song."""
    import wave
    import numpy as np
    t_to = float(t_to if t_to is not None else bm.get("duration", 10.0))
    n = int((t_to - t_from) * sr) + 1
    y = np.zeros(n, dtype=np.float32)
    k = np.arange(int(0.03 * sr))
    env = np.exp(-k / (0.006 * sr))
    for b in bm.get("beats") or []:
        t = float(b["t"])
        if t < t_from or t > t_to:
            continue
        f = 1760.0 if b.get("down") else 1100.0
        i = int((t - t_from) * sr)
        seg = (0.6 if b.get("down") else 0.35) * env * np.sin(2 * np.pi * f * k / sr)
        y[i:i + len(seg)] += seg[: max(0, n - i)]
    pcm = (np.clip(y, -1, 1) * 32767).astype("<i2")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return out
