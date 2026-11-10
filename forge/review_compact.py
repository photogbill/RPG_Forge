"""Review sheets a model can read (Night 3, G2) — small, labelled, indexed.

    python -m forge review <suite|batch> --compact [--cells 12] [--max-side 2000]
    python -m forge review <suite|batch> --pairs A,B [--crop 640]

Why: a bake-off grid is a 5–10 MB PNG with a hundred cells; a reader that looks at one staged picture at a time
(Claude) cannot see detail at that scale. These sheets hold at most 12 cells, the longest side is ≤ 2,000 px and the
JPEG ≤ 1.5 MB; every cell carries its number and its label *inside the picture* (checkpoint · LoRA · only the tool
fields that differ between the cells of that sheet). One prompt per sheet; a prompt with more cells than fit runs onto
page 2, 3 …  `review_index.json` maps each sheet to its job ids in reading order (cell 1 first), so "cell 7 is the best"
becomes a `bakeoff rate` call with no guessing.

`--pairs A,B` (the finishing bake-off, where the difference is in the detail): for every prompt × checkpoint × LoRA ×
seed that has a cell in category A and in category B, one sheet with the two pictures side by side at full sheet
height and the 1:1 detail crop under each (the crop from the job's meta.detail or the suite's detail_at.json). A and B
may also be two job ids.

Output: out/review/<target>/compact/ (or pairs_<A>_vs_<B>/) — sheet_NNN.jpg + review_index.json.
"""
from __future__ import annotations
import io, json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import config as cfgmod
from .review import collect, safe

MAX_BYTES = 1_500_000
# job fields that never differ meaningfully between cells, or are not "tool" settings
_IGNORE = {"id", "name", "prompt", "negative", "submitted_at", "started_at", "finished_at", "result", "meta", "batch",
           "game", "priority", "retries", "checkpoint", "loras", "seed", "type", "style_prefix", "variants"}


def font(size: int):
    for name in ("DejaVuSans.ttf", "arial.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _short(v) -> str:
    if isinstance(v, bool):
        return "on" if v else "off"
    if isinstance(v, dict):
        return ",".join(f"{k}={_short(x)}" for k, x in sorted(v.items()) if k not in ("_comment",))
    if isinstance(v, list):
        return "x".join(_short(x) for x in v)
    return Path(str(v)).stem if isinstance(v, str) and v.endswith((".safetensors", ".pth", ".ckpt")) else str(v)


def job_of(jobs_dir: Path, jid: str) -> dict:
    for st in ("done", "failed"):
        p = jobs_dir / st / f"{jid}.json"
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                return {}
    return {}


def differing(jobs: list[dict]) -> list[str]:
    """Tool fields whose value is not the same for every job in the list (missing counts as a value)."""
    keys = set()
    for j in jobs:
        keys |= {k for k in j if k not in _IGNORE and not k.startswith("_")}
    out = []
    for k in sorted(keys):
        vals = {json.dumps(j.get(k), sort_keys=True, default=str) for j in jobs}
        if len(vals) > 1:
            out.append(k)
    return out


def labels_for(rows: list[dict], jobs: list[dict]) -> list[str]:
    """checkpoint · LoRA · category (if it differs) · the tool fields that differ — never the ones that are the same."""
    diff = differing(jobs)
    cats = {r.get("category") for r in rows}
    seeds = {str((r.get("meta") or {}).get("seed")) for r in rows}
    out = []
    for r, j in zip(rows, jobs):
        bits = [Path(r.get("checkpoint") or "").stem or "?", (Path(r["lora"]).stem if r.get("lora") else "no LoRA")]
        if len(cats) > 1:
            bits.append(str(r.get("category")))
        if len(seeds) > 1:
            bits.append(f"seed {(r.get('meta') or {}).get('seed')}")
        bits += [f"{k}={_short(j.get(k)) if k in j else '-'}" for k in diff]
        out.append(" · ".join(bits))
    return out


def _fit(im: Image.Image, w: int, h: int) -> Image.Image:
    im = im.convert("RGB")
    im.thumbnail((w, h), Image.LANCZOS)
    return im


def _wrap(draw, text: str, f, width: int) -> list[str]:
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=f) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines[:3]


