"""The forge dashboard (roadmap N7 / F16): `python -m forge ui` → http://127.0.0.1:8765

Standard library only (http.server), bound to 127.0.0.1 — nothing outside this PC can reach it. It shows the queue
with an ETA, what is rendering now, per-batch progress, the newest pictures, failed jobs with their errors, and has
four actions, each logged: Retry (a failed job), Pause / Resume (the pending queue) and Approve (dry run first, then
confirm; a refusal is shown in plain words). Everything else is read-only. Colours: job type on the left edge of a
card; licence as the border — green = every model commercial-OK, red = not, grey = unknown or not a picture.
"""
from __future__ import annotations
import hashlib, json, threading, time, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image

from . import config as cfgmod
from .log import get

log = get("ui")
HOST, PORT = "127.0.0.1", 8765
TYPE_COLOURS = {"scene_paint": "#e0a040", "scene_kit": "#f0c040", "repaint": "#d08040", "render": "#6aa0e0",
                "scene_card": "#8a7ae0", "portrait": "#e070a0", "prop": "#60c0a0", "icon": "#50c8c8", "sleeve": "#c080e0",
                "pipeline": "#a0a0a0", "depth_map": "#7080ff", "upscale": "#80b0ff", "normal_map": "#90a0c0",
                "emissive_mask": "#ff9060", "scene_layers": "#70c070", "tile_texture": "#a0c060"}


