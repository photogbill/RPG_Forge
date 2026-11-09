"""Bake-off detail crops: move them without re-rendering, and find the faces (roadmap N6).

    bakeoff report <suite> --detail-at <prompt>=x,y[,size]   centre the 1:1 detail crop of one picture at the fractional
                                                            point (x, y) — saved to out/bakeoff/<suite>/detail_at.json,
                                                            so every later report keeps it
    bakeoff report <suite> --detail-auto                    centre each picture's crop on its largest face — only if
                                                            ComfyUI is up and the Impact Pack's detector is installed
                                                            (face_yolov8m, Apache-2.0); otherwise it says so and keeps
                                                            the centre

The face search runs one small graph per picture through ComfyUI (LoadImage → UltralyticsDetectorProvider →
BboxDetectorSEGS → SegsToCombinedMask → MaskToImage → SaveImage; node names read from the installed Impact Pack)
and takes the largest blob of the mask. Results are written into detail_at.json like a manual override (marked
"auto"), so a manual --detail-at always wins over a later --detail-auto.
"""
from __future__ import annotations
import io, json
from pathlib import Path

import numpy as np
from PIL import Image

from . import config as cfgmod

FACE_NODES = ("UltralyticsDetectorProvider", "BboxDetectorSEGS", "SegsToCombinedMask", "MaskToImage")


def path(suite: str) -> Path:
    return cfgmod.ROOT / "out" / "bakeoff" / suite / "detail_at.json"


def load(suite: str) -> dict:
    p = path(suite)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        return {}


def save(suite: str, data: dict) -> Path:
    p = path(suite)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1), encoding="utf-8", newline="\n")
    return p


def parse_at(text: str) -> tuple[str, dict]:
    """'juke_joint=0.42,0.35' or 'juke_joint=0.42,0.35,640' → ('juke_joint', {"at": [0.42, 0.35], "size": 640})."""
    if "=" not in text:
        raise ValueError(f"--detail-at wants <prompt>=x,y[,size], got '{text}'")
    pid, rest = text.split("=", 1)
    nums = [x.strip() for x in rest.split(",") if x.strip()]
    if len(nums) not in (2, 3):
        raise ValueError(f"--detail-at wants two fractions and an optional size, got '{rest}'")
    x, y = float(nums[0]), float(nums[1])
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        raise ValueError(f"x and y are fractions of the picture (0..1), got {x}, {y}")
    out = {"at": [round(x, 4), round(y, 4)], "source": "manual"}
    if len(nums) == 3:
        out["size"] = int(float(nums[2]))
    return pid.strip(), out


def set_at(suite: str, text: str) -> tuple[str, dict]:
    pid, rec = parse_at(text)
    d = load(suite)
    d[pid] = rec
    save(suite, d)
    return pid, rec


def apply(suite: str, rows: list[dict]) -> int:
    """Override meta.detail of the suite's rows from detail_at.json (in place). Returns how many rows changed.
    Only rows that already have a detail crop are touched — a suite without detail_crop gets no detail sheets."""
    d = load(suite)
    n = 0
    for r in rows:
        m = r.get("meta") or {}
        det = m.get("detail")
        if not isinstance(det, dict):
            continue
        o = d.get(str(m.get("prompt_id")))
        if not o:
            continue
        m["detail"] = {**det, "at": list(o["at"]), **({"size": int(o["size"])} if o.get("size") else {})}
        n += 1
    return n


# ------------------------------------------------------------------ faces
def face_graph(image_name: str, detector: str = "bbox/face_yolov8m.pt", threshold: float = 0.4) -> dict:
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "2": {"class_type": "UltralyticsDetectorProvider", "inputs": {"model_name": detector}},
        "3": {"class_type": "BboxDetectorSEGS", "inputs": {"bbox_detector": ["2", 0], "image": ["1", 0], "threshold": threshold,
                                                           "dilation": 0, "crop_factor": 1.0, "drop_size": 10, "labels": "all"}},
        "4": {"class_type": "SegsToCombinedMask", "inputs": {"segs": ["3", 0]}},
        "5": {"class_type": "MaskToImage", "inputs": {"mask": ["4", 0]}},
        "6": {"class_type": "SaveImage", "inputs": {"filename_prefix": "forge_faces", "images": ["5", 0]}},
    }


def largest_blob_centre(mask: Image.Image, grid: int = 160) -> tuple[float, float, float] | None:
    """(x, y, area fraction) of the largest connected bright region, as fractions of the picture; None if empty.
    Works on a coarse grid (connected components by flood fill) — a face box is large enough for that."""
    m = mask.convert("L")
    w, h = m.size
    s = grid / max(w, h)
    small = np.asarray(m.resize((max(1, int(w * s)), max(1, int(h * s))), Image.BILINEAR)) > 127
    H, W = small.shape
    seen = np.zeros_like(small, bool)
    best = None
    for y0 in range(H):
        for x0 in range(W):
            if not small[y0, x0] or seen[y0, x0]:
                continue
            stack, pts = [(y0, x0)], []
            seen[y0, x0] = True
            while stack:
                y, x = stack.pop()
                pts.append((y, x))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < H and 0 <= nx < W and small[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if best is None or len(pts) > len(best):
                best = pts
    if not best:
        return None
    ys, xs = zip(*best)
    return (float(np.mean(xs) + 0.5) / W, float(np.mean(ys) + 0.5) / H, len(best) / float(H * W))


def auto(suite: str, rows: list[dict], client) -> list[str]:
    """Centre each picture's crop on its largest face. One face search per prompt id (on the first finished image
    that has a detail crop). Writes detail_at.json (manual entries are never replaced). Returns report lines."""
    if client is None or not client.is_up():
        return ["detail-auto: ComfyUI is not running — crops stay where they were (start run_worker.bat and run the report again)"]
    try:
        info = client.object_info()
    except Exception as e:  # noqa: BLE001
        return [f"detail-auto: could not read ComfyUI's node list ({e}) — crops stay where they were"]
    missing = [n for n in FACE_NODES if n not in info]
    if missing:
        return [f"detail-auto: {', '.join(missing)} not installed (install_comfy_faces.bat) — crops stay where they were"]
    d = load(suite)
    lines, done = [], set()
    for r in rows:
        m = r.get("meta") or {}
        pid = str(m.get("prompt_id"))
        if pid in done or not isinstance(m.get("detail"), dict) or not r.get("image"):
            continue
        done.add(pid)
        if (d.get(pid) or {}).get("source") == "manual":
            lines.append(f"  {pid}: kept the manual crop at {d[pid]['at']}")
            continue
        try:
            name = client.upload_image(r["image"], name=f"faces_{suite}_{pid}.png")
            res = client.run_by_node(face_graph(name))
            got = res.get("6") or next(iter(res.values()))
            c = largest_blob_centre(Image.open(io.BytesIO(got[0])))
        except Exception as e:  # noqa: BLE001
            lines.append(f"  {pid}: face search failed ({type(e).__name__}: {e}) — centre kept")
            continue
        if c is None:
            lines.append(f"  {pid}: no face found — centre kept")
            continue
        d[pid] = {"at": [round(c[0], 4), round(c[1], 4)], "source": "auto", "face_area": round(c[2], 4)}
        lines.append(f"  {pid}: centred on the largest face at {d[pid]['at']}")
    save(suite, d)
    return ["detail-auto:"] + lines
