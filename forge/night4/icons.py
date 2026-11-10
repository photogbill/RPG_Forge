"""icon_batch (Night 4, F4): many item icons in one job, one hand per category.

Each item → the built-in `icon` job (render on a key colour → cut out → centred on a transparent canvas) at 2× the
game's icon size, then a 1× copy. Every item of a category is rendered on the category's ONE family seed, so a
category reads as drawn by one hand. The prompt template is expanded at submit ({{icon.house}}, {{icon.<category>}}
are Fable's placeholders); {name} and {description} are filled per item here from the game's own item data."""
from __future__ import annotations
import json
import logging
import zlib
from pathlib import Path

from PIL import Image

from ..jobs.common import Context, save_png, write_prov

log = logging.getLogger("forge.icons")
ICON_KEYS = ("checkpoint", "loras", "steps", "cfg", "sampler", "scheduler", "negative", "graph", "game", "style_prefix")


def _safe(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in str(s))[:60]


def _fill(template: str, it: dict) -> str:
    name = str(it.get("name") or it.get("id"))
    desc = str(it.get("description") or "").rstrip(". ")
    t = str(template).replace("{name}", name).replace("{description}", desc)
    return t.replace(": ,", ",").replace(", ,", ",").strip(" ,:")


def run(job: dict, ctx: Context, out: Path) -> dict:
    from .. import pipeline
    from ..jobs import get_handlers
    from ..ops import sheet as sh
    out = Path(out)
    items = [i for i in job.get("items") or [] if isinstance(i, dict) and i.get("id")]
    if not items:
        raise ValueError("icon_batch: `items` is empty")
    size = [int(v) for v in (job.get("size") or [256, 256])]
    template = job.get("prompt") or "{name}: {description}"
    if "{{" in str(template):
        raise ValueError("icon_batch: the prompt still holds {{blocks}} — submit it with submit.bat / produce.bat (they "
                         "expand the library first)")
    seeds = dict(job.get("seeds") or {})
    steps, cats = [], []
    for it in items:
        cat = str(it.get("category") or job.get("category") or "misc")
        seed = int(seeds.get(cat) or (1001 + zlib.crc32(cat.encode()) % 9000))
        seeds[cat] = seed
        st = {"type": "icon", "name": _safe(f"icon_{it['id']}"), "prompt": _fill(template, it), "seed": seed,
              "canvas": size[0] * 2, "size": list(job.get("render_size") or [1024, 1024]),
              "key_color": job.get("key") or "#ff00ff", "tolerance": int(job.get("tolerance") or 40), "variants": 1,
              **{k: job[k] for k in ICON_KEYS if job.get(k) is not None}}
        steps.append(st)
        cats.append(cat)
    res = pipeline.run({**job, "type": "pipeline", "steps": steps}, ctx, out, get_handlers())
    made, by_cat, licences = [], {}, []
    for it, cat, s in zip(items, cats, res["steps"]):
        sd = out / s["dir"]
        src = sd / "icon.png"
        big = Image.open(src).convert("RGBA")
        save_png(big, out / "icons@2x" / f"{it['id']}.png")
        small = big.resize((size[0], size[1]), Image.LANCZOS)
        save_png(small, out / "icons" / f"{it['id']}.png")
        made.append(f"icons/{it['id']}.png")
        by_cat.setdefault(cat, []).append((small, it))
        pp = sd / "prov.json"
        if pp.exists():
            for l in json.loads(pp.read_text(encoding="utf-8")).get("licences") or []:
                if l not in licences:
                    licences.append(l)
    for cat, pairs in by_cat.items():
        tiles = []
        for im, _ in pairs:
            bg = Image.new("RGBA", im.size, (52, 52, 58, 255)); bg.alpha_composite(im); tiles.append(bg.convert("RGB"))
        save_png(sh.contact_sheet(tiles, [str(it.get("name") or it["id"]) for _, it in pairs], cols=min(6, len(tiles)),
                                  cell=(size[0], size[1]), title=f"{job.get('name') or 'icons'} — {cat} (seed {seeds[cat]})"),
                 out / f"contact_{_safe(cat)}.png")
    ok = bool(licences) and all(l.get("commercial_ok") is True for l in licences)
    write_prov(out, job, op="icon_batch", items=[{"id": i["id"], "category": c, "wanted": i.get("wanted")} for i, c in zip(items, cats)],
               seeds=seeds, size=size, licences=licences, commercial_ok=ok, outputs=made,
               note="icons/<id>.png at the game's size; icons@2x/<id>.png for zoom; one family seed per category")
    log.info("icon_batch %s: %d icon(s) in %d categor(ies)", job.get("id"), len(made), len(by_cat))
    return {"outputs": made + [f"contact_{_safe(c)}.png" for c in by_cat], "icons": len(made), "seeds": seeds,
            "commercial_ok": ok}
