"""The example game's adapter — and the model for writing one for a real game.

The suite knows places, lines, quests, music slots and people; this file says where they are in *this* game's
files. Copy it to games/<your game>/workbench_adapter.py and change the paths and field names. Keep it to reading:
writing always goes through the suite's safe-save path, by ref (file + JSON pointer).
"""
from __future__ import annotations
from pathlib import Path

from forge.suite.adapter import GameAdapter, Line, MusicSlot, Person, Place, Quest, Ref


class Adapter(GameAdapter):
    name = "Example game (made up)"
    data_globs = ("data/**/*.json",)
    validator = ("tools/validate.py", "--file")      # the game's own checker; run on a temp copy before any save

    def places(self) -> list[Place]:
        out = []
        for rel in self.data_files():
            if not rel.startswith("data/places/"):
                continue
            d = self.load(rel)
            st, by = self.status_of(d)
            out.append(Place(id=d["id"], name=d.get("name", d["id"]), ref=Ref(rel, ""), kind=d.get("kind", "town"),
                             eras=list(d.get("eras") or []), status=st, approved_by=by, summary=d.get("summary", "")))
        return out

    def place_greeting(self, place, era):
        """For the read-through's sameness meter: the greeting this place's people use (data/places/<id>.json)."""
        for rel in self.data_files():
            if rel.startswith("data/places/") and self.load(rel).get("id") == place:
                return self.load(rel).get("greeting")
        return None

    def lines(self, place: str | None = None) -> list[Line]:
        out = []
        for rel in self.data_files():
            if not rel.startswith("data/dialogue/"):
                continue
            d = self.load(rel)
            for i, l in enumerate(d.get("lines") or []):
                pl = l.get("place") or d.get("place")
                if place and pl != place:
                    continue
                st, by = self.status_of(l)
                lyric = l.get("lyric")
                out.append(Line(ref=Ref(rel, f"/lines/{i}"), text=l.get("text", ""), who=l.get("who", ""), status=st,
                                approved_by=by, place=pl, era=l.get("era"), source=d.get("id", rel),
                                when="" if not l.get("if") else str(l["if"]), locked=bool(lyric),
                                lock_reason=f"a line of the song '{lyric}'" if lyric else ""))
        return out

    def locked(self, rel: str, pointer: str) -> str | None:
        why = super().locked(rel, pointer)
        if why:
            return why
        parts = pointer.strip("/").split("/")
        if rel.startswith("data/dialogue/") and len(parts) >= 3 and parts[0] == "lines" and parts[2] == "text":
            l = (self.load(rel).get("lines") or [])[int(parts[1])]
            if l.get("lyric"):
                return f"a line of the song '{l['lyric']}' — a song's own words are never edited here"
        return None

    def quests(self) -> list[Quest]:
        rel = "data/quests.json"
        out = []
        for k, q in self.load(rel).items():
            st, by = self.status_of(q)
            out.append(Quest(id=k, title=q.get("title", k), ref=Ref(rel, "/" + k), place=q.get("place"), era=q.get("era"),
                             giver=q.get("giver"), status=st, approved_by=by, steps=list(q.get("steps") or [])))
        return out

    def music_slots(self) -> list[MusicSlot]:
        rel = "data/music.json"
        out = []
        for k, m in self.load(rel).items():
            f = m.get("file")
            exists = bool(f) and (self.root / f).is_file()
            plays = list(m.get("plays") or [])           # where the game plays it; a track nobody wired isn't "in game" yet
            out.append(MusicSlot(id=k, ref=Ref(rel, "/" + k), purpose=m.get("purpose", ""), file=f, file_exists=exists,
                                 vocal=m.get("vocal"), status="in game" if exists and plays else "needed", scene=m.get("scene", k),
                                 kind="song" if m.get("vocal") else "theme", place=m.get("place"), era=m.get("era"),
                                 singers=[{"name": n, "voice": "", "source": "data/music.json"} for n in m.get("singers") or []],
                                 track=k))
        return out

    def music_set_file(self, slot, rel, who, loop_start=None, loop_end=None, trim_db=None):
        """A delivered track: data/music.json points at it (and keeps its loop points and trim) — through the safe path."""
        from forge.suite import safesave
        k = slot["id"]
        changes = [("put", f"/{k}/file", rel)]
        for field, v in (("loop_start", loop_start), ("loop_end", loop_end), ("trim_db", trim_db)):
            if v is not None:
                changes.append(("put", f"/{k}/{field}", float(v)))
        r = safesave.edit(self, "data/music.json", changes, who, reason=f"music delivered for {k}", kind="music")
        return "data/music.json updated" if r.get("ok") else "data/music.json NOT updated: " + "; ".join(r.get("refused") or ["conflict"])

    def people(self) -> list[Person]:
        rel = "data/characters.json"
        return [Person(id=k, name=c.get("name", k), ref=Ref(rel, "/" + k), kind=c.get("kind", ""), voice=c.get("voice", ""),
                       sheet=c.get("sheet"), portrait=c.get("portrait")) for k, c in self.load(rel).items()]
