# Workflows

ComfyUI **API-format** graphs with `{{placeholders}}`. The driver (`forge/engines/comfy.py`) fills them
and queues the result; nothing else in the forge knows which model is behind a workflow.

| File | Model family | Status |
|---|---|---|
| `txt2img_sdxl.json` | SDXL checkpoints (base 1.0, Juggernaut, Illustrious, pixel-art fine-tunes) | works; the default |
| `txt2img_flux2_klein.json` | FLUX.2 [klein] 4B (Apache 2.0) | **add by export** — see below |
| `edit_qwen_image.json` | Qwen-Image-Edit (reference image + instruction; pose sheets with the Spritely LoRAs) | **add by export** |

## Adding one

1. In ComfyUI, build the graph once by hand with the model loaded (the model's own card usually ships a workflow).
2. Settings → *Dev mode* → **Save (API format)** → drop the file here.
3. Replace the literal values with placeholders: the positive text → `"{{prompt}}"`, negative → `"{{negative}}"`,
   seed → `"{{seed:int}}"`, size → `"{{width:int}}"` / `"{{height:int}}"`, steps → `"{{steps:int}}"`, cfg → `"{{cfg:float}}"`,
   the checkpoint/UNET file → `"{{checkpoint}}"`. A string can mix text and placeholders (`"pixel art, {{prompt}}"`).
4. Keep exactly one `SaveImage` node (the driver collects every output image).
5. `python -m forge validate-workflow <name>` checks that every placeholder the handlers send is present.

Placeholders the handlers always send: `prompt negative seed width height steps cfg checkpoint batch`.
Image-editing handlers also send `image_path` (an uploaded input) — see `docs/JOB_TYPES.md`.
