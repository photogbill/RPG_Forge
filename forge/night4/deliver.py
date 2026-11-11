"""Delivery (Night 4, F3): approved pictures → the game, with a ledger so a redo can be traced and a delivery undone.

    deliver hold <job> --as <wanted> [--pick N | --file f]   approve WITHOUT copying (licence check now, copy later —
                                                             e.g. from a session that cannot reach the game folder)
    deliver [--dry] [--only <wanted>] [--fit]                copy every held approval, and every approval whose file in
                                                             the game is missing or was changed since, into the game
    deliver undo <wanted>                                    put back what the last delivery replaced
    deliver ledger                                           the record

Rules: only approved pictures move (approve's licence gate, or `hold`'s — the same check); the size must equal the
wanted item's target (`--fit` cover-fits and records that it did); whatever is replaced is kept in out/_replaced/ —
nothing is ever deleted; the ledger is games/<game>/delivered.json (job id, file, sha256, time, licences). When the
game folder is not reachable from here, deliver writes the copy list as a .bat for William instead
(out/deliver/copy_<time>.bat); running it copies, keeps the old files, and records the deliveries.
"""
from __future__ import annotations
import hashlib
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from .. import config as cfgmod

log = logging.getLogger("forge.deliver")


class DeliverError(RuntimeError):
    pass


def _gdir(cfg: dict, game: str) -> Path:
    return cfgmod.path_of(cfg, "games") / game


