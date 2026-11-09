# Working the forge as an AI assistant

This file is the hand-off for an assistant (Claude, or any agent) that can read and write the repo
folder but cannot run the GPU itself. It is written so a fresh session can drive the forge from this
page alone.

## What you can and cannot do

- You **can**: write job and batch files into `jobs/pending/`; read `jobs/done/`, `jobs/failed/` and
  `out/<id>/`; look at `out/<id>/contact.png` (that is how you grade a batch); run the CPU side yourself
  (`python -m forge worker --once` with no GPU) if you have Python where the files are; edit
  `games/<game>/forge.game.json` and batches; add palettes; regenerate docs.
- You **cannot**: run diffusion. GPU jobs wait until the person starts `run_worker.bat`. Say so when you
  queue them ("queued 21 cards; they'll render when the worker is up").
- You **must**: keep every output's `prov.json` with it when you copy approved assets into a game; put
  only `commercial_ok` models in shipped-asset jobs (`models/models.json`); never write outside the repo
  folder or the game's own asset folder.

## The loop, concretely

1. **Brief → batch.** Turn a design sheet into a batch file under `games/<game>/batches/`. One job per
   asset, `name` = the asset's slug, `prompt` = the picture in plain words (subject, action, light,
   mood); do not restate the style — `style_prefix` in the game config carries it. Set `variants` 2–4
   when you want a choice; 1 when the brief is exact.
2. **Submit.** `python -m forge submit games/<game>/batches/<batch>.json` — or, with no Python at hand,
   write the job files straight into `jobs/pending/` following `docs/PROTOCOL.md` (ids optional).
3. **Wait for the worker.** Check `jobs/done/` and `jobs/failed/`. A failed job's `error` tells you why
   (missing model, ComfyUI down, bad input path); fix and resubmit — never silently drop it.
4. **Grade.** Open `out/<id>/contact.png`. Judge against the brief: subject right? read at target size?
   palette holding? composition clear at 288×162? Write the verdict in one line per card.
5. **Correct.** Re-queue only what missed, with a changed prompt phrase or a fixed `seed` from the
   variant that was close (seeds are in `prov.json`). Same `name`, new job → a new id; the old stays.
6. **Approve.** Copy the approved file + its `prov.json` into the game's asset folder (for the Turing
   Accords game: `project/assets/<kind>/…` plus `project/assets/_provenance/<name>.json`). Record what
   was approved in the batch file's `approved` list so the next session knows.

## Committing

You cannot push (git credentials live on the person's machine). Whenever you change files in the repo,
write **`COMMIT_MESSAGE.txt`** at the repo root — a one-line title, a blank line, then what changed and
why, ending with your `Co-Authored-By` line — and tell the person to run `push.bat`. The script commits
with that file as the message, pushes, appends it to `CHANGELOG.md` and keeps it as
`COMMIT_MESSAGE.last.txt`, so the next session can read what the last push said. If a
`COMMIT_MESSAGE.txt` already exists when you start, the last change has not been pushed yet: append to
it rather than overwrite it.

## Writing prompts that work

- Say what is *in* the picture and where the light comes from; one sentence, concrete nouns. The
  game's `style_prefix` adds the medium ("painterly, muted palette, soft edges, 16:9 scene card").
- For a card series, keep the camera consistent across the set ("medium-wide, eye level") and vary only
  the scene — the set then reads as one artist's work.
- Portraits: one base description (the character brief) and short expression phrases ("listening,
  slight smile", "eyes down, grief") — the handler keeps the seed, so the face holds.
- Props: name the object, its era and material, and say "single object" — the handler adds the key
  background and the isolation words.
- Tiles: name the surface and the scale ("cracked asphalt, top-down, one square metre") — the handler
  adds the seamless/top-down words.

## Reading results

`out/<id>/` — `card.png` (final), `raw.png` (the render before downscale/snap — keep for a re-snap
with a new palette), `contact.png` (variants), `prov.json`, `report.json` (palette/colour counts for
CPU jobs), `job.json` (receipt with timings). `jobs/failed/<id>.json` — `error`, `traceback`.

## Where the Turing Accords pieces are

- Game config: `games/turing_accords/forge.game.json` (palette resurrect-64 until the palette test is
  judged; style prefix; card size 288×162; tile 32; hero cell 48×72).
- First batch: `games/turing_accords/batches/gate_law_cards.json` — the 21 vignette cards of
  `D:\Turing Accords Game\Set_Pieces\IV-T3_Gate_Law.md`; approved cards go to
  `D:\Turing Accords Game\project\assets\vignettes\gate_law\NN_slug.png` (same names as the placeholders,
  so the storyboard sheet picks them up with no edit).
