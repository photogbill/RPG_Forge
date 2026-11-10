"""A hand-off folder for an outside tool (Night 3B, G13).

Some good tools have no command line but can batch-process a whole folder (an AI upscaler, a photo editor). This
lets one of them be an optional manual stop in the forge without the forge depending on it:

    python -m forge handoff out <batch | job ids …> --to out/handoff/<name>/in      (handoff_out.bat)
        copies each job's raw render into the folder under a name that starts with the job id, writes README.txt
        (what size to produce, where to save) and handoff.json (which file came from which job)
    … the person runs the tool on out/handoff/<name>/in and saves the results into out/handoff/<name>/done …
    python -m forge handoff in <name> [--tool "<name version>"] [--priority 10] [--no-submit]   (handoff_in.bat)
        matches the returned files to their jobs by the job id at the start of each name (a tool may add its own tag
        after it), checks the sizes, and files each as that job's upscaled picture: one small job per file —
        `handoff_kit` (the kit's depth / normals / glow / layers rebuilt from it) for a scene kit, `handoff_file`
        otherwise. Missing, extra and wrong-size files are reported by name.
    python -m forge handoff tool add ["<name>" "<version>" yes|no "<condition>" "<where checked>"]
    python -m forge handoff tool list
        the tool register: one licence line per tool, typed once by the person. It lives in models/licences.json
        beside the model licences, so `approve` checks a tool exactly like a model; a tool with no entry is
        "licence not on file" and `approve` asks first.

Generic on purpose: nothing in this file names a product.
"""
from __future__ import annotations
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image

from . import config as cfgmod

TOOL_KIND = "outside tool"
RETURN_EXTS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp")
SEP = "__"                     # <job id>__<what it was>.png — the job id is the part before the first "__"
ASPECT_TOLERANCE = 0.01


class HandoffError(Exception):
    pass


# ------------------------------------------------------------------ the tool register
def register_path(root: Path | None = None) -> Path:
    return Path(root or cfgmod.ROOT) / "models" / "licences.json"


def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except ValueError as e:
        raise HandoffError(f"{p} is not valid JSON ({e}) — fix it by hand before recording another licence")


def _write_json_atomic(p: Path, data: dict) -> None:
    """Write then rename: a worker reading the file at the same moment sees the old or the new file, never half."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    os.replace(tmp, p)


def tool_key(name: str, version: str) -> str:
    name, version = str(name).strip(), str(version).strip()
    if not name:
        raise HandoffError("a tool needs a name")
    if any(c in name + version for c in "/\\:*?\"<>|"):
        raise HandoffError(f"keep / \\ : * ? \" < > | out of the tool's name and version: {name!r} {version!r}")
    return f"{name} {version}".strip()


def load_tools(root: Path | None = None) -> dict[str, dict]:
    return {k: v for k, v in _read_json(register_path(root)).items() if isinstance(v, dict) and v.get("kind") == TOOL_KIND}


def add_tool(name: str, version: str, commercial_ok: bool, condition: str = "", where: str = "",
             licence: str = "", root: Path | None = None) -> str:
    key = tool_key(name, version)
    p = register_path(root)
    data = _read_json(p)
    old = data.get(key)
    if old and old.get("kind") != TOOL_KIND:
        raise HandoffError(f"'{key}' is already in {p.name} as a model licence, not a tool — use another name")
    data[key] = {"kind": TOOL_KIND, "tool": name.strip(), "version": str(version).strip(),
                 "license": licence.strip() or ("outside tool — commercial use " + ("permitted" if commercial_ok else "NOT permitted")
                                                + (f" ({condition.strip()})" if condition.strip() else "")),
                 "commercial_ok": bool(commercial_ok),
                 "licence_condition": condition.strip() or None,
                 "checked": f"{datetime.now():%Y-%m-%d}" + (f" — {where.strip()}" if where.strip() else "")}
    _write_json_atomic(p, data)
    return key


def ask_tool(ask=input, out=print, root: Path | None = None, name: str | None = None,
             version: str | None = None) -> str | None:
    """The questions one at a time (handoff_tool_add.bat with no arguments). Returns the key, or None if stopped."""
    out("Record the licence of an outside tool (a program the forge hands pictures to). The forge never guesses one.")
    out("Press Enter on an empty answer to stop.\n")
    name = name or ask("Tool name (as the program calls itself): ").strip()
    if not name:
        return None
    version = version if version is not None else ask("Version (Help > About): ").strip()
    yn = ask("May its results be used commercially? yes / no: ").strip().lower()
    if yn not in ("yes", "no", "y", "n"):
        out("Answer yes or no — nothing recorded."); return None
    cond = ask("Any condition on that (e.g. a revenue cap) — Enter for none: ").strip()
    where = ask("Where you checked it (page, date): ").strip()
    key = add_tool(name, version, yn.startswith("y"), cond, where, root=root)
    out(f"recorded '{key}' in {register_path(root)}")
    return key


# ------------------------------------------------------------------ finding a job's pictures
def _prov(out_dir: Path) -> dict:
    p = out_dir / "prov.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except ValueError:
        return {}


def find_raw(out_dir: Path) -> Path | None:
    """The render before the forge's own upscale: raw.png in the job folder or its first pipeline step that has one."""
    if (out_dir / "raw.png").exists():
        return out_dir / "raw.png"
    for step in sorted(out_dir.glob("[0-9][0-9]_*")):
        if (step / "raw.png").exists():
            return step / "raw.png"
    return None