def _read(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default
    except (OSError, ValueError):
        return default


def _write(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    tmp.replace(p)


def ledger(cfg: dict, game: str) -> list[dict]:
    return _read(_gdir(cfg, game) / "delivered.json", {"entries": []}).get("entries", [])


def ledger_add(cfg: dict, game: str, entry: dict) -> None:
    p = _gdir(cfg, game) / "delivered.json"
    d = _read(p, {"_comment": "Every delivery into the game (deliver.bat / approve). Newest last. Undo: deliver undo <name>.",
                  "entries": []})
    d.setdefault("entries", []).append({"time": datetime.now().isoformat(timespec="seconds"), **entry})
    _write(p, d)


def live(cfg: dict, game: str) -> dict[str, dict]:
    """{wanted name: the delivery that is in the game now} — the last 'delivered' entry not followed by an undo."""
    out: dict[str, dict] = {}
    for e in ledger(cfg, game):
        if e.get("action") in ("delivered", "approved"):
            out[e["wanted"]] = e
        elif e.get("action") == "undo":
            out.pop(e["wanted"], None)
    return out


def _sha(p: Path) -> tuple[str, str]:
    b = p.read_bytes()
    return hashlib.sha256(b).hexdigest(), hashlib.sha1(b).hexdigest()[:16]


def held(cfg: dict, game: str) -> dict:
    return _read(_gdir(cfg, game) / "held.json", {})


def hold(cfg: dict, job_id: str, wanted_name: str, game: str | None = None, file: str | None = None,
         pick: int | None = None) -> dict:
    game = game or cfgmod.default_game(cfg)   # never a literal game (RPG_Forge is game-agnostic)
    from .. import manifest
    plan = manifest.approve(cfg, job_id, wanted_name, game, file=file, pick=pick, dry_run=True)   # the same licence gate
    h = held(cfg, game)
    h[wanted_name] = {"job_id": job_id, "file": plan["file"], "licences": plan["licences"], "size": plan["size"],
                      "target_size": plan["target_size"], "held": datetime.now().isoformat(timespec="seconds")}
    _write(_gdir(cfg, game) / "held.json", h)
    log.info("held %s ← %s", wanted_name, job_id)
    return h[wanted_name]


def _fit(src: Path, size, dest: Path) -> Path:
    from PIL import Image, ImageOps
    im = Image.open(src)
    im = ImageOps.fit(im, (int(size[0]), int(size[1])), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "PNG")
    return dest


def todo(cfg: dict, game: str, only: str | None = None) -> list[dict]:
    """What deliver would move: held approvals + approvals whose game file is missing or changed."""
    from .. import manifest
    wanted = manifest.load_wanted(cfg, game)["items"]
    gcfg = cfgmod.game_config(cfg, game)
    root = Path(gcfg.get("game_root") or "")
    out = []
    for name, h in held(cfg, game).items():
        out.append({"wanted": name, "job_id": h["job_id"], "src": h["file"], "licences": h.get("licences"), "why": "held approval"})
    for name, a in manifest.load_approved(cfg, game).items():
        if name in {o["wanted"] for o in out}:
            continue
        dest = root / a.get("dest", "")
        if not root.exists():
            continue                    # cannot tell from here — approve copied it when it ran
        if not dest.exists() or manifest.sha256(dest) != a.get("sha256"):
            src = cfgmod.path_of(cfg, "out") / a["job_id"] / a["file"]
            out.append({"wanted": name, "job_id": a["job_id"], "src": str(src), "licences": a.get("licences"),
                        "why": "missing in the game" if not dest.exists() else "changed in the game since approval"})
    for o in out:
        w = wanted.get(o["wanted"]) or {}
        o["dest_rel"] = w.get("path")
        o["target_size"] = w.get("target_size")
    return [o for o in out if not only or o["wanted"] == only]


def run(cfg: dict, game: str | None = None, dry: bool = False, only: str | None = None, fit: bool = False) -> dict:
    game = game or cfgmod.default_game(cfg)   # never a literal game (RPG_Forge is game-agnostic)
    from PIL import Image
    gcfg = cfgmod.game_config(cfg, game)
    root = Path(gcfg.get("game_root") or "")
    asset_root = Path(gcfg.get("asset_root") or (root / "project" / "assets"))
    out_root = cfgmod.path_of(cfg, "out")
    items = todo(cfg, game, only)
    rep = {"moved": [], "refused": [], "dry": dry, "listed": None}
    ready = []
    for it in items:
        src = Path(it["src"])
        if not src.exists():
            rep["refused"].append({**it, "reason": f"the approved file is gone: {src}"}); continue
        if not it.get("dest_rel"):
            rep["refused"].append({**it, "reason": "not in wanted.json any more"}); continue
        with Image.open(src) as im:
            got = list(im.size)
        tgt = it.get("target_size")
        if tgt and got != list(tgt):
            if not fit:
                rep["refused"].append({**it, "reason": f"size {got[0]}×{got[1]}, the game wants {tgt[0]}×{tgt[1]} "
                                                       "(deliver --fit crops and scales it to fit)"}); continue
            src = _fit(src, tgt, out_root / "_deliver_fit" / (it["wanted"].replace("/", "__") + ".png"))
            it["fitted"] = f"{got[0]}×{got[1]} → {tgt[0]}×{tgt[1]} (cover-fit)"
        it["src"] = str(src)
        ready.append(it)
    if dry:
        rep["moved"] = ready
        return rep
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if not asset_root.exists():
        rep["listed"] = str(write_bat(cfg, game, ready, root, stamp))
        return rep
    for it in ready:
        dest = root / it["dest_rel"]
        try:
            dest.resolve().relative_to(asset_root.resolve())
        except ValueError:
            rep["refused"].append({**it, "reason": f"{dest} is outside the game's asset folder"}); continue
        replaced = None
        if dest.exists():
            bdir = out_root / "_replaced" / it["wanted"].replace("/", "__")
            bdir.mkdir(parents=True, exist_ok=True)
            replaced = bdir / f"{stamp}_{dest.name}"
            shutil.copyfile(dest, replaced)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(it["src"], dest)
        s256, s1 = _sha(dest)
        _after_copy(cfg, game, it, dest, s256)
        ledger_add(cfg, game, {"action": "delivered", "wanted": it["wanted"], "job_id": it["job_id"],
                               "file": Path(it["src"]).name, "dest": it["dest_rel"], "sha256": s256, "sha1": s1,
                               "licences": it.get("licences"), "replaced": str(replaced) if replaced else None,
                               "fitted": it.get("fitted"), "why": it["why"]})
        rep["moved"].append({**it, "replaced": str(replaced) if replaced else None})
        log.info("delivered %s ← %s", it["wanted"], it["job_id"])
    return rep


def _after_copy(cfg: dict, game: str, it: dict, dest: Path, s256: str) -> None:
    """A held approval becomes a normal approval (approved.json + provenance in the game)."""
    from .. import manifest
    h = held(cfg, game)
    if it["wanted"] not in h:
        return
    gcfg = cfgmod.game_config(cfg, game)
    asset_root = Path(gcfg.get("asset_root"))
    prov_dir = Path(gcfg.get("provenance_dir") or (asset_root / "_provenance"))
    prov_dest = prov_dir / (it["wanted"].replace("/", "__") + ".json")
    _parts, read = manifest.collect_models(cfg, cfgmod.path_of(cfg, "out") / it["job_id"])
    rec = {"asset": it["dest_rel"], "wanted": it["wanted"], "approved": h[it["wanted"]]["held"],
           "delivered": datetime.now().isoformat(timespec="seconds"), "job_id": it["job_id"],
           "file": Path(it["src"]).name, "sha256": s256, "licences": it.get("licences"), "commercial_ok": True,
           "made_by": "RPG_Forge (AI-generated with the models listed; see licences)",
           "fitted": it.get("fitted"), "prov": [json.loads(Path(p).read_text(encoding="utf-8")) for p in read]}
    prov_dir.mkdir(parents=True, exist_ok=True)
    prov_dest.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    ap = manifest.load_approved(cfg, game)
    ap[it["wanted"]] = {"job_id": it["job_id"], "file": Path(it["src"]).name, "sha256": s256, "dest": it["dest_rel"],
                        "provenance": str(prov_dest), "date": rec["delivered"], "licences": it.get("licences")}
    _write(_gdir(cfg, game) / "approved.json", ap)
    h.pop(it["wanted"])
    _write(_gdir(cfg, game) / "held.json", h)


def write_bat(cfg: dict, game: str, ready: list[dict], root: Path, stamp: str) -> Path:
    """The copy list for William: back up what is there into the forge's out/_replaced, copy, then record."""
    d = cfgmod.path_of(cfg, "out") / "deliver"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"copy_{stamp}.bat"
    L = ["@echo off", "chcp 65001 >nul", "rem deliver.bat wrote this: the game folder was not reachable from the forge's session.",
         "rem Run it on the PC with the game folder. It keeps every file it replaces in the forge's out\\_replaced.",
         f'cd /d "%~dp0..\\.."', ""]
    for it in ready:
        dest = str(Path(str(root)) / it["dest_rel"]).replace("/", "\\")
        src = str(it["src"]).replace("/", "\\")
        bdir = f"out\\_replaced\\{it['wanted'].replace('/', '__')}"
        L += [f'if exist "{dest}" ( if not exist "{bdir}" mkdir "{bdir}" & copy /Y "{dest}" "{bdir}\\{stamp}_{Path(dest).name}" >nul )',
              f'if not exist "{str(Path(dest).parent)}" mkdir "{str(Path(dest).parent)}"',
              f'copy /Y "{src}" "{dest}" >nul && echo delivered {it["wanted"]}']
    L += ["", f"call venv\\Scripts\\python.exe -m forge deliver record {p.name}", "pause"]
    p.write_text("\r\n".join(L) + "\r\n", encoding="utf-8")
    (d / f"copy_{stamp}.json").write_text(json.dumps({"game": game, "items": ready, "stamp": stamp}, indent=1), encoding="utf-8")
    log.info("deliver: game folder not reachable — wrote %s (%d file(s))", p, len(ready))
    return p


def record_listed(cfg: dict, bat_name: str) -> int:
    """After a copy_<time>.bat ran on William's PC: ledger the files that are now in the game."""
    d = cfgmod.path_of(cfg, "out") / "deliver"
    info = json.loads((d / bat_name.replace(".bat", ".json")).read_text(encoding="utf-8"))
    game = info["game"]
    root = Path(cfgmod.game_config(cfg, game).get("game_root") or "")
    n = 0
    for it in info["items"]:
        dest = root / it["dest_rel"]
        if not dest.exists():
            continue
        s256, s1 = _sha(dest)
        if s256 != _sha(Path(it["src"]))[0]:
            continue
        _after_copy(cfg, game, it, dest, s256)
        rb = cfgmod.path_of(cfg, "out") / "_replaced" / it["wanted"].replace("/", "__") / f"{info['stamp']}_{dest.name}"
        ledger_add(cfg, game, {"action": "delivered", "wanted": it["wanted"], "job_id": it["job_id"], "file": Path(it["src"]).name,
                               "dest": it["dest_rel"], "sha256": s256, "sha1": s1, "licences": it.get("licences"),
                               "replaced": str(rb) if rb.exists() else None, "via": bat_name})
        n += 1
    return n


def undo(cfg: dict, game: str, wanted: str) -> dict:
    cur = live(cfg, game).get(wanted)
    if not cur:
        raise DeliverError(f"nothing delivered for {wanted} (deliver ledger shows the record)")
    root = Path(cfgmod.game_config(cfg, game).get("game_root") or "")
    dest = root / cur["dest"]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    keep = cfgmod.path_of(cfg, "out") / "_replaced" / wanted.replace("/", "__") / f"{stamp}_undone_{dest.name}"
    keep.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.copyfile(dest, keep)
    if cur.get("replaced") and Path(cur["replaced"]).exists():
        shutil.copyfile(cur["replaced"], dest)
        what = f"put back {Path(cur['replaced']).name}"
    else:
        if dest.exists():
            shutil.move(str(dest), str(keep.with_name(keep.name + ".moved")))   # nothing was there before: take it out
        what = "there was nothing before — the delivered file was moved to out/_replaced"
    ledger_add(cfg, game, {"action": "undo", "wanted": wanted, "job_id": cur.get("job_id"), "kept": str(keep), "what": what})
    return {"wanted": wanted, "what": what, "kept": str(keep)}
