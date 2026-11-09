"""The bake-off: every checkpoint × every compatible LoRA × a suite of test prompts, one seed, same settings —
then one report so the pictures can be compared side by side and a model picked *per kind of asset*.

    python -m forge bakeoff plan   <suite.json>      what would be queued (counts, skips) — no jobs
    python -m forge bakeoff submit <suite.json>      queue it (grouped by checkpoint so ComfyUI reloads less)
    python -m forge bakeoff report <suite-name>      grids per prompt + index.html from whatever has finished
    python -m forge bakeoff rate   <suite-name> <job-id> <1-5> [note]   record a verdict; the report shows it

A suite (games/<game>/bakeoff/*.json):
    {"suite": "sdxl_v1", "game": "turing_accords",
     "checkpoints": "*" | ["RealVisXL_V5.0_fp16.safetensors", ...],
     "loras": "*" | [...],  "include_no_lora": true,  "lora_strength": 0.8,
     "skip": {"checkpoints": [], "loras": []},
     "seeds": [1001], "size": [1024, 1024], "steps": 25, "cfg": 6.0, "sampler": "dpmpp_2m", "scheduler": "karras",
     "negative": "...",
     "lora_triggers": {"FFTALevel4…safetensors": "fftalevel64, pixel art"},      # words appended when that LoRA is on
     "graph": "sdxl" | "flux2_klein" | "flux1",                                   # engine graph; FLUX suites list diffusion-model files as checkpoints
     "base_override": "flux2", "checkpoint_kinds": ["unet", "unknown"],          # when the header scan cannot tell the architecture
     "lora_base_override": {"somefile.safetensors": "flux1"},                      # likewise for a LoRA with no metadata
     "checkpoint_dirs": ["flux_models"], "base_filter": "flux1",                    # discover checkpoints by folder / architecture instead of listing them
     "lora_base_filter": "flux1", "cfg_by_name": {"dedistill": 3.5},               # LoRAs by architecture; per-model overrides by a name substring
     "lora_checkpoint_filter": "marduk",                                            # apply LoRAs only on checkpoints matching this regex
     "categories": {"portrait": {"size": [832, 1216], "prompts": {"sarah": "..."}}, ...}}

A category normally queues raw `render` jobs. It can queue one of the forge's *tools* instead, so a suite can compare
what a finishing chain does on each model (same seed, same prompt, only the treatment changes):
     "categories": {"t2_refine_030": {"type": "scene_paint",                       # any job type that takes a prompt
                                      "job": {"target": [1920, 1080], "refine": {"denoise": 0.3}},   # extra job fields
                                      "detail_crop": 512,                          # also build 1:1 detail grids (a crop this big)
                                      "detail_at": {"dockerys_juke": [0.6, 0.5]},  # where to crop per prompt (fractions; default centre)
                                      "seconds_per_render": 70, "prompts": {...}}}
`job_type` / `job` / `detail_crop` at the top of the suite set the default for every category. The report takes each
job's first output picture (scene.png, icon.png …) where a render job has render.png.

Incompatible LoRAs (an SD1.5 or FLUX LoRA on an SDXL checkpoint) are skipped and listed — ComfyUI would
silently ignore them and the "result" would be a lie. A failed render (OOM, broken file) is a failed job
with its error; the report shows it as a red cell and the run continues.
"""
from __future__ import annotations
import html, json, re
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from . import config as cfgmod
from .ops import safetensors_meta as sm
from .ops.sheet import _font, _ascii
from .queue import Queue

GENERIC_TAGS = {"1girl", "1boy", "solo", "no humans", "simple background", "white background", "full body", "standing",
                "looking at viewer", "scenery", "outdoors", "indoors", "sky", "tree", "trees", "building", "water", "nature",
                "long hair", "short hair", "gloves", "boots", "hat", "weapon", "gun", "fire", "glowing", "battle", "multiple views",
                "character", "map", "big", "bar", "table", "exterior", "interior", "objets", "dungeon", "stairs", "plant",
                "3d \\(artwork\\)", "pink hair", "solo focus", "closed mouth", "smile", "knight", "samurai", "ninja", "black mage",
                "white mage", "thief", "city", "cityscape", "giant", "fence", "ferris wheel", "skyscraper", "damaged", "explosion"}


