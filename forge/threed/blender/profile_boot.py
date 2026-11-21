"""Runs INSIDE Blender (BUILD 98 Part 1a): enable one profile's add-ons, then run the job's script.

    blender --background --factory-startup [file.blend] --python profile_boot.py -- \
            --profile trees --modules a,b,c --script grow.py --out <run folder> [--] <the script's own args>

Writes <run folder>/boot.json: which add-ons came up, which failed and why, the Blender version, and the script's own
`result` (a dict the script may set as a global). Preferences are never saved, so nothing about William's Blender changes.
"""
import json
import os
import runpy
import sys
import time
import traceback


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opts, rest, i = {}, [], 0
    while i < len(argv):
        a = argv[i]
        if a == "--":
            rest = argv[i + 1:]
            break
        if a.startswith("--") and i + 1 < len(argv):
            opts[a[2:]] = argv[i + 1]
            i += 2
            continue
        rest.append(a)
        i += 1
    return opts, rest


def main():
    import addon_utils
    import bpy
    opts, rest = _args()
    out = opts.get("out") or os.getcwd()
    os.makedirs(out, exist_ok=True)
    boot = {"blender": bpy.app.version_string, "profile": opts.get("profile") or "", "enabled": [], "failed": {},
            "script": opts.get("script") or "", "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        bpy.context.preferences.use_preferences_save = False
    except Exception:  # noqa: BLE001
        pass
    for mod in [m for m in (opts.get("modules") or "").split(",") if m]:
        try:
            got = addon_utils.enable(mod, default_set=True, persistent=False, handle_error=None)
            if got is None and not addon_utils.check(mod)[1]:
                boot["failed"][mod] = "did not load (not installed in this Blender, or its own error above)"
            else:
                boot["enabled"].append(mod)
        except Exception as ex:  # noqa: BLE001
            boot["failed"][mod] = f"{type(ex).__name__}: {ex}"
    print("FORGE_BOOT", json.dumps({"enabled": len(boot["enabled"]), "failed": boot["failed"]}), flush=True)
    code = 0
    if boot["script"]:
        sys.argv = [boot["script"]] + rest
        try:
            g = runpy.run_path(boot["script"], run_name="__main__")
            res = g.get("result")
            if res is not None:
                boot["result"] = res
        except SystemExit as ex:
            code = int(ex.code or 0) if not isinstance(ex.code, str) else 1
        except Exception:  # noqa: BLE001
            boot["error"] = traceback.format_exc()[-4000:]
            code = 1
    boot["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    boot["exit"] = code
    with open(os.path.join(out, "boot.json"), "w", encoding="utf-8") as f:
        json.dump(boot, f, indent=1, default=str)
    print("FORGE_DONE", code, flush=True)
    sys.exit(code)


main()
