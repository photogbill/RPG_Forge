"""The asset manifest (roadmap F4): what the game wants vs. what the forge has made, and `approve`.

    python -m forge wanted [--refresh] [--kind scene] [--missing] [--game turing_accords]
    python -m forge approve <job-id> --as <wanted-name> [--file scene_2.png | --pick 2] [--dry-run]
    python -m forge models licence <file> "<licence>" yes|no [note]     record a licence you checked yourself
    python -m forge licences                                            the licence chain of every approved asset

wanted.json is exported from the game (games/<game>/export_wanted.py, read-only on the game). `approve` copies one
output of a finished job to the game path the manifest names — by path, no game code changes — with a provenance
record beside it in the game's `_provenance` folder, after checking that **every model that touched the pixels**
is known and commercial-OK (the job's own prov.json, the steps of a pipeline, and any earlier forge job whose
output it was made from). Anything unknown or non-commercial is refused, with the line to fix it. What was there
before is backed up to out/_approved_backup/ first. Approvals are recorded in games/<game>/approved.json (and in the
batch file's `approved` list) so the next session knows.
"""
from __future__ import annotations
import hashlib, json, re, shutil
from datetime import datetime
from pathlib import Path

from . import config as cfgmod
from .jobs.common import Context, licence_chain


class ApproveError(RuntimeError):
    pass


# ------------------------------------------------------------------ wanted
def game_dir(cfg: dict, game: str) -> Path:
    return cfgmod.path_of(cfg, "games") / game


def load_wanted(cfg: dict, game: str) -> dict:
    p = game_dir(cfg, game) / "wanted.json"
    if not p.exists():
        raise FileNotFoundError(f"{p} not found — run wanted.bat --refresh (python -m forge wanted --refresh)")
    return json.loads(p.read_text(encoding="utf-8"))


