"""A list of things -> one picture each -> one 3D model each, through the art ComfyUI's own TRELLIS.2 / Pixal3D nodes.

The list is the same file the first game's trellis_trial.py read (2026-11-12/13), so a list that worked there works here:

    {"batch": "...", "models": ["trellis2"], "resolutions": [1024], "faces": 60000, "texture": 2048, "minutes_per_model": 60,
     "picture": {"unet": "flux-2-klein-4b.safetensors", "size": 1024, "seed": 1001, "always": "...", "negative": "..."},
     "objects": [{"id": "...", "prompt": "...", "always": "...", "seed": 1, "image": "path/to/picture.png",
                  "resolutions": [...], "faces": ..., "texture": ..., "seed3d": ..., "real_size_m": {"height": 1.8}}]}

For every thing: (1) the picture, painted by FLUX.2 klein unless the list names a file ("image"); (2) one model per
image-to-3D model asked for, trying the resolutions in order and stepping down only when the card ran out of memory or
time. Everything lands in <out>/pictures/<id>.png, <out>/models/<id>__<model>.glb (+ .prov.json beside each),
<out>/prompts/, report.json and REPORT.txt. Resumable: what is already there is skipped. A failure is written down and
the run goes on. The card lock is held while the art ComfyUI works, and its models are put away at the end.
"""
from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path

from . import comfyapi, licences, template

log = logging.getLogger("forge.threed.bodies")
DEFAULT_UNET = "flux-2-klein-4b.safetensors"


def picture_prompt(obj: dict, pic: dict) -> str:
    """The words a thing's picture is painted from: its own description, then the standing 'always' block."""
    return (str(obj.get("prompt", "")).strip() + " " + str(obj.get("always", pic.get("always", ""))).strip()).strip()


def paint(url: str, pic: dict, obj: dict, target: Path, batch: str, cfg: dict | None = None) -> dict:
    """Paint one thing's picture with FLUX.2 klein. Returns what it was made from (for provenance)."""
    from ..engines import flux2_graph
    from ..engines.comfy import ComfyClient
    flux2 = ((cfg or {}).get("comfy") or {}).get("flux2") or {}
    unet = pic.get("unet", DEFAULT_UNET)
    seed = int(obj.get("seed", pic.get("seed", 1001)))
    size = int(pic.get("size", 1024))
    words = picture_prompt(obj, pic)
    negative = str(obj.get("negative", pic.get("negative", "")))
    kw = {}
    if flux2.get("text_encoder"):
        kw["text_encoder"] = flux2["text_encoder"]
    if flux2.get("vae"):
        kw["vae"] = flux2["vae"]
    g = flux2_graph.build(unet, words, negative, seed, size, size, filename_prefix=f"threed_{batch}_{obj['id']}", **kw)
    client = ComfyClient(url)
    client.timeout = 900
    face = None
    if obj.get("face_ref"):
        # 2026-11-19 (Fable, Lane 5): a face to start from — the picture goes in as FLUX.2 klein's own reference latent
        # (ComfyUI's core ReferenceLatent, as same_person.py does); the words still paint the whole figure
        ref = Path(obj["face_ref"])
        face = client.upload_image(ref, subfolder="forge", name=f"threed_{batch}_{obj['id']}_face{ref.suffix}")
        g["40"] = {"class_type": "LoadImage", "inputs": {"image": face}}
        # BUILD 84 (2i): this ComfyUI's ImageScaleToTotalPixels has a required `resolution_steps`; without it /prompt said
        # "400 Bad Request" and every picture with a face to start from failed (two this morning)
        g["41"] = {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": ["40", 0], "upscale_method": "lanczos", "megapixels": 1.0,
                                                                       "resolution_steps": 1}}
        g["42"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["41", 0], "vae": ["3", 0]}}
        g["43"] = {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["4", 0], "latent": ["42", 0]}}
        g["10"]["inputs"]["positive"] = ["43", 0]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(client.run(g)[0])
    return {"prompt": words, "negative": negative, "seed": seed, "size": size, "model": unet,
            **({"face_ref": str(obj["face_ref"])} if face else {})}


