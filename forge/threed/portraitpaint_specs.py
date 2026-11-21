"""Job-type spec of the painted portraits plug-in (BUILD 93) — no imports."""

PORTRAIT_PAINT = {
    "needs": "gpu",
    "doc": "A portrait painted again from what the forge already has (plug-in, forge/threed/portraitpaint.py): `portrait` = "
           "a body portrait (a `model_portrait` picture), `picture` = the picture that body was made from (optional). "
           "FLUX.2 [klein] 4B's reference editing through ComfyUI's core ReferenceLatent (Apache-2.0; nothing to "
           "download). Three `ways`, each with every seed in `seeds`: `over` (the body portrait alone is the reference: "
           "the same pose, framing, clothes and light, real skin and eyes), `picture` (the body's own picture alone: its "
           "true face, the framing asked for in words), `both` (the face from the body's picture, the pose and light "
           "from the body portrait). Without `picture` only `over` is made. New pictures start 'Fantastic Realism, "
           "Hyperrealistic,'; the light is one warm key close to the face falling to dark, with a faint rim in `rim` "
           "[r, g, b] where a character owns a colour. Every result is measured against the body portrait (did the "
           "layout hold, did the colours hold — rough tripwires, never a judge of likeness) and one is proposed by "
           "those numbers, or named with `pick` ('<way>__<seed>'). It takes the card lock and waits its turn. Outputs: "
           "<slot>__<way>__<seed>.png (1024), <slot>.png (the proposed one, `out_size` 768), <slot>_384.png, contact.png.",
    "required": ["portrait"],
    "optional": {"picture": None, "ways": None, "seeds": [1001, 2002], "rim": None, "who": None, "also": None, "pick": None,
                 "size": 1024, "out_size": 768, "slot_name": "portrait", "world_id": None, "unet": None,
                 "layout_min": 0.5, "colour_min": 0.6, "use_card_lock": True, "wait_card_minutes": 720},
}
JOB_TYPES = {"portrait_paint": PORTRAIT_PAINT}
