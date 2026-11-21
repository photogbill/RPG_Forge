"""Filter Forge: every channel, with nobody saving a preset by hand (BUILD 87, Part 1).

What Filter Forge's own help says (read 2026-11-19; pages Render Channels, Presets, Command-Line Renderer):
  * a preset stores "the state of the Render Channels Menu" beside its controls, lighting and anti-aliasing;
  * the task file has no element for the channel — the only way to a channel is a preset;
  * a library filter's own presets sit inside the filter file; presets a person adds to a library filter are kept
    somewhere else, and the command-line renderer SKIPS those ("to render them, copy the filter to a custom folder …
    and point the Filter value there"). So the earlier route — save a Normal preset in the Filter Forge window, give
    the forge its number — could never have worked for a library filter.
  * the menu's order: legacy surface filters — Final, Diffuse, Bump, Normal, Specular Strength, Specular Exponent,
    Metallicity, Ambient Occlusion, Reflective Occlusion; PBR surface filters — Final, Albedo, Height, Normal,
    Roughness, Metallic, Emission, Occlusion; simple filters — Final only.

What the help does not say is how a preset writes that state down. Every preset's <Settings> carries map_type="0", so
the forge takes that for the menu's state and PROVES it by rendering rather than trusting the name: `probe` writes one
working copy of the filter per number — every preset's map_type set to it, so the preset number means what it always
meant — renders each small, and names what came back by what the picture is: the same as the final picture; a normal
map (blue, red and green centred); a grey map whose slopes agree with that normal map (height); a colour map; a flat
grey. Those anchors must sit where the menu's order puts them before the other grey maps (roughness, occlusion, the
specular pair) are named by the order. What was learned is kept in local/ff_channels.json, per filter type.

The working copies live in the job's own folder (never in Filter Forge's folders) and are removed when the render is
done — the forge still stores the PATH of a filter and nothing else; a filter is never committed, moved or passed on.
"""
from __future__ import annotations

import json
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image

from .. import config as cfgmod
from ..night3b import ffdriver
from . import look

MENU = {
    "legacy surface": ("final", "diffuse", "bump", "normal", "specular_strength", "specular_exponent", "metallic",
                       "ambient_occlusion", "reflective_occlusion"),
    "PBR surface": ("final", "albedo", "height", "normal", "roughness", "metallic", "emission", "occlusion"),
    "simple": ("final",),
}
HEIGHT_NAMES = ("height", "bump")
COLOUR_NAMES = ("diffuse", "albedo")
STORE = Path("local") / "ff_channels.json"
WORK = "_ffwork"
# what a set needs from each filter type: {the forge's channel: the menu's name}
NEEDS = {
    "legacy surface": {"normal": "normal", "height": "bump", "ambient_occlusion": "ambient_occlusion",
                       "specular_strength": "specular_strength", "specular_exponent": "specular_exponent",
                       "metallic": "metallic"},
    "PBR surface": {"normal": "normal", "height": "height", "roughness": "roughness", "ambient_occlusion": "occlusion",
                    "metallic": "metallic"},
    "simple": {},
}
_PRESETS = re.compile(rb"<Presets\b[^>]*>.*?</Presets\s*>", re.S)
_SETTINGS = re.compile(rb"<Settings\b[^>]*?/?>", re.S)


# ------------------------------------------------------------------ the working copy
def _set_attr(tag: bytes, name: bytes, value: bytes) -> bytes:
    pat = re.compile(rb"(\b" + name + rb'\s*=\s*")[^"]*(")')
    if pat.search(tag):
        return pat.sub(lambda m: m.group(1) + value + m.group(2), tag, count=1)
    end = b"/>" if tag.rstrip().endswith(b"/>") else b">"
    body = tag.rstrip()[: -len(end)].rstrip()
    return body + b" " + name + b'="' + value + b'"' + (b"/>" if end == b"/>" else b">")


def working_copy(data: bytes, map_type: int | None = None, variation: int | None = None) -> tuple[bytes, int]:
    """The filter file's bytes with every preset's map_type (and, if asked, variation) set — nothing else touched,
    byte for byte. Returns (new bytes, how many presets were set)."""
    m = _PRESETS.search(data)
    if not m:
        raise ffdriver.FilterForgeError("this filter file has no <Presets> inside it, so there is no preset to carry a channel")
    n = 0

    def one(t: re.Match) -> bytes:
        nonlocal n
        tag = t.group(0)
        if map_type is not None:
            tag = _set_attr(tag, b"map_type", str(int(map_type)).encode())
        if variation is not None:
            tag = _set_attr(tag, b"variation", str(int(variation)).encode())
        n += 1
        return tag
    block = _SETTINGS.sub(one, m.group(0))
    if n == 0:
        raise ffdriver.FilterForgeError("this filter's presets have no <Settings>, so there is nowhere to write the channel")
    return data[: m.start()] + block + data[m.end():], n


def write_copies(filter_path: Path, out: Path, numbers: list[int], variation: int | None = None) -> dict[int, Path]:
    """One working copy a number under <out>/_ffwork/<number>/<the filter's own file name>. Refuses Filter Forge's folders."""
    filter_path, out = Path(filter_path), Path(out)
    data = filter_path.read_bytes()
    made = {}
    for k in numbers:
        d = out / WORK / f"{int(k):02d}"
        d.mkdir(parents=True, exist_ok=True)
        new, _n = working_copy(data, int(k), variation)
        p = d / filter_path.name
        if p.resolve() == filter_path.resolve():
            raise ffdriver.FilterForgeError("refusing to write over the filter itself")
        p.write_bytes(new)
        made[int(k)] = p
    return made


