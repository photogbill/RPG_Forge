"""The world queue (BUILD 39): a standing list of what a game's world needs, made whenever the machine is free.

    games/<id>/wanted_3d/*.json        the list — anyone adds entries at any time (a person, a session, the suite)
    games/<id>/wanted_3d/_state/       what the queue has done with each entry (written by the queue only)
    out/3d/world/<id>/<entry>/         everything made for one entry: picture, model, checks, report
    out/3d/world/<id>/REPORT.txt       one line per entry, newest first; world.log is the whole log
    make_what_we_need.bat              the one launcher: takes the next entry, makes it, checks it, goes on until stopped

An entry (one per thing; a file may hold one entry, a list of them, or {"defaults": {...}, "entries": [...]}):

    {"id": "jersey_barrier", "kind": "prop", "tier": "large_prop",
     "words": "A concrete jersey barrier, weathered, chipped edges",
     "real_size_m": {"width": 3.0},
     "first": {"where": "the first mission, the approach", "order": 1.02}}

  kind      body | prop | building | panel | tree
  tier      principal | named | crowd (bodies) · large_prop | small_prop | hand_prop (things) — faces and texture size
  words     what the picture is painted from (or "image": a picture to use as it is)
  first     where the thing first appears; `order` sorts the queue (lower first). Ties go to `rank` (lower first) —
            the order of need when two things tie is the person's — then to when the entry was written.
  hold      true: leave it until a person says otherwise.

Before every item the launcher reads the list again, so adding to it while it runs is safe and the launcher is never
edited. Closing its window loses at most the item in hand: every step skips what is already made, and the item in hand
is taken up first next time. It waits whenever the graphics card is someone else's (the card lock, a GPU job of the
art worker, requests waiting in ComfyUI). It approves nothing: a thing that passes its checks goes to Art -> Review &
approve; a thing that fails one is held back with the reason in plain words and a picture of what the check saw.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import socket
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from . import checks
from .env import out_root

log = logging.getLogger("forge.threed.world")

KINDS = ("body", "prop", "building", "panel", "tree")
# Faces and texture size by tier. principal and crowd were measured on 2026-11-14 (the launch-site run: the same three
# people at 60,000 faces / 2048 and at 20,000 / 1024 — the crowd bodies are half the file); the others are first
# settings, to be measured the same way. A game overrides any of them in games/<id>/wanted_3d/_tiers.json, the forge in
# forge.json -> threed.tiers.
TIERS = {
    "principal": {"faces": 60000, "texture": 2048, "for": "the party and the main cast", "measured": True},
    "named": {"faces": 40000, "texture": 2048, "for": "named people with lines", "measured": False},
    "crowd": {"faces": 20000, "texture": 1024, "for": "unnamed townsfolk, soldiers, crowds", "measured": True},
    "large_prop": {"faces": 40000, "texture": 2048, "for": "vehicles (TRELLIS.2: BUILD 40), buildings (Pixal3D), machines, "
                                                          "anything a person walks around", "measured": False},
    "small_prop": {"faces": 15000, "texture": 1024, "for": "furniture, crates, signs, lockers", "measured": False},
    "hand_prop": {"faces": 6000, "texture": 512, "for": "weapons, tools, anything held in a hand", "measured": False},
}
TIER_DEFAULT = {"body": "named", "prop": "small_prop", "building": "large_prop", "panel": "large_prop", "tree": "large_prop"}
BODY_TIERS = ("principal", "named", "crowd")
# seconds per item when nothing has been made yet (from the 2026-11-13/14 runs on the 16 GB card)
FIRST_GUESS = {"body": 600, "prop": 420, "building": 480, "panel": 5, "tree": 30, "quick": 10}
MAX_TRIES = 2                       # a thing whose making fails twice waits for a person ("Make again")
PEOPLE_WORDS = "Relaxed, kind expression, mouth closed."
# a smile in the picture is a smile forever: expression belongs to animation and portraits, not to a body
SMILE_WORD = re.compile(r"\b(?:smil(?:e|es|ed|ing|ey)|grin(?:s|ning|ned)?|laugh(?:s|ing)?|beaming)\b", re.I)
NEGATION = re.compile(r"\b(?:no|not|never|without|nor)\b|n't\b", re.I)
SMILE_PHRASE = re.compile(
    r"(?:\b(?:always|often|usually|constantly|forever)\s+)?"
    r"(?:\b(?:with|wearing|showing|giving|flashing|has|having)\s+(?:a|an|the|his|her|their)?\s*)?"
    r"(?:\b(?:big|broad|warm|wide|kind|gentle|soft|bright|toothy|friendly|slight|faint|easy|ready|cheerful|happy)\s+)*"
    r"\b(?:smil(?:e|es|ed|ing|ey)|grin(?:s|ning|ned)?|laugh(?:s|ing)?|beaming)\b"
    r"(?:\s+(?:at|to|towards?|for)\s+(?:the\s+|a\s+)?\w+)?", re.I)
MAKING_FIELDS = ("kind", "tier", "words", "image", "real_size_m", "seed", "model", "panel", "species", "faces", "texture",
                 "rig_kind", "skip_motions", "head_words", "shared_body", "wreck_of", "damage", "glow", "adopt", "no_straighten")
# BUILD 40's fields count only when an entry has them, so a thing made before them keeps its hash (and isn't made again)
MAKING_FIELDS_SET = ("seated", "carried_object", "expects", "age", "flame", "back_image", "back_words")


class WorldError(ValueError):
    pass


# ------------------------------------------------------------------------------------------------ where things are
def games_dir(cfg: dict | None) -> Path:
    from .. import config as cfgmod
    return cfgmod.path_of(cfg, "games") if cfg and "paths" in cfg else Path((cfg or {}).get("_root") or cfgmod.ROOT) / "games"


def list_dir(cfg: dict | None, gid: str) -> Path:
    return games_dir(cfg) / gid / "wanted_3d"


def state_dir(cfg: dict | None, gid: str) -> Path:
    return list_dir(cfg, gid) / "_state"


def world_dir(cfg: dict | None, gid: str) -> Path:
    return out_root(cfg) / "world" / gid


def item_dir(cfg: dict | None, gid: str, eid: str) -> Path:
    return world_dir(cfg, gid) / eid


def root_of(cfg: dict | None) -> Path:
    from .. import config as cfgmod
    return Path((cfg or {}).get("_root") or cfgmod.ROOT)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9_\-]+", "_", str(s or "").strip().lower()).strip("_")[:64]


def _read(p: Path, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(p: Path, data) -> None:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.{os.getpid()}.part")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------------------------------------ the list
def normalise(raw: dict, defaults: dict | None = None, file: str = "") -> dict:
    """One entry, checked and filled in. Raises WorldError with the reason in words."""
    e = {**(defaults or {}), **raw}
    eid = slug(e.get("id") or "")
    if not eid:
        raise WorldError(f"an entry in {file or 'the list'} has no id")
    kind = str(e.get("kind") or "prop").lower()
    if kind not in KINDS:
        raise WorldError(f"{eid}: kind must be one of {', '.join(KINDS)} (not {kind!r})")
    tier = str(e.get("tier") or TIER_DEFAULT[kind]).lower()
    if tier not in TIERS:
        raise WorldError(f"{eid}: tier must be one of {', '.join(TIERS)} (not {tier!r})")
    if kind == "body" and tier not in BODY_TIERS:
        raise WorldError(f"{eid}: a body's tier is principal, named or crowd")
    words = str(e.get("words") or e.get("prompt") or "").strip()
    if e.get("needs_words") and not words:                 # BUILD 34: a place's thing nobody has described: held
        e["hold"] = True
    elif kind in ("body", "prop", "building") and not (words or e.get("image") or e.get("adopt") or e.get("wreck_of")
                                                         or (e.get("shared_body") and e.get("head_words"))):
        raise WorldError(f"{eid}: say what it looks like (words) or give a picture (image)")
    size = e.get("real_size_m") or {}
    if isinstance(size, (int, float)):
        size = {"height": float(size)}
    size = {k: float(v) for k, v in dict(size).items() if k in ("height", "width", "depth") and v not in (None, "", 0)}
    if kind == "body" and "height" not in size:
        size["height"] = 1.72
    first = e.get("first") or {}
    if isinstance(first, (int, float)):
        first = {"order": float(first)}
    elif isinstance(first, str):
        first = {"where": first}
    out = {k: v for k, v in e.items() if k not in ("prompt",)}
    out.update(id=eid, kind=kind, tier=tier, words=words, real_size_m=size, first=dict(first),
               rank=float(e.get("rank") or 0), hold=bool(e.get("hold")), _file=file)
    return out


def load(cfg: dict | None, gid: str) -> tuple[list[dict], list[str]]:
    """Every entry in the game's list (read fresh), and the problems found (an entry with a problem is left out)."""
    d = list_dir(cfg, gid)
    entries, problems, seen = [], [], {}
    if not d.is_dir():
        return entries, problems
    for n, p in enumerate(sorted(x for x in d.glob("*.json") if not x.name.startswith("_"))):
        data = _read(p, None)
        if data is None:
            problems.append(f"{p.name} isn't readable JSON (a half-saved file is read again next time)")
            continue
        defaults = {}
        if isinstance(data, dict) and "entries" in data:
            defaults, items = dict(data.get("defaults") or {}), list(data.get("entries") or [])
        elif isinstance(data, list):
            items = data
        else:
            items = [data]
        for k, raw in enumerate(items):
            if not isinstance(raw, dict):
                problems.append(f"{p.name}: entry {k + 1} isn't an object")
                continue
            try:
                e = normalise(raw, defaults, p.name)
            except WorldError as ex:
                problems.append(str(ex))
                continue
            if e["id"] in seen:
                problems.append(f"{e['id']} is in the list twice ({seen[e['id']]} and {p.name}) — the first one counts")
                continue
            seen[e["id"]] = p.name
            e["_seq"] = (n, k)
            e["_mtime"] = p.stat().st_mtime
            entries.append(e)
    return entries, problems


