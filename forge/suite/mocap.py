"""Motion capture — what has to be filmed, so nothing is forgotten (William, 2026-11-15 21:28: "We should put a separate
tab in forge for motion capture requirements so we don't forget.").

**The list** is one forge-side file, `games/<game>/mocap_takes.json`, so a session can add a take even when the game's
folder isn't reachable from where it runs. A take says **who** is being captured (the character) and **who performs**
it, **where** it is used (the scene, the song), **what to perform** in plain words, the **marks** (where to stand, turn,
stop — by beat or second once the song is mapped), how long, how urgent, and where it has got to:

    needed → planned → filmed → processed → in_game

`filmed` wants the footage's path (it stays on the owner's computer — nothing here uploads anything); `processed` means
the forge has turned it into motion on the character's skeleton (a later build: video → skeleton → rig).

**The guide** (the "How to film" tab) is the camera setup that makes footage the motion tools can read, written for the
camera the owner has; it lives here so it is in front of whoever films, not in a chat.

Take: {id, title, who, performer, partner?, where, song?, perform, marks?, length_sec?, priority: now|soon|someday,
       status, footage?, notes?, by, added, history: [{at, by, what}]}
"""
from __future__ import annotations
import json, os, re
from datetime import datetime
from pathlib import Path

from ..log import get
from . import games, settings

log = get("suite")

STATUSES = ("needed", "planned", "filmed", "processed", "in_game")
PRIORITIES = ("now", "soon", "someday")
EDITABLE = ("status", "notes", "footage", "priority", "performer", "partner", "marks", "perform", "length_sec")


class MocapRefused(ValueError):
    """The rule said no; nothing was written."""


def path(cfg: dict, gid: str) -> Path:
    return games.games_dir(cfg) / gid / "mocap_takes.json"


def load(cfg: dict, gid: str) -> list[dict]:
    p = path(cfg, gid)
    try:
        d = json.loads(p.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as e:
        log.warning("mocap: %s unreadable (%s) — treated as empty", p, e)
        return []
    rows = d.get("takes") if isinstance(d, dict) else d
    return [r for r in (rows or []) if isinstance(r, dict) and r.get("id")]


def _about(cfg: dict, gid: str) -> str:
    try:
        d = json.loads(path(cfg, gid).read_text(encoding="utf-8-sig"))
        return str(d.get("_about") or "") if isinstance(d, dict) else ""
    except (OSError, ValueError):
        return ""


def _save(cfg: dict, gid: str, rows: list[dict]) -> None:
    p = path(cfg, gid)
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = {"_about": _about(cfg, gid) or "Motion capture: what has to be filmed (Motion capture tab in the forge).", "takes": rows}
    tmp = p.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, p)                                   # never half-written


def _now() -> str:
    t = settings.now() if hasattr(settings, "now") else datetime.now()
    return t.strftime("%Y-%m-%dT%H:%M:%S")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:60] or "take"


def add(cfg: dict, gid: str, *, by: str, title: str, who: str, perform: str, where: str = "", performer: str = "",
        partner: str = "", song: str = "", marks: str = "", length_sec: float | None = None, priority: str = "soon",
        notes: str = "") -> dict:
    if not by:
        raise MocapRefused("say who you are first — every take is signed")
    title, who, perform = title.strip(), who.strip(), perform.strip()
    if not title or not who or not perform:
        raise MocapRefused("a take needs a title, the character it is for, and what to perform")
    if priority not in PRIORITIES:
        raise MocapRefused(f"priority is one of {', '.join(PRIORITIES)}")
    rows = load(cfg, gid)
    ids = {r["id"] for r in rows}
    tid, n = _slug(title), 2
    base = tid
    while tid in ids:
        tid, n = f"{base}_{n}", n + 1
    row = {"id": tid, "title": title, "who": who, "performer": performer.strip(), "partner": partner.strip(),
           "where": where.strip(), "song": song.strip(), "perform": perform, "marks": marks.strip(),
           "length_sec": length_sec, "priority": priority, "status": "needed", "footage": "", "notes": notes.strip(),
           "by": by, "added": _now(), "history": [{"at": _now(), "by": by, "what": "added"}]}
    rows.append(row)
    _save(cfg, gid, rows)
    log.info("mocap: %s added %s (%s)", by, tid, gid)
    return row