def remove_copies(out: Path) -> int:
    """Take the working copies away again (the forge keeps a filter's path, never the filter). Returns files removed."""
    n = 0
    base = Path(out) / WORK
    if not base.is_dir():
        return 0
    for p in sorted(base.rglob("*"), reverse=True):
        try:
            if p.is_file():
                p.unlink()
                n += 1
            else:
                p.rmdir()
        except OSError:
            pass
    try:
        base.rmdir()
    except OSError:
        pass
    return n


# ------------------------------------------------------------------ the task file
def tasks_xml(copies: dict[str, Path], preset: int, out: Path, slot: str, size: tuple[int, int],
              normal_flip_y: bool = True, bit_depth: int = 16) -> tuple[str, list[dict]]:
    """One <Task> a working copy, in the shape ffdriver's own task file has (its global settings, once)."""
    root, rows = None, []
    for label, path in copies.items():
        xml, r = ffdriver.build_tasks(Path(path), {str(label): int(preset)}, Path(out).resolve(), slot, None, size,
                                      normal_flip_y, bit_depth)
        t = ET.fromstring(xml.split("?>", 1)[1])
        if root is None:
            root = t
        else:
            kids = list(root)
            at = next((i for i, c in enumerate(kids) if c.tag == "GlobalSettings"), len(kids))
            root.insert(at, t.find("Task"))
        rows += r
    if root is None:
        raise ValueError("nothing to render")
    if hasattr(ET, "indent"):
        ET.indent(root, space="\t")
    return '<?xml version="1.0" encoding="utf-8" ?>\n' + ET.tostring(root, encoding="unicode") + "\n", rows


def _run(job: dict, ctx, out: Path, copies: dict[str, Path], preset: int, slot: str, size, runner, timeout: int,
         log_name: str = "render.log") -> tuple[dict[str, dict], str, int]:
    """Render the working copies. Returns ({label: {"file": Path | None, "own_name": str | None}}, console, exit code)."""
    cfg = getattr(ctx, "cfg", None)
    exe = ffdriver.exe_path(cfg)
    xml, rows = tasks_xml(copies, preset, out, slot, tuple(int(x) for x in size), bool(job.get("normal_flip_y", True)),
                          int(job.get("bit_depth") or 16))
    (out / "_fftemp").mkdir(parents=True, exist_ok=True)
    task_file = out / ("tasks.xml" if log_name == "render.log" else "tasks_" + log_name.replace(".log", ".xml"))
    task_file.write_text(xml, encoding="utf-8", newline="\r\n")
    code, console = (runner or ffdriver.run_renderer)(exe, task_file, out, int(timeout))
    (out / log_name).write_text(console or "", encoding="utf-8", newline="\n")
    got: dict[str, dict] = {}
    for r in rows:
        p = Path(r["result"])
        rec = {"file": p if p.exists() else None, "own_name": None}
        for q in sorted(Path(out).glob(p.stem + "-*")):                 # Filter Forge's own "<name>-normal.png" style
            sfx = "-" + q.stem[len(p.stem) + 1:].split("-")[0].lower()
            name = ffdriver.CHANNEL_SUFFIXES.get(sfx)
            if name and rec["file"] is None:
                rec = {"file": q, "own_name": name}
        got[r["channel"]] = rec
    return got, console or "", code


def _check_ready(ctx, out: Path, runner) -> Path | None:
    cfg = getattr(ctx, "cfg", None)
    exe = ffdriver.exe_path(cfg)
    if runner is None:
        if not exe:
            raise ffdriver.FilterForgeError("Filter Forge is not set up: forge.json has no tools.filter_forge.exe")
        if not exe.exists():
            raise ffdriver.FilterForgeError(f"Filter Forge is not installed where forge.json says: {exe}")
        if os.name != "nt":
            raise ffdriver.FilterForgeError("Filter Forge renders only on Windows — run this on the Windows PC")
    if exe is not None:
        inst = ffdriver.install_dir(exe).resolve()
        if inst == Path(out).resolve() or inst in Path(out).resolve().parents:
            raise ffdriver.FilterForgeError("refusing to write into the Filter Forge install folder")
    return exe


# ------------------------------------------------------------------ naming what came back
def measure(final: np.ndarray, img: np.ndarray) -> dict:
    """What one rendered picture is, by its content alone."""
    a = img[..., :3] if img.shape[2] >= 3 else np.repeat(img, 3, axis=2)
    f = final[..., :3] if final.shape[2] >= 3 else np.repeat(final, 3, axis=2)
    if a.shape != f.shape:
        return {"kind": "other size", "shape": list(a.shape)}
    diff = float(np.abs(a - f).mean())
    mean = a.reshape(-1, 3).mean(axis=0)
    chroma = float((a.max(axis=2) - a.min(axis=2)).mean())
    g = a.mean(axis=2)
    spread = float(g.std())
    v = a * 2.0 - 1.0
    length = np.sqrt((v * v).sum(axis=2))
    unit = float(((length > 0.85) & (length < 1.15) & (v[..., 2] > 0)).mean())      # a normal map's pixels are unit vectors
    rec = {"same_as_final": round(diff, 4), "mean": [round(float(x), 3) for x in mean], "chroma": round(chroma, 4),
           "spread": round(spread, 4), "unit_vectors": round(unit, 3)}
    if diff < 0.004:
        rec["kind"] = "final"
    elif unit > 0.8 and mean[2] > 0.6 and abs(mean[0] - 0.5) < 0.15 and abs(mean[1] - 0.5) < 0.15:
        rec["kind"] = "normal"
    elif chroma < 0.012 and spread < 0.004:
        rec["kind"] = "flat"
        rec["value"] = round(float(g.mean()), 3)
    elif chroma < 0.012:
        rec["kind"] = "grey"
    else:
        rec["kind"] = "colour"
    return rec