def _back_of(cfg: dict | None, o: dict, out: Path) -> Path | None:
    """The back picture of a thing, if it has one: a file the list names ("back_image") or one painted from "back_words"."""
    if o.get("back_image"):
        p = Path(o["back_image"])
        return p if p.is_absolute() else Path((cfg or {}).get("_root") or ".") / p
    p = out / "pictures" / f"{o['id']}__back.png"
    return p if p.exists() else None


def repair_pose(url: str, pic: dict, obj: dict, target: Path, batch: str, cfg: dict | None, out: Path, n: int) -> Path | None:
    """BUILD 84 part 2: a picture whose only miss is its arms is made again from itself against the A-pose skeleton (the
    `guided` route of the same-person job, BUILD 74) — the same person, the same clothes, the arms moved — before any new
    picture is painted. Writes pictures/<id>__repair<n>.png and returns it, or None when the route can't run here (the
    models are not on this computer, or ComfyUI said no)."""
    from PIL import Image
    from . import same_person as sp
    from ..engines.comfy import ComfyClient
    ckpt, cn = "RealVisXL_V5.0_fp16.safetensors", "xinsir-union-sdxl-promax.safetensors"
    try:
        info = comfyapi.object_info(url)
        have = set(((info.get("CheckpointLoaderSimple") or {}).get("input", {}).get("required", {}).get("ckpt_name") or [[]])[0])
        have_cn = set(((info.get("ControlNetLoader") or {}).get("input", {}).get("required", {}).get("control_net_name") or [[]])[0])
        if (have and ckpt not in have) or (have_cn and cn not in have_cn):
            log.info("picture %s: no pose repair here (%s or %s is not in ComfyUI)", obj["id"], ckpt, cn)
            return None
    except Exception:  # noqa: BLE001 — a stand-in or an old ComfyUI: try it and let ComfyUI say
        pass
    src = Image.open(target).convert("RGB")
    pose = out / "pictures" / f"{obj['id']}__repair{n}_pose.png"
    sp.pose_skeleton(*src.size, deg=50.0).save(pose)
    client = ComfyClient(url)
    client.timeout = 900
    up = client.upload_image(target, subfolder="forge", name=f"threed_{batch}_{obj['id']}_repair{n}.png")
    pu = client.upload_image(pose, subfolder="forge", name=pose.name)
    words = sp.STYLE_START + sp.PRESETS["a_pose"] + ". " + str(obj.get("prompt", ""))
    g = sp.graph_guided(up, pu, words, sp.NEGATIVE, int(obj.get("seed", pic.get("seed", 1001))) + 101 * n, ckpt=ckpt, controlnet=cn)
    dst = out / "pictures" / f"{obj['id']}__repair{n}.png"
    dst.write_bytes(client.run(g)[0])
    return dst


