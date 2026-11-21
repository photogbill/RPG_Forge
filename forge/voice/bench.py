"""The voice bench's work (BUILD 71): a take from a face, a line and a voice; the two timing lanes; the words check; voice
cards that only the person can lock; verdicts; clearing the takes nobody marked. Every path comes from the game's
adapter (`voice_paths()`), because nothing in forge/ names a game.

Where a voice came from is on every take and card: `song` (a cut from a song — anything under voice_cuts or stems),
`person` (a sample someone gave, with whose voice and that they agreed), `engine` (designed from words, or a stock voice).
"""
from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path

import numpy as np

from . import audio, loud, tools
from ..suite import mouthrule

MOODS = ("neutral", "warm", "hard", "hurt")
VERDICTS = ("Sounds like them", "Not them", "Words wrong", "Mouth late", "Mouth early", "Wrong shapes")
STATUSES = ("trying", "proposed", "locked")
# Rhubarb's own descriptions are the guide: how open (0..1), how wide (-1 pinched .. +1 stretched), teeth showing
STANDIN = {"A": (0.0, 0.0, False), "B": (0.25, 0.1, True), "C": (0.5, 0.15, False), "D": (0.85, 0.25, False),
           "E": (0.45, -0.25, False), "F": (0.3, -0.5, False), "G": (0.15, 0.1, True), "H": (0.45, 0.0, False), "X": (0.05, 0.0, False)}


class BenchRefused(ValueError):
    pass


def default_paths(root: Path) -> dict:
    return {"takes": root / "voice_bench" / "takes", "verdicts": root / "voice_bench" / "verdicts.jsonl",
            "cards": root / "voice" / "cards", "names": root / "voice" / "names.json", "cuts": root / "voice_cuts",
            "samples": root / "voice_samples", "stems": root / "stems", "portraits": root / "project" / "assets" / "portraits",
            "stills": root / "look_proof" / "shots"}


def origin_of(path: Path | None, paths: dict, engine: str | None = None) -> str:
    if engine and engine != "file":
        return "engine"
    p = str(Path(path).resolve()).lower() if path else ""
    for k in ("cuts", "stems"):
        if paths.get(k) and p.startswith(str(Path(paths[k]).resolve()).lower()):
            return "song"
    if paths.get("samples") and p.startswith(str(Path(paths["samples"]).resolve()).lower()):
        return "person"
    return "file"


