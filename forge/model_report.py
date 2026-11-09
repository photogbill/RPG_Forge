"""Which downloaded models can the forge actually use? (roadmap N9c) — `python -m forge models unusable`

Writes out/unusable_models.md. REPORT ONLY: nothing is ever deleted; the person decides. Four groups:
    no graph       no forge graph can run it today (SD1.5, FLUX.3, MOSS-Image, unrecognised files) — delete candidates
    non-commercial runs, but its licence forbids commercial use — experiments only, never in the game
    licence unknown runs; nothing it makes can be approved until someone checks its page (licence.bat)
    ok             runs, commercial-OK
Helpers (text encoders, VAEs) are listed separately: they are not run on their own.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

from . import config as cfgmod

GRAPHS = {"sdxl": "sdxl", "flux1": "flux1", "flux2": "flux2_klein", "krea2": "krea2"}
WHY_NOT = {"sd15": "SD 1.5 — the forge has no SD 1.5 graph (and SD 1.5 LoRAs do nothing on SDXL)",
           "sd15/sd2": "SD 1.x/2.x — no graph", "sd2": "SD 2 — no graph", "sd15 (by size)": "looks like SD 1.5 by size — no graph",
           "flux3": "FLUX.3 — the forge has no FLUX.3 graph yet",
           "unknown": "architecture not recognised from the file header"}
HELPER_HINTS = ("vae", "qwen3vl", "qwen_3", "t5xxl", "clip_l", "text_encoder", "umt5")


def licence_family(name: str, base: str) -> str | None:
    """Licences that follow from what a model IS, readable from its name: FLUX.1 [dev] and its derivatives, the FLUX.2
    [klein] 9B. Only used when no licence is on record — a person's own check (licence.bat) always wins."""
    low = name.lower()
    if base == "flux1" and ("dev" in low or "dedistill" in low):
        return "FLUX.1 [dev] Non-Commercial License (a dev model or a dev derivative)"
    if base == "flux2" and "9b" in low:
        return "FLUX Non-Commercial License (FLUX.2 [klein] 9B)"
    return None


def _licence(ctx, name: str) -> dict:
    from .jobs.common import model_licence
    return model_licence(ctx, name)


def classify(rec: dict, ctx) -> tuple[str, str]:
    """(group, reason) for one inventory record."""
    name, kind, base = rec["file"], rec.get("kind"), str(rec.get("base") or "unknown")
    low = name.lower()
    if kind in ("vae", "text_encoder") or any(h in low for h in HELPER_HINTS):
        return "helper", f"{kind or 'helper'} — loaded by a graph, not run on its own"
    if "moss" in low:
        return "no graph", "MOSS-Image — no graph yet (F13: its licence must be found and filed first)"
    b = base.split()[0]
    if b == "unknown" and ("flux.1" in low or "flux1" in low):
        b = "flux1"                               # header not recognised; the flux1 suite runs it by name
    graph = GRAPHS.get(b)
    if kind in ("lora", "lycoris"):
        if graph is None:
            return "no graph", f"LoRA for {base}: " + WHY_NOT.get(base, "no graph for that architecture")
    elif graph is None:
        return "no graph", WHY_NOT.get(base, f"{base} — no graph")
    lic = _licence(ctx, name)
    ok = lic.get("commercial_ok")
    where = f"{GRAPHS.get(b, b)} graph"
    if ok is False:
        return "non-commercial", f"runs on the {where}; licence {lic.get('license')} — experiments only, never shipped"
    if ok is None:
        fam = licence_family(name, b)
        if fam:
            return "non-commercial", f"runs on the {where}; {fam} (by its name — confirm on its page) — experiments only"
        if b == "flux1":
            return "licence unknown", (f"runs on the {where}; most FLUX.1 fine-tunes are FLUX.1 [dev] derivatives (non-commercial) "
                                       "unless the page says schnell/Apache — check its page, then licence.bat")
        return "licence unknown", f"runs on the {where}; check its page, then licence.bat"
    return "ok", f"runs on the {where}; {lic.get('license')}"


def report(cfg: dict) -> tuple[str, dict[str, list]]:
    from .jobs.common import Context
    ctx = Context(cfg=cfg, root=cfgmod.ROOT)
    p = cfgmod.ROOT / "models" / "inventory.json"
    if not p.exists():
        raise FileNotFoundError("models/inventory.json not found — run scan_models.bat (python -m forge models scan) first")
    recs = json.loads(p.read_text(encoding="utf-8"))
    recs = recs if isinstance(recs, list) else (recs.get("models") or recs.get("files") or [])
    groups: dict[str, list] = {"no graph": [], "non-commercial": [], "licence unknown": [], "ok": [], "helper": []}
    for r in recs:
        g, why = classify(r, ctx)
        groups[g].append((r["file"], r.get("gb") or 0, why, r.get("path") or ""))
    lines = ["# Downloaded models — what the forge can use", "",
             f"Generated {datetime.now():%Y-%m-%d %H:%M} by `python -m forge models unusable` from models/inventory.json. "
             "**Report only — nothing was deleted.**", ""]
    titles = {"no graph": "No graph can run these today — delete candidates (or keep for later)",
              "non-commercial": "Run, but non-commercial — experiments only, never in the game",
              "licence unknown": "Run, licence unknown — nothing they make can be approved until checked",
              "ok": "Run, commercial-OK", "helper": "Helpers (text encoders, VAEs)"}
    for g in ("no graph", "non-commercial", "licence unknown", "ok", "helper"):
        items = sorted(groups[g])
        gb = sum(x[1] for x in items)
        lines += [f"## {titles[g]} — {len(items)} file(s), {gb:.1f} GB", ""]
        lines += [f"- `{f}` ({s:.1f} GB) — {why}" for f, s, why, _ in items] or ["- (none)"]
        lines.append("")
    return "\n".join(lines) + "\n", groups