def gate_picture(url: str, pic: dict, obj: dict, target: Path, batch: str, cfg: dict | None, out: Path,
                 made: dict | None = None, paint_fn=None, repair_fn=None) -> dict:
    """BUILD 40: the picture gate. A body's picture is measured (pose, limbs, proportions) before four minutes go into
    making the body; on a miss it is painted again with a new seed, up to `tries` times. Every try is kept beside the
    picture (pictures/<id>__try<n>.png) and the record goes to pictures/<id>.gate.json; when every try misses the thing
    is held, with the tries side by side (pictures/<id>__gate.png). A picture from a file is measured, never repainted.

    BUILD 84: a picture whose only miss is its arms is first repaired (repair_pose: the same picture against the A-pose
    skeleton) and judged again; only if the repair misses too is a new picture painted. A nudge goes near the front of the
    words; a thing made again carries the nudge its last miss asked for (obj["gate_nudge"]) into its first new try."""
    from . import gate
    paint_fn = paint_fn or paint
    repair_fn = repair_fn or repair_pose
    s = gate.settings(cfg)
    tries = max(1, int(obj.get("gate_tries") or s["tries"]))
    rec_path = out / "pictures" / f"{obj['id']}.gate.json"
    old = json.loads(rec_path.read_text(encoding="utf-8")) if rec_path.exists() else {}
    record = {"tries": list(old.get("tries") or []), "at": time.strftime("%Y-%m-%d %H:%M")}
    seed0 = int(obj.get("seed", pic.get("seed", 1001)))
    start = len(record["tries"])
    ok, j = False, None
    extra_words, said = "", None                 # BUILD 73: the words the last miss asks for, added to the next try's
    if old.get("held") and record["tries"]:
        said, extra_words = gate.nudge({"lines": record["tries"][-1].get("lines"), "measures": record["tries"][-1].get("measures"),
                                        "expects": old.get("expects")})
        extra_words = extra_words or ""
    elif obj.get("gate_nudge"):                      # BUILD 84: made again — the last round's nudge comes with it
        said, extra_words = obj.get("gate_nudge_said") or "carried", str(obj["gate_nudge"])
    repaired = 0
    for n in range(start, start + tries):
        used, used_said = "", None
        if n > start or old.get("held"):
            if obj.get("image"):
                break
            seed = seed0 + 7919 * n
            o2 = dict(obj, seed=seed)
            if extra_words:
                used, used_said = extra_words, said
                o2["prompt"] = gate.with_nudge(obj.get("prompt", ""), extra_words)
                log.info("picture %s (try %d): the words gain “%s”, near their front, after the last miss", obj["id"], n + 1, extra_words)
            got = paint_fn(url, pic, o2, target, batch, cfg)
            if made is not None:
                made[obj["id"]] = got
            (out / "pictures" / f"{obj['id']}.json").write_text(json.dumps(got, indent=1, ensure_ascii=False), encoding="utf-8")
        else:
            seed = seed0                      # the picture as painted (or given)
        j = gate.judge(target, obj, cfg)
        keep = out / "pictures" / f"{obj['id']}__try{n + 1}.png"
        shutil.copyfile(target, keep)
        record["tries"].append({"try": n + 1, "seed": seed, "ok": j["ok"], "lines": j["lines"], "picture": keep.name,
                                "measures": j["measures"], **({"nudge": used_said, "nudge_words": used} if used else {})})
        for ln in j["lines"]:
            log.info("picture %s (try %d): %s", obj["id"], n + 1, ln)
        if j["ok"]:
            ok = True
            break
        if gate.pose_miss_only(j) and not obj.get("image") and repaired < 1:
            # BUILD 84 part 2: repair before reroll — the picture is good but for its arms, so its arms are moved
            repaired += 1
            try:
                fixed = repair_fn(url, pic, obj, target, batch, cfg, out, n + 1)
            except Exception as e:  # noqa: BLE001 — a repair that can't run leaves the reroll as before
                log.warning("picture %s: the pose repair did not run (%s) — a new picture instead", obj["id"], e)
                fixed = None
            if fixed is not None and Path(fixed).exists():
                j2 = gate.judge(fixed, obj, cfg)
                record["tries"].append({"try": n + 1, "repair": True, "seed": seed, "ok": j2["ok"], "lines": j2["lines"],
                                        "picture": Path(fixed).name, "measures": j2["measures"], "repaired_from": keep.name})
                for ln in j2["lines"]:
                    log.info("picture %s (try %d, its pose repaired): %s", obj["id"], n + 1, ln)
                if j2["ok"]:
                    shutil.copyfile(fixed, target)
                    record["repaired"] = {"from": keep.name, "picture": Path(fixed).name}
                    ok, j = True, j2
                    break
        said, extra_words = gate.nudge(j)
        extra_words = extra_words or ""
    record["ok"], record["held"] = ok, not ok
    record["expects"] = (j or {}).get("expects")
    if not ok:
        mine = record["tries"][start:]
        why = [ln for t in mine for ln in t["lines"] if "Made again" in ln]
        record["why"] = sorted(set(w.replace(" Made again.", "") for w in why))
        try:
            gate.side_by_side([out / "pictures" / t["picture"] for t in mine],
                              [f"try {t['try']}: " + "; ".join(x.replace("Picture gate — ", "").replace(" Made again.", "")
                                                              for x in t["lines"] if "Made again" in x)
                               + (f"  [words gained: {t['nudge_words']}]" if t.get("nudge_words") else "") for t in mine],
                              out / "pictures" / f"{obj['id']}__gate.png")
            record["side_by_side"] = f"{obj['id']}__gate.png"
        except Exception as e:  # noqa: BLE001
            log.warning("picture %s: the side-by-side picture was not made - %s", obj["id"], e)
        log.warning("picture %s: HELD by the picture gate after %d tr%s - %s", obj["id"], len(mine),
                    "y" if len(mine) == 1 else "ies", "; ".join(record["why"]))
    rec_path.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
    return record