def making_hash(e: dict) -> str:
    d = {k: e.get(k) for k in MAKING_FIELDS}
    d.update({k: e[k] for k in MAKING_FIELDS_SET if e.get(k) not in (None, "", {}, [], False)})
    return hashlib.sha1(json.dumps(d, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]


def read_state(cfg: dict | None, gid: str, eid: str) -> dict:
    return _read(state_dir(cfg, gid) / f"{eid}.json", {})


def write_state(cfg: dict | None, gid: str, eid: str, st: dict) -> dict:
    st["updated"] = _now()
    _write(state_dir(cfg, gid) / f"{eid}.json", st)
    return st


def review_state(cfg: dict | None, gid: str, st: dict) -> str | None:
    """What Review & approve says about a made thing: waiting / approved / rejected / delivered (None if not sent)."""
    tid = st.get("try")
    if not tid:
        return None
    tdir = games_dir(cfg) / gid / "threed"
    t = next(iter((tdir / "tries").glob(f"*/{tid}.json")), None)
    if t is None:
        return None
    r = (_read(t, {}).get("review") or {}).get("state")
    if r == "approved":
        a = _read(tdir / "approved.json", {})
        if any(v.get("try") == tid and v.get("delivered") for v in a.values()):
            return "delivered"
    return r


def merged(cfg: dict | None, gid: str) -> tuple[list[dict], list[str]]:
    """The list with what the queue has done with each entry, sorted in the order it will be made."""
    entries, problems = load(cfg, gid)
    out = []
    for e in entries:
        st = read_state(cfg, gid, e["id"])
        state = st.get("state") or "wanted"
        if state == "making" and not st.get("started"):
            state = "wanted"
        rv = review_state(cfg, gid, st) if state == "made" else None
        shown = {"approved": "approved", "rejected": "turned down", "delivered": "delivered"}.get(rv or "", state)
        if e["hold"] and state in ("wanted", "failed"):
            shown = "on hold"
        changed = bool(st.get("hash")) and st.get("hash") != making_hash(e) and state not in ("wanted", "making")
        out.append({**e, "state": state, "shown": shown, "review": rv, "st": st, "changed": changed})
    out.sort(key=order_key)
    return out, problems


def order_key(e: dict):
    f = e.get("first") or {}
    o = f.get("order")
    try:
        o = float(o)
    except (TypeError, ValueError):
        o = float("inf")
    return (o, float(e.get("rank") or 0), e.get("_seq", (0, 0)))


def depends_on(e: dict) -> str | None:
    """The entry this one is made from (a wreck from its intact model, a head on a shared body), if any."""
    return slug(e.get("wreck_of") or e.get("shared_body") or "") or None


def ready(e: dict, by_id: dict) -> bool:
    d = depends_on(e)
    return not d or (d in by_id and by_id[d]["state"] == "made")


def next_item(items: list[dict]) -> dict | None:
    """The item in hand when the launcher stopped first; then the first wanted thing in order of first appearance
    (a thing made from another waits until that one is made)."""
    by_id = {e["id"]: e for e in items}
    for e in items:
        if e["state"] == "making" and not e["hold"]:
            return e
    for e in items:
        if e["hold"] or not ready(e, by_id):
            continue
        if e["state"] == "wanted":
            return e
        if e["state"] == "failed" and int(e["st"].get("tries") or 0) < MAX_TRIES and e["st"].get("retry_after", 0) <= time.time():
            return e
    return None


# ------------------------------------------------------------------------------------------------ tiers and words
def tiers(cfg: dict | None, gid: str | None = None) -> dict:
    t = {k: dict(v) for k, v in TIERS.items()}
    for over in (((cfg or {}).get("threed") or {}).get("tiers") or {},
                 _read(list_dir(cfg, gid) / "_tiers.json", {}) if gid else {}):
        for k, v in (over or {}).items():
            if k in t and isinstance(v, dict):
                t[k].update({kk: vv for kk, vv in v.items() if kk in ("faces", "texture", "for", "measured")})
    return t


def tier_numbers(cfg: dict | None, gid: str, e: dict) -> tuple[int, int]:
    t = tiers(cfg, gid)[e["tier"]]
    return int(e.get("faces") or t["faces"]), int(e.get("texture") or t["texture"])


def body_words(words: str) -> tuple[str, list[str]]:
    """A body's description without its smile (a smile in the picture is a smile forever): every clause that asks for a
    smile, grin or laugh is taken out; a clause that rules one out ("not smiling", "without a grin") stays. Returns
    (words, the clauses taken out)."""
    parts = re.split(r"([,.;])", str(words or ""))
    segs = [(parts[i], parts[i + 1] if i + 1 < len(parts) else "") for i in range(0, len(parts), 2)]
    kept, gone = [], []
    for text, sep in segs:
        m = SMILE_WORD.search(text)
        if m and not NEGATION.search(text[: m.start()]):
            rest = text
            for pm in list(SMILE_PHRASE.finditer(text))[::-1]:
                if not NEGATION.search(text[: pm.start()]):
                    gone.append(pm.group(0).strip())
                    rest = rest[: pm.start()] + rest[pm.end():]
            if not re.sub(r"\b(?:and|a|an|the|with|is|are)\b", "", rest, flags=re.I).strip(" ,;."):
                if sep == "." and kept and kept[-1][1] in (",", ";"):
                    kept[-1] = (kept[-1][0], ".")           # the sentence still ends where it ended
                continue
            text = rest
        kept.append((text, sep))
    out = "".join(t + sp for t, sp in kept)
    out = re.sub(r"\s+", " ", out)
    out = re.sub(r"\s+([,.;])", r"\1", out)
    out = re.sub(r"([,;])\s*\.", ".", out)
    out = re.sub(r"\.\s*\.", ".", out)
    return out.strip(" ,;"), [g for g in gone[::-1] if g]


def standing_words(cfg: dict | None, gid: str, kind: str) -> tuple[str, str]:
    """The 'always' and negative words for a kind: the game's prompt blocks when it has them, else the forge's. A body's
    always-words end with the people wording (expression belongs to animation and portraits)."""
    from . import jobs
    k = "body" if kind == "body" else ("building" if kind == "building" else "prop")
    always, negative = jobs.words(cfg or {}, gid, k, "always"), jobs.words(cfg or {}, gid, k, "negative")
    if kind == "body":
        always, _ = body_words(always)
        if "mouth closed" not in always.lower():
            always = (always.rstrip() + " " + PEOPLE_WORDS).strip()
    return always, negative


# ------------------------------------------------------------------------------------------------ the machine
def machine_busy(cfg: dict | None, url: str | None = None, rig_url: str | None = None) -> str:
    """'' when the graphics card is free for the world queue; else why not, in words."""
    from . import cardlock, comfyapi
    st = cardlock.state(cfg)
    if st.get("held"):
        return f"{st.get('holder', 'someone')} has the graphics card (since {st.get('since', '?')})"
    try:
        from .. import config as cfgmod, schema
        jobs = cfgmod.path_of(cfg, "jobs") if cfg and "paths" in cfg else root_of(cfg) / "jobs"
        for p in sorted((jobs / "running").glob("*.json")):
            j = _read(p, {})
            if j and schema.needs_gpu(j):
                return f"the art worker is on a GPU job ({j.get('type')} {j.get('name') or j.get('id')})"
    except Exception:  # noqa: BLE001 — an unreadable queue is not a reason to stop
        pass
    url = url or ((cfg or {}).get("comfy") or {}).get("url") or "http://127.0.0.1:8188"
    if not comfyapi.is_up(url, timeout=3.0):
        return f"ComfyUI is not answering at {url}"
    n = comfyapi.queue_count(url)
    if n:
        return f"ComfyUI has {n} request(s) from someone else"
    from .env import from_cfg
    if comfyapi.is_up(rig_url or from_cfg(cfg).url, timeout=2.0):
        return "the rigging ComfyUI is running (it holds the card)"
    return ""


def model_for(kind: str) -> str:
    """The image-to-3D model a kind is made with (the forge's defaults.json: TRELLIS.2 for things, Pixal3D for buildings)."""
    d = _read(Path(__file__).with_name("defaults.json"), {})
    k = "building" if kind == "building" else ("body" if kind == "body" else "prop")
    return ((d.get("kinds") or {}).get(k) or {}).get("model") or "trellis2"


def blender_python_of(cfg: dict | None, given=None):
    """A Python with Blender inside to use for the Blender steps (forge.json threed.blender_python; tests name a stand-in)."""
    return given or ((cfg or {}).get("threed") or {}).get("blender_python") or None


def needs_card(e: dict) -> bool:
    return e["kind"] in ("body", "prop", "building") and not e.get("adopt")


# ------------------------------------------------------------------------------------------------ making one thing
def _rel(cfg: dict | None, p: Path | None) -> str | None:
    if p is None:
        return None
    try:
        return Path(p).resolve().relative_to(root_of(cfg).resolve()).as_posix()
    except ValueError:
        return str(p)


def _resolve(cfg: dict | None, gid: str, p: str | None) -> Path | None:
    if not p:
        return None
    q = Path(str(p).replace("\\", "/"))
    if q.is_absolute():
        return q
    for base in (root_of(cfg), games_dir(cfg) / gid):
        if (base / q).exists():
            return base / q
    return root_of(cfg) / q


class _Beat:
    """The launcher's heartbeat (out/3d/world/<id>/_launcher.json) — beats every 20 s while anything runs."""

    def __init__(self, cfg, gid):
        self.p = world_dir(cfg, gid) / "_launcher.json"
        self.d = {"pid": os.getpid(), "host": socket.gethostname(), "started": _now(), "beat": time.time(), "item": None,
                  "step": "starting", "since": _now(), "waiting": ""}
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._loop, daemon=True)

    def set(self, **kw) -> None:
        if "step" in kw or "item" in kw:
            kw.setdefault("since", _now())
        self.d.update(kw)
        self.write()

    def write(self) -> None:
        self.d["beat"] = time.time()
        try:
            _write(self.p, self.d)
        except OSError:
            pass

    def _loop(self):
        while not self._stop.wait(20):
            self.write()

    def __enter__(self):
        self.write()
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self.d.update(step="stopped", item=None, stopped=_now())
        self.write()


