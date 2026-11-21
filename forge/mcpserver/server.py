"""The forge as an MCP connector (BUILD 83 Part A, 2026-11-19) — so Claude Fable and Claude Opus can drive RPG_Forge from a chat.

✦ William, 2026-11-19 14:22: "Now we need to build MCP into RPG_Forge so that Fable and Opus can utilize it."

    venv_mcp\\Scripts\\python.exe -m forge.mcpserver            the server (Claude's desktop app starts it; stdio)
    venv_mcp\\Scripts\\python.exe -m forge.mcpserver --check    the self-test: its tools, and the forge answering
    venv_mcp\\Scripts\\python.exe -m forge.mcpserver --config-block   the entry for Claude's settings file

It runs in its own small environment (venv_mcp: the MCP library and Pillow), so the art worker's environment is never
touched. It holds no forge logic: every operation is run by `forge.mcpserver.ops` in the forge's own environment, one
process a call, so each call runs the forge's newest code. Seven tools:

  forge_status    everything at a glance            forge_job       one art job, with its contact sheet
  forge_search    find an operation and its input   forge_wait      wait (≤ 50 s) for an art job, then forge_job
  forge_call      run one operation                 forge_area      a place and its pictures
  forge_pictures  look at any picture the forge made (downsized)

It listens on no network port and writes only inside the forge: logs/forge_<date>.log and local/mcp/.
"""
from __future__ import annotations

import io
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from .. import config as cfgmod
from ..log import DailyFileHandler
from . import ops as opsmod

ROOT = cfgmod.ROOT
WIN = sys.platform == "win32"
log = logging.getLogger("forge.mcp")
PICTURE_TYPES = (".png", ".jpg", ".jpeg", ".webp")
WAIT_MAX = 50
OP_TIMEOUT = 900

INSTRUCTIONS = """RPG_Forge is William's art foundry for his RPGs: a queue of art jobs (pictures through ComfyUI), the world
list (3D things the world queue makes, day and night), places (town plans that become 3D stages), approvals and the Mail.

How to use it:
- Start with forge_status. It shows the backlog in hours; under a day, writing the next list comes first.
- forge_search finds the operation for what you want and gives its exact input; forge_call runs it.
- Every change: sign it with who = your own name ("Claude Fable" or "Claude Opus"). Try dry_run first when it is big. Give
  an idempotency_key when you might retry (a retried call with the same key is never done twice).
- Approving (approvals.all, world.match_and_release …) is Claude Fable's only, and only while William's "Claude Fable may
  approve for me" is on; it is signed "Claude Fable, for William".
- Nothing here deletes anything, starts or stops the world queue, or changes canon, lyrics, rulings or settings.
- Look at what was made: forge_job shows a job's contact sheet; forge_pictures shows any picture by its path."""


# ------------------------------------------------------------------------------------------------ the forge, one call a process
def _cfg() -> dict:
    return cfgmod.load()


def forge_python(cfg: dict | None = None) -> str:
    """The forge's own Python: forge.json -> mcp.python, else venv\\Scripts\\python.exe (or venv/bin/python)."""
    cfg = cfg or {}
    want = ((cfg.get("mcp") or {}).get("python"))
    for p in ([want] if want else []) + [ROOT / "venv" / "Scripts" / "python.exe", ROOT / "venv-mac" / "bin" / "python",
                                         ROOT / "venv" / "bin" / "python"]:
        if p and Path(p).exists():
            return str(p)
    return sys.executable


def run_op(req: dict, timeout: float = OP_TIMEOUT) -> dict:
    cfg = _cfg()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONIOENCODING"] = "utf-8"
    kw = {"creationflags": 0x08000000} if WIN else {}            # CREATE_NO_WINDOW: no console flashes on William's screen
    t0 = time.time()
    try:
        p = subprocess.run([forge_python(cfg), "-m", "forge.mcpserver.ops"], input=json.dumps(req, default=str),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT), env=env,
                           timeout=timeout, **kw)
    except subprocess.TimeoutExpired:
        log.warning("mcp: %s took longer than %d s", req.get("op"), timeout)
        return opsmod.error("outcome_unknown", f"the forge took longer than {int(timeout)} s on {req.get('op')}; it may still be "
                            "working", "forge_status in a minute; look before calling again (approvals.log, jobs.list)")
    lines = [ln for ln in (p.stdout or "").splitlines() if ln.strip()]
    try:
        ans = json.loads(lines[-1])
    except (IndexError, ValueError):
        log.error("mcp: %s gave no answer (exit %s): %s", req.get("op"), p.returncode, (p.stderr or "")[-2000:])
        return opsmod.error("internal", f"the forge gave no answer (exit {p.returncode}): {(p.stderr or '')[-600:]}",
                            "logs/forge_<date>.log; tell William if it repeats")
    log.info("mcp: tool call %s → %s (%.1f s)", req.get("op"), ans.get("status"), time.time() - t0)
    return ans