# ---------------------------------------------------------------- inventory
def inventory(cfg: dict, refresh: bool = False) -> list[dict]:
    """models/inventory.json — scanned headers of every checkpoint and LoRA in the configured folders."""
    inv_path = cfgmod.ROOT / "models" / "inventory.json"
    if inv_path.exists() and not refresh:
        with open(inv_path, "r", encoding="utf-8") as f:
            return json.load(f)
    recs = sm.scan(cfgmod.model_dirs(cfg, "checkpoints") + cfgmod.model_dirs(cfg, "loras"))
    inv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(inv_path, "w", encoding="utf-8") as f:
        json.dump(recs, f, indent=1, ensure_ascii=False)
    (cfgmod.ROOT / "models" / "INVENTORY.md").write_text(sm.render_markdown(recs), encoding="utf-8", newline="\n")
    return recs


def guess_trigger(rec: dict) -> str:
    """The LoRA's trigger word, if the trainer metadata gives it away: a made-up token (no spaces, not a
    generic tag) or a phrase with 'style'/'sheet'/'map'/'level' in it. Empty when unsure."""
    for t in rec.get("triggers", []):
        tl = t.lower().strip()
        if tl in GENERIC_TAGS:
            continue
        if " " not in tl and not tl.isdigit() and len(tl) >= 5:
            return t
        if any(w in tl for w in ("style", "sheet", "map", "level", "icon", "pixel art", "game scene")):
            return t
    return ""


# ---------------------------------------------------------------- planning
def _select(names_all: list[str], spec, skip: list[str]) -> list[str]:
    if spec == "*" or spec is None:
        chosen = list(names_all)
    else:
        chosen = [n for n in spec if n in names_all]
        missing = [n for n in spec if n not in names_all]
        if missing:
            raise FileNotFoundError("not in the model folders: " + ", ".join(missing))
    return [n for n in chosen if n not in set(skip or [])]


