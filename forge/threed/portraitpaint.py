"""Portraits painted over the bodies (BUILD 93): a body portrait is true to its body and too crude for a dialogue box —
the bodies were made to be seen small. Each body was made from a picture that already has the face; the model that
painted that picture can take a reference picture and a sentence. So the portrait is painted again from what the forge
already has, and nothing new is downloaded.

    python -m forge.threed.portraitpaint paint  [--game <id>] [--only <name> …] [--again] [--ways over both …] [--seeds 1 2 …]
    python -m forge.threed.portraitpaint pick <name> <way>__<seed>  [--game <id>]      (no card: uses what is painted)
    python -m forge.threed.portraitpaint sheet  [--game <id>]                          (no card: the sheet again)

Three ways, one contract, so they can be compared and the loser dropped (job type portrait_paint):
  over     the body portrait alone is the reference: the same pose, framing, clothes and light; real skin and eyes.
  picture  the picture the body was made from, alone: its true face; the framing and the light asked for in words.
  both     the face from the body's picture, the pose, framing and light from the body portrait (two references).
All three are FLUX.2 [klein] 4B's own reference editing (Apache-2.0) through ComfyUI's core ReferenceLatent node; a
second reference is a second node on the same line. Every new picture starts with the style start the same-person
job uses, and the light is the portrait rule's: one warm key close to the face, falling to dark, a faint rim.

Every result is measured against the body portrait by two plain measures the forge already has — did the layout hold
(the same light and dark in the same places, both pictures blurred small), did the colours hold (the figure's colour,
patch by patch). They are rough
tripwires and the sheet says so: they can tell a picture that was reframed or recoloured, never whether it is the same
face. One result a name is PROPOSED by those numbers; a game's table, or `pick`, names another. Nothing is approved here.

It puts work on the graphics card, so it takes the card lock and waits its turn; a session never starts it.

What a game says, in games/<id>/pictures/ (proposal files): portraits.json (BUILD 91: the names, their bodies, a rim
colour where a character owns one) and, optional, portraits_painted.json:
    {"skip": {"<name>": "why"}, "ways": [...], "seeds": [...],
     "names": {"<name>": {"who": "a boy of ten", "also": "…", "ways": [...], "pick": "<way>__<seed>"}}}
Results: out/pictures/<game>/portraits_painted/ — <name>.png (768), 384/<name>.png, candidates/, the sheet.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import traceback
from pathlib import Path

import numpy as np
from PIL import Image

from .. import config as cfgmod
from .same_person import STYLE_START

log = logging.getLogger("forge.portraitpaint")
WAYS = ("over", "picture", "both")
ORDER = ("both", "over", "picture")            # between results the numbers cannot separate, the one that used most wins
GROUND = (10, 10, 13)                          # the near-black a body portrait is laid on before the model sees it
UNET = "flux-2-klein-4b.safetensors"
SUBFOLDER = "forge_portrait_paint"
REAL = "real skin with fine texture, real eyes with catchlights, real hair, real cloth"
REST = "a calm face at rest, mouth closed, eyes open, looking at the camera"
LIGHT = ("lit by one warm candle close to the face from the right, the light falling off quickly into deep shadow, {rim}, "
         "a plain near-black background")
RIMS = {"cyan": (0.2, 0.9, 1.0), "red": (0.8, 0.05, 0.08), "blue": (0.2, 0.35, 1.0), "green": (0.2, 0.9, 0.3), "amber": (1.0, 0.65, 0.1),
        "violet": (0.6, 0.25, 1.0), "white": (1.0, 1.0, 1.0)}


class PaintError(Exception):
    pass


# ------------------------------------------------------------------ the words
def rim_words(rim) -> str:
    """The faint light behind, in words: a colour's name only where a character owns one."""
    if not rim:
        return "a faint cool rim of light on the hair and the shoulder from behind on the left"
    r = np.asarray([float(x) for x in list(rim)[:3]])
    if r.max() > 1.0:
        r = r / 255.0
    name = min(RIMS, key=lambda k: float(((np.asarray(RIMS[k]) - r) ** 2).sum()))
    return f"a faint {name} rim of light on the hair and the shoulder from behind on the left"