def sheet(images: list[Image.Image], labels: list[str], title: str, max_side: int = 2000, cols: int | None = None) -> Image.Image:
    """≤ 12 cells, numbered, labels in the picture; the whole sheet's longest side = max_side or less."""
    n = len(images)
    cols = cols or (1 if n == 1 else 2 if n <= 4 else 3 if n <= 9 else 4)
    rows = (n + cols - 1) // cols
    aspect = max(0.3, min(3.0, sum(i.width / max(1, i.height) for i in images) / max(1, n)))
    pad, title_h = 10, 40
    f, fb = font(17), font(22)
    label_h = 3 * 21 + 6
    # largest cell width so that both sides fit max_side
    cw = (max_side - pad * (cols + 1)) // cols
    ch = int(cw / aspect)
    total_h = title_h + rows * (ch + label_h + pad) + pad
    if total_h > max_side:
        ch = (max_side - title_h - pad - rows * (label_h + pad)) // rows
        cw = int(ch * aspect)
    W = cols * cw + pad * (cols + 1)
    H = title_h + rows * (ch + label_h + pad) + pad
    canvas = Image.new("RGB", (W, H), (22, 22, 27))
    d = ImageDraw.Draw(canvas)
    d.text((pad, 8), title, fill=(240, 180, 80), font=fb)
    for i, (im, lab) in enumerate(zip(images, labels)):
        r, c = divmod(i, cols)
        x = pad + c * (cw + pad)
        y = title_h + r * (ch + label_h + pad)
        t = _fit(im, cw, ch)
        canvas.paste(t, (x + (cw - t.width) // 2, y + (ch - t.height) // 2))
        d.rectangle([x, y, x + (44 if i < 9 else 58), y + 30], fill=(0, 0, 0))
        d.text((x + 6, y + 3), f"#{i + 1}", fill=(255, 220, 120), font=fb)
        for k, line in enumerate(_wrap(d, lab, f, cw)):
            d.text((x, y + ch + 3 + k * 21), line, fill=(230, 230, 236), font=f)
    return canvas


def save_jpeg(img: Image.Image, path: Path, limit: int = MAX_BYTES) -> int:
    """JPEG under `limit` bytes: lower the quality, then the size, until it fits."""
    path.parent.mkdir(parents=True, exist_ok=True)
    im = img
    for _ in range(8):
        for q in (88, 80, 72, 64, 56):
            b = io.BytesIO()
            im.save(b, "JPEG", quality=q, optimize=True)
            if b.tell() <= limit:
                path.write_bytes(b.getvalue())
                return b.tell()
        im = im.resize((int(im.width * 0.85), int(im.height * 0.85)), Image.LANCZOS)
    path.write_bytes(b.getvalue())
    return b.tell()


def pages(items: list, per: int) -> list[list]:
    return [items[i:i + per] for i in range(0, len(items), per)] or []


def _done_rows(cfg: dict, target: str) -> list[dict]:
    rows = [r for r in collect(cfg, target) if r["state"] == "done" and r["images"]]
    rows.sort(key=lambda r: (str(r.get("prompt_id")), Path(r.get("checkpoint") or "").stem, r.get("lora") or "",
                             str(r.get("category")), r["id"]))
    return rows


def build_compact(cfg: dict, target: str, cells: int = 12, max_side: int = 2000, limit: int = MAX_BYTES,
                  prompt: str | None = None) -> tuple[Path, dict]:
    cells = max(1, min(12, int(cells)))
    rows = _done_rows(cfg, target)
    if prompt:
        rows = [r for r in rows if str(r.get("prompt_id") or r.get("name")) == prompt]
    if not rows:
        raise ValueError(f"no finished pictures for '{target}' (looked for batch '{target}' and 'bakeoff/{target}')")
    jobs_dir = cfgmod.path_of(cfg, "jobs")
    out = cfgmod.path_of(cfg, "out") / "review" / safe(target) / "compact"
    out.mkdir(parents=True, exist_ok=True)
    by_prompt: dict[str, list[dict]] = {}
    for r in rows:
        by_prompt.setdefault(str(r.get("prompt_id") or r.get("name")), []).append(r)
    index = {"target": target, "cells_per_sheet": cells, "max_side": max_side, "sheets": []}
    n = 0
    for pid, rs in by_prompt.items():
        pg = pages(rs, cells)
        for k, chunk in enumerate(pg):
            n += 1
            jobs = [job_of(jobs_dir, r["id"]) for r in chunk]
            labs = labels_for(chunk, jobs)
            imgs = []
            for r in chunk:
                with Image.open(r["images"][0]) as im:
                    imgs.append(im.convert("RGB").copy())
            title = f"{target} · {pid}" + (f" · page {k + 1}/{len(pg)}" if len(pg) > 1 else "") + f" · {len(chunk)} cells"
            name = f"sheet_{n:03d}.jpg"
            size = save_jpeg(sheet(imgs, labs, title, max_side), out / name, limit)
            index["sheets"].append({"sheet": name, "prompt": pid, "page": k + 1, "pages": len(pg), "bytes": size,
                                    "cells": [{"n": i + 1, "id": r["id"], "label": lab} for i, (r, lab) in enumerate(zip(chunk, labs))]})
    (out / "review_index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
    return out, index


def _detail_for(cfg: dict, target: str, r: dict, crop: int) -> dict:
    from . import detail
    det = dict((r.get("meta") or {}).get("detail") or {})
    over = detail.load(target).get(str((r.get("meta") or {}).get("prompt_id"))) if target else None
    if isinstance(over, dict):
        det.update({k: v for k, v in over.items() if k in ("at", "size")})
    det.setdefault("size", crop)
    det.setdefault("at", [0.5, 0.5])
    return det


def crop_1to1(im: Image.Image, det: dict) -> Image.Image:
    size = int(det.get("size") or 512)
    ax, ay = (det.get("at") or [0.5, 0.5])[:2]
    w, h = im.size
    sw, sh = min(size, w), min(size, h)
    x = int(min(max(0, round(w * float(ax) - sw / 2)), w - sw))
    y = int(min(max(0, round(h * float(ay) - sh / 2)), h - sh))
    return im.crop((x, y, x + sw, y + sh))


def pair_sheet(a: Image.Image, b: Image.Image, la: str, lb: str, det: dict, title: str, max_side: int = 2000) -> Image.Image:
    pad, title_h, label_h = 10, 40, 28
    f, fb = font(17), font(22)
    cw = (max_side - 3 * pad) // 2
    aspect = a.width / max(1, a.height)
    ph = int(cw / aspect)
    ca, cb = crop_1to1(a, det), crop_1to1(b, det)
    crop_side = min(cw, ca.width, max_side - title_h - ph - 2 * label_h - 3 * pad)
    if crop_side < 200:              # very tall pictures: give the crop room, shrink the whole picture
        ph = max(200, max_side - title_h - 2 * label_h - 3 * pad - min(cw, ca.width))
        crop_side = min(cw, ca.width, max_side - title_h - ph - 2 * label_h - 3 * pad)
    H = title_h + ph + label_h + crop_side + label_h + 2 * pad
    W = 2 * cw + 3 * pad
    canvas = Image.new("RGB", (W, H), (22, 22, 27))
    d = ImageDraw.Draw(canvas)
    d.text((pad, 8), title, fill=(240, 180, 80), font=fb)
    for i, (im, crop, lab) in enumerate(((a, ca, la), (b, cb, lb))):
        x = pad + i * (cw + pad)
        t = _fit(im, cw, ph)
        canvas.paste(t, (x + (cw - t.width) // 2, title_h))
        d.text((x, title_h + ph + 4), (("A  " if i == 0 else "B  ") + lab)[:90], fill=(230, 230, 236), font=f)
        cy = title_h + ph + label_h + pad
        c = crop.convert("RGB")
        if c.width != crop_side:
            c = c.resize((crop_side, int(c.height * crop_side / c.width)), Image.LANCZOS)  # 1:1 unless it cannot fit
        canvas.paste(c, (x + (cw - c.width) // 2, cy))
        d.text((x, cy + c.height + 4), f"detail {'1:1' if c.width == crop.width else f'{c.width / crop.width:.2f}:1'} "
               f"at {det.get('at')} · {crop.width}px", fill=(170, 170, 180), font=f)
    return canvas


def build_pairs(cfg: dict, target: str, a: str, b: str, crop: int = 640, max_side: int = 2000,
                limit: int = MAX_BYTES) -> tuple[Path, dict]:
    rows = _done_rows(cfg, target)
    by_id = {r["id"]: r for r in rows}
    out = cfgmod.path_of(cfg, "out") / "review" / safe(target) / f"pairs_{safe(a)}_vs_{safe(b)}"
    pairs = []
    if a in by_id and b in by_id:
        pairs = [(by_id[a], by_id[b])]
    else:
        def key(r):
            m = r.get("meta") or {}
            return (str(m.get("prompt_id") or r.get("name")), r.get("checkpoint") or "", r.get("lora") or "", str(m.get("seed")))
        A = {key(r): r for r in rows if r.get("category") == a}
        B = {key(r): r for r in rows if r.get("category") == b}
        pairs = [(A[k], B[k]) for k in sorted(set(A) & set(B))]
        if not pairs:
            cats = sorted({str(r.get("category")) for r in rows})
            raise ValueError(f"no cells in both '{a}' and '{b}' for '{target}'. Categories here: {', '.join(cats) or '(none)'}")
    out.mkdir(parents=True, exist_ok=True)
    index = {"target": target, "a": a, "b": b, "sheets": []}
    for n, (ra, rb) in enumerate(pairs, 1):
        with Image.open(ra["images"][0]) as ia, Image.open(rb["images"][0]) as ib:
            ia, ib = ia.convert("RGB").copy(), ib.convert("RGB").copy()
        det = _detail_for(cfg, target, ra, crop)
        la, lb = labels_for([ra, rb], [job_of(cfgmod.path_of(cfg, "jobs"), ra["id"]), job_of(cfgmod.path_of(cfg, "jobs"), rb["id"])])
        m = ra.get("meta") or {}
        title = f"{target} · {m.get('prompt_id') or ra.get('name')} · {Path(ra.get('checkpoint') or '').stem} · A={a}  B={b}"
        name = f"pair_{n:03d}.jpg"
        size = save_jpeg(pair_sheet(ia, ib, la, lb, det, title, max_side), out / name, limit)
        index["sheets"].append({"sheet": name, "bytes": size, "detail": det,
                                "cells": [{"n": 1, "side": "A", "id": ra["id"], "label": la}, {"n": 2, "side": "B", "id": rb["id"], "label": lb}]})
    (out / "review_index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
    return out, index


def build_family(cfg: dict, template: str, batch: str | None = None, max_side: int = 2000) -> tuple[Path, dict]:
    """G11: every member of a room family side by side (by meta.family == template), from finished jobs, or — when
    nothing has rendered yet — from the drafts' control images, so a family can be checked before it is painted."""
    jobs_dir, out_root = cfgmod.path_of(cfg, "jobs"), cfgmod.path_of(cfg, "out")
    found = []
    for st in ("done",):
        for p in sorted((jobs_dir / st).glob("*.json")):
            try:
                j = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if (j.get("meta") or {}).get("family") != template or (batch and j.get("batch") != batch):
                continue
            d = out_root / j["id"]
            img = next((d / o for o in ((j.get("result") or {}).get("outputs") or []) if (d / o).exists()), None) or \
                (d / "scene.png" if (d / "scene.png").exists() else None)
            if img:
                found.append((j, img))
    if not found:
        raise ValueError(f"no finished pictures of family '{template}' yet")
    out = out_root / "review" / f"family_{safe(template)}"
    imgs, labs, cells = [], [], []
    for j, img in found[:12]:
        with Image.open(img) as im:
            imgs.append(im.convert("RGB").copy())
        m = j.get("meta") or {}
        labs.append(f"{m.get('member') or j.get('name')} · {m.get('skin') or ''} · {m.get('era') or ''}".strip(" ·"))
        cells.append({"n": len(cells) + 1, "id": j["id"], "label": labs[-1]})
    size = save_jpeg(sheet(imgs, labs, f"family {template} · {len(imgs)} members", max_side), out / "family.jpg")
    idx = {"family": template, "sheet": "family.jpg", "bytes": size, "cells": cells}
    out.mkdir(parents=True, exist_ok=True)
    (out / "review_index.json").write_text(json.dumps(idx, indent=1), encoding="utf-8")
    return out, idx