def plan(suite: dict, inv: list[dict], cfg: dict) -> dict:
    # Which inventory kinds count as "checkpoints" for this suite: SDXL suites want real checkpoints; FLUX suites name
    # diffusion-model (unet) files, which the header scan may label "unet" or "unknown". `base_override` pins the
    # architecture of the listed checkpoints when the scan cannot tell (FLUX.2 klein files have no trainer metadata).
    graph = str(suite.get("graph", "sdxl")).lower()
    default_kinds = ("checkpoint",) if graph == "sdxl" else ("checkpoint", "unet", "unknown")
    kinds = tuple(suite.get("checkpoint_kinds") or default_kinds)
    ckpts = {r["file"]: r for r in inv if r.get("kind") in kinds}
    if suite.get("checkpoint_dirs"):      # only files that live in these folders (names relative to the repo root)
        want = [str(x).replace("\\", "/").rstrip("/").lower() for x in suite["checkpoint_dirs"]]
        def _in_dirs(r: dict) -> bool:
            full = str(r.get("path") or r["file"]).replace("\\", "/")
            parent = full.rsplit("/", 1)[0].lower() if "/" in full else ""
            return any(parent.endswith(w) for w in want)
        ckpts = {k: r for k, r in ckpts.items() if _in_dirs(r)}
    if suite.get("base_filter"):           # only files whose detected architecture starts with this (e.g. "flux1")
        ckpts = {k: r for k, r in ckpts.items() if str(r.get("base", "")).startswith(str(suite["base_filter"]))}
    if suite.get("checkpoint_include"):    # a regex on the file name that a checkpoint must match (e.g. "klein")
        rx = re.compile(str(suite["checkpoint_include"]), re.I)
        ckpts = {k: r for k, r in ckpts.items() if rx.search(k)}
    if suite.get("checkpoint_exclude"):    # a regex on the file name; e.g. keep FLUX.2 files out of a FLUX.1 suite
        rx = re.compile(str(suite["checkpoint_exclude"]), re.I)
        ckpts = {k: r for k, r in ckpts.items() if not rx.search(k)}
    if suite.get("base_override"):
        for r in ckpts.values():
            r = dict(r); r["base"] = str(suite["base_override"])
            ckpts[r["file"]] = r
    loras = {r["file"]: r for r in inv if r.get("kind") in ("lora", "lycoris")}
    if suite.get("lora_base_filter"):      # only LoRAs whose detected architecture starts with this (drops 'unknown' ones too)
        loras = {k: r for k, r in loras.items() if str(r.get("base", "")).startswith(str(suite["lora_base_filter"]))}
    skip = suite.get("skip", {})
    ck_names = _select(sorted(ckpts), suite.get("checkpoints", "*"), skip.get("checkpoints", []))
    lo_names = _select(sorted(loras), suite.get("loras", "*"), skip.get("loras", []))
    triggers = dict(suite.get("lora_triggers", {}))
    for n in lo_names:
        triggers.setdefault(n, guess_trigger(loras[n]))
    strength = float(suite.get("lora_strength", 0.8))
    seeds = suite.get("seeds") or [1001]
    jobs: list[dict] = []
    skipped: list[dict] = []
    seconds_total = 0.0
    for ck in ck_names:
        ck_base = ckpts[ck].get("base", "unknown")
        combos: list[tuple[str | None, list[dict]]] = []
        if suite.get("include_no_lora", True):
            combos.append((None, []))
        lo_ck_rx = re.compile(str(suite["lora_checkpoint_filter"]), re.I) if suite.get("lora_checkpoint_filter") else None
        for lo in lo_names:
            if lo_ck_rx and not lo_ck_rx.search(ck):
                continue                                   # LoRAs only on the checkpoints that match (e.g. one reference model)
            lo_base = str(suite.get("lora_base_override", {}).get(lo) or loras[lo].get("base", "unknown"))
            if lo_base != "unknown" and ck_base != "unknown" and lo_base.split()[0] != ck_base.split()[0]:
                skipped.append({"checkpoint": ck, "lora": lo, "reason": f"{lo_base} LoRA on a {ck_base} checkpoint — ComfyUI would silently ignore it"})
                continue
            combos.append((lo, [{"name": lo, "strength": strength, "clip": strength}]))
        for lo, chain in combos:
            for cat, cdef in suite.get("categories", {}).items():
                jtype = str(cdef.get("type") or suite.get("job_type") or "render")
                jfields = {**(suite.get("job") or {}), **(cdef.get("job") or {})}
                crop = cdef.get("detail_crop", suite.get("detail_crop"))
                cat_secs = float(cdef.get("seconds_per_render", suite.get("seconds_per_render", 9.0)))
                cat_loras = cdef.get("lora_filter")
                if cat_loras and lo is not None and not re.search(cat_loras, lo, re.I):
                    continue
                for pid, ptext in cdef.get("prompts", {}).items():
                    for seed in seeds:
                        trig = triggers.get(lo, "") if lo else ""
                        prompt = (trig + ", " if trig else "") + ptext
                        extra = {}
                        if graph != "sdxl":
                            extra["graph"] = graph
                            for k in ("text_encoder", "vae", "clip_l", "t5", "guidance", "all_in_one", "distilled"):
                                if suite.get(k) is not None:
                                    extra[k] = suite[k]
                            if graph == "flux1" and ckpts[ck].get("kind") == "checkpoint":
                                extra["all_in_one"] = True      # CLIP + VAE baked in → CheckpointLoaderSimple
                            # per-model overrides by a substring of the file name (e.g. de-distilled fine-tunes need a real CFG)
                            for key, field in (("cfg_by_name", "cfg"), ("steps_by_name", "steps"), ("guidance_by_name", "guidance")):
                                for needle, val in (suite.get(key) or {}).items():
                                    if needle.lower() in ck.lower():
                                        extra[field] = val
                        meta_extra = {}
                        if jtype != "render":
                            meta_extra["job_type"] = jtype
                        if crop:
                            meta_extra["detail"] = {"size": int(crop), "at": list((cdef.get("detail_at") or {}).get(pid) or [0.5, 0.5])}
                        seconds_total += cat_secs
                        jobs.append({
                            **extra,
                            "type": jtype, "game": suite.get("game"),
                            "name": f"{cat}_{pid}_{_slug(ck)}_{_slug(lo) if lo else 'nolora'}_{seed}",
                            "batch": f"bakeoff/{suite['suite']}",
                            "prompt": prompt, "negative": cdef.get("negative", suite.get("negative")),
                            "checkpoint": ck, "loras": chain, "seed": int(seed),
                            "size": cdef.get("size", suite.get("size", [1024, 1024])),
                            "steps": extra.get("steps", (int(suite["steps"]) if suite.get("steps") is not None else (25 if graph == "sdxl" else None))),
                            "cfg": extra.get("cfg", (float(suite["cfg"]) if suite.get("cfg") is not None else (6.0 if graph == "sdxl" else None))),
                            "sampler": suite.get("sampler", "dpmpp_2m" if graph == "sdxl" else "euler"),
                            "scheduler": suite.get("scheduler", "karras" if graph == "sdxl" else "simple"),
                            "style_prefix": "",   # bake-offs test the model, not the house style
                            **jfields,            # a tool's own fields (target, refine, face_fix, control …) win
                            "meta": {"suite": suite["suite"], "category": cat, "prompt_id": pid, "checkpoint": ck,
                                     "lora": lo, "seed": int(seed), "trigger": trig, **meta_extra},
                        })
    return {"suite": suite["suite"], "checkpoints": ck_names, "loras": lo_names, "triggers": {k: triggers[k] for k in lo_names},
            "jobs": jobs, "skipped": skipped,
            "estimate_min": round(seconds_total / 60.0, 1)}


