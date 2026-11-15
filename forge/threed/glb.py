"""Read a .glb without Blender: its size, how tall it stands, its motions, whether it has a skeleton.

For the screens (the viewer's list of motions, a model's height in metres), the checks (a test dance never reaches a
game) and the tests. Only the file's JSON part is read, plus the position data when its extent is not written down.
`box()` writes a small valid .glb (a box, optionally with named motions) — the stand-in ComfyUI's "3D model".
"""
from __future__ import annotations

import json
import math
import struct
from pathlib import Path

MAGIC = b"glTF"
JSON_CHUNK, BIN_CHUNK = 0x4E4F534A, 0x004E4942


def read_json(path: Path) -> dict:
    with open(path, "rb") as f:
        head = f.read(20)
        if len(head) < 20 or head[:4] != MAGIC:
            raise ValueError(f"{Path(path).name} is not a .glb file")
        _, _, _total, clen, ctype = struct.unpack("<4sIIII", head)
        if ctype != JSON_CHUNK:
            raise ValueError(f"{Path(path).name}: the first part of the file is not its JSON")
        return json.loads(f.read(clen).decode("utf-8"))


def _mat(node: dict) -> list[float]:
    """A node's 4x4 transform (column-major, glTF's order)."""
    if "matrix" in node:
        return list(node["matrix"])
    t = node.get("translation", [0, 0, 0])
    q = node.get("rotation", [0, 0, 0, 1])
    s = node.get("scale", [1, 1, 1])
    x, y, z, w = q
    r = [1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w),
         2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w),
         2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y)]
    return [r[0] * s[0], r[1] * s[0], r[2] * s[0], 0, r[3] * s[1], r[4] * s[1], r[5] * s[1], 0,
            r[6] * s[2], r[7] * s[2], r[8] * s[2], 0, t[0], t[1], t[2], 1]


def _mul(a: list[float], b: list[float]) -> list[float]:
    return [sum(a[k * 4 + i] * b[j * 4 + k] for k in range(4)) for j in range(4) for i in range(4)]


def _apply(m: list[float], p) -> tuple[float, float, float]:
    x, y, z = p
    return (m[0] * x + m[4] * y + m[8] * z + m[12], m[1] * x + m[5] * y + m[9] * z + m[13], m[2] * x + m[6] * y + m[10] * z + m[14])


def info(path: Path) -> dict:
    """What a person (or a check) wants to know about a model, cheaply."""
    p = Path(path)
    j = read_json(p)
    acc = j.get("accessors", [])
    nodes = j.get("nodes", [])
    meshes = j.get("meshes", [])
    skinned_meshes = {n.get("mesh") for n in nodes if "skin" in n}
    # world transforms of the nodes that carry a mesh (a skinned mesh is placed by its skeleton: its own node is ignored)
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}

    def world(i: int) -> list[float]:
        m = _mat(nodes[i])
        while i in parent:
            i = parent[i]
            m = _mul(_mat(nodes[i]), m)
        return m

    lo, hi = [math.inf] * 3, [-math.inf] * 3
    tris = 0
    for i, n in enumerate(nodes):
        if "mesh" not in n or n["mesh"] >= len(meshes):
            continue
        m = None if n["mesh"] in skinned_meshes else world(i)
        for prim in meshes[n["mesh"]].get("primitives", []):
            a = acc[prim["attributes"]["POSITION"]] if "POSITION" in prim.get("attributes", {}) else None
            if a and "min" in a and "max" in a:
                corners = [(x, y, z) for x in (a["min"][0], a["max"][0]) for y in (a["min"][1], a["max"][1])
                           for z in (a["min"][2], a["max"][2])]
                for c in corners:
                    w = _apply(m, c) if m else c
                    for k in range(3):
                        lo[k], hi[k] = min(lo[k], w[k]), max(hi[k], w[k])
            if "indices" in prim:
                tris += acc[prim["indices"]]["count"] // 3
            elif a:
                tris += a["count"] // 3
    size = [round(hi[k] - lo[k], 4) for k in range(3)] if lo[0] < math.inf else [0.0, 0.0, 0.0]
    anims = [a.get("name") or f"motion_{k}" for k, a in enumerate(j.get("animations", []))]
    return {
        "file": p.name, "bytes": p.stat().st_size, "generator": (j.get("asset") or {}).get("generator", ""),
        "meshes": len(meshes), "triangles": tris, "nodes": len(nodes), "skins": len(j.get("skins", [])),
        "joints": sum(len(s.get("joints", [])) for s in j.get("skins", [])),
        "images": len(j.get("images", [])), "materials": len(j.get("materials", [])),
        "motions": anims, "extensions": j.get("extensionsUsed", []),
        # glTF is Y-up: height is the Y extent
        "size_m": {"width": size[0], "height": size[1], "depth": size[2]},
        "floor_y": round(lo[1], 4) if lo[1] < math.inf else 0.0,
    }


def _pad(b: bytes, fill: bytes) -> bytes:
    return b + fill * ((4 - len(b) % 4) % 4)