def launcher_state(cfg: dict | None, gid: str) -> dict:
    d = _read(world_dir(cfg, gid) / "_launcher.json", {})
    if not d:
        return {"running": False}
    age = time.time() - float(d.get("beat") or 0)
    alive = d.get("step") != "stopped" and age < 90
    if alive and d.get("host") == socket.gethostname() and d.get("pid"):
        from .cardlock import _pid_alive
        if _pid_alive(int(d["pid"])) is False:
            alive = False
    return {"running": alive, "item": d.get("item") if alive else None, "step": d.get("step"), "since": d.get("since"),
            "started": d.get("started"), "waiting": d.get("waiting") if alive else "", "beat_age": round(age),
            "stopped": d.get("stopped")}


def _stop_asked(cfg, gid) -> bool:
    return (world_dir(cfg, gid) / "STOP").exists()


def ask_stop(cfg: dict | None, gid: str, who: str = "") -> None:
    p = world_dir(cfg, gid) / "STOP"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"asked by {who or 'someone'} at {_now()}\n", encoding="utf-8")


def _clear_stop(cfg, gid) -> None:
    p = world_dir(cfg, gid) / "STOP"
    if p.exists():
        try:
            os.replace(p, p.with_name("STOP.done"))
        except OSError:
            pass


def make(cfg: dict | None, gid: str, e: dict, art_url: str | None = None, env=None, blender_python=None,
         use_lock: bool = True, beat: _Beat | None = None, local_out: Path | None = None) -> dict:
    """Make, check and report one entry. Returns its new state (also written to _state/<id>.json)."""
    out = item_dir(cfg, gid, e["id"])
    out.mkdir(parents=True, exist_ok=True)
    st = read_state(cfg, gid, e["id"])
    resumed = st.get("state") == "making"
    tries = int(st.get("tries") or 0) + (0 if resumed else 1)
    st = {"state": "making", "started": st.get("started") if resumed else _now(), "tries": tries, "hash": making_hash(e),
          "folder": _rel(cfg, out), "kind": e["kind"], "tier": e["tier"], "history": list(st.get("history") or [])[-20:],
          **({"gate_override": st["gate_override"]} if st.get("gate_override") else {})}
    write_state(cfg, gid, e["id"], st)
    h = logging.FileHandler(out / "run.log", encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
    lg = logging.getLogger("forge.threed")
    lg.addHandler(h)
    if lg.level == logging.NOTSET or lg.level > logging.INFO:
        lg.setLevel(logging.INFO)
    t0 = time.time()
    try:
        log.info("==== %s (%s, %s) — %s%s", e["id"], e["kind"], e["tier"], "taken up again" if resumed else f"try {tries}",
                 f"; first appears: {e['first'].get('where')}" if e["first"].get("where") else "")
        route = {"body": _make_body, "prop": _make_thing, "building": _make_thing, "panel": _make_panel, "tree": _make_tree}[e["kind"]]
        if e.get("adopt"):
            route = _adopt
        elif e["kind"] == "body" and e.get("shared_body"):
            route = _make_head_on_body
        elif e.get("wreck_of"):
            route = _make_wreck
        res = route(cfg, gid, e, out, art_url=art_url, env=env, blender_python=blender_python, use_lock=use_lock, beat=beat,
                    local_out=local_out)
        if res.get("state") == "made" and e.get("glow") and res.get("model"):
            res = _add_glow(cfg, e, res)
        if res.get("state") == "made" and e.get("flame") and res.get("model"):
            res = _add_flame(cfg, gid, e, res)
    except Exception as ex:  # noqa: BLE001 — a failure is written down and the queue goes on
        log.exception("%s: FAILED - %s", e["id"], ex)
        res = {"state": "failed", "error": f"{type(ex).__name__}: {ex}"[:1500]}
    finally:
        lg.removeHandler(h)
        h.close()
    secs = round(time.time() - t0)
    if res.get("state") == "wanted":                         # it turned out to wait for another entry: no try is spent
        st.update(res, tries=max(0, tries - 1), started=None)
        write_state(cfg, gid, e["id"], st)
        return st
    st.update(res)
    st["seconds"] = secs + int((st.get("seconds_before") or 0))
    st["finished"] = _now()
    if st["state"] == "failed":
        st["retry_after"] = time.time() + 15 * 60                  # not straight away: let the next thing have a go
    st["history"].append({"at": _now(), "state": st["state"], "seconds": secs, "try": tries})
    write_state(cfg, gid, e["id"], st)
    if st["state"] == "made":
        st["try"] = to_review(cfg, gid, e, st)
        write_state(cfg, gid, e["id"], st)
    _item_report(out, e, st)
    log.info("%s: %s in %d s%s", e["id"], st["state"].upper(), secs, (" — " + st.get("error", "")) if st["state"] == "failed" else "")
    return st


def _paint_spec(cfg, gid, e, model: str) -> dict:
    faces, texture = tier_numbers(cfg, gid, e)
    always, negative = standing_words(cfg, gid, e["kind"])
    obj = {"id": e["id"], "seed": int(e.get("seed") or 1001) + int(read_state(cfg, gid, e["id"]).get("tries", 1)) - 1,
           "real_size_m": e["real_size_m"]}
    notes = []
    words = e["words"]
    if e["kind"] == "body":
        words, smiles = body_words(words)
        if smiles:
            notes.append("took " + "; ".join(f"“{s}”" for s in smiles) + " out of the body picture's words — a smile in the "
                         "picture is a smile forever (expression belongs to animation and portraits)")
        if not e.get("image") and e.get("standing_words", True) is not False:
            from . import rules
            words, always, sw_notes = rules.body_word_rules(words, always)     # BUILD 40: what the second run taught
            notes += sw_notes
    if e.get("image"):
        img = _resolve(cfg, gid, e["image"])
        if not img or not img.exists():
            raise FileNotFoundError(f"the picture {e['image']} is not there")
        obj["image"] = str(img)
    else:
        obj["prompt"] = words
    for k in ("back_image", "back_words"):                 # BUILD 40: a back view, for Pixal3D (buildings)
        if e.get(k):
            obj[k] = str(_resolve(cfg, gid, e[k])) if k == "back_image" else e[k]
    if e["kind"] == "body":
        # BUILD 40: what the picture gate holds the picture to, when the entry says it outright
        for k in ("expects", "age", "seated", "carried_object", "gate_tries"):
            if e.get(k) not in (None, "", {}):
                obj[k] = e[k]
    spec = {"batch": f"world_{gid}_{e['id']}"[:60], "models": [model], "resolutions": [1024], "faces": faces, "texture": texture,
            "minutes_per_model": int(e.get("minutes") or 60),
            "picture": {"unet": e.get("unet") or "flux-2-klein-4b.safetensors", "size": 1024, "seed": obj["seed"],
                        "always": always, "negative": negative},
            "objects": [obj]}
    return {"spec": spec, "notes": notes, "words": words, "always": always}


def _make_thing(cfg, gid, e, out, art_url=None, use_lock=True, beat=None, local_out=None, env=None, blender_python=None, **_):
    from . import bodies
    model = e.get("model") or model_for(e["kind"])
    p = _paint_spec(cfg, gid, e, model)
    if beat:
        beat.set(step="picture and model")
    rows = bodies.run(cfg, p["spec"], out, url=art_url, local_out=local_out, lock_holder=f"world list {gid}: {e['id']}",
                      use_lock=use_lock)
    row = rows[0] if rows else {}
    raw = out / "models" / f"{e['id']}__{model}.glb"
    if not row.get("ok") or not raw.exists():
        return {"state": "failed", "error": "no 3D model was made: " + str(row.get("error") or "see run.log")[:600], "notes": p["notes"]}
    return _check_and_place(cfg, gid, e, out, raw, out / "pictures" / f"{e['id']}.png", env, blender_python,
                            extra={"engine": model, "notes": p["notes"], "words_used": p["words"]})


def _result(res: dict, check: str) -> dict | None:
    return next((r for r in res.get("results") or [] if r.get("check") == check), None)


def _put_right(cfg, e: dict, out: Path, raw: Path, pic: Path | None, res: dict) -> tuple[Path, dict, dict]:
    """BUILD 40: what the queue puts right by itself, the model as made always kept beside it — blank glass given a dark
    glass colour; a body's colours matched to its picture. A prop's or building's colour miss is not trusted blind (its
    picture carries studio light the texture rightly doesn't): the matched version is made beside it and a person
    chooses it (Use the matched colours) or lets the thing through. Returns (the model to go on with, the checks on it,
    extra state)."""
    s = checks.settings(cfg)
    notes, extra, cur = [], {}, raw
    gl = _result(res, "glass")
    if gl and not gl["ok"] and s.get("glass_fix"):
        dst = out / f"{e['id']}__glass.glb"
        try:
            fr = checks.fix_glass(cur, dst, cfg)
            if fr.get("changed") and fr.get("ok"):
                cur = dst
                notes.append(f"Blank glass: {gl['share'] * 100:.1f}% of the surface was a white mirror — given a dark glass colour "
                             "and its own roughness by the queue (the model as made is kept beside it).")
        except Exception as ex:  # noqa: BLE001 — a fix that fails leaves the thing held, as before
            log.warning("  blank glass not fixed: %s", ex)
    co = _result(res, "colour")
    if co and not co["ok"] and not co.get("skipped") and s.get("colour_fix") and pic is not None:
        from PIL import Image
        dst = out / f"{e['id']}__colour.glb"
        try:
            im = Image.open(pic)
            im.load()
            kind = e["tier"] if e["kind"] == "body" else e["kind"]
            fr = checks.fix_colour(cur, dst, im, cfg, kind)
            if fr.get("before") is not None and fr["before"].get("render") is not None:
                checks.colour_picture(fr["before"], fr.get("after"), out / "colour.png")
                extra["colour_picture"] = _rel(cfg, out / "colour.png")
            if co.get("auto_fix") and fr.get("ok"):
                cur = dst
                extra["colour_lut"] = np.asarray(fr["lut"]).tolist()
                notes.append(f"Colours hold: {co['mean_ratio'] * 100:.0f}% of its picture's brightness — matched to the picture by "
                             "the queue, one tone curve per colour (the model as made is kept beside it).")
            elif fr.get("after") is not None:
                extra["colour_offer"] = _rel(cfg, dst)
                extra["colour_offer_lut"] = np.asarray(fr["lut"]).tolist()
        except Exception as ex:  # noqa: BLE001
            log.warning("  colours not matched: %s", ex)
    if cur != raw:
        res = checks.run(cur, pic, e["kind"], e["tier"], cfg, out_picture=out / "checks.png")
        res["lines"] = notes + res["lines"]
        res["results"] = [{"check": "put_right", "ok": True, "line": n} for n in notes] + res["results"]
        extra["put_right"] = notes
    return cur, res, extra


def _check_and_place(cfg, gid, e, out, raw: Path, picture: Path | None, env=None, blender_python=None, extra=None) -> dict:
    """The checks on the model as it came out; if it passes, its real size in metres, stood on the floor."""
    pic = picture if picture and picture.exists() else None
    res = checks.run(raw, pic, e["kind"], e["tier"], cfg, out_picture=out / "checks.png")
    raw, res, fixed = _put_right(cfg, e, out, raw, pic, res)
    extra = {**(extra or {}), **fixed}
    straightened = None
    lvl = next((r for r in res["results"] if r["check"] == "level"), None)
    limit = float(checks.settings(cfg).get("straighten_up_to_deg") or 0)
    others_ok = all(r["ok"] for r in res["results"] if r["check"] != "level")
    if (not res["ok"] and lvl and not lvl["ok"] and lvl.get("leans_as_whole") and others_ok and lvl["tilt_deg"] <= limit
            and not e.get("no_straighten")):
        # it leans as a whole (Pixal3D does this to nearly every building): turning it level loses nothing — the model as
        # made is kept beside it — so the queue does it and says so, instead of holding it for a person's click
        from . import meshio
        level_glb = out / f"{e['id']}__level.glb"
        meshio.place(raw, level_glb, size=None, rotation=lvl["straighten"], centre=False, floor=False)
        res2 = checks.run(level_glb, pic, e["kind"], e["tier"], cfg, out_picture=out / "checks.png")
        if res2["ok"]:
            note = (f"Sits level: it leant {lvl['tilt_deg']}° as a whole, and its walls agreed — straightened by the queue "
                    f"(nothing lost; the model as made is kept beside it).")
            res2["lines"] = [note] + [ln for ln in res2["lines"]]
            res2["results"] = [{"check": "straightened", "ok": True, "from_deg": lvl["tilt_deg"], "line": note}] + res2["results"]
            res, raw, straightened = res2, level_glb, lvl["tilt_deg"]
    _write(out / "checks.json", res)
    for ln in res["lines"]:
        log.info("  %s", ln)
    base = {"model_raw": _rel(cfg, raw), "picture": _rel(cfg, picture) if picture and picture.exists() else None,
            "checks": res["lines"], "check_results": res["results"], "check_picture": _rel(cfg, Path(res["picture"])) if res.get("picture") else None,
            **({"auto_straightened_deg": straightened, "straightened": True} if straightened else {}), **(extra or {})}
    if not res["ok"]:
        return {"state": "held", "why": [r["line"] for r in res["results"] if not r["ok"]], **base}
    final = place_final(cfg, e, raw, out, env=env, blender_python=blender_python)
    return {"state": "made", **base, **final}


def place_final(cfg, e, raw: Path, out: Path, rotation=None, env=None, blender_python=None) -> dict:
    """The thing as it goes to the game: crumbs off and seams welded (Blender, when there is one), its real size in
    metres, standing on the floor, centred — `<out>/<id>.glb`."""
    from . import meshio
    final = out / f"{e['id']}.glb"
    src, tidied = raw, None
    if e["kind"] in ("prop", "building") and env is not None:
        from . import tidy
        t = tidy.tidy(env, raw, out / f"{e['id']}__tidy.glb", scraps=float(e.get("scraps") or 0.02), size=e["real_size_m"] or None,
                      python=blender_python)
        if t["ok"]:
            src, tidied = out / f"{e['id']}__tidy.glb", t["report"]
        else:
            log.warning("  not tidied (%s) — sized without Blender", t["error"][:300])
    rep = meshio.place(src, final, size=e["real_size_m"] or None, rotation=rotation)
    log.info("  real size: %s (scale %.4f by %s)%s", rep["size_m"], rep["scale"], rep["by"] or "-", ", straightened" if rotation else "")
    return {"model": _rel(cfg, final), "size_m": rep["size_m"], "tidy": tidied, "straightened": bool(rotation)}


def _make_body(cfg, gid, e, out, art_url=None, use_lock=True, beat=None, local_out=None, env=None, blender_python=None, **_):
    from . import line
    p = _paint_spec(cfg, gid, e, "trellis2")
    spec = p["spec"]
    obj = spec["objects"][0]
    obj["kind"] = e.get("rig_kind") or "people"
    if e.get("skip_motions"):
        obj["skip_motions"] = list(e["skip_motions"])
    spec["rig"] = dict(e.get("rig") or {})
    if e.get("motions"):
        spec["motions"] = dict(e["motions"])
    # BUILD 40: the picture gate looks at the picture before the body is made from it (a person can switch it off for
    # an entry with "gate": false, or let one picture through with "Make the body from this picture anyway")
    st0 = read_state(cfg, gid, e["id"])
    spec["gate"] = e.get("gate") not in (False, "off") and not st0.get("gate_override")
    if beat:
        beat.set(step="picture and body")
    line.run(cfg, spec, out, skip=("rig", "fit"), art_url=art_url, env=env, blender_python=blender_python, use_lock=use_lock,
             local_out=local_out)
    raw = out / "models" / f"{e['id']}__trellis2.glb"
    grec = _read(out / "pictures" / f"{e['id']}.gate.json", {})
    gate_lines = [ln for t in grec.get("tries") or [] for ln in t.get("lines") or []][-6:]
    if spec["gate"] and grec.get("held") and not raw.exists():
        return {"state": "held", "held_by": "picture gate", "why": ["Picture gate: " + w.replace("Picture gate — ", "")
                                                                   for w in grec.get("why") or ["the picture missed"]],
                "picture": _rel(cfg, out / "pictures" / f"{e['id']}.png"),
                "gate": {"tries": [{"try": t["try"], "seed": t["seed"], "ok": t["ok"], "lines": t["lines"],
                                    "picture": _rel(cfg, out / "pictures" / t["picture"])} for t in grec.get("tries") or []],
                         "side_by_side": _rel(cfg, out / "pictures" / grec["side_by_side"]) if grec.get("side_by_side") else None},
                "checks": gate_lines, "notes": p["notes"], "words_used": p["words"], "engine": "trellis2"}
    if not raw.exists():
        r = _read(out / "report.json", [])
        err = next((x.get("error") for x in r if isinstance(x, dict) and x.get("error")), "see run.log")
        return {"state": "failed", "error": f"no 3D body was made: {err}"[:600], "notes": p["notes"]}
    pic = out / "pictures" / f"{e['id']}.png"
    res = checks.run(raw, pic, "body", e["tier"], cfg, out_picture=out / "checks.png")
    fixed = {}
    if not res["ok"]:
        # BUILD 40: blank glass and a body's colours are put right by the queue. The skeleton step reads the body from
        # models/, so the matched body takes the raw file's place there and the body as made is kept beside it.
        cur, res, fixed = _put_right(cfg, e, out, raw, pic if pic.exists() else None, res)
        if cur != raw:
            import shutil
            as_made = raw.with_name(raw.stem + "__as_made.glb")
            if not as_made.exists():
                shutil.copyfile(raw, as_made)
            shutil.copyfile(cur, raw)
            fixed["model_as_made"] = _rel(cfg, as_made)
    _write(out / "checks.json", res)
    for ln in res["lines"]:
        log.info("  %s", ln)
    if st0.get("gate_override"):
        gate_lines = [f"Picture gate: let through by {st0['gate_override'].get('by')} (picture {st0['gate_override'].get('try')})."]
    base = {"model_raw": _rel(cfg, raw), "picture": _rel(cfg, pic), "checks": gate_lines + res["lines"],
            "check_results": res["results"], "check_picture": _rel(cfg, Path(res["picture"])) if res.get("picture") else None,
            "notes": p["notes"], "words_used": p["words"], "engine": "trellis2", **fixed}
    if not res["ok"]:
        return {"state": "held", "why": [r["line"] for r in res["results"] if not r["ok"]], **base}
    rg = obj.get("rigger") or ("unirig" if obj["kind"] in ("animal", "thing") else "mia")
    still = "seated" if e.get("seated") else (f"leaning on a {e['carried_object']}" if e.get("carried_object") else "")
    if still:
        # BUILD 40: a seated body (a wheelchair comes out fused to its sitter) or one leaning on a cane or crutch gets a
        # skeleton but no motion fitting: the library's walks and runs on such a body mean nothing
        if beat:
            beat.set(step="skeleton (no motions: " + still + ")")
        line.run(cfg, spec, out, skip=("pictures", "fit"), art_url=art_url, env=env, blender_python=blender_python,
                 use_lock=use_lock, local_out=local_out)
        fbx = out / "rig" / f"{e['id']}__{rg}.fbx"
        final = place_final(cfg, e, raw, out, env=env, blender_python=blender_python)
        note = (f"{still.capitalize()}: no motions were fitted — the library's walks and runs on a body like this mean nothing. "
                + ("The skeleton is made; " if fbx.exists() else "The skeleton was not made; ")
                + "motions for it (sitting, or a walk with the aid) are a person's choice in 3D → Skeleton & motions.")
        log.info("  %s", note)
        return {"state": "made", **base, **final, "fbx": _rel(cfg, fbx) if fbx.exists() else None, "rigger": rg,
                "motion_note": note, "checks": base["checks"] + [note]}
    if beat:
        beat.set(step="skeleton and motions")
    rows = line.run(cfg, spec, out, skip=("pictures",), art_url=art_url, env=env, blender_python=blender_python,
                    use_lock=use_lock, local_out=local_out)
    row = rows[0] if rows else {}
    moves = out / "moves" / f"{e['id']}_moves.glb"
    if not row.get("motions") or not moves.exists():
        return {"state": "failed", "error": (row.get("why") or "the skeleton or the motions were not made")[:600], **base}
    sheet = moves.with_suffix(".json")
    return {"state": "made", **base, "model": _rel(cfg, moves), "sheet": _rel(cfg, sheet) if sheet.exists() else None,
            "fbx": _rel(cfg, out / "rig" / f"{e['id']}__{rg}.fbx"), "rigger": rg,
            "size_m": {"height": e["real_size_m"].get("height")}}


def _make_panel(cfg, gid, e, out, beat=None, **_):
    from . import panels
    if beat:
        beat.set(step="cut-out panel")
    rep = panels.make(cfg, gid, e, out)
    for ln in rep["lines"]:
        log.info("  %s", ln)
    spec = e.get("panel") or {}
    # what went into it, for Review's licence lines: the texture's maker (none for the forge's own stand-in) and
    # whatever made the posts it keeps (another entry of the list, or a model file nobody has recorded)
    posts_keys = []
    if spec.get("from_model"):
        src_state = read_state(cfg, gid, slug(spec["from_model"]))
        posts_keys = (licence_keys(src_state) if src_state.get("engine")
                      else [f"model file {Path(str(spec['from_model'])).name}"])
    return {"state": "made", "model": _rel(cfg, Path(rep["glb"])), "size_m": rep["size_m"],
            "checks": ["Made by rule (a flat panel with a cut-out texture): the image-to-3D checks don't apply."] + rep["lines"],
            "texture": rep.get("texture"), "stand_in_texture": rep.get("stand_in", False), "engine": "panel",
            "texture_licence": None if rep.get("stand_in") else (spec.get("texture_licence") or "texture licence not given"),
            "posts_keys": posts_keys}


def _make_tree(cfg, gid, e, out, env=None, blender_python=None, beat=None, **_):
    from . import trees
    from .env import from_cfg
    env = env or from_cfg(cfg)
    sp = e.get("species") or "broadleaf"
    sheet = next((s for s in trees.sheets(games_dir(cfg) / gid) if s["name"] == sp or Path(s["file"]).stem == sp), None)
    if sheet is None:
        return {"state": "failed", "error": f"there is no species sheet called {sp!r}"}
    if beat:
        beat.set(step="growing the tree")
    r = trees.grow(env, out / "tree", sheet, int(e.get("seed") or 11), bare=bool(e.get("bare")), name=sheet.get("name"),
                   python=blender_python)
    if not r["ok"]:
        return {"state": "failed", "error": r["error"][:600]}
    final = place_final(cfg, e, Path(r["glb"]), out)
    return {"state": "made", **final, "checks": ["Grown by rule from a species sheet: the image-to-3D checks don't apply."],
            "engine": "forge_tree"}


def _add_glow(cfg, e: dict, res: dict) -> dict:
    """The glow layer (eyes, lamps) on a made thing: its glow colours become an emissive texture the game can brighten."""
    from . import damage
    spec = e["glow"] if isinstance(e["glow"], dict) else {"colours": e["glow"] if isinstance(e["glow"], list) else [e["glow"]]}
    model = root_of(cfg) / res["model"]
    tmp = model.with_name(model.stem + "__glow.glb")
    r = damage.glow(model, tmp, colours=tuple(spec.get("colours") or ("amber",)), strength=float(spec.get("strength") or 1.0),
                    name=str(spec.get("name") or "glow"))
    os.replace(tmp, model)
    log.info("  %s", r["line"])
    return {**res, "glow": r, "checks": list(res.get("checks") or []) + [r["line"]]}


def _add_flame(cfg, gid, e: dict, res: dict) -> dict:
    """BUILD 40: flame cards where the made thing's colours burn (a campfire, lit candles), from a flame picture of the
    palette when the entry names one ("flame": {"texture": ..., "source": ...}), else a stand-in flame made here."""
    from . import damage
    spec = e["flame"] if isinstance(e["flame"], dict) else {}
    tex = _resolve(cfg, gid, spec["texture"]) if spec.get("texture") else None
    if tex is not None and not tex.exists():
        log.warning("  the flame picture %s is not there — a stand-in flame is used", spec["texture"])
        tex = None
    model = root_of(cfg) / res["model"]
    tmp = model.with_name(model.stem + "__flame.glb")
    r = damage.flame(model, tmp, texture=tex, colours=tuple(spec.get("colours") or damage.FLAME_COLOURS),
                     strength=float(spec.get("strength") or 3.0), scale=float(spec.get("scale") or 1.0),
                     source=str(spec.get("source") or (spec.get("texture") if tex else "")), min_val=float(spec.get("min_val") or 0.82),
                     width_share=spec.get("width_share"))
    os.replace(tmp, model)
    log.info("  %s", r["line"])
    return {**res, "flame": {k: r[k] for k in ("sites", "line") if k in r}, "checks": list(res.get("checks") or []) + [r["line"]]}


def _make_wreck(cfg, gid, e, out, beat=None, **_):
    """A wrecked version made from the intact thing (already made and checked) plus damage — never from a new picture."""
    from . import damage
    src_id = slug(e["wreck_of"])
    src = read_state(cfg, gid, src_id)
    if src.get("state") != "made" or not src.get("model"):
        return {"state": "wanted", "why": [f"waits for {src_id} to be made"]}
    if beat:
        beat.set(step="damaging the intact model")
    spec = e.get("damage") or {}
    final = out / f"{e['id']}.glb"
    r = damage.wreck(root_of(cfg) / src["model"], final, seed=int(spec.get("seed") or e.get("seed") or 1),
                     hits=int(spec.get("hits") or 4), strength=float(spec.get("strength") or 0.8), hole=bool(spec.get("hole", True)))
    from . import meshio
    lo, hi = meshio.Glb.load(final).bounds()
    line = (f"Made from {src_id} (made and checked) plus damage: {r['hits']} hits, {r['faces_removed']} faces punched out, "
            f"scorch on {r['faces_scorched']} faces (strength {r['strength']}).")
    log.info("  %s", line)
    return {"state": "made", "model": _rel(cfg, final), "picture": src.get("picture"), "engine": src.get("engine"),
            "adopted": src.get("adopted", False), "tidy": src.get("tidy"), "wreck_of": src_id, "damage": r,
            "size_m": {"width": round(float(hi[0] - lo[0]), 3), "height": round(float(hi[1] - lo[1]), 3), "depth": round(float(hi[2] - lo[2]), 3)},
            "checks": [line, "The image-to-3D checks were done on the intact model."]}


def _make_head_on_body(cfg, gid, e, out, art_url=None, use_lock=True, beat=None, local_out=None, env=None, blender_python=None, **_):
    """One person of a crowd: their own head (a head-and-shoulders picture, a small head model) joined at the collar
    onto the shared body, then a skeleton and motions like any body."""
    from . import bodies, heads, line
    from .env import from_cfg
    sb = slug(e["shared_body"])
    sbs = read_state(cfg, gid, sb)
    if sbs.get("state") != "made" or not sbs.get("model_raw"):
        return {"state": "wanted", "why": [f"waits for the shared body {sb} to be made"]}
    words, smiles = body_words(str(e.get("head_words") or e.get("words") or ""))
    notes = [f"took “{x}” out of the head picture's words (expression belongs to animation and portraits)" for x in smiles]
    seed = int(e.get("seed") or 1001) + int(read_state(cfg, gid, e["id"]).get("tries", 1)) - 1
    hid = f"{e['id']}_head"
    spec = {"batch": f"world_{gid}_{hid}"[:60], "models": ["trellis2"], "resolutions": [1024], "faces": 15000, "texture": 1024,
            "minutes_per_model": 30, "picture": {"size": 1024, "seed": seed, "always": e.get("head_always") or heads.HEAD_ALWAYS,
                                                 "negative": heads.HEAD_NEGATIVE},
            "objects": [{"id": hid, "prompt": words, "seed": seed}]}
    if beat:
        beat.set(step="the head: picture and model")
    rows = bodies.run(cfg, spec, out, url=art_url, local_out=local_out, lock_holder=f"world list {gid}: {e['id']} (head)", use_lock=use_lock)
    head = out / "models" / f"{hid}__trellis2.glb"
    if not (rows and rows[0].get("ok")) or not head.exists():
        return {"state": "failed", "error": "no head model was made: " + str((rows or [{}])[0].get("error") or "see run.log")[:500]}
    if beat:
        beat.set(step="joining the head at the collar")
    joined = out / "models" / f"{e['id']}__trellis2.glb"
    j = heads.join(env or from_cfg(cfg), root_of(cfg) / sbs["model_raw"], head, joined, collar=e.get("collar"), python=blender_python)
    if not j["ok"]:
        return {"state": "failed", "error": "the head could not be joined: " + j["error"]}
    res = checks.run(joined, None, "body", e["tier"], cfg, out_picture=out / "checks.png", only=("loose", "glass"))
    _write(out / "checks.json", res)
    base = {"model_raw": _rel(cfg, joined), "picture": _rel(cfg, out / "pictures" / f"{hid}.png"), "engine": "trellis2",
            "checks": [f"Head joined at the collar ({j['report'].get('collar_share')} of the height, head scaled "
                       f"{j['report'].get('head_scale')})."] + res["lines"], "check_results": res["results"], "notes": notes,
            "shared_body": sb, "join": j["report"]}
    if not res["ok"]:
        return {"state": "held", "why": [r["line"] for r in res["results"] if not r["ok"]], **base}
    if beat:
        beat.set(step="skeleton and motions")
    lspec = {"batch": spec["batch"], "rig": dict(e.get("rig") or {}), **({"motions": e["motions"]} if e.get("motions") else {}),
             "objects": [{"id": e["id"], "kind": "people", "real_size_m": e["real_size_m"],
                          **({"skip_motions": list(e["skip_motions"])} if e.get("skip_motions") else {})}]}
    rows = line.run(cfg, lspec, out, skip=("pictures",), art_url=art_url, env=env, blender_python=blender_python,
                    use_lock=use_lock, local_out=local_out)
    moves = out / "moves" / f"{e['id']}_moves.glb"
    if not (rows and rows[0].get("motions")) or not moves.exists():
        return {"state": "failed", "error": ((rows or [{}])[0].get("why") or "the skeleton or the motions were not made")[:600], **base}
    sheet = moves.with_suffix(".json")
    return {"state": "made", **base, "model": _rel(cfg, moves), "sheet": _rel(cfg, sheet) if sheet.exists() else None,
            "fbx": _rel(cfg, out / "rig" / f"{e['id']}__mia.fbx"), "rigger": "mia", "size_m": {"height": e["real_size_m"].get("height")}}


def _adopt(cfg, gid, e, out, env=None, blender_python=None, beat=None, **_):
    """A thing made before the queue existed (a run's model): checked and sized like anything the queue makes, never remade."""
    raw = _resolve(cfg, gid, e["adopt"])
    if not raw or not raw.exists():
        return {"state": "failed", "error": f"the model to adopt is not there: {e['adopt']}"}
    if beat:
        beat.set(step="checking a model made earlier")
    pic = _resolve(cfg, gid, e.get("adopt_picture")) if e.get("adopt_picture") else None
    if e["kind"] == "body":
        res = checks.run(raw, pic, "body", e["tier"], cfg, out_picture=out / "checks.png")
        raw0 = raw
        raw, res, fixed = _put_right(cfg, e, out, raw, pic, res)
        _write(out / "checks.json", res)
        base = {"model_raw": _rel(cfg, raw), "picture": _rel(cfg, pic) if pic else None, "checks": res["lines"],
                "check_results": res["results"], "check_picture": _rel(cfg, Path(res["picture"])) if res.get("picture") else None,
                "adopted": True, "engine": e.get("model") or "trellis2", **fixed}
        if not res["ok"]:
            return {"state": "held", "why": [r["line"] for r in res["results"] if not r["ok"]], **base}
        moves = _resolve(cfg, gid, e.get("adopt_moves")) if e.get("adopt_moves") else None
        if moves and moves.exists() and fixed.get("colour_lut"):
            # the run's moving copy gets the same curves (the run's own file is left as it is)
            mv = out / f"{e['id']}_moves__colour.glb"
            checks.apply_lut(moves, mv, fixed["colour_lut"])
            if moves.with_suffix(".json").exists() and not mv.with_suffix(".json").exists():
                import shutil
                shutil.copyfile(moves.with_suffix(".json"), mv.with_suffix(".json"))
            moves = mv
        if raw != raw0:
            base["model_as_made"] = _rel(cfg, raw0)
        if moves and moves.exists():
            sheet = moves.with_suffix(".json")
            return {"state": "made", **base, "model": _rel(cfg, moves), "sheet": _rel(cfg, sheet) if sheet.exists() else None,
                    "size_m": {"height": e["real_size_m"].get("height")}}
        return {"state": "held", **base, "why": ["Adopted body has no motions yet: run it through Skeleton & motions."]}
    return _check_and_place(cfg, gid, e, out, raw, pic, env, blender_python,
                            extra={"adopted": True, "engine": e.get("model") or ("pixal3d" if "pixal3d" in raw.name else "trellis2")})


def _item_report(out: Path, e: dict, st: dict) -> None:
    lines = [f"{e['id']} ({e['kind']}, {e['tier']}): {st['state'].upper()}  —  {st.get('finished', '')}, {st.get('seconds', 0)} s",
             f"first appears: {e['first'].get('where') or '-'}", ""]
    lines += [f"  {ln}" for ln in st.get("checks") or []]
    if st.get("why"):
        lines += ["", "Held back because:"] + [f"  - {w}" for w in st["why"]]
    if st.get("error"):
        lines += ["", "Failed: " + st["error"]]
    for n in st.get("notes") or []:
        lines.append(f"Note: {n}")
    if st.get("model"):
        lines += ["", f"The model: {st['model']}" + (f"  ({st['size_m']})" if st.get("size_m") else "")]
    (out / "REPORT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ------------------------------------------------------------------------------------------------ to Review & approve
def licence_keys(st: dict) -> list[str]:
    keys = []
    eng = st.get("engine")
    if eng in ("trellis2", "pixal3d"):
        keys += ([] if st.get("adopted") and not st.get("picture") else ["flux2_klein_4b"]) + [eng, "comfy_template"]
    if st.get("fbx"):
        keys += [st.get("rigger") or "mia", "comfyui_unirig"]
    if st.get("sheet"):
        keys += ["quaternius_ual", "blender"]
    if st.get("tidy"):
        keys += ["blender"]
    if eng == "forge_tree":
        keys += ["forge_tree", "blender"]
    if eng == "panel":
        keys += list(st.get("posts_keys") or []) + ([st["texture_licence"]] if st.get("texture_licence") else [])
    return list(dict.fromkeys(keys))


def to_review(cfg: dict | None, gid: str, e: dict, st: dict) -> str:
    """A made thing goes to Art -> Review & approve as a 'try' (the same place the 3D tabs send theirs). Returns its id."""
    tdir = games_dir(cfg) / gid / "threed" / "tries" / slug(e["id"])
    tid = f"world-{slug(e['id'])}-{int(st.get('tries') or 1)}-{datetime.now():%m%d%H%M%S}"
    kind = "body" if e["kind"] == "body" else ("building" if e["kind"] == "building" else "prop")
    steps = {}
    if st.get("picture"):
        steps["pictures"] = {"state": "done", "files": [st["picture"]]}
    if kind == "body":
        steps["body"] = {"state": "done", "model": st.get("model_raw"), "picture": st.get("picture"), "engine": st.get("engine")}
        if st.get("fbx"):
            steps["skeleton"] = {"state": "done", "fbx": st["fbx"], "rigger": st.get("rigger")}
        if st.get("motion_note"):
            steps["motions"] = {"state": "skipped", "note": st["motion_note"]}
        else:
            steps["motions"] = {"state": "done", "moves": st.get("model"), "sheet": st.get("sheet")}
    else:
        steps["body"] = {"state": "done", "model": st.get("model"), "picture": st.get("picture"), "engine": st.get("engine"),
                         "tidy": st.get("tidy")}
    t = {"id": tid, "who": slug(e["id"]), "who_name": e.get("name") or e["id"].replace("_", " "), "kind": kind,
         "world_kind": e["kind"], "look": st.get("words_used") or e.get("words"), "from": "world", "world_id": e["id"],
         "tier": e["tier"], "real_size_m": e["real_size_m"], "height_m": e["real_size_m"].get("height"),
         "created": _now(), "t_ns": time.time_ns(), "by": "the world queue", "steps": steps,
         "licence_keys": licence_keys(st), "checks": st.get("checks"), "check_picture": st.get("check_picture"),
         "review": {"state": "waiting", "by": "the world queue", "at": _now(),
                    "note": "made from the world list; every check passed" + (" (straightened by a person)" if st.get("straightened") else "")
                            + (" (let through by a person)" if st.get("let_through") else "")}}
    _write(tdir / f"{tid}.json", t)
    return tid


# ------------------------------------------------------------------------------------------------ the loop
def run(cfg: dict | None, gid: str, once: bool = False, until_empty: bool = False, poll: float = 60.0, art_url: str | None = None,
        env=None, blender_python=None, use_lock: bool = True, max_items: int | None = None, check_machine: bool = True,
        local_out: Path | None = None) -> dict:
    """The launcher's loop: the next thing, made, checked, reported — until stopped (STOP, Ctrl+C or closing the window),
    or, with `until_empty`, until nothing is left to make. Returns {"made", "held", "failed", "stopped_by"}."""
    wd = world_dir(cfg, gid)
    wd.mkdir(parents=True, exist_ok=True)
    h = logging.FileHandler(wd / "world.log", encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"))
    lg = logging.getLogger("forge.threed")
    lg.addHandler(h)
    if lg.level == logging.NOTSET or lg.level > logging.INFO:
        lg.setLevel(logging.INFO)
    if env is None:
        from .env import from_cfg
        env = from_cfg(cfg)
    blender_python = blender_python_of(cfg, blender_python)
    tally = {"made": 0, "held": 0, "failed": 0, "stopped_by": None}
    told_wait, told_idle = "", False
    _clear_stop(cfg, gid)
    try:
        with _Beat(cfg, gid) as beat:
            log.info("==== the world queue for %s started (pid %d) ====", gid, os.getpid())
            while True:
                if _stop_asked(cfg, gid):
                    tally["stopped_by"] = "asked"
                    log.info("stopped, as asked (STOP)")
                    _clear_stop(cfg, gid)
                    break
                items, problems = merged(cfg, gid)
                for p in problems:
                    if p not in getattr(run, "_said", set()):
                        log.warning("the list: %s", p)
                        run._said = getattr(run, "_said", set()) | {p}
                e = next_item(items)
                if e is None:
                    if once or until_empty:
                        tally["stopped_by"] = "nothing left"
                        log.info("nothing left to make")
                        break
                    if not told_idle:
                        log.info("nothing to make — waiting for the list to grow (adding an entry is enough)")
                        told_idle = True
                    beat.set(step="waiting for the list to grow", item=None, waiting="")
                    time.sleep(poll)
                    continue
                told_idle = False
                if check_machine and needs_card(e):
                    busy = machine_busy(cfg, art_url)
                    if busy:
                        if busy != told_wait:
                            log.info("waiting before %s: %s", e["id"], busy)
                            told_wait = busy
                        beat.set(step="waiting for the machine", item=e["id"], waiting=busy)
                        if once:
                            tally["stopped_by"] = "busy"
                            break
                        time.sleep(poll)
                        continue
                told_wait = ""
                beat.set(step="making", item=e["id"], waiting="")
                st = make(cfg, gid, e, art_url=art_url, env=env, blender_python=blender_python, use_lock=use_lock, beat=beat,
                          local_out=local_out)
                tally[st["state"] if st["state"] in tally else "failed"] += 1
                write_report(cfg, gid)
                if once or (max_items and sum(tally[k] for k in ("made", "held", "failed")) >= max_items):
                    tally["stopped_by"] = "once" if once else "max_items"
                    break
    except KeyboardInterrupt:
        tally["stopped_by"] = "ctrl+c"
        log.info("stopped with Ctrl+C — the item in hand is taken up first next time")
    finally:
        try:
            write_report(cfg, gid)
        except Exception:  # noqa: BLE001
            pass
        lg.removeHandler(h)
        h.close()
    return tally


# ------------------------------------------------------------------------------------------------ what a person sees
def route_of(e: dict) -> str:
    """How long a thing takes depends on how it is made: adopting a model made earlier or damaging an intact one takes
    seconds ('quick'); everything else by its kind."""
    return "quick" if (e.get("adopt") or e.get("wreck_of")) else e["kind"]


def speeds(cfg: dict | None, gid: str, items: list[dict] | None = None) -> dict:
    """Seconds per thing, by how it is made: today's when anything was made today, else the last week's, else first guesses."""
    items = items if items is not None else merged(cfg, gid)[0]
    today = datetime.now().strftime("%Y-%m-%d")
    by_day: dict[str, list] = {}
    week: dict[str, list] = {}
    for e in items:
        rk = route_of(e)
        for hst in e["st"].get("history") or []:
            if hst.get("state") not in ("made", "held") or not hst.get("seconds") or rk == "panel":
                continue
            at = str(hst.get("at") or "")
            if at.startswith(today):
                by_day.setdefault(rk, []).append(hst["seconds"])
            try:
                if (datetime.now() - datetime.fromisoformat(at)).days <= 7:
                    week.setdefault(rk, []).append(hst["seconds"])
            except ValueError:
                pass
    out = {}
    for k in tuple(KINDS) + ("quick",):
        if by_day.get(k):
            out[k] = {"seconds": sum(by_day[k]) / len(by_day[k]), "basis": "today's speed", "n": len(by_day[k])}
        elif week.get(k):
            out[k] = {"seconds": sum(week[k]) / len(week[k]), "basis": "this week's speed", "n": len(week[k])}
        else:
            out[k] = {"seconds": float(FIRST_GUESS[k]), "basis": "a first guess", "n": 0}
    return out


def words_for(seconds: float) -> str:
    if seconds < 90:
        return f"about {max(1, round(seconds / 60))} minute"
    if seconds < 3600:
        return f"about {round(seconds / 60)} minutes"
    return f"about {seconds / 3600:.1f} hours"


def estimate(cfg: dict | None, gid: str, items: list[dict] | None = None) -> dict:
    items = items if items is not None else merged(cfg, gid)[0]
    sp = speeds(cfg, gid, items)
    todo = [e for e in items if e["state"] in ("wanted", "making") and not e["hold"]]
    per = {}
    for e in todo:
        per.setdefault(route_of(e), 0)
        per[route_of(e)] += 1
    secs = sum(sp[k]["seconds"] * n for k, n in per.items())
    basis = sorted({sp[k]["basis"] for k in per}) or ["-"]
    return {"to_make": len(todo), "per_kind": per, "seconds": round(secs), "words": words_for(secs) if todo else "nothing to make",
            "basis": " / ".join(basis), "speeds": {k: round(v["seconds"]) for k, v in sp.items()}}


def status(cfg: dict | None, gid: str) -> dict:
    items, problems = merged(cfg, gid)
    counts: dict[str, int] = {}
    for e in items:
        counts[e["shown"]] = counts.get(e["shown"], 0) + 1
    nxt = next_item(items)
    view = []
    for e in items:
        st = e["st"]
        view.append({"id": e["id"], "kind": e["kind"], "tier": e["tier"], "words": e["words"], "first": e["first"],
                     "rank": e["rank"], "hold": e["hold"], "state": e["state"], "shown": e["shown"], "changed": e["changed"],
                     "size": e["real_size_m"], "file": e["_file"], "why": st.get("why") or [], "error": st.get("error"),
                     "checks": st.get("checks") or [], "check_picture": st.get("check_picture"), "model": st.get("model"),
                     "picture": st.get("picture"), "seconds": st.get("seconds"), "finished": st.get("finished"),
                     "tries": st.get("tries"), "try": st.get("try"), "notes": st.get("notes") or [], "adopted": bool(e.get("adopt")),
                     "straighten": next((r.get("straighten") for r in st.get("check_results") or [] if r.get("check") == "level"
                                         and not r.get("ok")), None),
                     "colour_offer": st.get("colour_offer"), "colour_picture": st.get("colour_picture"),
                     "put_right": st.get("put_right") or [], "as_made": st.get("model_as_made"),
                     "held_by": st.get("held_by"), "gate": st.get("gate"), "gate_override": st.get("gate_override"),
                     "flame": bool(e.get("flame")), "glow": bool(e.get("glow")),
                     "motion_note": st.get("motion_note"),
                     "next": bool(nxt and nxt["id"] == e["id"])})
    rep = world_dir(cfg, gid) / "world.log"
    tail = ""
    if rep.exists():
        try:
            with open(rep, "rb") as f:
                f.seek(max(0, rep.stat().st_size - 6000))
                tail = "\n".join(f.read().decode("utf-8", "replace").splitlines()[-25:])
        except OSError:
            pass
    return {"game": gid, "launcher": launcher_state(cfg, gid), "counts": counts, "items": view, "problems": problems,
            "estimate": estimate(cfg, gid, items), "tiers": tiers(cfg, gid), "next": nxt["id"] if nxt else None, "log": tail,
            "list_dir": _rel(cfg, list_dir(cfg, gid)), "stop_asked": _stop_asked(cfg, gid)}


def write_report(cfg: dict | None, gid: str) -> Path:
    s = status(cfg, gid)
    est = s["estimate"]
    lines = [f"The world list for {gid} — {_now()}",
             "  " + ", ".join(f"{n} {k}" for k, n in sorted(s["counts"].items())),
             f"  still to make: {est['to_make']} — {est['words']} at {est['basis']}", ""]
    done = sorted((i for i in s["items"] if i.get("finished")), key=lambda i: i["finished"] or "", reverse=True)
    for i in done[:60]:
        lines.append(f"  {i['shown'].upper():<12} {i['id']:<28} {i['kind']:<8} {i['finished']}  "
                     + ("; ".join(i["why"])[:200] if i["why"] else (i.get("error") or "")[:200]))
    if s["problems"]:
        lines += ["", "Problems in the list:"] + [f"  - {p}" for p in s["problems"]]
    p = world_dir(cfg, gid) / "REPORT.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# ------------------------------------------------------------------------------------------------ a person's actions
def add_entry(cfg: dict | None, gid: str, entry: dict, who: str = "") -> dict:
    """One entry as its own file (so two people adding at once never overwrite each other). Returns it."""
    e = normalise(entry, file="(new)")
    existing = {x["id"] for x in load(cfg, gid)[0]}
    if e["id"] in existing:
        raise WorldError(f"{e['id']} is already in the list")
    raw = {k: v for k, v in entry.items() if not str(k).startswith("_")}
    raw["id"] = e["id"]
    raw.setdefault("added", {"by": who or "someone", "at": _now()})
    _write(list_dir(cfg, gid) / f"{e['id']}.json", raw)
    return e


def _entry_file(cfg, gid, eid: str) -> tuple[Path, dict, int | None]:
    for p in sorted(x for x in list_dir(cfg, gid).glob("*.json") if not x.name.startswith("_")):
        data = _read(p, None)
        if isinstance(data, dict) and "entries" in data:
            for k, raw in enumerate(data["entries"]):
                if isinstance(raw, dict) and slug(raw.get("id")) == eid:
                    return p, data, k
        elif isinstance(data, list):
            for k, raw in enumerate(data):
                if isinstance(raw, dict) and slug(raw.get("id")) == eid:
                    return p, data, k
        elif isinstance(data, dict) and slug(data.get("id")) == eid:
            return p, data, None
    raise WorldError(f"{eid} is not in the list")


def set_fields(cfg: dict | None, gid: str, eid: str, fields: dict) -> None:
    """Change a person's fields of one entry where it lives (hold, rank, first, words, size ...)."""
    p, data, k = _entry_file(cfg, gid, eid)
    target = data if k is None else (data["entries"][k] if isinstance(data, dict) else data[k])
    for f, v in fields.items():
        if f in ("id", "_file", "_seq", "_mtime"):
            continue
        if v is None:
            target.pop(f, None)
        else:
            target[f] = v
    normalise(target, data.get("defaults") if isinstance(data, dict) else None, p.name)      # still a valid entry
    _write(p, data)


def make_again(cfg: dict | None, gid: str, eid: str, who: str = "") -> dict:
    """Forget what was made (the folder is kept, renamed) and put the thing back in the queue with a fresh picture."""
    st = read_state(cfg, gid, eid)
    d = item_dir(cfg, gid, eid)
    if d.exists():
        os.replace(d, d.with_name(f"{eid}__try{int(st.get('tries') or 1)}_{datetime.now():%m%d%H%M%S}"))
    hist = list(st.get("history") or [])
    hist.append({"at": _now(), "state": "make again", "by": who})
    write_state(cfg, gid, eid, {"state": "wanted", "tries": int(st.get("tries") or 0), "history": hist[-20:],
                                "previous": {k: st.get(k) for k in ("state", "why", "error", "model", "finished")}})
    return {"ok": True, "message": f"{eid} is back in the queue; it gets a fresh picture."}


def gate_anyway(cfg: dict | None, gid: str, eid: str, who: str, pick: int | None = None) -> dict:
    """A person overrules the picture gate: the body is made from one of the tries (the last one unless `pick` names
    another). The thing goes back in the queue keeping its folder, so the picture is not painted again."""
    if not who:
        raise WorldError("say who you are first")
    st = read_state(cfg, gid, eid)
    if st.get("state") != "held" or st.get("held_by") != "picture gate":
        raise WorldError(f"{eid} is not held by the picture gate")
    out = item_dir(cfg, gid, eid)
    tries = (st.get("gate") or {}).get("tries") or []
    if not tries:
        raise WorldError("there are no tries to pick from")
    t = next((x for x in tries if x["try"] == int(pick)), None) if pick not in (None, "") else tries[-1]
    if t is None:
        raise WorldError(f"there is no try {pick}")
    src = root_of(cfg) / t["picture"]
    if not src.exists():
        raise WorldError(f"the picture of try {t['try']} is not there any more")
    import shutil
    shutil.copyfile(src, out / "pictures" / f"{eid}.png")
    rec_p = out / "pictures" / f"{eid}.gate.json"
    rec = _read(rec_p, {})
    rec.update(held=False, overruled={"by": who, "at": _now(), "try": t["try"]})
    _write(rec_p, rec)
    hist = list(st.get("history") or [])
    hist.append({"at": _now(), "state": f"picture gate overruled (try {t['try']})", "by": who})
    write_state(cfg, gid, eid, {"state": "wanted", "tries": int(st.get("tries") or 1), "history": hist[-20:],
                                "gate_override": {"by": who, "at": _now(), "try": t["try"]},
                                "previous": {k: st.get(k) for k in ("state", "why", "held_by")}})
    return {"ok": True, "message": f"{eid} is back in the queue; its body will be made from picture try {t['try']} as it is."}


def let_through(cfg: dict | None, gid: str, eid: str, who: str, env=None, blender_python=None) -> dict:
    """A person overrules the checks for a held thing: it is sized and goes to Review & approve as it is."""
    entries = {e["id"]: e for e in load(cfg, gid)[0]}
    if eid not in entries:
        raise WorldError(f"{eid} is not in the list")
    e, st = entries[eid], read_state(cfg, gid, eid)
    if st.get("state") != "held":
        raise WorldError(f"{eid} is not held back")
    out = item_dir(cfg, gid, eid)
    blender_python = blender_python_of(cfg, blender_python)
    if e["kind"] == "body":
        if not st.get("model") or not (root_of(cfg) / st["model"]).exists():
            raise WorldError("a held body has no skeleton or motions yet — make it again, or take it to Skeleton & motions")
        final = {}
    else:
        raw = root_of(cfg) / st["model_raw"]
        final = place_final(cfg, e, raw, out, env=env, blender_python=blender_python)
    st.update(final, state="made", let_through={"by": who, "at": _now()})
    st.setdefault("history", []).append({"at": _now(), "state": "let through", "by": who})
    st["try"] = to_review(cfg, gid, e, st)
    write_state(cfg, gid, eid, st)
    _item_report(out, e, st)
    return {"ok": True, "message": f"{eid} is in Art → Review & approve; its checks are shown with it."}


def use_colours(cfg: dict | None, gid: str, eid: str, who: str, env=None, blender_python=None) -> dict:
    """A person chooses the matched colours for a thing held for its colours (BUILD 40): the matched version is checked
    again and, if everything passes, sized and sent on. The model as made stays beside it."""
    entries = {e["id"]: e for e in load(cfg, gid)[0]}
    if eid not in entries:
        raise WorldError(f"{eid} is not in the list")
    e, st = entries[eid], read_state(cfg, gid, eid)
    if st.get("state") != "held" or not st.get("colour_offer"):
        raise WorldError(f"{eid} is not held with matched colours to choose")
    out = item_dir(cfg, gid, eid)
    blender_python = blender_python_of(cfg, blender_python)
    cur = root_of(cfg) / st["colour_offer"]
    pic = root_of(cfg) / st["picture"] if st.get("picture") else None
    res = checks.run(cur, pic, e["kind"], e["tier"], cfg, out_picture=out / "checks.png")
    note = "Colours hold: matched to the picture — chosen by a person (the model as made is kept beside it)."
    res["lines"] = [note] + res["lines"]
    _write(out / "checks.json", res)
    st.update(checks=res["lines"], check_results=res["results"], model_as_made=st.get("model_raw"), model_raw=_rel(cfg, cur),
              colour_chosen={"by": who, "at": _now()}, colour_offer=None)
    st.setdefault("history", []).append({"at": _now(), "state": "colours matched", "by": who})
    others = [r for r in res["results"] if not r["ok"] and r.get("check") != "level"]
    lvl = next((r for r in res["results"] if r.get("check") == "level" and not r["ok"]), None)
    if others or lvl:
        st["why"] = [r["line"] for r in res["results"] if not r["ok"]]
        write_state(cfg, gid, eid, st)
        _item_report(out, e, st)
        return {"ok": False, "message": "Colours matched, but something else still holds it back: " + " ".join(st["why"])}
    if e["kind"] == "body":
        st.update(state="held", why=["Colours matched: make it again from Skeleton & motions to fit its motions to the matched body."])
        write_state(cfg, gid, eid, st)
        return {"ok": True, "message": "Colours matched; the body needs its skeleton and motions fitted again."}
    final = place_final(cfg, e, cur, out, env=env, blender_python=blender_python)
    st.update(final, state="made", why=[])
    st["try"] = to_review(cfg, gid, e, st)
    write_state(cfg, gid, eid, st)
    _item_report(out, e, st)
    return {"ok": True, "message": "The matched colours are in; every check passes now — it's in Art → Review & approve."}


def straighten(cfg: dict | None, gid: str, eid: str, who: str, env=None, blender_python=None) -> dict:
    """A thing held back only for leaning: turned level, checked again, and sent on if everything else passed."""
    entries = {e["id"]: e for e in load(cfg, gid)[0]}
    if eid not in entries:
        raise WorldError(f"{eid} is not in the list")
    e, st = entries[eid], read_state(cfg, gid, eid)
    lvl = next((r for r in st.get("check_results") or [] if r.get("check") == "level"), None)
    if st.get("state") != "held" or not lvl or lvl.get("ok"):
        raise WorldError(f"{eid} is not held back for leaning")
    out = item_dir(cfg, gid, eid)
    blender_python = blender_python_of(cfg, blender_python)
    raw = root_of(cfg) / st["model_raw"]
    from . import meshio
    level_glb = out / f"{eid}__level.glb"
    meshio.place(raw, level_glb, size=None, rotation=lvl["straighten"], centre=False, floor=False)
    pic = root_of(cfg) / st["picture"] if st.get("picture") else None
    res = checks.run(level_glb, pic, e["kind"], e["tier"], cfg, out_picture=out / "checks.png")
    _write(out / "checks.json", res)
    st.update(checks=res["lines"], check_results=res["results"], model_raw=_rel(cfg, level_glb),
              check_picture=_rel(cfg, Path(res["picture"])) if res.get("picture") else None)
    st.setdefault("history", []).append({"at": _now(), "state": "straightened", "by": who, "by_deg": lvl.get("tilt_deg")})
    if not res["ok"]:
        st["why"] = [r["line"] for r in res["results"] if not r["ok"]]
        write_state(cfg, gid, eid, st)
        _item_report(out, e, st)
        return {"ok": False, "message": f"Straightened ({lvl.get('tilt_deg')}°), but something else still holds it back: " + " ".join(st["why"])}
    final = place_final(cfg, e, level_glb, out, env=env, blender_python=blender_python)
    st.update(final, state="made", straightened=True, why=[])
    st["try"] = to_review(cfg, gid, e, st)
    write_state(cfg, gid, eid, st)
    _item_report(out, e, st)
    return {"ok": True, "message": f"Straightened by {lvl.get('tilt_deg')}°; every check passes now — it's in Art → Review & approve."}