def _slug(s: str | None) -> str:
    if not s:
        return "none"
    s = Path(s).stem
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")
    return s[:40]


def _folder(s: str | None) -> str:
    """A readable folder name from a model file name: the stem, spaces → _, odd characters dropped."""
    if not s:
        return ""
    stem = Path(s).stem.replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9._()-]+", "", stem)[:80]


def submit(plan_: dict, q: Queue) -> list[str]:
    ids = [q.submit(j) for j in plan_["jobs"]]
    rec_dir = cfgmod.ROOT / "out" / "bakeoff" / plan_["suite"]
    rec_dir.mkdir(parents=True, exist_ok=True)
    with open(rec_dir / "plan.json", "w", encoding="utf-8") as f:
        json.dump({**plan_, "job_ids": ids, "submitted": datetime.now().isoformat(timespec="seconds")}, f, indent=1, ensure_ascii=False)
    return ids


# ---------------------------------------------------------------- organized output
def organized_paths(suite_name: str, meta: dict) -> tuple[Path, Path]:
    """Where a render is filed for side-by-side comparison, by model and by picture:
        out/bakeoff/<suite>/by_model/<checkpoint>/<lora|_no_lora>/<category>__<prompt>__seed<seed>.png
        out/bakeoff/<suite>/by_category/<category>/<prompt>/<checkpoint>__<lora|_no_lora>__seed<seed>.png
    """
    root = cfgmod.ROOT / "out" / "bakeoff" / suite_name
    ck = _folder(meta.get("checkpoint")) or "unknown"
    lo = _folder(meta.get("lora")) if meta.get("lora") else "_no_lora"
    cat, pid, seed = str(meta.get("category", "x")), str(meta.get("prompt_id", "x")), str(meta.get("seed", 0))
    return (root / "by_model" / ck / lo / f"{cat}__{pid}__seed{seed}.png",
            root / "by_category" / cat / pid / f"{ck}__{lo}__seed{seed}.png")


def file_render(suite_name: str, meta: dict, src: Path) -> list[Path]:
    """Copy one finished render into both trees (idempotent)."""
    import shutil
    out = []
    for dest in organized_paths(suite_name, meta):
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists() or dest.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dest)
        out.append(dest)
    return out


