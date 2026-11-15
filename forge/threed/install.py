"""Install and check the rigging ComfyUI with the ComfyUI-UniRig node pack (UniRig + Make-It-Animatable).

    python -m forge 3d install [--dry-run] [--skip a,b] [--only a,b] [--torch-index <url>]      (Settings -> 3D tools -> Install)
    python -m forge 3d check                                                                   (Settings -> 3D tools -> Check)

Copied from the first game's rig_install.py (2026-11-12/13; it took three tries, and the fixes are in the steps below),
with its paths taken from the forge's settings instead of fixed. Steps, each skipped when it is already done, so it is
safe to run again after a failure:
  space     enough free disk, git present
  comfy     a second ComfyUI (engines/rig) at the same version as the art ComfyUI
  venv      its own Python environment
  torch     the same PyTorch build the art ComfyUI runs (known good on this card)
  reqs      ComfyUI's own requirements
  pack      the ComfyUI-UniRig node pack, at the commit that was read before this was written
  packreqs  the pack's three requirements (comfy-env, comfy-3d-viewers, trimesh)
  envpython the isolated environment is told to use Python 3.11, whatever Python ComfyUI itself runs on. Left alone it
            copies ComfyUI's Python (3.10 here), and the only Blender that exists as a module for 3.10 is Blender 3.6;
            the pack is written for Blender 4.2 and later and its nodes fail to load on 3.6 (first install, 2026-11-12).
  isolated  the pack's install.py: comfy-env builds the isolated environment (pixi; Blender as a module; spconv,
            flash-attn, torch-scatter ...). The long step. If the environment holds packages built for another
            Python than its own, it is thrown away and built fresh: changing the environment's Python in place left
            the 3.10 build of PyTorch inside a 3.11 environment (second install, 2026-11-13), and PyTorch then
            cannot load.
  smoke     start it once on the processor only (no graphics memory), save what its nodes take, stop it

Nothing here touches engines/ComfyUI, the forge's own environment or the forge's job queue, and nothing is written
outside the forge's drive (env.py moves every cache and the pack's environment there). Every line of every step goes to
out/3d/_install/install.log; the short verdict is out/3d/_install/INSTALL_REPORT.txt.
"""
from __future__ import annotations

import collections
import hashlib
import json
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from .env import RigEnv, WIN, from_cfg, out_root, stop

R: RigEnv = RigEnv()                                              # set from the forge's settings in main()
OUT: Path = R.root / "out" / "3d" / "_install"

COMFY_REPO = "https://github.com/comfyanonymous/ComfyUI"
PACK_REPO = "https://github.com/PozzettiAndrea/ComfyUI-UniRig.git"
PACK_COMMIT = "69ee59dc459d2da7cb0291930c1f944886c31d7c"         # 2026-07-31, pack version 1.6.7 - the code that was read
NEED_FREE_GB = 40
STEPS = ["space", "comfy", "venv", "torch", "reqs", "pack", "packreqs", "envpython", "isolated", "smoke"]
ENV_PYTHON = "3.11"                                               # Blender 4.2 LTS to 5.0 are built for Python 3.11
MIN_BLENDER = (4, 2)                                              # the pack says: tested against Blender 4.2 LTS and 5.x
DEFAULT_TORCH = {"torch": "2.11.0", "torchvision": "0.26.0", "torchaudio": "2.11.0", "tag": "cu128"}

DRY = False
_log_file = None
results: list[dict] = []


def say(text: str = "") -> None:
    line = time.strftime("%H:%M:%S ") + text
    print(line, flush=True)
    if _log_file:
        _log_file.write(line + "\n")
        _log_file.flush()


