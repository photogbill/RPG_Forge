# Job types

Generated from `forge/schema.py` — do not edit by hand.

## `scene_card`  (GPU)

A painted scene card (a cutscene vignette, a location card, a record sleeve): text → image via ComfyUI → downscale to card_size → optional palette snap. Output: card.png, raw.png, prov.json.

Required: `prompt`

Optional (default): `negative` (None), `seed` (-1), `card_size` (None), `render_scale` (None), `palette` (None), `snap` (True), `style_prefix` (None), `workflow` (None), `checkpoint` (None), `steps` (28), `cfg` (6.0), `game` (None), `variants` (1)

## `concept`  (GPU)

A location concept painting — the single image a kit is derived from (the gas station at dusk, the inn's common room). Rendered large; no palette snap. Output: concept.png, prov.json.

Required: `prompt`

Optional (default): `negative` (None), `seed` (-1), `size` ([1536, 864]), `style_prefix` (None), `workflow` (None), `checkpoint` (None), `steps` (30), `cfg` (6.0), `game` (None), `variants` (2)

## `portrait`  (GPU)

A seed-locked portrait set: one seed, one base prompt, a list of expression/stance phrases; each phrase renders once with the same seed so the face holds. Output: <expr>.png ×N + contact sheet.

Required: `prompt`, `expressions`

Optional (default): `negative` (None), `seed` (12345), `size` ([768, 768]), `out_size` ([128, 128]), `palette` (None), `snap` (False), `style_prefix` (None), `workflow` (None), `checkpoint` (None), `steps` (30), `cfg` (6.0), `game` (None)

## `prop`  (GPU)

A prop sprite (gas pump, bed, counter): rendered on a flat key colour → background removed → trimmed → downscaled to target_h → palette snap. Output: prop.png (RGBA), raw.png, prov.json.

Required: `prompt`

Optional (default): `negative` (None), `seed` (-1), `size` ([768, 768]), `target_h` (64), `key_color` ('#ff00ff'), `palette` (None), `snap` (True), `style_prefix` (None), `workflow` (None), `checkpoint` (None), `steps` (28), `cfg` (6.0), `game` (None), `variants` (3)

## `tile_texture`  (GPU)

A tileable surface (asphalt, siding, grass): rendered → made seamless → downscaled to tile_size → palette snap → seam score + N jittered variants. Output: tile.png, variants.png, raw.png, prov.json.

Required: `prompt`

Optional (default): `negative` (None), `seed` (-1), `size` ([512, 512]), `tile_size` (32), `palette` (None), `snap` (True), `style_prefix` (None), `workflow` (None), `checkpoint` (None), `steps` (28), `cfg` (6.0), `game` (None), `variants` (4)

## `render`  (GPU)

A raw render with any checkpoint + LoRA chain, no post-processing — the bake-off's unit and the thing to reach for when you want to see what a model does. `graph` picks the engine graph: 'sdxl' (default; checkpoint + LoraLoader chain), 'flux2_klein' (FLUX.2 [klein] 4B: `checkpoint` is the diffusion-model file, `text_encoder`/`vae` default from forge.json comfy.flux2, `distilled` auto from the name, `cfg`/`steps` default 5/20 base or 1/4 distilled) or 'flux1' (FLUX.1 dev/schnell + fine-tunes: `clip_l`/`t5`/`vae`/`guidance` from comfy.flux1; `all_in_one` for a checkpoint with CLIP+VAE baked in; cfg is always 1). Output: render.png (+ _2…), prov.json.

Required: `prompt`

Optional (default): `negative` (None), `seed` (-1), `size` ([1024, 1024]), `steps` (25), `cfg` (6.0), `sampler` ('dpmpp_2m'), `scheduler` ('karras'), `checkpoint` (None), `loras` ([]), `clip_skip` (0), `count` (1), `style_prefix` (''), `game` (None), `meta` ({}), `graph` ('sdxl'), `text_encoder` (None), `vae` (None), `clip_l` (None), `t5` (None), `guidance` (None), `distilled` (None), `all_in_one` (False)

## `scene_paint`  (GPU)

A painted scene background at game resolution (roadmap F1): render at `size` (default 1344×768) → upscale model (`upscale`, default forge.json comfy.upscale_model = RealESRGAN_x4plus, BSD-3) → cover-fit to `target` (default the game's `scene_size` or 1920×1080; 2560×1080 for a scrolling street) → `refine` (hires-fix repaint at the final size, denoise 0.3; false to skip) → `face_fix` (Impact Pack FaceDetailer; true or {denoise, threshold, guide_size}). Optional `init` + `denoise` start from a picture (img2img), `control` {type: canny|depth|lineart|tile…, image, strength 0.6, start, end} pins the layout with the SDXL union ControlNet (canny is computed on the CPU), `freeu` true adds FreeU_V2 (SDXL). Any `graph` (sdxl · flux1 · flux2_klein). Output: scene.png, raw.png, prov.json (+ control.png, control_overlay.png, contact.png for variants). prov.json lists every model that touched the pixels and `commercial_ok`.

Required: `prompt`

Optional (default): `negative` (None), `seed` (-1), `size` ([1344, 768]), `target` (None), `crop` ('center'), `init` (None), `denoise` (None), `control` (None), `upscale` (True), `refine` (True), `face_fix` (False), `freeu` (False), `graph` ('sdxl'), `checkpoint` (None), `loras` (None), `steps` (None), `cfg` (None), `sampler` (None), `scheduler` (None), `style_prefix` (None), `game` (None), `variants` (1)

## `repaint`  (GPU)

Image-to-image from a greybox (roadmap F2): `init` is required and the painting comes back at the init's exact pixel size (stretched, never cropped) so walk polygons, doors and spawns stay valid. `denoise` (default 0.55) may be a list, e.g. [0.45, 0.55, 0.65] — one painting per value, same seed, on one contact sheet labelled with denoise and a layout-agreement score. Takes `control`, `refine`, `face_fix`, `freeu`, `upscale` like scene_paint. Output: scene[_dNNN].png, raw*.png, contact.png, prov.json.

Required: `prompt`, `init`

Optional (default): `negative` (None), `seed` (-1), `denoise` (0.55), `size` (None), `megapixels` (1.0), `target` (None), `control` (None), `upscale` (True), `refine` (True), `face_fix` (False), `freeu` (False), `graph` ('sdxl'), `checkpoint` (None), `loras` (None), `steps` (None), `cfg` (None), `sampler` (None), `scheduler` (None), `style_prefix` (None), `game` (None)

## `upscale`  (GPU)

Upscale images with an upscale model (default comfy.upscale_model) to an exact `fit` [w, h] (crop 'center' = cover-fit, 'disabled' = stretch) or by `factor` (default 2). Output: <name>.png per input. The inputs' own provenance still decides whether they can ship.

Required: `inputs`

Optional (default): `model` (None), `fit` (None), `factor` (2), `crop` ('center')

## `icon`  (GPU)

An inventory icon (roadmap F6): `prop` on a square canvas — render on a key colour → background removed → trimmed → centred on a transparent `canvas` (256 default; 512 for hi-res) with `padding` → optional palette snap. Default checkpoint/LoRA from the game's checkpoints_by_job.icon / loras_by_job.icon. Output: icon.png (+ icon_N.png, contact.png), raw*.png, prov.json.

Required: `prompt`

Optional (default): `negative` (None), `seed` (-1), `size` ([1024, 1024]), `canvas` (256), `padding` (0.08), `key_color` ('#ff00ff'), `snap` (False), `palette` (None), `graph` ('sdxl'), `checkpoint` (None), `loras` (None), `steps` (None), `cfg` (None), `style_prefix` (None), `game` (None), `variants` (1)

## `sleeve`  (GPU)

A record sleeve (roadmap F7): square art by the model (no lettering asked of it) + typography set by PIL — `title`, `artist`, optional `label` — in `layout` 'band' (a title band across the bottom) or 'corner' (stacked type in the top-left). Fonts: `font` / `font_bold` paths, else the game's assets/fonts, else a built-in fallback. Output: sleeve.png (`out_size`, default 1024), art.png, prov.json.

Required: `prompt`, `title`

Optional (default): `artist` (''), `label` (''), `layout` ('band'), `out_size` (1024), `size` ([1024, 1024]), `font` (None), `font_bold` (None), `negative` (None), `seed` (-1), `graph` ('sdxl'), `checkpoint` (None), `loras` (None), `steps` (None), `cfg` (None), `style_prefix` (None), `game` (None), `refine` (False)

## `pipeline`  (GPU)

A chain of jobs run as one (roadmap F5): `steps` is a list of job objects ({type, …}); a string '$prev.outputs[0]' (or '$prev.outputs', '$steps[N].outputs[K]') is replaced with the matching output path of an earlier step. Each step writes to out/<id>/NN_<type>/; the chain stops at the first failing step and the error names it. `game`, `batch` and `name` are passed down to every step. Needs the GPU worker only when a step does.

Required: `steps`

Optional (default): `game` (None), `contact` (True)

## `palette_snap`  (CPU)

Snap one or more images to a palette in OKLab (nearest perceptual colour), alpha preserved. Output: <name>.png per input + report.json (colour counts).

Required: `inputs`

Optional (default): `palette` (None), `dither` (None), `hysteresis` (0.0), `game` (None)

## `pixelize`  (CPU)

Turn a large generated image into pixel art: detect the pixel grid (or take `scale`), downscale cell-by-cell (mode/median/center), optional palette snap. Output: <name>.png + report.json.

Required: `inputs`

Optional (default): `scale` (None), `method` ('mode'), `palette` (None), `snap` (False), `target` (None), `game` (None)

## `remove_bg`  (CPU)

Flood-fill a flat background from the corners to alpha, trim, optionally pad to a size. Output: <name>.png (RGBA).

Required: `inputs`

Optional (default): `key_color` (None), `tolerance` (28), `trim` (True), `pad_to` (None), `anchor` ('bottom')

## `contact_sheet`  (CPU)

A labelled grid of images for review (this is how Claude looks at a batch). Output: contact.png.

Required: `inputs`

Optional (default): `cols` (4), `cell` ([288, 162]), `labels` (None), `title` (None)

## `pack_sheet`  (CPU)

Pack frames into a sprite sheet with uniform cells (row-major), e.g. 8 facings × N frames. Output: sheet.png + sheet.json (cell size, order).

Required: `inputs`

Optional (default): `cols` (8), `cell` (None), `anchor` ('bottom')

## `godot_tileset`  (CPU)

Write a Godot 4 TileSet .tres for a tile strip PNG (which tiles collide). Output: <name>.tres.

Required: `png`, `tile_size`, `blocking`

Optional (default): `res_path` (None)

## `canny`  (CPU)

Canny edges (white on black) of each input — the ControlNet canny image, computed in numpy. `low`/`high` are fractions of the strongest gradient. Output: <name>.png.

Required: `inputs`

Optional (default): `low` (0.08), `high` (0.2), `sigma` (1.2)

## `normal_map`  (CPU)

A tangent-space normal map for the game's `<id>_n.png` slot, OpenGL convention (Godot). `source` 'luminance' (F11: height = brightness) or 'depth' (N1: from a depth map — `depth` is one path per input; `detail` 0..1 blends the luminance normals back in for brush texture; `flatten` 0..1 (default 0.85) removes the depth's slow trend first so a receding floor does not read as one big slope; `smooth` (default 1.0) blurs the height first; Output: <name>_n.png, <name>_lit.png (a lit-from-the-left preview), contact.png (with source 'depth', both kinds side by side unless `compare` is false).

Required: `inputs`

Optional (default): `source` ('luminance'), `depth` (None), `strength` (2.0), `smooth` (1.0), `detail` (0.0), `flatten` (0.85), `invert_y` (False), `preview` (True), `compare` (None)

## `emissive_mask`  (CPU)

The glowing parts of each painting — bright AND saturated pixels (screens, neon, cores) plus any near `colors` — on black, for the game's additive `<id>_e.png` slot (roadmap F11). Output: <name>_e.png + report.json (fraction lit).

Required: `inputs`

Optional (default): `threshold` (0.85), `min_saturation` (0.25), `colors` ([]), `tolerance` (40), `feather` (1.5)

## `depth_map`  (GPU)

A depth map per input (roadmap N1): Depth Anything V2 **Small** (Apache-2.0 — the forge always names it; the node's own default, Large, is CC-BY-NC) through comfyui_controlnet_aux (install_comfy_aux.bat). Output: <name>_depth.png, 16-bit grey, white = near, at the input's exact size. `resolution` is the model's working size (default 1024); `invert` flips near/far.

Required: `inputs`

Optional (default): `resolution` (1024), `invert` (False)

## `scene_layers`  (CPU)

Parallax planes from a painting and its depth map (roadmap N2). `depth`: one path per input. `cuts` [a, b] (0 < a < b < 1) or 'auto' (Otsu valleys of the depth histogram). Output per input: <name>_back.png (opaque, holes filled by edge extension, wider by `overscan` px each side), <name>_over.png (RGBA, soft edge `feather` px), <name>_mid_alpha.png (extra: the mid plane's own pixels), <name>_slide.png (the planes sliding ±`preview_shift` px; magenta would be a hole), layers.json (cuts, parallax 0.94/1.0/1.06, coverage). The painting itself is the mid plane and is never changed; a plane under 2% of the frame is dropped with a note.

Required: `inputs`, `depth`

Optional (default): `cuts` ('auto'), `feather` (3.0), `overscan` (48), `fill` ('extend'), `preview_shift` (40)

## `scene_kit`  (GPU)

A whole painted scene as the game's six-file set, in one job (roadmap N3): scene_paint (or repaint when `init` is given) → depth_map → normal_map (source depth) → emissive_mask → scene_layers. Takes every scene_paint / repaint field, plus `normals` {strength, smooth, detail}, `glow` {threshold, colors, …}, `layers` {cuts, overscan, feather}, `depth_resolution`, `slot_name` (default 'scene'). Output at the top of out/<id>/: scene.png, scene_n.png, scene_e.png, scene_back.png, scene_over.png, scene_depth.png, layers.json, contact.png (painting · depth · lit · glow · planes); each step's files in NN_<type>/. One prov.json whose licence chain covers every model, the depth model included. Approve with `approve <id> --as scenes/<map> --set`.

Required: `prompt`

Optional (default): `init` (None), `denoise` (None), `target` (None), `size` (None), `seed` (-1), `control` (None), `normals` (None), `glow` (None), `layers` (None), `depth_resolution` (None), `slot_name` ('scene'), `graph` ('sdxl'), `checkpoint` (None), `loras` (None), `game` (None)

## `overworld`  (CPU)

PLANNED — pull public-domain layers (Natural Earth, TIGER, GNIS, 3DEP, NLCD), compress the scale, emit a biome/road/town map in the game's format. Submitting one today returns 'not implemented'.

Required: `region`

Optional (default): `scale` ('fe6'), `layers` (['naturalearth'])

## `filter_forge`  (CPU)

Render with Filter Forge's command-line renderer (plug-in, forge/night3b/ffdriver.py; needs forge.json tools.filter_forge.exe — the public repo works without it, the job then fails with a plain message). `filter` = path of an .ffxml (never copied — the forge stores paths), `preset` = the preset number (0 = the filter's first preset), `input` = a picture for an effect filter (omit for a texture filter), `size` [w, h] for a texture (default [1024, 1024]). A channel (normal, height, …) is a preset you save in Filter Forge with that channel chosen in its Render Channels menu: `channels` {"final": 0, "normal": 9} renders one task per channel (a list like ["final"] uses `preset`). `seamless: true` checks the preset has Seamless Tiling on (when the forge can read it) and measures the wrap seam of the result. Normal maps come out in OpenGL convention (NormalMapFlipY true; checked against the height/bump channel when one is rendered too) and are also written as <slot>_n.png. `tileable: true` (Night 4) makes every channel tile in the forge afterwards (offset + heal, the same geometry for all channels) → <file>_tile.png, measured before/after. Outputs: <slot>_<channel>.png (16-bit), <slot>_n.png, tasks.xml, render.log, contact.png.

Required: `filter`

Optional (default): `preset` (0), `input` (None), `size` ([1024, 1024]), `channels` (['final']), `seamless` (False), `slot_name` ('texture'), `normal_flip_y` (True), `bit_depth` (16), `timeout_sec` (900), `seam_limit` (1.5), `tileable` (False), `tile_band` (0.12)

## `handoff_file`  (CPU)

File a picture that came back from an outside tool (plug-in, forge/night3b/handoff_jobs.py; made by `handoff in`): `input` = the returned picture, `source_job` = the forge job it was made from, `tool` = the tool's key in the tool register (`handoff tool add`). The picture becomes this job's own output under the source's file name; provenance follows the source's models and adds the tool as a licence line. Outputs: <name>.png, contact.png (the forge's own version beside the tool's).

Required: `input`, `source_job`, `tool`

Optional (default): `slot_name` (None), `target` (None)

## `handoff_kit`  (GPU)

A scene kit rebuilt on a picture that came back from an outside tool (plug-in; made by `handoff in` when the source was a scene_kit): the returned picture is the painting; depth (Depth Anything V2 Small), normals, glow and layers are built from it with the source kit's settings. Same six files as a kit, so `kit check` and `approve --set` work on it. Provenance: the source's models + the depth model + the tool.

Required: `input`, `source_job`, `tool`

Optional (default): `slot_name` (None), `target` (None), `depth_resolution` (None)

## `inpaint`  (GPU)

Repaint only the masked part of a picture (plug-in, forge/night3/inpaint.py): `init` + `mask` (white = repaint; `mask_grow`/`mask_feather` optional) + a prompt for that part. SDXL with the job's own checkpoint (SetLatentNoiseMask; `method: encode_for_inpaint` for inpaint checkpoints). Outside the mask the output is bit-identical to the init. Outputs: inpaint.png, mask.png, contact.png (base · mask · result · difference).

Required: `init`, `mask`, `prompt`

Optional (default): `checkpoint` (None), `loras` (None), `seed` (-1), `steps` (None), `cfg` (None), `sampler` (None), `scheduler` (None), `negative` (None), `graph` ('sdxl'), `freeu` (False), `denoise` (0.9), `method` ('noise_mask'), `grow_mask_by` (0), `pad` (96), `min_side` (768), `megapixels` (1.0), `style_prefix` (None), `controlnet` (None), `canny_strength` (0.5), `mask_grow` (0), `mask_feather` (0)

## `scene_state`  (GPU)

A state of a painted room (plug-in): `base` (a painting, or a scene_kit folder) + `mask` or `greybox_base` + `greybox_state` (the mask is what changed, grown and feathered; refused over 35 % of the frame) + a prompt for only the changed part. Outside the mask the state is bit-identical to the base; for a kit, the companions are rebuilt and changed only inside the mask. Outputs: scene.png, mask.png, contact.png, difference.png (+ scene_n/_e/_depth/_over/_back/_mid_alpha for a kit).

Required: `base`, `prompt`

Optional (default): `checkpoint` (None), `loras` (None), `seed` (-1), `steps` (None), `cfg` (None), `sampler` (None), `scheduler` (None), `negative` (None), `graph` ('sdxl'), `freeu` (False), `denoise` (0.9), `method` ('noise_mask'), `grow_mask_by` (0), `pad` (96), `min_side` (768), `megapixels` (1.0), `style_prefix` (None), `controlnet` (None), `canny_strength` (0.5), `mask` (None), `greybox_base` (None), `greybox_state` (None), `threshold` (12), `grow` (24), `feather` (12.0), `max_share` (0.35), `control` (True), `companions` (True), `mask_grow` (0), `mask_feather` (0)

## `sprite_intake`  (CPU)

A character sheet from any outside tool → the game's sprite contract (plug-in, forge/night4/intake.py). `input` = the sheet (any grid, any backdrop: flat, white, painted checkerboard or real alpha; labels between rows are dropped), `character` (+ `variant`). Figures are found as connected shapes, numbered in reading order and mapped to facings/frames by `mapping` (default games/<game>/intake/<character>[__<variant>]/<sheet>.intake.json — the first run writes the forge's guess there; a person fixes it and reruns). One scale, feet on one baseline, centred on the feet. `tool` = "<name version>" of the program that made the sheet (its licence line comes from the tool register). Outputs: sheet.png (one row, 8 facings S…SE, cell 144×216 — the contract), anim.png (rows = facings, columns = frames, when there are frames), numbers.png, frames/, turntable.gif, anim_<facing>.gif, edges.md, report.json.

Required: `input`, `character`

Optional (default): `variant` (None), `mapping` (None), `tool` (None), `cell` ([144, 216]), `figure_height` (0.92), `baseline` (6), `scale` ('uniform'), `key` (None), `tolerance` (30)

## `character_set`  (GPU)

One character variant → its set (plug-in, forge/night4/charset.py): portrait moods on the variant's locked seed (same face, one `{{mood.<m>}}` block each), a battle pose (`{{pose.battle}}`), and a turnaround with the variant's sheet LoRA(s) → cut and packed through sprite_intake into the same sheet contract as a drawn sheet. Everything inherits the registry (games/<game>/characters/<id>.json); job keys win. `parts` picks a subset: ["moods", "battle", "turnaround"]. Outputs: moods/<m>.png, battle.png, turnaround.png, sheet.png (+ the intake files), contact.png.

Required: `character`

Optional (default): `variant` (None), `parts` (None), `moods` (None), `portrait_size` ([896, 1152]), `battle_size` ([832, 1216]), `turnaround_size` ([1536, 768]), `sheet_lora` (None), `sheet_lora_strength` (0.8), `mapping` (None)

## `tileable`  (CPU)

Make a texture tile seamlessly (plug-in, forge/night4/tileable.py): offset by half, heal the cross seam — inpainted on the job's checkpoint when a GPU worker runs it (`heal: inpaint`), a blend otherwise (`heal: blend`, CPU) — and verify with the wrap-seam score before/after; refused (the input kept) if it got worse. `input` = picture or a job folder. Outputs: tile.png, tiled_2x2.png, compare.png, report.json.

Required: `input`

Optional (default): `heal` ('auto'), `band` (0.12), `prompt` (None), `checkpoint` (None), `denoise` (0.6), `seed` (-1), `limit` (1.5)

## `icon_batch`  (GPU)

Many item icons in one job (plug-in, forge/night4/icons.py): `items` = [{"id", "name", "description", "category"}] (produce/brief fill it from wanted.json), one family seed per category so a category looks drawn by one hand; each is rendered square, cut out (transparent), saved at `size` and 2×. Prompt template `prompt` with {name} {description} in it (default: "{{icon.house}}, {{icon.<category>}}, {name}: {description}" — the blocks are Fable's). Outputs: icons/<id>.png, icons@2x/<id>.png, contact_<category>.png.

Required: `items`

Optional (default): `prompt` (None), `size` ([256, 256]), `render_size` ([1024, 1024]), `seeds` (None), `checkpoint` (None), `loras` (None), `steps` (None), `cfg` (None), `sampler` (None), `scheduler` (None), `negative` (None), `key` ('#ff00ff'), `tolerance` (40)

## `photo_plate`  (GPU)

One of William's photographs → a painted plate (plug-in, forge/night4/photo.py). `photo` is a PATH (never copied into the repo); it must be listed in the git-ignored games/<game>/refs.local.json with `people: none` or `people: william` (his cameo ruling) or the job refuses. img2img on the scene checkpoint at `target` with `denoise` and ControlNet depth/canny from the photo, then the kit companions (depth, normals, glow, layers) so it lights like any painted scene. Provenance: "William's own photograph" + the path.

Required: `photo`, `prompt`

Optional (default): `target` ([1920, 1080]), `denoise` (0.55), `control` ('canny'), `control_strength` (0.5), `checkpoint` (None), `loras` (None), `seed` (-1), `steps` (None), `cfg` (None), `sampler` (None), `scheduler` (None), `negative` (None), `companions` (True), `graph` ('sdxl')

## `ping`  (CPU)

Plug-in health check (forge/plugins/ping.py): writes ping.txt. If a worker runs it, that worker picks up new plug-in job types without a restart. Output: ping.txt.

Required: 

Optional (default): `say` (None)

## `scene_big`  (GPU)

A painting larger than one pass (plug-in, forge/night3/big.py): small whole-scene paint from the greybox (`init`) or prompt — or start from `source`, an existing painting — → upscale to `target` → tiled img2img refine (ControlNet tile, + canny from the greybox) → feathered merge → seam scores. Outputs: scene.png, small.png, upscaled.png, tiles/, seams.json, seam_sheet.jpg, contact.png.

Required: `prompt`, `target`

Optional (default): `init` (None), `source` (None), `size` (None), `megapixels` (1.0), `init_denoise` (0.65), `tile` ([1344, 768]), `overlap` (128), `max_step` (2.0), `denoise` (0.3), `tile_strength` (0.6), `canny_strength` (0.4), `checkpoint` (None), `loras` (None), `seed` (-1), `steps` (None), `cfg` (None), `sampler` (None), `scheduler` (None), `negative` (None), `graph` ('sdxl'), `freeu` (False), `upscale_model` (None), `controlnet` (None), `control` (None), `style_prefix` (None)

## `facings_pack`  (CPU)

Single-pose pictures → one facings sheet (plug-in, forge/ops/sprites.py): `input` = a folder of poses named by facing (…_S.png, …_NW.png) or exactly eight in S,SW,W,NW,N,NE,E,SE order. Background removed, one common figure height, feet on one baseline, centred per cell (default 144×216), `mirror` fills a facing from its opposite (['W→E']). Outputs: sheet.png (1152×216), report.json (edge touches), turntable.gif.

Required: `input`

Optional (default): `cell` ([144, 216]), `mirror` (None), `figure_height` (0.92), `baseline` (6), `key` (None), `tolerance` (28)

## `anim_preview`  (CPU)

A sprite sheet → GIF per facing (rows) and a turntable (plug-in). `input` = the sheet, `cell`, `layout` auto|rows|facings, `fps`. Outputs: anim_<facing>.gif, turntable.gif.

Required: `input`

Optional (default): `cell` ([144, 216]), `layout` ('auto'), `fps` (8.0), `turntable_fps` (2.0)

## `turnaround_split`  (CPU)

A 3- or 8-view turnaround sheet → the separate views (plug-in), cut at empty columns. Outputs: view_NN.png.

Required: `input`

Optional (default): `min_gap` (6), `min_width` (12), `key` (None), `tolerance` (28)

## `nine_slice`  (CPU)

A painted panel or frame → a nine-slice (plug-in, forge/ops/ui_pieces.py): trimmed, corners/edges detected (or `margins` {left,top,right,bottom}), centre made tileable, `key` (auto or [r,g,b]) removes a flat background first, margins snapped to a multiple of 3 (UI is 640×360 ×3), `scale` to resize. Outputs: piece.png, piece.json (Godot NinePatchRect patch_margin_*), preview.png (stretched to three sizes).

Required: `input`

Optional (default): `margins` (None), `scale` (1.0), `snap` (3), `tileable` (True), `key` (None)

## `button_states`  (CPU)

One button picture → normal / hover / pressed / disabled by tone only (plug-in). Outputs: <name>_normal.png … and states.png.

Required: `input`