def words_for(way: str, rim=None, who: str | None = None, also: str | None = None) -> str:
    """The sentence for one way. `who` is a few plain words about the person (an age, say) that a picture alone may not
    carry; `also` is anything a game wants added. Starts with the style start every new picture of a person starts with.
    The model's makers say how to write these: say what changes and let the pictures carry what things look like; with
    two pictures, name each one's part, as "image 1" and "image 2" (their order is the order of the references)."""
    if way not in WAYS:
        raise PaintError(f"there is no way called {way!r}: say one of {', '.join(WAYS)}")
    w = f" ({who.strip()})" if who and who.strip() else ""
    light = LIGHT.format(rim=rim_words(rim))
    if way == "over":
        s = (f"the same person{w}, changed from a rough 3D model into a real photograph, head and shoulders. Keep the pose, the "
             f"framing, the hair and its colours, the clothes and the direction of the light exactly as they are; {REAL}; {REST}; {light}.")
    elif way == "picture":
        s = (f"a head-and-shoulders portrait photograph of the same person{w}, the body turned a little to one side, the same "
             f"face, hair and clothes; {REAL}; {REST}; {light}; a long lens, the background out of focus.")
    else:
        s = (f"a head-and-shoulders portrait photograph of the person in image 1{w}, with that person's face, hair and clothes, "
             f"posed, framed and lit as in image 2; {REAL}; {REST}; {light}.")
    return STYLE_START + s + (" " + also.strip() if also and also.strip() else "")


# ------------------------------------------------------------------ the graph
def graph(refs: list[str], words: str, seed: int, width: int = 1024, height: int = 1024, unet: str = UNET,
          text_encoder: str = "qwen_3_4b.safetensors", vae: str = "flux2-vae.safetensors") -> dict:
    """FLUX.2 [klein] 4B's text-to-image graph with each picture in `refs` (names as ComfyUI's input folder knows them)
    added as a reference latent, in order — one ReferenceLatent node a picture, each on the one before. With one
    reference this is the same-person job's `graph_instructed`."""
    from ..engines import flux2_graph
    if not refs:
        raise PaintError("a painted portrait needs at least one reference picture")
    g = flux2_graph.build(unet, words, "", int(seed), int(width), int(height), text_encoder=text_encoder, vae=vae,
                          filename_prefix="forge_portrait_paint")
    cond = ["4", 0]
    for i, name in enumerate(refs):
        a = 40 + i * 10
        g[str(a)] = {"class_type": "LoadImage", "inputs": {"image": name}}
        g[str(a + 1)] = {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": [str(a), 0], "upscale_method": "lanczos",
                                                                              "megapixels": 1.0, "resolution_steps": 1}}
        g[str(a + 2)] = {"class_type": "VAEEncode", "inputs": {"pixels": [str(a + 1), 0], "vae": ["3", 0]}}
        g[str(a + 3)] = {"class_type": "ReferenceLatent", "inputs": {"conditioning": cond, "latent": [str(a + 2), 0]}}
        cond = [str(a + 3), 0]
    g["10"]["inputs"]["positive"] = cond
    if g["5"]["class_type"] == "ConditioningZeroOut":
        g["5"]["inputs"]["conditioning"] = cond
    return g


def refs_for(way: str, portrait_name: str, picture_name: str | None) -> list[str]:
    if way == "over":
        return [portrait_name]
    if not picture_name:
        raise PaintError(f"the way '{way}' needs the picture the body was made from, and there is none")
    return [picture_name] if way == "picture" else [picture_name, portrait_name]


# ------------------------------------------------------------------ what a result kept
def flatten(img: Image.Image, size: int | None = None, ground=GROUND) -> tuple[Image.Image, np.ndarray]:
    """A body portrait (clear background) laid on the near-black ground: (the picture, where the figure is 0..1)."""
    im = img.convert("RGBA")
    if size and im.size != (size, size):
        im = im.convert("RGBa").resize((size, size), Image.LANCZOS).convert("RGBA")
    base = Image.new("RGBA", im.size, tuple(ground) + (255,))
    base.alpha_composite(im)
    return base.convert("RGB"), np.asarray(im.getchannel("A"), dtype=np.float32) / 255.0


