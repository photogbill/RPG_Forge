"""`python -m forge voice …` — the voice bench's tools (BUILD 71). The screen is Characters → Voice bench.

    voice status                      what is installed (Rhubarb, Whisper, the engines) and what each licence says
    voice get rhubarb [--dry-run]     fetch the pinned Rhubarb release into tools/rhubarb (MIT), sum recorded and checked
    voice get whisper [--dry-run]     faster-whisper + large-v3 into engines/voice/whisper, its own environment (MIT)
    voice lipsync <sound> [--text "..."] [--language en] [--out x.mouth.json]
    voice loud <sound> [--out x.mouth.json]       the mouth from loudness alone (nothing to install)
    voice hear <sound> [--script "..."]           what Whisper hears, and the words that differ
Nothing is written outside the forge's folder; the graphics card is asked for, never taken.
"""
from __future__ import annotations

import json
from pathlib import Path


def _opt(args, f, d=None):
    return args[args.index(f) + 1] if f in args and args.index(f) + 1 < len(args) else d


def cmd_voice(cfg: dict, args: list[str]) -> int:
    from .voice import engines, tools
    sub = args[0] if args else "status"
    if sub == "status":
        print(json.dumps({"rhubarb": tools.need(cfg, "rhubarb"), "whisper": tools.need(cfg, "whisper"),
                          "engines": [{k: e[k] for k in ("id", "name", "installed", "licence_ok", "licence_why", "card", "can")}
                                      for e in engines.all_engines()]}, indent=1, ensure_ascii=False))
        return 0
    if sub == "get" and len(args) > 1:
        f = {"rhubarb": tools.get_rhubarb, "whisper": tools.get_whisper}.get(args[1])
        if f is None:
            print("voice get rhubarb | whisper")
            return 2
        r = f(cfg, dry_run="--dry-run" in args)
        print(r["message"])
        return 0 if r["ok"] else 1
    if sub in ("lipsync", "loud", "hear") and len(args) > 1:
        snd = Path(args[1])
        if sub == "loud":
            from .voice import audio, loud
            s, rate = audio.read(snd)
            d = loud.cues(s, rate)
        elif sub == "lipsync":
            from .voice import lipsync
            out = Path(_opt(args, "--out", str(snd.with_suffix(".mouth.json"))))
            r = lipsync.run(snd, out, _opt(args, "--text", ""), _opt(args, "--language", "en"))
            print(r.get("error") or f"{out} ({r['seconds']} s)")
            return 0 if r["ok"] else 1
        else:
            from .voice import hear
            r = hear.run(snd)
            if r["ok"] and _opt(args, "--script"):
                r.update(hear.compare(_opt(args, "--script"), r["text"]))
            print(json.dumps(r, indent=1, ensure_ascii=False))
            return 0 if r["ok"] else 1
        out = Path(_opt(args, "--out", str(snd.with_suffix(".mouth.json"))))
        out.write_text(json.dumps(d, indent=1), encoding="utf-8")
        print(f"{out}: {len(d['mouthCues'])} shapes")
        return 0
    print(__doc__)
    return 2


COMMANDS = {"voice": cmd_voice}
