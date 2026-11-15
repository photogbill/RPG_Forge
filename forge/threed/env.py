"""The rigging ComfyUI: where it lives, and the environment every one of its processes runs in.

A second ComfyUI (`engines/rig`, port 8189) with its own Python environment, so nothing installed for rigging can break
the ComfyUI the art runs on (`engines/ComfyUI`, port 8188). Copied from the first game's rig_env.py (2026-11-12/13),
where it was proven; nothing here names a game.

Everything it downloads, builds or caches stays on the forge's own drive, inside engines/rig. Left alone, the node
pack's installer (comfy-env 0.4.1) puts its multi-gigabyte environment in %LOCALAPPDATA%\\Programs\\comfy-env, the pixi
program in the user profile, and pip / uv / Hugging Face caches under the user profile too. `rig_env()` moves all of
them: COMFY_ENV_ROOT for the environment, the tools' own cache settings, and a stand-in home folder for the rest.

Settings (all optional) come from forge.json -> "threed": {"rig_root": "engines/rig", "rig_port": 8189,
"blender_exe": "<a Blender program, used for the Blender steps when the rigging environment's Blender is missing>"}.
Tests point `RigEnv` at a temporary folder and a stand-in ComfyUI (`command`), so nothing real is touched.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

WIN = sys.platform == "win32"
DEFAULT_PORT = 8189


def forge_root() -> Path:
    return Path(__file__).resolve().parents[2]


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if WIN else "bin/python")


class RigEnv:
    """Paths and processes of one rigging ComfyUI. `command` replaces the start command (the stand-in, in tests)."""

    def __init__(self, root: Path | None = None, rig: Path | None = None, port: int = DEFAULT_PORT,
                 command: list[str] | None = None, blender_exe: str | None = None, out: Path | None = None):
        self.root = Path(root or forge_root())
        self.rig = Path(rig) if rig else self.root / "engines" / "rig"
        self.home = self.rig / "_home"                     # its stand-in home folder (caches, pixi, temp files)
        self.envs = self.rig / "ce"                        # comfy-env's workspace (the isolated environment lives here)
        self.pack = self.rig / "custom_nodes" / "ComfyUI-UniRig"
        self.port = int(port)
        self.url = f"http://127.0.0.1:{self.port}"
        self.rig_python = venv_python(self.rig / "venv")
        self.command = list(command) if command else None
        self.blender_exe = blender_exe or ""
        self.out = Path(out) if out else self.root / "out" / "3d" / "_rig"     # its own logs (never out/rig_test)

    # ------------------------------------------------------------------ where things are
    @property
    def input_dir(self) -> Path:
        return self.rig / "input"

    @property
    def output_dir(self) -> Path:
        return self.rig / "output"

    @property
    def env_python(self) -> Path:
        """The Python that has Blender inside it: the rigging tools' own isolated environment."""
        return self.envs / "envs" / "unirig-nodes" / ".pixi" / "envs" / "default" / ("python.exe" if WIN else "bin/python")

    def installed(self) -> bool:
        return self.command is not None or self.rig_python.exists()

    def metadata_caches(self) -> list[Path]:
        """The pack reads its list of meshes once and caches it; dropping these makes it look again."""
        return list((self.envs / "envs").glob("*/.pixi/envs/default/.metadata_cache.pkl"))

    # ------------------------------------------------------------------ environments
    def rig_env(self, extra: dict | None = None) -> dict:
        """The environment for every process of the rigging ComfyUI. Creates the folders it names."""
        home = self.home
        cache = home / "cache"
        e = dict(os.environ)
        e.update({
            "COMFY_ENV_ROOT": str(self.envs),
            "USERPROFILE": str(home), "HOME": str(home),
            "APPDATA": str(home / "AppData" / "Roaming"),
            "LOCALAPPDATA": str(home / "AppData" / "Local"),
            "TEMP": str(home / "tmp"), "TMP": str(home / "tmp"),
            "PIXI_HOME": str(home / ".pixi"),
            "PIXI_CACHE_DIR": str(cache / "pixi"),
            "RATTLER_CACHE_DIR": str(cache / "rattler"),
            "UV_CACHE_DIR": str(cache / "uv"),
            "PIP_CACHE_DIR": str(cache / "pip"),
            "HF_HOME": str(cache / "huggingface"),
            "TORCH_HOME": str(cache / "torch"),
            "XDG_CACHE_HOME": str(cache),
            "PYTHONNOUSERSITE": "1", "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        })
        for k in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV"):
            e.pop(k, None)                                     # nothing of the forge's own environment leaks in
        # 'python' and 'pip' by name must mean the rigging ComfyUI's, never the forge's or the art ComfyUI's
        own = str(self.rig_python.parent)
        others = {str((self.root / "venv" / ("Scripts" if WIN else "bin")).resolve()).lower(),
                  str((self.root / "engines" / "ComfyUI" / "venv" / ("Scripts" if WIN else "bin")).resolve()).lower()}
        kept = [p for p in e.get("PATH", "").split(os.pathsep) if p and str(Path(p)).lower() not in others and p != own]
        e["PATH"] = os.pathsep.join([own] + kept)
        for k in ("USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "PIXI_HOME", "PIXI_CACHE_DIR", "RATTLER_CACHE_DIR",
                  "UV_CACHE_DIR", "PIP_CACHE_DIR", "HF_HOME", "TORCH_HOME", "COMFY_ENV_ROOT"):
            Path(e[k]).mkdir(parents=True, exist_ok=True)
        if extra:
            e.update(extra)
        return e

    def blender_env(self) -> dict:
        """The rigging tools' environment, with the isolated Python's own folders first on the path (it is started
        directly, not through the node pack, so nothing else has put them there)."""
        env = self.rig_env()
        py = self.env_python
        base = py.parent if WIN else py.parent.parent
        first = [base, base / "Library" / "mingw-w64" / "bin", base / "Library" / "usr" / "bin", base / "Library" / "bin",
                 base / "Scripts", base / "bin"]
        env["PATH"] = os.pathsep.join([str(d) for d in first if d.exists()] + [env.get("PATH", "")])
        return env

    def blender_command(self, script: Path, args: list[str]) -> tuple[list[str], dict] | None:
        """How to run one of the forge's Blender scripts here: the rigging environment's Python (Blender as a module),
        else a Blender program (forge.json threed.blender_exe) in the background. None when there is neither."""
        if self.env_python.exists():
            return [str(self.env_python), str(script)] + [str(a) for a in args], self.blender_env()
        if self.blender_exe and Path(self.blender_exe).exists():
            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8"
            return [self.blender_exe, "--background", "--factory-startup", "--python", str(script), "--"] + [str(a) for a in args], env
        return None

    # ------------------------------------------------------------------ the process
    def is_up(self, timeout: float = 5.0) -> bool:
        try:
            with urllib.request.urlopen(self.url + "/system_stats", timeout=timeout) as r:
                return r.status == 200
        except Exception:
            return False

    def start_comfy(self, log_path: Path, cpu: bool = False, extra_env: dict | None = None) -> subprocess.Popen:
        """Start the rigging ComfyUI; its whole console goes to log_path. cpu=True touches no graphics memory."""
        if self.command:
            cmd, cwd, env = list(self.command), str(self.root), dict(os.environ)
            if extra_env:
                env.update(extra_env)
        else:
            cmd = [str(self.rig_python), "main.py", "--listen", "127.0.0.1", "--port", str(self.port), "--disable-auto-launch"]
            if cpu:
                cmd.append("--cpu")
            cwd, env = str(self.rig), self.rig_env(extra_env)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        f = open(log_path, "a", encoding="utf-8", errors="replace")
        f.write(f"\n==== {time.strftime('%Y-%m-%d %H:%M:%S')} starting: {' '.join(cmd)}\n")
        f.flush()
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if WIN else 0
        return subprocess.Popen(cmd, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT, creationflags=flags)


def stop(proc: subprocess.Popen) -> None:
    """Stop a process and everything it started."""
    if proc.poll() is not None:
        return
    if WIN:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        proc.terminate()
    try:
        proc.wait(timeout=30)
    except Exception:
        proc.kill()


def settings(cfg: dict | None) -> dict:
    """forge.json -> "threed" (optional), with the defaults filled in."""
    t = dict((cfg or {}).get("threed") or {})
    t.setdefault("rig_root", "engines/rig")
    t.setdefault("rig_port", DEFAULT_PORT)
    t.setdefault("blender_exe", "")
    return t


def from_cfg(cfg: dict | None, root: Path | None = None) -> RigEnv:
    """The rigging ComfyUI this forge is set up for."""
    root = Path(root or (cfg or {}).get("_root") or forge_root())
    t = settings(cfg)
    rig = Path(t["rig_root"])
    rig = rig if rig.is_absolute() else root / rig
    cmd = t.get("rig_command")                     # tests only: a stand-in in place of the real rigging ComfyUI
    out = Path(t["out_root"]) / "_rig" if t.get("out_root") else None
    return RigEnv(root=root, rig=rig, port=int(t["rig_port"]), command=cmd, blender_exe=t.get("blender_exe") or "", out=out)


def out_root(cfg: dict | None, root: Path | None = None) -> Path:
    """Where the workshop writes: out/3d/ (forge.json threed.out_root may move it; tests do)."""
    t = settings(cfg)
    if t.get("out_root"):
        return Path(t["out_root"])
    root = Path(root or (cfg or {}).get("_root") or forge_root())
    try:
        from .. import config as cfgmod
        return cfgmod.path_of(cfg, "out") / "3d" if cfg and cfg.get("paths") else root / "out" / "3d"
    except Exception:  # noqa: BLE001 — a cfg without paths (tests): beside the forge
        return root / "out" / "3d"


BLENDER_SCRIPTS = Path(__file__).resolve().parent / "blender"


def run_blender(env: RigEnv, script: str, args: list, minutes: float = 20, log=None, python: str | None = None) -> tuple[int, list[str]]:
    """Run one of the forge's Blender scripts (forge/threed/blender/<script>) and pass on every line it prints.
    Returns (exit code, its lines); -1 when it was stopped for taking longer than `minutes`, -2 when there is no Blender.
    `python` names a Python with Blender inside it to use instead (tests)."""
    import threading
    path = BLENDER_SCRIPTS / script
    if python:                                             # a Python with Blender inside (or, in tests, a stand-in for one)
        pre = [str(x) for x in python] if isinstance(python, (list, tuple)) else [str(python)]
        cmd, e = pre + [str(path)] + [str(a) for a in args], dict(os.environ)
    else:
        how = env.blender_command(path, args)
        if how is None:
            return -2, [f"no Blender here: neither the rigging environment's ({env.env_python}) nor a Blender program "
                        "(forge.json threed.blender_exe)"]
        cmd, e = how
    e["PYTHONIOENCODING"] = "utf-8"
    e["PYTHONUNBUFFERED"] = "1"
    lines: list[str] = []
    try:
        proc = subprocess.Popen(cmd, cwd=str(env.root) if env.root.is_dir() else None, env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
    except Exception as ex:  # noqa: BLE001
        return -2, [f"could not start Blender: {ex}"]
    late = {"hit": False}

    def too_long() -> None:
        late["hit"] = True
        stop(proc)

    guard = threading.Timer(minutes * 60, too_long)
    guard.daemon = True
    guard.start()
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                lines.append(line)
                if log and not line.startswith(("Fra:", "Info:")):
                    log.info("   | %s", line[:400])
        code = proc.wait()
    finally:
        guard.cancel()
    return (-1 if late["hit"] else code), lines
