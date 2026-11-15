"""A stand-in ComfyUI: answers the doors the 3D steps use, the way the real one does, and writes the files a real run
would — so the whole line (picture -> body -> skeleton -> motions) can be tested on any computer, with no graphics
card, at every push. Fable first tested the overnight line this way on 2026-11-13 (a forty-line server with planted
failures); this is that server, kept in the forge.

    python -m forge.threed.standin --kind art|rig --port 8288 --root <folder> [--delay 0.2]

Doors: GET /system_stats /object_info /queue /history/<id> /view;  POST /prompt /queue /interrupt /free /upload/image.
`--kind art` knows the image-to-3D template's nodes (standin_info_art.json, built from two real requests) and any
picture graph (it paints a flat figure for every SaveImage); `--kind rig` knows the rigging pack's nodes
(standin_info_rig.json, read from the real rigging ComfyUI on 2026-11-13), and its mesh list is its own input folder.

Planted failures — a word anywhere in a request's text decides what happens to it:
    PLANT_FAIL    the request fails with an execution error (a node, an exception, a traceback)
    PLANT_OOM     it fails with "CUDA out of memory" (a lower resolution should then be tried)
    PLANT_OOM_ONCE  the first such request runs out of memory, the next one goes through
    PLANT_HANG    it never finishes (the caller's time limit must stop it)
    PLANT_NOFILE  it finishes but saves nothing
    PLANT_SLOW    it takes four times as long
Nothing here talks to a real ComfyUI or touches a graphics card.
"""
from __future__ import annotations

import io
import json
import re
import struct
import sys
import threading
import time
import uuid
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
PLANTS = ("PLANT_OOM_ONCE", "PLANT_FAIL", "PLANT_OOM", "PLANT_HANG", "PLANT_NOFILE", "PLANT_SLOW")


def _seg(px: float, py: float, a: tuple, b: tuple) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / max(dx * dx + dy * dy, 1e-9)))
    return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5


def png(w: int = 128, h: int = 128, rgb=(150, 150, 160), arm_deg: float = 45.0, arms: str = "both", head: float = 0.062,
        forearm: bool = True) -> bytes:
    """A small PNG without any picture library: a grey card with a darker standing figure in an A-pose, with an adult's
    proportions (head about one seventh of the height), so the picture gate (BUILD 40) sees a good picture."""
    import math
    rows = []
    top, H, cx = h * 0.05, h * 0.9, w / 2
    head_r = head * H
    head_c = (cx, top + head_r * 1.05)
    sh_y = head_c[1] + head_r + 0.04 * H
    hip_y = sh_y + 0.33 * H
    a = math.radians(arm_deg)
    sides = {"both": (-1, 1), "left": (-1,), "right": (1,)}[arms]
    arms = [((cx + s * 0.10 * H, sh_y + 0.02 * H), (cx + s * (0.10 * H + 0.31 * H * math.sin(a)), sh_y + 0.02 * H + 0.31 * H * math.cos(a)))
            for s in sides]
    if not forearm and len(arms) == 2:          # the left arm ends just below the elbow
        (p0, p1) = arms[0]
        arms[0] = (p0, (p0[0] + (p1[0] - p0[0]) * 0.45, p0[1] + (p1[1] - p0[1]) * 0.45))
    legs = [((cx + s * 0.05 * H, hip_y), (cx + s * 0.065 * H, top + H - 0.02 * H)) for s in (-1, 1)]
    for y in range(h):
        row = bytearray([0])
        for x in range(w):
            px, py = x + 0.5, y + 0.5
            inside = ((px - head_c[0]) ** 2 + (py - head_c[1]) ** 2) ** 0.5 < head_r
            inside |= abs(px - cx) < 0.025 * H and head_c[1] < py < sh_y + 2           # the neck
            if sh_y <= py <= hip_y + 0.03 * H:                                          # the trunk, narrowing to the hips
                f = (py - sh_y) / (hip_y - sh_y)
                inside |= abs(px - cx) < (0.105 - 0.025 * min(f, 1.0)) * H
            inside |= any(_seg(px, py, p, q) < 0.026 * H for p, q in arms)
            inside |= any(_seg(px, py, p, q) < 0.04 * H for p, q in legs)
            row += bytes((60, 60, 70) if inside else rgb)
        rows.append(bytes(row))
    raw = zlib.compress(b"".join(rows))

    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")


