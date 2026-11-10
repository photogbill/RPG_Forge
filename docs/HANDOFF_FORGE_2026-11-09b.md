# Hand-off — RPG_Forge, 2026-11-09 session 2 (Opus: N1–N9; N8 built, then cut)

Plan: `docs/ROADMAP_NIGHT_2.md §2b`. **Tests: 64 → 98, all green** (`python -m pytest`; the GPU paths are tested against a
fake ComfyUI). **The tools test (`tools_v1`) ran on the real GPU first: 13 of 13 done, 0 failed** — nothing from last
session needed fixing. The queue was empty after it, so everything below is **wired into the live handlers** (no stubs
except where noted). GPU proof of N1–N3: see "Proven on the GPU" at the end.

## Contract note (read first — for the game session)

The six-file contract is unchanged. One addition outside it: `scene_layers` / `scene_kit` also write
`<id>_mid_alpha.png` — the mid plane's own pixels (depth ≥ the back cut, soft edge). Reason: the contract keeps the
painting as an **opaque** mid plane, and an opaque mid plane hides `_back` completely, so the far plane can only show
at the frame edges while the camera slides. If the game wants real depth separation between back and mid, give the
mid plane this alpha. Nothing breaks if the game ignores it. The `_slide.png` previews use it.

## Built