def refresh_wanted(cfg: dict, game: str, scan_root: str | None = None) -> dict:
    """Export wanted.json. `scan_root` reads the game from another path (tests, a mapped drive); the file always
    records the configured game_root, which is where `approve` writes."""
    gcfg = cfgmod.game_config(cfg, game)
    root = gcfg.get("game_root")
    if not root:
        raise ValueError(f"games/{game}/forge.game.json has no game_root")
    script = game_dir(cfg, game) / "export_wanted.py"
    if not script.exists():
        raise FileNotFoundError(f"{script} not found")
    import importlib.util
    spec = importlib.util.spec_from_file_location(f"export_wanted_{game}", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    data = mod.export(scan_root or root)
    data["game_root"] = root
    if scan_root:
        data["scanned_from"] = str(scan_root)
    (game_dir(cfg, game) / "wanted.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    return data


def load_approved(cfg: dict, game: str) -> dict:
    p = game_dir(cfg, game) / "approved.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def status(cfg: dict, game: str) -> list[dict]:
    """Every wanted item with `state`: approved · stale (approved, but the file on disk changed since — e.g. a
    placeholder regenerator overwrote it) · missing (nothing approved yet)."""
    wanted = load_wanted(cfg, game)
    approved = load_approved(cfg, game)
    root = Path(cfgmod.game_config(cfg, game).get("game_root") or wanted.get("game_root", ""))
    rows = []
    for name, w in sorted(wanted["items"].items()):
        a = approved.get(name)
        state = "missing"
        if a:
            p = root / w["path"]
            state = "approved" if p.exists() and sha256(p) == a.get("sha256") else "stale"
        rows.append({**w, "state": state, "approval": a})
    return rows


# ------------------------------------------------------------------ provenance
MODEL_KEYS = ("checkpoint", "upscale_model")


def _job_dir(cfg: dict, job_id: str) -> Path:
    return cfgmod.path_of(cfg, "out") / job_id


def _out_root(cfg: dict) -> Path:
    return cfgmod.path_of(cfg, "out")


def collect_models(cfg: dict, prov_dir: Path, seen: set | None = None) -> tuple[dict, list[str]]:
    """Every model file named by prov.json files in prov_dir (and its pipeline step folders), following inputs
    that came from other forge jobs. Returns ({role#n: file}, [the prov.json paths read])."""
    seen = seen if seen is not None else set()
    parts: dict[str, str] = {}
    read: list[str] = []
    out_root = _out_root(cfg)
    provs = [prov_dir / "prov.json"] + sorted(prov_dir.glob("[0-9][0-9]_*/prov.json"))
    for pp in provs:
        if not pp.exists() or str(pp) in seen:
            continue
        seen.add(str(pp))
        read.append(str(pp))
        d = json.loads(pp.read_text(encoding="utf-8"))
        n = len(parts)
        for k in MODEL_KEYS:
            if d.get(k):
                parts[f"{k}#{n}"] = d[k]
                n += 1
        for lo in d.get("loras") or []:
            if isinstance(lo, dict) and lo.get("name"):
                parts[f"lora#{n}"] = lo["name"]
                n += 1
        for lic in d.get("licences") or []:
            if lic.get("file"):
                parts[f"{lic.get('role', 'model')}#{n}"] = lic["file"]
                n += 1
        for r in d.get("renders") or []:          # portrait sets
            if r.get("checkpoint"):
                parts[f"checkpoint#{n}"] = r["checkpoint"]
                n += 1
        # inputs that are other forge jobs' outputs
        refs = list(d.get("inputs") or []) + [d.get("init")] + [((d.get("control") or {}).get("image"))]
        for ref in refs:
            if not ref:
                continue
            p = Path(str(ref))
            p = p if p.is_absolute() else cfgmod.ROOT / p
            try:
                rel = p.resolve().relative_to(out_root.resolve())
            except (ValueError, OSError):
                continue
            src = out_root / rel.parts[0]
            sub, more = collect_models(cfg, src, seen)
            for k, v in sub.items():
                parts[f"{k}<{rel.parts[0]}"] = v
            read += more
    return parts, read


def _pick_file(job: dict, out_dir: Path, file: str | None, pick: int | None) -> Path:
    outs = [o for o in (job.get("result") or {}).get("outputs") or []]
    if file:
        p = out_dir / file
        if not p.exists():
            raise ApproveError(f"{file} is not in out/{job['id']}/ (outputs: {', '.join(outs) or 'none listed'})")
        return p
    if pick is not None:
        if not 1 <= pick <= len(outs):
            raise ApproveError(f"--pick {pick}: the job has {len(outs)} output(s): {', '.join(outs)}")
        return out_dir / outs[pick - 1]
    if len(outs) == 1:
        return out_dir / outs[0]
    if not outs:
        raise ApproveError(f"job {job['id']} lists no outputs; name one with --file")
    raise ApproveError(f"job {job['id']} has {len(outs)} outputs — choose one with --pick N or --file NAME: " + ", ".join(outs))


def _inside(p: Path, root: Path) -> bool:
    try:
        p.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def approve(cfg: dict, job_id: str, wanted_name: str, game: str | None = None, file: str | None = None,
            pick: int | None = None, dry_run: bool = False) -> dict:
    jobs = cfgmod.path_of(cfg, "jobs")
    jp = jobs / "done" / f"{job_id}.json"
    if not jp.exists():
        if (jobs / "failed" / f"{job_id}.json").exists():
            raise ApproveError(f"job {job_id} failed — nothing to approve")
        raise ApproveError(f"no finished job {job_id} in jobs/done/")
    job = json.loads(jp.read_text(encoding="utf-8"))
    game = game or job.get("game") or "turing_accords"
    gcfg = cfgmod.game_config(cfg, game)
    wanted = load_wanted(cfg, game)
    if wanted_name not in wanted["items"]:
        close = [n for n in wanted["items"] if wanted_name.split("/")[-1] in n][:6]
        raise ApproveError(f"'{wanted_name}' is not in games/{game}/wanted.json" + (f" — did you mean: {', '.join(close)}" if close else ""))
    w = wanted["items"][wanted_name]
    out_dir = _job_dir(cfg, job_id)
    src = _pick_file(job, out_dir, file, pick)
    # licence chain — every model that touched the pixels, checked against today's registry
    ctx = Context(cfg=cfg, root=cfgmod.ROOT)
    parts, read = collect_models(cfg, out_dir)
    chain, ok = licence_chain(ctx, parts)
    if not parts:
        raise ApproveError(f"job {job_id}: no model is recorded in its provenance ({', '.join(read) or 'no prov.json'}) — "
                           "the forge cannot tell what made this picture, so it will not ship it")
    if not ok:
        bad = [c for c in chain if c.get("commercial_ok") is not True]
        lines = [f"  {c['file']}: {c.get('license')} (commercial_ok={c.get('commercial_ok')})" for c in bad]
        fix = ("If you have checked a licence yourself (e.g. the Civitai page), record it:\n"
               "  licence.bat \"<file>\" \"<licence name>\" yes \"<where you checked>\"\n"
               "Non-commercial models can never ship.")
        raise ApproveError(f"refused — not every model behind this picture is known commercial-OK:\n" + "\n".join(lines) + "\n" + fix)
    root = Path(gcfg.get("game_root") or wanted.get("game_root", ""))
    asset_root = Path(gcfg.get("asset_root") or (root / "project" / "assets"))
    dest = root / w["path"]
    if not _inside(dest, asset_root):
        raise ApproveError(f"refused — {dest} is outside the game's asset folder {asset_root}")
    prov_dir = Path(gcfg.get("provenance_dir") or (asset_root / "_provenance"))
    prov_dest = prov_dir / (wanted_name.replace("/", "__") + ".json")
    if not _inside(prov_dest, asset_root):
        raise ApproveError(f"refused — provenance folder {prov_dir} is outside {asset_root}")
    if src.suffix.lower() != Path(dest).suffix.lower():
        raise ApproveError(f"refused — {src.name} is {src.suffix}, the game wants {Path(dest).suffix}")
    from PIL import Image
    with Image.open(src) as im:
        got = list(im.size)
    plan = {"job": job_id, "file": str(src), "wanted": wanted_name, "dest": str(dest), "provenance": str(prov_dest),
            "size": got, "target_size": w.get("target_size"), "licences": chain,
            "size_note": None if not w.get("target_size") or got == w["target_size"] else
            f"size {got[0]}×{got[1]} differs from the target {w['target_size'][0]}×{w['target_size'][1]} — the game scales it; resize first if it must match"}
    if dry_run:
        plan["dry_run"] = True
        return plan
    # back up what is there, then copy
    if dest.exists():
        bdir = _out_root(cfg) / "_approved_backup" / wanted_name.replace("/", "__")
        bdir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(dest, bdir / f"{datetime.now():%Y%m%d-%H%M%S}_{dest.name}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    digest = sha256(dest)
    prov_dir.mkdir(parents=True, exist_ok=True)
    record = {"asset": w["path"], "wanted": wanted_name, "approved": datetime.now().isoformat(timespec="seconds"),
              "job_id": job_id, "file": src.name, "sha256": digest, "licences": chain, "commercial_ok": True,
              "made_by": "RPG_Forge (AI-generated with the models listed; see licences)",
              "prov": [json.loads(Path(p).read_text(encoding="utf-8")) for p in read]}
    prov_dest.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    approved = load_approved(cfg, game)
    approved[wanted_name] = {"job_id": job_id, "file": src.name, "sha256": digest, "dest": w["path"],
                             "provenance": str(prov_dest), "date": record["approved"], "licences": chain}
    (game_dir(cfg, game) / "approved.json").write_text(json.dumps(approved, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    _note_in_batch(cfg, game, job, wanted_name, src.name)
    plan["sha256"] = digest
    return plan


def _note_in_batch(cfg: dict, game: str, job: dict, wanted_name: str, file: str) -> None:
    b = job.get("batch")
    if not b or not re.fullmatch(r"[\w.\-]+", str(b)):
        return
    p = game_dir(cfg, game) / "batches" / f"{b}.json"
    if not p.exists():
        return
    data = json.loads(p.read_text(encoding="utf-8"))
    lst = data.setdefault("approved", [])
    lst[:] = [x for x in lst if not (isinstance(x, dict) and x.get("wanted") == wanted_name)]
    lst.append({"wanted": wanted_name, "job": job["id"], "name": job.get("name"), "file": file})
    p.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")


# ------------------------------------------------------------------ licences
def record_licence(cfg: dict, file: str, licence: str, commercial_ok: bool, note: str = "") -> Path:
    """models/licences.json — a licence a person checked (a Civitai checkpoint or LoRA). The forge never guesses one."""
    p = cfgmod.ROOT / "models" / "licences.json"
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    data[Path(file).name] = {"license": licence, "commercial_ok": bool(commercial_ok),
                             "checked": f"{datetime.now():%Y-%m-%d}" + (f" — {note}" if note else "")}
    p.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    return p


def licence_report(cfg: dict, game: str) -> str:
    approved = load_approved(cfg, game)
    lines = [f"# Licences of approved assets — {game}", "", f"Generated {datetime.now():%Y-%m-%d %H:%M} by `python -m forge licences`.", ""]
    if not approved:
        lines.append("Nothing approved yet.")
    for name, a in sorted(approved.items()):
        lines.append(f"## {name}")
        lines.append(f"`{a['dest']}` — job `{a['job_id']}` / {a['file']} — approved {a['date']}")
        for c in a.get("licences") or []:
            lines.append(f"- {c.get('role')}: `{c.get('file')}` — {c.get('license')} — commercial OK: {c.get('commercial_ok')}")
        lines.append("")
    return "\n".join(lines) + "\n"
