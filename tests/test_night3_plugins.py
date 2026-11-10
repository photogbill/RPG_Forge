"""Night 3 plug-ins all load in a fresh process, their specs are complete, and every type validates with defaults —
a broken shared file (forge/night3/specs.py) would take every Night 3 type down, so this guards it."""
from forge import plugins, schema
from forge.jobs import get_handlers

NIGHT3 = {"scene_big", "inpaint", "scene_state", "facings_pack", "anim_preview", "turnaround_split", "nine_slice", "button_states"}


def test_every_night3_type_loads_and_validates():
    h = get_handlers()
    assert NIGHT3 <= set(h)
    loaded = {t for ts in plugins.loaded().values() for t in ts}
    assert NIGHT3 <= loaded
    for t in NIGHT3:
        spec = schema.JOB_TYPES[t]
        job = {"type": t, **{r: ([1, 1] if r == "target" else "x") for r in spec["required"]}}
        assert schema.validate(job) == [], t
        full = schema.with_defaults(job)
        assert set(spec["optional"]) <= set(full)
    assert schema.needs_gpu({"type": "scene_big"}) and not schema.needs_gpu({"type": "nine_slice"})
    assert "scene_state" in schema.render_docs()
