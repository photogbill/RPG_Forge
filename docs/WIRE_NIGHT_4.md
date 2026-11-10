# Wiring left from Night 4 — do these with an EMPTY queue (worker stopped, `jobs/pending` empty)

The worker was running all of Night 4 (the FLUX sprite bake-off), so Part B was not done. Everything Night 4 built is
a plug-in, a new file, or a non-worker file (cli, ui, manifest, export). These items touch files the running worker
holds or reloads. Run `python -m pytest` before and after (Night 4 ended at **189 green**).

## W1–W3 — unchanged from `docs/WIRE_NIGHT_3.md`

Do them exactly as written there (`scene_kit big: true`, `scene_layers fill: "inpaint"`, `prov.json` carries the
prompt library), with the tests named there.

## W4 · `brief missing` / `produce plan` draft big maps as one kit (follows W1)

- `forge/brief_missing.py` `draft()`: `"type": "scene_big" if big else "scene_kit"` → always `"scene_kit"`, with
  `"big": True` when big. `produce plan` reuses brief's drafts, so it follows with no change of its own.
- Test: `tests/test_brief_missing.py` (`by["street"]["type"] == "scene_kit"` and `by["street"]["big"]`).

## W5 · `character` inheritance into `submit` proper (retire the shim)

- `forge/cli.py` `cmd_submit()`: right before the `_pl.prepare(...)` call, resolve characters on the merged jobs:
  `from .night4 import characters as _ch, charset as _cs` and for each `{**_d, **j}`:
  `_cs.expand_set(cfg, job, game)` if `job["type"] == "character_set"`, elif `job.get("character")`: `_ch.resolve(cfg, job, game)`.
  Refuse the file on `CharacterError` / `CharsetError` like a `PromptError`.
- `forge/cli_night4.py`: delete `"submit": cmd_submit` from `COMMANDS` (keep the function for one release, unused).
  `produce.queue()` and `feedback.draft_action()` then call `cli.cmd_submit` / the queue directly.
- Tests: `tests/test_night4_characters.py::test_submit_shim_resolves_characters` → point it at `cli.cmd_submit`
  (monkeypatch `Queue.submit_batch` to capture).

## W6 · the worker's log rolls at midnight (3B surprise)

- `forge/log.py` `setup()`: replace the plain FileHandler with one that reopens `forge_<date>.log` when the date of the
  record changes (subclass `logging.FileHandler`, override `emit` to compare `datetime.now().date()` with the open
  file's date). Needs a worker restart to take effect.
- Test: a handler with a fake clock writes two records on two dates into two files.

## W7 · job ids in local time when made in the Linux VM (3B surprise)

- `forge.json` gains `"timezone": "America/New_York"`. `forge/config.py` `load()`: when `os.name != "nt"` and the key is
  set, `os.environ["TZ"] = tz; time.tzset()` — every `datetime.now()` (queue ids, logs, reports) is then local. No
  change on Windows (already local). Test: load with the key under a monkeypatched `os.name`, check `time.tzname`.

## W8 · the disk guard inside the worker (so it works without produce_watch.bat)

- `forge/queue.py` `run_worker()`: every 5 minutes (keep a `last_guard` time), `from .night4 import guard; guard.check(cfg)`
  — needs the cfg passed in (add a `cfg=None` parameter; `cmd_worker` passes it). The guard only moves pending files;
  the job being rendered finishes.
- Test: `run_worker(..., once=True)` with `free_gb` monkeypatched under the limit → pending moved to paused.

## Contract questions for the game session (not wiring — answers needed)

1. **Towns:** `export_wanted.py` reads `town`, `era`, `state`, `state_of` from each map file and `look`, `fate`,
   `enclaves` from `project/data/towns.json` (see its docstring for the shape). Confirm or rename (one place each).
2. **Validator:** the export prefers `project/data/art_needs.json` (`{"items": [{name, kind, path, target_size,
   name_in_game, description, notes}]}`) if the game writes one (game plan 27 §3.1). Confirm the name.
3. **Icons:** every item in `items.json` is now a wanted icon; an item with no `icon` field is proposed at
   `res://assets/icons/<id>.png` with `referenced: false`. The game must add the field (or load that path) to show it.
4. **Sarah's sets:** the game has one field sheet `placeholder/hero_sarah` (and `hero_sarah_light`). Warrior Sarah needs
   a slot of its own; is `hero_sarah_light` the Part 1 hologram (a third variant of Sarah in the registry)?
5. **Playtest notes:** `feedback_in` reads `playtest/art_feedback.json` as `{"entries": [{map, state, files, note, shot,
   time, tester}]}` (a bare list works too); `shot` relative to `playtest/`.
