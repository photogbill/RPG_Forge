"""3D bodies -> skeletons, with the two riggers of the ComfyUI-UniRig node pack in the rigging ComfyUI (port 8189).

    people  -> Make-It-Animatable ("mia"), finger bones kept (no_fingers false)       ◆ proven on 2026-11-13
    animals -> UniRig ("unirig", Mixamo-named template), after the body's seams are welded (tidy.weld)

For every body: load it -> rig it (Mixamo-named skeleton) -> save, plus a picture of how the rigger saw the body's
orientation. Writes <out>/<body>__<rigger>.fbx (the rigged body at rest), <body>__<rigger>_preview.glb (the rigger's own
.glb of it, for the viewer), <body>__orientation.png, report.json and REPORT.txt. Resumable; a failure is written down,
whatever was made before it is kept, and the run goes on. It starts the rigging ComfyUI itself when it is not already
running (and stops it again at the end), holding the card lock the whole time.

The pack's own Mixamo test dances ("motions") are for testing the pack only: the workshop never asks for them, and
motions.TEST_DANCES keeps them out of any game. Copied from the first game's rig_trial.py (2026-11-13).
"""
from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path

from . import comfyapi
from .env import RigEnv, stop

log = logging.getLogger("forge.threed.rig")
RIGGERS = ("mia", "unirig")
KIND_RIGGER = {"people": "mia", "person": "mia", "animal": "unirig", "thing": "unirig"}


