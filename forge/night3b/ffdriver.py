"""Filter Forge driver (Night 3B, G14): build the command-line renderer's task XML, run it, collect the files.

What the renderer actually accepts — read from its own help (Filter Forge Help.chm → Miscellaneous → Command-Line
Renderer), its Resources/System/BatchSample.xml and the element names inside FFXCmdRenderer-x64.exe — is small:
`FFXCmdRenderer-x64.exe [-l log_prefix] tasks.xml`, and per <Task>: <Image value= width= height=> (a picture for an
effect filter; empty value + width/height for a texture filter), <Selection>, <Filter value=".ffxml">, <Preset value=N>
(0 = the first), <Result path= format=> with optional <Options>, optional <RenderingOptions> and <Gamma>; one
<GlobalSettings> with <RenderingOptions> (incl. NormalMapFlipY: false = DirectX, true = OpenGL) and
<BitmapFormatOptions>. There is NO element for seamless tiling, size, variation or the channel to render: the help
says those are stored in the preset ("Each preset stores … the Settings tab … the state of the Render Channels menu").
So in the forge:
  * a channel is a preset: `channels: {"final": 0, "normal": 9}` — preset 9 being one William saved in Filter Forge
    with Normal chosen in the Render Channels menu (Professional edition). Every factory preset renders the final image;
    asking a factory preset for another channel is refused with that explanation.
  * `seamless: true` is checked against the preset's own Settings (readable for factory presets) and the result's wrap
    seam is measured either way.
  * Filter Forge names extra channel files with its own suffixes (-normal, -height, -rough, -ao, -emis, … — the list
    below is from the renderer's strings); the collector picks those up as well as the Result path.
The licence: the filters are Filter Forge's (or their authors') and may not be redistributed, so the forge stores the
PATH of a filter, never the file — nothing here copies, moves or writes an .ffxml, and nothing writes into the install
folder (results, temp files and the log all go to the job's own out folder).
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image

from .. import config as cfgmod

TOOL_KEY_FALLBACK = "Filter Forge"
CHANNEL_SUFFIXES = {
    "-normal": "normal", "-norm": "normal", "-height": "height", "-bump": "bump", "-rough": "roughness",
    "-smooth": "smoothness", "-metal": "metallic", "-metalsm": "metallic_smoothness", "-albedo": "albedo",
    "-albedosm": "albedo_smoothness", "-diffuse": "diffuse", "-ao": "ambient_occlusion", "-occl": "occlusion",
    "-ro": "reflective_occlusion", "-emis": "emission", "-spec": "specular_strength", "-specexp": "specular_exponent",
    "-base": "base", "-mask": "mask", "-rma": "rma", "-mra": "mra", "-arm": "arm",
}
CHANNELS = {"final"} | set(CHANNEL_SUFFIXES.values())
FILTER_TYPES = {"0": "simple", "1": "legacy surface", "2": "PBR surface"}


class FilterForgeError(Exception):
    pass


# ------------------------------------------------------------------ configuration
def tool_cfg(cfg: dict | None = None) -> dict:
    """forge.json tools.filter_forge, re-read from disk (a running worker's cfg is from the moment it started)."""
    fresh = {}
    try:
        fresh = (cfgmod.load().get("tools") or {}).get("filter_forge") or {}
    except Exception:  # noqa: BLE001
        pass
    return {**(((cfg or {}).get("tools") or {}).get("filter_forge") or {}), **fresh}


def exe_path(cfg: dict | None = None) -> Path | None:
    raw = tool_cfg(cfg).get("exe")
    return Path(raw) if raw else None


def install_dir(exe: Path) -> Path:
    return exe.parent.parent if exe.parent.name.lower() == "bin" else exe.parent


_version_cache: dict = {}


def pe_strings(data: bytes) -> dict:
    """ProductName / ProductVersion / FileVersion from a Windows executable's version resource (UTF-16 strings)."""
    out = {}
    for key in ("ProductName", "ProductVersion", "FileVersion"):
        k = key.encode("utf-16-le") + b"\x00\x00"
        i = data.find(k)
        if i < 0:
            continue
        j = i + len(k)
        while j < len(data) - 1 and data[j:j + 2] == b"\x00\x00":        # padding to a 32-bit boundary
            j += 2
        end = j
        while end < len(data) - 1 and data[end:end + 2] != b"\x00\x00":
            end += 2
        try:
            out[key] = data[j:end].decode("utf-16-le").strip()
        except UnicodeDecodeError:
            pass
    return out


def version_info(exe: Path) -> dict:
    try:
        st = exe.stat()
    except OSError:
        return {}
    ck = (str(exe), st.st_mtime)
    if ck not in _version_cache:
        try:
            _version_cache[ck] = pe_strings(exe.read_bytes())
        except OSError:
            _version_cache[ck] = {}
    return _version_cache[ck]


def tool_key(info: dict) -> str:
    name = (info.get("ProductName") or TOOL_KEY_FALLBACK).strip()
    ver = (info.get("ProductVersion") or "").strip()
    return f"{name} {ver}".strip()


def doctor_lines(cfg: dict) -> list[str]:
    exe = exe_path(cfg)
    if not exe:
        return ["· Filter Forge: not installed (optional — set tools.filter_forge.exe in forge.json to use the filter_forge job type)"]
    if not exe.exists():
        return [f"· Filter Forge: not installed — {exe} does not exist (fix tools.filter_forge.exe in forge.json)"]
    info = version_info(exe)
    lines = [f"✓ Filter Forge {info.get('ProductVersion', '?')} at {exe}"]
    if os.name != "nt":
        lines.append("· Filter Forge renders only on Windows (this is not)")
    from .. import handoff as ho
    key = tool_key(info)
    rec = ho.load_tools().get(key)
    lines.append(f"  licence line for '{key}': " + (f"on file (commercial {'yes' if rec.get('commercial_ok') else 'NO'})" if rec
                                                    else "not on file — handoff_tool_add.bat (approve will ask)"))
    return lines


# ------------------------------------------------------------------ filters (read-only)
def library_dirs(cfg: dict | None = None) -> list[tuple[str, Path]]:
    dirs: list[tuple[str, Path]] = []
    exe = exe_path(cfg)
    if exe:
        dirs.append(("install folder (bundled filters)", install_dir(exe) / "Resources" / "System" / "Library"))
    for raw in tool_cfg(cfg).get("library_dirs") or []:
        dirs.append((f"library ({raw})", Path(raw)))
    for env in ("APPDATA", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if not base:
            continue
        for sub in ("Filter Forge 9", "Filter Forge"):
            for leaf in ("System/Library", "My Filters", "Library"):
                dirs.append((f"your library (%{env}%\\{sub}\\{leaf})", Path(base) / sub / leaf))
    seen, out = set(), []
    for label, d in dirs:
        try:
            key = str(d.resolve()).lower()
        except OSError:
            continue
        if key in seen or not d.is_dir():
            continue
        seen.add(key)
        out.append((label, d))
    return out


def library_id(path: Path) -> str | None:
    m = re.match(r"Library_(\d+)-(\d+)$", Path(path).stem)
    return f"{m.group(1)}-{m.group(2)}" if m else None


def read_filter(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"filter not found: {path}")
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as e:
        raise ValueError(f"{path.name} is not a readable .ffxml ({e})")
    info = root.find("Information")
    name = None
    if info is not None:
        name = info.get("name-en") or info.get("name") or (info.findtext("name") or "").strip() or None
    res = root.find(".//Result")
    ft = res.find("FilterType").get("value") if res is not None and res.find("FilterType") is not None else "0"
    comps = root.find("Components")
    tags = [c.tag for c in comps] if comps is not None else []
    needs_picture = any(re.fullmatch(r"Image\d*", t) for t in tags)
    presets = []
    for i, p in enumerate(root.findall("Presets/Preset")):
        s = p.find("Settings")
        a = s.attrib if s is not None else {}
        presets.append({"index": i, "seamless": a.get("seamless") == "true", "size_factor": float(a.get("size_factor") or 1),
                        "variation": a.get("variation"), "map_type": int(a.get("map_type") or 0),
                        "channels_set": a.get("channels_set"), "note": (p.findtext("notes") or p.get("notes") or "").strip() or None})
    return {"path": str(path), "file": path.name, "name": name or path.stem, "filter_type": FILTER_TYPES.get(ft, ft),
            "kind": "effect" if needs_picture else "texture", "library_id": library_id(path), "presets": presets}


def list_filters(cfg: dict | None = None) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for label, d in library_dirs(cfg):
        rows = []
        for f in sorted(d.rglob("*.ffxml")):
            try:
                info = read_filter(f)
            except (ValueError, OSError):
                rows.append({"file": f.name, "path": str(f), "kind": "?", "presets": 0, "seamless_presets": [], "name": "(unreadable)"})
                continue
            rows.append({"file": f.name, "path": str(f), "kind": info["kind"], "presets": len(info["presets"]),
                         "seamless_presets": [p["index"] for p in info["presets"] if p["seamless"]], "name": info["name"]})
        if rows:
            out[f"{label}: {d}"] = rows
    return out


def find_filter(cfg: dict | None, ref: str) -> Path:
    p = Path(ref)
    if p.exists():
        return p
    stem = p.stem if p.suffix.lower() == ".ffxml" else p.name
    for _label, d in library_dirs(cfg):
        hits = sorted(d.rglob(f"{stem}.ffxml"))
        if hits:
            return hits[0]
    raise FileNotFoundError(f"filter '{ref}' not found (looked in: " + ", ".join(str(d) for _l, d in library_dirs(cfg)) + ")")


# ------------------------------------------------------------------ the task file
def channel_map(job: dict) -> dict[str, int]:
    ch = job.get("channels") or ["final"]
    preset = int(job.get("preset") or 0)
    if isinstance(ch, dict):
        m = {str(k).lower(): int(v) for k, v in ch.items()}
    elif isinstance(ch, (list, tuple)):
        names = [str(c).lower() for c in ch]
        if names != ["final"]:
            raise ValueError("each channel is its own preset in Filter Forge — give `channels` as {\"final\": "
                             f"{preset}, \"normal\": <the number of a preset saved with Normal chosen in the Render Channels "
                             "menu>, …}; `filter-forge presets <filter>` lists the numbers")
        m = {"final": preset}
    else:
        raise ValueError("`channels` must be a list like [\"final\"] or a mapping like {\"final\": 0, \"normal\": 9}")
    bad = sorted(set(m) - CHANNELS)
    if bad:
        raise ValueError(f"unknown channel(s) {bad} — known: {', '.join(sorted(CHANNELS))}")
    return m


def _sub(parent, tag, **attrs):
    e = ET.SubElement(parent, tag)
    for k, v in attrs.items():
        e.set(k, str(v))
    return e


def build_tasks(filter_path: Path, channels: dict[str, int], out: Path, slot: str, input_path: Path | None,
                size: tuple[int, int], normal_flip_y: bool = True, bit_depth: int = 16) -> tuple[str, list[dict]]:
    """The task XML (text) and [{channel, preset, result}] — one task per channel. Pure."""
    out = Path(out)
    tasks = ET.Element("Tasks")
    rows = []
    for ch, preset in channels.items():
        t = _sub(tasks, "Task")
        if input_path is not None:
            _sub(t, "Image", value=str(input_path))
        else:
            _sub(t, "Image", value="", width=int(size[0]), height=int(size[1]))
        _sub(t, "Selection", value="")
        result = out / f"{slot}_{ch}.png"
        r = _sub(t, "Result", path=str(result), format="PNG")
        o = _sub(r, "Options")
        _sub(o, "BitDepth", value=int(bit_depth))
        _sub(o, "IncludeTransparency", value="true")
        _sub(o, "ImageCompression", value="BEST")
        _sub(t, "Filter", value=str(filter_path))
        _sub(t, "Preset", value=int(preset))
        rows.append({"channel": ch, "preset": int(preset), "result": str(result)})
    g = _sub(tasks, "GlobalSettings")
    ro = _sub(g, "RenderingOptions")
    for k, v in (("UseMultithreading", "true"), ("Dither", "true"), ("Progressive", "true"), ("OptimizeBlurs", "true"),
                 ("AntiAliasBitmapComponentSources", "false"), ("Jitter", "0"),
                 ("TemporaryFilesLocation", str(out / "_fftemp")), ("RAMUsageLimit", "60"),
                 ("NormalMapFlipY", "true" if normal_flip_y else "false")):
        _sub(ro, k, value=v)
    # every format section must be present: the renderer refused a block with PNG alone ("Item 'BMP' not found in
    # item 'BitmapFormatOptions'", proof run 2026-11-10 01:18) — so this is BatchSample.xml's block, PNG set our way
    bf = _sub(g, "BitmapFormatOptions")
    _sub(bf, "DefaultFormat", value="PNG")
    for fmt, opts in (("BMP", (("BitDepth", "32"), ("FlipRowOrder", "false"))),
                      ("JPG", (("Quality", "98"), ("FullPrecision", "true"))),
                      ("TIF", (("BitDepth", "8"), ("FloatFormat", "false"), ("IncludeTransparency", "true"), ("ImageCompression", "LZW"))),
                      ("TGA", (("BitDepth", "32"), ("IncludeTransparency", "true"), ("FlipRowOrder", "false"))),
                      ("PNG", (("BitDepth", str(int(bit_depth))), ("IncludeTransparency", "true"), ("ImageCompression", "BEST"))),
                      ("EXR", (("BitDepth", "32"), ("IncludeTransparency", "true"), ("ImageCompression", "PIZ"), ("FlipRowOrder", "false"))),
                      ("PFM", ())):
        sec = _sub(bf, fmt)
        for k, v in opts:
            _sub(sec, k, value=v)
    gm = _sub(g, "Gamma")                      # as in the shipped BatchSample.xml (sRGB)
    _sub(gm, "GammaValue", value="2.2")
    _sub(gm, "GammaCorrection", value="true")
    ET.indent(tasks, space="\t") if hasattr(ET, "indent") else None
    return '<?xml version="1.0" encoding="utf-8" ?>\n' + ET.tostring(tasks, encoding="unicode") + "\n", rows


def root_for(job: dict) -> Path:
    return cfgmod.ROOT


def _resolve(root: Path, p) -> Path:
    q = Path(str(p))
    return q if q.is_absolute() else Path(root) / q


def check_presets(info: dict, channels: dict[str, int], seamless: bool) -> list[str]:
    """Refuse what the filter file shows cannot work; return notes for what cannot be checked."""
    n = len(info["presets"])
    notes = []
    for ch, idx in channels.items():
        if idx < 0:
            raise ValueError(f"preset numbers start at 0 (got {idx} for {ch})")
        if idx < n:
            p = info["presets"][idx]
            if ch != "final" and p["map_type"] == 0 and not p.get("channels_set"):
                raise ValueError(f"preset {idx} of '{info['name']}' is a factory preset — it renders the final image, not the "
                                 f"{ch} map. In Filter Forge: choose {ch.title()} in the Render Channels menu, Presets tab → "
                                 f"Add Preset, then use that preset's number (factory presets are 0–{n - 1}; yours follow).")
            if seamless and not p["seamless"]:
                raise ValueError(f"preset {idx} of '{info['name']}' has Seamless Tiling off — pick a preset that has it "
                                 f"(seamless presets: {[q['index'] for q in info['presets'] if q['seamless']] or 'none'}) or save one "
                                 "with the Seamless Tiling box ticked")
        else:
            notes.append(f"preset {idx} ({ch}) is one of your own presets (the filter file has {n}); its settings are not in "
                         "the filter file, so channel and seamless are taken on trust and the result is measured")
    return notes


def task_xml(job: dict, out: Path, root: Path | None = None) -> tuple[str, list[dict], dict, list[str]]:
    root = Path(root or cfgmod.ROOT)
    fpath = _resolve(root, job["filter"])
    if fpath.suffix.lower() != ".ffxml":
        raise ValueError(f"`filter` must be an .ffxml file (got {fpath.name})")
    info = read_filter(fpath)
    channels = channel_map(job)
    inp = _resolve(root, job["input"]) if job.get("input") else None
    if inp is not None and not inp.exists():
        raise FileNotFoundError(f"input picture not found: {inp}")
    if inp is None and info["kind"] == "effect":
        raise ValueError(f"'{info['name']}' is an effect filter — it needs an `input` picture")
    size = tuple(int(x) for x in (job.get("size") or [1024, 1024]))
    if inp is None and (min(size) < 1 or max(size) > 16384):
        raise ValueError(f"size {size} is out of range")
    notes = check_presets(info, channels, bool(job.get("seamless")))
    xml, rows = build_tasks(fpath, channels, Path(out).resolve(), str(job.get("slot_name") or "texture"), inp, size,
                            bool(job.get("normal_flip_y", True)), int(job.get("bit_depth") or 16))
    return xml, rows, info, notes


# ------------------------------------------------------------------ measuring the results
def _arr(img: Image.Image) -> np.ndarray:
    if img.mode in ("I;16", "I;16B", "I", "F"):
        a = np.asarray(img).astype(np.float64)
        return (a / 65535.0)[..., None]
    if img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGB")
    a = np.asarray(img).astype(np.float64)
    if a.ndim == 2:
        a = a[..., None]
    scale = 65535.0 if a.max() > 255 else 255.0
    return a[..., :3] / scale


def load_png(path: Path) -> np.ndarray:
    """A PNG as floats 0..1, H×W×C (16-bit grey exactly; Pillow reads 16-bit colour PNGs as 8-bit)."""
    im = Image.open(path)
    if im.mode in ("RGB", "RGBA", "L", "I;16", "I;16B", "I", "F", "P", "LA"):
        if im.mode in ("P", "LA"):
            im = im.convert("RGBA")
        return _arr(im)
    return _arr(im.convert("RGB"))


def seam_score(a: np.ndarray) -> dict:
    """How visible the wrap seam is: the step across the wrap (last column → first column, last row → first row)
    divided by the larger steps between neighbouring interior columns/rows (their 95th percentile — a smooth periodic
    texture has its steepest step anywhere, the wrap included). ≈1 or less = seamless; ≫1 = a seam."""
    a = a.astype(np.float64)
    def ratio(x):                 # columns along axis 1
        steps = np.abs(np.diff(x, axis=1)).mean(axis=tuple(i for i in range(x.ndim) if i != 1))
        wrap = np.abs(x[:, 0] - x[:, -1]).mean()
        return float(wrap / max(float(np.percentile(steps, 95)), 1e-6))
    return {"x": round(ratio(a), 3), "y": round(ratio(np.swapaxes(a, 0, 1)), 3)}


def normal_convention(normal: np.ndarray, height: np.ndarray) -> dict:
    """Compare a rendered normal map with OpenGL normals computed from the same surface's height map:
    green agreeing = OpenGL (Godot), green opposed = DirectX. Red must agree for the comparison to mean anything."""
    from ..ops import lighting
    h = height[..., :3].mean(axis=-1) if height.ndim == 3 else height
    ref = np.asarray(lighting.normal_map(Image.fromarray(np.clip(h * 255 + 0.5, 0, 255).astype(np.uint8)).convert("RGB"),
                                         strength=2.0, smooth=1.0)).astype(np.float64) / 255.0
    n = normal[..., :3]
    if n.shape[:2] != ref.shape[:2]:
        raise ValueError("normal and height maps differ in size")
    def corr(a, b):
        a, b = a.ravel() - a.mean(), b.ravel() - b.mean()
        d = np.sqrt((a * a).sum() * (b * b).sum())
        return float((a * b).sum() / d) if d > 0 else 0.0
    r, g = corr(n[..., 0], ref[..., 0]), corr(n[..., 1], ref[..., 1])
    if r < 0.2:
        verdict = "unclear"
    elif g > 0.2:
        verdict = "opengl"
    elif g < -0.2:
        verdict = "directx"
    else:
        verdict = "unclear"
    return {"verdict": verdict, "red_agreement": round(r, 3), "green_agreement": round(g, 3)}


def game_normal(a: np.ndarray, flip_green: bool = False) -> Image.Image:
    """A rendered normal map → the game's 8-bit RGB `_n.png` (OpenGL, green = up)."""
    rgb = a[..., :3].copy()
    if flip_green:
        rgb[..., 1] = 1.0 - rgb[..., 1]
    return Image.fromarray(np.clip(rgb * 255.0 + 0.5, 0, 255).astype(np.uint8), "RGB")


def collect(rows: list[dict], out: Path) -> tuple[dict[str, Path], list[str]]:
    """Find what the renderer wrote: each task's Result path, plus any '<stem>-<channel suffix>' files."""
    out = Path(out)
    got, notes = {}, []
    for r in rows:
        p = Path(r["result"])
        if p.exists():
            got.setdefault(r["channel"], p)
        for q in sorted(out.glob(p.stem + "-*")):
            sfx = "-" + q.stem[len(p.stem) + 1:].split("-")[0].lower()
            ch = CHANNEL_SUFFIXES.get(sfx)
            if ch and ch not in got:
                got[ch] = q
                notes.append(f"{q.name}: Filter Forge's own {ch} file")
        if r["channel"] not in got:
            notes.append(f"no file came back for {r['channel']} (preset {r['preset']})")
    return got, notes


# ------------------------------------------------------------------ running
def run_renderer(exe: Path, task_file: Path, out: Path, timeout: int) -> tuple[int, str]:
    """Run FFXCmdRenderer in the job's folder (temp files go there via TemporaryFilesLocation). Returns (code, console).
    Only the task file is passed: the renderer printed its usage and did nothing when given `-l <folder\\prefix>`
    (proof run 2026-11-10 01:16), so its own log stays in %TEMP% and the console text is kept as render.log."""
    p = subprocess.run([str(exe), str(task_file)], cwd=str(out), capture_output=True,
                       text=True, errors="replace", timeout=int(timeout),
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return p.returncode, (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")


def render(job: dict, ctx, out: Path, runner=None) -> dict:
    """The filter_forge job handler."""
    from ..jobs.common import save_png, write_prov
    from ..ops import sheet as sh
    from ..night3b.handoff_jobs import tool_line
    out = Path(out)
    cfg = getattr(ctx, "cfg", None)
    exe = exe_path(cfg)
    if runner is None:
        if not exe:
            raise FilterForgeError("Filter Forge is not set up: forge.json has no tools.filter_forge.exe "
                                   "(e.g. \"C:\\\\Program Files\\\\Filter Forge 9\\\\Bin\\\\FFXCmdRenderer-x64.exe\")")
        if not exe.exists():
            raise FilterForgeError(f"Filter Forge is not installed where forge.json says: {exe}")
        if os.name != "nt":
            raise FilterForgeError("Filter Forge renders only on Windows — run this job on the Windows worker")
    root = Path(getattr(ctx, "root", None) or cfgmod.ROOT)
    xml, rows, info, notes = task_xml(job, out, root)
    inst = install_dir(exe).resolve() if exe else None
    if inst is not None and (inst == out.resolve() or inst in out.resolve().parents):
        raise FilterForgeError("refusing to write into the Filter Forge install folder")
    (out / "_fftemp").mkdir(parents=True, exist_ok=True)
    task_file = out / "tasks.xml"
    task_file.write_text(xml, encoding="utf-8", newline="\r\n")
    code, console = (runner or run_renderer)(exe, task_file, out, int(job.get("timeout_sec") or 900))
    (out / "render.log").write_text(console or "", encoding="utf-8", newline="\n")
    got, cnotes = collect(rows, out)
    notes += cnotes
    m = re.search(r"Tasks completed (\d+)\. Tasks failed (\d+)\.", console or "")
    if not got:
        tail = "\n".join((console or "").strip().splitlines()[-8:])
        if "Usage:" in (console or "") and "Starting rendering task" not in (console or ""):
            raise FilterForgeError(f"Filter Forge did not accept its command line (it printed its usage). Output:\n{tail}")
        raise FilterForgeError(f"Filter Forge wrote nothing (exit {code}). Last lines of its output:\n{tail}")
    slot = str(job.get("slot_name") or "texture")
    measured: dict = {}
    first = got.get("final") or next(iter(got.values()))
    fa = load_png(first)
    if job.get("seamless"):
        measured["seam"] = seam_score(fa)
        lim = float(job.get("seam_limit") or 1.5)
        if max(measured["seam"].values()) > lim:
            notes.append(f"the wrap seam is visible (x {measured['seam']['x']}, y {measured['seam']['y']}; ≈1 is seamless, "
                         f"limit {lim}) — in the 2026-11-10 tests the command-line renderer did not deliver a seamless wrap "
                         "even from presets with Seamless Tiling on, so make it tileable in the forge before tiling it")
    outputs = [Path(p).name for p in got.values()]
    if "normal" in got:
        na = load_png(got["normal"])
        flip = False
        h_ch = next((c for c in ("height", "bump") if c in got), None)
        if h_ch:
            conv = normal_convention(na, load_png(got[h_ch]))
            measured["normal_convention"] = {**conv, "checked_against": h_ch}
            if conv["verdict"] == "directx":
                flip = True
                notes.append("the normal map came back DirectX-style (green down) — flipped to OpenGL for the game's _n slot")
        else:
            measured["normal_convention"] = {"verdict": "set, not measured",
                                             "why": "NormalMapFlipY=true (OpenGL per the help); render a height or bump "
                                                    "channel too and the forge checks it"}
        save_png(game_normal(na, flip), out / f"{slot}_n.png")
        outputs.append(f"{slot}_n.png")
        measured["normal_flipped_by_forge"] = flip
    # contact: every channel, plus a 2×2 tiling of the final image when seamless was asked for
    tiles, labels = [], []
    for ch, p in got.items():
        tiles.append(Image.fromarray(np.clip(load_png(p)[..., :3] * 255 + 0.5, 0, 255).astype(np.uint8).squeeze())
                     .convert("RGB")); labels.append(ch)
    if job.get("seamless"):
        im = tiles[0]
        w, h = im.size
        t2 = Image.new("RGB", (w * 2, h * 2))
        for dx in (0, w):
            for dy in (0, h):
                t2.paste(im, (dx, dy))
        tiles.append(t2.resize((w, h))); labels.append(f"tiled 2×2 · seam x {measured['seam']['x']} y {measured['seam']['y']}")
    save_png(sh.contact_sheet(tiles, labels, cols=min(3, len(tiles)), cell=(384, 384), title=job.get("name")), out / "contact.png")
    vinfo = version_info(exe) if exe and exe.exists() else {}
    key = tool_key(vinfo) if vinfo else str(job.get("_tool_key") or TOOL_KEY_FALLBACK)
    lic = [tool_line(ctx, key)]
    inputs = [str(_resolve(root, job["input"]))] if job.get("input") else []
    if inputs:
        try:
            src_prov = Path(inputs[0]).parent / "prov.json"
            if src_prov.exists():
                lic = list(json.loads(src_prov.read_text(encoding="utf-8")).get("licences") or []) + lic
        except ValueError:
            pass
    ok = all(r.get("commercial_ok") is True for r in lic)
    write_prov(out, job, op="filter_forge", tool=key, filter_forge_version=vinfo.get("FileVersion"),
               filter=info["file"], filter_path=info["path"], filter_name=info["name"], filter_library_id=info["library_id"],
               filter_kind=info["kind"], filter_type=info["filter_type"], channels={r["channel"]: r["preset"] for r in rows},
               preset=int(job.get("preset") or 0), seamless=bool(job.get("seamless")), normal_flip_y=bool(job.get("normal_flip_y", True)),
               inputs=inputs, licences=lic, commercial_ok=ok, measured=measured, notes=notes,
               tasks={"completed": int(m.group(1)), "failed": int(m.group(2))} if m else None,
               filter_licence_note="the filter is used from its own folder by path and never copied — filters may not be "
                                   "redistributed (Filter Forge EULA); rendered results: commercial use per William")
    return {"outputs": outputs + ["contact.png", "tasks.xml"], "channels": sorted(got), "measured": measured,
            "notes": notes, "commercial_ok": ok, "tool": key, "exit_code": code}