def _blurred(img: Image.Image, n: int = 32) -> np.ndarray:
    """A picture's light and dark, small: grey, n x n, with its own mean taken off and its own spread divided out."""
    g = np.asarray(img.convert("L").resize((n, n), Image.BOX), dtype=np.float32)
    g = g - g.mean()
    return g / max(float(g.std()), 1e-3)


def kept(body: Image.Image, figure: np.ndarray, result: Image.Image, layout_min: float = 0.5, colour_min: float = 0.6) -> dict:
    """Two rough tripwires against the body portrait. `layout`: how alike the two pictures are once both are blurred to
    32 x 32 — the same light and dark in the same places (1.0), or not (0) — low when the picture was reframed, re-posed
    or lit from another side; brightness as a whole does not count. `colour`: how well the figure's colour holds, patch
    by patch — low when hair or clothes changed colour. Neither can say it is the same face; nothing on the disk can,
    under a licence a game may use."""
    n = 384
    b = body.convert("RGB").resize((n, n), Image.LANCZOS)
    r = result.convert("RGB").resize((n, n), Image.LANCZOS)
    layout = max(0.0, float((_blurred(b) * _blurred(r)).mean()))
    m = np.asarray(Image.fromarray((figure * 255).astype(np.uint8)).resize((n, n), Image.BILINEAR), dtype=np.float32) / 255.0
    A, B = np.asarray(b, dtype=np.float32) / 255.0, np.asarray(r, dtype=np.float32) / 255.0
    drift, cells = 0.0, 0
    k = n // 6
    for y in range(0, n, k):
        for x in range(0, n, k):
            w = m[y:y + k, x:x + k]
            if w.sum() < 0.5 * k * k:                       # a patch that is mostly background says nothing
                continue
            ca = (A[y:y + k, x:x + k] * w[..., None]).sum(axis=(0, 1)) / w.sum()
            cb = (B[y:y + k, x:x + k] * w[..., None]).sum(axis=(0, 1)) / w.sum()
            if ca.sum() < 0.12 and cb.sum() < 0.12:         # both in shadow: no colour to compare
                continue
            ca, cb = ca / max(ca.sum(), 1e-3), cb / max(cb.sum(), 1e-3)      # the colour without its brightness
            drift += float(np.abs(ca - cb).sum())
            cells += 1
    colour = 1.0 if not cells else max(0.0, 1.0 - (drift / cells) / 0.5)
    ok = layout >= layout_min and colour >= colour_min
    says = f"layout held {layout:.2f}, colours held {colour:.2f}"
    if layout < layout_min:
        says += " - reframed, re-posed or lit from another side"
    if colour < colour_min:
        says += " - the colours moved"
    return {"layout": round(layout, 3), "colour": round(colour, 3), "ok": bool(ok), "says": says, "patches": cells}


def choose(cands: list[dict], pick: str | None = None) -> tuple[dict | None, str]:
    """(the proposed candidate, why). A named `pick` wins; else the best by the two measures among those that passed
    both, a near tie going to the way that used most; else the best of all, with a warning."""
    good = [c for c in cands if c.get("file")]
    if not good:
        return None, "nothing was painted"
    if pick:
        for c in good:
            if c["key"] == pick:
                return c, "named in the table"
        return None, f"the table names {pick}, and that one was not painted ({', '.join(c['key'] for c in good)})"
    score = lambda c: 0.6 * c["kept"]["layout"] + 0.4 * c["kept"]["colour"]          # noqa: E731
    passed = [c for c in good if c["kept"]["ok"]]
    pool = passed or good
    top = max(score(c) for c in pool)
    near = [c for c in pool if top - score(c) <= 0.03]
    best = min(near, key=lambda c: (ORDER.index(c["way"]), -score(c)))
    return best, ("the best of those that held layout and colours" if passed
                  else "NONE held both layout and colours: this is only the nearest - look before using it")


# ------------------------------------------------------------------ the job
def _comfy(ctx, cfg):
    c = getattr(ctx, "comfy", None)
    if c is not None:
        return c
    from ..engines.comfy import ComfyClient
    cm = (cfg or {}).get("comfy") or {}
    return ComfyClient(cm.get("url") or "http://127.0.0.1:8188", timeout_sec=int(cm.get("timeout_sec") or 1800))


