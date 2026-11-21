"""Material Maker, driven (BUILD 87, Part 2): a graph (.ptex) → a seamless material set, with a seed and named parameters.

How it exports from the command line was read from the installed program itself (Material Maker 1.8, the script
parse_args inside material_maker.exe, 2026-11-19 — its shipped doc page is older than its code):

    material_maker.exe --export-material -t "<target>" -o <folder> --size <pixels> --output-file <name> <file.ptex>

  * the FIRST argument is skipped by its parser, so it must be the --export-material word itself;
  * -t / --target: an export profile of the Material node (default "Godot/Godot 4 Standard"; a near miss is matched to
    the closest and it prints "Using target …"); "Godot/Godot 4 ORM" writes <name>_albedo.png, <name>_orm.png (red =
    occlusion, green = roughness, blue = metal), <name>_normal.png, <name>_heightmap.png, <name>_emission.png — each
    only when that input of the Material node is connected — and a <name>.tres it leaves alone if one is there;
  * -o / --output-dir (made if missing), --size in pixels (default 2048), --output-file (default %f, the file's name);
  * it prints "Exporting Material <file> to <prefix>...", then "Done", and quits. On a mistake it prints and does NOT
    quit, so the forge gives it a time limit and stops it.
It opens a small window while it works: it draws on the graphics card, so the forge holds its card lock around every
export and the 3D queue gets the card back between two materials.

Seeds: every random node's own seed has its parent graph's seed added (the program's gen_base.get_seed), so setting
the top graph's `seed` moves the whole surface together — that is this job's `seed`.

Named parameters are the forge's, not Material Maker's remotes: a graph's side file <graph>.json says which node
parameter each name moves and between which two values, and `patch` writes them into a copy before the export. One
graph, two settings ("broken", "mended") = the same wall in two states.

The program is used from where it is installed and its data folders are pointed at local/material_maker_data (as
material_maker.bat does), so nothing is written to a user folder. Material Maker is MIT-licensed free software.
"""
from __future__ import annotations

import copy
import json
import math
import os
import subprocess
import time
from pathlib import Path

import numpy as np

from .. import config as cfgmod
from . import look

GRAPHS = Path(__file__).resolve().parent / "graphs"
TARGET = "Godot/Godot 4 ORM"
EXPORTS = {"colour": "_albedo", "orm": "_orm", "normal": "_normal", "height": "_heightmap", "emission": "_emission"}
MATERIAL_PORTS = ("albedo", "metallic", "roughness", "emission", "normal", "ao", "depth", "opacity", "sss")
BUILTIN = {"graph", "remote", "ios", "comment", "comment_line", "buffer", "iterate_buffer", "switch", "image", "text",
           "export", "debug", "reroute", "variations", "meshmap", "shader", "sdf", "webcam", "portal"}
LICENCE = {"role": "outside_tool", "file": "Material Maker", "model": "Material Maker",
           "license": "MIT (Material Maker, Rodolphe Suescun and contributors) - what it exports is the maker's own; "
                      "the graph is the forge's own", "commercial_ok": True}


class MaterialMakerError(Exception):
    pass


# ------------------------------------------------------------------ where it is
def exe_path(cfg: dict | None = None, root: Path | None = None) -> Path:
    root = Path(root or cfgmod.ROOT)
    raw = (((cfg or {}).get("tools") or {}).get("material_maker") or {}).get("exe")
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else root / p
    base = root / "engines" / "material_maker"
    for name in ("material_maker.exe", "material_maker.x86_64", "material_maker"):
        if (base / name).is_file():
            return base / name
    return base / ("material_maker.exe" if os.name == "nt" else "material_maker.x86_64")


def data_env(root: Path | None = None) -> dict:
    """The environment that keeps Material Maker's settings and cache beside the forge (as material_maker.bat does)."""
    root = Path(root or cfgmod.ROOT)
    data = root / "local" / "material_maker_data"
    (data / "cache").mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update(APPDATA=str(data), LOCALAPPDATA=str(data / "cache"), XDG_DATA_HOME=str(data), XDG_CONFIG_HOME=str(data),
               XDG_CACHE_HOME=str(data / "cache"))
    return env


def command(exe: Path, ptex: Path, out_dir: Path, name: str, size: int = 2048, target: str = TARGET) -> list[str]:
    """The command line, in the order the program's parser needs (the export word first; see the module's notes)."""
    return [str(exe), "--export-material", "-t", str(target), "-o", Path(out_dir).as_posix(), "--size", str(int(size)),
            "--output-file", str(name), Path(ptex).as_posix()]


