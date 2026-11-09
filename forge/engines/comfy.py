"""ComfyUI driver: fill a workflow template, queue it, wait, fetch the images.

Workflows live in forge/engines/workflows/<name>.json in ComfyUI's **API format** (in ComfyUI:
Settings → enable Dev mode → "Save (API format)"). Any string value of the form "{{key}}" is replaced
from the params; "{{key:int}}" / "{{key:float}}" are typed. So a new model only needs a new exported
workflow with the placeholders dropped in — no Python.
"""
from __future__ import annotations
import copy, json, random, re, time, uuid
from pathlib import Path
from typing import Any
import urllib.request, urllib.parse, urllib.error

from ..log import get

log = get("comfy")
WORKFLOWS = Path(__file__).parent / "workflows"
_PH = re.compile(r"^\{\{(\w+)(?::(int|float|str))?\}\}$")


def list_workflows() -> list[str]:
    return sorted(p.stem for p in WORKFLOWS.glob("*.json"))


def load_workflow(name: str) -> dict:
    p = WORKFLOWS / f"{name}.json"
    if not p.exists():
        raise FileNotFoundError(f"workflow '{name}' not found; have: {', '.join(list_workflows())}")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def fill(template: dict, params: dict[str, Any]) -> dict:
    """Replace {{placeholders}} anywhere in the workflow. Unfilled placeholders raise."""
    missing: list[str] = []

    def walk(v):
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, str):
            m = _PH.match(v)
            if m:
                key, typ = m.group(1), m.group(2)
                if key not in params or params[key] is None:
                    missing.append(key)
                    return v
                val = params[key]
                if typ == "int":
                    return int(val)
                if typ == "float":
                    return float(val)
                return str(val) if typ == "str" else val
            # inline substitution inside longer strings: "{{style_prefix}} {{prompt}}"
            if "{{" in v:
                def rep(mm):
                    k = mm.group(1)
                    if k not in params or params[k] is None:
                        return ""
                    return str(params[k])
                return re.sub(r"\{\{(\w+)(?::\w+)?\}\}", rep, v)
        return v

    out = walk(copy.deepcopy(template))
    if missing:
        raise ValueError("workflow is missing params: " + ", ".join(sorted(set(missing))))
    return out


class ComfyClient:
    def __init__(self, url: str = "http://127.0.0.1:8188", timeout_sec: int = 1800, poll_sec: float = 1.0):
        self.url = url.rstrip("/")
        self.timeout = timeout_sec
        self.poll = poll_sec
        self.client_id = uuid.uuid4().hex

    # ------------------------------------------------------------ http
    def _get(self, path: str, timeout: float = 10.0) -> Any:
        with urllib.request.urlopen(self.url + path, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _post(self, path: str, body: dict, timeout: float = 30.0) -> Any:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.url + path, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def is_up(self) -> bool:
        try:
            self._get("/system_stats", timeout=3.0)
            return True
        except Exception:
            return False

    def system_stats(self) -> dict:
        return self._get("/system_stats")

    # ------------------------------------------------------------ running
    def queue(self, workflow: dict) -> str:
        res = self._post("/prompt", {"prompt": workflow, "client_id": self.client_id})
        if "error" in res:
            raise RuntimeError(f"ComfyUI rejected the workflow: {res['error']} {res.get('node_errors', '')}")
        return res["prompt_id"]

    def wait(self, prompt_id: str) -> dict:
        """Poll /history until the prompt finishes. Returns the history entry (outputs by node)."""
        t0 = time.time()
        while time.time() - t0 < self.timeout:
            hist = self._get(f"/history/{prompt_id}")
            if prompt_id in hist:
                entry = hist[prompt_id]
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    msgs = [m for m in status.get("messages", []) if m and m[0] == "execution_error"]
                    raise RuntimeError(f"ComfyUI execution error: {msgs[-1][1].get('exception_message') if msgs else 'unknown'}")
                return entry
            time.sleep(self.poll)
        raise TimeoutError(f"ComfyUI did not finish prompt {prompt_id} within {self.timeout}s")

    def fetch_image(self, filename: str, subfolder: str = "", type_: str = "output") -> bytes:
        q = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder, "type": type_})
        with urllib.request.urlopen(f"{self.url}/view?{q}", timeout=60) as r:
            return r.read()

    def object_info(self) -> dict:
        """Every node type this ComfyUI knows, with its inputs (used to fill custom nodes and by doctor)."""
        return self._get("/object_info", timeout=60.0)

    def upload_image(self, path, subfolder: str = "forge", name: str | None = None) -> str:
        """Put a local picture into ComfyUI's input folder (POST /upload/image) and return the name LoadImage wants
        ('forge/<file>'). Works whether ComfyUI runs here or elsewhere."""
        p = Path(path)
        fname = name or p.name
        boundary = "----forge" + uuid.uuid4().hex
        data = p.read_bytes()
        parts = []
        for key, val in (("subfolder", subfolder), ("type", "input"), ("overwrite", "true")):
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{val}\r\n".encode("utf-8"))
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{fname}\"\r\n"
                     f"Content-Type: image/png\r\n\r\n".encode("utf-8") + data + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        req = urllib.request.Request(self.url + "/upload/image", data=b"".join(parts),
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            res = json.loads(r.read().decode("utf-8"))
        sub = res.get("subfolder") or ""
        return f"{sub}/{res['name']}" if sub else res["name"]

    def run_by_node(self, workflow: dict) -> dict[str, list[bytes]]:
        """Queue → wait → {save-node id: [PNG bytes, …]} so a graph with two SaveImage nodes (raw + final) can tell
        them apart."""
        pid = self.queue(workflow)
        log.debug("queued prompt %s", pid)
        entry = self.wait(pid)
        out: dict[str, list[bytes]] = {}
        for node_id, o in entry.get("outputs", {}).items():
            for im in o.get("images", []):
                if im.get("type") == "output":
                    out.setdefault(str(node_id), []).append(self.fetch_image(im["filename"], im.get("subfolder", ""), im["type"]))
        if not out:
            raise RuntimeError("ComfyUI finished but produced no output images (is there a SaveImage node?)")
        return out

    def run(self, workflow: dict) -> list[bytes]:
        """Queue → wait → return every output image as PNG bytes, in node order."""
        pid = self.queue(workflow)
        log.debug("queued prompt %s", pid)
        entry = self.wait(pid)
        images: list[bytes] = []
        for node_id, out in entry.get("outputs", {}).items():
            for im in out.get("images", []):
                if im.get("type") == "output":
                    images.append(self.fetch_image(im["filename"], im.get("subfolder", ""), im["type"]))
        if not images:
            raise RuntimeError("ComfyUI finished but produced no output images (is there a SaveImage node?)")
        return images


def txt2img(client: ComfyClient, workflow_name: str, prompt: str, negative: str, seed: int, width: int,
            height: int, steps: int, cfg: float, checkpoint: str, batch: int = 1, extra: dict | None = None) -> list[bytes]:
    """The common call every GPU handler makes. seed < 0 → random (recorded by the caller)."""
    if seed is None or seed < 0:
        seed = random.randint(0, 2**31 - 1)
    params = {"prompt": prompt, "negative": negative, "seed": seed, "width": width, "height": height,
              "steps": steps, "cfg": cfg, "checkpoint": checkpoint, "batch": batch}
    if extra:
        params.update(extra)
    wf = fill(load_workflow(workflow_name), params)
    log.info("txt2img %s %dx%d seed %d steps %d — %s", workflow_name, width, height, seed, steps, prompt[:80])
    return client.run(wf)