| Item | What | Where |
|---|---|---|
| **N1** depth + normals | `depth_map` GPU job (Depth Anything V2 **Small** only — the node's own default is Large, CC-BY-NC; the graph builder refuses to run without naming Small); 16-bit output, white = near, resampled to the input's exact size. `normal_map` gains `source: luminance|depth`, `depth`, `detail` (whiteout blend of luminance normals for brush texture), a lit-from-the-left preview and a side-by-side contact sheet | `forge/ops/depth.py`, `forge/jobs/scene.py` |
| **N2** `scene_layers` | depth cuts (`auto` = 2-threshold Otsu on the depth histogram, or `[a, b]`), soft over-plane alpha, push-pull hole fill for the back plane (deterministic), overscan by reflection, planes < 2 % dropped with a note, `layers.json` (cuts, parallax 0.94/1.0/1.06, coverage), `_slide.png` (±40 px; magenta would be a hole). `fill: "inpaint"` falls back to extend with a note (not built) | `forge/ops/layers.py` |
| **N3** `scene_kit` | one job → paint/repaint → depth → normals → glow → layers; the six slot files at the top of `out/<id>/`; one contact sheet; one prov whose licence chain includes the depth model. `brief maps` now drafts `scene_kit` jobs. Template `jobs/templates/scene_kit.json` | `forge/jobs/scene.py`, `forge/brief.py` |
| **N4** `approve --set` | `export_wanted.py` lists the five companions per map (`optional`, `set_of`, `_back` target wider by 96 px); `approve <id> --as scenes/<map> --set [--dry-run]`: one licence check, all-or-nothing (licence, sizes, paths checked before anything is copied), one provenance file per slot, backups as before. `wanted --missing` hides the optional slots | `forge/manifest.py`, `games/turing_accords/export_wanted.py`, `approve.bat` |
| **N5** no double runs | `bakeoff submit` skips cells (suite · category · prompt · checkpoint · LoRA · seed · type · tool fields) already done/pending/running/paused; failed cells re-queue; `--force`. `submit --skip-done` for plain batches. `bakeoff_tonight.bat` submits the tools test with `--skip-done` and ends with `eta` | `forge/dedupe.py`, `forge/eta.py`, `eta.bat` |
| **N6** detail crops | `bakeoff report <suite> --detail-at <prompt>=x,y[,size]` (saved, kept by later reports) and `--detail-auto` (largest face via Impact Pack nodes, only if ComfyUI is up; manual wins) | `forge/detail.py` |
| **N7** dashboard | `ui.bat` → http://127.0.0.1:8765: counts, ETA, rendering now, batch bars, newest pictures (licence border, job-type edge, click to zoom), failed jobs + Retry, Pause/Resume, Approve (dry run → Confirm; set approval when the job is a scene_kit; refusals in plain words; licence conditions shown). Stdlib only, 127.0.0.1, POSTs need `X-Forge: 1`; every action logged | `forge/ui.py` |
| **N8** Krea 2 | **CUT** (William, 2026-11-09): built and tested, then removed when the Stable Yogi fine-tune's "commercial use by permission only" came up — "if Krea 2 has that license, we won't use it period". Removed: the graph, its wiring, the doctor check, the registry entries, forge.json `comfy.krea2`, the krea2_v1 suite. Kept: generic `licence_condition` printing in `approve` / `licences`; the scanner's Krea 2 detection (so `models unusable` names Krea files for deletion). Note for the record: the Krea 2 *base* licence (Community License v1) differs from the fine-tune's — commercial use allowed under US$1M/year revenue | — |
| **N9** small things | (a) `licence.bat` with no arguments asks one question at a time, offering the unknown-licence models; (b) `doctor` lists every model with no licence that a job used; (c) `models unusable` → `out/unusable_models.md` (report only); (d) `review` shows the detail crop beside the thumbnail; (e) `bakeoff_tonight.bat` prints the total and an ETA | `forge/cli.py`, `forge/doctor.py`, `forge/model_report.py`, `forge/review.py` |
| fixes | `test_doctor_shapes_and_queue` used the real model folders (failed once William pulled the models); the scanner called FLUX.2 klein and FLUX.3 files "flux1" (now uses ComfyUI's own detection keys) and did not know Krea 2 | `tests/test_manifest.py`, `forge/ops/safetensors_meta.py` |

## Try each one

- `submit.bat jobs\templates\scene_kit.json` → `out\<id>\contact.png`, then `approve.bat <id> scenes/<map> --set --dry-run`
- `submit.bat jobs\templates\depth_map.json` (edit the input) · `jobs\templates\scene_layers.json`
- `ui.bat` — the dashboard
- `eta.bat` — how long the queue will take
- `bakeoff_tonight.bat` twice — the second run queues 0 new
- `python -m forge bakeoff report finish_v1 --detail-auto` (ComfyUI running) or `--detail-at juke_joint=0.4,0.35`
- `python -m forge models unusable` · `licence.bat` (no arguments)

## What William needs to know

1. **Krea 2 is out of the forge.** The Stable Yogi checkpoint was deleted; `cinematicFantasy_v1.safetensors` (a
   Krea 2 LoRA, 0.2 GB) is still in `lora models\` with nothing that can use it — `models unusable` lists it.
2. **`models unusable`:** 6 files no graph can run (21.9 GB: the MOSS files, the FLUX.3 klein, two LoRAs whose
   architecture the scanner can't read); 3 non-commercial by their names (FLUX.1 dev derivatives, the 9B klein — 47 GB,
   experiments only); 30 still need a licence check. Nothing was deleted.
3. **`amano_yoshitaka_xl.safetensors`** is in the LoRA collection and in the bake-offs: a LoRA named after an artist.
   Your art-direction rule is not to generate in a named artist's style. Your call whether it stays in the suites.
4. **The public repo was missing `forge/engines/`** (the ComfyUI driver and every graph builder): `.gitignore`'s
   `engines/` line, meant for the ComfyUI install, matched it too. Fixed to `/engines/`; the next `push.bat` uploads
   them. Until then a fresh clone of the repo cannot render.
5. **After adding a job type, restart `run_worker.bat`.** Code fixes reach a running worker; new job types don't (the
   worker built its type table at start).

## Stubbed / not done

- `scene_layers` `fill: "inpaint"` (GPU inpaint of the back plane) — falls back to `extend` with a note.
- F12 (turnaround → rig), F13 (MOSS-Image — licence still unknown), F14 (IP-Adapter) — unchanged, still P2.

## Proven on the GPU (batch `night3_checks`, after the worker restart)

| Check | Result |
|---|---|
| c1 depth + normals (gas station) | 16-bit depth 1920×1080, white = near (bottom 10 % ≈ 0.83, top ≈ 0.0; ~50 000 levels); normals from depth vs luminance on one sheet |
| c2 layers (street 2560×1080) | auto cuts 0.19 / 0.53; back 2656×1080 (overscan 48), over RGBA; slide preview: no holes |
| c3 `scene_kit` (gas station) | all six slot files, painting 1920×1080, `_back` 2016×1080; licence chain ArtUniverse + RealESRGAN + Depth Anything V2 Small, commercial OK |

Two fixes came out of looking at it (both in `forge/ops/depth.py`, tested): **de-banding** — ComfyUI saves depth as
8-bit, so floors arrive as terraces that printed as contour lines in the normals; a blur of ≥ 3 px (at 1080p, scaled)
now runs before the gradient. **`flatten`** (default 0.85) — a receding floor read as one big slope; the depth's trend up
the screen is removed only where a pixel is ground, so upright objects keep their shape and nothing gets a halo.
Side by side: `out/_tests/flatten_compare_v5.png`. Whether 0.85 or 0 looks better under real lights is Fable's / William's
eye in Godot — reflections on wet ground show as soft bumps either way (that is the depth model reading the reflection).

`approve --set --dry-run` could not be proven from the Linux VM (it cannot resolve `D:\` paths and the game folder is not
connected); run `approve.bat 20261109-205640-c3_n3_kit_gas_station-f6be scenes/bills_house --set --dry-run` on the PC
(after `wanted.bat --refresh`) — a dry run copies nothing.