def build_rig(body: dict, rigger: str) -> dict:
    """The request: load the body, rig it, and save the picture of how the rigger saw its orientation."""
    name = f"{body['id']}__{rigger}"
    p: dict = {
        "1": {"class_type": "UniRigLoadMesh", "inputs": {"source_folder": "input", "file_path": f"3d/{body['id']}.glb"}},
        "8": {"class_type": "UniRigOrientationCheck", "inputs": {"mesh": ["1", 0], "max_height": 512}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": f"rig/{body['id']}__orientation"}},
        # a request only runs what one of its end nodes needs; the preview node is the pack's own end node for a rig
        "7": {"class_type": "UniRigPreviewRiggedMesh", "inputs": {"fbx_output_path": ["3", 0]}},
    }
    if rigger == "mia":
        p["2"] = {"class_type": "MIALoadModel", "inputs": {"precision": "auto", "attn_backend": "auto"}}
        p["3"] = {"class_type": "MIAAutoRig", "inputs": {
            "trimesh": ["1", 0], "model": ["2", 0], "fbx_name": name,
            "no_fingers": bool(body.get("no_fingers", False)),       # people keep their finger bones (BUILD 36 rule)
            "use_normal": bool(body.get("use_normal", False)),       # helps when the arms hang close to the body
            "reset_to_rest": True}}
    elif rigger == "unirig":
        p["2"] = {"class_type": "UniRigLoadModel", "inputs": {"precision": "auto", "attn_backend": "auto"}}
        p["3"] = {"class_type": "UniRigAutoRig", "inputs": {
            "trimesh": ["1", 0], "model": ["2", 0], "skeleton_template": body.get("skeleton_template", "mixamo"), "fbx_name": name,
            "target_face_count": int(body.get("target_face_count", 50000)), "debug": False}}
    else:
        raise ValueError(f"unknown rigger {rigger!r}; the forge knows {', '.join(RIGGERS)}")
    return p


def build_motion(rigged_fbx: Path, name: str, motions: list[str]) -> dict:
    """Play the pack's test motions on a rigged body (testing the pack only - never for a game)."""
    return {str(4 + k): {"class_type": "UniRigApplyAnimation", "inputs": {
        "model_fbx_path": str(rigged_fbx), "animation_type": "mixamo", "animation_file": motion,
        "output_name": f"{name}__{Path(motion).stem.lower()}"}} for k, motion in enumerate(motions)}


def comfy_tail(path: Path, n: int = 40) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except OSError:
        return ""


def rigger_for(body: dict) -> str:
    return body.get("rigger") or KIND_RIGGER.get(str(body.get("kind", "people")), "mia")


def rig_bodies(cfg: dict | None, bodies: list[dict], out: Path, env: RigEnv | None = None, riggers: list[str] | None = None,
               motions: list[str] | None = None, minutes_per_rig: int = 30, lock_holder: str | None = None,
               use_lock: bool = True, art_url: str | None = None, start_minutes: float = 30) -> list[dict]:
    """Rig every body. A body is {"id", "glb", "kind": people|animal, "use_normal", "no_fingers", "rigger"}.
    `riggers` forces the riggers for all (the old trial's way); by default each body gets its kind's rigger."""
    from .cardlock import CardLock
    from .env import from_cfg
    env = env or from_cfg(cfg)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    motions = list(motions or [])
    timeout_sec = int(minutes_per_rig) * 60
    art_url = art_url or ((cfg or {}).get("comfy") or {}).get("url") or "http://127.0.0.1:8188"
    rows: list[dict] = []
    if not env.installed():
        rows = [{"body": b["id"], "rigger": rigger_for(b), "ok": False,
                 "error": "the rigging ComfyUI is not installed (Settings -> This computer -> 3D tools -> Install)"} for b in bodies]
        _report(out, rows)
        return rows
    # the bodies go into the rigging ComfyUI's own input folder; its mesh list is read once and cached, so the cache is
    # dropped to make it look again
    in3d = env.input_dir / "3d"
    in3d.mkdir(parents=True, exist_ok=True)
    ready = []
    for b in bodies:
        src = Path(b["glb"])
        src = src if src.is_absolute() else env.root / src
        if not src.exists():
            rows.append({"body": b["id"], "rigger": rigger_for(b), "ok": False, "error": f"the body is not there: {src}"})
            log.error("body %s: %s is not there", b["id"], src)
            continue
        dst = in3d / f"{b['id']}.glb"
        if not (dst.exists() and dst.stat().st_size == src.stat().st_size and dst.stat().st_mtime >= src.stat().st_mtime):
            shutil.copyfile(src, dst)
            log.info("body %s: %.1f MB copied into the rigging ComfyUI's input", b["id"], src.stat().st_size / 2**20)
        ready.append(b)
    for c in env.metadata_caches():
        try:
            c.unlink()
        except OSError:
            pass
    if not ready:
        _report(out, rows)
        return rows

    lock = CardLock(cfg, lock_holder or f"skeletons {out.name}", log=log, art_url=art_url, rig_url=env.url, side="rig") if use_lock else None
    proc = None
    started_here = False
    comfy_log = out / "comfy.log"
    try:
        if lock:
            lock.acquire()
        if comfyapi.is_up(art_url, timeout=2.0) and not comfyapi.queue_count(art_url):
            try:
                comfyapi.free(art_url)                       # the art ComfyUI puts its models away: the card is for rigging
            except Exception:  # noqa: BLE001
                pass
        if not env.is_up():
            log.info("starting the rigging ComfyUI (its console: %s); the first minutes are it reading its nodes", comfy_log)
            proc = env.start_comfy(comfy_log, cpu=False, extra_env={"COMFY_ENV_DEBUG_STACKTRACE": "1"})
            started_here = True
            t0 = time.time()
            while not env.is_up():
                if proc.poll() is not None:
                    raise RuntimeError(f"the rigging ComfyUI stopped by itself (exit {proc.returncode}). Its last lines:\n{comfy_tail(comfy_log)}")
                if time.time() - t0 > start_minutes * 60:
                    raise RuntimeError(f"the rigging ComfyUI did not answer within {start_minutes:.0f} minutes. Its last lines:\n{comfy_tail(comfy_log)}")
                if lock:
                    lock.beat()
                time.sleep(1 if env.command else 5)
            log.info("it answers after %.0f s; %s", time.time() - t0, comfyapi.memory_line(env.url))
        info = comfyapi.object_info(env.url)
        rig_out = env.output_dir
        for b in ready:
            for rg in (riggers or [rigger_for(b)]):
                rows.append(_rig_one(env, b, rg, motions, info, rig_out, out, timeout_sec, lock, comfy_log))
                _report(out, rows, partial=True)
    except Exception as e:  # noqa: BLE001 — a start failure fails every body that was waiting, in words
        log.error("%s", e)
        done = {(r["body"], r["rigger"]) for r in rows}
        for b in ready:
            rg = rigger_for(b)
            if (b["id"], rg) not in done:
                rows.append({"body": b["id"], "rigger": rg, "ok": False, "error": str(e)[:3000]})
    finally:
        if started_here and proc is not None:
            log.info("stopping the rigging ComfyUI")
            stop(proc)
        if lock:
            lock.release()
    _report(out, rows)
    return rows


def _rig_one(env: RigEnv, b: dict, rg: str, motions: list[str], info: dict, rig_out: Path, out: Path, timeout_sec: int,
             lock, comfy_log: Path) -> dict:
    name = f"{b['id']}__{rg}"
    row = {"body": b["id"], "rigger": rg, "ok": False}
    wanted = [out / f"{name}__{Path(m).stem.lower()}.fbx" for m in motions]
    if (out / f"{name}.fbx").exists() and all(w.exists() for w in wanted):
        row.update(ok=True, note="already there")
        log.info("%s: already there", name)
        return row
    prompt = build_rig(b, rg)
    (out / f"{name}.request.json").write_text(json.dumps(prompt, indent=1), encoding="utf-8")
    bad = comfyapi.check_against(prompt, info)
    if bad:
        row["error"] = "the request does not fit this ComfyUI: " + "; ".join(bad)
        log.error("%s: %s", name, row["error"])
        return row
    t1 = time.time()
    log.info("%s: rigging started (the first use of a rigger downloads its model files)", name)
    try:
        comfyapi.run(env.url, prompt, timeout_sec, poll=1.0 if env.command else 3.0, on_wait=(lock.beat if lock else None))
        rigged = next((f for f in (rig_out / f"{name}_mia.fbx", rig_out / f"{name}_mixamo.fbx")
                       if f.exists() and f.stat().st_mtime >= t1 - 2), None)
        if rigged is None:
            raise RuntimeError("the rigger finished but its .fbx is not in the rigging ComfyUI's output folder; there now: "
                               + ", ".join(sorted(f.name for f in rig_out.glob("*.fbx"))[-12:]))
        row["rig_seconds"] = round(time.time() - t1)
        log.info("%s: rigged in %.0f s (%s, %.1f MB)", name, time.time() - t1, rigged.name, rigged.stat().st_size / 2**20)
        if motions:
            motion_prompt = build_motion(rigged, name, motions)
            bad = comfyapi.check_against(motion_prompt, info)
            if bad:
                raise RuntimeError("the motion request does not fit this ComfyUI: " + "; ".join(bad))
            comfyapi.run(env.url, motion_prompt, timeout_sec, on_wait=(lock.beat if lock else None))
    except Exception as e:  # noqa: BLE001
        row["error"] = str(e)[:6000]
        log.error("%s: FAILED after %.0f s - %s", name, time.time() - t1, row["error"])
        log.error("the rigging ComfyUI's last lines:\n%s", comfy_tail(comfy_log, 60))
    # keep whatever was made (a rig without its motions is still worth looking at)
    made = sorted(f for f in rig_out.rglob("*") if f.is_file() and f.stat().st_mtime >= t1 - 2
                  and (f.name.startswith(name) or f.name.startswith(f"{b['id']}__orientation")))
    kept = []
    for f in made:
        target = out / f.name
        if f.suffix.lower() == ".fbx" and f.stem in (name + t for t in ("_mia", "_mixamo", "_vroid", "_articulationxl")):
            target = out / f"{name}.fbx"
        elif f.suffix.lower() == ".glb" and f.stem in (name + t for t in ("_mia", "_mixamo")):
            target = out / f"{name}_preview.glb"
        elif f.name.startswith(f"{b['id']}__orientation") and f.suffix.lower() == ".png":
            target = out / f"{b['id']}__orientation.png"
        shutil.copyfile(f, target)
        kept.append(target.name)
    missing = [w.name for w in wanted if not w.exists()] + ([] if (out / f"{name}.fbx").exists() else [f"{name}.fbx"])
    row.update(ok=not missing and "error" not in row, seconds=round(time.time() - t1), files=kept)
    if missing and "error" not in row:
        row["error"] = "it finished, but these files were not found in the rigging ComfyUI's output: " + ", ".join(missing)
        log.error("%s: %s (found: %s)", name, row["error"], kept)
    elif row["ok"]:
        log.info("%s: DONE in %.0f s -> %s", name, time.time() - t1, ", ".join(kept))
    return row


def _report(out: Path, rows: list[dict], partial: bool = False) -> None:
    (out / "report.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    if partial:
        return
    lines = [f"Skeletons '{out.name}': {sum(r['ok'] for r in rows)} of {len(rows)} made", ""]
    for r in rows:
        if r["ok"]:
            lines.append(f"  ok      {r['body']:<22} {r['rigger']:<7} " + (r.get("note") or f"{r.get('seconds', 0)} s"))
        else:
            lines.append(f"  FAILED  {r['body']:<22} {r['rigger']:<7} {' '.join(str(r.get('error', 'unknown')).splitlines()[:2])[:220]}")
    (out / "REPORT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
