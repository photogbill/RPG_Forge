"""Handler of the sprite_intake job (Night 4, F1). The work is in forge/night4/intake.py."""
from __future__ import annotations
import json
import logging
from pathlib import Path

from PIL import Image

from .. import config as cfgmod
from ..jobs.common import Context, save_png, write_prov
from . import intake as it

log = logging.getLogger("forge.intake")


def mapping_path(cfg_root: Path, game: str, character: str, variant: str | None, sheet: Path) -> Path:
    who = character + (f"__{variant}" if variant else "")
    return cfg_root / "games" / game / "intake" / who / f"{sheet.stem}.intake.json"


def _inside(p: Path, root: Path) -> bool:
    try:
        p.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _hexkey(v):
    if not v:
        return None
    if isinstance(v, str):
        from ..ops.alpha import hex_to_rgb
        return hex_to_rgb(v)
    return tuple(v)


def run(job: dict, ctx: Context, out: Path) -> dict:
    out = Path(out)
    src = ctx.resolve(job["input"])
    if not src.exists():
        raise it.IntakeError(f"sheet not found: {src}")
    if src.is_dir():
        raise it.IntakeError(f"{src} is a folder — one job per sheet (sprite_intake.bat takes a folder and makes one each)")
    game = job.get("game") or "turing_accords"
    character = str(job["character"])
    variant = job.get("variant")
    warnings: list[str] = []
    # the registry (F2): asymmetric characters must not be flipped silently
    asym = None
    try:
        from . import characters as chmod
        ch = chmod.load(ctx.cfg, game, character)
        asym = chmod.is_asymmetric(ch, variant)
    except Exception as e:  # noqa: BLE001 — a character with no registry file can still be cut
        warnings.append(f"no registry entry for '{character}' ({e}) — make one with characters.bat stubs")
    img = Image.open(src)
    img.load()
    det = it.detect(img, _hexkey(job.get("key")), int(job.get("tolerance") or 30))
    mp = ctx.resolve(job["mapping"]) if job.get("mapping") else mapping_path(ctx.root, game, character, variant, src)
    first = not mp.exists()
    if first:
        mapping = it.new_mapping(src, det, character, variant)
        if job.get("tool"):
            mapping["tool"] = job["tool"]
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(json.dumps(mapping, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
        log.info("intake: wrote the first guess %s (%s)", mp, mapping["guess"])
    else:
        mapping = json.loads(mp.read_text(encoding="utf-8"))
        if mapping.get("sheet_sha1") and mapping["sheet_sha1"] != it.sha1(src):
            guess = it.new_mapping(src, det, character, variant)
            gp = mp.with_name(mp.name.replace(".intake.json", ".intake.guess.json"))
            gp.write_text(json.dumps(guess, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
            warnings.append(f"the sheet changed since its mapping was made — figure numbers may have moved. Used the "
                            f"existing mapping; a fresh guess for the new sheet is in {gp.name}")
        mapping.setdefault("backdrop", det["backdrop"])
    if mapping.get("mirror") and asym:
        warnings.append(f"MIRRORED {', '.join(mapping['mirror'])} although '{character}' is marked asymmetric in the "
                        "registry (a holster on one hip) — the flipped facings carry it on the wrong side")
    cell = tuple(job.get("cell") or it.CELL)
    built = it.build(img, det["_fg"], mapping, cell, float(job.get("figure_height") or 0.92),
                     int(job["baseline"]) if job.get("baseline") is not None else 6, str(job.get("scale") or "uniform"))
    built["warnings"] = warnings + built["warnings"]
    sheet, anim = it.pack(built)
    outputs = []
    save_png(sheet, out / "sheet.png"); outputs.append("sheet.png")
    if anim is not None:
        save_png(anim, out / "anim.png"); outputs.append("anim.png")
    for fc, tiles in built["frames"].items():
        for i, t in enumerate(tiles):
            save_png(t, out / "frames" / f"{fc}_{i:02d}.png")
    save_png(it.numbers_sheet(img, det, mapping), out / "numbers.png"); outputs.append("numbers.png")
    from ..ops import sprites as sp
    present = [built["frames"][f][0] for f in it.FACINGS if f in built["frames"]]
    sp._gif(present, out / "turntable.gif", 2.0)
    outputs.append("turntable.gif")
    for fc, tiles in built["frames"].items():
        if len(tiles) > 1:
            sp._gif(tiles, out / f"anim_{fc}.gif", 8.0)
            outputs.append(f"anim_{fc}.gif")
    (out / "edges.md").write_text(it.edge_report_md(built, mapping, str(src)), encoding="utf-8")
    rep = {"sheet": str(src), "mapping": str(mp), "first_run": first, "guess": mapping.get("guess"),
           "confidence": mapping.get("confidence"), "checked_by_person": mapping.get("checked_by_person"),
           "backdrop": det["backdrop"], "found": len(det["figures"]),
           "dropped": [{"what": d["what"], "bbox": d["bbox"]} for d in det["dropped"]],
           **{k: v for k, v in built.items() if k != "frames"}}
    (out / "report.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
    tool = job.get("tool") or mapping.get("tool")
    from_forge = _inside(src, ctx.root / "out")
    if from_forge and not tool:
        licences = []          # made by a forge job: approve follows `inputs` to that job's models
    elif tool:
        from ..night3b.handoff_jobs import tool_line
        licences = [tool_line(ctx, str(tool))]
    else:
        licences = [{"role": "outside_tool", "file": "unnamed outside tool", "license": "not named — rerun with --tool "
                     "\"<name version>\" and record its licence with handoff_tool_add.bat", "commercial_ok": None}]
        built["warnings"].append("the program that made this sheet is not named — approve will refuse it until it is "
                                 "(sprite_intake.bat … --tool \"<name version>\")")
    ok = all(l.get("commercial_ok") is True for l in licences) if licences else None
    write_prov(out, job, op="sprite_intake", input=str(src), inputs=[str(src)] if from_forge else [], mapping=str(mp), character=character, variant=variant,
               licences=licences, commercial_ok=ok, outputs=outputs, scale=built["scale"], cell=list(cell),
               mirrored=built["mirrored"], missing=built["missing"],
               contract="sheet.png: one row of 8 facings S,SW,W,NW,N,NE,E,SE (Player.direction_index), cell "
                        f"{cell[0]}×{cell[1]}, feet on y={cell[1] - (job.get('baseline') if job.get('baseline') is not None else 6)}")
    log.info("intake %s: %d found, %d used, missing %s, %d warning(s)", src.name, len(det["figures"]),
             sum(1 for r in built["figures"] if r.get("used")), built["missing"], len(built["warnings"]))
    return {"outputs": outputs, "found": len(det["figures"]), "mapping": str(mp), "first_run": first,
            "guess": mapping.get("guess"), "confidence": mapping.get("confidence"), "missing": built["missing"],
            "warnings": built["warnings"], "commercial_ok": ok}
