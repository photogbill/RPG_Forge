"""out/ housekeeping (Night 4, F3) — the report says what could be archived (nothing is moved or deleted by it).

    python -m forge housekeeping [--days 14]   → out/reports/housekeeping_<date>.md
    python -m forge housekeeping --dedupe       the bake-off trees' copies become hard links to the job's render (no picture lost)
    python -m forge housekeeping --prune-comfy  deletes ComfyUI's own copy of every forge picture (out/_comfy/forge*.png) older
                                                than 20 min — the forge fetched its copy the moment the job finished
(2026-11-11, William: "any images we don't need, can you delete? They add up in size over time." — only true duplicates.)
Candidates: bake-off renders older than N days that no review rated ≥ 4 and nothing approved came from; failed-job
folders; inline test folders. Kept off the list: anything approved or delivered (approved.json / delivered.json),
anything an approved picture was made from, out/_replaced and out/_approved_backup (those are the undo history)."""
from __future__ import annotations
import json
from datetime import datetime, timedelta
from pathlib import Path

from .. import config as cfgmod


def _size(p: Path) -> int:
    t = 0
    for f in p.rglob("*"):
        try:
            if f.is_file():
                t += f.stat().st_size
        except OSError:
            pass
    return t


def report(cfg: dict, days: int = 14, game: str | None = None) -> tuple[Path, dict]:
    game = game or cfgmod.default_game(cfg)   # never a literal game (RPG_Forge is game-agnostic)
    from .. import manifest
    from . import deliver as dl
    out_root = cfgmod.path_of(cfg, "out")
    jobs = cfgmod.path_of(cfg, "jobs")
    keep = {a.get("job_id") for a in manifest.load_approved(cfg, game).values()}
    keep |= {e.get("job_id") for e in dl.ledger(cfg, game)}
    cutoff = datetime.now() - timedelta(days=days)
    rows = {"bakeoff": [], "failed": [], "other_old": []}
    total = 0
    for d in sorted(p for p in out_root.iterdir() if p.is_dir() and not p.name.startswith("_") and p.name[:2] == "20"):
        try:
            mt = datetime.fromtimestamp(d.stat().st_mtime)
        except OSError:
            continue
        if mt > cutoff or d.name in keep:
            continue
        jf = None
        for sub in ("done", "failed"):
            if (jobs / sub / f"{d.name}.json").exists():
                jf = (sub, jobs / sub / f"{d.name}.json"); break
        batch = ""
        if jf:
            try:
                batch = json.loads(jf[1].read_text(encoding="utf-8")).get("batch") or ""
            except (OSError, ValueError):
                pass
        size = _size(d)
        total += size
        kind = "failed" if jf and jf[0] == "failed" else ("bakeoff" if str(batch).startswith("bakeoff") else "other_old")
        rows[kind].append((d.name, batch, size, mt))
    L = [f"# out/ housekeeping — {datetime.now():%Y-%m-%d %H:%M}", "",
         f"Report only — nothing was moved or deleted. Older than {days} days, not approved, not delivered: "
         f"**{total / 1e9:.1f} GB** in {sum(len(v) for v in rows.values())} folder(s).", ""]
    for kind, title in (("bakeoff", "Bake-off renders"), ("failed", "Failed jobs"), ("other_old", "Other")):
        r = rows[kind]
        L += [f"## {title} — {sum(x[2] for x in r) / 1e9:.2f} GB in {len(r)}", ""]
        for name, batch, size, mt in sorted(r, key=lambda x: -x[2])[:40]:
            L.append(f"- `{name}` {size / 1e6:.0f} MB · {batch} · {mt:%Y-%m-%d}")
        if len(r) > 40:
            L.append(f"- … and {len(r) - 40} more")
        L.append("")
    p = out_root / "reports" / f"housekeeping_{datetime.now():%Y%m%d}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(L), encoding="utf-8")
    return p, {k: len(v) for k, v in rows.items()} | {"gb": round(total / 1e9, 2)}


# ---------------------------------------------------------------- 2026-11-11: duplicates only
def prune_comfy(cfg: dict, older_min: float = 20.0) -> tuple[int, int]:
    """ComfyUI saves every picture to out/_comfy/ too; the forge fetches its own copy into out/<job>/ when the job
    finishes and never reads _comfy again. Delete forge*.png there older than `older_min` (a running job's file is
    younger). Returns (files, bytes)."""
    import time
    d = cfgmod.path_of(cfg, "out") / "_comfy"
    if not d.is_dir():
        return 0, 0
    cut = time.time() - older_min * 60
    n = b = 0
    for f in d.glob("forge*.png"):
        try:
            st = f.stat()
            if st.st_mtime < cut:
                f.unlink()
                n += 1
                b += st.st_size
        except OSError:
            continue
    return n, b


def dedupe(cfg: dict) -> dict:
    """Every bake-off picture is filed twice (by_model/, by_category/) beside the job's own render.png. Replace each
    filed copy that has the same size as its render with a hard link to it: same picture, one file on disk."""
    import os
    from .. import bakeoff
    jobs = cfgmod.path_of(cfg, "jobs") / "done"
    out_root = cfgmod.path_of(cfg, "out")
    r = {"linked": 0, "already": 0, "freed": 0, "skipped": 0}
    for jf in jobs.glob("*.json"):
        try:
            job = json.loads(jf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        meta = job.get("meta") or {}
        if not str(job.get("batch", "")).startswith("bakeoff/") or not meta.get("suite"):
            continue
        src = bakeoff.job_image(out_root / job.get("id", jf.stem), job)
        if src is None:
            continue
        for dest in bakeoff.organized_paths(meta["suite"], meta):
            try:
                if not dest.exists():
                    continue
                if os.path.samefile(src, dest):
                    r["already"] += 1
                    continue
                size = dest.stat().st_size
                if size != src.stat().st_size:
                    r["skipped"] += 1          # not the same picture (re-rendered?) — leave it
                    continue
                tmp = dest.with_name(dest.name + ".lnk_tmp")
                if tmp.exists():
                    tmp.unlink()
                os.link(src, tmp)
                os.replace(tmp, dest)
                r["linked"] += 1
                r["freed"] += size
            except OSError:
                r["skipped"] += 1
    return r
