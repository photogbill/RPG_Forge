"""`python -m forge film …` — filming a set piece to its music (BUILD 43). The game's film folder is
<game_root>/film/<film>/ (game_root from games/<game>/forge.game.json): its tracks, beat maps, marks and cue sheets.
A game's `games/<game>/film_adapter.py` says which places can be shot and where its cast's bodies are.

    film beatmaps [--film opera] [--only <id>]        measure every track the film lists (tracks.json) → beats/
    film beatmap <audio> [--meter 4] [--bpm 76] [--out x.json]       one file, anywhere
    film check [--film opera] [<part> …]              every sheet checked; the report → film_check.txt in the film folder
    film timeline <part> [--film opera]               the renderer's timeline (seconds) → out/film/<game>/<film>/<part>/
    film conductor <part> [--film opera]              the conductor's track for a part, and its picture
    film clicks <part>                                a click on every beat of the part (a silent preview's metronome)
    film render <part> [--final] [--song] [--frames A-B] [--no-render]   stage the part in Blender (and render it)
    film encode <part> [--final] [--song]             the rendered frames → <part>.mp4 (the song window, muffled if asked)
    film video <heads|tails> [--final]                the parts of film.json, in order, joined into one film
    film refit <body id> […]                          fit a body with both motion libraries (UAL1 + UAL2) and the keyed
                                                      moves → <id>_moves_ual2.glb beside its own (never over it)
Nothing here uses the graphics card except a Blender render; nothing is written outside the forge and the game's film folder.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

from . import config as cfgmod


def _opt(args, flag, d=None):
    return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else d


def _positional(args, flags_with_value=("--film", "--game", "--meter", "--bpm", "--out", "--frames", "--only")):
    out, skip = [], False
    for i, a in enumerate(args):
        if skip:
            skip = False
            continue
        if a in flags_with_value:
            skip = True
            continue
        if a.startswith("--"):
            continue
        out.append(a)
    return out


class Film:
    """One film of one game: where everything is."""

    def __init__(self, cfg: dict, args: list):
        self.cfg = cfg
        self.game = _opt(args, "--game") or cfgmod.default_game(cfg)
        self.film = _opt(args, "--film", "opera")
        gcfg = cfgmod.game_config(cfg, self.game)
        root = gcfg.get("game_root")
        if not root:
            raise SystemExit(f"games/{self.game}/forge.game.json has no game_root: the film folder cannot be found")
        self.game_root = Path(root)
        self.dir = self.game_root / "film" / self.film
        self.out = cfgmod.path_of(cfg, "out") / "film" / self.game / self.film
        self.adapter = self._adapter()

    def _adapter(self):
        p = cfgmod.path_of(self.cfg, "games") / self.game / "film_adapter.py"
        if not p.exists():
            return None
        spec = importlib.util.spec_from_file_location(f"film_adapter_{self.game}", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def tracks(self) -> dict:
        return json.loads((self.dir / "tracks.json").read_text(encoding="utf-8"))

    def music(self, name: str) -> Path:
        md = self.tracks().get("music_dir", "project/assets/music")
        return self.game_root / md / name

    def sheet(self, part: str) -> dict:
        from .film import cuesheet
        p = self.dir / f"{part}.cues.json"
        if not p.exists():
            raise SystemExit(f"no cue sheet called {part} ({p})")
        return cuesheet.load(p)

    def parts(self) -> list[str]:
        return sorted(p.name[: -len(".cues.json")] for p in self.dir.glob("*.cues.json"))

    def marks(self, place: str):
        return self.adapter.marks(place, self.dir) if self.adapter else None

    def moves(self) -> set | None:
        from .threed import glb
        lib_dir = cfgmod.ROOT / "local" / "libraries" / "quaternius_ual"
        names: set = set()
        merged = lib_dir / "UAL1_UAL2_Standard.json"
        if merged.exists():
            names |= set(json.loads(merged.read_text(encoding="utf-8")).get("motions") or {})
        else:
            for g in sorted(lib_dir.glob("**/Unreal-Godot/UAL*_Standard.glb")):
                try:
                    names |= {n[:-len("_Armature")] if n.endswith("_Armature") else n for n in glb.info(g)["motions"]}
                except Exception:  # noqa: BLE001
                    pass
        if not names:
            return None                                    # no library here: moves are not checked
        km = Path(__file__).resolve().parent / "threed" / "blender" / "keyed_moves.json"
        names |= set(json.loads(km.read_text(encoding="utf-8"))["moves"])
        return names

    def part_out(self, part: str, mode: str = "") -> Path:
        p = self.out / part / mode if mode else self.out / part
        p.mkdir(parents=True, exist_ok=True)
        return p


# ------------------------------------------------------------------------------------------------------------ commands
def cmd_beatmaps(film: Film, only: str | None) -> int:
    from .film import beatmap
    tr = film.tracks()
    n = 0
    for t in tr["tracks"]:
        if not t.get("file") or (only and t["id"] != only):
            continue
        src = film.music(t["file"])
        if not src.exists():
            print(f"  {t['id']}: not on disk ({src})")
            continue
        bm = beatmap.analyse(src, meter=int(t.get("meter", 4)), bpm_hint=t.get("bpm_hint"), sections=t.get("sections"))
        out = film.dir / "beats" / (Path(t["file"]).stem + ".beats.json")
        beatmap.write(bm, out)
        beatmap.draw(beatmap.read(out), out.with_suffix(".png"), audio=src)
        n += 1
        print(f"  {t['id']}: {bm['tempo']['median_bpm']} BPM ({bm['tempo']['method']}), {len(bm['bars'])} bars, "
              f"steady within {bm['checks']['grid_ms_median']} ms → {out.name}")
    print(f"{n} beat maps written in {film.dir / 'beats'}")
    return 0


def _check_one(film: Film, part: str) -> tuple[list, list, str]:
    from .film import cuesheet
    sh = film.sheet(part)
    try:
        bm = cuesheet.beat_map_for(sh, film.dir)
    except cuesheet.SheetError as e:
        return [str(e)], [], "waits"
    marks = film.marks(sh.get("place") or "")
    if marks is None:
        return [], [f"the place '{sh.get('place')}' is not built yet: its marks cannot be checked"], "waits"
    errs, warns = cuesheet.check(sh, bm, marks or None, film.moves(), set(sh.get("singers") or []))
    return errs, warns, ("ok" if not errs else "errors")


def cmd_check(film: Film, parts: list[str]) -> int:
    parts = parts or film.parts()
    lines, bad = [], 0
    closeups = 0
    for part in parts:
        errs, warns, state = _check_one(film, part)
        sh = film.sheet(part)
        closeups += sum(1 for c in sh.get("camera") or [] if c.get("test_closeup"))
        lines.append(f"{part}: {state} — {len(errs)} to fix, {len(warns)} to look at")
        lines += [f"   fix   {e}" for e in errs] + [f"   look  {w}" for w in warns]
        bad += bool(errs)
    if closeups > 1:
        lines.append(f"the film has {closeups} test close-ups: it has one (✦ b43-faces)")
        bad += 1
    text = "\n".join(lines)
    (film.dir / "film_check.txt").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if bad else 0


def _timeline(film: Film, part: str) -> tuple[dict, dict, dict]:
    from .film import cuesheet
    sh = film.sheet(part)
    bm = cuesheet.beat_map_for(sh, film.dir)
    marks = film.marks(sh.get("place") or "") or {}
    tl = cuesheet.resolve(sh, bm, marks)
    tl["audio"] = str(film.music(sh["track"])) if sh.get("track") else None
    tl["muffled"] = bool(sh.get("muffled"))
    return sh, bm, tl


def cmd_timeline(film: Film, part: str) -> int:
    _sh, _bm, tl = _timeline(film, part)
    out = film.part_out(part) / "timeline.json"
    out.write_text(json.dumps(tl, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"timeline: {len(tl['tracks'])} people, {len(tl['camera'])} shots, {tl['from']:.2f}–{tl['to']:.2f} s → {out}")
    return 0


def cmd_conductor(film: Film, part: str) -> Path | None:
    from .film import conductor
    sh, bm, tl = _timeline(film, part)
    if not tl["conductor"] or not bm.get("beats"):
        print(f"{part}: no conductor here")
        return None
    track = conductor.make(bm, acting=tl["conductor"], fps=tl["fps"], start=tl["from"], end=tl["to"])
    probs = conductor.check(track, bm)
    out = film.part_out(part) / "conductor.json"
    conductor.write(track, out)
    conductor.draw(track, out.with_suffix(".png"), seconds=12, start=tl["from"] + 2.0)
    print(f"conductor: {len(track['ictus'])} beats conducted, {len(probs)} off their beat → {out}")
    for p in probs[:10]:
        print("   " + p)
    return out


def cmd_clicks(film: Film, part: str) -> int:
    from .film import encode
    _sh, bm, tl = _timeline(film, part)
    out = film.part_out(part) / "clicks.wav"
    encode.click_track(bm, out, tl["from"], tl["to"])
    print(f"clicks → {out}")
    return 0


def blender_exe(film: Film) -> str | None:
    exe = getattr(film.adapter, "BLENDER", None) if film.adapter else None
    t = (film.cfg.get("threed") or {}).get("blender_exe")
    for c in (exe, t, shutil.which("blender")):
        if c and Path(c).exists():
            return str(c)
    return None


def cmd_render(film: Film, part: str, final: bool, song: bool, frames: str | None, render: bool) -> int:
    sh, _bm, tl = _timeline(film, part)
    if film.adapter is None:
        print("this game has no film_adapter.py: nothing says where its places are")
        return 2
    place = film.adapter.places(film.dir).get(sh.get("place") or "")
    if not place or not Path(place["blend"]).exists():
        print(f"{part}: the place '{sh.get('place')}' is not built yet ({place and place['blend']})")
        return 2
    mode = "final" if final else "preview"
    out = film.part_out(part, mode)
    tlp = out / "timeline.json"
    tlp.write_text(json.dumps(tl, indent=1, ensure_ascii=False), encoding="utf-8")
    cast = {}
    for who, c in (tl.get("cast") or {}).items():
        f, why = film.adapter.body_file(c.get("body", ""))
        cast[who] = {**c, "file": f, "why": why}
    castp = out / "cast.json"
    castp.write_text(json.dumps(cast, indent=1, ensure_ascii=False), encoding="utf-8")
    cond = cmd_conductor(film, part)
    exe = blender_exe(film)
    if not exe:
        print("Blender was not found (set FORGE_BLENDER or forge.json threed.blender_exe)")
        return 2
    script = Path(film.adapter.SCENE_SCRIPT)
    cmd = [exe, "--background", str(place["blend"]), "--python", str(script), "--", "--timeline", str(tlp), "--cast", str(castp),
           "--out", str(out), "--forge", str(cfgmod.ROOT), "--" + mode]
    if song and tl.get("audio"):
        cmd += ["--audio", tl["audio"]]
    if cond:
        cmd += ["--conductor-track", str(cond)]
    cmd += ["--sfx-dir", str(film.dir / "sfx")]
    if frames:
        cmd += ["--frames", frames]
    if render:
        cmd += ["--render"]
    print("Blender:", " ".join(f'"{c}"' if " " in c else c for c in cmd))
    r = subprocess.run(cmd)
    return r.returncode


def cmd_encode(film: Film, part: str, final: bool, song: bool) -> int:
    from .film import encode
    _sh, _bm, tl = _timeline(film, part)
    mode = "final" if final else "preview"
    frames = film.part_out(part, mode) / "frames"
    out = film.part_out(part, mode) / f"{part}.mp4"
    audio = tl.get("audio") if song or final else None
    if not audio and not song and not final:
        clicks = film.part_out(part) / "clicks.wav"
        if clicks.exists():
            audio = str(clicks)
            r = encode.frames_to_film(frames, out, audio, tl["fps"], 0.0, tl["to"] - tl["from"], mode)
            print(json.dumps({k: v for k, v in r.items() if k != "cmd"}))
            return 0 if r.get("ok") else 1
    r = encode.frames_to_film(frames, out, audio, tl["fps"], tl["from"], tl["to"], mode, muffled=tl.get("muffled", False))
    print(json.dumps({k: v for k, v in r.items() if k != "cmd"}))
    return 0 if r.get("ok") else 1


def cmd_video(film: Film, side: str, final: bool) -> int:
    from .film import encode
    fj = json.loads((film.dir / "film.json").read_text(encoding="utf-8"))
    v = fj["videos"].get(side)
    if v is None:
        print(f"no video called {side} (film.json has {', '.join(fj['videos'])})")
        return 2
    mode = "final" if final else "preview"
    parts, waiting = [], []
    for s in fj["sequence"]:
        part = v["aria"] if s.get("by_video") else s["part"]
        if s.get("pending") or part == "credits":
            waiting.append(part if not s.get("pending") else f"{part} ({s['pending']})")
            continue
        f = film.out / part / mode / f"{part}.mp4"
        (parts if f.exists() else waiting).append(f if f.exists() else f"{part} (not rendered: {f})")
    print("joining: " + ", ".join(Path(p).stem for p in parts))
    for w in waiting:
        print("  left out: " + str(w))
    if not parts:
        return 1
    r = encode.join(parts, film.out / v["file"], mode)
    print(json.dumps({k: val for k, val in r.items() if k != "cmd"}))
    return 0 if r.get("ok") else 1


def cmd_refit(cfg: dict, film: Film, ids: list[str]) -> int:
    """Fit bodies with both libraries; the result goes beside the world queue's file, never over it."""
    from .threed import env as envmod, motions
    e = envmod.from_cfg(cfg)
    lib_dir = cfgmod.ROOT / "local" / "libraries" / "quaternius_ual"
    merged = lib_dir / "UAL1_UAL2_Standard.glb"
    if not merged.exists():
        srcs = [next(lib_dir.glob("Universal Animation Library[[]Standard[]]/Unreal-Godot/UAL1_Standard.glb"), None),
                next(lib_dir.glob("Universal Animation Library 2[[]Standard[]]/Unreal-Godot/UAL2_Standard.glb"), None)]
        if not all(srcs):
            print("both libraries must be unzipped in local/libraries/quaternius_ual")
            return 2
        code, lines = envmod.run_blender(e, "merge_libraries.py", [merged] + srcs, 15)
        print("\n".join(lines[-3:]))
        if code != 0 or not merged.exists():
            return 1
    bad = 0
    for tid in ids:
        fbx = film.adapter.rigged_file(tid) if film.adapter else None
        if not fbx:
            print(f"  {tid}: no rigged body")
            bad += 1
            continue
        own = Path(fbx).parents[1] / "moves" / f"{tid}_moves.json"
        height = 1.72
        if own.exists():
            height = float(json.loads(own.read_text(encoding="utf-8")).get("height_m") or height)
        out = Path(fbx).parents[1] / "moves" / f"{tid}_moves_ual2.glb"
        r = motions.fit(e, merged, Path(fbx), out, height=height, minutes=25)
        if not r.get("ok"):
            print(f"  {tid}: {r.get('error')}")
            bad += 1
            continue
        code, lines = envmod.run_blender(e, "keyed_moves.py", ["--body", out, "--out", out, "--base-action", "Idle_Loop"], 15)
        print(f"  {tid}: fitted ({r.get('note')}); keyed moves: {'yes' if code == 0 else 'no — ' + ' '.join(lines[-2:])}")
    return 1 if bad else 0


