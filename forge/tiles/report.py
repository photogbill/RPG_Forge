"""The materials report: every source's take on every material, processed the same way, scored, on one sheet each.

  out/bakeoff/materials/
      <material>.png              one contact sheet: a row per source — the tile, tiled 3×3, lit N/E/S/W, its normals,
                                  and the tile beside a painting of the game's
      <material>/<source>.png     the processed tile (seamless, at its own full resolution) and <source>_n.png its normals
      verdict.json                the scores, a suggested order, and the person's picks
      MATERIALS_VERDICT.md        the same as a table, a draft for the person to decide

Processing (the same for every source): made seamless when its seam scores over 1.0 (offset and heal, night4/tileable), normals
from Filter Forge's own normal channel when it rendered one, else from luminance. Picks are the person's: a name that
starts with "claude" cannot pick.
"""
from __future__ import annotations
import json, re
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from ..ops.tiles import seam_score
from . import score as S

ROW_H = 192


def _src_label(suite: str, checkpoint: str) -> str:
    c = str(checkpoint or "")
    if suite.endswith("_ff_v1") or c.startswith("filter_forge:"):
        return "ff:" + c.split(":", 1)[-1]
    if "klein" in c.lower():
        return "klein-base" if "base" in c.lower() else "klein"
    return "sdxl"


def collect(cfg: dict, suites: list[str]) -> dict:
    """{material: {source: {"image", "normal", "seconds", "job"}}} from every finished job of the suites."""
    from .. import config as cfgmod
    from ..queue import Queue
    from ..bakeoff import job_image
    q = Queue(cfgmod.path_of(cfg, "jobs"), cfgmod.path_of(cfg, "out"))
    out: dict = {}
    for p in sorted((q.jobs / "done").glob("*.json")):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        meta = j.get("meta") or {}
        if str(j.get("batch", "")).replace("bakeoff/", "") not in suites:
            continue
        od = q.out / j["id"]
        img = None
        for cand in ("texture_final_tile.png", "texture_final.png"):
            if (od / cand).exists():
                img = od / cand
                break
        img = img or job_image(od, j)
        if not img:
            continue
        nrm = od / "texture_n.png"
        secs = None
        try:
            secs = (datetime.fromisoformat(j["finished_at"]) - datetime.fromisoformat(j["started_at"])).total_seconds()
        except Exception:  # noqa: BLE001
            pass
        src = _src_label(meta.get("suite", ""), meta.get("checkpoint", ""))
        key = meta.get("category") if meta.get("category") in ("war", "after") else None
        mid = meta.get("prompt_id")
        slot = out.setdefault(mid if not key else f"{mid}@{key}", {})
        slot[src] = {"image": str(img), "normal": str(nrm) if nrm.exists() else None, "seconds": secs, "job": j["id"]}
    return out


def process(image: Path, normal: Path | None = None, size: int = 1024) -> tuple[Image.Image, Image.Image, dict]:
    from ..ops.depth import normals_from_luminance
    im = Image.open(image).convert("RGB")         # kept at its own resolution (never squeezed): sharp tiles need it
    if im.width != im.height:
        side = min(im.size)
        im = im.crop((0, 0, side, side))
    before = seam_score(im)
    healed = False
    if before > 1.0:
        from ..night4 import tileable             # offset + heal the cross (the same CPU path the tileable job uses)
        fixed = tileable.blend(im, band=0.12, mode="cut").convert("RGB")
        if seam_score(fixed) < before:
            im, healed = fixed, True
    if normal and Path(normal).exists():
        n = Image.open(normal).convert("RGB").resize(im.size, Image.LANCZOS)
        nsrc = "filter forge's normal channel"
    else:
        n = normals_from_luminance(im, strength=2.0, smooth=1.0)
        nsrc = "from luminance"
    return im, n, {"seam_before": round(before, 3), "healed": healed, "normal_from": nsrc}


