"""The adapter contract — the only place that knows one game's file shapes.

The suite itself knows six things and nothing about any particular game: **places** (a town, a district, a dungeon),
**lines** (anything a character says or a caption shows), **quests**, **music slots**, **people**, and **status**
(draft / approved / flagged, and who approved). Each game supplies `games/<id>/workbench_adapter.py` with a class
`Adapter(GameAdapter)` that says where its data files are and how to read those six things out of them. A second game
needs a new folder and adapter, and no change to forge code.

Every object carries a **ref**: the data file (relative to the game folder, forward slashes) and a JSON pointer to
the object inside it — `data/dialogue/keeper.json#/lines/2`. Edits go through `safesave` by ref; the suite never
keeps a copy of a game's content.

Contract version 1 (BUILD 01): data files, validation, the six kinds read-only. Editing screens (BUILD 07) use refs.
BUILD 06 added the music hooks (all optional, with defaults): music_paths, deliver_target, music_set_file, lyric_target,
local_file, owner — see forge/suite/music.py.
"""
from __future__ import annotations
import json, subprocess, sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .jsondoc import JsonDoc, JsonDocError, TextDoc, join_pointer

CONTRACT = 1
STATUSES = ("draft", "approved", "flagged")


@dataclass
class Ref:
    file: str                       # relative to the game folder, forward slashes
    pointer: str = ""               # RFC 6901 inside the file; "" = the whole file

    def __str__(self) -> str:
        return f"{self.file}#{self.pointer}"

    @classmethod
    def parse(cls, s: str) -> "Ref":
        f, _, p = str(s).partition("#")
        return cls(f, p)


@dataclass
class Place:
    id: str
    name: str
    ref: Ref
    kind: str = "town"
    eras: list = field(default_factory=list)
    status: str | None = None
    approved_by: str | None = None
    dev: bool = False               # a test/dev place the player never sees
    maps: list = field(default_factory=list)
    summary: str = ""


@dataclass
class Line:
    ref: Ref                        # the line object
    text: str
    who: str = ""
    status: str | None = None
    approved_by: str | None = None
    place: str | None = None        # place id
    era: str | None = None
    when: str = ""                  # its conditions, in plain words if the adapter can, else raw
    source: str = ""                # which conversation / cue it belongs to
    text_field: str = "text"        # the field of the line object that holds the words
    locked: bool = False            # a song's own words — never edited in the suite
    lock_reason: str = ""


@dataclass
class Quest:
    id: str
    title: str
    ref: Ref
    place: str | None = None
    era: str | None = None
    giver: str | None = None
    status: str | None = None
    approved_by: str | None = None
    steps: list = field(default_factory=list)


@dataclass
class MusicSlot:
    id: str
    ref: Ref
    purpose: str = ""
    file: str | None = None         # what the game plays (its own path form)
    file_exists: bool = False
    vocal: bool | None = None
    status: str = "needed"          # what the game itself says: needed | written (the song exists) | in game | inherits
    scene: str = ""                 # where it plays, in words
    kind: str = ""                  # the game's own word for the kind of slot (a town theme, a boss, a song …)
    place: str | None = None        # place id
    era: str | None = None
    singers: list = field(default_factory=list)   # [{name, voice, source}] — voice "ask" where nobody wrote it down
    track: str | None = None        # the game's id for the music it plays here (slots sharing a track are one piece of work)
    game_word: str = ""             # the game's own status word, shown beside the chip


@dataclass
class Person:
    id: str
    name: str
    ref: Ref
    kind: str = ""
    voice: str = ""
    sheet: str | None = None
    portrait: str | None = None


def as_dict(obj) -> dict:
    d = asdict(obj)
    if isinstance(getattr(obj, "ref", None), Ref):
        d["ref"] = str(obj.ref)
    return d


class AdapterError(RuntimeError):
    pass


