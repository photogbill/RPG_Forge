"""Even loudness across every song and sound (BUILD 98 Part 13; Opus 2026-11-21).

William, 2026-11-21 02:08: "Go ahead and add all those that you identified that we should do." Songs from different
albums and Suno runs sit at different levels. This measures each file's integrated loudness (EBU R128 / LUFS), true
peak and loudness range with ffmpeg's loudnorm filter, and writes the gain that brings it to one target. The game applies
the gain at playback (`volume_db`), so no file is ever re-encoded or changed.

  python -m forge.audio.loudness measure <folder> [--target -18] [--peak -1.0] [--out <json>]
    writes <json> (default: <game project>/data/audio_loudness.json): {"target_lufs", "peak_ceiling", "files": {name:
    {"lufs", "true_peak", "lra", "gain_db", "limited_by_peak"}}}. Resumable: files already measured (same size and
    modification time) are skipped, so a long batch can be stopped and run again.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from ..log import get

log = get("audio")
EXTS = (".ogg", ".wav", ".mp3", ".flac", ".m4a")


def ffmpeg_exe() -> str:
    try:
        from .. import config as cfgmod
        p = (cfgmod.load().get("tools") or {}).get("ffmpeg")
        if p and Path(p).exists():
            return str(p)
    except Exception:  # noqa: BLE001
        pass
    return shutil.which("ffmpeg") or "ffmpeg"


def measure_one(path: Path, target: float = -18.0) -> dict:
    cmd = [ffmpeg_exe(), "-hide_banner", "-nostats", "-i", str(path), "-af",
           f"loudnorm=I={target}:TP=-1.0:LRA=11:print_format=json", "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if not m:
        raise RuntimeError(f"no loudness read for {path.name}: {r.stderr[-300:]}")
    d = json.loads(m.group(0))
    return {"lufs": float(d["input_i"]), "true_peak": float(d["input_tp"]), "lra": float(d["input_lra"])}


def gain_for(m: dict, target: float, ceiling: float) -> tuple[float, bool]:
    g = target - m["lufs"]
    if m["true_peak"] + g > ceiling:              # never push a peak over the ceiling
        return round(ceiling - m["true_peak"], 2), True
    return round(g, 2), False


def measure(folder: Path, out: Path, target: float = -18.0, ceiling: float = -1.0, budget_s: float | None = None) -> dict:
    data = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    files = data.get("files") or {}
    data.update({"target_lufs": target, "peak_ceiling": ceiling,
                 "about": "Gain (dB) a player applies so every file plays at target_lufs; written by "
                          "D:\\RPG_Forge forge.audio.loudness. Files are never changed."})
    todo = sorted(p for p in folder.rglob("*") if p.suffix.lower() in EXTS)
    t0, done = time.time(), 0
    for p in todo:
        key = p.relative_to(folder).as_posix()
        st = p.stat()
        sig = f"{st.st_size}:{int(st.st_mtime)}"
        if key in files and files[key].get("sig") == sig:
            continue
        if budget_s and time.time() - t0 > budget_s:
            break
        try:
            m = measure_one(p, target)
            g, lim = gain_for(m, target, ceiling)
            files[key] = {**m, "gain_db": g, "limited_by_peak": lim, "sig": sig}
            log.info("loudness %s: %.1f LUFS, peak %.1f, gain %+.1f dB%s", key, m["lufs"], m["true_peak"], g,
                     " (held by its peak)" if lim else "")
        except Exception as e:  # noqa: BLE001
            files[key] = {"error": str(e)[:300], "sig": sig}
            log.warning("loudness %s: %s", key, e)
        done += 1
        if done % 10 == 0:
            data["files"] = files
            out.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    data["files"] = files
    data["measured"] = len([f for f in files.values() if "lufs" in f])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    left = len([p for p in todo if p.relative_to(folder).as_posix() not in files])
    return {"measured_now": done, "total": len(todo), "left": left, "out": str(out)}


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] != "measure" or len(a) < 2:
        print(__doc__); sys.exit(2)
    folder = Path(a[1])

    def opt(k, d):
        return a[a.index(k) + 1] if k in a else d
    out = Path(opt("--out", str(folder.parents[1] / "data" / "audio_loudness.json")))
    r = measure(folder, out, float(opt("--target", -18)), float(opt("--peak", -1.0)),
                float(opt("--budget", 0)) or None)
    print(f"Measured {r['measured_now']} now; {r['left']} of {r['total']} left. Written: {r['out']}")