def cmd_film(cfg: dict, args: list[str]) -> int:
    sub = args[0] if args else "help"
    rest = args[1:]
    pos = _positional(rest)
    if sub in ("help", "-h", "--help"):
        print(__doc__)
        return 0
    if sub == "beatmap":
        from .film import beatmap
        if not pos:
            print("film beatmap <audio> [--meter 4] [--bpm 76] [--out x.json]")
            return 2
        bm = beatmap.analyse(pos[0], meter=int(_opt(rest, "--meter", 4)), bpm_hint=float(_opt(rest, "--bpm")) if _opt(rest, "--bpm") else None)
        out = Path(_opt(rest, "--out") or (Path(pos[0]).with_suffix(".beats.json")))
        beatmap.write(bm, out)
        beatmap.draw(beatmap.read(out), out.with_suffix(".png"), audio=pos[0])
        print(json.dumps({"tempo": bm["tempo"], "checks": bm["checks"], "out": str(out)}, indent=1))
        return 0
    film = Film(cfg, rest)
    if sub == "beatmaps":
        return cmd_beatmaps(film, _opt(rest, "--only"))
    if sub == "check":
        return cmd_check(film, pos)
    if sub in ("timeline", "conductor", "clicks", "render", "encode") and not pos:
        print(f"film {sub} <part> — the parts: {', '.join(film.parts())}")
        return 2
    if sub == "timeline":
        return cmd_timeline(film, pos[0])
    if sub == "conductor":
        return 0 if cmd_conductor(film, pos[0]) or True else 1
    if sub == "clicks":
        return cmd_clicks(film, pos[0])
    if sub == "render":
        return cmd_render(film, pos[0], "--final" in rest, "--song" in rest, _opt(rest, "--frames"), "--no-render" not in rest)
    if sub == "encode":
        return cmd_encode(film, pos[0], "--final" in rest, "--song" in rest)
    if sub == "video":
        return cmd_video(film, pos[0] if pos else "heads", "--final" in rest)
    if sub == "refit":
        return cmd_refit(cfg, film, pos)
    print(f"unknown: film {sub}\n{__doc__}")
    return 2


COMMANDS = {"film": cmd_film}
