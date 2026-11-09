# For Fable — the forge pieces are in place (2026-11-09)

William asked that you design today's forge test run (its prompts are art decisions) and then use F1–F4 to paint the
first hour's rooms. Everything you need is built and tested against a fake ComfyUI; nothing has rendered on the GPU
yet. Full detail: `docs/HANDOFF_FORGE_2026-11-09.md`. How to drive it: `docs/CLAUDE.md` (last section). Fields:
`docs/JOB_TYPES.md`. Templates: `jobs/templates/`.

## Before the test run (William, once)

`pull_quality.bat` → `install_comfy_faces.bat` → (optional, depth only) `install_comfy_aux.bat` → restart
`run_worker.bat` → `doctor.bat`. Doctor lists which graphs/stages this ComfyUI can run and any model the queue is missing.

## What the test run should exercise (one small job each is enough)

- [ ] `scene_paint`, SDXL, `variants: 2`, default `refine` → 1920×1080 `scene_N.png` + `raw_N.png` + contact sheet. Compare raw vs scene: does the refine pass add detail or drift?
- [ ] `scene_paint` with `refine: false`: the plain upscale, for the comparison above
- [ ] `scene_paint` with `target: [2560, 1080]`: the scrolling-street size
- [ ] `scene_paint` with people in frame and `face_fix: true` (try `{"denoise": 0.3}` vs `0.5`)
- [ ] `scene_paint` with `freeu: true`: same seed as a plain one, to judge it
- [ ] `repaint` from a greybox with `denoise: [0.45, 0.55, 0.65]` and `control: {"type": "canny", "strength": 0.6}`: the contact sheet shows a `layout` score per value. The game's `tools/greybox_to_painted.py` makes `assets/scenes/<map>_greybox.png`; until it has run, any flat-colour layout PNG will do
- [ ] the same repaint with `control` removed: how far the layout drifts without it
- [ ] one `scene_paint`/`repaint` with `graph: "flux2_klein"` (klein 4B is Apache-2.0) if those files are pulled
- [ ] `upscale` of one existing bake-off render to `fit: [1920, 1080]`
- [ ] `icon` with `variants: 3`, and `sleeve` in both layouts
- [ ] a `pipeline` (template: render → upscale → palette_snap)
- [ ] `approve --dry-run` on the best result, then a real `approve` into `scenes/<map>`. **This needs a commercial-OK checkpoint** (below)

`review.bat <batch>` builds the comparison page (borders: green = every model commercial-OK, red = non-commercial, grey = unknown).

## Decisions that are yours (the forge only carries defaults)

Refine denoise (0.3 default) and whether it stays on · when to use `face_fix` and at what denoise · ControlNet strength/end
for repaints · the scenes checkpoint and LoRA (`checkpoints_by_job` / `loras_by_job` in `forge.game.json` — `scene_paint`,
`repaint`, `icon`, `sleeve` read their own type's entry) · the `style_prefix` · the real prompts in the drafts.

## Licence state — read before approving anything

- **ArtUniverseSDXL_v8 (the scenes default) has no licence on record**, so `approve` refuses everything it makes until William
  checks its Civitai page and runs `licence.bat`. `sd_xl_base_1.0` (RAIL++-M), FLUX.2 klein 4B and FLUX.1 schnell (Apache-2.0)
  are approvable today. Every Civitai LoRA in a shipped picture needs the same check.
- William's rule: **non-commercial is a no-go.** No NC model is registered as a default; don't introduce one.

## Drafts waiting for prompts

`brief.bat maps` / `sleeves` / `icons` writes `games/turing_accords/batches/draft_*.json`: one job per map (scene_paint at the
map's ×3 size, or a canny-locked repaint once its greybox exists), per record (159 sleeves, titles and singers filled in), and per
item (93). The prompts are just the game's notes or placeholders. Write each one (from the lyrics, for sleeves), delete
`"_draft"`, then submit. `wanted.bat --missing` lists all 275 wanted files with their target sizes.

## One thing for the game session

`make_placeholders.py` rewrites every placeholder PNG, so it would overwrite approved art (the forge reports such files as
*stale*). Ask the game session to make it skip any file that has a `project/assets/_provenance/<name>.json`.