def paint_job(job: dict, ctx, out: Path, client=None, lock=None) -> dict:
    """The portrait_paint job handler. `client` stands in for ComfyUI in tests; `lock` is a card lock the caller already
    holds for a whole batch (then this takes none of its own)."""
    from ..jobs.common import save_png, write_prov
    from ..ops import sheet as sh
    out = Path(out)
    cfg = getattr(ctx, "cfg", None) or {}
    root = Path(getattr(ctx, "root", None) or cfgmod.ROOT)
    slot = str(job.get("slot_name") or "portrait")
    res = lambda p: Path(str(p)) if Path(str(p)).is_absolute() else root / str(p)          # noqa: E731
    src = res(job["portrait"])
    if not src.is_file():
        raise PaintError(f"the body portrait is not there: {src}")
    pic = res(job["picture"]) if job.get("picture") else None
    if pic is not None and not pic.is_file():
        raise PaintError(f"the picture the body was made from is not there: {pic}")
    ways = [str(w) for w in (job.get("ways") or (WAYS if pic else ("over",)))]
    for w in ways:
        if w not in WAYS:
            raise PaintError(f"there is no way called {w!r}: say one of {', '.join(WAYS)}")
    notes = []
    if pic is None and any(w != "over" for w in ways):
        notes.append("no picture of the body's own was given: only 'over' was painted")
        ways = [w for w in ways if w == "over"]
    if not ways:
        raise PaintError("no way to paint: 'picture' and 'both' need the picture the body was made from")
    seeds = [int(s) for s in (job.get("seeds") or [1001, 2002])]
    size = int(job.get("size") or 1024) // 16 * 16
    body, figure = flatten(Image.open(src), size)
    ref_body = out / f"_{slot}_reference_portrait.png"
    body.save(ref_body)
    flux = ((cfg.get("comfy") or {}).get("flux2") or {})
    unet = str(job.get("unet") or UNET)
    client = client or _comfy(ctx, cfg)
    mine = None
    if lock is None and job.get("use_card_lock", True):
        from .cardlock import CardLock
        mine = lock = CardLock(cfg, f"painted portrait {slot}", wait_minutes=float(job.get("wait_card_minutes") or 720), side="art").acquire()
    cands, tiles, labels = [], [body.resize((384, 384), Image.LANCZOS)], ["the body portrait"]
    try:
        tag = str(job.get("id") or slot)
        up_body = client.upload_image(ref_body, subfolder=SUBFOLDER, name=f"{tag}__portrait.png")
        up_pic = client.upload_image(pic, subfolder=SUBFOLDER, name=f"{tag}__picture{pic.suffix.lower()}") if pic is not None else None
        for way in ways:
            words = words_for(way, job.get("rim"), job.get("who"), job.get("also"))
            for seed in seeds:
                key = f"{way}__{seed}"
                c = {"key": key, "way": way, "seed": seed, "words": words}
                t0 = time.time()
                try:
                    g = graph(refs_for(way, up_body, up_pic), words, seed, size, size, unet=unet,
                              text_encoder=flux.get("text_encoder") or "qwen_3_4b.safetensors", vae=flux.get("vae") or "flux2-vae.safetensors")
                    data = client.run(g)[0]
                    f = out / f"{slot}__{key}.png"
                    f.write_bytes(data)
                    img = Image.open(f).convert("RGB")
                    c.update(file=f.name, kept=kept(body, figure, img, float(job.get("layout_min") or 0.5), float(job.get("colour_min") or 0.6)),
                             seconds=round(time.time() - t0, 1))
                    tiles.append(img.resize((384, 384), Image.LANCZOS))
                    labels.append(f"{way} {seed}: {c['kept']['says']}")
                except PaintError:
                    raise
                except Exception as e:  # noqa: BLE001 — one failure is written down; the rest go on
                    c["error"] = f"{type(e).__name__}: {e}"[:300]
                    log.error("portrait_paint %s %s failed: %s", slot, key, c["error"])
                cands.append(c)
                if lock is not None:
                    lock.beat()
    finally:
        if mine is not None:
            mine.release()
    best, why = choose(cands, job.get("pick"))
    if best is None:
        firsts = "; ".join(f"{c['key']}: {c['error']}" for c in cands if c.get("error"))[:600]
        raise PaintError(f"{why}" + (f" - {firsts}" if firsts else ""))
    final = Image.open(out / best["file"]).convert("RGB")
    out_size = int(job.get("out_size") or 768)
    save_png(final.resize((out_size, out_size), Image.LANCZOS), out / f"{slot}.png")
    save_png(final.resize((384, 384), Image.LANCZOS), out / f"{slot}_384.png")
    labels = [("PROPOSED - " + lab if i and cands_file(cands, i - 1) == best["file"] else lab) for i, lab in enumerate(labels)]
    save_png(sh.contact_sheet(tiles, labels, cols=min(4, len(tiles)), cell=(384, 384), title=f"{job.get('name') or slot}: {why}"), out / "contact.png")
    lines, ok, rec = _licences(cfg, job)
    write_prov(out, job, op="portrait_paint", portrait=str(job["portrait"]), picture=str(job.get("picture") or ""), unet=unet, ways=ways,
               seeds=seeds, candidates=cands, proposed=best["key"], proposed_why=why, size=size, out_size=out_size,
               measures="layout = how alike the body portrait and the painting are, both blurred to 32 x 32; colour = the figure's colour patch by patch. "
                        "Rough tripwires: they cannot say it is the same face.",
               licences_lines=lines, commercial_ok=ok, notes=notes, **rec)
    return {"outputs": [f"{slot}.png", f"{slot}_384.png"] + [c["file"] for c in cands if c.get("file")] + ["contact.png"],
            "proposed": best["key"], "why": why, "candidates": [{k: c.get(k) for k in ("key", "way", "seed", "file", "kept", "error")} for c in cands],
            "notes": notes, "commercial_ok": ok}