def find_main(out_dir: Path, job: dict | None = None) -> Path | None:
    """The job's main picture (what the rest of the kit was built from / what approve would pick)."""
    prov = _prov(out_dir)
    slots = prov.get("slots") or ((job or {}).get("result") or {}).get("slots") or {}
    if slots.get("_main") and (out_dir / slots["_main"]).exists():
        return out_dir / slots["_main"]
    for o in ((job or {}).get("result") or {}).get("outputs") or []:
        p = out_dir / str(o)
        if p.suffix.lower() == ".png" and p.exists() and not p.stem.startswith(("contact", "sheet")):
            return p
    for name in ("scene.png", "painting.png", "upscaled.png"):
        if (out_dir / name).exists():
            return out_dir / name
    pngs = [p for p in sorted(out_dir.glob("*.png")) if not p.stem.startswith(("contact", "sheet", "check", "raw"))]
    return pngs[0] if pngs else None


def is_kit(out_dir: Path, job: dict | None = None) -> bool:
    return bool(_prov(out_dir).get("set")) or (job or {}).get("type") == "scene_kit"


def resolve_jobs(cfg: dict, refs: list[str]) -> list[tuple[str, dict]]:
    """Job ids and/or batch names (a batch matches itself and its sub-batches) → finished jobs, oldest first."""
    done = cfgmod.path_of(cfg, "jobs") / "done"
    picked: dict[str, dict] = {}
    all_jobs = None
    for ref in refs:
        p = done / f"{ref}.json"
        if p.exists():
            picked[ref] = json.loads(p.read_text(encoding="utf-8"))
            continue
        if all_jobs is None:
            all_jobs = {}
            for q in sorted(done.glob("*.json")):
                try:
                    all_jobs[q.stem] = json.loads(q.read_text(encoding="utf-8"))
                except ValueError:
                    continue
        hits = {k: j for k, j in all_jobs.items() if str(j.get("batch") or "") == ref or str(j.get("batch") or "").startswith(ref + "/")}
        if not hits:
            raise HandoffError(f"'{ref}' is neither a finished job id nor a batch with finished jobs (looked in {done})")
        picked.update(hits)
    return sorted(picked.items())


def _base_from(cfg: dict, to: str | None, name: str | None) -> Path:
    out_root = cfgmod.path_of(cfg, "out")
    if to:
        t = Path(to)
        t = t if t.is_absolute() else cfgmod.ROOT / t
        base = t.parent if t.name.lower() == "in" else t
    elif name:
        base = out_root / "handoff" / name
    else:
        raise HandoffError("say where: --to out/handoff/<name>/in")
    base = base.resolve()
    if out_root.resolve() not in base.parents:
        raise HandoffError(f"the hand-off folder must be inside {out_root} (got {base})")
    return base