class State:
    """Reads the queue folders; done jobs never change, so they are parsed once and cached by file name."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.jobs = cfgmod.path_of(cfg, "jobs")
        self.out = cfgmod.path_of(cfg, "out")
        self._done: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _read(self, p: Path) -> dict | None:
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return None if j.get("tombstone") else j

    def folder(self, state: str) -> list[dict]:
        out = []
        for p in sorted((self.jobs / state).glob("*.json")):
            if state == "done":
                with self._lock:
                    j = self._done.get(p.name)
                if j is None:
                    j = self._read(p)
                    if j is None:
                        continue
                    with self._lock:
                        self._done[p.name] = j
            else:
                j = self._read(p)
                if j is None:
                    continue
            j = dict(j)
            j["_state"] = state
            j["_mtime"] = p.stat().st_mtime if p.exists() else 0
            out.append(j)
        return out

    def image_for(self, j: dict) -> str | None:
        d = self.out / str(j.get("id"))
        if not d.exists():
            return None
        if (d / "contact.png").exists():
            return f"{j['id']}/contact.png"
        for o in ((j.get("result") or {}).get("outputs") or []):
            if str(o).lower().endswith(".png") and (d / o).exists():
                return f"{j['id']}/{o}".replace("\\", "/")
        pngs = sorted(p for p in d.glob("*.png") if not p.name.startswith(("raw", "control")))
        return f"{j['id']}/{pngs[0].name}" if pngs else None

    def licence_of(self, j: dict) -> str:
        r = j.get("result") or {}
        ok = r.get("commercial_ok")
        if ok is None:
            p = self.out / str(j.get("id")) / "prov.json"
            if p.exists():
                try:
                    ok = json.loads(p.read_text(encoding="utf-8")).get("commercial_ok")
                except (OSError, ValueError):
                    ok = None
        return "ok" if ok is True else ("no" if ok is False else "unknown")

    def check_of(self, j: dict) -> dict | None:
        """Night 3 (G5/G9): the kit check's verdict, if `kit check` (or approve --set) has run on this job."""
        p = self.out / str(j.get("id")) / "check.json"
        if not p.exists():
            return None
        try:
            v = json.loads(p.read_text(encoding="utf-8")).get("verdict")
        except (OSError, ValueError):
            return None
        return {"verdict": v, "image": f"{j['id']}/check.png" if (p.parent / "check.png").exists() else None}

    def job(self, jid: str) -> dict | None:
        for st in ("done", "failed", "pending", "running", "paused"):
            p = self.jobs / st / f"{jid}.json"
            if p.exists():
                return self._read(p)
        return None

    def snapshot(self) -> dict:
        from . import eta
        pend, run, done, failed, paused = (self.folder(s) for s in ("pending", "running", "done", "failed", "paused"))
        batches: dict[str, dict] = {}
        for jl in (pend, run, done, failed, paused):
            for j in jl:
                b = str(j.get("batch") or "(no batch)")
                e = batches.setdefault(b, {"pending": 0, "running": 0, "done": 0, "failed": 0, "paused": 0, "last": 0.0})
                e[j["_state"]] += 1
                e["last"] = max(e["last"], j["_mtime"])
        # batches that are active, or touched in the last two days
        now = time.time()
        shown = {b: v for b, v in batches.items() if v["pending"] or v["running"] or v["paused"] or now - v["last"] < 2 * 86400}
        recent = sorted(done, key=lambda j: j["_mtime"], reverse=True)[:24]
        fails = sorted(failed, key=lambda j: j["_mtime"], reverse=True)[:30]
        running = []
        for j in run:
            started = j.get("started_at")
            running.append({"id": j["id"], "type": j.get("type"), "name": j.get("name"), "batch": j.get("batch"), "started": started})
        e = eta.estimate(self.cfg)
        # Night 3 (G9): which batch is running now and which are still to come, in the order the worker takes them
        order = sorted(pend, key=lambda j: (-int(j.get("priority") or 0), str(j.get("id"))))
        upcoming = []
        for j in order:
            b = str(j.get("batch") or "(no batch)")
            if b not in upcoming:
                upcoming.append(b)
        now_batch = running[0]["batch"] if running else None
        return {
            "now_batch": now_batch, "upcoming": [b for b in upcoming if b != now_batch][:6],
            "counts": {"pending": len(pend), "running": len(run), "done": len(done), "failed": len(failed), "paused": len(paused)},
            "eta": {"seconds": e["seconds"], "human": eta.human(e["seconds"]) if e["pending"] else "—", "based_on": e["based_on"]},
            "running": running,
            "batches": [{"name": b, **v} for b, v in sorted(shown.items(), key=lambda kv: -kv[1]["last"])],
            "recent": [{"id": j["id"], "type": j.get("type"), "name": j.get("name"), "batch": j.get("batch"),
                        "image": self.image_for(j), "licence": self.licence_of(j),
                        "outputs": [o for o in ((j.get("result") or {}).get("outputs") or [])],
                        "set": bool((j.get("result") or {}).get("slots")), "finished": j.get("finished_at"),
                        "check": self.check_of(j)} for j in recent],
            "failed": [{"id": j["id"], "type": j.get("type"), "name": j.get("name"), "batch": j.get("batch"),
                        "error": str(j.get("error") or "")[:600], "finished": j.get("finished_at")} for j in fails],
            "colours": TYPE_COLOURS,
            "time": time.strftime("%H:%M:%S"),
            **self.night4(),
        }


def _night4(self) -> dict:
    """Night 4: the disk guard's banner (produce_watch.bat) and the Called out drafts (feedback_in.bat)."""
    out = {"guard": None, "called_out": []}
    try:
        from .night4 import guard, feedback
        out["guard"] = (guard.read(self.cfg) or {}).get("message")
        out["called_out"] = feedback.list_drafts(self.cfg)[:30]
    except Exception as e:  # noqa: BLE001 — the dashboard must come up whatever
        log.warning("ui: night 4 panels: %s", e)
    return out


State.night4 = _night4


def thumb(out_root: Path, rel: str, width: int = 420) -> Path:
    """A cached JPEG thumbnail of out/<rel> (rel must stay inside out/)."""
    src = (out_root / rel).resolve()
    if not str(src).startswith(str(out_root.resolve())) or not src.exists() or src.suffix.lower() != ".png":
        raise FileNotFoundError(rel)
    key = hashlib.sha1(f"{src}|{src.stat().st_mtime}|{width}".encode()).hexdigest()[:20]
    dest = out_root / "_ui_thumbs" / f"{key}.jpg"
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as im:
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, (40, 40, 46, 255))
            bg.alpha_composite(im)
            bg = bg.convert("RGB")
            bg.thumbnail((width, width * 4))
            bg.save(dest, "JPEG", quality=85)
    return dest