def box(path: Path, size=(1.0, 1.0, 1.0), motions: list[str] | None = None, joints: int = 0, generator: str = "stand-in") -> Path:
    """A small valid .glb: one box `size` metres (x, y, z), standing on y = 0; with `motions`, a skeleton of `joints`
    (at least one) bones and one named animation per motion (a short turn of the root), so a viewer can play them."""
    w, h, d = (float(v) for v in size)
    x0, x1, y0, y1, z0, z1 = -w / 2, w / 2, 0.0, h, -d / 2, d / 2
    pos = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    idx = [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4, 3, 7, 6, 3, 6, 2, 0, 4, 7, 0, 7, 3, 1, 2, 6, 1, 6, 5]
    binb = b"".join(struct.pack("<3f", *p) for p in pos)
    off_idx = len(binb)
    binb += b"".join(struct.pack("<H", i) for i in idx)
    binb = _pad(binb, b"\x00")
    j: dict = {
        "asset": {"version": "2.0", "generator": generator},
        "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "body"}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3", "min": [x0, y0, z0], "max": [x1, y1, z1]},
            {"bufferView": 1, "componentType": 5123, "count": len(idx), "type": "SCALAR"}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": off_idx},
                        {"buffer": 0, "byteOffset": off_idx, "byteLength": len(idx) * 2}],
    }
    if motions:
        n = max(1, int(joints))
        joint_nodes = list(range(1, n + 1))
        j["nodes"][0]["skin"] = 0
        for k in joint_nodes:
            j["nodes"].append({"name": f"bone_{k}", "translation": [0, h / (n + 1), 0] if k > 1 else [0, 0, 0],
                               **({"children": [k + 1]} if k < n else {})})
        j["scenes"][0]["nodes"] = [0, 1]
        # inverse bind matrices: identity
        ibm_off = len(binb)
        binb += struct.pack("<16f", *[1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]) * n
        j["bufferViews"].append({"buffer": 0, "byteOffset": ibm_off, "byteLength": 64 * n})
        j["accessors"].append({"bufferView": len(j["bufferViews"]) - 1, "componentType": 5126, "count": n, "type": "MAT4"})
        j["skins"] = [{"joints": joint_nodes, "inverseBindMatrices": len(j["accessors"]) - 1}]
        # every vertex on the root bone
        jw_off = len(binb)
        binb += struct.pack("<4B", 0, 0, 0, 0) * 8
        binb = _pad(binb, b"\x00")
        wt_off = len(binb)
        binb += struct.pack("<4f", 1, 0, 0, 0) * 8
        j["bufferViews"] += [{"buffer": 0, "byteOffset": jw_off, "byteLength": 32}, {"buffer": 0, "byteOffset": wt_off, "byteLength": 128}]
        j["accessors"] += [{"bufferView": len(j["bufferViews"]) - 2, "componentType": 5121, "count": 8, "type": "VEC4"},
                           {"bufferView": len(j["bufferViews"]) - 1, "componentType": 5126, "count": 8, "type": "VEC4"}]
        j["meshes"][0]["primitives"][0]["attributes"].update({"JOINTS_0": len(j["accessors"]) - 2, "WEIGHTS_0": len(j["accessors"]) - 1})
        # one shared time track (0 s, 1 s) and one rotation track per motion
        t_off = len(binb)
        binb += struct.pack("<2f", 0.0, 1.0)
        j["bufferViews"].append({"buffer": 0, "byteOffset": t_off, "byteLength": 8})
        j["accessors"].append({"bufferView": len(j["bufferViews"]) - 1, "componentType": 5126, "count": 2, "type": "SCALAR",
                               "min": [0.0], "max": [1.0]})
        t_acc = len(j["accessors"]) - 1
        j["animations"] = []
        for k, name in enumerate(motions):
            a = math.radians(10 + 5 * (k % 6))
            r_off = len(binb)
            binb += struct.pack("<4f", 0, 0, 0, 1) + struct.pack("<4f", 0, math.sin(a / 2), 0, math.cos(a / 2))
            j["bufferViews"].append({"buffer": 0, "byteOffset": r_off, "byteLength": 32})
            j["accessors"].append({"bufferView": len(j["bufferViews"]) - 1, "componentType": 5126, "count": 2, "type": "VEC4"})
            j["animations"].append({"name": name, "samplers": [{"input": t_acc, "output": len(j["accessors"]) - 1}],
                                    "channels": [{"sampler": 0, "target": {"node": 1, "path": "rotation"}}]})
    binb = _pad(binb, b"\x00")
    j["buffers"] = [{"byteLength": len(binb)}]
    js = _pad(json.dumps(j, separators=(",", ":")).encode("utf-8"), b" ")
    total = 12 + 8 + len(js) + 8 + len(binb)
    out = struct.pack("<4sII", MAGIC, 2, total) + struct.pack("<II", len(js), JSON_CHUNK) + js + struct.pack("<II", len(binb), BIN_CHUNK) + binb
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(out)
    return p