def organize(suite_name: str, q: Queue) -> int:
    """(Re)build the by_model / by_category trees from every finished render of the suite."""
    n = 0
    for r in _collect(suite_name, q):
        if r["image"]:
            file_render(suite_name, r["meta"], Path(r["image"]))
            n += 1
    return n


# ---------------------------------------------------------------- reporting
def job_image(out_dir: Path, job: dict) -> Path | None:
    """The picture to compare for a finished job: render.png for a raw render, else the job's first PNG output
    (scene.png for scene_paint/repaint, icon.png, sleeve.png …). None if nothing has been written yet."""
    p = out_dir / "render.png"
    if p.exists():
        return p
    for o in (job.get("result") or {}).get("outputs") or []:
        q = out_dir / str(o)
        if str(o).lower().endswith(".png") and q.exists():
            return q
    return None


def detail_crop(im: Image.Image, detail: dict) -> Image.Image:
    """A 1:1 crop of `size` px centred at the fractional point `at` (clamped to the picture) — refine, face repair
    and upscaler differences do not survive a thumbnail; this is the part of the picture to judge them on."""
    size = int(detail.get("size") or 512)
    ax, ay = (detail.get("at") or [0.5, 0.5])[:2]
    w, h = im.size
    sw, sh_ = min(size, w), min(size, h)
    x = int(min(max(0, round(w * float(ax) - sw / 2)), w - sw))
    y = int(min(max(0, round(h * float(ay) - sh_ / 2)), h - sh_))
    return im.crop((x, y, x + sw, y + sh_))


