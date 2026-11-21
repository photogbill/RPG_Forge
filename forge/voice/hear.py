"""The words check (BUILD 71 part 3 — William's method): a recording → what Whisper large-v3 hears, with a time on every
word, run in its own environment (engines/voice/whisper). The script and the transcript are reduced the same way (case,
punctuation, the names list) and compared word by word: the words match, or the ones that differ are named."""
from __future__ import annotations

import difflib
import json
import re
import subprocess
import time
from pathlib import Path

from . import tools

RUNNER = r'''
import json, sys
from faster_whisper import WhisperModel
model_dir, sound, device, lang = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
m = WhisperModel(model_dir, device=device, compute_type="float16" if device == "cuda" else "int8")
segs, info = m.transcribe(sound, word_timestamps=True, language=None if lang == "auto" else lang)
words = [{"w": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3), "p": round(w.probability, 3)}
         for s in segs for w in (s.words or [])]
print("HEARD " + json.dumps({"language": info.language, "words": words}))
'''


def norm(text: str, names: dict | None = None) -> list[str]:
    """Lower case, no punctuation, every name the names list knows written its one way."""
    t = text.lower()
    for name, spellings in (names or {}).items():
        for s in [name] + list(spellings.get("heard_as", []) if isinstance(spellings, dict) else spellings):
            t = re.sub(rf"\b{re.escape(str(s).lower())}\b", name.lower(), t)
    return re.findall(r"[a-z0-9']+", t.replace("’", "'"))


def compare(script: str, heard: str, names: dict | None = None) -> dict:
    a, b = norm(script, names), norm(heard, names)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    diffs = [{"said": " ".join(a[i1:i2]), "heard": " ".join(b[j1:j2]), "op": op}
             for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal"]
    return {"match": not diffs, "differ": diffs, "ratio": round(sm.ratio(), 3)}


def run(sound: Path, language: str = "en", device: str = "cpu", minutes: float = 15) -> dict:
    py = tools.whisper_python()
    if py is None or not tools.whisper_ready():
        return {"ok": False, "error": "Whisper is not installed — get_whisper.bat (or Settings → This computer → Voice tools)"}
    model = tools.whisper_home() / "models" / "large-v3"
    script = tools.home() / "whisper_runner.py"
    script.write_text(RUNNER, encoding="utf-8")
    t0 = time.time()
    r = subprocess.run([str(py), str(script), str(model), str(sound), device, language], capture_output=True, text=True,
                       timeout=int(minutes * 60), env=tools.tool_env())
    secs = round(time.time() - t0, 1)
    line = next((ln for ln in r.stdout.splitlines() if ln.startswith("HEARD ")), "")
    tools.log({"tool": "whisper", "sound": Path(sound).name, "device": device, "seconds": secs, "exit": r.returncode})
    if not line:
        return {"ok": False, "error": (r.stderr or r.stdout)[-400:], "seconds": secs}
    d = json.loads(line[6:])
    return {"ok": True, "words": d["words"], "text": " ".join(w["w"] for w in d["words"]), "language": d["language"],
            "seconds": secs, "device": device}
