"""The voice bench's job types (BUILD 71): `lipsync` (Rhubarb, CPU), `hear` (Whisper large-v3, CPU unless the card is
free), `speak` (a voice engine; then hear and lipsync by themselves). A plug-in, so a running worker learns them without a
restart."""
from __future__ import annotations

import json
from pathlib import Path


def lipsync(job: dict, ctx, out_dir) -> dict:
    from ..voice import lipsync as ls
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    snd = Path(job["sound"])
    dst = Path(job.get("out") or out / (snd.stem + ".mouth.json"))
    r = ls.run(snd, dst, text=job.get("text") or "", language=job.get("language") or "en")
    if not r["ok"]:
        raise RuntimeError(r["error"])
    return {"outputs": [str(dst)], "seconds": r["seconds"]}


def hear(job: dict, ctx, out_dir) -> dict:
    from ..voice import hear as hr
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    r = hr.run(Path(job["sound"]), language=job.get("language") or "en", device=job.get("device") or "cpu")
    if not r["ok"]:
        raise RuntimeError(r["error"])
    if job.get("script"):
        r.update(hr.compare(job["script"], r["text"], job.get("names")))
    (out / "heard.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
    return {"outputs": ["heard.json"], "match": r.get("match"), "seconds": r["seconds"]}


def speak(job: dict, ctx, out_dir) -> dict:
    from ..voice import engines
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    e = engines.get(job["engine"])
    if e.INFO.get("online"):
        raise RuntimeError("an online engine is never handed a file")
    wav = out / "voice.wav"
    r = e.speak(job["text"], job.get("voice") or {}, wav, int(job.get("seed") or 1), job.get("device") or "cpu")
    if not r.get("ok"):
        raise RuntimeError(r.get("error") or "the engine made nothing")
    return {"outputs": ["voice.wav"], "seconds": r.get("seconds")}


JOB_TYPES = {
    "lipsync": {"needs": "cpu", "doc": "BUILD 71: a recording (and its line) → <name>.mouth.json by Rhubarb Lip Sync.",
                "required": ["sound"], "optional": {"text": "", "language": "en", "out": None}},
    "hear": {"needs": "cpu", "doc": "BUILD 71: a recording → the words Whisper large-v3 hears, a time on each; with a script, "
                                    "the words that differ.", "required": ["sound"],
             "optional": {"script": "", "language": "en", "device": "cpu", "names": None}},
    "speak": {"needs": "cpu", "doc": "BUILD 71: a line in a voice from a voice engine (its own environment).",
              "required": ["engine", "text"], "optional": {"voice": None, "seed": 1, "device": "cpu"}},
}
HANDLERS = {"lipsync": lipsync, "hear": hear, "speak": speak}