class GameAdapter:
    """Base class. A game's adapter overrides `data_globs`, the six readers and (if it has one) `validate`."""

    contract = CONTRACT
    name = "A game"
    data_globs: tuple = ("data/**/*.json",)
    locked_globs: tuple = ()        # data files the suite must never write (e.g. lyric sheets)
    validator: tuple | None = None  # (python script relative to the game folder, "--file") — see validate()

    def __init__(self, game_id: str, game_root: Path, game_cfg: dict | None = None):
        self.id = game_id
        self.root = Path(game_root)
        self.cfg = game_cfg or {}
        self._cache: dict[str, tuple[float, int, object]] = {}

    # ---------- files
    def data_files(self) -> list[str]:
        """Every data file, relative to the game folder. The listing is cached for a few seconds (globbing a large
        game over a network drive is the slow part of every screen)."""
        import time as _t
        hit = getattr(self, "_files_cache", None)
        if hit and _t.time() - hit[0] < 5.0:
            return list(hit[1])
        seen = set()
        for g in self.data_globs:
            for p in self.root.glob(g):
                if p.is_file() and "_workbench" not in p.parts:
                    seen.add(p.relative_to(self.root).as_posix())
        self._files_cache = (_t.time(), sorted(seen))
        return sorted(seen)

    def is_locked_file(self, rel: str) -> bool:
        from fnmatch import fnmatch
        return any(fnmatch(rel, g) for g in self.locked_globs)

    def locked(self, rel: str, pointer: str) -> str | None:
        """Why the field at rel#pointer must never be edited here, or None. Base: locked files. Adapters add lines
        (a song's own words) by overriding and calling super()."""
        if self.is_locked_file(rel):
            return f"{rel} is never written by the suite"
        return None

    def path(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        root = self.root.resolve()
        if root not in p.parents:
            raise AdapterError(f"{rel} is outside the game folder")
        return p

    def read_doc(self, rel: str):
        data = self.path(rel).read_bytes()
        return JsonDoc.from_bytes(data) if rel.lower().endswith(".json") else TextDoc.from_bytes(data)

    def load(self, rel: str):
        """The parsed value of a JSON data file, cached until the file changes on disk."""
        p = self.path(rel)
        st = p.stat()
        hit = self._cache.get(rel)
        if hit and hit[0] == st.st_mtime and hit[1] == st.st_size:
            return hit[2]
        v = json.loads(p.read_text(encoding="utf-8-sig"))
        self._cache[rel] = (st.st_mtime, st.st_size, v)
        return v

    # ---------- validation (the safe-save path calls this on a temp copy before anything is replaced)
    def validate(self, rel: str, temp_path: Path) -> list[str]:
        """Problems with the new version of `rel`, written at `temp_path` (same file name, inside a folder of the
        same name as rel's own folder). Default: it must read as JSON. With `validator` set, the game's own checker
        runs too: python <script> --file <temp_path>; exit 0 = fine, else the lines it printed are the problems."""
        problems: list[str] = []
        if rel.lower().endswith(".json"):
            try:
                JsonDoc.from_bytes(Path(temp_path).read_bytes())
            except JsonDocError as e:
                return [f"{rel}: {e}"]
        if self.validator:
            script, flag = self.validator
            sp = self.root / script
            if not sp.exists():
                return [f"the game's checker {script} is missing — nothing was saved"]
            try:
                r = subprocess.run([sys.executable, str(sp), flag, str(temp_path)], cwd=str(sp.parent),
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
            except subprocess.TimeoutExpired:
                return ["the game's checker took over a minute — nothing was saved"]
            if r.returncode != 0:
                out = [l.strip() for l in (r.stdout + "\n" + r.stderr).splitlines() if l.strip()]
                out = [l[len("PROBLEM:"):].strip() if l.startswith("PROBLEM:") else l for l in out]
                problems += [l for l in out if not l.endswith("problems") and l != "OK"] or [f"the game's checker said no (exit {r.returncode})"]
        return problems

    # ---------- the six kinds (override)
    def places(self) -> list[Place]:
        return []

    def lines(self, place: str | None = None) -> list[Line]:
        return []

    def quests(self) -> list[Quest]:
        return []

    def music_slots(self) -> list[MusicSlot]:
        return []

    def people(self) -> list[Person]:
        return []

    # ---------- music (BUILD 06): where the board, sheets, briefs, songs and inbox live; where a delivered track goes
    @property
    def owner(self) -> str:
        """Who briefs and finished songs are sent to: forge.game.json "owner"."""
        return str(self.cfg.get("owner") or "the owner")

    def music_paths(self) -> dict:
        """Folders (relative to the game folder) for the Music board's record, the style sheets, briefs, song drafts,
        the score inbox and delivered audio with no file name of its own. Override to move any of them."""
        return {"board": "music/board.json", "styles": "music/styles", "songs": "music/songs", "briefs": "music/briefs",
                "inbox": "score_inbox", "audio": "music/audio"}

    def deliver_target(self, slot: dict, ext: str) -> str | None:
        """Where a track dropped on `slot` is copied (relative to the game folder). Base: the slot's own file path with the
        dropped file's extension; None → music/audio/<slot>.<ext>."""
        f = slot.get("file")
        if f and "://" not in str(f) and not str(f).startswith("/") and ":" not in str(f):
            from pathlib import PurePosixPath
            return PurePosixPath(str(f)).with_suffix(ext).as_posix()
        return None

    def music_set_file(self, slot: dict, rel: str, who: str, loop_start=None, loop_end=None, trim_db=None) -> str | None:
        """Point the game's music data at a delivered file (and its loop points / volume trim), through the safe-save
        path. Base: nothing — the board alone records the delivery. Returns a few words on what changed, or None."""
        return None

    def lyric_target(self, slot: dict, title: str) -> str | None:
        """Where the words as delivered are filed (a new file; never overwritten). None → music/songs/<slot>/as_delivered.txt."""
        return None

    def local_file(self, slot: dict):
        """The audio file the game plays for a slot, as a path on this PC (for the play button), or None."""
        f = slot.get("file")
        if f and "://" not in str(f):
            p = self.root / str(f)
            return p if p.is_file() else None
        return None

    # ---------- helpers for adapters and screens
    @staticmethod
    def status_of(obj: dict) -> tuple[str | None, str | None]:
        if not isinstance(obj, dict):
            return None, None
        st = obj.get("status")
        if st is None and obj.get("draft") is True:
            st = "draft"
        return (st if st in STATUSES else (str(st) if st else None)), (obj.get("approved_by") or None)

    def summary(self) -> dict:
        """Counts for the game picker and the Story side. Never raises: a broken reader shows as an error line."""
        out: dict = {"id": self.id, "name": self.name, "root": str(self.root), "root_exists": self.root.is_dir(),
                     "contract": self.contract, "errors": []}
        if not out["root_exists"]:
            out["errors"].append(f"the game folder {self.root} is not reachable from this PC")
            return out
        try:
            out["data_files"] = len(self.data_files())
        except Exception as e:  # noqa: BLE001
            out["errors"].append(f"data files: {e}")
        for kind, fn in (("places", self.places), ("lines", self.lines), ("quests", self.quests),
                         ("music_slots", self.music_slots), ("people", self.people)):
            try:
                items = fn()
            except Exception as e:  # noqa: BLE001
                out["errors"].append(f"{kind}: {type(e).__name__}: {e}")
                continue
            entry = {"count": len(items)}
            if items and not hasattr(items[0], "status"):
                out[kind] = entry
                continue
            sts = [getattr(i, "status", None) for i in items]
            counts: dict = {}
            for st in sts:
                counts[st or "none"] = counts.get(st or "none", 0) + 1
            if kind == "music_slots":
                counts = {k: counts[k] for k in ("needed", "written", "in game", "inherits") if k in counts}
            entry["by_status"] = counts
            if kind == "lines":
                entry["locked"] = sum(1 for i in items if i.locked)
            if kind == "places":
                entry["dev"] = sum(1 for i in items if i.dev)
            out[kind] = entry
        return out
