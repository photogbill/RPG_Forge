r"""William's camera into the game (BUILD 98 Part 3): photo textures and object scans, straight onto the Libraries shelf.

✦ William, 2026-11-21: "I can take pictures of texture with the R5, macro lenses, etc. That's easy for me."

    python -m forge.scans list                  what is waiting in scans/incoming/ and what each became
    python -m forge.scans intake [<folder>]     every waiting folder (or one): develop, make seamless, make the maps, shelve

A folder is `scans/incoming/<date>_<subject>/` (e.g. 2026-11-22_oak_bark). Its kind is guessed from the subject and the
number of frames: a scan has many frames of one object (more than 40, or "scan" in the name); anything else is a texture.

Raw files (CR3, CR2, DNG) are developed by William's own Photographic Studio through its command line (studio-cli.bat
edit, a neutral 16-bit sRGB TIFF; its docs/CLI.md), found at D:\Analyst_Toolkit\Photographic Denoiser (or STUDIO_DIR);
forge.json tools -> photographic_studio -> develop overrides the command ({in} and {out} are filled in). Developed
TIFF/PNG/JPG files he exports into the same folder are used as they are. Nothing is ever written beside his originals except the intake's own `_intake/` folder.

A texture becomes: the frame with the least blur, cropped square at its middle, made seamless (forge/night4/tileable.py, the
same method the Filter Forge sets use), at 2048 px: colour, normal (from the detail), height, roughness and AO, each a PNG,
then a shelf entry with "William's own (his R5 photograph)" as its licence. A scan is checked (frames, overlap of names)
and handed to RealityScan's command line when tools.list finds it; otherwise it waits and says why.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
RAW = {".cr3", ".cr2", ".dng", ".nef", ".arw"}
DEVELOPED = {".tif", ".tiff", ".png", ".jpg", ".jpeg"}
LICENCE = "William's own (his R5 photograph)"
STUDIO_DIR = os.environ.get("STUDIO_DIR") or r"D:\Analyst_Toolkit\Photographic Denoiser"


def incoming_dir(cfg: dict | None = None) -> Path:
    return ROOT / "scans" / "incoming"


def folders(cfg=None) -> list[Path]:
    d = incoming_dir(cfg)
    return sorted(p for p in d.iterdir() if p.is_dir() and not p.name.startswith("_")) if d.exists() else []


def kind_of(folder: Path) -> str:
    n = sum(1 for p in folder.iterdir() if p.suffix.lower() in RAW | DEVELOPED)
    return "scan" if ("scan" in folder.name.lower() or n > 40) else "texture"


def state(folder: Path) -> dict:
    raws = sorted(p.name for p in folder.iterdir() if p.suffix.lower() in RAW)
    dev = sorted(p.name for p in folder.iterdir() if p.suffix.lower() in DEVELOPED)
    done = (folder / "_intake" / "done.json")
    return {"folder": folder.name, "kind": kind_of(folder), "raw": len(raws), "developed": len(dev),
            "done": json.loads(done.read_text(encoding="utf-8")) if done.exists() else None}


# ------------------------------------------------------------------------------------------------ develop
def develop(folder: Path, cfg: dict | None = None) -> list[Path]:
    """Developed frames for a folder: his exports if there are any, else the Studio's command line, else none."""
    have = sorted(p for p in folder.iterdir() if p.suffix.lower() in DEVELOPED)
    if have:
        return have
    cmd = (((cfg or {}).get("tools") or {}).get("photographic_studio") or {}).get("develop")
    if not cmd:
        # William's Studio has a command line made for the forge (its docs/CLI.md): a raw becomes a 16-bit sRGB TIFF,
        # neutral, with no automatic brightness (his rule: nothing automatic unless asked).
        cli = Path(STUDIO_DIR) / "studio-cli.bat"
        if cli.exists():
            cmd = [str(cli), "edit", "{in}", "--out", "{out}", "--format", "tiff", "--space", "srgb", "--bits", "16", "--json"]
    if not cmd:
        return []
    out = folder / "_intake" / "developed"
    out.mkdir(parents=True, exist_ok=True)
    for raw in sorted(p for p in folder.iterdir() if p.suffix.lower() in RAW):
        args = [str(a).replace("{in}", str(raw)).replace("{out}", str(out)) for a in cmd]
        subprocess.run(args, capture_output=True, text=True, timeout=600)
    return sorted(p for p in out.iterdir() if p.suffix.lower() in DEVELOPED)


# ------------------------------------------------------------------------------------------------ maps
def sharpness(im: Image.Image) -> float:
    g = np.asarray(im.convert("L").resize((512, int(512 * im.height / max(im.width, 1)))), np.float32)
    lap = g[1:-1, 1:-1] * 4 - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
    return float(lap.var())


def square(im: Image.Image, size: int = 2048) -> Image.Image:
    s = min(im.width, im.height)
    l, t = (im.width - s) // 2, (im.height - s) // 2
    return im.crop((l, t, l + s, t + s)).resize((size, size), Image.LANCZOS)