def _agrees(normal: np.ndarray, grey_map: np.ndarray) -> float:
    """How well a grey map's slopes agree with a normal map (the red, left-right agreement; 1 = perfectly)."""
    try:
        return float(ffdriver.normal_convention(normal, grey_map)["red_agreement"])
    except Exception:  # noqa: BLE001
        return 0.0


def name_numbers(ftype: str, rows: dict[int, dict], arrays: dict[int, np.ndarray]) -> dict:
    """{verdict: yes | partial | no, numbers: {menu name: number}, evidence, offset} from the measured rows.
    `rows` {number: measure()} (a number that rendered nothing is absent); `arrays` the pictures themselves."""
    menu = MENU.get(ftype)
    kinds = {k: r.get("kind") for k, r in rows.items()}
    others = {k: v for k, v in kinds.items() if k != 0 and v not in ("final", None, "other size")}
    if 0 not in rows:
        return {"verdict": "no", "numbers": {}, "evidence": "number 0 (the final picture) did not render, so nothing can be compared"}
    if not others:
        return {"verdict": "no", "numbers": {}, "evidence": "every number rendered the final picture again (or nothing): "
                "the command-line renderer does not take the channel from map_type in a copy of the filter"}
    normals = [k for k, v in kinds.items() if v == "normal"]
    for k, r in rows.items():
        if r.get("own_name"):                       # Filter Forge named the file itself: the strongest evidence there is
            pass
    agree = {}
    if normals:
        for k, v in kinds.items():
            if v == "grey":
                agree[k] = round(_agrees(arrays[normals[0]], arrays[k]), 3)
    heights = sorted((k for k, a in agree.items() if a >= 0.3), key=lambda k: -agree[k])
    named_by_ff = {r["own_name"]: k for k, r in rows.items() if r.get("own_name")}
    base = {"kinds": {str(k): v for k, v in sorted(kinds.items())}, "height_agreement": {str(k): a for k, a in agree.items()}}
    if menu is None or len(menu) < 2:
        return {"verdict": "partial" if normals else "no", "numbers": {**({"normal": normals[0]} if normals else {})},
                "evidence": f"filter type '{ftype}' has no menu order on file; only what the pictures show is named", **base}
    i_n = menu.index("normal")
    i_h = next(menu.index(n) for n in HEIGHT_NAMES if n in menu)
    i_c = next(menu.index(n) for n in COLOUR_NAMES if n in menu)
    for off in range(0, max(rows) + 1):
        kn, kh, kc = off + i_n, off + i_h, off + i_c
        if kinds.get(kn) != "normal":
            continue
        h_ok = kinds.get(kh) in ("grey", "flat") and (kh in heights or not heights)
        c_ok = kinds.get(kc) in ("colour", "grey", "flat")          # a grey surface has a grey colour map
        if not (h_ok and c_ok):
            continue
        numbers = {"final": 0}
        for i, name in enumerate(menu[1:], start=1):
            k = off + i
            if kinds.get(k) not in (None, "final", "other size"):
                numbers[name] = k
        conflict = [n for n, k in named_by_ff.items() if n in numbers and numbers[n] != k]
        if conflict:
            continue
        sure = kh in heights
        ev = (f"normal map at number {kn} and the height map at {kh}"
              + (f" (its slopes agree with the normal map, {agree.get(kh)})" if sure else " (grey; too flat to test against the normal map)")
              + f", colour at {kc}: the order of Filter Forge's Render Channels menu for a {ftype} filter"
              + (f", shifted by {off}" if off else "") + ". The other grey maps are named by that order.")
        return {"verdict": "yes" if sure else "partial", "numbers": numbers, "offset": off, "evidence": ev, **base}
    numbers = {"final": 0}
    if normals:
        numbers["normal"] = normals[0]
    if heights:
        numbers[next(n for n in HEIGHT_NAMES if n in menu)] = heights[0]
    numbers.update({n: k for n, k in named_by_ff.items() if n in menu})
    return {"verdict": "partial" if len(numbers) > 1 else "no", "numbers": numbers,
            "evidence": "the numbers do not follow the menu's order; only what the pictures themselves show is named "
                        "(normal: blue; height: slopes agree with the normal map)" if len(numbers) > 1 else
                        "channels came back, but none could be told for a normal or a height map", **base}


# ------------------------------------------------------------------ what was learned (local/ff_channels.json)
def store_path(root: Path | None = None) -> Path:
    return Path(root or cfgmod.ROOT) / STORE


