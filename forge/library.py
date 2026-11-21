"""The Libraries shelf (BUILD 98 Part 1c): every outside asset the forge keeps, each with its licence and its source.

✦ William, 2026-11-21: "Lets build every tool that we need into rpg forge". 98 1c: "Nothing goes into the game without its
licence line."

    python -m forge.library search <words> [--kind texture|model|hdri] [--online]
    python -m forge.library import polyhaven <asset id> [--res 2k]
    python -m forge.library import ambientcg <asset id> [--res 2K]
    python -m forge.library import folder <path> --source fab|scan|blenderkit --licence "<its licence line>" [--name …]
    python -m forge.library list

The shelf is library/ in the forge folder: library/library.json (one entry per asset: id, name, kind, source, licence,
source_url, files, tags, added, by) and one folder per asset, library/<source>/<id>/, with LICENCE.txt beside the files.
Only licences on the allowed list are taken (CC0, the Fab Standard Licence, BlenderKit Royalty-Free, William's own);
anything else is refused with its reason (BUILD_RULES: nothing non-commercial, nothing 'by permission').
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = {"User-Agent": "RPG-Forge library (offline game dev suite)"}
ALLOWED = ("cc0", "fab standard", "royalty-free", "royalty free", "william's own", "mit", "cc-by 4.0", "cc-by-4.0")
REFUSED = ("non-commercial", "noncommercial", "nc-", "-nc", "by permission", "editorial", "personal use")


class LibraryError(Exception):
    pass


def shelf_dir(cfg: dict | None = None) -> Path:
    raw = ((cfg or {}).get("paths") or {}).get("library")
    return Path(raw) if raw and Path(raw).is_absolute() else ROOT / (raw or "library")


def _index_path(cfg=None) -> Path:
    return shelf_dir(cfg) / "library.json"


def load(cfg=None) -> dict:
    p = _index_path(cfg)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"_comment": "The Libraries shelf (BUILD 98 1c). Every asset with its licence and source; nothing goes into a game "
                        "without its licence line.", "assets": []}


def save(d: dict, cfg=None) -> None:
    p = _index_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.part")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def licence_ok(line: str) -> tuple[bool, str]:
    s = (line or "").lower()
    if any(r in s for r in REFUSED):
        return False, f"refused: {line!r} is not allowed in a game we sell (BUILD_RULES)"
    if any(a in s for a in ALLOWED):
        return True, ""
    return False, f"refused: {line!r} is not on the allowed list ({', '.join(ALLOWED)}); ask William"


def search(words: str, kind: str = "", cfg=None) -> list[dict]:
    ws = [w for w in re.split(r"\W+", (words or "").lower()) if w]
    out = []
    for a in load(cfg)["assets"]:
        hay = " ".join([a.get("id", ""), a.get("name", ""), " ".join(a.get("tags") or []), a.get("source", "")]).lower()
        if kind and a.get("kind") != kind:
            continue
        if all(w in hay for w in ws):
            out.append(a)
    return out


def _get_json(url: str):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def _download(url: str, dest: Path) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    os.replace(tmp, dest)
    return dest.stat().st_size


def search_online(words: str, kind: str = "texture") -> list[dict]:
    """Poly Haven's own list (CC0), matched on name, tags and categories. Read only."""
    t = {"texture": "textures", "model": "models", "hdri": "hdris"}.get(kind or "texture", "textures")
    d = _get_json(f"https://api.polyhaven.com/assets?t={t}")
    ws = [w for w in re.split(r"\W+", (words or "").lower()) if w]
    out = []
    for aid, a in d.items():
        hay = " ".join([aid, a.get("name", ""), " ".join(a.get("tags") or []), " ".join(a.get("categories") or [])]).lower()
        if all(w in hay for w in ws):
            out.append({"source": "polyhaven", "id": aid, "name": a.get("name"), "kind": kind or "texture",
                        "licence": "CC0", "url": f"https://polyhaven.com/a/{aid}"})
    return out[:60]


def _add(entry: dict, cfg=None) -> dict:
    ok, why = licence_ok(entry.get("licence", ""))
    if not ok:
        raise LibraryError(why)
    d = load(cfg)
    d["assets"] = [a for a in d["assets"] if not (a.get("source") == entry["source"] and a.get("id") == entry["id"])]
    d["assets"].append(entry)
    save(d, cfg)
    folder = shelf_dir(cfg) / entry["source"] / entry["id"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "LICENCE.txt").write_text(f"{entry['name']}\nSource: {entry.get('source_url', '')}\nLicence: "
                                        f"{entry['licence']}\nAdded {entry['added']} by {entry.get('by', '')}\n",
                                        encoding="utf-8")
    return entry