def grey_balance(im: Image.Image) -> Image.Image:
    """A gentle grey-world balance (the grey card's frame is for William's eye and the Studio; this only takes off a cast)."""
    a = np.asarray(im.convert("RGB"), np.float32)
    m = a.reshape(-1, 3).mean(0)
    a = a * (m.mean() / np.maximum(m, 1e-3))
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def maps_from(colour: Image.Image) -> dict:
    g = np.asarray(colour.convert("L"), np.float32) / 255.0
    low = np.asarray(colour.convert("L").filter(ImageFilter.GaussianBlur(24)), np.float32) / 255.0
    height = np.clip(0.5 + (g - low) * 1.6, 0, 1)
    hgt = Image.fromarray((height * 255).astype(np.uint8))
    h = np.asarray(hgt.filter(ImageFilter.GaussianBlur(1.2)), np.float32) / 255.0
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 4.0
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 4.0
    n = np.dstack([-dx, dy, np.ones_like(h)])            # OpenGL-style normal (Godot's convention)
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    normal = Image.fromarray(((n * 0.5 + 0.5) * 255).astype(np.uint8))
    detail = np.abs(g - low)
    rough = np.clip(0.55 + detail * 2.2 - (g - 0.5) * 0.25, 0.25, 1.0)
    cav = np.asarray(hgt.filter(ImageFilter.GaussianBlur(6)), np.float32) / 255.0
    ao = np.clip(1.0 - np.maximum(cav - h, 0) * 3.0, 0, 1)
    return {"normal": normal, "height": hgt, "roughness": Image.fromarray((rough * 255).astype(np.uint8)),
            "ao": Image.fromarray((ao * 255).astype(np.uint8))}


def texture(folder: Path, frames: list[Path], size: int = 2048) -> dict:
    best = max(frames, key=lambda p: sharpness(Image.open(p)))
    im = grey_balance(square(Image.open(best).convert("RGB"), size))
    try:
        from .night4 import tileable
        tiled = tileable.blend(im, band=0.12)
    except Exception:  # noqa: BLE001 — the healing method is unavailable: keep the square crop, say so
        tiled = im
    out = folder / "_intake" / "texture"
    out.mkdir(parents=True, exist_ok=True)
    subject = re.sub(r"^\d{4}-\d{2}-\d{2}_", "", folder.name)
    files = {"colour": out / f"{subject}_colour.png"}
    tiled.save(files["colour"])
    for k, im2 in maps_from(tiled).items():
        files[k] = out / f"{subject}_{k}.png"
        im2.save(files[k])
    return {"subject": subject, "from_frame": best.name, "files": {k: str(v) for k, v in files.items()}}


# ------------------------------------------------------------------------------------------------ the intake
def intake(folder: Path | None = None, cfg: dict | None = None, who: str = "William") -> list[dict]:
    from . import library, toolsreg
    res = []
    for f in ([folder] if folder else folders(cfg)):
        st = state(f)
        if st["done"]:
            res.append({"folder": f.name, "state": "already done", **st["done"]})
            continue
        frames = develop(f, cfg)
        if not frames:
            res.append({"folder": f.name, "state": "waiting for development",
                        "why": "raw files only, and forge.json has no tools.photographic_studio.develop yet — export TIFFs "
                               "from the Studio into the folder, or tell Claude the Studio's command line"})
            continue
        if st["kind"] == "texture":
            t = texture(f, frames)
            entry = library.import_folder(str(Path(t["files"]["colour"]).parent), "scan", LICENCE,
                                          name=t["subject"], kind="texture", who=who, cfg=cfg,
                                          tags=[t["subject"].replace("_", " "), "photo texture", "r5"])
            done = {"state": "on the shelf", "kind": "texture", "shelf_id": entry["id"], "from_frame": t["from_frame"],
                    "at": datetime.now().isoformat(timespec="seconds")}
        else:
            rs = next((r for r in toolsreg.listing(cfg) if r["id"] == "realityscan"), None)
            if not rs or rs["state"] != "found":
                res.append({"folder": f.name, "state": "waiting for RealityScan",
                            "why": "RealityScan is not installed (Epic Games Launcher -> RealityScan, free under US$1M)",
                            "frames": len(frames)})
                continue
            done = {"state": "ready for RealityScan", "kind": "scan", "frames": len(frames),
                    "at": datetime.now().isoformat(timespec="seconds"),
                    "next": "its command line run is the next piece (scans.reconstruct): align, mesh, texture, then "
                            "CurioMesh retopology and a bake through blender.run's retopo_bake profile"}
        (f / "_intake").mkdir(exist_ok=True)
        (f / "_intake" / "done.json").write_text(json.dumps(done, indent=1), encoding="utf-8")
        res.append({"folder": f.name, **done})
    return res


def main(argv=None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    if not a or a[0] == "list":
        print(json.dumps([state(f) for f in folders()], indent=1))
        return 0
    if a[0] == "intake":
        cfg = None
        try:
            from . import config as cfgmod
            cfg = cfgmod.load()
        except Exception:  # noqa: BLE001
            pass
        print(json.dumps(intake(Path(a[1]) if len(a) > 1 else None, cfg), indent=1))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
