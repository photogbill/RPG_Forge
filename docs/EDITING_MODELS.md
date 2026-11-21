# Editing models on the disk — what each can take (BUILD 74 part 1)

*Opus, 2026-11-17, read from `D:\RPG_Forge` (models/, flux_models/, sdmodels/, engines/ComfyUI). Nothing was started.
"Licence" says where it was read: a licence file on the disk, the forge's own record (`models/models.json`,
`models/licences.json`), or the model's own page on the web that night. Where no licence file is on the disk, it says so —
William's rule is to read the licence yourself, and a file on the disk is the only copy that cannot change.*

## What can take a reference picture plus an instruction, a mask, a pose guide

| model | file | licence (as read) | (a) reference + words | (b) a mask | (c) pose / depth guide | ComfyUI nodes, installed? |
|---|---|---|---|---|---|---|
| FLUX.2 [klein] 4B (distilled) | `models/diffusion_models/flux-2-klein-4b.safetensors` | **Apache-2.0** — Black Forest Labs' model page and blog, read 2026-11-17 (the 4B models are Apache-2.0; the 9B are the FLUX Non-Commercial Licence). No licence file on the disk. The forge's record: commercial OK. | **yes** — single- and multi-reference editing in the same checkpoint | through a composite afterwards (the forge's `masked` keeps outside pixels by compositing) | no ControlNet for FLUX.2 on the disk | `ReferenceLatent` is in ComfyUI's core (`comfy_extras/nodes_edit_model.py`, on the disk); the rest is the forge's `flux2_klein` graph |
| FLUX.2 [klein] 4B base | `models/diffusion_models/flux-2-klein-base-4b.safetensors` | Apache-2.0 (as above) | yes (20 steps, cfg 5) | as above | no | as above |
| RealVisXL V5.0 (SDXL) | `sdmodels/RealVisXL_V5.0_fp16.safetensors` | CreativeML Open RAIL++-M (SDXL 1.0's licence; the RAIL++ text is on the disk at `docs/model_licences/CreativeML_Open_RAIL++-M_SDXL_1.0.txt`). The model's own page names openrail++; no copy of that page on the disk. | image-to-image only (no instruction) | **yes** — `InpaintModelConditioning` + `DifferentialDiffusion` (core) | **yes**, with the union ControlNet | all core |
| xinsir ControlNet union SDXL promax | `models/controlnet/xinsir-union-sdxl-promax.safetensors` | Apache-2.0 per its model page; the forge's record: commercial OK. No licence file on the disk. | — | — | **yes** — openpose, depth, canny … (`SetUnionControlNetType`, core) | core; the pose/depth preprocessors are in `comfyui_controlnet_aux` (Apache-2.0, `LICENSE.txt` on the disk) |
| FLUX.1 schnell (fp8) | `models/diffusion_models/flux1-schnell-fp8-e4m3fn.safetensors` | Apache-2.0 (forge record) | no reference editing | composite only | no | — |
| SDXL base 1.0, ArtUniverse v8, SDVN6-RealXL-Detailface | `sdmodels/` | RAIL++-M (file on the disk); ArtUniverse checked by William 2026-11-09 | img2img only | yes (as RealVisXL) | yes (union CN) | core |
| moss_* (2 files) | `sdmodels/` | **unknown** — no record, no file | — | — | — | not used here; William to check or delete |
| Qwen-Image-Edit-2509 | *not on the disk* | the forge's record says commercial OK | would be (a) | — | — | not installed — named only because `models.json` lists it |

**For the faces:** `models/ultralytics/bbox/face_yolov8m.pt` (FaceDetailer's face finder; William's chosen tool) — the
Impact Pack is GPL-3.0 (`LICENSE.txt` on the disk) and the YOLOv8 weights come under Ultralytics' AGPL-3.0. They run on
this computer to make pictures; nothing of their code or weights ships in a game. **No face-likeness (embedding) model
with a commercial licence is on the disk** (InsightFace's models are non-commercial), so `guided` and `instructed` are
checked by the plain measures the gate already has — the head's proportion of the figure and the face's colour — and the
report says that is all it is.

## What this means for the three ways (part 2)

- `masked` → **RealVisXL inpainting** (photoreal, mask honoured exactly, composited back so nothing outside moves). Best
  for expressions (mouth, mouth and brows) and for arms against the body. Expected winner for 70's portrait sets.
- `instructed` → **FLUX.2 [klein] 4B with a reference latent**. The only way on the disk to make a person older or younger,
  or to turn an illustrated sheet into a photograph, with no new download. Likeness is the question the bake-off answers.
- `guided` → **RealVisXL + the union ControlNet (openpose) at image-to-image strength 0.82**, an A-pose skeleton drawn by
  the forge. Weakest at keeping a face: there is no identity adapter on the disk.

**Nothing has to be downloaded for the bake-off.** If `guided` loses on likeness, what would help is an identity adapter
under a commercial licence — to be looked for and read before anything is fetched (William pulls models himself).
