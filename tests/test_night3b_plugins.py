"""Night 3B plug-ins load in a fresh process, their specs are complete and every type validates with defaults."""
from forge import plugins, schema
from forge.jobs import get_handlers

NIGHT3B = {"handoff_file", "handoff_kit", "filter_forge"}


def test_every_night3b_type_loads_and_validates():
    h = get_handlers()
    assert NIGHT3B <= set(h)
    loaded = {t for ts in plugins.loaded().values() for t in ts}
    assert NIGHT3B <= loaded
    for t in NIGHT3B:
        spec = schema.JOB_TYPES[t]
        job = {"type": t, **{r: "x" for r in spec["required"]}}
        assert schema.validate(job) == [], t
        assert set(spec["optional"]) <= set(schema.with_defaults(job))
    assert schema.needs_gpu({"type": "handoff_kit"}) and not schema.needs_gpu({"type": "filter_forge"})
    assert not schema.needs_gpu({"type": "handoff_file"})