def contact_sheet(material: str, rows: list[dict], refs: list[Image.Image]) -> Image.Image:
    W = 1400
    out = Image.new("RGB", (W, 40 + ROW_H * max(1, len(rows))), (22, 22, 26))
    d = ImageDraw.Draw(out)
    d.text((10, 12), f"{material} — one row per source: tile · tiled 3x3 · lit N E S W · normals · beside a painting", fill=(235, 235, 235))
    for i, r in enumerate(rows):
        y = 40 + i * ROW_H
        a, n = r["albedo"], r["normal"]
        out.paste(a.resize((ROW_H - 12, ROW_H - 12)), (10, y))
        out.paste(S.tiled(a, 3, ROW_H - 12), (ROW_H + 4, y))
        out.paste(S.lit_strip(a, n, (ROW_H - 12) // 2), (2 * ROW_H, y))
        out.paste(n.resize(((ROW_H - 12) // 2, (ROW_H - 12) // 2)), (2 * ROW_H + 4 * ((ROW_H - 12) // 2) + 6, y))
        if refs:
            ref = refs[i % len(refs)].convert("RGB")
            h = (ROW_H - 12) // 2
            crop = ref.resize((int(ref.width * h * 2 / ref.height), h * 2)).crop((0, 0, h * 2, h * 2))
            side = Image.new("RGB", (h * 4, h * 2))
            side.paste(S.tiled(a, 2, h * 2), (0, 0))
            side.paste(crop, (h * 2, 0))
            out.paste(side, (W - h * 4 - 10, y))
        sc = r["score"]
        txt = (f"{r['source']}   seam {sc['seam']}  repetition {sc['repetition']}  normals {sc['normals']}  "
               f"palette {sc['palette'] if sc['palette'] is not None else '—'}  {sc['seconds'] or '—'} s"
               + ("  (healed)" if r["proc"]["healed"] else ""))
        d.text((2 * ROW_H, y + (ROW_H - 12) // 2 + 6), txt, fill=(235, 235, 235))
        if r.get("rank") == 1:
            d.text((2 * ROW_H, y + (ROW_H - 12) // 2 + 22), "suggested (scores only — your pick decides)", fill=(255, 210, 90))
    return out


def report(found: dict, out_dir: Path, refs: list[Image.Image] | None = None, names: dict | None = None,
           size: int = 1024) -> dict:
    """found: what collect() returns (or the same shape built by hand). Writes the sheets, tiles and verdict."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    vpath = out_dir / "verdict.json"
    old = json.loads(vpath.read_text(encoding="utf-8")) if vpath.exists() else {}
    verdict = {"written": datetime.now().isoformat(timespec="seconds"), "materials": {}, "picks": old.get("picks", {})}
    for mid in sorted(found):
        rows = []
        for src, r in sorted(found[mid].items()):
            a, n, proc = process(Path(r["image"]), Path(r["normal"]) if r.get("normal") else None, size)
            sd = out_dir / _safe(mid)
            sd.mkdir(exist_ok=True)
            a.save(sd / f"{_safe(src)}.png")
            n.save(sd / f"{_safe(src)}_n.png")
            rows.append({"source": src, "albedo": a, "normal": n, "proc": proc, "job": r.get("job"),
                         "score": S.score(a, n, refs, r.get("seconds")),
                         "tile": str(sd / f"{_safe(src)}.png"), "normal_file": str(sd / f"{_safe(src)}_n.png")})
        rows.sort(key=lambda r: S.rank_key(r["score"]))
        for i, r in enumerate(rows):
            r["rank"] = i + 1
        contact_sheet((names or {}).get(mid, mid), rows, refs or []).save(out_dir / f"{_safe(mid)}.png")
        verdict["materials"][mid] = [{k: r[k] for k in ("source", "rank", "score", "proc", "tile", "normal_file", "job")} for r in rows]
    vpath.write_text(json.dumps(verdict, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "MATERIALS_VERDICT.md").write_text(verdict_md(verdict, names or {}), encoding="utf-8", newline="\n")
    return verdict


def verdict_md(v: dict, names: dict) -> str:
    lines = ["# Materials verdict — draft", "",
             "Scores are the forge's; the pick is yours (Art → Bake-offs, or `tiles pick <material> <source>`). "
             "seam about 1.0 or less is seamless (over 1.5 shows a line) · repetition: lower repeats less · normals: higher lights better (0–1) · "
             "palette: lower sits closer to the paintings.", "",
             "| material | source | seam | repetition | normals | palette | s | suggested | picked |", "|---|---|---|---|---|---|---|---|---|"]
    for mid, rows in v["materials"].items():
        pick = (v.get("picks") or {}).get(mid, {}).get("source")
        for r in rows:
            s = r["score"]
            lines.append(f"| {names.get(mid, mid)} | {r['source']} | {s['seam']} | {s['repetition']} | {s['normals']} | "
                         f"{s['palette'] if s['palette'] is not None else '—'} | {s['seconds'] or '—'} | "
                         f"{'◆' if r['rank'] == 1 else ''} | {'✦' if pick == r['source'] else ''} |")
    return "\n".join(lines) + "\n"


def pick(out_dir: Path, material: str, source: str, who: str) -> dict:
    from ..suite import settings
    if not who or settings.is_assistant(who):
        raise ValueError("a pick is a person's call — Claude suggests, the person picks")
    vpath = Path(out_dir) / "verdict.json"
    v = json.loads(vpath.read_text(encoding="utf-8"))
    rows = {r["source"]: r for r in v["materials"].get(material, [])}
    if source not in rows:
        raise ValueError(f"no source '{source}' for {material} — have: {', '.join(rows) or 'none'}")
    v.setdefault("picks", {})[material] = {"source": source, "by": who, "at": datetime.now().isoformat(timespec="seconds"),
                                          "image": rows[source]["tile"], "normal": rows[source]["normal_file"]}
    vpath.write_text(json.dumps(v, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (Path(out_dir) / "MATERIALS_VERDICT.md").write_text(verdict_md(v, {}), encoding="utf-8", newline="\n")
    return v["picks"][material]


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.@-]+", "_", s)