def upload(url: str, picture: Path, name: str) -> str:
    from ..engines.comfy import ComfyClient
    return ComfyClient(url).upload_image(picture, subfolder="forge", name=name)


def make_model(url: str, info: dict, tpl: dict, picture: Path, final: Path, model: str, ladder: list[int], faces: int,
               texture: int, prefix_base: str, seed3d: int | None, timeout_sec: int, local_out: Path | None,
               lock=None, prompts_dir: Path | None = None, upload_name: str | None = None, back: Path | None = None) -> dict:
    """One picture through one image-to-3D model. Returns a report row; never raises for a failed model. `back`, a picture
    of the back, is used by Pixal3D (BUILD 40); TRELLIS.2 takes one picture only."""
    row: dict = {"model": model, "ok": False}
    try:
        image_name = upload(url, picture, upload_name or picture.name)
        back_name = None
        if back is not None and Path(back).exists():
            if model == "pixal3d":
                back_name = upload(url, Path(back), (upload_name or picture.name).replace(".png", "__back.png"))
                row["back_view"] = True
            else:
                log.warning("%s / %s: a back picture was given, but %s takes one picture only — not used", final.stem, model, model)
                row["back_view"] = False
    except Exception as e:  # noqa: BLE001
        row["error"] = f"could not hand the picture to ComfyUI: {e}"
        log.error("%s / %s: %s", final.stem, model, row["error"])
        return row
    for res in ladder:
        prefix = f"{prefix_base}__{model}_r{res}"
        t0 = time.time()
        try:
            prompt = template.build_prompt(tpl, info, image_name, model, res, faces, texture, prefix, seed3d)
            if back_name:
                prompt = template.add_back_view(prompt, back_name)
            if prompts_dir is not None:
                prompts_dir.mkdir(parents=True, exist_ok=True)
                (prompts_dir / f"{Path(prefix).name}.json").write_text(json.dumps(prompt, indent=1), encoding="utf-8")
            log.info("%s / %s at %d: started (%d nodes); %s", final.stem, model, res, len(prompt), comfyapi.memory_line(url))
            entry = comfyapi.run(url, prompt, timeout_sec, on_wait=(lock.beat if lock else None))
            comfyapi.collect(url, entry, prefix, (".glb", ".gltf"), local_out, t0, final)
            row.update(ok=True, resolution=res, seconds=round(time.time() - t0), bytes=final.stat().st_size, prefix=prefix)
            log.info("%s / %s at %d: DONE in %.0f s, %.1f MB -> %s", final.stem, model, res, time.time() - t0,
                     final.stat().st_size / 2**20, final)
            return row
        except Exception as e:  # noqa: BLE001 — every failure is written down; the run goes on
            text = str(e).strip()
            row.setdefault("tries", []).append({"resolution": res, "seconds": round(time.time() - t0), "error": text[:3000]})
            log.error("%s / %s at %d: FAILED after %.0f s - %s", final.stem, model, res, time.time() - t0, text[:6000])
            try:
                comfyapi.free(url)
            except Exception:  # noqa: BLE001
                pass
            if not comfyapi.is_memory_or_time(e):
                break                                   # a lower setting would fail the same way
    row["error"] = (row.get("tries") or [{}])[-1].get("error", "unknown")
    return row


