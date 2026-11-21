"""blender.run — William's Blender with one add-on profile, for one job (BUILD 98 Part 1a, Claude Opus 2026-11-21).

✦ William, 2026-11-21: "Lets build every tool that we need into rpg forge (that's really its job, to be the one stop shop
for our game development." The forge's own background Blender stays --factory-startup (the world queue is never touched by
any add-on). A run here names a profile from forge/threed/blender/profiles.json; only that profile's add-ons are enabled,
for that run, and preferences are never saved.

    python -m forge.blenderrun profiles
    python -m forge.blenderrun run <script.py> [--profile trees] [--blend file.blend] [--name grow_dawn_redwood] [--wait] [-- args…]
    python -m forge.blenderrun status [<run id>]

Every run gets its own folder, out/blender/<stamp>_<name>/: the command, Blender's whole log (log.txt), boot.json (which
add-ons came up and the script's result) and whatever the script writes there (it is given the folder as --out and in
FORGE_RUN_DIR). A run is started below normal priority. It does not take the graphics card's lock, so a script run here
renders on the processor (Workbench, EEVEE at small sizes, or Cycles on the CPU); a script that needs the card takes it
itself through forge/threed/cardlock.py, as the world queue's own steps do.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "forge" / "threed" / "blender" / "profiles.json"
BOOT = ROOT / "forge" / "threed" / "blender" / "profile_boot.py"
WIN = sys.platform == "win32"


class RunError(Exception):
    pass


def load_profiles(path: Path | None = None) -> dict:
    return json.loads(Path(path or PROFILES).read_text(encoding="utf-8"))


def blender_program(cfg: dict | None = None, prof: dict | None = None) -> str:
    t = (cfg or {}).get("threed") or {}
    return str(t.get("blender_program") or (prof or load_profiles()).get("blender_program") or "")


def runs_dir(cfg: dict | None = None) -> Path:
    try:
        from . import config as cfgmod
        return cfgmod.path_of(cfg or cfgmod.load(), "out") / "blender"
    except Exception:  # noqa: BLE001
        return ROOT / "out" / "blender"


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s)[:60] or "run"


def command(script: str, profile: str = "", blend: str = "", out: Path | None = None, args: list | None = None,
            prof: dict | None = None, program: str = "") -> list[str]:
    """The exact command line. Pure: tests check it without a Blender."""
    prof = prof or load_profiles()
    mods: list[str] = []
    if profile:
        p = (prof.get("profiles") or {}).get(profile)
        if not p:
            raise RunError(f"no profile {profile!r}; the profiles are {', '.join(sorted(prof.get('profiles') or {}))}")
        mods = list(p.get("modules") or [])
    exe = program or prof.get("blender_program") or "blender"
    cmd = [exe, "--background", "--factory-startup"]
    if blend:
        cmd.append(str(blend))
    cmd += ["--python", str(BOOT), "--", "--profile", profile or "", "--modules", ",".join(mods),
            "--script", str(script), "--out", str(out or "."), "--"] + [str(a) for a in (args or [])]
    return cmd


def start(script: str, profile: str = "", blend: str = "", args: list | None = None, name: str = "", who: str = "",
          cfg: dict | None = None, wait: bool = False, minutes: float = 60) -> dict:
    prof = load_profiles()
    exe = blender_program(cfg, prof)
    if not exe or not Path(exe).exists():
        raise RunError(f"Blender is not where the forge looks ({exe or 'nowhere set'}); set forge.json threed.blender_program")
    sp = Path(script)
    if not sp.is_absolute():
        sp = ROOT / sp
    if not sp.exists():
        raise RunError(f"no script at {sp}")
    rid = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{_slug(name or sp.stem)}"
    rd = runs_dir(cfg) / rid
    rd.mkdir(parents=True, exist_ok=True)
    cmd = command(str(sp), profile, blend, rd, args, prof, exe)
    meta = {"id": rid, "script": str(sp), "profile": profile, "blend": blend, "args": args or [], "who": who,
            "started": datetime.now().isoformat(timespec="seconds"), "command": cmd}
    env = dict(os.environ, FORGE_RUN_DIR=str(rd), PYTHONNOUSERSITE="1")
    log = open(rd / "log.txt", "w", encoding="utf-8", errors="replace")
    flags = 0
    if WIN:
        flags = 0x00004000 | 0x08000000          # BELOW_NORMAL_PRIORITY_CLASS | CREATE_NO_WINDOW
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(rd), env=env, creationflags=flags)
    meta["pid"] = proc.pid
    (rd / "run.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    if wait:
        try:
            proc.wait(timeout=minutes * 60)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        return status(rid, cfg)
    return {"id": rid, "state": "running", "folder": str(rd), "pid": proc.pid}


def _alive(pid: int) -> bool:
    if not pid:
        return False
    if WIN:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def status(rid: str = "", cfg: dict | None = None) -> dict:
    base = runs_dir(cfg)
    if not rid:
        runs = sorted([p.name for p in base.glob("*") if p.is_dir()], reverse=True)[:20] if base.exists() else []
        return {"runs": [status(r, cfg) for r in runs]}
    rd = base / rid
    if not rd.exists():
        raise RunError(f"no run {rid}")
    meta = json.loads((rd / "run.json").read_text(encoding="utf-8")) if (rd / "run.json").exists() else {}
    boot = json.loads((rd / "boot.json").read_text(encoding="utf-8")) if (rd / "boot.json").exists() else None
    state = "done" if boot and boot.get("exit") == 0 else "failed" if boot else (
        "running" if _alive(int(meta.get("pid") or 0)) else "failed")
    tail = ""
    if (rd / "log.txt").exists():
        tail = "".join((rd / "log.txt").read_text(encoding="utf-8", errors="replace").splitlines(True)[-25:])
    files = sorted(p.name for p in rd.iterdir() if p.name not in ("run.json", "boot.json", "log.txt"))
    return {"id": rid, "state": state, "profile": meta.get("profile"), "script": meta.get("script"),
            "started": meta.get("started"), "enabled": (boot or {}).get("enabled"), "failed_addons": (boot or {}).get("failed"),
            "result": (boot or {}).get("result"), "error": (boot or {}).get("error"), "files": files[:60],
            "folder": str(rd), "log_tail": tail if state != "done" else ""}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "profiles":
        p = load_profiles()
        for k, v in sorted(p["profiles"].items()):
            print(f"{k:14} {len(v['modules'])} add-ons")
        return 0
    if argv[0] == "status":
        print(json.dumps(status(argv[1] if len(argv) > 1 else ""), indent=1))
        return 0
    if argv[0] == "run":
        rest = argv[1:]
        extra = rest[rest.index("--") + 1:] if "--" in rest else []
        rest = rest[: rest.index("--")] if "--" in rest else rest
        opts = {"profile": "", "blend": "", "name": ""}
        script, wait, i = "", False, 0
        while i < len(rest):
            if rest[i] == "--wait":
                wait = True
            elif rest[i].startswith("--") and i + 1 < len(rest):
                opts[rest[i][2:]] = rest[i + 1]
                i += 1
            else:
                script = rest[i]
            i += 1
        print(json.dumps(start(script, opts["profile"], opts["blend"], extra, opts["name"], "William", wait=wait), indent=1))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
