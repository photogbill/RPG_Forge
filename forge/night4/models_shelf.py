"""The model shelf report (Night 4, F8) — what William asked for: which of his downloaded models can go.

    models_report.bat   →  out/reports/MODELS_SHELF_<date>.md (+ .json)        REPORT ONLY — nothing is deleted

For every file under the model folders: does it load (a graph can run it), licence colour, used by how many approved
pictures, how often and when it was last used, the verdict from the two bake-off verdict docs (kept / dropped, with the
reason) and its size. The last table is "safe to delete — n GB": files that are dropped by a verdict, unusable, or
non-commercial, AND that nothing still needs — no approved picture, no queued or parked job, no setting in forge.json,
the game config or the character registry."""
from __future__ import annotations
import json
import re
from datetime import datetime
from pathlib import Path

from .. import config as cfgmod

EXTS = (".safetensors", ".ckpt", ".pt", ".pth", ".gguf", ".bin", ".sft")

# The verdicts, by file stem (normalised), from the bake-off verdicts of 2026-11-09/10 (William: "remove models that
# obviously won't be used"). "scope" says what the drop covers.
DROPPED = {
    "sd_xl_base_1.0": ("sprites", "invents shields/blades/rifles not in the prompt (sprite verdict); still the portrait pick and the forge default"),
    "sdvn6-realxl-detailface": ("sprites", "crops at the thigh, glamour drift (sprite verdict); portraits at most"),
    "gmic icon_v5-000180": ("sprites", "an icon checkpoint (sprite verdict); bake-off 1's alternate for icons"),
    "pixel_xl_v1": ("all", "real pixel art — wrong for the 1080p painted ruling (sprite verdict)"),
    "finalfantasy_tactics_sprite_sheet": ("all", "pure noise grids on 3 of 4 checkpoints (sprite verdict)"),
    "spritesheet (1)": ("all", "pure noise grids (sprite verdict); bake-off 1: a broken file from training set 128078"),
}
KEPT = {
    "artuniversesdxl_v8": "the sprite and scene pick (both verdicts)",
    "realvisxl_v5.0_fp16": "the photographic alternative; the horrific register (both verdicts)",
    "spritesheet": "multi-view turnarounds on ArtUniverse — under test (hair_test_v1 D)",
    "sprite_sheet_generator_2-_space_candy_media": "clean 3-view turnarounds (bake-off 1) — under test",
    "game_icon_v1.0": "the unified game-icon read (bake-off 1)",
    "rpg_portrait": "portraits with character (bake-off 1)",
    "retro_illustration": "scene alternate at 0.5 (bake-off 1)",
    "fftalevel4_20241206-1733511624460-000004": "16-bit layout references (bake-off 1)",
    "dd_table_rpg": "top-down room plans (bake-off 1)",
}


def norm(name: str) -> str:
    return re.sub(r"\.(safetensors|ckpt|pt|pth|gguf|bin|sft)$", "", Path(str(name)).name.lower()).strip()


def _files(cfg: dict) -> list[dict]:
    seen, out = set(), []
    for kind, dirs in (cfg.get("model_dirs") or {}).items():
        for d in cfgmod.model_dirs(cfg, kind):
            if not Path(d).exists():
                continue
            for p in sorted(Path(d).rglob("*")):
                if p.suffix.lower() in EXTS and p.is_file() and str(p).lower() not in seen:
                    seen.add(str(p).lower())
                    out.append({"file": p.name, "path": str(p), "kind_dir": kind, "gb": round(p.stat().st_size / 1e9, 2)})
    return out


def _usage(cfg: dict) -> dict[str, dict]:
    """{norm name: {"runs", "last", "queued"}} from finished jobs (their results name the models) and queued ones."""
    use: dict[str, dict] = {}
    jobs = cfgmod.path_of(cfg, "jobs")

    def names(j: dict) -> set[str]:
        r = j.get("result") if isinstance(j.get("result"), dict) else {}
        out = set()
        for v in (j.get("checkpoint"), r.get("checkpoint"), j.get("upscale_model")):
            if v:
                out.add(norm(v))
        for lo in list(j.get("loras") or []) + list(r.get("loras") or []):
            out.add(norm(lo.get("name") if isinstance(lo, dict) else lo))
        for rr in j.get("renders") or []:
            if isinstance(rr, dict) and rr.get("checkpoint"):
                out.add(norm(rr["checkpoint"]))
        return {n for n in out if n}

    for sub in ("done", "pending", "paused", "running"):
        for p in (jobs / sub).glob("*.json"):
            try:
                j = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for n in names(j):
                u = use.setdefault(n, {"runs": 0, "last": None, "queued": 0})
                if sub == "done":
                    u["runs"] += 1
                    t = j.get("finished_at")
                    if t and (u["last"] is None or t > u["last"]):
                        u["last"] = t
                else:
                    u["queued"] += 1
    return use


def _settings(cfg: dict, game: str) -> set[str]:
    """Model names a setting still points at: forge.json, the game config, the character registry."""
    from . import characters as chm
    txt = json.dumps(cfg) + json.dumps(cfgmod.game_config(cfg, game))
    for cid in chm.all_ids(cfg, game):
        try:
            txt += json.dumps(chm.load(cfg, game, cid))
        except chm.CharacterError:
            pass
    return {norm(m) for m in re.findall(r"[\w .()\-]+\.(?:safetensors|ckpt|pth|pt|gguf)", txt)}