def _text(ans) -> str:
    return json.dumps(ans, indent=1, ensure_ascii=False, default=str)


# ------------------------------------------------------------------------------------------------ pictures
def picture_path(path: str) -> Path:
    p = Path(str(path))
    p = (p if p.is_absolute() else ROOT / p).resolve()
    if ROOT.resolve() not in p.parents:
        raise ValueError("only pictures inside the forge folder can be shown")
    if p.suffix.lower() not in PICTURE_TYPES:
        raise ValueError(f"not a picture ({', '.join(PICTURE_TYPES)})")
    if not p.is_file():
        raise FileNotFoundError(f"no picture at {path}")
    return p


def picture_bytes(path: str, max_side: int = 1024) -> tuple[bytes, str]:
    """(JPEG bytes, a line about it) — downsized, transparency laid on grey."""
    from PIL import Image as PILImage
    p = picture_path(path)
    max_side = max(64, min(int(max_side or 1024), 2048))
    with PILImage.open(p) as im:
        size = im.size
        im.thumbnail((max_side, max_side))
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = PILImage.new("RGB", im.size, (128, 128, 128))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        else:
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
    rel = p.relative_to(ROOT.resolve()).as_posix()
    return buf.getvalue(), f"{rel} — {size[0]}×{size[1]}, shown at {im.size[0]}×{im.size[1]}"


# ------------------------------------------------------------------------------------------------ the server
def build_server():
    try:
        from mcp.server.mcpserver import MCPServer as Server, Image
    except ImportError:                                           # the 1.x library
        from mcp.server.fastmcp import FastMCP as Server, Image

    server = Server("rpg-forge", instructions=INSTRUCTIONS)

    def tool(description: str):
        def deco(fn):
            try:
                return server.tool(description=description, structured_output=False)(fn)
            except TypeError:                                     # a library without structured_output
                return server.tool(description=description)(fn)
        return deco

    def with_picture(ans: dict, path: str | None, max_side: int = 1024):
        out = [_text(ans)]
        if path:
            try:
                data, line = picture_bytes(path, max_side)
                out += [line, Image(data=data, format="jpeg")]
            except Exception as ex:  # noqa: BLE001 — the words still go back
                out.append(f"(the picture could not be shown: {ex})")
        return out

    @tool("Everything at a glance: the art queue, the world queue and its backlog in hours (under a day: the next list "
          "comes first), the never-stop launcher, ComfyUI, the disk, and what waits for approval. Start here.")
    def forge_status():
        return _text(run_op({"op": "status"}))

    @tool("Find the operation for what you want to do, with its exact input. Words like 'queue a picture', 'world list', "
          "'approve', 'place', 'mail', 'make again'. Empty: lists every operation and job type.")
    def forge_search(query: str = ""):
        return _text(search(query))

    @tool("Run one forge operation (forge_search shows them). input: its fields. who: your own name as you sign, e.g. "
          "'Claude Fable' or 'Claude Opus' (needed for every change). dry_run: true says what would happen and changes "
          "nothing. idempotency_key: any unique words — a retried call with the same key is never done twice.")
    def forge_call(op: str, input: dict | None = None, who: str = "", dry_run: bool = False, idempotency_key: str = ""):
        return _text(run_op({"op": op, "input": input or {}, "who": who, "dry_run": bool(dry_run), "key": idempotency_key}))

    @tool("One art job: its state, result and files, with its contact sheet as a picture.")
    def forge_job(job_id: str):
        ans = run_op({"op": "jobs.get", "input": {"id": job_id}})
        return with_picture(ans, (ans.get("result") or {}).get("contact") if ans.get("status") == "done" else None)

    @tool(f"Wait for an art job to finish (at most {WAIT_MAX} s a call), then show it as forge_job does. Call again if it "
          "is still going.")
    def forge_wait(job_id: str, seconds: int = WAIT_MAX):
        jobs = cfgmod.path_of(_cfg(), "jobs")
        end = time.time() + max(1, min(int(seconds or WAIT_MAX), WAIT_MAX))
        while time.time() < end:
            if (jobs / "done" / f"{job_id}.json").exists() or (jobs / "failed" / f"{job_id}.json").exists():
                break
            time.sleep(2)
        ans = run_op({"op": "jobs.get", "input": {"id": job_id}})
        return with_picture(ans, (ans.get("result") or {}).get("contact") if ans.get("status") == "done" else None)

    @tool("A place (a town plan that becomes a 3D stage): its things on the world list and their states, and the game's "
          "own pictures of it (up to three). No place: lists them. (The area checklists are BUILD 83 Part B, not built yet.)")
    def forge_area(place: str = ""):
        if not place:
            return _text(run_op({"op": "places.list"}))
        ans = run_op({"op": "places.show", "input": {"place": place}})
        out = [_text(ans)]
        r = ans.get("result") or {}
        for pth in (r.get("look_pictures") or [])[:3] or ([r["plan_picture"]] if r.get("plan_picture") else []):
            try:
                data, line = picture_bytes(pth, 768)
                out += [line, Image(data=data, format="jpeg")]
            except Exception as ex:  # noqa: BLE001
                out.append(f"({pth}: {ex})")
        return out

    @tool("Look at any picture inside the forge folder by its path (as other tools give it, e.g. "
          "'out/20261119-…/contact.png'), downsized to max_side pixels (default 1024, at most 2048).")
    def forge_pictures(path: str, max_side: int = 1024):
        try:
            data, line = picture_bytes(path, max_side)
        except Exception as ex:  # noqa: BLE001
            return _text(opsmod.error("not_found" if isinstance(ex, FileNotFoundError) else "invalid_input", str(ex),
                                      "use a path another tool gave (forge_job, jobs.get, places.show)"))
        return [line, Image(data=data, format="jpeg")]

    server._forge_tools = ["forge_status", "forge_search", "forge_call", "forge_job", "forge_wait", "forge_area",
                           "forge_pictures"]
    return server


