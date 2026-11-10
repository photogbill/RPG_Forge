"""Plug-in job types: added while a worker runs, never able to break it."""
import importlib
import os
import sys
import time

import pytest

from forge import plugins, schema
from forge.jobs import get_handlers


@pytest.fixture
def plug(tmp_path):
    """A scratch folder on the plug-in path; everything it added is removed afterwards."""
    before_types = dict(schema.JOB_TYPES)
    plugins.__path__.append(str(tmp_path))
    yield tmp_path
    plugins.__path__.remove(str(tmp_path))
    for name in [n for n in sys.modules if n.startswith("forge.plugins.t_")]:
        del sys.modules[name]
    for d in (plugins._good, plugins._stamp):
        for name in [n for n in d if n.startswith("forge.plugins.t_")]:
            del d[name]
    for t in [t for t, o in plugins._owner.items() if o.startswith("forge.plugins.t_")]:
        del plugins._owner[t]
    schema.JOB_TYPES.clear()
    schema.JOB_TYPES.update(before_types)
    plugins._said.clear()
    get_handlers()


GOOD = '''
def demo(job, ctx, out):
    return {"said": %r}
JOB_TYPES = {"t_demo": {"needs": "cpu", "doc": "a test type", "required": ["word"], "optional": {"loud": False}}}
HANDLERS = {"t_demo": demo}
'''


def _write(path, text, bump=0):
    path.write_text(text, encoding="utf-8")
    t = time.time() + bump
    os.utime(path, (t, t))


def test_no_plugins_changes_nothing():
    base = set(get_handlers())
    assert "scene_kit" in base and "render" in base
    assert plugins.loaded() == {} or all(not n.startswith("forge.plugins.t_") for n in plugins.loaded())


def test_plugin_adds_a_job_type_to_handlers_and_schema(plug):
    _write(plug / "t_one.py", GOOD % "first")
    h = get_handlers(reload=True)
    assert h["t_demo"]({}, None, None) == {"said": "first"}
    assert schema.validate({"type": "t_demo", "word": "x"}) == []
    assert schema.validate({"type": "t_demo"}) == ["t_demo: missing required field 'word'"]
    assert schema.needs_gpu({"type": "t_demo", "word": "x"}) is False
    assert schema.with_defaults({"type": "t_demo", "word": "x"})["loud"] is False
    assert "t_demo" in schema.render_docs()
    assert plugins.loaded()["forge.plugins.t_one"] == ["t_demo"]


def test_schema_finds_a_plugin_without_the_worker(plug):
    _write(plug / "t_one.py", GOOD % "first")
    assert "t_demo" not in schema.JOB_TYPES
    assert schema.validate({"type": "t_demo", "word": "x"}) == []      # submit path: no get_handlers call first


def test_changed_file_is_picked_up_and_unchanged_is_not_reimported(plug):
    f = plug / "t_one.py"
    _write(f, GOOD % "first")
    get_handlers(reload=True)
    mod = sys.modules["forge.plugins.t_one"]
    mod.MARK = 1
    get_handlers(reload=True)
    assert getattr(sys.modules["forge.plugins.t_one"], "MARK", None) == 1          # untouched file: not re-imported
    _write(f, GOOD % "second", bump=5)
    assert get_handlers(reload=True)["t_demo"]({}, None, None) == {"said": "second"}


def test_half_saved_plugin_keeps_its_last_good_version(plug):
    f = plug / "t_one.py"
    _write(f, GOOD % "first")
    get_handlers(reload=True)
    _write(f, "def demo(job, ctx, out):\n    return {\n", bump=5)                  # a syntax error on disk
    h = get_handlers(reload=True)
    assert h["t_demo"]({}, None, None) == {"said": "first"}
    assert "scene_kit" in h


def test_broken_from_the_start_is_ignored_and_built_ins_survive(plug):
    _write(plug / "t_bad.py", "raise RuntimeError('boom')\n")
    h = get_handlers(reload=True)
    assert "scene_kit" in h and "t_demo" not in h
    assert schema.validate({"type": "render", "prompt": "x", "checkpoint": "y"}) is not None


def test_plugin_cannot_replace_a_built_in_type(plug):
    real = get_handlers()["render"]
    _write(plug / "t_thief.py", '''
def fake(job, ctx, out):
    return {"stolen": True}
JOB_TYPES = {"render": {"needs": "cpu", "doc": "x", "required": [], "optional": {}}}
HANDLERS = {"render": fake}
''')
    h = get_handlers(reload=True)
    assert h["render"] is get_handlers()["render"]
    assert h["render"].__name__ == real.__name__ == "render"
    assert schema.JOB_TYPES["render"]["needs"] == "gpu"


def test_spec_and_handler_must_match(plug):
    _write(plug / "t_lop.py", '''
def a(job, ctx, out):
    return {}
JOB_TYPES = {}
HANDLERS = {"t_orphan": a}
''')
    assert "t_orphan" not in get_handlers(reload=True)


def test_depends_are_reloaded_when_they_change(plug):
    helper = plug / "t_helper.py"
    _write(helper, "WORD = 'one'\nJOB_TYPES = {}\nHANDLERS = {}\n")
    _write(plug / "t_user.py", '''
from forge.plugins import t_helper
DEPENDS = ("forge.plugins.t_helper",)
def say(job, ctx, out):
    return {"said": t_helper.WORD}
JOB_TYPES = {"t_say": {"needs": "cpu", "doc": "x", "required": [], "optional": {}}}
HANDLERS = {"t_say": say}
''')
    assert get_handlers(reload=True)["t_say"]({}, None, None) == {"said": "one"}
    _write(helper, "WORD = 'two'\nJOB_TYPES = {}\nHANDLERS = {}\n", bump=5)
    assert get_handlers(reload=True)["t_say"]({}, None, None) == {"said": "two"}


def test_ping_ships_and_runs(tmp_path):
    h = get_handlers(reload=True)
    assert schema.validate({"type": "ping", "name": "hello"}) == []
    r = h["ping"]({"type": "ping", "say": "hi"}, None, tmp_path / "o")
    assert (tmp_path / "o" / "ping.txt").read_text(encoding="utf-8").startswith("pong ") and r["outputs"] == ["ping.txt"]
