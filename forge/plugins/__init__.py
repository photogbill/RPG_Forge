"""Plug-in job types: add a job type to a worker that is already running.

Why this exists: the worker re-imports the built-in handler modules before every job, so a code *fix* reaches
it without a restart - but its table of job *types* is fixed when it starts. A plug-in is the way round that.

A plug-in is one file in this folder, `forge/plugins/<name>.py` (a name starting with "_" is ignored):

    JOB_TYPES = {"scene_big": {"needs": "gpu", "doc": "...", "required": ["prompt"], "optional": {...}}}
    HANDLERS  = {"scene_big": scene_big}          # callable(job, ctx, out_dir) -> result dict
    DEPENDS   = ("forge.ops.tiles",)              # optional: its own helper modules, reloaded when they change

Rules, all enforced here:
  * a plug-in can never replace a built-in job type or another plug-in's type (first owner keeps it);
  * every handler needs a spec with needs / required / optional / doc, and the other way round;
  * a plug-in whose file is half-saved or broken keeps its last good version and the problem is logged once;
    it can never take the worker or another job type down;
  * a file is re-imported only when it (or one of its DEPENDS) changed on disk.

`load()` is called by forge.jobs.get_handlers (the worker, before every job) and by forge.schema when it meets
a type it does not know (submit, validate, docs). Nothing else needs to change to add a job type.
"""
from __future__ import annotations
import importlib
import logging
import pkgutil
import sys
from pathlib import Path

log = logging.getLogger("forge.plugins")

_SPEC_KEYS = ("needs", "doc", "required", "optional")
_good: dict[str, tuple[dict, dict]] = {}      # module name -> (handlers, specs): the last version that loaded cleanly
_stamp: dict[str, float] = {}                 # module name -> newest mtime seen (its file and its DEPENDS)
_owner: dict[str, str] = {}                   # job type -> the plug-in module that owns it
_said: set[str] = set()                       # problems already logged (say each once)


def _warn(msg: str) -> None:
    if msg not in _said:
        _said.add(msg)
        log.warning(msg)


def _mtime(modname: str) -> float:
    mod = sys.modules.get(modname)
    f = getattr(mod, "__file__", None) if mod else None
    try:
        return Path(f).stat().st_mtime if f else 0.0
    except OSError:
        return 0.0


def _check(name: str, handlers, specs) -> str | None:
    if not isinstance(handlers, dict) or not isinstance(specs, dict):
        return "HANDLERS and JOB_TYPES must both be dicts"
    if set(handlers) != set(specs):
        return f"HANDLERS and JOB_TYPES name different job types: {sorted(set(handlers) ^ set(specs))}"
    for t, spec in specs.items():
        if not isinstance(spec, dict) or any(k not in spec for k in _SPEC_KEYS):
            return f"job type '{t}': its spec needs {', '.join(_SPEC_KEYS)}"
        if spec["needs"] not in ("gpu", "cpu"):
            return f"job type '{t}': needs must be 'gpu' or 'cpu'"
        if not isinstance(spec["required"], list) or not isinstance(spec["optional"], dict):
            return f"job type '{t}': required must be a list and optional a dict"
        if not callable(handlers[t]):
            return f"job type '{t}': its handler is not callable"
    return None


def _load_one(name: str) -> None:
    """Import or (if its files changed) re-import one plug-in; on any problem keep the last good version."""
    try:
        mod = sys.modules.get(name)
        if mod is None:
            mod = importlib.import_module(name)
            fresh = True
        else:
            deps = tuple(getattr(mod, "DEPENDS", ()) or ())
            newest = max([_mtime(name)] + [_mtime(d) for d in deps])
            fresh = newest > _stamp.get(name, 0.0)
            if fresh:
                for d in deps:
                    if d in sys.modules:
                        importlib.reload(sys.modules[d])
                mod = importlib.reload(mod)
        if not fresh and name in _good:
            return
        handlers, specs = getattr(mod, "HANDLERS", None), getattr(mod, "JOB_TYPES", None)
        problem = _check(name, handlers, specs)
        deps = tuple(getattr(mod, "DEPENDS", ()) or ())
        _stamp[name] = max([_mtime(name)] + [_mtime(d) for d in deps])
        if problem:
            _warn(f"plug-in {name} ignored: {problem}")
            return
        _good[name] = (dict(handlers), {t: dict(s) for t, s in specs.items()})
        log.info("plug-in %s loaded: %s", name, ", ".join(sorted(handlers)))
    except Exception as e:  # noqa: BLE001 - a broken plug-in must never stop the worker
        _stamp[name] = max(_stamp.get(name, 0.0), _mtime(name))
        _warn(f"plug-in {name} failed to load ({type(e).__name__}: {e}) - keeping its last good version, if any")


def load(job_types: dict | None = None, builtin: dict | None = None) -> dict:
    """Return {job type: handler} for every healthy plug-in and merge their specs into `job_types`.

    `job_types` is forge.schema.JOB_TYPES (specs are added to it, never replaced for a built-in);
    `builtin` is the built-in handler table (a plug-in type of the same name is refused).
    """
    try:
        importlib.invalidate_caches()
        names = sorted(f"{__name__}.{m.name}" for m in pkgutil.iter_modules(__path__) if not m.name.startswith("_"))
    except Exception as e:  # noqa: BLE001
        _warn(f"plug-in folder could not be read ({type(e).__name__}: {e})")
        names = sorted(_good)
    out: dict = {}
    for name in names:
        _load_one(name)
        if name not in _good:
            continue
        handlers, specs = _good[name]
        for t, fn in handlers.items():
            owned_by = _owner.get(t)
            builtin_type = (builtin is not None and t in builtin) or \
                           (job_types is not None and t in job_types and owned_by is None)
            if builtin_type:
                _warn(f"plug-in {name}: '{t}' is a built-in job type - ignored")
                continue
            if owned_by not in (None, name):
                _warn(f"plug-in {name}: '{t}' already belongs to {owned_by} - ignored")
                continue
            _owner[t] = name
            out[t] = fn
            if job_types is not None:
                job_types[t] = specs[t]
    return out


def loaded() -> dict[str, list[str]]:
    """{plug-in module: [job types]} - for `doctor` and the docs."""
    return {name: sorted(h) for name, (h, _s) in sorted(_good.items())}