class StandIn:
    """The state of one stand-in ComfyUI: its folders, its queue, its history."""

    def __init__(self, root: Path, kind: str = "art", delay: float = 0.2):
        self.root = Path(root)
        self.kind = kind
        self.delay = float(delay)
        self.input = self.root / "input"
        self.output = self.root / "output"
        self.input.mkdir(parents=True, exist_ok=True)
        self.output.mkdir(parents=True, exist_ok=True)
        info_file = HERE / ("standin_info_rig.json" if kind == "rig" else "standin_info_art.json")
        self.info = json.loads(info_file.read_text(encoding="utf-8"))
        self.history: dict[str, dict] = {}
        self.running: list[str] = []
        self.lock = threading.Lock()
        self.seen: list[dict] = []                    # every request taken, for the tests to read
        self.interrupted = 0
        self.freed = 0
        self.counter = 0
        self.oom_once_spent = False

    # ------------------------------------------------------------------ what it knows
    def object_info(self) -> dict:
        info = json.loads(json.dumps(self.info))
        if "UniRigLoadMesh" in info:
            meshes = sorted(p.relative_to(self.input).as_posix() for p in self.input.rglob("*")
                            if p.suffix.lower() in (".glb", ".gltf", ".obj", ".fbx"))
            info["UniRigLoadMesh"]["input"]["required"]["file_path"][1]["options"] = meshes
        return info

    # ------------------------------------------------------------------ taking a request
    def take(self, prompt: dict) -> dict:
        text = json.dumps(prompt)
        bad = [f"node {nid}: no node called {n.get('class_type')}" for nid, n in prompt.items()
               if self.kind == "rig" and n.get("class_type") not in self.info]
        if bad:
            return {"error": {"type": "invalid_prompt", "message": "; ".join(bad)}, "node_errors": {}}
        pid = uuid.uuid4().hex
        with self.lock:
            self.seen.append(prompt)
            self.running.append(pid)
        plant = next((p for p in PLANTS if p in text), None)
        threading.Thread(target=self._work, args=(pid, prompt, plant), daemon=True).start()
        return {"prompt_id": pid, "number": len(self.seen), "node_errors": {}}

    def _next(self) -> int:
        with self.lock:
            self.counter += 1
            return self.counter

    def _save(self, prefix: str, ext: str, data: bytes) -> dict:
        prefix = prefix.replace("\\", "/")
        sub, stem = (prefix.rsplit("/", 1) if "/" in prefix else ("", prefix))
        name = f"{stem}_{self._next():05d}_{ext}"
        target = self.output / sub / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return {"filename": name, "subfolder": sub, "type": "output"}

    def _work(self, pid: str, prompt: dict, plant: str | None) -> None:
        from . import glb
        time.sleep(self.delay * (4 if plant == "PLANT_SLOW" else 1))
        if plant == "PLANT_HANG":
            while pid in self.running:                   # until interrupted
                time.sleep(0.05)
            self._done(pid, prompt, {}, error=("Interrupted", "processing was interrupted"))
            return
        if plant == "PLANT_OOM_ONCE":
            with self.lock:
                spent, self.oom_once_spent = self.oom_once_spent, True
            plant = None if spent else "PLANT_OOM"
        if plant in ("PLANT_FAIL", "PLANT_OOM"):
            node = next(iter(prompt))
            msg = ("CUDA out of memory. Tried to allocate 2.00 GiB" if plant == "PLANT_OOM"
                   else "a planted failure: the stand-in was asked to fail this request")
            self._done(pid, prompt, {}, error=("torch.OutOfMemoryError" if plant == "PLANT_OOM" else "RuntimeError", msg), node=node)
            return
        outputs: dict = {}
        if plant != "PLANT_NOFILE":
            for nid, n in prompt.items():
                ct, ins = n.get("class_type"), n.get("inputs", {})
                try:
                    if ct == "SaveImage":
                        n = max([int(v) for x in prompt.values() for k, v in x.get("inputs", {}).items()
                                 if k == "batch_size" and isinstance(v, int)] or [1])
                        outputs[nid] = {"images": [self._save(str(ins.get("filename_prefix", "ComfyUI")), ".png",
                                                              png(rgb=(150 + 20 * k % 100, 150, 160 - 15 * k)))
                                                   for k in range(n)]}
                    elif ct == "Save3DAdvanced":
                        buf = io.BytesIO()
                        tmp = self.root / f"_tmp_{pid}.glb"
                        glb.box(tmp, (0.6, 1.0, 0.4))
                        buf.write(tmp.read_bytes())
                        tmp.unlink()
                        outputs[nid] = {"3d": [self._save(str(ins.get("filename_prefix", "3d/ComfyUI")), ".glb", buf.getvalue())]}
                    elif ct == "UniRigLoadMesh":
                        src = self.input / str(ins.get("file_path", ""))
                        if ins.get("source_folder", "input") == "input" and not src.exists():
                            self._done(pid, prompt, {}, error=("FileNotFoundError", f"mesh not found: {src.name}"), node=nid)
                            return
                    elif ct in ("MIAAutoRig", "UniRigAutoRig"):
                        name = str(ins.get("fbx_name") or "rigged")
                        tail = "_mia" if ct == "MIAAutoRig" else "_mixamo"
                        (self.output / f"{name}{tail}.fbx").write_bytes(b"Kaydara FBX Binary  \x00stand-in rig of " + name.encode())
                        glb.box(self.output / f"{name}{tail}.glb", (0.5, 1.75, 0.3), motions=["A_TPose"], joints=3)
                        outputs[nid] = {"text": [f"{name}{tail}.fbx"]}
                    elif ct == "UniRigApplyAnimation":
                        out_name = str(ins.get("output_name") or "animated")
                        (self.output / f"{out_name}.fbx").write_bytes(b"Kaydara FBX Binary  \x00stand-in motion")
                        outputs[nid] = {"text": [f"{out_name}.fbx"]}
                except Exception as e:  # noqa: BLE001 — the stand-in reports its own failures like ComfyUI would
                    self._done(pid, prompt, {}, error=(type(e).__name__, str(e)), node=nid)
                    return
        self._done(pid, prompt, outputs)

    def _done(self, pid: str, prompt: dict, outputs: dict, error: tuple[str, str] | None = None, node: str | None = None) -> None:
        if error:
            nid = node or next(iter(prompt), "0")
            status = {"status_str": "error", "completed": False, "messages": [
                ["execution_start", {"prompt_id": pid}],
                ["execution_error", {"prompt_id": pid, "node_id": nid, "node_type": prompt.get(nid, {}).get("class_type", "?"),
                                     "exception_type": error[0], "exception_message": error[1],
                                     "traceback": ["  File \"stand-in\", line 1, in execute\n", f"{error[0]}: {error[1]}\n"]}]]}
        else:
            status = {"status_str": "success", "completed": True, "messages": [["execution_success", {"prompt_id": pid}]]}
        with self.lock:
            self.history[pid] = {"prompt": [0, pid, prompt, {}, list(prompt)], "outputs": outputs, "status": status}
            if pid in self.running:
                self.running.remove(pid)

    def interrupt(self) -> None:
        with self.lock:
            self.interrupted += 1
            if self.running:
                self.running.pop(0)