def wanted_names(cfg: dict) -> list[str]:
    from . import manifest
    try:
        w = manifest.load_wanted(cfg, cfgmod.default_game(cfg))
    except FileNotFoundError:
        return []
    return sorted(n for n, v in w["items"].items() if not v.get("set_of"))


def act(cfg: dict, action: str, body: dict) -> dict:
    """The four actions. Returns {"ok": bool, "message": str, ...}."""
    from .queue import Queue
    q = Queue(cfgmod.path_of(cfg, "jobs"), cfgmod.path_of(cfg, "out"))
    if action == "pause":
        n = q.pause()
        log.info("ui: pause → %d job(s) parked", n)
        return {"ok": True, "message": f"paused — {n} job(s) moved to jobs/paused (the one rendering now finishes)"}
    if action == "resume":
        n = q.resume()
        log.info("ui: resume → %d job(s) back in the queue", n)
        return {"ok": True, "message": f"resumed — {n} job(s) back in the queue"}
    if action == "retry":
        jid = str(body.get("id") or "")
        if not jid or not (cfgmod.path_of(cfg, "jobs") / "failed" / f"{jid}.json").exists():
            return {"ok": False, "message": f"no failed job {jid}"}
        import os
        src = cfgmod.path_of(cfg, "jobs") / "failed" / f"{jid}.json"
        job = json.loads(src.read_text(encoding="utf-8"))
        for k in ("error", "traceback", "started_at", "finished_at", "result"):
            job.pop(k, None)
        job["retries"] = int(job.get("retries", 0)) + 1
        q._write_atomic(src, job)          # the queue's own atomic write, then a rename — exactly what retry.bat does
        os.replace(src, cfgmod.path_of(cfg, "jobs") / "pending" / src.name)
        log.info("ui: retry %s", jid)
        return {"ok": True, "message": f"{job.get('name') or jid} is back in the queue"}
    if action == "approve":
        from . import manifest
        jid, name = str(body.get("id") or ""), str(body.get("name") or "").strip()
        dry = bool(body.get("dry_run", True))
        if not jid or not name:
            return {"ok": False, "message": "choose what this picture is for (a wanted name, e.g. scenes/town_square)"}
        try:
            if body.get("set"):
                from . import kitcheck                    # Night 3 (G5): refuse a kit that fails the check
                kd = cfgmod.path_of(cfg, "out") / jid
                if kd.is_dir():
                    chk = kitcheck.check(cfg, kd, name.split("/")[-1])
                    bad = [l for l in chk["lines"] if l["status"] == "fail"]
                    if bad:
                        return {"ok": False, "message": "kit check failed: " + "; ".join(f"{l['check']} — {l['message']}" for l in bad)}
                plan = manifest.approve_set(cfg, jid, name, dry_run=dry)
                rows = [{"what": r["slot"], "file": Path(r["file"]).name, "dest": r["dest"], "size": r["size"]} for r in plan["rows"]]
            else:
                pick = int(body["pick"]) if body.get("pick") else None
                plan = manifest.approve(cfg, jid, name, pick=pick, dry_run=dry)
                rows = [{"what": "picture", "file": Path(plan["file"]).name, "dest": plan["dest"], "size": plan["size"]}]
        except Exception as e:  # noqa: BLE001 — a refusal is the message
            log.info("ui: approve %s as %s refused: %s", jid, name, e)
            return {"ok": False, "message": str(e)}
        conds = plan.get("conditions") or manifest.licence_conditions(cfg, plan.get("licences") or [])
        log.info("ui: approve %s as %s%s%s", jid, name, " (set)" if body.get("set") else "", " DRY RUN" if dry else " — copied")
        return {"ok": True, "dry_run": dry, "rows": rows, "licences": plan.get("licences"), "conditions": conds,
                "note": plan.get("size_note"),
                "message": ("Ready to copy — check the table, then Confirm." if dry else "Approved — copied into the game with provenance.")}
    if action in ("draft_submit", "draft_dismiss", "draft_himself"):        # Night 4 (F5): Called out
        from .night4 import feedback
        r = feedback.draft_action(cfg, action, str(body.get("draft") or ""))
        log.info("ui: %s %s → %s", action, body.get("draft"), r.get("message"))
        return r
    return {"ok": False, "message": f"unknown action {action}"}