def search(query: str = "") -> dict:
    """Operations and job types whose name or words match (all of them for an empty query). Runs here: no forge logic."""
    q = [w for w in str(query or "").lower().split() if w]
    rows = []
    for o in opsmod.OPS.values():
        hay = (o.name + " " + o.doc + " " + " ".join(o.inputs)).lower()
        if not q or any(w in hay for w in q):
            rows.append(o.describe())
    types = []
    try:
        from .. import schema
        for t, s in sorted(schema.JOB_TYPES.items()):
            hay = (t + " " + s["doc"]).lower()
            if not q or any(w in hay for w in q):
                types.append({"type": t, "needs": s["needs"], "what": s["doc"][:220], "required": s["required"]})
    except Exception:  # noqa: BLE001
        pass
    return {"operations": rows, "job_types": types[:40],
            "how": "forge_call(op, input, who, dry_run, idempotency_key). A job type is queued with jobs.submit: "
                   "{\"job\": {\"type\": …, \"name\": …, required fields}}."}


# ------------------------------------------------------------------------------------------------ setup helpers
def config_block() -> dict:
    py = ROOT / "venv_mcp" / ("Scripts/python.exe" if WIN else "bin/python")
    return {"rpg-forge": {"command": str(py), "args": ["-m", "forge.mcpserver"], "env": {"PYTHONPATH": str(ROOT)}}}


def _log_to_file() -> None:
    lg = logging.getLogger("forge")
    if not any(isinstance(h, DailyFileHandler) for h in lg.handlers):
        try:
            h = DailyFileHandler(cfgmod.path_of(_cfg(), "logs"))
            h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
            lg.addHandler(h)
            lg.setLevel(logging.INFO)
        except Exception:  # noqa: BLE001 — never on stdout: stdout is the connector's own line to Claude
            pass


def check() -> int:
    """The self-test (mcp_check.bat): the library, the tools, the forge answering."""
    ok = True
    try:
        import importlib.metadata as md
        print(f"The MCP library: {md.version('mcp')}")
    except Exception as ex:  # noqa: BLE001
        print(f"The MCP library is NOT installed ({ex}) — run mcp_setup.bat")
        return 1
    try:
        s = build_server()
        print(f"The connector's tools: {', '.join(s._forge_tools)}")
    except Exception as ex:  # noqa: BLE001
        print(f"The connector did not build: {type(ex).__name__}: {ex}")
        return 1
    print(f"The forge's own Python: {forge_python(_cfg())}")
    ans = run_op({"op": "status"}, timeout=120)
    if ans.get("status") != "done":
        ok = False
        print(f"The forge did NOT answer: {ans.get('message')}")
    else:
        r = ans["result"]
        w = r.get("world_queue") or {}
        print(f"The forge answers. Game: {r.get('game')}. Art queue: {r.get('art_queue')}. World list: "
              f"{w.get('to_make')} to make ({w.get('time_left')}); world queue {'running' if w.get('running') else 'not running'}.")
    print(f"Operations: {len(opsmod.OPS)}.")
    try:
        data, line = picture_bytes(str(Path("docs") / "media" / next(p.name for p in (ROOT / "docs" / "media").iterdir()
                                                                    if p.suffix.lower() in PICTURE_TYPES)), 256)
        print(f"Pictures: OK ({line.split(' — ')[0]})")
    except StopIteration:
        print("Pictures: no picture in docs/media to try (fine)")
    except Exception as ex:  # noqa: BLE001
        ok = False
        print(f"Pictures: NOT OK ({ex}) — is Pillow installed in venv_mcp?")
    print("OK — the connector is ready." if ok else "Something above is not right.")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--check" in argv:
        for s in (sys.stdout, sys.stderr):
            try:
                s.reconfigure(errors="replace")
            except Exception:  # noqa: BLE001
                pass
        return check()
    if "--config-block" in argv:
        print(json.dumps(config_block(), indent=2))
        return 0
    _log_to_file()
    log.info("mcp: the connector started (pid %d)", os.getpid())
    build_server().run("stdio")
    return 0