def _handler(si: StandIn):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _json(self, obj, code=200):
            b = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path == "/system_stats":
                self._json({"system": {"os": "stand-in", "ram_free": 32 * 2**30, "comfyui_version": "stand-in"},
                            "devices": [{"name": f"stand-in ({si.kind})", "type": "cpu", "vram_total": 16 * 2**30, "vram_free": 15 * 2**30}]})
            elif u.path == "/object_info":
                self._json(si.object_info())
            elif u.path == "/queue":
                self._json({"queue_running": [[0, p] for p in si.running[:1]], "queue_pending": [[0, p] for p in si.running[1:]]})
            elif u.path.startswith("/history/"):
                pid = u.path.rsplit("/", 1)[-1]
                self._json({pid: si.history[pid]} if pid in si.history else {})
            elif u.path == "/history":
                self._json(si.history)
            elif u.path == "/view":
                f = si.output / q.get("subfolder", [""])[0] / q.get("filename", [""])[0]
                if not f.is_file() or si.output.resolve() not in f.resolve().parents:
                    self._json({"error": "not found"}, 404)
                    return
                b = f.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
            else:
                self._json({"error": "no such door"}, 404)

        def do_POST(self):
            u = urlparse(self.path)
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b""
            if u.path == "/prompt":
                r = si.take((json.loads(raw or b"{}") or {}).get("prompt") or {})
                self._json(r, 400 if "error" in r else 200)
            elif u.path == "/interrupt":
                si.interrupt()
                self._json({})
            elif u.path == "/queue":
                self._json({})
            elif u.path == "/free":
                si.freed += 1
                self._json({})
            elif u.path == "/upload/image":
                m = re.search(rb'name="subfolder"\r\n\r\n([^\r]*)\r\n', raw)
                sub = (m.group(1).decode() if m else "")
                m = re.search(rb'name="image"; filename="([^"]+)"\r\nContent-Type: [^\r]*\r\n\r\n', raw)
                if not m:
                    self._json({"error": "no image"}, 400)
                    return
                name = m.group(1).decode()
                start = m.end()
                end = raw.rfind(b"\r\n--", start)
                (si.input / sub).mkdir(parents=True, exist_ok=True)
                (si.input / sub / name).write_bytes(raw[start:end])
                self._json({"name": name, "subfolder": sub, "type": "input"})
            else:
                self._json({"error": "no such door"}, 404)
    return H


def serve(root: Path, kind: str = "art", port: int = 0, delay: float = 0.2) -> tuple[ThreadingHTTPServer, StandIn, str]:
    """Start one in this process (a thread). Returns (server, state, url); server.shutdown() stops it."""
    si = StandIn(root, kind, delay)
    srv = ThreadingHTTPServer(("127.0.0.1", int(port)), _handler(si))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, si, f"http://127.0.0.1:{srv.server_address[1]}"


def main(argv: list[str]) -> int:
    opt = {"--kind": "art", "--port": "8288", "--root": "standin_comfy", "--delay": "0.2"}
    for k in list(opt):
        if k in argv and argv.index(k) + 1 < len(argv):
            opt[k] = argv[argv.index(k) + 1]
    si = StandIn(Path(opt["--root"]), opt["--kind"], float(opt["--delay"]))
    srv = ThreadingHTTPServer(("127.0.0.1", int(opt["--port"])), _handler(si))
    print(f"stand-in ComfyUI ({opt['--kind']}) on http://127.0.0.1:{opt['--port']}, folders in {opt['--root']}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