class Handler(BaseHTTPRequestHandler):
    state: State = None          # set by serve()
    cfg: dict = None

    def log_message(self, fmt, *args):      # quiet: the forge log gets the actions
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):
        u = urlparse(self.path)
        try:
            if u.path == "/":
                self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif u.path == "/api/state":
                self._json(self.state.snapshot())
            elif u.path == "/api/wanted":
                self._json(wanted_names(self.cfg))
            elif u.path == "/report":                      # Night 3 (G1/G9): the newest morning report
                from . import night_report
                rep = night_report.latest(self.cfg)
                if rep is None:
                    rep, _md, _r = night_report.build(self.cfg)
                self.send_response(302)
                self.send_header("Location", "/out/reports/" + rep.name)
                self.end_headers()
            elif u.path.startswith("/out/"):                 # read-only files under out/ (reports, bake-off pages)
                rel = u.path[len("/out/"):]
                src = (self.state.out / rel).resolve()
                types = {".html": "text/html; charset=utf-8", ".jpg": "image/jpeg", ".png": "image/png",
                         ".md": "text/plain; charset=utf-8", ".json": "application/json", ".gif": "image/gif"}
                if not str(src).startswith(str(self.state.out.resolve())) or not src.is_file() or src.suffix.lower() not in types:
                    raise FileNotFoundError(rel)
                self._send(200, src.read_bytes(), types[src.suffix.lower()])
            elif u.path == "/api/job":                        # Night 3 (G9): one job's fields, for the A/B view
                j = self.state.job(parse_qs(u.query).get("id", [""])[0])
                if j is None:
                    raise FileNotFoundError("job")
                self._json({k: v for k, v in j.items() if k not in ("traceback",)})
            elif u.path in ("/thumb", "/full"):
                rel = parse_qs(u.query).get("p", [""])[0]
                if u.path == "/thumb":
                    p = thumb(self.state.out, rel)
                    self._send(200, p.read_bytes(), "image/jpeg")
                else:
                    src = (self.state.out / rel).resolve()
                    if not str(src).startswith(str(self.state.out.resolve())) or not src.exists() or src.suffix.lower() != ".png":
                        raise FileNotFoundError(rel)
                    self._send(200, src.read_bytes(), "image/png")
            else:
                self._send(404, b"not found", "text/plain")
        except FileNotFoundError:
            self._send(404, b"not found", "text/plain")
        except Exception:  # noqa: BLE001
            log.error("ui GET %s: %s", self.path, traceback.format_exc())
            self._send(500, b"error - see the forge log", "text/plain")

    def do_POST(self):
        # a page on another site cannot set this header without a CORS preflight, which this server never answers
        if self.headers.get("X-Forge") != "1":
            self._send(403, b"forbidden", "text/plain")
            return
        u = urlparse(self.path)
        if not u.path.startswith("/api/act/"):
            self._send(404, b"not found", "text/plain")
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            self._json(act(self.cfg, u.path.rsplit("/", 1)[-1], body))
        except Exception as e:  # noqa: BLE001
            log.error("ui POST %s: %s", self.path, traceback.format_exc())
            self._json({"ok": False, "message": f"{type(e).__name__}: {e}"}, 500)


def make_server(cfg: dict, port: int = PORT) -> ThreadingHTTPServer:
    Handler.state = State(cfg)
    Handler.cfg = cfg
    return ThreadingHTTPServer((HOST, port), Handler)


