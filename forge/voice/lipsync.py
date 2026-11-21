"""The forge's `lipsync` job (BUILD 61 part 1, built in BUILD 71): a recording, with its line's text as Rhubarb's dialog
file (which makes it more accurate), → `<name>.mouth.json` exactly as the game's MouthModel reads it. English uses
Rhubarb's default recogniser; anything else (the Opera's Italian) `phonetic`. CPU only."""
from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path

from . import audio, tools


def run(sound: Path, out_json: Path, text: str = "", language: str = "en", exe: Path | None = None, minutes: float = 10) -> dict:
    exe = exe or tools.rhubarb_exe()
    if exe is None:
        return {"ok": False, "error": "Rhubarb is not installed — get_rhubarb.bat (or Settings → This computer → Voice tools)"}
    sound, out_json = Path(sound), Path(out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with tempfile.TemporaryDirectory(dir=str(tools.home())) as d:
        src = sound if sound.suffix.lower() in (".wav", ".ogg") else audio.to_wav(sound, Path(d) / "in.wav")
        args = [str(exe), "-f", "json", "-o", str(out_json), "--extendedShapes", "GHX", "--machineReadable"]
        if text.strip():
            dlg = Path(d) / "dialog.txt"
            dlg.write_text(text, encoding="utf-8")
            args += ["-d", str(dlg)]
        if language != "en":
            args += ["-r", "phonetic"]
        args.append(str(src))
        r = subprocess.run(args, capture_output=True, text=True, timeout=int(minutes * 60), env=tools.tool_env())
    secs = round(time.time() - t0, 1)
    tools.log({"tool": "rhubarb", "sound": sound.name, "text": bool(text), "language": language, "seconds": secs, "exit": r.returncode})
    if r.returncode != 0 or not out_json.exists():
        return {"ok": False, "error": (r.stderr or r.stdout)[-400:], "seconds": secs}
    data = json.loads(out_json.read_text(encoding="utf-8"))
    data.setdefault("metadata", {})["method"] = "rhubarb"
    out_json.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return {"ok": True, "mouth": data, "seconds": secs, "device": "cpu"}