# ------------------------------------------------------------------------------------------------ the stand-in mouth
def standin_mouths(picture, box: tuple[int, int, int, int], table: dict | None = None) -> dict:
    """One picture and a box round its mouth → a frame a shape: the lower lip and chin eased down, the gap filled dark, the
    width pinched or stretched (the table: how open, how wide, teeth). Every frame says STAND-IN on it; never saved as art."""
    from PIL import Image, ImageDraw
    t = {**STANDIN, **(table or {})}
    im = picture.convert("RGB")
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = max(4, x1 - x0), max(4, y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    out = {}
    for s, (opn, wide, teeth) in t.items():
        f = im.copy()
        if opn > 0.02:
            drop = int(h * 0.9 * opn)
            below = im.crop((x0 - w // 4, int(cy), x1 + w // 4, min(im.height, y1 + h)))
            f.paste(below, (x0 - w // 4, int(cy) + drop))
            ww = w * (1 + 0.5 * wide) / 2
            d = ImageDraw.Draw(f)
            d.ellipse([cx - ww, cy - 2, cx + ww, cy + max(3, drop)], fill=(40, 16, 18))
            if teeth:
                d.rectangle([cx - ww * 0.7, cy - 1, cx + ww * 0.7, cy + max(2, drop * 0.3)], fill=(225, 220, 210))
        d = ImageDraw.Draw(f)
        d.rectangle([0, 0, 92, 16], fill=(255, 220, 0))
        d.text((4, 2), "STAND-IN", fill=(0, 0, 0))
        out[s] = f
    return out


# ------------------------------------------------------------------------------------------------ a take
def make_take(paths: dict, line: str, sound: Path, who_for: str = "", mood: str = "neutral", engine: str = "file",
              offset: float = 0.0, blend: float = mouthrule.BLEND_SEC, names: dict | None = None, use_rhubarb: bool = True,
              use_whisper: bool = True, language: str = "en", card: dict | None = None) -> dict:
    """A take: the sound kept, the mouth by both methods (loud always; Rhubarb when installed), the words checked (when
    Whisper is installed), saved under takes/<character or loose>/<take id>/ with take.json."""
    if mood not in MOODS:
        raise BenchRefused(f"a mood is one of {', '.join(MOODS)}")
    sound = Path(sound)
    tid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    d = Path(paths["takes"]) / (who_for or "loose") / tid
    d.mkdir(parents=True, exist_ok=True)
    kept = d / ("voice" + sound.suffix.lower())
    shutil.copyfile(sound, kept)
    t0 = time.time()
    wav = audio.to_wav(kept, d / "voice16k.wav") if kept.suffix.lower() != ".wav" else kept
    samples, rate = audio.read(wav)
    lanes = {"loud": loud.cues(samples, rate)}
    (d / "loud.mouth.json").write_text(json.dumps(lanes["loud"], indent=1), encoding="utf-8")
    checks = {}
    if use_rhubarb and tools.rhubarb_exe() is not None:
        from . import lipsync
        r = lipsync.run(wav, d / "rhubarb.mouth.json", text=line, language=language)
        if r["ok"]:
            lanes["rhubarb"] = r["mouth"]
        else:
            checks["rhubarb"] = r.get("error")
    else:
        checks["rhubarb"] = "not installed"
    heard = None
    if use_whisper and tools.whisper_ready():
        from . import hear
        h = hear.run(wav, language=language)
        if h["ok"]:
            heard = {**h, **hear.compare(line, h["text"], names)}
            (d / "heard.json").write_text(json.dumps(heard, indent=1), encoding="utf-8")
        else:
            checks["whisper"] = h.get("error")
    else:
        checks["whisper"] = "not installed"
    origin = origin_of(sound, paths, engine)
    take = {"id": tid, "for": who_for or None, "line": line, "mood": mood, "engine": engine, "origin": origin, "source": str(sound),
            "sound": kept.name, "settings": {"offset": offset, "blend": blend}, "lanes": sorted(lanes),
            "duration": round(len(samples) / rate, 3), "words": None if heard is None else {"match": heard["match"], "differ": heard["differ"]},
            "checks": checks, "card": card, "verdict": [], "marked": False, "made": time.strftime("%Y-%m-%d %H:%M:%S"),
            "seconds": round(time.time() - t0, 2), "device": "cpu"}
    (d / "take.json").write_text(json.dumps(take, indent=1, ensure_ascii=False), encoding="utf-8")
    tools.log({"bench": "take", "id": tid, "for": who_for, "engine": engine, "origin": origin, "lanes": sorted(lanes),
               "seconds": take["seconds"]})
    return {**take, "folder": str(d), "lanes_data": lanes, "envelope": audio.envelope(samples, rate).round(3).tolist(),
            "heard": heard}


def lanes_for_face(take_dir: Path, available, offset: float = 0.0, blend: float = mouthrule.BLEND_SEC) -> dict:
    """What the face shows frame by frame by each method — worked out here, the page only draws it."""
    out = {}
    for p in sorted(Path(take_dir).glob("*.mouth.json")):
        tr = mouthrule.parse(json.loads(p.read_text(encoding="utf-8")))
        out[p.name.split(".")[0]] = mouthrule.lane(tr, offset=offset, blend=blend, available=available)
    return out


def takes(paths: dict) -> list[dict]:
    out = []
    for p in sorted(Path(paths["takes"]).glob("*/*/take.json"), reverse=True):
        try:
            t = json.loads(p.read_text(encoding="utf-8"))
            t["folder"] = str(p.parent)
            out.append(t)
        except (OSError, ValueError):
            continue
    return out


def verdict(paths: dict, take_dir: Path, marks: list[str], note: str, who: str) -> dict:
    if not who:
        raise BenchRefused("say who you are first")
    bad = [m for m in marks if m not in VERDICTS]
    if bad:
        raise BenchRefused(f"not a verdict: {', '.join(bad)}")
    p = Path(take_dir) / "take.json"
    t = json.loads(p.read_text(encoding="utf-8"))
    row = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "take": t["id"], "for": t.get("for"), "engine": t.get("engine"),
           "marks": marks, "note": note, "by": who, "offset": (t.get("settings") or {}).get("offset")}
    t["verdict"] = (t.get("verdict") or []) + [row]
    t["marked"] = True
    p.write_text(json.dumps(t, indent=1, ensure_ascii=False), encoding="utf-8")
    vp = Path(paths["verdicts"])
    vp.parent.mkdir(parents=True, exist_ok=True)
    with open(vp, "a", encoding="utf-8") as f:                 # append-only
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def clear_unmarked(paths: dict) -> dict:
    """Takes nobody marked are cleared (William does not want unused files piling up); marked ones stay."""
    gone, kept = 0, 0
    for t in takes(paths):
        if t.get("marked"):
            kept += 1
            continue
        shutil.rmtree(t["folder"], ignore_errors=True)
        gone += 1
    return {"cleared": gone, "kept": kept}


def learned(paths: dict) -> dict:
    """What the bench has learned: for an engine — takes, how often the words matched, how often "sounds like them";
    for a timing method — the mouth verdicts; the offsets left on marked takes."""
    rows = takes(paths)
    eng: dict = {}
    for t in rows:
        e = eng.setdefault(t.get("engine") or "file", {"takes": 0, "words_match": 0, "words_checked": 0, "sounds_like": 0, "seconds": []})
        e["takes"] += 1
        if t.get("words") is not None:
            e["words_checked"] += 1
            e["words_match"] += 1 if t["words"]["match"] else 0
        e["sounds_like"] += sum(1 for v in t.get("verdict") or [] if "Sounds like them" in v.get("marks", []))
        e["seconds"].append(t.get("seconds") or 0)
    for e in eng.values():
        e["seconds_a_line"] = round(float(np.mean(e.pop("seconds"))), 2) if e["takes"] else None
    mouth = {}
    for t in rows:
        for v in t.get("verdict") or []:
            for m in v.get("marks", []):
                if m.startswith("Mouth") or m == "Wrong shapes":
                    mouth[m] = mouth.get(m, 0) + 1
    offsets = [(t.get("settings") or {}).get("offset", 0) for t in rows if t.get("marked")]
    return {"engines": eng, "mouth_verdicts": mouth, "offsets_left": offsets,
            "offset_median": float(np.median(offsets)) if offsets else None}


# ------------------------------------------------------------------------------------------------ voice cards
def card_path(paths: dict, cid: str) -> Path:
    return Path(paths["cards"]) / f"{cid}.json"


def save_card(paths: dict, cid: str, card: dict, who: str) -> dict:
    """A voice card as `trying` or `proposed`. Locking is never done here (lock_card, the person's own click)."""
    if not who:
        raise BenchRefused("say who you are first")
    p = card_path(paths, cid)
    old = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    if old.get("status", "").startswith("locked"):
        raise BenchRefused(f"{cid}'s card is locked — only William can unlock it")
    st = card.get("status") or "trying"
    if st not in ("trying", "proposed"):
        raise BenchRefused("a card is saved as trying or proposed; locking is the person's own click")
    src = card.get("reference_origin")
    if card.get("way") == "reference" and src not in ("song", "person", "engine"):
        raise BenchRefused("a reference voice says where it came from: song, person or engine")
    out = {**old, **card, "id": cid, "status": st, "saved": time.strftime("%Y-%m-%d %H:%M"), "saved_by": who}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


def lock_card(paths: dict, cid: str, who: str, by_person: bool) -> dict:
    """Locking is William's click and writes a ruling (the suite does that). Refused for a preset voice, for a person's
    sample with no 'whose voice, and agreed', and for anything not pressed by a person."""
    if not by_person or not who:
        raise BenchRefused("only the person locks a voice card, by their own click")
    p = card_path(paths, cid)
    if not p.exists():
        raise BenchRefused(f"no card for {cid}")
    c = json.loads(p.read_text(encoding="utf-8"))
    if c.get("way") == "preset":
        raise BenchRefused("a card built on a stock voice is for timing tests — it cannot be locked")
    if c.get("reference_origin") == "person" and not (c.get("consent") or {}).get("agreed"):
        raise BenchRefused("a person's sample needs whose voice it is and that they agreed before the card can be locked")
    c["status"] = f"locked by {who} {time.strftime('%Y-%m-%d')}"
    c["locked"] = {"by": who, "at": time.strftime("%Y-%m-%d %H:%M")}
    p.write_text(json.dumps(c, indent=1, ensure_ascii=False), encoding="utf-8")
    return c


def usable_in_game(card: dict) -> tuple[bool, str]:
    """What BUILD 70 part 6 asks before it uses a card: locked; and a song-referenced card needs his second yes as well."""
    if not str(card.get("status", "")).startswith("locked"):
        return False, "the card is not locked"
    if card.get("reference_origin") == "song" and not card.get("game_yes"):
        return False, "its reference is a cut from a song — that needs William's second yes, recorded as a ruling"
    return True, ""