def serve(cfg: dict, port: int = PORT) -> None:
    srv = make_server(cfg, port)
    log.info("ui: serving http://%s:%d (Ctrl+C to stop)", HOST, port)
    print(f"RPG_Forge dashboard: http://{HOST}:{port}   (close this window to stop it)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>RPG_Forge</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{--bg:#16161b;--panel:#1f1f26;--line:#2e2e38;--ink:#e8e6e1;--dim:#9a98a3;--ok:#3fbf6a;--no:#e05050;--unk:#6e6c78;--accent:#f0b040}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 "Segoe UI",system-ui,sans-serif}
header{display:flex;align-items:center;gap:18px;padding:14px 22px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:5}
h1{font-size:19px;margin:0;letter-spacing:.5px}h1 b{color:var(--accent)}
.pill{padding:3px 10px;border-radius:12px;background:var(--panel);border:1px solid var(--line);font-variant-numeric:tabular-nums}
.pill.r{border-color:var(--accent);color:var(--accent)}.pill.f{border-color:var(--no);color:#ff8a8a}
button{background:#2a2a33;color:var(--ink);border:1px solid #3a3a46;border-radius:6px;padding:6px 12px;cursor:pointer;font:inherit}
button:hover{border-color:var(--accent)}button.go{background:#2d4a33;border-color:var(--ok)}button.stop{background:#4a2d2d;border-color:var(--no)}
main{padding:18px 22px;display:grid;grid-template-columns:minmax(320px,1fr) 2.3fr;gap:20px}
section{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin-bottom:18px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:1.2px;color:var(--dim);margin:0 0 10px}
.bar{height:10px;background:#2a2a33;border-radius:5px;overflow:hidden;display:flex;margin:3px 0 10px}
.bar i{display:block;height:100%}.b-done{background:var(--ok)}.b-fail{background:var(--no)}.b-run{background:var(--accent)}.b-pause{background:#6a6aa0}
.batch{font-size:13px}.batch small{color:var(--dim);float:right}
.now{border-left:4px solid var(--accent);padding:6px 10px;margin:6px 0;background:#26262e;border-radius:4px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}
.card{background:#25252d;border-radius:8px;overflow:hidden;border:2px solid var(--unk);position:relative}
.card.ok{border-color:var(--ok)}.card.no{border-color:var(--no)}
.card .edge{position:absolute;left:0;top:0;bottom:0;width:6px}
.card img{width:100%;display:block;background:#111;cursor:zoom-in;min-height:60px}
.card .meta{padding:7px 9px 9px 14px;font-size:12px}.card .meta b{display:block;font-size:13px;word-break:break-all}
.card .meta span{color:var(--dim)}.card button{margin-top:6px;padding:3px 9px;font-size:12px}
.fail{border-left:4px solid var(--no);background:#2a2226;padding:8px 10px;margin:8px 0;border-radius:4px;font-size:12.5px}
.fail pre{white-space:pre-wrap;margin:5px 0;color:#ffb0b0;font-size:12px;max-height:110px;overflow:auto}
#modal{position:fixed;inset:0;background:rgba(0,0,0,.75);display:none;align-items:center;justify-content:center;z-index:20}
#modal .box{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px 20px;width:min(900px,94vw);max-height:90vh;overflow:auto}
#modal input,#modal select{background:#14141a;color:var(--ink);border:1px solid #3a3a46;border-radius:6px;padding:6px 8px;font:inherit;width:100%}
table{border-collapse:collapse;width:100%;font-size:12.5px;margin:10px 0}td,th{border-bottom:1px solid var(--line);padding:5px 6px;text-align:left}
.msg{padding:9px 12px;border-radius:6px;margin:10px 0;white-space:pre-wrap}.msg.ok{background:#1f3a27}.msg.no{background:#3a1f1f}
.cond{color:var(--accent)}#zoom{position:fixed;inset:0;background:rgba(0,0,0,.9);display:none;align-items:center;justify-content:center;z-index:30;cursor:zoom-out}
#zoom img{max-width:96vw;max-height:94vh}.legend span{display:inline-block;margin:2px 8px 2px 0;font-size:12px}.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}
</style></head><body>
<header><h1>RPG<b>_</b>Forge</h1>
<span class="pill" id="c-pend">queued –</span><span class="pill r" id="c-run">rendering –</span>
<span class="pill" id="c-done">done –</span><span class="pill f" id="c-fail">failed –</span><span class="pill" id="c-eta">ETA –</span>
<a class="pill" href="/report" target="_blank" style="color:var(--ink);text-decoration:none">Report</a>
<button id="ab-btn" onclick="openAB()" disabled>Compare A/B</button>
<span style="flex:1"></span><button class="stop" onclick="act('pause',{})">Pause queue</button><button class="go" onclick="act('resume',{})">Resume</button>
<span class="pill" id="clock">–</span></header>
<div id="guard" style="display:none;background:#5a1d1d;color:#fff;padding:8px 14px;font-weight:600"></div>
<main><div>
<section><h2>Rendering now</h2><div id="now"></div><div id="upnext" style="color:var(--dim);font-size:12.5px;margin-top:6px"></div></section>
<section><h2>Batches</h2><div id="batches"></div></section>
<section><h2>Called out</h2><div id="called"></div></section>
<section><h2>Failed</h2><div id="failed"></div></section>
<section><h2>Colours</h2><div class="legend" id="legend"></div>
<div class="legend"><span><i style="background:var(--ok)"></i>border: every model commercial-OK</span><span><i style="background:var(--no)"></i>not OK</span><span><i style="background:var(--unk)"></i>unknown / not a picture</span></div></section>
</div><div><section><h2>Newest pictures</h2><div class="grid" id="recent"></div></section></div></main>
<div id="modal"><div class="box"><h2 id="m-title">Approve</h2>
<p style="color:var(--dim);margin-top:0">Copies the picture into the game folder with its provenance. Nothing is copied until you press Confirm.</p>
<label>What is it for? (a wanted name)</label><input id="m-name" list="wanted" placeholder="e.g. scenes/town_square  or  vignettes/intro/01_title"><datalist id="wanted"></datalist>
<div id="m-pickrow" style="margin-top:8px"><label>Which picture</label><select id="m-pick"></select></div>
<label style="display:block;margin-top:8px"><input type="checkbox" id="m-set" style="width:auto"> the whole scene set (painting, normals, glow, planes, depth)</label>
<div id="m-out"></div>
<div style="display:flex;gap:10px;margin-top:10px"><button onclick="approve(true)">Check</button><button class="go" id="m-confirm" disabled onclick="approve(false)">Confirm</button><span style="flex:1"></span><button onclick="closeModal()">Close</button></div>
</div></div>
<div id="zoom" onclick="this.style.display='none'"><img id="zoom-img"></div>
<div id="ab" onclick="if(event.target.id==='ab')this.style.display='none'" style="position:fixed;inset:0;background:rgba(0,0,0,.92);display:none;z-index:31;overflow:auto;padding:14px">
<div style="display:flex;gap:12px;align-items:flex-start"><div style="flex:1"><div id="ab-la"></div><img id="ab-a" style="width:100%"></div><div style="flex:1"><div id="ab-lb"></div><img id="ab-b" style="width:100%"></div></div>
<table id="ab-diff" style="max-width:1100px;background:var(--panel)"></table><button onclick="document.getElementById('ab').style.display='none'">Close</button></div>
<script>
let S=null, M=null;
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function refresh(){try{const r=await fetch('/api/state');S=await r.json();draw();}catch(e){document.getElementById('clock').textContent='offline';}}
function draw(){const c=S.counts;
 T('c-pend',`queued ${c.pending}`+(c.paused?` · paused ${c.paused}`:''));T('c-run',`rendering ${c.running}`);T('c-done',`done ${c.done}`);T('c-fail',`failed ${c.failed}`);
 T('c-eta',`ETA ${S.eta.human}`);document.getElementById('c-eta').title=S.eta.based_on;T('clock',S.time);
 H('now',S.running.length?S.running.map(j=>`<div class="now" style="border-color:${col(j.type)}"><b>${esc(j.name)}</b><br><span style="color:var(--dim)">${esc(j.type)} · ${esc(j.batch||'')} · started ${esc((j.started||'').slice(11))}</span></div>`).join(''):'<span style="color:var(--dim)">nothing — the worker is idle or not running (run_worker.bat)</span>');
 H('batches',S.batches.map(b=>{const t=b.done+b.failed+b.running+b.pending+b.paused||1,p=x=>(100*x/t).toFixed(1)+'%';
  return `<div class="batch">${esc(b.name)} <small>${b.done}/${t} done${b.failed?` · ${b.failed} failed`:''}${b.pending?` · ${b.pending} to go`:''}</small><div class="bar"><i class="b-done" style="width:${p(b.done)}"></i><i class="b-fail" style="width:${p(b.failed)}"></i><i class="b-run" style="width:${p(b.running)}"></i><i class="b-pause" style="width:${p(b.paused)}"></i></div></div>`}).join('')||'<span style="color:var(--dim)">no recent batches</span>');
 H('failed',S.failed.map(f=>`<div class="fail"><b>${esc(f.name)}</b> <span style="color:var(--dim)">${esc(f.type)} · ${esc(f.batch||'')}</span><pre>${esc(f.error)}</pre><button onclick="act('retry',{id:'${esc(f.id)}'})">Retry</button></div>`).join('')||'<span style="color:var(--dim)">none</span>');
 H('recent',S.recent.map((j,i)=>`<div class="card ${j.licence}"><div class="edge" style="background:${col(j.type)}"></div>${j.image?`<img loading="lazy" src="/thumb?p=${encodeURIComponent(j.image)}" onclick="zoom('${encodeURIComponent(j.image)}')">`:''}<div class="meta"><b>${esc(j.name)}</b><span>${esc(j.type)} · ${esc((j.finished||'').slice(11,16))}</span>${kitDot(j)}<br><button onclick="openApprove(${i})">Approve…</button> <label style="font-size:12px"><input type="checkbox" ${AB.includes(j.id)?'checked':''} onchange="pickAB('${esc(j.id)}',this.checked)" style="width:auto"> A/B</label></div></div>`).join(''));
 H('upnext',(S.now_batch?`running: <b>${esc(S.now_batch)}</b>`:'')+(S.upcoming&&S.upcoming.length?` · then: ${S.upcoming.map(esc).join(' → ')}`:''));
 H('legend',Object.entries(S.colours).map(([k,v])=>`<span><i style="background:${v}"></i>${k}</span>`).join(''));
 const g=document.getElementById('guard');g.style.display=S.guard?'block':'none';g.textContent=S.guard||'';
 H('called',(S.called_out||[]).map(d=>`<div class="fail"><b>${esc(d.wanted)}</b> <span style="color:var(--dim)">${esc(d.type)} · ${esc(d.why||'')}</span><pre>${esc(d.note||'')}</pre><button onclick="act('draft_submit',{draft:'${esc(d.draft)}'})" ${d.ready?'':'disabled title="Fable fills the mask and prompt first"'}>Approve draft</button> <button onclick="act('draft_dismiss',{draft:'${esc(d.draft)}'})">Dismiss</button> <button onclick="act('draft_himself',{draft:'${esc(d.draft)}'})">He'll fix it himself</button></div>`).join('')||'<span style="color:var(--dim)">nothing called out</span>');}
const T=(id,t)=>document.getElementById(id).textContent=t, H=(id,h)=>{const e=document.getElementById(id);if(e.innerHTML!==h)e.innerHTML=h;}, col=t=>(S.colours[t]||'#888');
const KC={pass:'var(--ok)',warn:'#e0a838',fail:'var(--no)'};
function kitDot(j){if(!j.check)return '';const c=j.check;return ` <span title="kit check: ${esc(c.verdict)} — click for the sheet" style="cursor:pointer;color:${KC[c.verdict]||'#888'}" ${c.image?`onclick="zoom('${encodeURIComponent(c.image)}')"`:''}>● kit ${esc(c.verdict)}</span>`;}
let AB=[];function pickAB(id,on){AB=AB.filter(x=>x!==id);if(on)AB.push(id);if(AB.length>2)AB=AB.slice(-2);document.getElementById('ab-btn').disabled=AB.length!==2;draw();}
async function openAB(){const [a,b]=await Promise.all(AB.map(id=>fetch('/api/job?id='+encodeURIComponent(id)).then(r=>r.json())));
 const ra=S.recent.find(x=>x.id===a.id),rb=S.recent.find(x=>x.id===b.id);
 document.getElementById('ab-a').src='/full?p='+encodeURIComponent(ra.image);document.getElementById('ab-b').src='/full?p='+encodeURIComponent(rb.image);
 document.getElementById('ab-la').innerHTML='<b>A</b> '+esc(a.name);document.getElementById('ab-lb').innerHTML='<b>B</b> '+esc(b.name);
 const skip=new Set(['id','name','submitted_at','started_at','finished_at','result']);const keys=[...new Set([...Object.keys(a),...Object.keys(b)])].filter(k=>!skip.has(k)).sort();
 const v=x=>x===undefined?'—':esc(typeof x==='object'?JSON.stringify(x):x);
 document.getElementById('ab-diff').innerHTML='<tr><th>field</th><th>A</th><th>B</th></tr>'+keys.filter(k=>JSON.stringify(a[k])!==JSON.stringify(b[k])).map(k=>`<tr><td>${esc(k)}</td><td>${v(a[k])}</td><td>${v(b[k])}</td></tr>`).join('')||'<tr><td>no differences in the job fields</td></tr>';
 document.getElementById('ab').style.display='block';}
function zoom(p){document.getElementById('zoom-img').src='/full?p='+p;document.getElementById('zoom').style.display='flex';}
async function post(a,b){const r=await fetch('/api/act/'+a,{method:'POST',headers:{'Content-Type':'application/json','X-Forge':'1'},body:JSON.stringify(b)});return r.json();}
async function act(a,b){const r=await post(a,b);alert(r.message);refresh();}
async function openApprove(i){M=S.recent[i];document.getElementById('m-title').textContent='Approve '+M.name;
 const w=await (await fetch('/api/wanted')).json();document.getElementById('wanted').innerHTML=w.map(n=>`<option value="${esc(n)}">`).join('');
 const outs=M.outputs.filter(o=>o.toLowerCase().endsWith('.png'));document.getElementById('m-pick').innerHTML=outs.map((o,k)=>`<option value="${k+1}">${esc(o)}</option>`).join('');
 document.getElementById('m-pickrow').style.display=outs.length>1&&!M.set?'block':'none';document.getElementById('m-set').checked=M.set;
 document.getElementById('m-out').innerHTML='';document.getElementById('m-confirm').disabled=true;document.getElementById('modal').style.display='flex';}
function closeModal(){document.getElementById('modal').style.display='none';}
async function approve(dry){const body={id:M.id,name:document.getElementById('m-name').value,set:document.getElementById('m-set').checked,dry_run:dry};
 if(document.getElementById('m-pickrow').style.display!=='none')body.pick=document.getElementById('m-pick').value;
 const r=await post('approve',body);let h=`<div class="msg ${r.ok?'ok':'no'}">${esc(r.message)}</div>`;
 if(r.rows)h+=`<table><tr><th></th><th>file</th><th>size</th><th>goes to</th></tr>`+r.rows.map(x=>`<tr><td>${esc(x.what)}</td><td>${esc(x.file)}</td><td>${x.size?x.size.join('×'):''}</td><td>${esc(x.dest)}</td></tr>`).join('')+'</table>';
 if(r.licences)h+=`<table><tr><th>role</th><th>model</th><th>licence</th></tr>`+r.licences.map(c=>`<tr><td>${esc(c.role)}</td><td>${esc(c.file)}</td><td>${esc(c.license)}</td></tr>`).join('')+'</table>';
 (r.conditions||[]).forEach(c=>h+=`<div class="cond">⚠ condition: ${esc(c)}</div>`);if(r.note)h+=`<div style="color:var(--dim)">${esc(r.note)}</div>`;
 document.getElementById('m-out').innerHTML=h;document.getElementById('m-confirm').disabled=!(r.ok&&r.dry_run);if(r.ok&&!r.dry_run)refresh();}
refresh();setInterval(refresh,5000);
</script></body></html>"""
