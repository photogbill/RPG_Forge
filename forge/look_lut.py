"""A town's colour grade, from William's own grading into the game (BUILD 98 Part 9).

William grades a set of the town's game stills in Photoshop or Lightroom the way he would a shoot and exports a
.cube LUT (Photoshop: File > Export > Color Lookup Tables, CUBE). This turns it into what Godot 4 reads for an
Environment's colour correction: a PNG of N slices side by side (N × N each; slice = blue, x = red, y = green) with a
.import beside it that tells Godot to import it as a 3D texture of N horizontal slices.

    python -m forge.look_lut make  <file.cube> <out folder> [--name linden_mills]
    python -m forge.look_lut identity <out folder> [--size 33]      a grade that changes nothing (to wire the hook)
    python -m forge.look_lut apply <file.cube> <picture> <out.png>  to see the grade on a still before the game

Pure Python and numpy; Pillow for the pictures. Claude Opus, 2026-11-21.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

import numpy as np


class LutError(ValueError):
    pass


def read_cube(path: Path) -> dict:
    """A .cube file (Adobe/Resolve 3D LUT): size N, domain, and an [N, N, N, 3] table indexed [b, g, r]."""
    size = None
    lo, hi = [0.0, 0.0, 0.0], [1.0, 1.0, 1.0]
    title = ""
    rows: list = []
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        u = line.upper()
        if u.startswith("TITLE"):
            title = line[5:].strip().strip('"')
        elif u.startswith("LUT_3D_SIZE"):
            size = int(line.split()[1])
        elif u.startswith("LUT_1D_SIZE"):
            raise LutError("this is a 1D LUT; export a 3D LUT (CUBE, 3D) from Photoshop")
        elif u.startswith("DOMAIN_MIN"):
            lo = [float(v) for v in line.split()[1:4]]
        elif u.startswith("DOMAIN_MAX"):
            hi = [float(v) for v in line.split()[1:4]]
        elif re.match(r"^[-+0-9.eE]", line):
            v = line.split()
            if len(v) >= 3:
                rows.append([float(v[0]), float(v[1]), float(v[2])])
    if not size:
        raise LutError("no LUT_3D_SIZE in the file")
    if len(rows) != size ** 3:
        raise LutError(f"a {size}³ LUT needs {size ** 3} rows; the file has {len(rows)}")
    t = np.array(rows, np.float32).reshape(size, size, size, 3)     # red changes fastest: [b][g][r]
    lo_a, hi_a = np.array(lo, np.float32), np.array(hi, np.float32)
    t = (t - lo_a) / np.where(hi_a - lo_a == 0, 1, hi_a - lo_a)
    return {"size": size, "table": np.clip(t, 0.0, 1.0), "title": title}


def identity(size: int = 33) -> dict:
    a = np.linspace(0.0, 1.0, size, dtype=np.float32)
    b, g, r = np.meshgrid(a, a, a, indexing="ij")
    return {"size": size, "table": np.stack([r, g, b], -1), "title": "identity"}


def to_strip(lut: dict) -> np.ndarray:
    """[N, N*N, 3] uint8: slice k (blue = k) at x in [k*N, (k+1)*N), x within = red, y = green (top row green 0)."""
    n, t = lut["size"], lut["table"]
    strip = np.zeros((n, n * n, 3), np.float32)
    for k in range(n):
        strip[:, k * n:(k + 1) * n] = t[k]                 # t[k] is [g][r]
    return np.clip(np.round(strip * 255.0), 0, 255).astype(np.uint8)


IMPORT = """[remap]

importer="3d_texture"
type="CompressedTexture3D"

[deps]

source_file="res://{res}"

[params]

compress/mode=0
compress/high_quality=false
compress/lossy_quality=0.7
compress/hdr_compression=1
compress/channel_pack=0
mipmaps/generate=false
mipmaps/limit=-1
slices/horizontal={n}
slices/vertical=1
"""


def make(cube: Path, out_dir: Path, name: str = "", res_dir: str = "") -> dict:
    from PIL import Image
    lut = read_cube(cube)
    name = name or Path(cube).stem
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / f"{name}_grade_lut.png"
    Image.fromarray(to_strip(lut), "RGB").save(png)
    res = f"{res_dir.strip('/')}/{png.name}" if res_dir else png.name
    (out_dir / f"{png.name}.import").write_text(IMPORT.format(res=res, n=lut["size"]), encoding="utf-8")
    meta = {"name": name, "size": lut["size"], "from": str(cube), "title": lut["title"], "png": str(png),
            "godot": "Environment > Adjustments > Color Correction: this PNG, imported as a 3D texture of "
                     f"{lut['size']} horizontal slices (the .import beside it says so)",
            "made": datetime.now().isoformat(timespec="seconds")}
    (out_dir / f"{name}_grade_lut.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


def apply(lut: dict, rgb: np.ndarray) -> np.ndarray:
    """Grade an [H, W, 3] uint8 picture with trilinear lookup (what the game's colour correction does)."""
    n, t = lut["size"], lut["table"]
    x = rgb.astype(np.float32) / 255.0 * (n - 1)
    i0 = np.clip(np.floor(x).astype(int), 0, n - 2)
    f = x - i0
    r0, g0, b0 = i0[..., 0], i0[..., 1], i0[..., 2]
    fr, fg, fb = f[..., 0:1], f[..., 1:2], f[..., 2:3]
    out = 0
    for db in (0, 1):
        for dg in (0, 1):
            for dr in (0, 1):
                w = (fr if dr else 1 - fr) * (fg if dg else 1 - fg) * (fb if db else 1 - fb)
                out = out + w * t[b0 + db, g0 + dg, r0 + dr]
    return np.clip(np.round(out * 255.0), 0, 255).astype(np.uint8)


def write_cube(lut: dict, path: Path) -> None:
    n, t = lut["size"], lut["table"]
    lines = [f'TITLE "{lut.get("title") or "forge"}"', f"LUT_3D_SIZE {n}"]
    for b in range(n):
        for g in range(n):
            for r in range(n):
                lines.append("%.6f %.6f %.6f" % tuple(t[b, g, r]))
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="A town's colour grade into Godot (BUILD 98 Part 9)")
    sub = ap.add_subparsers(dest="cmd")
    m = sub.add_parser("make"); m.add_argument("cube"); m.add_argument("out"); m.add_argument("--name", default="")
    m.add_argument("--res-dir", default="")
    i = sub.add_parser("identity"); i.add_argument("out"); i.add_argument("--size", type=int, default=33)
    a = sub.add_parser("apply"); a.add_argument("cube"); a.add_argument("picture"); a.add_argument("out")
    o = ap.parse_args(argv)
    if o.cmd == "make":
        print(json.dumps(make(Path(o.cube), Path(o.out), o.name, o.res_dir), indent=1))
    elif o.cmd == "identity":
        p = Path(o.out); p.mkdir(parents=True, exist_ok=True)
        write_cube(identity(o.size), p / "identity.cube")
        print(json.dumps(make(p / "identity.cube", p, "identity"), indent=1))
    elif o.cmd == "apply":
        from PIL import Image
        im = np.array(Image.open(o.picture).convert("RGB"))
        Image.fromarray(apply(read_cube(Path(o.cube)), im)).save(o.out)
        print(o.out)
    else:
        ap.print_help()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