def write_prov(final: Path, obj: dict, model: str, row: dict, picture_made: dict | None, url: str, extra: dict | None = None) -> Path:
    """Provenance beside every model: the picture's words as expanded, seeds, model, settings, tool versions, licences."""
    try:
        stats = comfyapi.get(url, "/system_stats", timeout=10).get("system", {})
    except Exception:  # noqa: BLE001
        stats = {}
    prov = {
        "kind": "model_3d", "id": obj.get("id"), "file": final.name, "made": time.strftime("%Y-%m-%d %H:%M:%S"),
        "picture": picture_made or {"from_file": obj.get("image")},
        "model": model, "resolution": row.get("resolution"), "faces": row.get("faces"), "texture": row.get("texture"),
        "seed3d": obj.get("seed3d"), "seconds": row.get("seconds"),
        "tools": {"comfyui": stats.get("comfyui_version", "?"), "template": template.TEMPLATE.name, "forge_threed": "1"},
        "licences": licences.lines(["flux2_klein_4b" if picture_made else None, model, "comfy_template"]),
        "commercial_ok": licences.all_ok(["flux2_klein_4b" if picture_made else None, model, "comfy_template"]),
    }
    if extra:
        prov.update(extra)
    p = final.with_suffix(".prov.json")
    p.write_text(json.dumps(prov, indent=1, ensure_ascii=False), encoding="utf-8")
    return p