def cands_file(cands: list[dict], n: int) -> str | None:
    """The file of the n-th candidate that has one (the contact sheet's tiles are those, in order)."""
    have = [c["file"] for c in cands if c.get("file")]
    return have[n] if n < len(have) else None


def _licences(cfg, job: dict) -> tuple[list[str], bool | None, dict]:
    """The painting model's licence line, and those of the body the portrait was taken from (the world queue's record)."""
    try:
        from . import licences
        keys = ["flux2_klein_4b"]
        rec = {}
        if job.get("game") and job.get("world_id"):
            from . import world
            st = world.read_state(cfg, str(job["game"]), str(job["world_id"]))
            keys += [k for k in world.licence_keys(st) if k not in keys]
            rec = {"try": st.get("try"), "engine": st.get("engine")}
        return licences.lines(keys), licences.all_ok(keys), {**rec, "licence_keys": keys}
    except Exception as e:  # noqa: BLE001
        return [f"licences not read ({e})"], None, {}


# ------------------------------------------------------------------ the commands
def _dirs(cfg: dict, game: str) -> tuple[Path, Path, Path]:
    base = cfgmod.path_of(cfg, "out") / "pictures" / game
    return cfgmod.path_of(cfg, "games") / game / "pictures", base / "portraits", base / "portraits_painted"


def _tables(gdir: Path) -> tuple[dict, dict]:
    f = gdir / "portraits.json"
    if not f.is_file():
        raise PaintError(f"this game has no {f} (the names and their bodies: docs/MODEL_PICTURES.md)")
    table = json.loads(f.read_text(encoding="utf-8"))
    g = gdir / "portraits_painted.json"
    return table, (json.loads(g.read_text(encoding="utf-8")) if g.is_file() else {})