def _approved(cfg: dict, game: str) -> dict[str, int]:
    from .. import manifest
    n: dict[str, int] = {}
    for a in manifest.load_approved(cfg, game).values():
        for l in a.get("licences") or []:
            if l.get("file"):
                n[norm(l["file"])] = n.get(norm(l["file"]), 0) + 1
    return n


def build(cfg: dict, game: str | None = None, scan: bool = True) -> tuple[Path, dict]:
    game = game or cfgmod.default_game(cfg)   # never a literal game (RPG_Forge is game-agnostic)
    from .. import bakeoff, model_report
    from ..jobs.common import Context
    inv = {r["file"]: r for r in (bakeoff.inventory(cfg, refresh=scan) or [])}
    ctx = Context(cfg=cfg, root=cfgmod.ROOT)
    use, need, appr = _usage(cfg), _settings(cfg, game), _approved(cfg, game)
    rows = []
    for f in _files(cfg):
        n = norm(f["file"])
        rec = inv.get(f["file"])
        if rec:
            group, why = model_report.classify(rec, ctx)
        else:
            group, why = ("helper", "not a model the scanner reads (config, encoder or upscaler)") if f["kind_dir"] not in \
                ("checkpoints", "loras", "diffusion_models") else ("unscanned", "not in the inventory — scan_models.bat")
        loads = group in ("ok", "non-commercial", "licence unknown", "helper")
        colour = {"ok": "green", "non-commercial": "red", "licence unknown": "grey"}.get(group, "grey" if loads else "—")
        u = use.get(n, {"runs": 0, "last": None, "queued": 0})
        if n in DROPPED:
            verdict, reason = (f"dropped ({DROPPED[n][0]})", DROPPED[n][1])
        elif n in KEPT:
            verdict, reason = "kept", KEPT[n]
        else:
            verdict, reason = "-", ""
        needed = []
        if appr.get(n):
            needed.append(f"{appr[n]} approved picture(s)")
        if u["queued"]:
            needed.append(f"{u['queued']} queued/parked job(s)")
        if n in need:
            needed.append("a setting (forge.json / game config / registry)")
        drop_all = n in DROPPED and DROPPED[n][0] == "all"
        candidate = (drop_all or not loads or group == "non-commercial") and group != "helper"
        rows.append({**f, "loads": loads, "group": group, "why": why, "licence": colour, "approved": appr.get(n, 0),
                     "runs": u["runs"], "last": u["last"], "queued": u["queued"], "verdict": verdict, "reason": reason,
                     "needed_by": needed, "safe_to_delete": candidate and not needed})
    safe = [r for r in rows if r["safe_to_delete"]]
    L = [f"# The model shelf — {datetime.now():%Y-%m-%d %H:%M}", "",
         "**Report only — nothing was deleted.** One row per file under the model folders (forge.json → model_dirs).", "",
         "| file | size | loads | licence | approved pictures | runs | last used | verdict |", "|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["kind_dir"], r["file"].lower())):
        L.append(f"| `{r['file']}` | {r['gb']:.1f} GB | {'yes' if r['loads'] else 'no'} | {r['licence']} | {r['approved']} | "
                 f"{r['runs']}{' (+' + str(r['queued']) + ' queued)' if r['queued'] else ''} | "
                 f"{(r['last'] or '-')[:10]} | {r['verdict']}{' — ' + r['reason'] if r['reason'] else ''} |")
    L += ["", f"## Safe to delete — {sum(r['gb'] for r in safe):.1f} GB in {len(safe)} file(s)", "",
          "Dropped by a verdict for every use, or unusable here, or non-commercial — and nothing still needs it "
          "(no approved picture, no queued or parked job, no setting). Delete them yourself in Explorer if you agree.", ""]
    by_verdict = [r for r in safe if r["verdict"].startswith("dropped") or r["group"] == "non-commercial"]
    cant_run = [r for r in safe if r not in by_verdict]
    L += [f"### Dropped by a verdict (or non-commercial) — {sum(r['gb'] for r in by_verdict):.1f} GB", ""]
    L += [f"- `{r['path']}` — {r['gb']:.1f} GB — {r['reason'] or r['why']}" for r in sorted(by_verdict, key=lambda r: -r["gb"])] or ["- (nothing)"]
    L += ["", f"### Nothing can run them here today — your call (a future graph might) — {sum(r['gb'] for r in cant_run):.1f} GB", ""]
    L += [f"- `{r['path']}` — {r['gb']:.1f} GB — {r['why']}" for r in sorted(cant_run, key=lambda r: -r["gb"])] or ["- (nothing)"]
    held = [r for r in rows if (r["verdict"].startswith("dropped") or not r["loads"] or r["group"] == "non-commercial")
            and not r["safe_to_delete"] and r["group"] != "helper"]
    if held:
        L += ["", "## Would go, but something still needs it", ""]
        L += [f"- `{r['file']}` ({r['gb']:.1f} GB) — {r['verdict'] if r['verdict'] != '-' else r['group']}; needed by "
              f"{', '.join(r['needed_by']) or 'a sprite-only drop — still used elsewhere'}" for r in held]
    p = cfgmod.path_of(cfg, "out") / "reports" / f"MODELS_SHELF_{datetime.now():%Y%m%d}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    p.with_suffix(".json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    return p, {"files": len(rows), "safe": len(safe), "safe_gb": round(sum(r["gb"] for r in safe), 1),
               "verdict_gb": round(sum(r["gb"] for r in by_verdict), 1), "cant_run_gb": round(sum(r["gb"] for r in cant_run), 1)}
