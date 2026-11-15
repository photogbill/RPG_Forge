"""Talking to a ComfyUI for the 3D steps: send a request, wait for it, keep its own words when it says no, and find the
file it saved. One set of helpers for both ComfyUIs (the art one on 8188 and the rigging one on 8189), from the first
game's trellis_trial.py and rig_trial.py, where they were proven.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

MEMORY_WORDS = ("out of memory", "outofmemory", "oom", "allocat", "cuda error", "not enough memory", "paging file")


def get(url: str, path: str = "", timeout: float = 30.0):
    with urllib.request.urlopen(url.rstrip("/") + path, timeout=timeout) as r:
        raw = r.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}


def post(url: str, path: str, body: dict, timeout: float = 60.0) -> dict:
    """POST, and when ComfyUI says no, keep what it said (it answers 400 with the reasons in the body)."""
    req = urllib.request.Request(url.rstrip("/") + path, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return {"http_error": e.code, **json.loads(raw)}
        except Exception:
            return {"http_error": e.code, "error": raw[:4000]}


def is_up(url: str, timeout: float = 4.0) -> bool:
    try:
        get(url, "/system_stats", timeout=timeout)
        return True
    except Exception:
        return False


def queue_count(url: str, timeout: float = 8.0) -> int | None:
    """How many requests the ComfyUI has running or waiting; None when it is not answering at all."""
    try:
        q = get(url, "/queue", timeout=timeout)
        return len(q.get("queue_running") or []) + len(q.get("queue_pending") or [])
    except Exception:
        return None


def free(url: str) -> None:
    """Ask it to put its models away (frees the card for the other ComfyUI)."""
    post(url, "/free", {"unload_models": True, "free_memory": True})
    time.sleep(1)


def memory_line(url: str) -> str:
    try:
        s = get(url, "/system_stats", timeout=10)
        d = (s.get("devices") or [{}])[0]
        return "vram free %.1f of %.1f GB, ram free %.1f GB" % (d.get("vram_free", 0) / 2**30, d.get("vram_total", 0) / 2**30,
                                                               s.get("system", {}).get("ram_free", 0) / 2**30)
    except Exception as e:                                     # the figures are only for the log
        return f"(no memory figures: {e})"


def error_words(status: dict) -> str:
    """ComfyUI's own account of a failed request: the node, the exception and the last lines of its traceback."""
    lines = []
    for kind, data in status.get("messages") or []:
        if kind == "execution_error" and isinstance(data, dict):
            lines.append(f"{data.get('node_type')} (node {data.get('node_id')}): {data.get('exception_type')}: "
                         f"{data.get('exception_message')}")
            lines.extend(str(x).rstrip() for x in (data.get("traceback") or [])[-25:])
    return "\n".join(lines) or json.dumps(status)[:4000]


def run(url: str, prompt: dict, timeout_sec: int, poll: float = 2.0, on_wait=None) -> dict:
    """Send one request and wait for it. Returns the history entry; raises with ComfyUI's own words on failure,
    TimeoutError (after interrupting it and clearing its queue) when it takes longer than timeout_sec.
    `on_wait()` is called while waiting (the card lock's heartbeat)."""
    res = post(url, "/prompt", {"prompt": prompt, "client_id": uuid.uuid4().hex})
    if "prompt_id" not in res:
        raise RuntimeError("ComfyUI would not take the request: " + json.dumps(res, ensure_ascii=False)[:6000])
    pid = res["prompt_id"]
    t0 = time.time()
    while time.time() - t0 < timeout_sec:
        time.sleep(poll)
        if on_wait:
            on_wait()
        try:
            hist = get(url, f"/history/{pid}", timeout=60)
        except Exception:
            continue
        entry = hist.get(pid)
        if not entry:
            continue
        status = entry.get("status") or {}
        if status.get("status_str") == "error":
            raise RuntimeError("ComfyUI reported an error:\n" + error_words(status))
        if status.get("completed") or status.get("status_str") == "success":
            return entry
    post(url, "/interrupt", {})
    post(url, "/queue", {"clear": True})
    raise TimeoutError(f"no answer after {timeout_sec // 60} minutes; the request was interrupted")


