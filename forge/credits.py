"""Credits for the models (Night 3, G8): every model that touched a shipped pixel, nameable on demand.

    python -m forge credits [--game <id>]   → out/reports/CREDITS_MODELS.md   (credits.bat)

Reads the provenance files in the game's asset folder (`_provenance/*.json`, written by `approve`); if the game folder
is not readable, the forge's own approval records (games/<game>/approved.json). Each model is listed once with its
licence, any licence condition, and how many shipped files it touched. Any approved file with no provenance, or with
a model whose licence is unknown or not commercial-OK, is listed loudly at the top — there should be none.
"""
from __future__ import annotations
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from . import config as cfgmod


def gather(cfg: dict, game: str) -> dict:
    from .manifest import load_approved, licence_conditions
    gcfg = cfgmod.game_config(cfg, game)
    asset_root = Path(gcfg.get("asset_root") or "")
    prov_dir = Path(gcfg.get("provenance_dir") or (asset_root / "_provenance"))
    approved = load_approved(cfg, game)
    source = "game _provenance folder"
    records: dict[str, dict] = {}
    if prov_dir.exists():
        for p in sorted(prov_dir.glob("*.json")):
            try:
                records[p.stem.replace("__", "/")] = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                records[p.stem.replace("__", "/")] = {"_unreadable": str(p)}
    else:
        source = "the forge's approval records (games/%s/approved.json) — the game folder is not readable here" % game
    models: dict[str, dict] = {}
    touched = defaultdict(set)
    problems = []
    names = set(approved) | set(records)
    for name in sorted(names):
        rec = records.get(name)
        a = approved.get(name) or {}
        if prov_dir.exists() and rec is None:
            problems.append(f"{name}: approved, but there is NO provenance file in {prov_dir}")
        chain = (rec or {}).get("licences") if rec and not rec.get("_unreadable") else a.get("licences")
        if rec and rec.get("_unreadable"):
            problems.append(f"{name}: provenance file unreadable ({rec['_unreadable']})")
        if not chain:
            problems.append(f"{name}: no licence chain on record")
            continue
        for c in chain:
            f = c.get("file") or "?"
            m = models.setdefault(f, {"file": f, "model": c.get("model"), "license": c.get("license"),
                                      "commercial_ok": c.get("commercial_ok"), "roles": set()})
            m["roles"].add(c.get("role") or "?")
            touched[f].add(name)
            if c.get("commercial_ok") is not True:
                problems.append(f"{name}: {f} has licence '{c.get('license')}' — commercial OK: {c.get('commercial_ok')}")
    for f, m in models.items():
        m["files"] = len(touched[f])
        m["roles"] = sorted(m["roles"])
        conds = licence_conditions(cfg, [{"file": f}])
        m["condition"] = "; ".join(conds) if conds else None
    return {"game": game, "source": source, "approved": len(names), "models": sorted(models.values(), key=lambda m: -m["files"]),
            "problems": problems}


def write(cfg: dict, game: str) -> tuple[Path, dict]:
    g = gather(cfg, game)
    L = [f"# Models used in shipped art — {game}", "",
         f"Generated {datetime.now():%Y-%m-%d %H:%M} by `python -m forge credits`, from {g['source']}.", ""]
    if g["problems"]:
        L += ["## ⚠ PROBLEMS — fix these before shipping", ""] + [f"- **{p}**" for p in g["problems"]] + [""]
    if not g["approved"]:
        L += ["Nothing has been approved into the game yet — no shipped file, no model to credit.", ""]
    else:
        L += [f"{g['approved']} approved file(s). Every model below touched at least one of them.", "",
              "| model file | model | licence | commercial OK | used as | shipped files | condition |", "|---|---|---|---|---|---|---|"]
        for m in g["models"]:
            L.append(f"| {m['file']} | {m['model'] or ''} | {m['license'] or ''} | {m['commercial_ok']} | {', '.join(m['roles'])} | "
                     f"{m['files']} | {m['condition'] or ''} |")
        L.append("")
    p = cfgmod.path_of(cfg, "out") / "reports" / "CREDITS_MODELS.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    return p, g