def run(cmd: list, cwd: Path | None = None, env: dict | None = None, timeout: int = 3600) -> tuple[int, list[str]]:
    """Run one command; every line of its output goes to the console and the log. Returns (exit code, last lines)."""
    cmd = [str(c) for c in cmd]
    say("$ " + " ".join(cmd) + (f"      [in {cwd}]" if cwd else ""))
    if DRY:
        return 0, []
    tail: collections.deque = collections.deque(maxlen=60)
    try:
        p = subprocess.Popen(cmd, cwd=str(cwd) if cwd else None, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace", bufsize=1)
    except OSError as e:
        say(f"    could not start: {e}")
        return 127, [str(e)]
    timed_out = []
    killer = threading.Timer(timeout, lambda: (timed_out.append(1), stop(p)))
    killer.daemon = True
    killer.start()
    try:
        for line in p.stdout:
            for part in line.rstrip("\r\n").split("\r"):          # progress bars redraw with carriage returns
                part = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", part).rstrip()
                if part:
                    tail.append(part)
                    say("    " + part)
        p.wait()
    finally:
        killer.cancel()
    if timed_out:
        say(f"    STOPPED: it ran longer than {timeout // 60} minutes")
        return 124, list(tail)
    return p.returncode, list(tail)


def ask(cmd: list, env: dict | None = None, cwd: Path | None = None) -> str:
    """Run a quick command quietly and return what it printed ('' on any failure)."""
    try:
        r = subprocess.run([str(c) for c in cmd], cwd=str(cwd) if cwd else None, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def marker(name: str, content: str = "") -> Path:
    return R.home / "steps" / (name + "." + hashlib.sha1(content.encode("utf-8")).hexdigest()[:10] + ".ok")


def mark(path: Path) -> None:
    if not DRY:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")


def art_comfy_facts() -> tuple[str, dict]:
    """The art ComfyUI's version and its exact PyTorch build, read from its files (it is not started or changed)."""
    art = R.root / "engines" / "ComfyUI"
    version = "0.44.0"
    try:
        m = re.search(r'__version__\s*=\s*"([^"]+)"', (art / "comfyui_version.py").read_text(encoding="utf-8"))
        version = m.group(1) if m else version
    except OSError:
        pass
    torch = dict(DEFAULT_TORCH)
    for sp in list(art.glob("venv/Lib/site-packages")) + list(art.glob("venv/lib/python*/site-packages")):
        for name in ("torch", "torchvision", "torchaudio"):
            for d in sp.glob(name + "-*.dist-info"):
                m = re.match(re.escape(name) + r"-([0-9][^+]*)(?:\+(\w+))?\.dist-info$", d.name)
                if m:
                    torch[name] = m.group(1)
                    if name == "torch" and m.group(2):
                        torch["tag"] = m.group(2)
    return version, torch


# ---------------------------------------------------------------------------------------------------------- steps

def step_space(_a) -> tuple[bool, str]:
    free = shutil.disk_usage(R.root).free / 2**30
    if free < NEED_FREE_GB:
        return False, f"only {free:.0f} GB free on this drive; this wants {NEED_FREE_GB} GB to be safe"
    if not shutil.which("git"):
        return False, "git is not installed (https://git-scm.com/download/win)"
    return True, f"{free:.0f} GB free; git found"


def step_comfy(a) -> tuple[bool, str]:
    if (R.rig / "main.py").exists():
        return True, "already there"
    if R.rig.exists() and any(R.rig.iterdir()) and not DRY:
        aside = R.rig.with_name(f"rig_incomplete_{time.strftime('%Y%m%d_%H%M%S')}")
        R.rig.rename(aside)
        say(f"    an unfinished engines\\rig was moved aside to {aside.name}")
    code, tail = run(["git", "-c", "advice.detachedHead=false", "clone", "--depth", "1", "--branch", "v" + a["comfy_version"],
                      COMFY_REPO, R.rig], timeout=1800)
    return code == 0, f"ComfyUI v{a['comfy_version']}" if code == 0 else "git clone failed"


def step_venv(_a) -> tuple[bool, str]:
    if R.rig_python.exists():
        return True, "already there"
    base = Path(sys.base_prefix) / ("python.exe" if WIN else "bin/python3")
    code, _ = run([base, "-m", "venv", R.rig / "venv"], timeout=900)
    if code != 0:
        return False, f"could not create the environment with {base}"
    code, _ = run([R.rig_python, "-m", "pip", "install", "--upgrade", "pip"], env=R.rig_env(), timeout=900)
    return code == 0, f"Python {sys.version_info.major}.{sys.version_info.minor} from {base}"


def torch_now() -> str:
    return ask([R.rig_python, "-c", "import torch; print(torch.__version__)"], env=R.rig_env()) if R.rig_python.exists() else ""


def step_torch(a) -> tuple[bool, str]:
    t = a["torch"]
    want = f"{t['torch']}+{t['tag']}"
    have = torch_now()
    if have and (have == want or a["torch_index"]):
        return True, f"already there ({have})"
    index = a["torch_index"] or f"https://download.pytorch.org/whl/{t['tag']}"
    code, _ = run([R.rig_python, "-m", "pip", "install", f"torch=={t['torch']}", f"torchvision=={t['torchvision']}",
                   f"torchaudio=={t['torchaudio']}", "--index-url", index], env=R.rig_env(), timeout=7200)
    have = torch_now() if not DRY else want
    return code == 0 and bool(have), f"PyTorch {have}" if code == 0 else "pip could not install PyTorch"


def step_reqs(_a) -> tuple[bool, str]:
    req = R.rig / "requirements.txt"
    done = marker("comfy_requirements", req.read_text(encoding="utf-8") if req.exists() else "")
    if done.exists():
        return True, "already there"
    code, _ = run([R.rig_python, "-m", "pip", "install", "-r", req], cwd=R.rig, env=R.rig_env(), timeout=7200)
    if code == 0:
        mark(done)
    return code == 0, "installed" if code == 0 else "pip failed on ComfyUI's requirements"


def step_pack(_a) -> tuple[bool, str]:
    if not (R.pack / "nodes").exists():
        code, _ = run(["git", "clone", PACK_REPO, R.pack], timeout=1800)
        if code != 0:
            return False, "git clone of the node pack failed"
    head = ask(["git", "-C", R.pack, "rev-parse", "HEAD"])
    if head != PACK_COMMIT:
        code, _ = run(["git", "-C", R.pack, "-c", "advice.detachedHead=false", "checkout", PACK_COMMIT], timeout=600)
        if code != 0:
            run(["git", "-C", R.pack, "fetch", "origin"], timeout=1800)
            code, _ = run(["git", "-C", R.pack, "-c", "advice.detachedHead=false", "checkout", PACK_COMMIT], timeout=600)
        if code != 0:
            return False, f"could not check out {PACK_COMMIT[:10]}"
    return True, f"ComfyUI-UniRig at {PACK_COMMIT[:10]}"


def step_packreqs(_a) -> tuple[bool, str]:
    req = R.pack / "requirements.txt"
    done = marker("pack_requirements", req.read_text(encoding="utf-8") if req.exists() else "")
    if done.exists():
        return True, "already there"
    before = torch_now()
    code, _ = run([R.rig_python, "-m", "pip", "install", "-r", req, "--upgrade"], cwd=R.pack, env=R.rig_env(), timeout=3600)
    after = torch_now()
    note = "installed"
    if before and after != before:
        note = f"installed - WARNING: PyTorch changed from {before} to {after or 'not importable'}"
        say("    " + note)
    if code == 0:
        mark(done)
    return code == 0, note if code == 0 else "pip failed on the pack's requirements"


def env_toml() -> Path:
    return R.pack / "nodes" / "comfy-env.toml"


def step_envpython(_a) -> tuple[bool, str]:
    """Pin the isolated environment's Python in the pack's own comfy-env.toml (its top-level `python` key)."""
    path = env_toml()
    if not path.exists():
        return DRY, "the pack's nodes\\comfy-env.toml is not there"
    text = path.read_text(encoding="utf-8")
    head = text.split("\n[", 1)[0] if not text.startswith("[") else ""
    m = re.search(r'(?m)^python\s*=\s*"([^"]+)"', head)
    if m and m.group(1) == ENV_PYTHON:
        return True, f"already Python {ENV_PYTHON}"
    if m:
        text = re.sub(r'(?m)^python\s*=\s*"[^"]+"[^\n]*\n', "", text, count=1)
    note = ("# Added by the forge's rig_install.py: the isolated environment's own Python. Without this line it copies\n"
            "# ComfyUI's Python; on 3.10 that means Blender 3.6 as the module, which this pack's nodes do not load on.\n")
    if not DRY:
        path.write_text(note + f'python = "{ENV_PYTHON}"\n\n' + text, encoding="utf-8")
    return True, f"isolated environment set to Python {ENV_PYTHON} (was: {m.group(1) if m else 'the same as ComfyUI'})"


def env_versions() -> dict:
    """What the finished isolated environment holds: its Python and its Blender module, read from conda's records."""
    out = {}
    for meta in (R.envs / "envs").glob("*/.pixi/envs/default/conda-meta"):
        for name in ("python", "bpy"):
            for f in meta.glob(name + "-[0-9]*.json"):
                out[name] = f.name[len(name) + 1:].split("-")[0]
    return out


def env_dirs() -> list[Path]:
    return [p for p in (R.envs / "envs").glob("*/.pixi/envs/default") if p.is_dir()]


def stale_packages() -> dict:
    """Packages inside an isolated environment that were built for a different Python than the environment's own.

    A wheel records what it was built for in <name>.dist-info/WHEEL ("Tag: cp310-cp310-win_amd64"). On Windows every
    Python version shares one Lib\\site-packages, so when an environment's Python is changed in place a package whose
    version did not change is left as it was - built for the old Python, unloadable by the new one.
    """
    out: dict[str, str] = {}
    for env in env_dirs():
        py = None
        for f in (env / "conda-meta").glob("python-3.*.json"):
            m = re.match(r"python-3\.(\d+)\.", f.name)
            py = f"cp3{m.group(1)}" if m else py
        if not py:
            continue
        sps = [env / "Lib" / "site-packages"] + list(env.glob("lib/python3.*/site-packages"))
        for sp in sps:
            if not sp.is_dir():
                continue
            for wheel in sp.glob("*.dist-info/WHEEL"):
                try:
                    tags = re.findall(r"(?m)^Tag:\s*(\S+)", wheel.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    continue
                built = {t.split("-")[1] for t in tags if t.count("-") >= 2 and re.fullmatch(r"cp3\d+t?", t.split("-")[1])}
                if built and py not in built:
                    out[wheel.parent.name[:-len(".dist-info")]] = f"{sorted(built)[0]} in a {py} environment"
    return out


def clean_envs() -> None:
    """Throw the isolated environments away so the next install builds them from nothing (they are this installer's
    own build, a few minutes old, and everything in them is downloaded again from the caches on this drive)."""
    for env in env_dirs():
        aside = env.with_name(f"default_stale_{time.strftime('%H%M%S')}")
        env.rename(aside)
        say(f"    removing the old environment ({aside.parent.parent.parent.name}) ...")
        try:
            shutil.rmtree(("\\\\?\\" + str(aside)) if WIN else str(aside))
        except OSError as e:
            say(f"    could not remove all of {aside} ({e}); it is not used any more and can be deleted by hand")
    stamp = R.envs / "install.hash"                                # without this comfy-env says "nothing changed" and skips
    if stamp.exists():
        stamp.unlink()


def step_isolated(_a) -> tuple[bool, str]:
    toml_text = env_toml().read_text(encoding="utf-8") if env_toml().exists() else ""
    done = marker("isolated_env", PACK_COMMIT + toml_text)
    stale = {} if DRY else stale_packages()
    if done.exists() and not stale:
        return True, "already there"
    if stale:
        say(f"    {len(stale)} package(s) in the environment were built for another Python: "
            + ", ".join(f"{k} ({v})" for k, v in sorted(stale.items())[:8]) + (" ..." if len(stale) > 8 else ""))
        say("    the environment is thrown away and built fresh")
        clean_envs()
    say("    This is the long step: it downloads pixi, Blender as a Python module and the GPU packages.")
    code, tail = run([R.rig_python, "install.py"], cwd=R.pack, env=R.rig_env({"COMFY_ENV_DEBUG_INSTALL": "1"}), timeout=4 * 3600)
    envs = sorted(p.name for p in (R.envs / "envs").glob("*") if (p / ".pixi" / "envs" / "default").is_dir())
    say(f"    finished environments in engines\\rig\\ce\\envs: {envs or 'none'}")
    ok = code == 0 and bool(envs)
    if not ok:
        return False, "install.py failed" if code else "install.py ended without making an environment"
    v = env_versions()
    say(f"    the environment holds Python {v.get('python', '?')} and Blender {v.get('bpy', '?')} as a module")
    try:
        blender = tuple(int(x) for x in v.get("bpy", "0.0").split(".")[:2])
    except ValueError:
        blender = (0, 0)
    if blender < MIN_BLENDER and not DRY:
        return False, (f"the environment got Blender {v.get('bpy', '?')}; the pack needs {MIN_BLENDER[0]}.{MIN_BLENDER[1]} or later "
                       f"(its Python is {v.get('python', '?')})")
    stale = {} if DRY else stale_packages()
    if stale:
        return False, "after a fresh build these are still built for another Python: " + ", ".join(f"{k} ({v})" for k, v in sorted(stale.items())[:8])
    mark(done)
    return True, f"{', '.join(envs)}: Python {v.get('python', '?')}, Blender {v.get('bpy', '?')}"


def step_smoke(_a) -> tuple[bool, str]:
    if DRY:
        return True, "dry run"
    if R.is_up():
        return False, f"something is already answering on port {R.port}; close it and run this again"
    log_path = OUT / "comfy_first_start.log"
    say(f"    starting the rigging ComfyUI on the processor only; its console goes to {log_path}")
    start_mark = f"==== smoke {time.strftime('%Y-%m-%d %H:%M:%S')} ===="
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as lf:
        lf.write("\n" + start_mark + "\n")
    # the node scan prints only its last ten lines when it fails; these two make it print everything
    proc = R.start_comfy(log_path, cpu=True, extra_env={"COMFY_ENV_DEBUG_META": "1", "COMFY_ENV_DEBUG_STACKTRACE": "1"})
    info: dict = {}
    mine: dict = {}
    try:
        t0 = time.time()
        while time.time() - t0 < 25 * 60:
            if proc.poll() is not None:
                return False, f"ComfyUI stopped by itself (exit {proc.returncode}); read out\\3d\\_install\\comfy_first_start.log"
            if R.is_up():
                break
            time.sleep(5)
        else:
            return False, "ComfyUI did not answer within 25 minutes"
        say(f"    it answers after {time.time() - t0:.0f} s; asking what its nodes take ...")
        with urllib.request.urlopen(R.url + "/object_info", timeout=300) as r:
            info = json.loads(r.read().decode("utf-8"))
        mine = {k: v for k, v in info.items() if k.startswith(("UniRig", "MIA")) or "unirig" in str(v.get("category", "")).lower()}
        (OUT / "object_info_rig.json").write_text(json.dumps(mine, indent=1, ensure_ascii=False), encoding="utf-8")
        (OUT / "object_info_names.txt").write_text("\n".join(sorted(info)), encoding="utf-8")
    finally:
        stop(proc)
    text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    text = text.split(start_mark)[-1]
    for ln in text.splitlines():
        if "IMPORT FAILED" in ln:
            say("    " + ln.strip())
    need = {"MIAAutoRig", "UniRigAutoRig", "UniRigLoadMesh", "UniRigApplyAnimation"}
    missing = sorted(need - set(mine))
    if missing:
        # the reason is whatever the node scan printed: show the part that matters here, the whole of it is in the log
        scan = [ln for ln in text.splitlines() if ln.startswith("[comfy-env]")]
        errors = [k for k, ln in enumerate(scan) if "Traceback" in ln or "Error" in ln]
        errors = [k for k in errors if "unregister()" not in scan[max(k - 1, 0)] and "_OpNamespace" not in scan[k] and "_ClassNamespace" not in scan[k]]
        if errors:
            say("    what the node scan said (Blender's own shutdown noise left out):")
            for ln in scan[max(errors[0] - 3, 0):errors[0] + 45]:
                say("      " + ln[:300])
        return False, f"it starts ({len(info)} kinds of node) but these rigging nodes are missing: {', '.join(missing)}"
    return True, f"{len(info)} kinds of node, {len(mine)} of them rigging nodes"


FUNCS = {"space": step_space, "comfy": step_comfy, "venv": step_venv, "torch": step_torch, "reqs": step_reqs,
         "pack": step_pack, "packreqs": step_packreqs, "envpython": step_envpython, "isolated": step_isolated,
         "smoke": step_smoke}


def main(argv: list[str], cfg: dict | None = None) -> int:
    global DRY, _log_file, R, OUT
    R = from_cfg(cfg)
    OUT = out_root(cfg, R.root) / "_install"
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    opt = {"--skip": "", "--only": "", "--torch-index": ""}
    for k in list(opt):
        if k in argv and argv.index(k) + 1 < len(argv):
            opt[k] = argv[argv.index(k) + 1]
    DRY = "--dry-run" in argv
    skip = {s for s in opt["--skip"].split(",") if s}
    only = {s for s in opt["--only"].split(",") if s}
    OUT.mkdir(parents=True, exist_ok=True)
    _log_file = open(OUT / "install.log", "a", encoding="utf-8", errors="replace")
    version, torch = art_comfy_facts()
    a = {"comfy_version": version, "torch": torch, "torch_index": opt["--torch-index"]}
    say("=" * 100)
    say(f"Rigging ComfyUI install{' (DRY RUN)' if DRY else ''}: {R.rig}")
    say(f"mirrors the art ComfyUI: v{version}, PyTorch {torch['torch']}+{torch['tag']}; pack commit {PACK_COMMIT[:10]}")
    say(f"everything stays under {R.rig} (home {R.home.name}, environments {R.envs.name}); logs in {OUT}")
    t_all = time.time()
    failed = None
    for name in STEPS:
        if name in skip or (only and name not in only):
            results.append({"step": name, "ok": None, "note": "not asked for", "seconds": 0})
            continue
        say("")
        say(f"---- {name} ----")
        t0 = time.time()
        try:
            ok, note = FUNCS[name](a)
        except Exception as e:  # a step must never take the report down with it
            import traceback
            for ln in traceback.format_exc().splitlines():
                say("    " + ln)
            ok, note = False, f"{type(e).__name__}: {e}"
        results.append({"step": name, "ok": ok, "note": note, "seconds": round(time.time() - t0)})
        say(f"---- {name}: {'OK' if ok else 'FAILED'} - {note} ({time.time() - t0:.0f} s)")
        if not ok:
            failed = name
            break
    free = shutil.disk_usage(R.root).free / 2**30
    lines = [f"Rigging ComfyUI install, {time.strftime('%Y-%m-%d %H:%M')}: "
             + ("ALL STEPS OK" if not failed else f"STOPPED AT '{failed}'") + f"  ({(time.time() - t_all) / 60:.0f} min, {free:.0f} GB free now)", ""]
    for r in results:
        state = {True: "ok    ", False: "FAILED", None: "-     "}[r["ok"]]
        lines.append(f"  {state} {r['step']:<9} {r['note']}" + (f"  ({r['seconds']} s)" if r["seconds"] else ""))
    lines += ["", "Full log: out\\3d\\_install\\install.log" + ("" if not failed else "   - the reason is in its last lines"),
              "Safe to run again: finished steps are skipped."]
    report = "\n".join(lines)
    if not DRY:
        (OUT / "INSTALL_REPORT.txt").write_text(report + "\n", encoding="utf-8")
        (OUT / "install_state.json").write_text(json.dumps({"results": results, "comfy_version": version, "torch": torch,
                                                              "pack_commit": PACK_COMMIT}, indent=1), encoding="utf-8")
    say("")
    for ln in lines:
        say(ln)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))


# ---------------------------------------------------------------------------------------------- the check (starts nothing)
def _template_files() -> list[tuple[str, str]]:
    """(loader kind, file name) for every model file the image-to-3D template loads."""
    from . import template
    wf = template.load()
    kinds = {"UNETLoader": "diffusion_models", "VAELoader": "vae", "CLIPVisionLoader": "clip_vision",
             "LoadBackgroundRemovalModel": "background_removal", "LoadMoGeModel": "geometry_estimation"}
    out = []
    for n in wf["nodes"]:
        if n["type"] in kinds and n.get("widgets_values"):
            out.append((kinds[n["type"]], str(n["widgets_values"][0])))
    return sorted(set(out))


def _find(names: set[str], dirs: list[Path], max_depth: int = 4) -> dict[str, str]:
    """Where each named file is under the given folders (a shallow walk; big folders are not read twice)."""
    import os
    found: dict[str, str] = {}
    for d in dirs:
        if not d.is_dir():
            continue
        base = len(d.parts)
        for cur, subs, files in os.walk(d):
            if len(Path(cur).parts) - base >= max_depth:
                subs[:] = []
            for f in files:
                if f in names and f not in found:
                    found[f] = str(Path(cur) / f)
            if len(found) == len(names):
                return found
    return found


def check(cfg: dict | None = None) -> dict:
    """Settings -> 3D tools -> Check: what is installed, what is missing, what to do. Starts nothing, changes nothing."""
    import os
    env = from_cfg(cfg)
    root = env.root
    items: list[dict] = []

    def item(what: str, ok, detail: str = "", fix: str = ""):
        items.append({"what": what, "ok": ok, "detail": detail, "fix": fix})

    item("the rigging ComfyUI (engines/rig)", (env.rig / "main.py").exists(), str(env.rig),
         "Install (it puts a second ComfyUI beside the art one; about 40 GB of room wanted)")
    item("its own Python", env.rig_python.exists(), str(env.rig_python), "Install")
    head = _git_head(env.pack)
    item("the ComfyUI-UniRig node pack", (env.pack / "nodes").exists(),
         ("at " + head[:10] + (" (the commit the forge was written for)" if head.startswith(PACK_COMMIT[:10]) else "")) if head else "",
         "Install")
    v = env_versions_of(env)
    item("Blender inside the rigging environment", env.env_python.exists(),
         f"Python {v.get('python', '?')}, Blender {v.get('bpy', '?')}" if env.env_python.exists() else str(env.env_python),
         "Install (the 'isolated' step)" if not env.blender_exe else "")
    if env.blender_exe:
        item("a Blender program (forge.json threed.blender_exe)", Path(env.blender_exe).exists(), env.blender_exe, "fix the path")
    # the art ComfyUI's image-to-3D model files
    comfy_models = root / "engines" / "ComfyUI" / "models"
    dirs = [comfy_models]
    try:
        from .. import config as cfgmod
        for k in ("diffusion_models", "vae", "checkpoints", "text_encoders", "clip"):
            dirs += cfgmod.model_dirs(cfg or {}, k)
    except Exception:  # noqa: BLE001
        pass
    files = _template_files()
    where = _find({f for _, f in files}, dirs)
    for kind, f in files:
        use = "Pixal3D" if "pixal3d" in f or "moge" in f else "TRELLIS.2" if "trellis" in f else "both"
        item(f"model file {f} ({use})", f in where, where.get(f, f"not under {comfy_models}/{kind}"),
             "the art ComfyUI downloads it the first time the template runs, or put it in that folder")
    flux = ((cfg or {}).get("comfy") or {}).get("flux2") or {}
    fx = {"flux-2-klein-4b.safetensors", flux.get("text_encoder") or "qwen_3_4b.safetensors", flux.get("vae") or "flux2-vae.safetensors"}
    fw = _find(fx, dirs)
    for f in sorted(fx):
        item(f"picture model file {f} (FLUX.2 klein)", f in fw, fw.get(f, "not found in the model folders"), "pull_flux.bat")
    from . import motions
    lib, trav = motions.library_paths(cfg, root)
    item("the motion library", lib.exists(), str(lib), "unzip the Quaternius Universal Animation Library into local/libraries/quaternius_ual")
    item("the motion library's root-motion file (speeds)", bool(trav), str(trav or ""), "it is in the same download")
    # the installer's defaults would put gigabytes in the user profile: say so if a past run did
    la = os.environ.get("LOCALAPPDATA", "")
    stray = Path(la) / "Programs" / "comfy-env" if la else None
    if stray is not None:
        item("nothing in the user profile", not stray.exists(),
             f"{stray} exists - left by a run without the forge's settings" if stray.exists() else "",
             "it can be deleted by hand once the rigging ComfyUI works from engines/rig")
    try:
        import shutil
        free = shutil.disk_usage(root).free / 2**30
        item("free room on the forge's drive", free >= 20, f"{free:.0f} GB free", "make room: models and environments are big")
    except OSError:
        pass
    state, report = {}, ""
    for d in (out_root(cfg, root) / "_install", root / "out" / "rig_test"):
        if (d / "install_state.json").exists():
            try:
                state = json.loads((d / "install_state.json").read_text(encoding="utf-8"))
                report = (d / "INSTALL_REPORT.txt").read_text(encoding="utf-8") if (d / "INSTALL_REPORT.txt").exists() else ""
            except (OSError, ValueError):
                pass
            break
    ok = all(i["ok"] for i in items if i["ok"] is not None)
    return {"ok": ok, "items": items, "last_install": report, "state": state, "rig": str(env.rig), "port": env.port,
            "blender": str(env.env_python) if env.env_python.exists() else (env.blender_exe or "")}


def _git_head(repo: Path) -> str:
    """The commit a checkout is at, read from its files (no git needed): a detached HEAD, or the branch it points at."""
    g = repo / ".git"
    try:
        head = (g / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if not head.startswith("ref:"):
        return head
    ref = head[4:].strip()
    try:
        return (g / ref).read_text(encoding="utf-8").strip()
    except OSError:
        pass
    try:
        for line in (g / "packed-refs").read_text(encoding="utf-8").splitlines():
            if line.endswith(" " + ref):
                return line.split()[0]
    except OSError:
        pass
    return ""


def env_versions_of(env: RigEnv) -> dict:
    out = {}
    for meta in (env.envs / "envs").glob("*/.pixi/envs/default/conda-meta"):
        for name in ("python", "bpy"):
            for f in meta.glob(name + "-[0-9]*.json"):
                out[name] = f.name[len(name) + 1:].split("-")[0]
    return out


def doctor_lines(cfg: dict | None = None) -> list[str]:
    """doctor's 3D section: versions, files, free room."""
    c = check(cfg)
    lines = ["3D workshop (BUILD 36):"]
    for i in c["items"]:
        lines.append(("  ✓ " if i["ok"] else "  ✗ ") + i["what"] + (f" — {i['detail']}" if i["detail"] else "")
                     + ("" if i["ok"] or not i["fix"] else f"  → {i['fix']}"))
    return lines
