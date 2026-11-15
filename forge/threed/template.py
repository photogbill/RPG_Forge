"""ComfyUI's own image-to-3D template (Comfy-Org workflow_templates, MIT: `3d_pixal3d_trellis2_image_to_model`) turned
into the request the running ComfyUI's /prompt door takes, with what that ComfyUI says its nodes take — so it follows
whatever version is installed. One switch picks TRELLIS.2 or Pixal3D; the model not wanted is cut out before the
request is sent, so it is never loaded (and need not even be on the disk).

Copied from the first game's trellis_trial.py (2026-11-12), where it was proven at 1024 on a 16 GB card.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

TEMPLATE = Path(__file__).with_name("workflows") / "3d_pixal3d_trellis2_image_to_model.json"
MODELS = ("trellis2", "pixal3d")

# The template's own node ids (checked against the copy beside this file when it is used).
N_IMAGE, N_WHICH, N_UPSAMPLE, N_DECIMATE, N_TEXTURE, N_SAVE = 122, 316, 94, 186, 288, 322
WIDGET_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO", "COLOR", "LOAD_3D"}
CHOICE = "COMFY_DYNAMICCOMBO_V3"                                 # a choice that brings its own extra settings
SEED_WORDS = {"fixed", "increment", "decrement", "randomize"}
SKIP_TYPES = {"MarkdownNote", "Note"}


def load(path: Path | None = None) -> dict:
    return json.loads(Path(path or TEMPLATE).read_text(encoding="utf-8"))


def to_api(wf: dict, info: dict) -> dict:
    """A workflow as the ComfyUI page saves it -> the prompt its /prompt door takes."""
    links = {l[0]: l for l in wf["links"]}                       # id, from node, from slot, to node, to slot, type
    api: dict = {}
    for n in wf["nodes"]:
        typ = n["type"]
        if typ in SKIP_TYPES or n.get("mode", 0) in (2, 4):
            continue
        meta = info.get(typ)
        if meta is None:
            raise RuntimeError(f"this ComfyUI has no node called {typ} - is it up to date?")
        spec_all: dict = {}
        order: list[str] = []
        for part in ("required", "optional"):
            part_spec = meta.get("input", {}).get(part, {}) or {}
            spec_all.update(part_spec)
            names = (meta.get("input_order") or {}).get(part)
            order += list(names if names is not None else part_spec.keys())
        linked = {i["name"]: links[i["link"]] for i in n.get("inputs", []) if i.get("link") is not None}
        values = n.get("widgets_values")
        by_name = values if isinstance(values, dict) else None
        values = list(values) if isinstance(values, list) else []
        k = 0
        inputs: dict = {}
        for name in order:
            spec = spec_all.get(name) or ["*"]
            kind = spec[0]
            opts = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
            is_widget = (isinstance(kind, list) or kind in WIDGET_TYPES) and not opts.get("forceInput")
            if kind == CHOICE:
                key = by_name.get(name) if by_name is not None else (values[k] if k < len(values) else None)
                if by_name is None and k < len(values):
                    k += 1
                option = next((o for o in opts.get("options", []) if o.get("key") == key), None)
                if option is None:
                    option = (opts.get("options") or [{"key": key, "inputs": {}}])[0]
                    key = option.get("key")
                inputs[name] = key
                for part in ("required", "optional"):             # the chosen option's own settings follow it
                    for sub, sub_spec in ((option.get("inputs") or {}).get(part) or {}).items():
                        sub_kind = sub_spec[0]
                        sub_opts = sub_spec[1] if len(sub_spec) > 1 and isinstance(sub_spec[1], dict) else {}
                        full = f"{name}.{sub}"
                        if full in linked:
                            inputs[full] = [str(linked[full][1]), linked[full][2]]
                        elif isinstance(sub_kind, list) or sub_kind in WIDGET_TYPES:
                            if by_name is not None:
                                inputs[full] = by_name.get(full, sub_opts.get("default"))
                            elif k < len(values):
                                inputs[full] = values[k]
                                k += 1
                            else:
                                inputs[full] = sub_opts.get("default")
            elif is_widget:
                if by_name is not None:
                    val = by_name.get(name, opts.get("default"))
                elif k < len(values):
                    val = values[k]
                    k += 1
                    if kind == "INT" and k < len(values) and isinstance(values[k], str) and values[k] in SEED_WORDS:
                        k += 1                                    # the page's "what to do with the seed next time"
                else:
                    val = opts.get("default")
                if name in linked:
                    inputs[name] = [str(linked[name][1]), linked[name][2]]
                elif val is not None:
                    inputs[name] = val
            elif name in linked:
                inputs[name] = [str(linked[name][1]), linked[name][2]]
        for name, l in linked.items():                            # a link the node's own list did not name
            inputs.setdefault(name, [str(l[1]), l[2]])
        api[str(n["id"])] = {"class_type": typ, "inputs": inputs}
    return api


def resolve_switches(api: dict) -> dict:
    """Take each switch out and wire what follows it straight to the side it is set to."""
    for _ in range(20):
        sw = next((i for i, n in api.items() if n["class_type"] == "ComfySwitchNode"), None)
        if sw is None:
            break
        ins = api[sw]["inputs"]
        val = ins.get("switch", False)
        if isinstance(val, list):
            val = api[val[0]]["inputs"].get("value", False)
        chosen = ins.get("on_true" if val else "on_false")
        if chosen is None:
            raise RuntimeError(f"switch {sw} has nothing on its {'true' if val else 'false'} side")
        for n in api.values():
            for key, v in n["inputs"].items():
                if isinstance(v, list) and len(v) == 2 and v[0] == sw:
                    n["inputs"][key] = list(chosen)
        del api[sw]
    return api


def prune(api: dict, keep: str) -> dict:
    """Only what the save node needs."""
    want, stack = set(), [keep]
    while stack:
        i = stack.pop()
        if i in want or i not in api:
            continue
        want.add(i)
        stack += [v[0] for v in api[i]["inputs"].values() if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str)]
    return {i: n for i, n in api.items() if i in want}


def build_prompt(template: dict, info: dict, image_name: str, model: str, resolution: int, faces: int, texture: int,
                 prefix: str, seed: int | None = None) -> dict:
    """The request for one picture through one image-to-3D model at one resolution."""
    if model not in MODELS:
        raise ValueError(f"unknown image-to-3D model {model!r}; the forge knows {', '.join(MODELS)}")
    wf = copy.deepcopy(template)
    nodes = {n["id"]: n for n in wf["nodes"]}
    for nid, typ in ((N_IMAGE, "LoadImage"), (N_WHICH, "PrimitiveBoolean"), (N_UPSAMPLE, "Trellis2UpsampleStage"),
                     (N_DECIMATE, "DecimateMesh"), (N_TEXTURE, "PrimitiveInt"), (N_SAVE, "Save3DAdvanced")):
        if nid not in nodes or nodes[nid]["type"] != typ:
            raise RuntimeError(f"the image-to-3D template is not the one this was written for (node {nid} is not a {typ})")
    nodes[N_IMAGE]["widgets_values"][0] = image_name
    nodes[N_WHICH]["widgets_values"][0] = (model == "trellis2")
    nodes[N_UPSAMPLE]["widgets_values"][0] = int(resolution)
    nodes[N_DECIMATE]["widgets_values"][0] = int(faces)
    nodes[N_TEXTURE]["widgets_values"][0] = int(texture)
    nodes[N_SAVE]["widgets_values"][0] = prefix
    if seed is not None:
        for n in wf["nodes"]:
            if n["type"] == "KSampler":
                n["widgets_values"][0] = int(seed)
    api = resolve_switches(to_api(wf, info))
    return prune(api, str(N_SAVE))


def node_types(template: dict | None = None) -> list[str]:
    """Every kind of node the template uses (doctor checks the art ComfyUI has them)."""
    wf = template or load()
    return sorted({n["type"] for n in wf["nodes"] if n["type"] not in SKIP_TYPES})


def add_back_view(api: dict, back_image_name: str) -> dict:
    """BUILD 40: a second picture, of the back, for Pixal3D. The installed nodes have it: Pixal3DMultiViewConditioning takes
    front, left, back and right views on a fixed orbit. The back picture goes through the same background removal and
    crop as the front, and the one-view conditioning node is swapped for the multi-view one (the front's field of view,
    as MoGe measured it, for both). TRELLIS.2's conditioning takes one picture only, so a body cannot have a back view."""
    api = copy.deepcopy(api)
    cond = next((k for k, n in api.items() if n.get("class_type") == "Pixal3DConditioning"), None)
    crop = next((k for k, n in api.items() if n.get("class_type") == "ImageCropToMask"), None)
    rb = next((k for k, n in api.items() if n.get("class_type") == "RemoveBackground"), None)
    if not cond or not crop or not rb:
        raise RuntimeError("the Pixal3D part of the template is not the one the back view was written for")
    ids = [int(k) for k in api if str(k).isdigit()]
    nid = max(ids) + 1000
    load, rem, cut = str(nid), str(nid + 1), str(nid + 2)
    api[load] = {"class_type": "LoadImage", "inputs": {"image": back_image_name}}
    api[rem] = {"class_type": "RemoveBackground", "inputs": {"bg_removal_model": api[rb]["inputs"]["bg_removal_model"],
                                                            "image": [load, 0]}}
    ci = dict(api[crop]["inputs"])
    ci.update(images=[load, 0], masks=[rem, 0])
    api[cut] = {"class_type": "ImageCropToMask", "inputs": ci}
    old = api[cond]["inputs"]
    api[cond] = {"class_type": "Pixal3DMultiViewConditioning",
                 "inputs": {"clip_vision_model": old["clip_vision_model"], "fov": old.get("camera_angle_x", 20.0),
                            "front": old["image"], "back": [cut, 0]}}
    return api