def load_store(root: Path | None = None) -> dict:
    try:
        d = json.loads(store_path(root).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def learned(ftype: str, root: Path | None = None) -> dict | None:
    """The proof on file for a filter type, if it says yes or partial."""
    rec = (load_store(root).get("types") or {}).get(ftype)
    return rec if rec and rec.get("verdict") in ("yes", "partial") and rec.get("numbers") else None


def remember(ftype: str, result: dict, filter_file: str, tool: str, root: Path | None = None) -> dict:
    """Add one proof to the store. A later proof that disagrees is kept beside the first and the type is marked."""
    p = store_path(root)
    d = load_store(root)
    d.setdefault("_what", "What the forge learned by rendering: which map_type number in a Filter Forge preset renders which "
                          "channel, per filter type (forge/materials/ffchannels.py, BUILD 87). Delete this file to learn again.")
    types = d.setdefault("types", {})
    rec = types.get(ftype)
    entry = {"filter": filter_file, "verdict": result["verdict"], "numbers": result.get("numbers", {}),
             "when": time.strftime("%Y-%m-%d %H:%M"), "tool": tool}
    if rec is None or rec.get("verdict") == "no" or (rec.get("verdict") == "partial" and result["verdict"] == "yes"):
        types[ftype] = {"how": "map_type in every preset of a working copy", "verdict": result["verdict"],
                        "numbers": result.get("numbers", {}), "evidence": result.get("evidence"),
                        "proofs": (rec or {}).get("proofs", []) + [entry]}
    else:
        rec.setdefault("proofs", []).append(entry)
        if result["verdict"] in ("yes", "partial"):
            clash = {n: (rec["numbers"][n], k) for n, k in result.get("numbers", {}).items()
                     if n in rec["numbers"] and rec["numbers"][n] != k}
            if clash:
                rec["conflict"] = {n: list(v) for n, v in clash.items()}
            else:
                rec["numbers"] = {**result.get("numbers", {}), **rec["numbers"]}
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return types[ftype]


# ------------------------------------------------------------------ the proof
def probe(job: dict, ctx, out: Path, runner=None, numbers: int = 12, size=(256, 256), log_name: str = "render.log") -> dict:
    """Render numbers 0..numbers-1 of one filter small and name them. Returns name_numbers()'s result plus the rows."""
    out = Path(out)
    root = Path(getattr(ctx, "root", None) or cfgmod.ROOT)
    fpath = ffdriver._resolve(root, job["filter"])
    info = ffdriver.read_filter(fpath)
    if info["kind"] == "effect":
        raise ffdriver.FilterForgeError(f"'{info['name']}' is an effect filter (it needs a picture to work on); the proof wants a texture filter")
    preset = int(job.get("preset") or 0)
    copies = write_copies(fpath, out, list(range(int(numbers))))
    slot = str(job.get("slot_name") or "proof")
    got, console, code = _run(job, ctx, out, {f"k{k:02d}": p for k, p in copies.items()}, preset, slot, size, runner,
                              int(job.get("timeout_sec") or 1800), log_name)
    arrays, rows = {}, {}
    for label, rec in got.items():
        k = int(label[1:])
        if rec["file"] is None:
            continue
        arrays[k] = ffdriver.load_png(rec["file"])
    if 0 in arrays:
        for k, a in arrays.items():
            rows[k] = {**measure(arrays[0], a), "file": got[f"k{k:02d}"]["file"].name, "own_name": got[f"k{k:02d}"]["own_name"]}
    res = name_numbers(info["filter_type"], rows, arrays)
    res.update(filter=info["file"], filter_name=info["name"], filter_type=info["filter_type"], preset=preset,
               rows={str(k): r for k, r in sorted(rows.items())}, exit_code=code,
               rendered=len(arrays), asked=int(numbers))
    if not arrays:
        tail = "\n".join((console or "").strip().splitlines()[-8:])
        raise ffdriver.FilterForgeError(f"Filter Forge wrote nothing for the proof (exit {code}). Last lines of its output:\n{tail}")
    res["_arrays"] = arrays
    return res


def proof_sheet(res: dict, cell: int = 192) -> Image.Image:
    """Every number's picture with what it was named — the thing to look at when the verdict is not a plain yes."""
    names = {k: n for n, k in (res.get("numbers") or {}).items()}
    ims, labs = [], []
    for k, a in sorted(res["_arrays"].items()):
        ims.append(look.to_image(a[..., :3] if a.shape[2] >= 3 else a))
        r = res["rows"].get(str(k), {})
        labs.append(f"{k}: {names.get(k, '?' if r.get('kind') != 'final' or k == 0 else 'final again')} [{r.get('kind')}]")
    from ..ops import sheet as sh
    return sh.contact_sheet(ims, labs, cols=min(6, len(ims)), cell=(cell, cell),
                            title=f"{res['filter_name']} ({res['filter_type']}) - channel proof: {res['verdict'].upper()}")


def proof(job: dict, ctx, out: Path, runner=None) -> dict:
    """The ff_channel_proof job handler."""
    from ..jobs.common import save_png, write_prov
    out = Path(out)
    exe = _check_ready(ctx, out, runner)
    try:
        res = probe(job, ctx, out, runner, int(job.get("numbers") or 12), tuple(job.get("size") or (256, 256)))
    except Exception:
        if not job.get("keep_copy"):
            remove_copies(out)
        raise
    save_png(proof_sheet(res), out / "proof.png")
    arrays = res.pop("_arrays")
    vinfo = ffdriver.version_info(exe) if exe and exe.exists() else {}
    tool = ffdriver.tool_key(vinfo) if vinfo else str(job.get("_tool_key") or ffdriver.TOOL_KEY_FALLBACK)
    rec = remember(res["filter_type"], res, res["filter"], tool, Path(getattr(ctx, "root", None) or cfgmod.ROOT))
    (out / "proof.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    removed = 0 if (job.get("keep_copy") or res["verdict"] == "no") else remove_copies(out)
    notes = [res["evidence"]]
    if res["verdict"] == "no":
        notes.append("the working copies are kept in this job's _ffwork folder so the failure can be looked at")
    write_prov(out, job, op="ff_channel_proof", tool=tool, filter=res["filter"], filter_type=res["filter_type"],
               verdict=res["verdict"], numbers=res.get("numbers"), notes=notes, working_copies_removed=removed,
               filter_licence_note="working copies of the filter were written into this job's folder to carry the channel "
                                   "and removed after the render; a filter is never committed or passed on")
    return {"outputs": ["proof.png", "proof.json", "tasks.xml"], "verdict": res["verdict"], "numbers": res.get("numbers"),
            "filter_type": res["filter_type"], "evidence": res["evidence"], "on_file": rec.get("verdict"),
            "rendered": len(arrays), "notes": notes, "tool": tool}


# ------------------------------------------------------------------ one geometry for every channel
def tile_together(chs: dict[str, np.ndarray], lead: str = "final", band: float = 0.12) -> tuple[dict[str, np.ndarray], dict]:
    """Heal the wrap seam of every channel with ONE geometry taken from the lead picture (the roll and the cut path),
    so colour, normal and height stay on each other. (forge.night4.tileable heals each picture by itself, which moves
    each by its own amount — right for one picture, wrong for a set.) Arrays are floats 0..1."""
    from ..night4 import tileable as T
    a = chs[lead][..., :3] * 255.0
    before = ffdriver.seam_score(chs[lead][..., :3])
    dx, dy = T.quiet_shift(a)
    o = np.roll(a, dx, axis=1)
    m1 = T._seam_weight(a, o, dx, band, "cut")
    r = m1[..., None] * a + (1.0 - m1[..., None]) * o
    rs = np.swapaxes(r, 0, 1)
    m2 = T._seam_weight(rs, np.roll(rs, dy, axis=1), dy, band, "cut")
    out = {}
    for name, c in chs.items():
        c3 = c if c.ndim == 3 else c[..., None]
        s1 = m1[..., None] * c3 + (1.0 - m1[..., None]) * np.roll(c3, dx, axis=1)
        t = np.swapaxes(s1, 0, 1)
        s2 = np.swapaxes(m2[..., None] * t + (1.0 - m2[..., None]) * np.roll(t, dy, axis=1), 0, 1)
        if name == "normal":                                   # a blend of two unit vectors is shorter than one
            v = s2[..., :3] * 2.0 - 1.0
            v = v / np.maximum(np.sqrt((v * v).sum(axis=-1, keepdims=True)), 1e-9)
            s2 = np.concatenate([v * 0.5 + 0.5, s2[..., 3:]], axis=-1)
        out[name] = s2 if c.ndim == 3 else s2[..., 0]
    after = ffdriver.seam_score(out[lead][..., :3])
    return out, {"shift": [int(dx), int(dy)], "band": band, "before": before, "after": after, "lead": lead}


def matches(a: np.ndarray, b: np.ndarray) -> dict:
    """Is picture a the same picture as b (so a's channels sit on b)? Mean difference and correlation of brightness."""
    if a.shape[:2] != b.shape[:2]:
        return {"same": False, "why": f"sizes differ ({a.shape[1]}x{a.shape[0]} against {b.shape[1]}x{b.shape[0]})"}
    ga, gb = look.grey(a[..., :3]), look.grey(b[..., :3])
    diff = float(np.abs(a[..., :3] - b[..., :3]).mean())
    da, db = ga - ga.mean(), gb - gb.mean()
    den = float(np.sqrt((da * da).sum() * (db * db).sum()))
    corr = float((da * db).sum() / den) if den > 0 else (1.0 if diff < 0.01 else 0.0)
    return {"same": diff <= 0.02 and corr >= 0.97, "mean_difference": round(diff, 4), "correlation": round(corr, 4)}


def legacy_roughness(strength: np.ndarray | None, exponent: np.ndarray | None) -> tuple[np.ndarray | None, str]:
    """A legacy surface filter has no roughness channel. Its two specular channels say the same thing another way:
    a strong, tight highlight is a smooth surface. roughness = 1 − strength × exponent (both as Filter Forge wrote them)."""
    if strength is None and exponent is None:
        return None, "none"
    s = look.grey(strength) if strength is not None else None
    e = look.grey(exponent) if exponent is not None else None
    if s is not None and e is not None:
        return np.clip(1.0 - s * e, 0.04, 1.0), "worked out: 1 - Specular Strength x Specular Exponent (a legacy filter has no roughness channel)"
    one = s if s is not None else e
    return np.clip(1.0 - 0.6 * one, 0.04, 1.0), ("worked out from Specular " + ("Strength" if s is not None else "Exponent") + " alone")


# ------------------------------------------------------------------ the channel set
def render_set(job: dict, ctx, out: Path, runner=None) -> dict:
    """The ff_channels job handler."""
    from ..jobs.common import save_png, write_prov
    from ..night3b.handoff_jobs import tool_line
    out = Path(out)
    root = Path(getattr(ctx, "root", None) or cfgmod.ROOT)
    exe = _check_ready(ctx, out, runner)
    fpath = ffdriver._resolve(root, job["filter"])
    if fpath.suffix.lower() != ".ffxml":
        raise ValueError(f"`filter` must be an .ffxml file (got {fpath.name})")
    info = ffdriver.read_filter(fpath)
    if info["kind"] == "effect":
        raise ffdriver.FilterForgeError(f"'{info['name']}' is an effect filter — it works on a picture; a channel set is for texture filters")
    ftype = info["filter_type"]
    preset = int(job.get("preset") or 0)
    size = tuple(int(x) for x in (job.get("size") or [1024, 1024]))
    slot = str(job.get("slot_name") or "material")
    notes: list[str] = []
    needs = dict(NEEDS.get(ftype, {}))
    numbers = job.get("map_types")
    proved_here = None
    if needs and not numbers:
        rec = learned(ftype, root)
        if rec is None or rec.get("conflict"):
            notes.append(f"no clean proof on file for {ftype} filters — proving this filter first (small renders)")
            proved_here = probe({**job, "slot_name": slot + "_proof"}, ctx, out, runner, 12, (192, 192), "proof.log")
            proved_here.pop("_arrays", None)
            if proved_here["verdict"] != "no":
                remember(ftype, proved_here, info["file"], "", root)
            numbers = proved_here.get("numbers") or {}
            notes.append("proof: " + proved_here["evidence"])
        else:
            numbers = rec["numbers"]
    numbers = {str(k): int(v) for k, v in (numbers or {}).items()}
    ask = {"final": 0}
    for ch, menu_name in needs.items():
        if menu_name in numbers:
            ask[ch] = numbers[menu_name]
    variation = job.get("variation")
    copies = write_copies(fpath, out, sorted(set(ask.values())), int(variation) if variation is not None else None)
    try:
        got, console, code = _run(job, ctx, out, {ch: copies[k] for ch, k in ask.items()}, preset, slot + "_raw", size, runner,
                                  int(job.get("timeout_sec") or 14400))
    except Exception:
        if not job.get("keep_copy"):
            remove_copies(out)
        raise
    if got.get("final", {}).get("file") is None:
        tail = "\n".join((console or "").strip().splitlines()[-8:])
        raise ffdriver.FilterForgeError(f"Filter Forge wrote no final picture (exit {code}); the working copies are kept in "
                               f"{WORK} to look at. Last lines of its output:\n{tail}")
    arr = {ch: ffdriver.load_png(rec["file"]) for ch, rec in got.items() if rec["file"] is not None}
    how: dict[str, str] = {}
    final = arr["final"]
    # the anchors again, on the real render: a number that gave the final picture or the wrong kind is not used
    for ch in list(arr):
        if ch == "final":
            continue
        m = measure(final, arr[ch])
        if m["kind"] == "final" or (ch == "normal" and m["kind"] != "normal") or m["kind"] == "other size":
            notes.append(f"the {ch} render (number {ask[ch]}) came back as '{m['kind']}', not a {ch} map — not used")
            del arr[ch]
    measured: dict = {"numbers": ask, "filter_type": ftype}
    flip = False
    if "normal" in arr and "height" in arr:
        conv = ffdriver.normal_convention(arr["normal"], arr["height"])
        measured["normal_convention"] = conv
        if conv["verdict"] == "directx":
            flip = True
            notes.append("the normal map came back DirectX-style (green down) — flipped to OpenGL")
        elif conv["verdict"] == "unclear":
            notes.append("the height map's slopes do not clearly agree with the normal map (a very flat surface, or the "
                         "height number is wrong) — look at contact.png before trusting the height")
    sets: dict[str, np.ndarray] = {"final": final[..., :3] if final.shape[2] >= 3 else np.repeat(final, 3, axis=2)}
    if "normal" in arr:
        n = arr["normal"][..., :3].copy()
        if flip:
            n[..., 1] = 1.0 - n[..., 1]
        sets["normal"] = n
        how["normal"] = f"true: Filter Forge's Normal channel (number {ask['normal']})"
    else:
        sets["normal"] = look.guessed_normal(sets["final"])
        how["normal"] = "FALLBACK: guessed from the picture's brightness (no Normal channel came back)"
    if "height" in arr:
        sets["height"] = look.grey(arr["height"])
        how["height"] = f"true: Filter Forge's {'Bump' if ftype == 'legacy surface' else 'Height'} channel (number {ask['height']})"
    if "roughness" in arr:
        sets["roughness"] = look.grey(arr["roughness"])
        how["roughness"] = f"true: Filter Forge's Roughness channel (number {ask['roughness']})"
    elif "specular_strength" in arr or "specular_exponent" in arr:
        r, why = legacy_roughness(arr.get("specular_strength"), arr.get("specular_exponent"))
        sets["roughness"], how["roughness"] = r, why
    if "ambient_occlusion" in arr:
        sets["ambient_occlusion"] = look.grey(arr["ambient_occlusion"])
        how["ambient_occlusion"] = f"true: Filter Forge's {'Ambient Occlusion' if ftype == 'legacy surface' else 'Occlusion'} channel (number {ask['ambient_occlusion']})"
    if "metallic" in arr and float(look.grey(arr["metallic"]).max()) > 0.02:
        sets["metallic"] = look.grey(arr["metallic"])
        how["metallic"] = f"true: Filter Forge's Metallic channel (number {ask['metallic']})"
    for ch in job.get("want") or []:
        how.setdefault(ch, "MISSING: Filter Forge gave no such channel for this filter"
                       + (" (a simple filter renders only the final picture)" if ftype == "simple" else ""))
    if job.get("tileable"):
        sets, tinfo = tile_together(sets, "final", float(job.get("tile_band") or 0.12))
        measured["tiled_together"] = tinfo
    measured["seam"] = ffdriver.seam_score(sets["final"])
    files = {"final": f"{slot}.png"}
    look.save(sets["final"], out / files["final"])
    for ch, end, bits in (("normal", "_n", 8), ("height", "_height", 16), ("roughness", "_rough", 8),
                          ("ambient_occlusion", "_ao", 8), ("metallic", "_metal", 8)):
        if ch in sets:
            files[ch] = f"{slot}{end}.png"
            look.save(sets[ch], out / files[ch], bits)
    # before and after, under the same lamp
    after = {"colour": sets["final"], "normal": sets["normal"], "height": sets.get("height", np.full(sets["final"].shape[:2], 0.5)),
             "roughness": sets.get("roughness", np.full(sets["final"].shape[:2], 0.85)),
             "ambient_occlusion": sets.get("ambient_occlusion", np.ones(sets["final"].shape[:2])),
             "metallic": sets.get("metallic", np.zeros(sets["final"].shape[:2])),
             "how": {k: v.split(":")[0] for k, v in how.items()}}
    flat = np.ones(sets["final"].shape[:2])
    before = {"colour": sets["final"], "normal": look.guessed_normal(sets["final"]), "height": flat * 0.5, "roughness": flat * 0.85,
              "ambient_occlusion": flat, "metallic": flat * 0.0, "how": {}}
    name = str(job.get("name") or info["name"])
    save_png(look.moving_light(before, after, name, labels=("before: normal guessed from brightness, no roughness",
                                                             "after: Filter Forge's own channels")), out / "moving_light.png")
    save_png(look.stamp(look.material_row(after, f"{name} - {info['name']} ({ftype})")), out / "contact.png")
    # beside an existing picture
    delivered = deliver_beside(job, root, sets, how, notes) if job.get("beside") else None
    removed = 0 if job.get("keep_copy") else remove_copies(out)
    vinfo = ffdriver.version_info(exe) if exe and exe.exists() else {}
    tool = ffdriver.tool_key(vinfo) if vinfo else str(job.get("_tool_key") or ffdriver.TOOL_KEY_FALLBACK)
    lic = [tool_line(ctx, tool)]
    ok = all(r.get("commercial_ok") is True for r in lic)
    report = {"filter": info["file"], "filter_name": info["name"], "filter_type": ftype, "preset": preset,
              "variation": variation, "size": list(size), "channels": how, "files": files, "measured": measured,
              "delivered": delivered, "notes": notes}
    (out / "channels.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    write_prov(out, job, op="ff_channels", tool=tool, filter_forge_version=vinfo.get("FileVersion"), filter=info["file"],
               filter_path=info["path"], filter_name=info["name"], filter_library_id=info["library_id"], filter_type=ftype,
               preset=preset, variation=variation, channels=how, numbers=ask, measured=measured, licences=lic,
               commercial_ok=ok, notes=notes, working_copies_removed=removed,
               filter_licence_note="working copies of the filter were written into this job's folder to carry each channel "
                                   "and removed after the render; a filter is never committed or passed on. Rendered results: "
                                   "commercial use per William")
    true = sorted(ch for ch, h in how.items() if h.startswith("true"))
    return {"outputs": list(files.values()) + ["channels.json", "contact.png", "moving_light.png", "tasks.xml"],
            "channels": how, "true_channels": true, "measured": measured, "notes": notes, "delivered": delivered,
            "commercial_ok": ok, "tool": tool, "exit_code": code}


BESIDE = (("normal", "_ffnormal", 8), ("height", "_height", 16), ("roughness", "_rough", 8), ("ambient_occlusion", "_ao", 8),
          ("metallic", "_metal", 8))


def deliver_beside(job: dict, root: Path, sets: dict, how: dict, notes: list[str]) -> dict:
    """Put the true channels beside an existing picture — only when this render IS that picture, only under names that
    are not there yet. Returns what was written and what was left alone, with the reason."""
    folder = ffdriver._resolve(root, job["beside"])
    stem = str(job.get("beside_stem") or job.get("slot_name") or "material")
    rep: dict = {"folder": str(folder), "stem": stem, "written": [], "left": []}
    target = ffdriver._resolve(root, job["match"]) if job.get("match") else folder / f"{stem}.png"
    if not target.is_file():
        rep["refused"] = f"there is no picture {target.name} to sit beside"
        notes.append("not delivered: " + rep["refused"])
        return rep
    m = matches(sets["final"], look.load(target)[..., :3])
    rep["match"] = m
    if not m["same"]:
        rep["refused"] = (f"this render is not the picture already there ({target.name}: " +
                          (m.get("why") or f"mean difference {m['mean_difference']}, correlation {m['correlation']}") +
                          ") — its channels would not sit on it, so nothing was written beside it")
        notes.append("not delivered: " + rep["refused"])
        return rep
    for ch, end, bits in BESIDE:
        if ch not in sets or not how.get(ch, "").startswith(("true", "worked out")):
            continue
        dest = folder / f"{stem}{end}.png"
        if dest.exists():
            rep["left"].append({"file": dest.name, "why": "already there (never written over)"})
            continue
        look.save(sets[ch], dest, bits)
        rep["written"].append(dest.name)
    side = folder / f"{stem}_channels.json"
    if rep["written"] and not side.exists():
        side.write_text(json.dumps({"_what": "Where this picture's channel files came from (forge/materials/ffchannels.py, BUILD 87).",
                                    "from_job": job.get("id"), "channels": how, "match": m}, indent=1, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        rep["written"].append(side.name)
    return rep


# ------------------------------------------------------------------ plans (which jobs to queue)
def job_for_picture(root: Path, picture: Path, source_job_dir: Path, batch: str, size: int | None = None) -> dict | None:
    """The ff_channels job that would give `picture` its channels, read from the job that rendered it. None with no
    Filter Forge job behind it."""
    try:
        j = json.loads((Path(source_job_dir) / "job.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if j.get("type") != "filter_forge" or not j.get("filter"):
        return None
    ch = j.get("channels")
    preset = int(ch.get("final", j.get("preset") or 0)) if isinstance(ch, dict) else int(j.get("preset") or 0)
    picture = Path(picture)
    tile = picture.stem.endswith("_tile")          # the healed picture is in use: heal this set the same way
    base_timeout = int(j.get("timeout_sec") or 900)
    return {"type": "ff_channels", "name": f"channels_{picture.stem}"[:60], "batch": batch, "filter": j["filter"],
            "preset": preset, "size": [size, size] if size else list(j.get("size") or [1024, 1024]),
            "seamless": bool(j.get("seamless", True)), "tileable": bool(tile), "slot_name": picture.stem,
            "beside": str(picture.parent), "beside_stem": picture.stem, "match": str(picture),
            "timeout_sec": max(14400, base_timeout * 8), "priority": 1,
            "meta": {"suite": "materials", "category": "channels", "prompt_id": picture.stem, "from_job": j.get("id"),
                     "checkpoint": f"filter_forge:{Path(str(j['filter'])).stem}", "lora": None, "seed": 0}}


def has_true_set(picture: Path) -> bool:
    return Path(picture).with_name(Path(picture).stem + "_ffnormal.png").is_file()


def library_plan(root: Path, folder: Path, batch: str = "materials/ff_channels") -> dict:
    """For a library folder with a _sources.json ({name: {"from": "out/<job>/<file>"}}): the jobs to queue, and the
    pictures that have no Filter Forge job behind them (they keep the brightness guess, and the report says so)."""
    folder = Path(folder)
    try:
        src = json.loads((folder / "_sources.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        src = {}
    jobs, done, no_source = [], [], []
    from ..threed import relief
    for pic in relief.wanted(folder):
        if pic.stem.endswith(look.ALL_ENDINGS):
            continue
        if has_true_set(pic):
            done.append(pic.name)
            continue
        frm = (src.get(pic.stem) or {}).get("from")
        job = job_for_picture(root, pic, ffdriver._resolve(root, frm).parent, batch, Image.open(pic).size[0]) if frm else None
        if job is None:
            no_source.append({"picture": pic.name, "why": "no Filter Forge job behind it" + (f" (made by {frm.split('/')[1][:40]}…)" if frm else " (not in _sources.json)")})
        else:
            jobs.append(job)
    return {"jobs": jobs, "already": done, "no_filter": no_source}


def picks_plan(root: Path, cull_file: Path, batch: str = "materials/ff_picks_channels", only_tiles: bool = False) -> dict:
    """For a cull file ({"picks": [{"verdict": "keep", "render_dir": "out/<job>", "use": "texture_final.png", …}]}):
    one ff_channels job a kept pick, its set delivered beside the picture in use."""
    d = json.loads(Path(cull_file).read_text(encoding="utf-8"))
    jobs, done, skipped = [], [], []
    for r in d.get("picks", []):
        if r.get("verdict") != "keep" or not r.get("render_dir"):
            continue
        if only_tiles and r.get("kind") != "tile":
            continue
        rd = ffdriver._resolve(root, r["render_dir"])
        pic = rd / str(r.get("use") or "texture_final.png")
        if not pic.is_file():
            skipped.append({"id": r.get("id"), "why": f"{pic.name} is not in {r['render_dir']}"})
            continue
        if has_true_set(pic):
            done.append(str(r.get("id")))
            continue
        job = job_for_picture(root, pic, rd, batch)
        if job is None:
            skipped.append({"id": r.get("id"), "why": "its job.json could not be read"})
            continue
        job["name"] = f"channels_pick_{r.get('id')}"
        job["meta"]["prompt_id"] = f"{r.get('picked_under', '')}: {r.get('name', '')}"[:90]
        jobs.append(job)
    return {"jobs": jobs, "already": done, "skipped": skipped}
