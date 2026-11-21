"""Characters → Voice bench (BUILD 71): a face, a line, a voice, and whether the mouth matches — before any of it is in
the game. Four panes: Face (a portrait set, a set dropped in, or one picture with a labelled stand-in mouth), Script
(typed, or the game's real lines), Voice (a recording; an engine when one is installed), Test (two timing lanes and the
words under the waveform, the offset and blend sliders). Every path comes from the game adapter's voice_paths()."""
from __future__ import annotations

import base64
import io
import json
import threading
from pathlib import Path

from . import games
from ..log import get
from ..voice import bench, engines, tools

log = get("suite")
_jobs: dict = {}


def _adapter(cfg: dict, gid: str):
    return games.adapter(cfg, gid) if games.has_adapter(cfg, gid) else None


def paths(cfg: dict, gid: str) -> dict:
    adp = _adapter(cfg, gid)
    if adp is not None and callable(getattr(adp, "voice_paths", None)):
        return {k: Path(v) for k, v in adp.voice_paths().items()}
    root = games.game_root(cfg, gid)
    return bench.default_paths(Path(root)) if root else {}


def _b64(img) -> str:
    b = io.BytesIO()
    img.save(b, "PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode("ascii")


def view(cfg: dict, gid: str) -> dict:
    p = paths(cfg, gid)
    if not p:
        return {"error": f"{gid} has no game folder this computer can see"}
    adp = _adapter(cfg, gid)
    people = []
    if adp is not None:
        try:
            for pe in adp.people():
                d = pe.__dict__ if hasattr(pe, "__dict__") else dict(pe)
                v = adp.profile_voice(d.get("id")) if callable(getattr(adp, "profile_voice", None)) else None
                people.append({"id": d.get("id"), "name": d.get("name") or d.get("id"), "voice": v})
        except Exception as e:  # noqa: BLE001
            log.warning("voice bench: the cast could not be read: %s", e)
    cuts = sorted(str(x.relative_to(p["cuts"])) for x in p["cuts"].rglob("*") if x.suffix.lower() in (".wav", ".ogg", ".mp3", ".flac")) if p["cuts"].exists() else []
    samples = sorted(str(x.relative_to(p["samples"])) for x in p["samples"].rglob("*") if x.suffix.lower() in (".wav", ".ogg", ".mp3", ".flac")) if p["samples"].exists() else []
    portraits = sorted(x.name for x in p["portraits"].iterdir() if x.is_dir()) if p["portraits"].exists() else []
    stills = sorted(x.name for x in p["stills"].glob("*.png"))[:40] if p["stills"].exists() else []
    cards = [json.loads(c.read_text(encoding="utf-8")) for c in sorted(p["cards"].glob("*.json"))] if p["cards"].exists() else []
    free, why = tools.card_free(cfg)
    return {"tools": {"rhubarb": tools.need(cfg, "rhubarb"), "whisper": tools.need(cfg, "whisper"),
                      "voice_engine": tools.need(cfg, "voice_engine")},
            "engines": engines.all_engines(), "people": people, "cuts": cuts, "samples": samples, "portraits": portraits,
            "stills": stills, "cards": cards, "takes": bench.takes(p)[:40], "moods": list(bench.MOODS),
            "verdicts": list(bench.VERDICTS), "shapes": {k: v for k, v in __import__("forge.suite.mouthrule", fromlist=["x"]).DESCRIBE.items()},
            "standin_table": bench.STANDIN, "card": {"free": free, "why": why}, "learned": bench.learned(p),
            "song_rule": "A voice whose reference is a cut from a song is for the bench; putting it in the game is a second yes "
                         "from William, recorded as a ruling. Song audio goes only into engines that run on this computer.",
            "paths": {k: str(v) for k, v in p.items()}}


def act(cfg: dict, gid: str, action: str, body: dict, who: str | None) -> dict:
    p = paths(cfg, gid)
    try:
        if action == "voice_standin":
            from PIL import Image
            src = body.get("picture") or ""
            img = Image.open(io.BytesIO(base64.b64decode(src.split(",", 1)[-1]))) if src.startswith("data:") else Image.open(src)
            frames = bench.standin_mouths(img, tuple(body["box"]), body.get("table"))
            return {"ok": True, "frames": {k: _b64(v) for k, v in frames.items()}}
        if action == "voice_take":
            src = body.get("sound") or ""
            if src.startswith("data:"):
                tmp = tools.home() / f"upload_{abs(hash(src)) % 10**8}{body.get('ext') or '.wav'}"
                tmp.write_bytes(base64.b64decode(src.split(",", 1)[-1]))
                sound = tmp
            elif body.get("from") == "cuts":
                sound = p["cuts"] / src
            elif body.get("from") == "samples":
                sound = p["samples"] / src
            else:
                sound = Path(src)
            if body.get("engine") and body["engine"] != "file":
                e = engines.get(body["engine"])
                if e.INFO.get("online"):
                    return {"ok": False, "message": "an online engine is never handed a file"}
                free, why = tools.card_free(cfg)
                dev = "cuda" if free and e.INFO.get("card") in ("wants", "can") and body.get("use_card") else "cpu"
                out = tools.home() / f"speak_{abs(hash(body.get('line'))) % 10**8}.wav"
                r = e.speak(body.get("line") or "", body.get("voice") or {}, out, int(body.get("seed") or 1), dev)
                if not r.get("ok"):
                    return {"ok": False, "message": r.get("error") or "the engine made nothing"}
                sound = out
            names = json.loads(p["names"].read_text(encoding="utf-8")) if p["names"].exists() else {}
            t = bench.make_take(p, body.get("line") or "", sound, body.get("for") or "", body.get("mood") or "neutral",
                                body.get("engine") or "file", float(body.get("offset") or 0), float(body.get("blend") or 0.06),
                                names=names, language=body.get("language") or "en", card=body.get("card"))
            t["face_lanes"] = bench.lanes_for_face(Path(t["folder"]), body.get("available") or list("ABCDEFGHX"),
                                                    float(body.get("offset") or 0), float(body.get("blend") or 0.06))
            t.pop("lanes_data", None)
            return {"ok": True, "take": t}
        if action == "voice_lanes":
            return {"ok": True, "lanes": bench.lanes_for_face(Path(body["folder"]), body.get("available") or list("ABCDEFGHX"),
                                                              float(body.get("offset") or 0), float(body.get("blend") or 0.06))}
        if action == "voice_verdict":
            return {"ok": True, "row": bench.verdict(p, Path(body["folder"]), list(body.get("marks") or []), body.get("note") or "", who or "")}
        if action == "voice_clear":
            if not who:
                return {"ok": False, "message": "say who you are first"}
            r = bench.clear_unmarked(p)
            return {"ok": True, "message": f"{r['cleared']} unmarked take(s) cleared; {r['kept']} marked kept", **r}
        if action == "voice_card_save":
            c = bench.save_card(p, str(body["id"]), dict(body.get("card") or {}), who or "")
            return {"ok": True, "card": c, "message": f"{c['id']}'s card saved ({c['status']})"}
        if action == "voice_card_lock":
            c = bench.lock_card(p, str(body["id"]), who or "", by_person=bool(body.get("by_person")))
            try:
                from . import rulings
                rulings.record(games.game_root(cfg, gid), who or "", f"Voice card locked: {c['id']} — {c.get('engine')} / {c.get('way')}"
                               + (f" (reference: {c.get('reference_origin')})" if c.get("reference_origin") else ""),
                               by=who or "", source="Characters → Voice bench (the lock is the person's own click)")
            except Exception as e:  # noqa: BLE001
                log.warning("voice bench: the lock's ruling was not written: %s", e)
            return {"ok": True, "card": c, "message": f"{c['id']}'s card is locked"}
        if action == "voice_get":
            if not who:
                return {"ok": False, "message": "say who you are first"}
            what = body.get("what")
            f = {"rhubarb": tools.get_rhubarb, "whisper": tools.get_whisper}.get(what)
            if f is None:
                return {"ok": False, "message": "rhubarb or whisper"}
            if what in _jobs and _jobs[what].get("running"):
                return {"ok": False, "message": f"{what} is being fetched already"}
            _jobs[what] = {"running": True}

            def run():
                try:
                    _jobs[what] = {"running": False, **f(cfg)}
                except Exception as e:  # noqa: BLE001
                    _jobs[what] = {"running": False, "ok": False, "message": f"{type(e).__name__}: {e}"}
            threading.Thread(target=run, daemon=True).start()
            return {"ok": True, "message": f"Fetching {what} into its own folder — the page shows when it is there."}
    except bench.BenchRefused as e:
        return {"ok": False, "message": str(e)}
    except (OSError, KeyError, ValueError) as e:
        return {"ok": False, "message": f"{type(e).__name__}: {e}"}
    return {"ok": False, "message": f"unknown action {action}"}


def safe_take_file(cfg: dict, gid: str, rel: str) -> Path:
    """A file inside the takes folder (the page plays a take's sound); anything else is refused."""
    base = Path(paths(cfg, gid)["takes"]).resolve()
    f = Path(rel).resolve()
    if base not in f.parents or not f.is_file() or f.suffix.lower() not in (".wav", ".ogg", ".mp3", ".flac", ".json"):
        raise FileNotFoundError(rel)
    return f
