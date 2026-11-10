# The queue protocol

Everything in RPG_Forge is a file in one of these folders. This document is the contract; the code
(`forge/queue.py`) implements it; nothing else needs to be known to drive the forge from outside.

## Folders

| Folder | Who writes | Meaning |
|---|---|---|
| `jobs/pending/<id>.json` | submitters | work to do, oldest first (ids sort by time) |
| `jobs/running/<id>.json` | a worker | claimed; `started_at` added |
| `jobs/done/<id>.json` | a worker | finished; `result` added |
| `jobs/failed/<id>.json` | a worker | failed; `error` + `traceback` added |
| `jobs/templates/*.json` | the repo | one example per job type (copy, edit, submit) |
| `out/<id>/` | a worker | the outputs: images, `contact.png`, `prov.json`, `report.json`, `job.json` (the receipt) |
| `logs/forge_YYYY-MM-DD.log` | workers | everything that happened, DEBUG level |

## Job file

```json
{
  "type": "scene_card",              // required — one of docs/JOB_TYPES.md
  "name": "gate_law_01_ribbon",      // recommended — letters, digits, - _ . ; becomes part of the id
  "game": "mygame",                 // optional — pulls palette/style/sizes from games/<game>/forge.game.json
  "batch": "gate_law_cards",         // optional — set automatically when submitted in a batch
  "prompt": "…",                     // type-specific fields follow
  "seed": -1                         // -1 = random; the chosen seed is recorded in prov.json
}
```

Unknown fields are kept (and passed to the handler), so a job can carry notes — e.g. `"brief": "card 01 of
Set_Pieces/IV-T3_Gate_Law.md"` — that come back in the receipt.

### Id

`YYYYMMDD-HHMMSS-<name>-<4 hex>`. Submitters may set `id` themselves (must be unique); otherwise the
queue assigns one. A folder listing of `jobs/done/` is therefore a timeline.

### Batch file

```json
{"batch": "intro_cards", "defaults": {"type": "scene_card", "game": "mygame"},
 "jobs": [{"name": "01_ribbon", "prompt": "…"}, {"name": "02_garage", "prompt": "…"}]}
```

`defaults` are merged under every job. `python -m forge submit batch.json` (or drag onto `submit.bat`).

## Claiming and finishing

- A worker lists `pending/`, takes the oldest job it can run (GPU types need the GPU worker), and moves
  the file to `running/` with `os.replace` — atomic, so two workers never take the same job.
- The handler writes to `out/<id>/` only. On success the job file moves to `done/` with `result`
  (small: file names, counts, seed, seconds). On an exception it moves to `failed/` with `error` and the
  Python traceback — the worker keeps going.
- `out/<id>/job.json` is a copy of the final job file: the receipt lives with the outputs.
- If a worker dies mid-job, `python -m forge requeue` moves `running/` back to `pending/`.

## Settings resolution

For fields like `palette`, `style_prefix`, `card_size`, `negative`, `workflow`, `checkpoint`:
**job field → `games/<game>/forge.game.json` → `forge.json` defaults**. So a game sets its look once
and jobs stay short; a single job can still override anything.

## Provenance (`prov.json`)

Written by every handler. GPU jobs record `engine`, `workflow`, `checkpoint`, `model`, `license`,
`commercial_ok`, `seed`, size, steps, cfg, the full prompt (with the style prefix) and the list of post
steps; CPU jobs record the op and its inputs. Keep these with the assets you ship — together they are
the AI-content disclosure and the licence audit (`docs/LICENSING.md`).

## Review loop

A contact sheet is written whenever a job produces more than one image (and `contact_sheet` makes one
for any set of files). The intended loop: submit → look at `out/<id>/contact.png` → write the next job
with what to change (a different seed, a phrase added, a crop) → approved files are copied into the
game's asset folder *with their `prov.json`*. Approval is a human (or assistant) act; the forge never
copies into a game by itself.