def run(cfg: dict | None, spec: dict, out: Path, url: str | None = None, models: list[str] | None = None,
        only: str | None = None, local_out: Path | None = None, lock_holder: str | None = None,
        info: dict | None = None, use_lock: bool = True) -> list[dict]:
    """Pictures and models for a whole list. Returns the report rows (also written to report.json / REPORT.txt)."""
    from .cardlock import CardLock
    url = url or ((cfg or {}).get("comfy") or {}).get("url") or "http://127.0.0.1:8188"
    out = Path(out)
    for sub in ("pictures", "models", "prompts"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    batch = spec.get("batch") or out.name
    models = models or list(spec.get("models", ["trellis2"]))
    objects = [o for o in spec["objects"] if not only or o["id"] == only]
    ladder = [int(r) for r in spec.get("resolutions", [1024])]
    faces, texture = int(spec.get("faces", 60000)), int(spec.get("texture", 2048))
    timeout_sec = int(spec.get("seconds_per_model") or int(spec.get("minutes_per_model", 60)) * 60)
    pic = spec.get("picture", {})
    rows: list[dict] = []
    if not comfyapi.is_up(url):
        log.error("ComfyUI is not answering at %s - nothing was run.", url)
        rows = [{"id": o["id"], "model": m, "ok": False, "error": f"ComfyUI is not answering at {url}"} for o in objects for m in models]
        _report(out, batch, rows)
        return rows
    lock = CardLock(cfg, lock_holder or f"3D models {batch}", log=log, art_url=url, side="art") if use_lock else None
    if lock:
        lock.acquire()
    made_pics: dict[str, dict] = {}
    try:
        info = info or comfyapi.object_info(url)
        tpl = template.load()
        log.info("ComfyUI at %s is up, it knows %d kinds of node; %s", url, len(info), comfyapi.memory_line(url))
        # 1. the pictures, all of them first (one painting model in memory, then it is put away)
        for o in objects:
            target = out / "pictures" / f"{o['id']}.png"
            if o.get("back_words") and not (out / "pictures" / f"{o['id']}__back.png").exists():
                try:                                       # BUILD 40: the back, painted from its own words, same seed
                    paint(url, pic, dict(o, prompt=o["back_words"]), out / "pictures" / f"{o['id']}__back.png", batch, cfg)
                    log.info("picture %s: the back painted", o["id"])
                except Exception as e:  # noqa: BLE001
                    log.exception("picture %s: the back FAILED - %s", o["id"], e)
            if target.exists():
                log.info("picture %s: already there", o["id"])
                continue
            if o.get("image"):
                src = Path(o["image"])
                src = src if src.is_absolute() else Path((cfg or {}).get("_root") or ".") / src
                try:
                    shutil.copyfile(src, target)
                    log.info("picture %s: copied from %s", o["id"], o["image"])
                except OSError as e:
                    log.error("picture %s: could not copy %s - %s", o["id"], o["image"], e)
                continue
            t0 = time.time()
            try:
                made_pics[o["id"]] = paint(url, pic, o, target, batch, cfg)
                (out / "pictures" / f"{o['id']}.json").write_text(json.dumps(made_pics[o["id"]], indent=1, ensure_ascii=False), encoding="utf-8")
                log.info("picture %s: painted in %.0f s", o["id"], time.time() - t0)
            except Exception as e:  # noqa: BLE001
                log.exception("picture %s: FAILED - %s", o["id"], e)
            if lock:
                lock.beat()
        # 1b. the picture gate, for the bodies of a list that asks for it (the world queue does)
        if spec.get("gate"):
            for o in objects:
                target = out / "pictures" / f"{o['id']}.png"
                rec = out / "pictures" / f"{o['id']}.gate.json"
                if target.exists() and (o["id"] in made_pics or not rec.exists() or
                                        json.loads(rec.read_text(encoding="utf-8")).get("held")):
                    try:
                        gate_picture(url, pic, o, target, batch, cfg, out, made_pics)
                    except Exception as e:  # noqa: BLE001
                        log.exception("picture %s: the picture gate failed (%s) - the body is made without it", o["id"], e)
                    if lock:
                        lock.beat()
        try:
            comfyapi.free(url)
        except Exception:  # noqa: BLE001
            pass
        # 2. the models: every thing through one image-to-3D model, then every thing through the next
        for model in models:
            for o in objects:
                picture = out / "pictures" / f"{o['id']}.png"
                final = out / "models" / f"{o['id']}__{model}.glb"
                row = {"id": o["id"], "model": model, "ok": False}
                rows.append(row)
                if final.exists():
                    row.update(ok=True, note="already there", bytes=final.stat().st_size)
                    log.info("%s / %s: already there", o["id"], model)
                    continue
                if not picture.exists():
                    row["error"] = "no picture"
                    continue
                grec = out / "pictures" / f"{o['id']}.gate.json"
                if spec.get("gate") and grec.exists() and json.loads(grec.read_text(encoding="utf-8")).get("held"):
                    row["error"] = "held by the picture gate (see pictures/" + o["id"] + "__gate.png)"
                    row["gate_held"] = True
                    continue
                r = make_model(url, info, tpl, picture, final, model, [int(x) for x in o.get("resolutions", ladder)],
                               int(o.get("faces", faces)), int(o.get("texture", texture)), f"3d/{batch}/{o['id']}",
                               o.get("seed3d"), timeout_sec, local_out, lock, out / "prompts", f"threed_{batch}_{o['id']}.png",
                               back=_back_of(cfg, o, out))
                r.update(faces=int(o.get("faces", faces)), texture=int(o.get("texture", texture)))
                row.update({k: v for k, v in r.items() if k != "model"})
                if row["ok"]:
                    pmade = made_pics.get(o["id"])
                    if pmade is None and (out / "pictures" / f"{o['id']}.json").exists():
                        pmade = json.loads((out / "pictures" / f"{o['id']}.json").read_text(encoding="utf-8"))
                    write_prov(final, o, model, row, pmade, url, {"real_size_m": o.get("real_size_m")})
                _report(out, batch, rows, partial=True)
            try:
                comfyapi.free(url)
            except Exception:  # noqa: BLE001
                pass
    finally:
        if lock:
            lock.release()
    _report(out, batch, rows)
    return rows


def _report(out: Path, batch: str, rows: list[dict], partial: bool = False) -> None:
    (out / "report.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    if partial:
        return
    lines = [f"Image-to-3D run '{batch}': {sum(r['ok'] for r in rows)} of {len(rows)} models made", ""]
    for r in rows:
        if r["ok"]:
            lines.append(f"  ok    {r['id']:<22} {r['model']:<9} " + (f"at {r['resolution']}, {r['seconds']} s, {r['bytes'] / 2**20:.1f} MB"
                                                                       if "seconds" in r else r.get("note", "")))
        else:
            lines.append(f"  FAIL  {r['id']:<22} {r['model']:<9} {str(r.get('error', ''))[:200]}")
    (out / "REPORT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