def _rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(cfgmod.ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(p.resolve())


# ------------------------------------------------------------------ out
README = """Hand-off folder '{name}' — made by RPG_Forge on {date}
================================================================

What to do
  1. Open your tool and batch-process every picture in this folder:
       {inn}
  2. Make each result the size listed below (that is the size the rest of the forge expects).
  3. Save the results into:
       {done}
     KEEP THE START OF EACH FILE NAME — everything up to and including the two underscores "__".
     Your tool may add its own tag after that, and may save PNG, JPG or TIF.
  4. Then run:  handoff_in.bat {name}

Pictures ({n})
{rows}

If a result comes back at a different size with the same shape, the forge resizes it to the size above and says so;
a different shape is refused and named. Nothing here is deleted by the forge.
"""


def hand_out(cfg: dict, refs: list[str], to: str | None = None, name: str | None = None) -> dict:
    base = _base_from(cfg, to, name)
    name = base.name
    inn, done = base / "in", base / "done"
    inn.mkdir(parents=True, exist_ok=True)
    done.mkdir(parents=True, exist_ok=True)
    out_root = cfgmod.path_of(cfg, "out")
    entries, notes = [], []
    for job_id, job in resolve_jobs(cfg, refs):
        od = out_root / job_id
        main = find_main(od, job)
        raw = find_raw(od)
        src = raw or main
        if src is None:
            notes.append(f"{job_id}: no picture in {od} — left out")
            continue
        if raw is None:
            notes.append(f"{job_id}: no raw render kept — handed out its finished picture {main.name} instead")
        with Image.open(main or src) as im:
            target = list(im.size)
        with Image.open(src) as im:
            src_size = list(im.size)
        fname = f"{job_id}{SEP}{src.stem}.png"
        if src.suffix.lower() == ".png":
            shutil.copyfile(src, inn / fname)
        else:
            Image.open(src).save(inn / fname, "PNG")
        prov = _prov(od)
        entries.append({"job": job_id, "file": fname, "source": _rel(src), "source_size": src_size, "target_size": target,
                        "kit": is_kit(od, job), "slot": (prov.get("slot_name") or (main.stem if main else "picture")),
                        "name": job.get("name"), "game": job.get("game")})
    if not entries:
        raise HandoffError("nothing to hand out" + (": " + "; ".join(notes) if notes else ""))
    man = {"name": name, "created": datetime.now().isoformat(timespec="seconds"), "in": _rel(inn), "done": _rel(done),
           "entries": entries, "notes": notes}
    _write_json_atomic(base / "handoff.json", man)
    rows = "\n".join(f"  {e['file']:70s} {e['source_size'][0]}x{e['source_size'][1]} -> make it {e['target_size'][0]}x{e['target_size'][1]}"
                     for e in entries)
    (base / "README.txt").write_text(README.format(name=name, date=f"{datetime.now():%Y-%m-%d %H:%M}", inn=inn, done=done,
                                                   n=len(entries), rows=rows), encoding="utf-8", newline="\r\n")
    return man


# ------------------------------------------------------------------ in
def _match(entries: list[dict], done: Path) -> tuple[dict[str, Path], list[str], list[str]]:
    by_job = {e["job"]: e for e in entries}
    got: dict[str, list[Path]] = {}
    extra = []
    for p in sorted(done.iterdir()) if done.exists() else []:
        if not p.is_file() or p.suffix.lower() not in RETURN_EXTS:
            continue
        jid = p.name.split(SEP, 1)[0] if SEP in p.name else None
        if jid in by_job:
            got.setdefault(jid, []).append(p)
        else:
            extra.append(p.name)
    picked, notes = {}, []
    for jid, files in got.items():
        files.sort(key=lambda q: q.stat().st_mtime)
        picked[jid] = files[-1]
        if len(files) > 1:
            notes.append(f"{jid}: {len(files)} files came back — using the newest, {files[-1].name}")
    return picked, extra, notes


def hand_in(cfg: dict, name: str, tool: str | None = None, submit: bool = True, priority: int = 10,
            root: Path | None = None, queue=None) -> dict:
    base = _base_from(cfg, None, name) if not Path(name).is_absolute() else Path(name)
    man_p = base / "handoff.json"
    if not man_p.exists():
        raise HandoffError(f"no hand-off called '{name}' ({man_p} is missing) — make one with handoff_out.bat first")
    man = json.loads(man_p.read_text(encoding="utf-8"))
    tools = load_tools(root)
    tool = tool or man.get("tool")
    if not tool:
        if len(tools) == 1:
            tool = next(iter(tools))
        else:
            raise HandoffError("which tool made these? --tool \"<name version>\"" +
                               (f" (on file: {', '.join(sorted(tools))})" if tools else " (none on file yet — handoff_tool_add.bat records one)"))
    tool = tool.strip()
    warn = [] if tool in tools else [f"'{tool}' has no licence on file — the pictures are filed, but approve will ask "
                                     "for it first (handoff_tool_add.bat)"]
    done = base / "done"
    picked, extra, notes = _match(man["entries"], done)
    filed_dir = base / "filed"
    filed_dir.mkdir(exist_ok=True)
    report = {"name": man["name"], "tool": tool, "filed": [], "missing": [], "wrong_size": [], "extra": extra,
              "notes": notes, "warnings": warn, "jobs": []}
    jobs = []
    for e in man["entries"]:
        jid = e["job"]
        f = picked.get(jid)
        if f is None:
            report["missing"].append(e["file"])
            continue
        tw, th = e["target_size"]
        try:
            im = Image.open(f)
            im.load()
        except Exception as ex:  # noqa: BLE001
            report["wrong_size"].append(f"{f.name}: cannot be read ({type(ex).__name__}: {ex})")
            continue
        w, h = im.size
        if (w, h) != (tw, th):
            if abs((w / h) - (tw / th)) / (tw / th) > ASPECT_TOLERANCE:
                report["wrong_size"].append(f"{f.name}: {w}x{h} is a different shape from {tw}x{th} — not filed")
                continue
            im = im.resize((tw, th), Image.LANCZOS)
            report["notes"].append(f"{f.name}: came back {w}x{h}, resized to {tw}x{th}")
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
        dest = filed_dir / f"{jid}.png"
        im.save(dest, "PNG")
        report["filed"].append({"job": jid, "returned": f.name, "file": _rel(dest)})
        jobs.append({"type": "handoff_kit" if e.get("kit") else "handoff_file", "input": _rel(dest), "source_job": jid,
                     "tool": tool, "slot_name": e.get("slot"), "target": [tw, th],
                     "name": f"{e.get('name') or jid}_{man['name']}", "batch": f"handoff/{man['name']}",
                     "priority": int(priority), **({"game": e["game"]} if e.get("game") else {}),
                     "returned_file": f.name})
    batch = {"batch": f"handoff/{man['name']}", "jobs": jobs}
    _write_json_atomic(base / "jobs.json", batch)
    report["batch_file"] = _rel(base / "jobs.json")
    if jobs and submit:
        if queue is None:
            from .queue import Queue
            cfgmod.ensure_dirs(cfg)
            queue = Queue(cfgmod.path_of(cfg, "jobs"), cfgmod.path_of(cfg, "out"))
        report["jobs"] = queue.submit_batch(batch)
    man["tool"] = tool
    man.setdefault("history", []).append({"in": datetime.now().isoformat(timespec="seconds"), "tool": tool,
                                          "filed": len(report["filed"]), "missing": len(report["missing"]),
                                          "wrong_size": len(report["wrong_size"]), "jobs": report["jobs"]})
    _write_json_atomic(man_p, man)
    return report


# ------------------------------------------------------------------ approve's pre-flight
def tools_in_job(cfg: dict, job_id: str) -> list[str]:
    """Outside tools named in a job's provenance (handoff jobs, Filter Forge jobs)."""
    od = cfgmod.path_of(cfg, "out") / job_id
    found = []
    provs = [od / "prov.json"] + sorted(od.glob("[0-9][0-9]_*/prov.json"))
    for p in provs:
        d = _prov(p.parent)
        for lic in d.get("licences") or []:
            if lic.get("role") == "outside_tool" and lic.get("file") and lic["file"] not in found:
                found.append(lic["file"])
    return found


def approve_preflight(cfg: dict, job_id: str, ask=input, out=print, interactive: bool | None = None,
                      root: Path | None = None) -> None:
    """Before approve: say which outside tools touched the picture; for one with no licence on file, ask for it."""
    tools = load_tools(root)
    if interactive is None:
        interactive = bool(getattr(sys.stdin, "isatty", lambda: False)())
    for key in tools_in_job(cfg, job_id):
        rec = tools.get(key)
        if rec:
            out(f"  outside tool: {key} — commercial use {'yes' if rec.get('commercial_ok') else 'NO'}"
                + (f" — condition: {rec['licence_condition']}" if rec.get("licence_condition") else ""))
            continue
        out(f"⚠ this picture went through '{key}', whose licence is not on file.")
        if interactive:
            yn = ask("  Record its licence now? yes / no: ").strip().lower()
            if yn.startswith("y"):
                name, _, version = key.rpartition(" ")
                k = None
                try:
                    k = ask_tool(ask=ask, out=out, root=root, name=name or key, version=version if name else "")
                except HandoffError as e:
                    out(f"  ✗ {e}")
                if k and k != key:
                    out(f"  note: you recorded '{k}', but the picture names '{key}' — type the same name and version")
        else:
            out(f"  record it first:  handoff_tool_add.bat   (name and version exactly: {key})")