def run_exporter(cmd: list[str], env: dict, cwd: Path, timeout: int) -> tuple[int | None, str]:
    """Run Material Maker and wait. It does not quit by itself after a mistake, so on the time limit it is stopped and
    the exit code is None. Returns (exit code or None, what it printed)."""
    p = subprocess.Popen(cmd, cwd=str(cwd), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    try:
        out, _ = p.communicate(timeout=int(timeout))
        return p.returncode, out or ""
    except subprocess.TimeoutExpired:
        p.kill()
        try:
            out, _ = p.communicate(timeout=20)
        except Exception:  # noqa: BLE001
            out = ""
        return None, (out or "") + f"\n[the forge stopped Material Maker after {int(timeout)} s]"


# ------------------------------------------------------------------ the node library, and a check against it
def node_library(install: Path) -> dict[str, dict]:
    """{node type: {"params": {name: def}, "inputs": n, "outputs": n, "variadic": bool}} from <install>/nodes/*.mmg."""
    lib: dict[str, dict] = {}
    nodes = Path(install) / "nodes"
    if not nodes.is_dir():
        return lib
    for f in sorted(nodes.glob("*.mmg")):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        sm = j.get("shader_model")
        if isinstance(sm, dict):
            ins, outs = sm.get("inputs") or [], sm.get("outputs") or []
            lib[f.stem] = {"params": {p.get("name"): p for p in sm.get("parameters") or []}, "inputs": len(ins), "outputs": len(outs),
                           "variadic": any("#" in str(i.get("name", "")) for i in ins) or any("#" in str(p.get("name", "")) for p in sm.get("parameters") or [])}
        else:
            ports = {n.get("name"): n.get("ports") or [] for n in j.get("nodes") or [] if n.get("type") == "ios"}
            params: dict = {}
            for n in j.get("nodes") or []:
                if n.get("type") == "remote":
                    for w in n.get("widgets") or []:
                        params[w.get("name")] = {"name": w.get("name"), "type": "remote"}
            for k in (j.get("parameters") or {}):
                params.setdefault(k, {"name": k, "type": "remote"})
            lib[f.stem] = {"params": params, "inputs": len(ports.get("gen_inputs", [])), "outputs": len(ports.get("gen_outputs", [])),
                           "variadic": False}
    return lib


def lint(graph: dict, lib: dict[str, dict], want: tuple[str, ...] = ("albedo", "roughness", "normal", "ao", "depth")) -> list[str]:
    """Problems in a graph, found before Material Maker is started: node types and parameter names that are not in the
    installed library, numbers outside a parameter's range, connections to ports that are not there, loops, and a
    Material node whose wanted inputs are not connected. An empty list = nothing found. A line that starts "note:"
    is something Material Maker itself lets pass (an old parameter name in a graph saved by an older version, a number
    past a slider's end): it is reported, and does not stop the export."""
    probs: list[str] = []
    nodes = {n.get("name"): n for n in graph.get("nodes") or []}
    if len(nodes) != len(graph.get("nodes") or []):
        probs.append("two nodes share a name")
    mats = [n for n in nodes.values() if n.get("type") == "material"]
    if len(mats) != 1:
        probs.append(f"a material graph needs exactly one Material node (found {len(mats)})")
    for name, n in nodes.items():
        t = n.get("type")
        d = lib.get(t)
        if d is None:
            if t not in BUILTIN:
                probs.append(f"node '{name}': type '{t}' is not in the installed node library")
            continue
        for p, v in (n.get("parameters") or {}).items():
            pd = d["params"].get(p)
            if pd is None:
                if not d["variadic"]:
                    probs.append(f"note: node '{name}' ({t}): no parameter '{p}' in this version (it has: {', '.join(sorted(k for k in d['params'] if k))})")
                continue
            if pd.get("type") == "float" and isinstance(v, (int, float)) and not isinstance(v, bool):
                lo, hi = pd.get("min"), pd.get("max")
                if lo is not None and hi is not None and not (float(lo) - 1e-9 <= float(v) <= float(hi) + 1e-9):
                    probs.append(f"note: node '{name}' ({t}): {p} = {v} is outside {lo}..{hi}")
            if pd.get("type") == "enum" and isinstance(v, int) and not (0 <= v < len(pd.get("values") or [0])):
                probs.append(f"node '{name}' ({t}): {p} = {v} is not one of its {len(pd.get('values') or [])} choices")
    into: dict[tuple, str] = {}
    edges: dict[str, set] = {k: set() for k in nodes}
    for c in graph.get("connections") or []:
        a, b = c.get("from"), c.get("to")
        if a not in nodes or b not in nodes:
            probs.append(f"connection {a} -> {b}: no such node")
            continue
        da, db = lib.get(nodes[a].get("type")), lib.get(nodes[b].get("type"))
        if da and not da["variadic"] and int(c.get("from_port", 0)) >= max(1, da["outputs"]):
            probs.append(f"connection {a}:{c.get('from_port')} -> {b}: '{nodes[a].get('type')}' has only {da['outputs']} output(s)")
        if db and not db["variadic"] and int(c.get("to_port", 0)) >= max(1, db["inputs"]):
            probs.append(f"connection {a} -> {b}:{c.get('to_port')}: '{nodes[b].get('type')}' has only {db['inputs']} input(s)")
        key = (b, int(c.get("to_port", 0)))
        if key in into:
            probs.append(f"input {b}:{key[1]} is fed twice ({into[key]} and {a})")
        into[key] = a
        edges[a].add(b)
    state: dict[str, int] = {}

    def walk(k: str) -> bool:
        state[k] = 1
        for nx in edges.get(k, ()):
            if state.get(nx) == 1 or (state.get(nx) is None and walk(nx)):
                return True
        state[k] = 2
        return False
    if any(state.get(k) is None and walk(k) for k in list(nodes)):
        probs.append("the connections make a loop")
    if len(mats) == 1:
        fed = {port for (b, port) in into if b == mats[0].get("name")}
        for w in want:
            if MATERIAL_PORTS.index(w) not in fed:
                probs.append(f"the Material node's {w} input is not connected, so that channel would not be exported")
    return probs


# ------------------------------------------------------------------ graphs, side files, patching
def find_graph(ref: str, root: Path | None = None) -> Path:
    root = Path(root or cfgmod.ROOT)
    p = Path(str(ref))
    for cand in (p, root / p, GRAPHS / (p.name if p.suffix else p.name + ".ptex")):
        if cand.is_file() and cand.suffix.lower() == ".ptex":
            return cand
    have = ", ".join(sorted(f.stem for f in GRAPHS.glob("*.ptex")))
    raise FileNotFoundError(f"graph '{ref}' not found (a .ptex path, or one of the forge's own: {have})")


def side_file(ptex: Path) -> dict:
    """<graph>.json beside a graph: its named parameters and settings. A graph without one has none."""
    try:
        d = json.loads(Path(ptex).with_suffix(".json").read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def values_for(side: dict, setting: str | None, given: dict | None) -> dict[str, float]:
    """Every named parameter's value: the side file's default, then the chosen setting, then what the job gave."""
    params = side.get("parameters") or {}
    vals = {k: float(v.get("default", 0.0)) for k, v in params.items()}
    if setting:
        st = (side.get("settings") or {}).get(setting)
        if st is None:
            raise ValueError(f"no setting '{setting}' (this graph has: {', '.join(sorted(side.get('settings') or {})) or 'none'})")
        vals.update({k: float(v) for k, v in st.items() if k in params})
    for k, v in (given or {}).items():
        if k not in params:
            raise ValueError(f"no named parameter '{k}' (this graph has: {', '.join(sorted(params)) or 'none'})")
        vals[k] = float(v)
    for k, v in vals.items():
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"named parameter '{k}' = {v}: a named parameter runs from 0 to 1")
    return vals


def patch(graph: dict, side: dict, values: dict[str, float], seed: float = 0.0, size: int | None = None) -> tuple[dict, list[dict]]:
    """A copy of the graph with the named parameters written into the node parameters they move, the top graph's seed
    set, and the Material node's size. Returns (graph, what was set)."""
    g = copy.deepcopy(graph)
    nodes = {n.get("name"): n for n in g.get("nodes") or []}
    done = []
    for name, v in values.items():
        for s in (side.get("parameters") or {}).get(name, {}).get("sets") or []:
            n = nodes.get(s.get("node"))
            if n is None:
                raise ValueError(f"named parameter '{name}' moves node '{s.get('node')}', which the graph does not have")
            a, b = s["to"]
            val = float(a) + (float(b) - float(a)) * float(v)
            if "point" in s:                                     # a gradient stop: {"param": "gradient", "point": 1, "key": "pos"}
                pts = n["parameters"][s.get("param", "gradient")]["points"]
                pts[int(s["point"])][s.get("key", "pos")] = round(val, 6)
            else:
                n.setdefault("parameters", {})[s["param"]] = round(val, 6)
            done.append({"parameter": name, "value": v, "node": s["node"], "sets": s.get("param", "gradient") + (f"[{s['point']}].{s.get('key', 'pos')}" if "point" in s else ""), "to": round(val, 6)})
    g.pop("seed_int", None)
    g.pop("seed_value", None)
    g["seed"] = float(seed)
    if size:
        for n in nodes.values():
            if n.get("type") == "material":
                n.setdefault("parameters", {})["size"] = int(round(math.log2(int(size))))
    return g, done


# ------------------------------------------------------------------ collecting what it wrote
def collect(out: Path, name: str) -> dict[str, Path]:
    out = Path(out)
    return {ch: out / f"{name}{end}.png" for ch, end in EXPORTS.items() if (out / f"{name}{end}.png").is_file()}


def split_orm(orm: np.ndarray) -> dict[str, np.ndarray]:
    return {"ambient_occlusion": orm[..., 0], "roughness": orm[..., 1], "metallic": orm[..., 2]}


def render(job: dict, ctx, out: Path, runner=None) -> dict:
    """The mm_material job handler."""
    from ..jobs.common import save_png, write_prov
    from ..night3b import ffdriver
    out = Path(out)
    cfg = getattr(ctx, "cfg", None)
    root = Path(getattr(ctx, "root", None) or cfgmod.ROOT)
    exe = exe_path(cfg, root)
    if runner is None and not exe.is_file():
        raise MaterialMakerError(f"Material Maker is not installed where the forge looks: {exe} "
                                 "(put it in engines\\material_maker, or set tools.material_maker.exe in forge.json)")
    ptex = find_graph(str(job["graph"]), root)
    side = side_file(ptex)
    try:
        graph = json.loads(ptex.read_text(encoding="utf-8"))
    except ValueError as e:
        raise MaterialMakerError(f"{ptex.name} is not a readable graph ({e})")
    notes: list[str] = []
    lib = node_library(exe.parent)
    want = tuple(side.get("needs") or ("albedo", "roughness", "normal", "ao", "depth"))
    if lib:
        found = lint(graph, lib, want)
        probs = [x for x in found if not x.startswith("note:")]
        notes += [x for x in found if x.startswith("note:")][:12]
        if probs:
            raise MaterialMakerError(f"{ptex.name} does not fit the installed Material Maker ({len(probs)} problem(s)): " + "; ".join(probs[:8]))
    else:
        notes.append("the graph could not be checked against the node library (no nodes folder beside the program)")
    size = int(job.get("size") or 2048)
    if size < 64 or size > 8192 or size & (size - 1):
        raise ValueError(f"size {size}: a power of two from 64 to 8192")
    values = values_for(side, job.get("setting"), job.get("parameters"))
    seed = float(job.get("seed") or 0.0)
    patched, sets = patch(graph, side, values, seed, size)
    slot = str(job.get("slot_name") or (ptex.stem + (f"_{job['setting']}" if job.get("setting") else "")))
    work = out / f"{slot}.ptex"
    work.write_text(json.dumps(patched, indent="\t") + "\n", encoding="utf-8")
    cmd = command(exe, work, out, slot + "_mm", size, str(job.get("target") or TARGET))
    (out / "command.txt").write_text(subprocess.list2cmdline(cmd) + "\n", encoding="utf-8")
    t0 = time.time()
    lock = None
    waited = 0.0
    if runner is None and job.get("use_card_lock", True):
        from ..threed.cardlock import CardLock
        lock = CardLock(cfg, f"material maker {slot}", wait_minutes=float(job.get("wait_card_minutes") or 720), side="art").acquire()
        waited = lock.waited
    try:
        code, console = (runner or run_exporter)(cmd, data_env(root), out, int(job.get("timeout_sec") or 900))
    finally:
        if lock is not None:
            lock.release()
    (out / "material_maker.log").write_text(console or "", encoding="utf-8", newline="\n")
    got = collect(out, slot + "_mm")
    if "colour" not in got:
        tail = "\n".join((console or "").strip().splitlines()[-10:])
        why = ("it did not finish in time and was stopped" if code is None else f"it ended with code {code}")
        raise MaterialMakerError(f"Material Maker exported no colour picture ({why}). The command is in command.txt, the "
                                 f"graph it was given is {work.name}. What it printed last:\n{tail or '(nothing reached the forge)'}")
    arr: dict[str, np.ndarray] = {"colour": look.load(got["colour"])[..., :3]}
    how = {"colour": "Material Maker (albedo)"}
    if "orm" in got:
        for ch, a in split_orm(look.load(got["orm"])).items():
            arr[ch] = a
            how[ch] = "Material Maker (" + {"ambient_occlusion": "red", "roughness": "green", "metallic": "blue"}[ch] + " of its ORM picture)"
    if "height" in got:
        arr["height"] = look.grey(look.load(got["height"]))
        how["height"] = "Material Maker (heightmap: white = high)"
    measured: dict = {"seconds": round(time.time() - t0, 1), "waited_for_card": round(waited, 1)}
    if "normal" in got:
        n = look.load(got["normal"])[..., :3].copy()
        if "height" in arr and float(arr["height"].std()) > 1e-4:
            conv = ffdriver.normal_convention(n, arr["height"][..., None])
            measured["normal_convention"] = conv
            if conv["verdict"] == "directx":
                n[..., 1] = 1.0 - n[..., 1]
                notes.append("the normal map came back green-down — flipped to OpenGL")
            elif conv["verdict"] == "unclear" and conv["red_agreement"] < -0.2:
                notes.append("the height map runs against the normal map (white looks LOW): check the graph's depth input")
        arr["normal"] = n
        how["normal"] = "Material Maker (normal)"
    if "emission" in got:
        arr["emission"] = look.load(got["emission"])[..., :3]
        how["emission"] = "Material Maker (emission)"
    for w, ch in (("roughness", "roughness"), ("normal", "normal"), ("ao", "ambient_occlusion"), ("depth", "height")):
        if w in want and ch not in arr:
            notes.append(f"no {ch} came back although the graph's side file asks for it")
    measured["seam"] = ffdriver.seam_score(arr["colour"])
    if max(measured["seam"].values()) > 1.5:
        notes.append(f"the colour picture shows a wrap seam (x {measured['seam']['x']}, y {measured['seam']['y']}; about 1 is seamless) — "
                     "a node in the graph does not tile")
    files = {"colour": f"{slot}.png"}
    look.save(arr["colour"], out / files["colour"])
    for ch, end, bits in (("normal", "_n", 8), ("height", "_height", 16), ("roughness", "_rough", 8), ("ambient_occlusion", "_ao", 8),
                          ("metallic", "_metal", 8), ("emission", "_emission", 8)):
        if ch in arr and not (ch == "metallic" and float(arr[ch].max()) <= 0.02):
            files[ch] = f"{slot}{end}.png"
            look.save(arr[ch], out / files[ch], bits)
    m = look.load_set(out / files["colour"], guess=True)
    label = str(side.get("label") or ptex.stem) + (f" - {job['setting']}" if job.get("setting") else "")
    save_png(look.stamp(look.material_row(m, label, note=f"Material Maker, seed {seed:g}, {size} px")), out / "contact.png")
    save_png(look.moving_light(None, m, label, labels=("", "under a lamp carried across it")), out / "moving_light.png")
    vinfo = ffdriver.version_info(exe) if exe.is_file() else {}
    tool = ("Material Maker " + str(vinfo.get("ProductVersion") or "")).strip()
    lic = [{**LICENCE, "file": tool, "model": tool}]
    report = {"graph": ptex.name, "setting": job.get("setting"), "values": values, "set": sets, "seed": seed, "size": size,
              "channels": how, "files": files, "measured": measured, "notes": notes}
    (out / "channels.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    write_prov(out, job, op="mm_material", tool=tool, graph=ptex.name, graph_path=str(ptex), setting=job.get("setting"),
               values=values, seed=seed, size=size, target=str(job.get("target") or TARGET), channels=how, measured=measured,
               licences=lic, commercial_ok=True, notes=notes)
    return {"outputs": list(files.values()) + [work.name, "channels.json", "contact.png", "moving_light.png"], "channels": how,
            "values": values, "seed": seed, "measured": measured, "notes": notes, "commercial_ok": True, "tool": tool,
            "exit_code": code}
