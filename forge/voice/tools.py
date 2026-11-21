"""Where the voice bench's tools live, how they run, and whether they are there (BUILD 71 part 4).

  tools/rhubarb/            Rhubarb Lip Sync, one pinned release (MIT), fetched by get_rhubarb.bat / .command
  engines/voice/whisper/    faster-whisper and the large-v3 weights, in their own environment (get_whisper.bat)
  engines/voice/<engine>/   a voice engine, each in its own environment
  engines/voice/_home/      every tool's home, cache and temp folder — nothing is written outside the forge's folder
  logs/voice/<day>.log      every run, its settings, device, seconds and result
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path

from .. import config as cfgmod

RHUBARB_VERSION = "1.14.0"
RHUBARB_URLS = {   # the project's own release page (MIT); confirm on the page before a new version is pinned
    "Windows": f"https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v{RHUBARB_VERSION}/Rhubarb-Lip-Sync-{RHUBARB_VERSION}-Windows.zip",
    "Darwin": f"https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v{RHUBARB_VERSION}/Rhubarb-Lip-Sync-{RHUBARB_VERSION}-macOS.zip",
    "Linux": f"https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v{RHUBARB_VERSION}/Rhubarb-Lip-Sync-{RHUBARB_VERSION}-Linux.zip",
}


def home() -> Path:
    h = cfgmod.ROOT / "engines" / "voice" / "_home"
    h.mkdir(parents=True, exist_ok=True)
    return h


def tool_env() -> dict:
    """An environment whose home, caches and temp folder are inside the forge's folder."""
    h = home()
    e = dict(os.environ)
    for k in ("HOME", "USERPROFILE", "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "TEMP", "TMP", "TMPDIR",
              "HF_HOME", "HUGGINGFACE_HUB_CACHE", "TORCH_HOME", "APPDATA", "LOCALAPPDATA"):
        e[k] = str(h / k.lower())
        Path(e[k]).mkdir(parents=True, exist_ok=True)
    return e


def log(entry: dict) -> None:
    d = cfgmod.ROOT / "logs" / "voice"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{time.strftime('%Y-%m-%d')}.log", "a", encoding="utf-8") as f:
        f.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"), **entry}, ensure_ascii=False) + "\n")


def rhubarb_exe(cfg: dict | None = None) -> Path | None:
    base = cfgmod.ROOT / "tools" / "rhubarb"
    if not base.exists():
        return None
    for name in ("rhubarb.exe", "rhubarb"):
        for p in base.rglob(name):
            if p.is_file():
                return p
    return None


def whisper_home(cfg: dict | None = None) -> Path:
    return cfgmod.ROOT / "engines" / "voice" / "whisper"


def whisper_python(cfg: dict | None = None) -> Path | None:
    h = whisper_home(cfg) / "venv"
    for p in (h / "Scripts" / "python.exe", h / "bin" / "python"):
        if p.exists():
            return p
    return None


def whisper_ready(cfg: dict | None = None) -> bool:
    return whisper_python(cfg) is not None and (whisper_home(cfg) / "READY").exists()


def engines_dir() -> Path:
    return cfgmod.ROOT / "engines" / "voice"


def need(cfg: dict, which: str) -> tuple[bool, str]:
    if which == "rhubarb":
        p = rhubarb_exe(cfg)
        return (p is not None, str(p) if p else "tools/rhubarb — get_rhubarb.bat")
    if which == "whisper":
        return (whisper_ready(cfg), str(whisper_home(cfg)))
    if which == "voice_engine":
        d = engines_dir()
        names = [p.name for p in d.iterdir() if p.is_dir() and (p / "READY").exists() and p.name not in ("whisper", "_home")] if d.exists() else []
        return (bool(names), ", ".join(names) if names else "none installed — the bench works with recordings")
    return (False, "")


def card_free(cfg: dict) -> tuple[bool, str]:
    """The card is asked for, never taken: free only when the art worker and the world queue are idle and the card lock is
    nobody's. Otherwise (what has it) — the run goes on the processor, or waits, as the person chooses."""
    try:
        from ..threed import cardlock
        st = cardlock.state(cfg)
        if st.get("held"):
            return False, f"{st.get('holder')} holds the card"
    except Exception:  # noqa: BLE001
        pass
    try:
        from ..threed.world import machine_busy
        why = machine_busy(cfg)
        if why:
            return False, why
    except Exception as e:  # noqa: BLE001
        return False, f"can't tell ({e})"
    return True, ""


def get_rhubarb(cfg: dict, dry_run: bool = False) -> dict:
    """Fetch the pinned Rhubarb release for this computer into tools/rhubarb, record its sum (and check it on every later
    fetch), log it. MIT."""
    import hashlib
    import urllib.request
    import zipfile
    sysname = platform.system()
    url = RHUBARB_URLS.get(sysname)
    if not url:
        return {"ok": False, "message": f"no Rhubarb build for {sysname}"}
    dst = cfgmod.ROOT / "tools" / "rhubarb"
    dst.mkdir(parents=True, exist_ok=True)
    if dry_run:
        return {"ok": True, "message": f"would fetch {url} into {dst}"}
    z = dst / Path(url).name
    urllib.request.urlretrieve(url, z)
    s = hashlib.sha256(z.read_bytes()).hexdigest()
    sums = dst / "SHA256.json"
    known = json.loads(sums.read_text(encoding="utf-8")) if sums.exists() else {}
    if known.get(z.name) and known[z.name] != s:
        return {"ok": False, "message": f"{z.name}: its sum changed since it was first fetched ({known[z.name][:12]} → {s[:12]}) — not unpacked"}
    known[z.name] = s
    sums.write_text(json.dumps(known, indent=1), encoding="utf-8")
    with zipfile.ZipFile(z) as zz:
        zz.extractall(dst)
    exe = rhubarb_exe(cfg)
    if exe and os.name != "nt":
        exe.chmod(0o755)
    log({"tool": "rhubarb", "action": "fetched", "url": url, "sha256": s, "exe": str(exe)})
    return {"ok": exe is not None, "message": f"Rhubarb {RHUBARB_VERSION} is in {dst} (sha256 {s[:12]}…)", "exe": str(exe)}


def get_whisper(cfg: dict, dry_run: bool = False) -> dict:
    """faster-whisper (MIT) in its own environment under engines/voice/whisper, the large-v3 weights (MIT) inside it."""
    h = whisper_home(cfg)
    h.mkdir(parents=True, exist_ok=True)
    py = shutil.which("python") or shutil.which("python3")
    if dry_run:
        return {"ok": True, "message": f"would make {h / 'venv'}, install faster-whisper and fetch large-v3 into {h / 'models'}"}
    env = tool_env()
    subprocess.run([py, "-m", "venv", str(h / "venv")], check=True, env=env)
    wpy = whisper_python(cfg)
    subprocess.run([str(wpy), "-m", "pip", "install", "faster-whisper==1.1.1"], check=True, env=env)
    subprocess.run([str(wpy), "-c", "from faster_whisper import download_model; "
                    f"download_model('large-v3', output_dir=r'{h / 'models' / 'large-v3'}')"], check=True, env=env)
    (h / "READY").write_text(time.strftime("%Y-%m-%d %H:%M"), encoding="utf-8")
    log({"tool": "whisper", "action": "installed", "where": str(h)})
    return {"ok": True, "message": f"Whisper large-v3 is ready in {h}"}
