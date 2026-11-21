"""tools.list — every outside tool the forge drives, where it is, its licence, and whether it is there (BUILD 98 Part 1).

    python -m forge.toolsreg            every tool, one line each (the doctor's check for each)
    python -m forge.toolsreg --json

The list is forge/tools/registry.json. A tool is "found" when the first of its paths exists; forge.json -> tools -> <id>
-> exe overrides the list. Online libraries are "online" (nothing to find). Nothing here names a game.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "forge" / "tools" / "registry.json"


def _abs(p: str, root: Path) -> Path:
    p = os.path.expandvars(p)
    q = Path(p)
    if q.is_absolute() or (len(p) > 1 and p[1] == ":"):
        return q
    return root / p.replace("\\", os.sep)


def load(path: Path | None = None) -> list[dict]:
    return json.loads(Path(path or REGISTRY).read_text(encoding="utf-8"))["tools"]


def find(t: dict, cfg: dict | None = None, root: Path | None = None) -> Path | None:
    root = Path(root or ROOT)
    over = (((cfg or {}).get("tools") or {}).get(t["id"]) or {}).get("exe")
    for p in ([over] if over else []) + list(t.get("paths") or []):
        q = _abs(str(p), root)
        if q.exists():
            return q
    return None


def version(t: dict, path: Path) -> str:
    args = t.get("version_args")
    if not args or path.suffix.lower() not in (".exe", ""):
        return ""
    try:
        out = subprocess.run([str(path)] + list(args), capture_output=True, text=True, timeout=30).stdout
        return (out.strip().splitlines() or [""])[0][:80]
    except Exception:  # noqa: BLE001
        return ""


def listing(cfg: dict | None = None, root: Path | None = None, with_version: bool = False) -> list[dict]:
    rows = []
    for t in load():
        p = find(t, cfg, root)
        state = "online" if (not t.get("paths") and t.get("online")) else ("found" if p else "not installed")
        if not t.get("paths") and not t.get("online"):
            state = "inside another tool"
        rows.append({"id": t["id"], "name": t["name"], "state": state, "path": str(p) if p else None,
                     "version": version(t, p) if (p and with_version) else "", "licence": t.get("licence"),
                     "for": t.get("for"), "op": t.get("op"), "by_hand": t.get("by_hand"), "install": t.get("install")})
    return rows


def doctor_lines(cfg: dict | None = None) -> list[str]:
    """For doctor.bat: one line a tool."""
    out = []
    for r in listing(cfg):
        mark = "OK " if r["state"] in ("found", "online", "inside another tool") else "-- "
        out.append(f"{mark}{r['name']}: {r['state']}" + (f" ({r['path']})" if r["path"] else "") +
                   (f" — install: {r['install']}" if r["state"] == "not installed" and r.get("install") else ""))
    return out


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--json" in argv:
        print(json.dumps(listing(with_version=True), indent=1))
    else:
        print("\n".join(doctor_lines()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
