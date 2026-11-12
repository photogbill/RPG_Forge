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

    # ---- optional hooks for Status (BUILD 26): the build queue and the game's own completeness checklist
    def builds(self) -> list[dict]:
        """The game's build queue (Builds/BUILD_QUEUE.md, read by the suite's markdown reader)."""
        from forge.suite import buildqueue
        return buildqueue.read(self.root / "Builds" / "BUILD_QUEUE.md")

    def completeness(self) -> list[dict]:
        """The game's own checklist: [{item, have, of} or {item, met}]. Here: COMPLETENESS.json, written by the game's report."""
        import json
        p = self.root / "COMPLETENESS.json"
        if not p.is_file():
            return []
        return list(json.loads(p.read_text(encoding="utf-8")).get("items") or [])

    # ---- optional hooks for the Story workbench (BUILD 07b)
    def reactions(self, person_id: str) -> list[dict]:
        """A person's reactions (this example keeps none; a real game lists banter, barks, per-town reactions here):
        [{town, era, text, ref}]."""
        return []

    def play_command(self, place, era):
        """The command that starts the game at a place (and era). The example has no engine, so it only says where."""
        import sys
        return [sys.executable, "-c", f"print('the example game would start at {place} ({era or 'any era'})')"]

    # ---------- floor plans (BUILD 29) — the model for a game's layout hooks
    # A place may carry "layout": {"archetypes": {"war": [...], "after": [...]}, "size": "town", "terrain": "river"}
    # (the owner's assignment). Without one, a suggestion is read from the place's own words, and says so.
    _SUGGEST = (("toll", "toll_kingdom"), ("bridge", "toll_kingdom"), ("ledger", "ledger_town"), ("fire", "buried_town"))

    def town_sheets(self) -> list[dict]:
        out = []
        for rel in self.data_files():
            if not rel.startswith("data/places/"):
                continue
            d = self.load(rel)
            lay = d.get("layout") or {}
            words = f"{d.get('summary', '')} {d.get('greeting', '')}".lower()
            sug = [a for w, a in self._SUGGEST if w in words]
            sug = list(dict.fromkeys(sug))
            arch = {era: ({"ids": lay["archetypes"][era], "how": "assigned", "why": ["layout.archetypes"]}
                          if (lay.get("archetypes") or {}).get(era) else
                          {"ids": sug, "how": "suggested ◆", "why": [f"{a}: its summary says so" for a in sug]})
                    for era in ("war", "after")}
            req = [{"kind": "inn", "label": "INN"}, {"kind": "store", "label": "STORE"}]
            unknowns = [] if lay.get("terrain") else ["terrain: not on the sheet — laid out on open ground"]
            out.append({"id": d["id"], "name": d.get("name", d["id"]), "node": d["id"], "ref": rel,
                        "size": lay.get("size") or "town", "terrain": lay.get("terrain"),
                        "required_by_era": {"war": req, "after": req}, "tiers_by_era": {"war": {"weapon": 0, "armor": 0, "accessory": 0},
                                                                                    "after": {"weapon": 1, "armor": 1, "accessory": 1}},
                        "archetypes": arch, "maps": [], "unknowns": unknowns})
        return sorted(out, key=lambda s: s["id"])

    @staticmethod
    def sheet_for(sheet: dict, era: str) -> dict:
        s = dict(sheet)
        s["required"] = list(sheet["required_by_era"][era])
        s["tiers"] = dict(sheet["tiers_by_era"][era])
        return s

    def layout_check(self, maps: dict) -> list[str]:
        """This made-up game's map rules: known glyphs, a start spawn, doors that lead somewhere that exists."""
        from forge.layout.store import GLYPHS_INV
        out = []
        have = set(maps) | {p.stem for p in (self.root / "data" / "maps").glob("*.json")} if (self.root / "data" / "maps").is_dir() else set(maps)
        for mid, m in maps.items():
            if any(ch not in GLYPHS_INV for r in m["rows"] for ch in r):
                out.append(f"map {mid}: a glyph the game doesn't know")
            if not any(e.get("type") == "spawn" and e.get("name") == "start" for e in m["entities"]):
                out.append(f"map {mid}: no start spawn")
            for e in m["entities"]:
                if e.get("type") == "door" and e.get("to") != "travel" and e.get("to") not in have:
                    out.append(f"map {mid}: door {e.get('id')} -> {e.get('to')} does not exist")
        return out

    def layout_install(self, maps: dict, folder, who: str) -> list[str]:
        import json
        d = self.root / "data" / "maps"
        d.mkdir(parents=True, exist_ok=True)
        for mid, m in maps.items():
            p = d / f"{mid}.json"
            if p.exists() and json.loads(p.read_text(encoding="utf-8")).get("rows") != m["rows"]:
                raise ValueError(f"data/maps/{mid}.json already exists and is not this plan — not written over")
        done = []
        for mid, m in maps.items():
            p = d / f"{mid}.json"
            if not p.exists():
                p.write_text(json.dumps(m, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
                done.append(f"data/maps/{mid}.json")
        return done