def _note(dest: Path, name: str) -> dict:
    try:
        return json.loads((dest / f"{name}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def plan(cfg: dict, game: str, only=None, again: bool = False, ways=None, seeds=None) -> tuple[list[dict], dict]:
    """(the jobs to run, what each name's state is in plain words) — reads only."""
    from . import world
    gdir, src, dest = _dirs(cfg, game)
    table, extra = _tables(gdir)
    skip = extra.get("skip") or {}
    jobs, states = [], {}
    for name, m in (table.get("portraits") or {}).items():
        if only and name not in only:
            continue
        if name in skip:
            states[name] = {"state": f"left as it is: {skip[name]}"}
            continue
        body = src / f"{name}.png"
        if not body.is_file():
            states[name] = {"state": "no body portrait yet (its body is not made, or the pictures have not been taken)", "world": m.get("world")}
            continue
        e = (extra.get("names") or {}).get(name) or {}
        pic = None
        if m.get("world"):
            st = world.read_state(cfg, game, m["world"])
            if st.get("picture") and (cfgmod.ROOT / st["picture"]).is_file():
                pic = cfgmod.ROOT / st["picture"]
        note = _note(dest, name)
        fresh = note.get("portrait_mtime") == int(body.stat().st_mtime) and (dest / f"{name}.png").is_file()
        states[name] = {"state": "painted" if fresh else "to paint", "world": m.get("world"), "body": str(body), "picture": str(pic) if pic else None,
                        "proposed": note.get("proposed") if fresh else None}
        if fresh and not again:
            continue
        states[name]["state"] = "to paint"
        jobs.append({"type": "portrait_paint", "name": f"painted_{name}"[:48], "game": game, "slot_name": name, "portrait": str(body),
                     **({"picture": str(pic)} if pic else {}), "world_id": m.get("world"),
                     **({"rim": m["rim"]} if m.get("rim") else {}),
                     **{k: e[k] for k in ("who", "also", "pick") if e.get(k)},
                     **({"ways": list(ways or e.get("ways") or extra.get("ways"))} if (ways or e.get("ways") or extra.get("ways")) else {}),
                     **({"seeds": [int(s) for s in (seeds or e.get("seeds") or extra.get("seeds"))]} if (seeds or e.get("seeds") or extra.get("seeds")) else {}),
                     "_name": name, "_mtime": int(body.stat().st_mtime)})
    return jobs, states


def run_batch(cfg: dict, jobs: list[dict], batch: str, client=None, use_lock: bool = True, say=print) -> list[dict]:
    """Queue `jobs` under `batch` and run that batch here, holding the card for the whole of it (taken once, between two
    of the world queue's models). The art worker is not started, stopped or fed; other waiting jobs stay where they are."""
    from .. import schema
    from ..jobs.common import Context
    from ..queue import Queue
    schema.validate({"type": "portrait_paint", "portrait": "x.png"})            # the schema learns the plug-in's type
    q = Queue(cfgmod.path_of(cfg, "jobs"), cfgmod.path_of(cfg, "out"))
    for j in jobs:
        q.submit({**j, "batch": batch})
    ctx = Context(cfg=cfg, palettes_dir=cfgmod.path_of(cfg, "palettes"), root=cfgmod.ROOT)
    lock = None
    if use_lock and jobs:
        from .cardlock import CardLock, state
        st = state(cfg)
        if st.get("held"):
            say(f"  The graphics card is with {st.get('holder', 'someone')} (since {st.get('since', '?')}). Waiting for its turn - "
                "this window can stay open; nothing is lost.", flush=True)
        lock = CardLock(cfg, "painted portraits", wait_minutes=720, side="art", log=log).acquire()
        say("  The graphics card is ours for this batch.", flush=True)
    rows = []
    try:
        while True:
            got = q.claim(lambda job: job.get("batch") == batch and job.get("type") == "portrait_paint" and not job.get("tombstone"))
            if got is None:
                return rows
            jid, job = got
            job = schema.with_defaults(job)
            t0 = time.time()
            say(f"  {time.strftime('%H:%M:%S')}  {job.get('name')} ...", end=" ", flush=True)
            try:
                res = paint_job(job, ctx, q.out_dir(jid), client=client, lock=lock) or {}
                res["seconds"] = round(time.time() - t0, 1)
                q.finish(jid, result=res)
                rows.append({"id": jid, "name": job.get("name"), "ok": True, "result": res, "job": job})
                say(f"done in {res['seconds']:.0f} s - proposed: {res['proposed']} ({res['why']})", flush=True)
            except Exception as e:  # noqa: BLE001
                q.finish(jid, error=f"{type(e).__name__}: {e}", tb=traceback.format_exc())
                rows.append({"id": jid, "name": job.get("name"), "ok": False, "error": f"{type(e).__name__}: {e}", "job": job})
                say("FAILED\n      " + str(e)[:800], flush=True)
                log.error("FAILED %s: %s", job.get("name"), e)
            except BaseException:                      # Ctrl+C: the job in hand is not left in jobs/running
                q.finish(jid, error="stopped before it finished (Ctrl+C)")
                raise
    finally:
        if lock is not None:
            lock.release()


def _keep(cfg: dict, row: dict, dest: Path) -> None:
    """Copy a finished job's pictures into the game's stable folder, with a note of what they were painted from."""
    src = cfgmod.path_of(cfg, "out") / row["id"]
    job, res = row["job"], row["result"]
    name = job["_name"]
    (dest / "candidates").mkdir(parents=True, exist_ok=True)
    (dest / "384").mkdir(parents=True, exist_ok=True)
    for c in res["candidates"]:
        if c.get("file"):
            Image.open(src / c["file"]).save(dest / "candidates" / f"{name}__{c['key']}.png")
    Image.open(src / f"{name}.png").save(dest / f"{name}.png")
    Image.open(src / f"{name}_384.png").save(dest / "384" / f"{name}.png")
    (dest / f"{name}.json").write_text(json.dumps({"portrait": job["portrait"], "portrait_mtime": job["_mtime"], "picture": job.get("picture"),
                                                   "job": row["id"], "proposed": res["proposed"], "why": res["why"],
                                                   "candidates": res["candidates"], "notes": res.get("notes")}, indent=1), encoding="utf-8")


def set_pick(cfg: dict, game: str, name: str, key: str) -> Path:
    """Make another painted candidate the proposed one — no card: it is copied from what was painted."""
    _, _, dest = _dirs(cfg, game)
    note = _note(dest, name)
    f = dest / "candidates" / f"{name}__{key}.png"
    if not note or not f.is_file():
        have = sorted(p.stem.split("__", 1)[1] for p in (dest / "candidates").glob(f"{name}__*.png"))
        raise PaintError(f"{name} has no painted candidate called {key}" + (f": it has {', '.join(have)}" if have else " (nothing is painted for that name yet)"))
    img = Image.open(f).convert("RGB")
    img.resize((768, 768), Image.LANCZOS).save(dest / f"{name}.png")
    (dest / "384").mkdir(exist_ok=True)
    img.resize((384, 384), Image.LANCZOS).save(dest / "384" / f"{name}.png")
    note.update(proposed=key, why="chosen by hand (the pick command)")
    (dest / f"{name}.json").write_text(json.dumps(note, indent=1), encoding="utf-8")
    return dest / f"{name}.png"


def write_sheet(cfg: dict, game: str, states: dict | None = None) -> Path | None:
    """One line a name: the body portrait, then every painted candidate with its two numbers; the proposed one in amber."""
    from . import modelpics as mp
    gdir, src, dest = _dirs(cfg, game)
    table, _ = _tables(gdir)
    lines, widest = [], 1
    for name in (table.get("portraits") or {}):
        note = _note(dest, name)
        body = src / f"{name}.png"
        if not note or not body.is_file():
            continue
        row = [{"image": Image.open(body), "label": name, "sub": "the body portrait"}]
        for c in note.get("candidates") or []:
            f = dest / "candidates" / f"{name}__{c['key']}.png"
            if c.get("file") and f.is_file():
                on = c["key"] == note.get("proposed")
                row.append({"image": Image.open(f).convert("RGBA"), "label": ("PROPOSED " if on else "") + c["key"].replace("__", " "),
                            "sub": f"layout {c['kept']['layout']:.2f} colour {c['kept']['colour']:.2f}" + ("" if c["kept"]["ok"] else " - LOOK"),
                            "flag": "near" if on else ""})
        lines.append(row)
        widest = max(widest, len(row))
    if not lines:
        return None
    rows = []
    for row in lines:
        rows += row + [{"image": None, "label": "", "sub": "", "why": ""}] * (widest - len(row))
    waiting = [n for n, s in (states or {}).items() if s.get("state", "").startswith("no body portrait")]
    left = [f"{n} ({s['state'].split(': ', 1)[-1]})" for n, s in (states or {}).items() if s.get("state", "").startswith("left as it is")]
    foot = ["amber = the proposed one. layout / colour: how much of the body portrait's layout and colours the painting kept - rough tripwires,",
            "not a judge of likeness. Another candidate: portraits_painted.bat pick <name> <way> <seed>. Nothing here is approved."]
    if waiting:
        foot.append("no body portrait yet: " + ", ".join(waiting))
    if left:
        foot.append("left as they are: " + "; ".join(left))
    s = mp.sheet(rows, f"Portraits painted over the bodies: {len(lines)} ({time.strftime('%Y-%m-%d %H:%M')})", cell=256, cols=widest,
                 bg=GROUND, foot=foot)
    dest.mkdir(parents=True, exist_ok=True)
    s.save(dest / "portraits_painted_sheet.png")
    return dest / "portraits_painted_sheet.png"


def cmd_paint(cfg: dict, game: str, args, client=None, use_lock: bool = True) -> tuple[dict, int]:
    """(each name's state, how many failed)."""
    jobs, states = plan(cfg, game, only=args.only, again=args.again, ways=args.ways, seeds=args.seeds)
    _, _, dest = _dirs(cfg, game)
    print(f"{len(jobs)} portrait(s) to paint" + (f" ({sum(1 for s in states.values() if s['state'] == 'painted')} already painted from the body portrait as it is now)"
                                                 if any(s["state"] == "painted" for s in states.values()) else ""), flush=True)
    bad = 0
    if jobs:
        c = client or _comfy(None, cfg)
        if hasattr(c, "is_up") and not c.is_up():
            raise PaintError("ComfyUI is not answering (" + str(((cfg.get("comfy") or {}).get("url")) or "http://127.0.0.1:8188") + "). "
                             "Nothing was queued. Start it (start_comfy.bat, or let art_around_the_clock.bat start it) and run this again.")
        for r in run_batch(cfg, jobs, "pictures/portraits_painted", client=c, use_lock=use_lock):
            name = r["job"]["_name"]
            if r["ok"]:
                _keep(cfg, r, dest)
                states[name].update(state="painted", proposed=r["result"]["proposed"], why=r["result"]["why"])
            else:
                states[name].update(state="tried and failed", error=r["error"][:300])
                bad += 1
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "portraits_painted.json").write_text(json.dumps(states, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return states, bad


def _setup_log(cfg: dict) -> Path:
    p = cfgmod.path_of(cfg, "logs") / "pictures.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    h = logging.FileHandler(p, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger("forge").addHandler(h)
    logging.getLogger("forge").setLevel(logging.INFO)
    return p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m forge.threed.portraitpaint", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["paint", "pick", "sheet"])
    ap.add_argument("rest", nargs="*", help="pick: <name> <way>__<seed>  (or <name> <way> <seed>)")
    ap.add_argument("--game", default=None)
    ap.add_argument("--only", action="append", help="a portrait name (may be given more than once)")
    ap.add_argument("--again", action="store_true", help="paint every portrait again, even one painted from the body portrait as it is now")
    ap.add_argument("--ways", nargs="+", choices=list(WAYS), default=None)
    ap.add_argument("--seeds", nargs="+", type=int, default=None)
    args = ap.parse_args(argv)
    cfg = cfgmod.load()
    cfgmod.ensure_dirs(cfg)
    logfile = _setup_log(cfg)
    game = args.game or cfgmod.default_game(cfg)
    try:
        states, bad = None, 0
        if args.command == "pick":
            if len(args.rest) not in (2, 3):
                raise PaintError("say which: pick <name> <way> <seed>   (for example: pick hero both 2002)")
            key = args.rest[1] if len(args.rest) == 2 else f"{args.rest[1]}__{args.rest[2]}"
            print(f"  {set_pick(cfg, game, args.rest[0], key)} is now {key}")
        elif args.command == "paint":
            states, bad = cmd_paint(cfg, game, args)
            for n, s in states.items():
                print(f"  {n}: {s['state']}" + (f" - proposed {s['proposed']}" if s.get("proposed") else "") + (f" - {s['error']}" if s.get("error") else ""))
        if states is None:
            states = plan(cfg, game)[1]
        f = write_sheet(cfg, game, states)
        print(f"  {f}" if f else "  Nothing is painted yet, so there is no sheet.")
        return 1 if bad else 0
    except PaintError as e:
        print(f"\n{e}")
        return 2
    except Exception as e:  # noqa: BLE001
        log.error("painted portraits failed: %s\n%s", e, traceback.format_exc())
        print(f"\nIt stopped: {e}\nThe whole story is in {logfile}. Tell Claude what this says.")
        return 3


if __name__ == "__main__":
    sys.exit(main())