def set_field(cfg: dict, gid: str, tid: str, field: str, value, by: str) -> dict:
    if not by:
        raise MocapRefused("say who you are first — every change is signed")
    if field not in EDITABLE:
        raise MocapRefused(f"{field} can't be changed here")
    rows = load(cfg, gid)
    row = next((r for r in rows if r["id"] == tid), None)
    if row is None:
        raise FileNotFoundError(tid)
    if field == "status":
        value = str(value)
        if value not in STATUSES:
            raise MocapRefused(f"status is one of {', '.join(STATUSES)}")
        if value in ("filmed", "processed", "in_game") and not (row.get("footage") or "").strip():
            raise MocapRefused("say where the footage is first (the Footage box) — then it can be marked filmed")
    if field == "priority" and value not in PRIORITIES:
        raise MocapRefused(f"priority is one of {', '.join(PRIORITIES)}")
    if field == "length_sec":
        value = float(value) if value not in (None, "") else None
    old = row.get(field)
    row[field] = value.strip() if isinstance(value, str) else value
    row.setdefault("history", []).append({"at": _now(), "by": by, "what": f"{field}: {old!r} → {row[field]!r}"[:200]})
    _save(cfg, gid, rows)
    log.info("mocap: %s set %s.%s (%s)", by, tid, field, gid)
    return row


GUIDE = [
    {"title": "The camera", "lines": [
        "Any camera works; a full-frame camera like the Canon EOS R5 is better than a phone — less noise, a sharper picture, real control.",
        "Lens: about 35 mm (24–50 mm is fine). Wider than 24 mm bends the body at the frame's edges; longer than 50 mm needs a big room.",
        "Distance: with 35 mm, about 3.5–4 m from the performer — head to toe in frame with room above the raised arms and below the feet.",
        "Height: the lens at about hip-to-chest height (1.0–1.2 m), level — not tilted down.",
        "On a tripod, locked: no panning, no zoom during a take. Image stabilisation off on the tripod.",
    ]},
    {"title": "Settings", "lines": [
        "4K, 50 or 60 frames a second (60 if the camera offers it with sound). Keep the frame rate the same for every take.",
        "Shutter 1/250 s or faster, so a moving hand is sharp, not a smear — the motion tools read sharp frames far better.",
        "Aperture f/5.6–f/8 so she stays in focus as she moves forward and back; focus locked on her (or face/eye tracking).",
        "Exposure, white balance and focus locked for the take. A normal picture style — not a flat log profile.",
        "Record sound on the camera (for the clap and the song) — nothing more is needed from it.",
        "On a Canon EOS R5: 4K at 59.94p (not 8K or 4K HQ — they heat the camera and fill the cards, and the motion tools gain nothing); "
        "IS off on the tripod; focus manually on her middle mark at f/8 (with 35 mm at about 3.7 m that keeps about 2.2 m to 13 m sharp), "
        "or Servo AF with eye detection if she moves a long way forward and back.",
    ]},
    {"title": "The room and the clothes", "lines": [
        "A plain wall behind, nothing moving in the background, no mirrors in frame. Even light from the front and sides.",
        "Fitted clothes in a colour that stands out from the wall — not a gown or a long skirt (the tracker loses the legs); the gown is put back on in 3D.",
        "Bare feet or flat shoes. Hair tied back if it would hide the face or shoulders.",
        "Tape marks on the floor where the take's marks say to stand, turn and stop.",
    ]},
    {"title": "Each take", "lines": [
        "Start: two seconds standing still, arms a little out from the sides, facing the camera.",
        "One clap, in frame, before the music — it lines the take up with the song.",
        "Play the actual song out loud and perform to it; mouthing the words helps later for the singing face.",
        "Do two or three takes of each; say the take's name to the camera at the start.",
        "Nothing dangerous: no flips, no throws, no jumps from height. Superhuman moves are made in 3D, not performed.",
    ]},
    {"title": "A second camera (a bonus)", "lines": [
        "A phone on a second tripod at a right angle to the main camera, same height, both started before the clap.",
        "A phone close on the face (for the singing face) — later, and only if wanted.",
    ]},
    {"title": "After", "lines": [
        "Copy the files into the game's mocap folder on this computer (nothing is uploaded), and put the path in the take's Footage box; mark it filmed.",
    ]},
]


def view(cfg: dict, gid: str) -> dict:
    rows = load(cfg, gid)
    order = {s: i for i, s in enumerate(STATUSES)}
    pri = {p: i for i, p in enumerate(PRIORITIES)}
    rows.sort(key=lambda r: (order.get(r.get("status"), 0) >= order["filmed"], pri.get(r.get("priority"), 1), r.get("added", "")))
    counts = {s: sum(1 for r in rows if r.get("status") == s) for s in STATUSES}
    return {"takes": rows, "counts": counts, "statuses": list(STATUSES), "priorities": list(PRIORITIES),
            "guide": GUIDE, "file": str(path(cfg, gid)), "about": _about(cfg, gid)}
