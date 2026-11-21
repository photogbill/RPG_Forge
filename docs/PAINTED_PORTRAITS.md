# Portraits painted over the bodies (BUILD 93)

A portrait taken from a made body (`docs/MODEL_PICTURES.md`) is a true picture of that body, and too crude for a
dialogue box: the bodies were made to be seen small. But each body was made from a picture that already has the face,
and the model that painted that picture can take a reference picture and a sentence. So the portrait is painted again
from what the forge already has. Nothing is downloaded.

Code: `forge/threed/portraitpaint.py`, the plug-in `forge/plugins/portraitpaint.py` (job type `portrait_paint`, a GPU
job; fields in `docs/JOB_TYPES.md`). It builds on the same-person job (`forge/threed/same_person.py`, BUILD 74).

## What to double-click

`portraits_painted.bat` — takes any body portrait that is missing (Blender, on the processor), then paints on the
graphics card. **It waits its turn for the card**, between two of the world queue's models, and holds it for the few
minutes the whole batch takes; the queue waits and carries on by itself. ComfyUI must be answering.

Run it again any time: only a name whose body portrait is new is painted. `portraits_painted.bat again` paints all.

Results, in `out/pictures/<game>/portraits_painted/`:

| File | What it is |
|---|---|
| `portraits_painted_sheet.png` | one line a name: the body portrait, then every candidate with its two numbers; the proposed one in amber |
| `<name>.png` | the proposed one, 768, on its own dark ground |
| `384/<name>.png` | the same at 384 |
| `candidates/<name>__<way>__<seed>.png` | every candidate, 1024 |
| `<name>.json` | what it was painted from, every candidate's numbers, which is proposed and why |

Each name is also a forge job with its own `prov.json` (the words, the references, the model's licence line and the
body's), so it goes through Review like any other picture. **Nothing here is approved, and nothing is put into a game.**

## The three ways

All three are FLUX.2 [klein] 4B's own reference editing (Apache-2.0) through ComfyUI's core `ReferenceLatent` node —
distilled, four steps. A second reference is a second node on the same line.

- **over** — the body portrait alone is the reference: "the same person, changed from a rough 3D model into a real
  photograph … keep the pose, the framing, the hair and its colours, the clothes and the direction of the light". The
  plainest paint-over. Its weakness: the only face it has seen is the crude one.
- **picture** — the picture the body was made from, alone: the true face, small, on a whole figure; the framing and the
  light are asked for in words. Its weakness: nothing ties it to the body portrait's pose and light, so a set of them
  may not sit together.
- **both** — the body's picture first (the face, the hair, the clothes), the body portrait second (the pose, the
  framing, the light); the sentence names each one's part as "image 1" and "image 2", as the model's makers advise.
  What the build expects to win; the first run is what says so. If two references turn out not to work on this
  ComfyUI, the other two ways still stand.

Two seeds each, so six candidates a name; two when a body has no picture of its own (then only **over** can be made).
Every new picture starts "Fantastic Realism, Hyperrealistic," — the style start every new picture of a person starts
with. The light is the portrait rule's: one warm key close to the face, falling to dark, a faint rim; the rim has a
colour's name only for a character who owns one (`rim` in the game's `portraits.json`).

## What the two numbers are — and are not

Every candidate is measured against the body portrait:

- **layout** — how alike the two pictures are once both are blurred to 32 × 32: the same light and dark in the same
  places (1.0) or not (0). Brightness as a whole does not count. Low when the picture was reframed, re-posed or lit
  from another side (the **picture** way usually is: nothing told it the framing but words).
- **colour** — the figure's colour, patch by patch, without its brightness (light is the painting's to set). Low when
  the hair or the clothes changed colour.

They are **rough tripwires**, and their two limits (`layout_min` 0.5, `colour_min` 0.6) are guesses until a first real
run has been looked at. They cannot say it is the same face: no face-likeness model with a licence a game may
use is on the disk (`docs/EDITING_MODELS.md`). One candidate a name is *proposed* by them — the best of those that
held both, a near tie going to the way that used most — so the .bat ends with a usable set. The eye decides:

    portraits_painted.bat pick <name> <way> <seed>        (no card: it copies what is already painted)

## What a game says (`games/<id>/pictures/`, proposal files)

`portraits.json` (BUILD 91) names the portraits, their bodies and a rim colour. Optional, `portraits_painted.json`:

    {"skip": {"<name>": "why this one is left as it is"},
     "ways": ["over", "both"], "seeds": [1001, 2002],
     "names": {"<name>": {"who": "a boy of ten", "also": "…", "ways": […], "seeds": […], "pick": "<way>__<seed>"}}}

- `who` — a few plain words a small picture may not carry (an age, above all: a child painted from a whole figure
  drifts older).
- `pick` — the candidate to propose, whatever the numbers say (read when a name is painted; for one already painted,
  use the `pick` command above).
- `skip` — a name with nothing to paint (a figure a shader draws, say).

## What it does not do

- It does not put a portrait into a game: Review and delivery, as ever.
- It does not make moods or mouth shapes. Those are the same-person job's `masked` way on a painted portrait, once one
  is approved — the mouth, or the mouth and brows, repainted and everything else proven unmoved.
- It does not start by itself and a session never starts it: it is a job on the graphics card.