def is_memory_or_time(e: Exception) -> bool:
    """A failure a smaller setting might get past (out of memory, too slow) — anything else would fail the same way."""
    return isinstance(e, TimeoutError) or any(w in str(e).lower() for w in MEMORY_WORDS)


def output_files(entry: dict, exts: tuple[str, ...]) -> list[dict]:
    """Every file a finished request reports, of the given kinds: [{filename, subfolder, type}]."""
    found = []

    def walk(v):
        if isinstance(v, dict):
            name = v.get("filename") or v.get("file") or v.get("name")
            if isinstance(name, str) and name.lower().endswith(exts):
                found.append({"filename": name, "subfolder": v.get("subfolder", ""), "type": v.get("type", "output")})
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str) and v.lower().endswith(exts):
            p = Path(v.replace("\\", "/"))
            found.append({"filename": p.name, "subfolder": str(p.parent).replace("\\", "/").strip("."), "type": "output"})

    walk(entry.get("outputs") or {})
    return found


def fetch(url: str, f: dict, timeout: float = 300) -> bytes:
    q = urllib.parse.urlencode({"filename": f["filename"], "subfolder": f.get("subfolder", ""), "type": f.get("type", "output")})
    with urllib.request.urlopen(f"{url.rstrip('/')}/view?{q}", timeout=timeout) as r:
        return r.read()


def newest_under(folder: Path, prefix: str, exts: tuple[str, ...], since: float) -> Path | None:
    """The newest file of the given kinds a ComfyUI wrote under <its output folder>/<prefix>* since a time."""
    base = (Path(folder) / prefix).parent
    stem = Path(prefix).name
    if not base.is_dir():
        return None
    found = [p for p in base.glob(stem + "*") if p.suffix.lower() in exts and p.stat().st_mtime >= since - 5]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def collect(url: str, entry: dict, prefix: str, exts: tuple[str, ...], local_out: Path | None, since: float, target: Path) -> Path:
    """Put the file a finished request made at `target`: from ComfyUI's own output folder when it is on this computer
    (fast, no copy over the network), else downloaded through /view. Raises when there is none."""
    import shutil
    if local_out is not None:
        made = newest_under(local_out, prefix, exts, since)
        if made is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(made, target)
            return target
    named = [f for f in output_files(entry, exts) if Path(f["filename"]).name.startswith(Path(prefix).name)]
    for f in named or output_files(entry, exts):
        data = fetch(url, f)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target
    raise RuntimeError(f"ComfyUI finished but no {'/'.join(exts)} file was found for {prefix} - its answer: "
                       + json.dumps(entry.get("outputs", {}))[:1500])


def object_info(url: str, timeout: float = 300) -> dict:
    return get(url, "/object_info", timeout=timeout)


def check_against(prompt: dict, info: dict) -> list[str]:
    """Compare a request with what the running ComfyUI says its nodes take; return what does not fit."""
    bad = []
    for nid, node in prompt.items():
        spec = info.get(node["class_type"])
        if spec is None:
            bad.append(f"node {nid}: ComfyUI has no node called {node['class_type']}")
            continue
        known = {**(spec.get("input", {}).get("required") or {}), **(spec.get("input", {}).get("optional") or {})}
        for key, val in node["inputs"].items():
            if key not in known:
                if "." in key and key.split(".")[0] in known:          # a dynamic choice's own setting
                    continue
                bad.append(f"node {nid} ({node['class_type']}): no input called {key}")
                continue
            kind = known[key][0]
            extra = known[key][1] if len(known[key]) > 1 and isinstance(known[key][1], dict) else {}
            options = kind if isinstance(kind, list) else extra.get("options")
            if options and isinstance(options[0], str) and not isinstance(val, list) and val not in options:
                bad.append(f"node {nid} ({node['class_type']}): {key} = {val!r} is not one of {options[:12]}")
    return bad