def across_grids(suite_name: str, rows: list[dict], out_dir: Path, ratings: dict, cell: int = 384) -> list[tuple]:
    """One picture across the suite's categories: rows = checkpoints, columns = categories (styles, or the
    treatments of a tools suite), one grid per prompt × LoRA × seed — built only where the same prompt id appears in
    more than one category. Where the jobs carry a detail crop (meta.detail), a second grid shows that crop at 1:1,
    because a refine pass or a face repair cannot be judged on a thumbnail.
    Returns [(prompt_id, lora, seed, file, kind)], kind 'across' or 'detail'."""
    by_pid: dict[tuple, list[dict]] = {}
    for r in rows:
        m = r["meta"]
        by_pid.setdefault((m.get("prompt_id"), m.get("lora") or "", m.get("seed")), []).append(r)
    f, made = _font(12), []
    for (pid, lo, seed), rs in sorted(by_pid.items(), key=lambda kv: (str(kv[0][0]), kv[0][1], str(kv[0][2]))):
        cats = sorted({r["meta"].get("category") for r in rs})
        if len(cats) < 2:
            continue
        cks = sorted({r["meta"].get("checkpoint", "?") for r in rs})
        cells = {(r["meta"].get("checkpoint", "?"), r["meta"].get("category")): r for r in rs}
        modes = [("across", None)]
        details = [r["meta"]["detail"] for r in rs if isinstance(r["meta"].get("detail"), dict)]
        if details:
            modes.append(("detail", details[0]))
        for kind, det in modes:
            cw = int(det.get("size") or 512) if det else cell
            first = next((r for r in rs if r["image"]), None)
            ch = cw
            if first and not det:
                try:
                    with Image.open(first["image"]) as t0:
                        ch = max(64, int(cw * t0.height / max(1, t0.width)))
                except Exception:  # noqa: BLE001
                    pass
            label_w, head_h = 170, 54
            im = Image.new("RGB", (label_w + len(cats) * (cw + 6), head_h + len(cks) * (ch + 6)), (22, 22, 26))
            dr = ImageDraw.Draw(im)
            what = f"1:1 detail crop {cw}px at {det.get('at')}" if det else "whole picture"
            dr.text((6, 4), _ascii(f"{suite_name} · {pid} · {Path(lo).stem if lo else 'no LoRA'} · seed {seed} · {what}  (rows: checkpoints · columns: categories)"),
                    font=_font(14), fill=(235, 230, 215))
            for ci, cat in enumerate(cats):
                dr.text((label_w + ci * (cw + 6) + 2, head_h - 22), _ascii(str(cat))[:int(cw / 7)], font=f, fill=(240, 198, 116))
            for ri, ck in enumerate(cks):
                y = head_h + ri * (ch + 6)
                for k, chunk in enumerate([Path(ck).stem[i:i + 24] for i in range(0, min(len(Path(ck).stem), 72), 24)]):
                    dr.text((4, y + 4 + 14 * k), _ascii(chunk), font=f, fill=(200, 200, 210))
                for ci, cat in enumerate(cats):
                    x = label_w + ci * (cw + 6)
                    r = cells.get((ck, cat))
                    if r is None or not r["image"]:
                        bad = r is not None and r["state"] == "failed"
                        dr.rectangle([x, y, x + cw - 1, y + ch - 1], fill=(90, 30, 30) if bad else None, outline=(60, 60, 68))
                        msg = _ascii(str(r["error"] or "failed")) if bad else ("not run" if r is None else r["state"])
                        for k in range(0, min(len(msg), 240), 48):
                            dr.text((x + 6, y + 6 + 14 * (k // 48)), msg[k:k + 48], font=f, fill=(255, 200, 200) if bad else (130, 130, 140))
                        continue
                    try:
                        t = Image.open(r["image"]).convert("RGB")
                        if det:
                            t = detail_crop(t, r["meta"].get("detail") or det)
                        else:
                            t.thumbnail((cw, ch), Image.LANCZOS)
                        im.paste(t, (x + (cw - t.width) // 2, y + (ch - t.height) // 2))
                    except Exception as e:  # noqa: BLE001
                        dr.rectangle([x, y, x + cw - 1, y + ch - 1], fill=(90, 30, 30))
                        dr.text((x + 6, y + 6), _ascii(f"unreadable: {e}")[:48], font=f, fill=(255, 200, 200))
                    if r["id"] in ratings:
                        sc = ratings[r["id"]]["score"]
                        dr.rectangle([x + cw - 26, y + 2, x + cw - 3, y + 18], fill=(40, 90, 40) if sc >= 4 else (90, 80, 30) if sc == 3 else (90, 30, 30))
                        dr.text((x + cw - 20, y + 3), str(sc), font=f, fill=(255, 255, 255))
            name = f"{kind}_{pid}_{_slug(lo) if lo else 'nolora'}_{seed}.png"
            im.save(out_dir / name)
            made.append((pid, lo, seed, name, kind))
    return made


def _collect(suite_name: str, q: Queue) -> list[dict]:
    """Every done/failed job of the suite with its output path (or error)."""
    rows = []
    for state in ("done", "failed", "running", "pending"):
        for p in (q.jobs / state).glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    j = json.load(f)
            except Exception:
                continue
            if j.get("batch") != f"bakeoff/{suite_name}" or j.get("tombstone"):
                continue
            img = job_image(q.out / j["id"], j)
            rows.append({"id": j["id"], "state": state, "meta": j.get("meta", {}), "error": j.get("error"), "type": j.get("type"),
                         "image": str(img) if img else None, "seconds": (j.get("result") or {}).get("seconds")})
    return rows


def ratings_path(suite_name: str) -> Path:
    return cfgmod.ROOT / "out" / "bakeoff" / suite_name / "ratings.json"


def rate(suite_name: str, job_id: str, score: int, note: str = "") -> None:
    p = ratings_path(suite_name)
    data = json.load(open(p, encoding="utf-8")) if p.exists() else {}
    data[job_id] = {"score": int(score), "note": note, "when": datetime.now().isoformat(timespec="seconds")}
    p.parent.mkdir(parents=True, exist_ok=True)
    json.dump(data, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


def report(suite_name: str, q: Queue, thumb: int = 256) -> Path:
    organize(suite_name, q)
    rows = _collect(suite_name, q)
    out_dir = cfgmod.ROOT / "out" / "bakeoff" / suite_name
    out_dir.mkdir(parents=True, exist_ok=True)
    ratings = json.load(open(ratings_path(suite_name), encoding="utf-8")) if ratings_path(suite_name).exists() else {}
    # axes
    ckpts = sorted({r["meta"].get("checkpoint", "?") for r in rows})
    loras = sorted({r["meta"].get("lora") or "" for r in rows}, key=lambda s: (s != "", s))
    cells = {(r["meta"].get("category"), r["meta"].get("prompt_id"), r["meta"].get("checkpoint"), r["meta"].get("lora") or "", r["meta"].get("seed")): r for r in rows}
    prompts = sorted({(r["meta"].get("category"), r["meta"].get("prompt_id")) for r in rows})
    seeds = sorted({r["meta"].get("seed") for r in rows})
    f = _font(12)
    grids = []
    for cat, pid in prompts:
        for seed in seeds:
            cols, rws = len(loras), len(ckpts)
            label_w, head_h = 170, 54
            W = label_w + cols * (thumb + 6)
            H = head_h + rws * (thumb + 6)
            im = Image.new("RGB", (W, H), (22, 22, 26))
            dr = ImageDraw.Draw(im)
            dr.text((6, 4), _ascii(f"{suite_name} · {cat} / {pid} · seed {seed}  (rows: checkpoints · columns: LoRAs)"), font=_font(14), fill=(235, 230, 215))
            for ci, lo in enumerate(loras):
                x = label_w + ci * (thumb + 6)
                lab = Path(lo).stem if lo else "(no LoRA)"
                dr.text((x + 2, head_h - 30), _ascii(lab)[:34], font=f, fill=(200, 200, 210))
                if len(lab) > 34:
                    dr.text((x + 2, head_h - 16), _ascii(lab)[34:68], font=f, fill=(200, 200, 210))
            for ri, ck in enumerate(ckpts):
                y = head_h + ri * (thumb + 6)
                for k, chunk in enumerate([Path(ck).stem[i:i + 24] for i in range(0, min(len(Path(ck).stem), 72), 24)]):
                    dr.text((4, y + 4 + 14 * k), _ascii(chunk), font=f, fill=(200, 200, 210))
                for ci, lo in enumerate(loras):
                    x = label_w + ci * (thumb + 6)
                    r = cells.get((cat, pid, ck, lo, seed))
                    if r is None:
                        dr.rectangle([x, y, x + thumb - 1, y + thumb - 1], outline=(50, 50, 56))
                        dr.text((x + 6, y + 6), "skipped / not run", font=f, fill=(110, 110, 120))
                        continue
                    if r["image"]:
                        try:
                            t = Image.open(r["image"]).convert("RGB")
                            t.thumbnail((thumb, thumb), Image.LANCZOS)
                            im.paste(t, (x + (thumb - t.width) // 2, y + (thumb - t.height) // 2))
                        except Exception as e:  # noqa: BLE001
                            dr.rectangle([x, y, x + thumb - 1, y + thumb - 1], fill=(90, 30, 30))
                            dr.text((x + 6, y + 6), _ascii(f"unreadable: {e}")[:40], font=f, fill=(255, 200, 200))
                    elif r["state"] == "failed":
                        dr.rectangle([x, y, x + thumb - 1, y + thumb - 1], fill=(90, 30, 30))
                        msg = _ascii(str(r["error"] or "failed"))
                        for k in range(0, min(len(msg), 160), 32):
                            dr.text((x + 6, y + 6 + 14 * (k // 32)), msg[k:k + 32], font=f, fill=(255, 200, 200))
                    else:
                        dr.rectangle([x, y, x + thumb - 1, y + thumb - 1], outline=(80, 80, 90))
                        dr.text((x + 6, y + 6), r["state"], font=f, fill=(150, 150, 160))
                    if r["id"] in ratings:
                        sc = ratings[r["id"]]["score"]
                        dr.rectangle([x + thumb - 26, y + 2, x + thumb - 3, y + 18], fill=(40, 90, 40) if sc >= 4 else (90, 80, 30) if sc == 3 else (90, 30, 30))
                        dr.text((x + thumb - 20, y + 3), str(sc), font=f, fill=(255, 255, 255))
            name = f"grid_{cat}_{pid}_{seed}.png"
            im.save(out_dir / name)
            grids.append((cat, pid, seed, name))
    across = across_grids(suite_name, rows, out_dir, ratings)
    # html index
    done = sum(1 for r in rows if r["image"])
    failed = sum(1 for r in rows if r["state"] == "failed")
    parts = [f"<!doctype html><meta charset='utf-8'><title>bake-off {html.escape(suite_name)}</title>",
             "<style>body{background:#16161a;color:#e8e2d6;font:14px system-ui;margin:16px}img{max-width:100%}h2{margin-top:32px}"
             ".cell{display:inline-block;width:200px;vertical-align:top;margin:4px;font-size:11px}.cell img{width:200px;height:200px;object-fit:contain;background:#222}"
             ".bad{color:#f88}.ok{color:#8f8}table{border-collapse:collapse}td,th{border:1px solid #333;padding:4px 8px}</style>",
             f"<h1>Bake-off: {html.escape(suite_name)}</h1><p>{done} rendered · {failed} failed · {len(rows) - done - failed} waiting · "
             f"{len(ckpts)} checkpoints · {len(loras)} LoRA columns · generated {datetime.now():%Y-%m-%d %H:%M}</p>",
             "<p>Every render is also filed twice for easy comparison: <code>by_model/&lt;checkpoint&gt;/&lt;lora&gt;/</code> "
             "and <code>by_category/&lt;kind&gt;/&lt;prompt&gt;/</code> (one folder per picture, one file per model).</p>"
             "<p>Grids: rows are checkpoints, columns are LoRAs. Rate a cell with <code>python -m forge bakeoff rate "
             f"{html.escape(suite_name)} &lt;job-id&gt; &lt;1-5&gt; \"note\"</code>; ratings show as corner badges.</p>"]
    if across:
        parts.append("<h1>One picture across the categories</h1><p>Rows are checkpoints, columns are the suite's categories "
                     "(styles or treatments). A <b>detail</b> sheet is the same grid as a 1:1 crop &mdash; judge refine, "
                     "face repair and upscaling there, not on the thumbnails. Click a sheet for full size.</p>")
        for pid, lo, seed, name, kind in across:
            parts.append(f"<h2>{html.escape(str(pid))} · {html.escape(Path(lo).stem if lo else 'no LoRA')} · seed {seed} · {kind}</h2>"
                         f"<a href='{name}'><img loading='lazy' src='{name}'></a>")
        parts.append("<h1>Per category</h1>")
    for cat, pid, seed, name in grids:
        parts.append(f"<h2>{html.escape(cat)} / {html.escape(pid)} · seed {seed}</h2><a href='{name}'><img src='{name}'></a>")
        parts.append("<div>")
        for r in sorted((r for r in rows if r['meta'].get('category') == cat and r['meta'].get('prompt_id') == pid and r['meta'].get('seed') == seed),
                        key=lambda r: (r['meta'].get('checkpoint'), r['meta'].get('lora') or '')):
            rel = f"../../{r['id']}/{Path(r['image']).name}" if r["image"] else None
            lab = f"{Path(r['meta'].get('checkpoint', '?')).stem}<br>{Path(r['meta'].get('lora') or '').stem or '(no LoRA)'}"
            badge = f" <b>★{ratings[r['id']]['score']}</b>" if r["id"] in ratings else ""
            if rel:
                parts.append(f"<div class='cell'><a href='{rel}'><img loading='lazy' src='{rel}'></a>{lab}{badge}<br><code>{r['id']}</code></div>")
            else:
                parts.append(f"<div class='cell'><div style='width:200px;height:200px;background:#311'></div>{lab}<br><span class='bad'>{html.escape(str(r['error'] or r['state']))[:120]}</span><br><code>{r['id']}</code></div>")
        parts.append("</div>")
    (out_dir / "index.html").write_text("\n".join(parts), encoding="utf-8")
    summary = {"suite": suite_name, "rendered": done, "failed": failed, "total": len(rows), "grids": [g[3] for g in grids],
               "across": [a[3] for a in across], "generated": datetime.now().isoformat(timespec="seconds")}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return out_dir / "index.html"