def import_polyhaven(aid: str, res: str = "2k", who: str = "", cfg=None) -> dict:
    info = _get_json(f"https://api.polyhaven.com/info/{aid}")
    files = _get_json(f"https://api.polyhaven.com/files/{aid}")
    kind = {0: "hdri", 1: "texture", 2: "model"}.get(int(info.get("type", 1)), "texture")
    folder = shelf_dir(cfg) / "polyhaven" / aid
    got = []
    if kind == "texture":
        want = {"Diffuse": "colour", "nor_gl": "normal", "Rough": "roughness", "Displacement": "height", "AO": "ao",
                "arm": "arm"}
        for key, role in want.items():
            node = (files.get(key) or {}).get(res) or {}
            f = node.get("png") or node.get("jpg") or node.get("exr")
            if f and f.get("url"):
                name = f"{aid}_{role}_{res}{Path(f['url']).suffix}"
                _download(f["url"], folder / name)
                got.append(name)
    elif kind == "hdri":
        node = (files.get("hdri") or {}).get(res) or {}
        f = node.get("hdr") or node.get("exr")
        if f:
            name = f"{aid}_{res}{Path(f['url']).suffix}"
            _download(f["url"], folder / name)
            got.append(name)
    else:
        node = (files.get("gltf") or {}).get(res) or {}
        g = node.get("gltf")
        if g:
            _download(g["url"], folder / Path(g["url"]).name)
            got.append(Path(g["url"]).name)
            for rel, inc in (g.get("include") or {}).items():
                _download(inc["url"], folder / rel)
                got.append(rel)
    if not got:
        raise LibraryError(f"Poly Haven has no {res} files for {aid}")
    return _add({"id": aid, "name": info.get("name") or aid, "kind": kind, "source": "polyhaven", "licence": "CC0",
                 "source_url": f"https://polyhaven.com/a/{aid}", "files": got, "tags": list(info.get("tags") or []) +
                 list(info.get("categories") or []), "added": datetime.now().isoformat(timespec="seconds"), "by": who,
                 "res": res}, cfg)


def import_ambientcg(aid: str, res: str = "2K", who: str = "", cfg=None) -> dict:
    url = f"https://ambientcg.com/get?file={aid}_{res}-PNG.zip"
    folder = shelf_dir(cfg) / "ambientcg" / aid
    z = folder / f"{aid}_{res}-PNG.zip"
    _download(url, z)
    with zipfile.ZipFile(z) as zz:
        names = [n for n in zz.namelist() if not n.endswith("/") and ".." not in n and not n.startswith("/")]
        for n in names:
            zz.extract(n, folder)
    z.unlink()
    return _add({"id": aid, "name": aid, "kind": "texture", "source": "ambientcg", "licence": "CC0",
                 "source_url": f"https://ambientcg.com/view?id={aid}", "files": names, "tags": [],
                 "added": datetime.now().isoformat(timespec="seconds"), "by": who, "res": res}, cfg)


def import_folder(path: str, source: str, licence: str, name: str = "", kind: str = "", who: str = "", cfg=None,
                  tags: list | None = None) -> dict:
    """Something already on disk (a Fab download, one of William's scans, a BlenderKit asset): copied onto the shelf
    with its licence line. The original is left where it was."""
    src = Path(path)
    if not src.exists():
        raise LibraryError(f"nothing at {src}")
    ok, why = licence_ok(licence)
    if not ok:
        raise LibraryError(why)
    aid = re.sub(r"[^a-z0-9_]+", "_", (name or src.stem).lower()).strip("_")
    folder = shelf_dir(cfg) / source / aid
    folder.mkdir(parents=True, exist_ok=True)
    files = []
    for f in ([src] if src.is_file() else sorted(p for p in src.rglob("*") if p.is_file())):
        rel = f.name if src.is_file() else str(f.relative_to(src))
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, folder / rel)
        files.append(rel)
    if not kind:
        exts = {Path(f).suffix.lower() for f in files}
        kind = "model" if exts & {".glb", ".gltf", ".fbx", ".obj", ".blend"} else "texture"
    return _add({"id": aid, "name": name or src.stem, "kind": kind, "source": source, "licence": licence,
                 "source_url": str(src), "files": files, "tags": list(tags or []),
                 "added": datetime.now().isoformat(timespec="seconds"), "by": who}, cfg)


def main(argv=None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    def opt(k, d=""):
        if f"--{k}" in a:
            i = a.index(f"--{k}")
            return a[i + 1]
        return d
    if a[0] == "list":
        for x in load()["assets"]:
            print(f"{x['source']:10} {x['id']:40} {x['kind']:8} {x['licence']}")
    elif a[0] == "search":
        words = " ".join(w for w in a[1:] if not w.startswith("--") and w not in (opt("kind"),))
        res = search_online(words, opt("kind", "texture")) if "--online" in a else search(words, opt("kind"))
        print(json.dumps(res, indent=1))
    elif a[0] == "import":
        src, ident = a[1], a[2]
        who = opt("who", "William")
        if src == "polyhaven":
            print(json.dumps(import_polyhaven(ident, opt("res", "2k"), who), indent=1))
        elif src == "ambientcg":
            print(json.dumps(import_ambientcg(ident, opt("res", "2K"), who), indent=1))
        elif src == "folder":
            print(json.dumps(import_folder(ident, opt("source", "own"), opt("licence"), opt("name"), opt("kind"), who),
                             indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
