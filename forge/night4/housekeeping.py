"""out/ housekeeping (Night 4, F3) — REPORT ONLY: what could be archived. Nothing is moved or deleted.

    python -m forge housekeeping [--days 14]   → out/reports/housekeeping_<date>.md
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


def report(cfg: dict, days: int = 14, game: str = "turing_accords") -> tuple[Path, dict]:
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
