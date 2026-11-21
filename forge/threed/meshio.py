"""A .glb as numbers, and small changes written back — without Blender (BUILD 39).

The checks after every model need the mesh itself (positions, triangles, texture coordinates, the colour and metal/rough
pictures), and the world queue needs a few changes on the way out: the thing's real size in metres, stood on the floor,
straightened when it leans, a flat cut-out panel added, a glow layer for eyes. All of it is plain numpy and Pillow, so
it runs on any computer the suite runs on (Windows, macOS, Linux) and in the tests.

    g = Glb.load(path)
    m = g.mesh()                  # {"P", "F", "UV", "N", "face_material", "materials"} — positions in world space
    img = g.texture_image(m["materials"][0], "baseColorTexture")
    g.wrap(scale=0.5, rotation=quat, translation=(0, 0.1, 0))   # one new root node above the old ones
    g.save(out)

`wrap()` never rewrites the mesh: it puts one node with the transform above the scene's nodes, which every glTF reader
(Godot, Blender, three.js) applies — skinned bodies included, because their skeleton hangs under that node too.
"""
from __future__ import annotations

import io
import json
import math
import struct
from pathlib import Path

import numpy as np

MAGIC = b"glTF"
JSON_CHUNK, BIN_CHUNK = 0x4E4F534A, 0x004E4942
COMPONENT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}
CODE = {np.dtype(np.int8): 5120, np.dtype(np.uint8): 5121, np.dtype(np.int16): 5122, np.dtype(np.uint16): 5123,
        np.dtype(np.uint32): 5125, np.dtype(np.float32): 5126}


def _pad(b: bytes | bytearray, fill: bytes) -> bytes:
    return bytes(b) + fill * ((4 - len(b) % 4) % 4)


# ------------------------------------------------------------------------------------------------ transforms
def node_matrix(node: dict) -> np.ndarray:
    """A node's 4x4 transform as a numpy matrix (row-major, column vectors: world = M @ [x, y, z, 1])."""
    if "matrix" in node:
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
    t = np.array(node.get("translation", [0, 0, 0]), dtype=np.float64)
    x, y, z, w = (float(v) for v in node.get("rotation", [0, 0, 0, 1]))
    s = np.array(node.get("scale", [1, 1, 1]), dtype=np.float64)
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m = np.eye(4)
    m[:3, :3] = r * s[None, :]
    m[:3, 3] = t
    return m


def quat_between(a, b) -> list[float]:
    """The shortest rotation taking direction a onto direction b, as a glTF quaternion [x, y, z, w]."""
    a = np.asarray(a, dtype=np.float64) / np.linalg.norm(a)
    b = np.asarray(b, dtype=np.float64) / np.linalg.norm(b)
    c = float(np.dot(a, b))
    if c > 1 - 1e-12:
        return [0.0, 0.0, 0.0, 1.0]
    if c < -1 + 1e-12:                                    # opposite: any perpendicular axis, half a turn
        ax = np.cross(a, [1, 0, 0]) if abs(a[0]) < 0.9 else np.cross(a, [0, 1, 0])
        ax /= np.linalg.norm(ax)
        return [float(ax[0]), float(ax[1]), float(ax[2]), 0.0]
    ax = np.cross(a, b)
    q = np.array([ax[0], ax[1], ax[2], 1 + c])
    q /= np.linalg.norm(q)
    return [float(v) for v in q]


def quat_matrix(q) -> np.ndarray:
    return node_matrix({"rotation": list(q)})[:3, :3]


# ------------------------------------------------------------------------------------------------ the file
class Glb:
    def __init__(self, j: dict, binb: bytes | bytearray | None = None):
        self.j = j
        self.bin = bytearray(binb or b"")

    # ------------------------------------------------------------------ reading
    @classmethod
    def load(cls, path) -> "Glb":
        b = Path(path).read_bytes()
        if len(b) < 20 or b[:4] != MAGIC:
            raise ValueError(f"{Path(path).name} is not a .glb file")
        clen, ctype = struct.unpack_from("<II", b, 12)
        if ctype != JSON_CHUNK:
            raise ValueError(f"{Path(path).name}: the first part of the file is not its JSON")
        j = json.loads(b[20:20 + clen].decode("utf-8"))
        off = 20 + clen
        binb = b""
        if off + 8 <= len(b):
            blen, btype = struct.unpack_from("<II", b, off)
            if btype == BIN_CHUNK:
                binb = b[off + 8: off + 8 + blen]
        return cls(j, binb)

    @classmethod
    def new(cls, generator: str = "RPG_Forge") -> "Glb":
        return cls({"asset": {"version": "2.0", "generator": generator}, "scene": 0, "scenes": [{"nodes": []}], "nodes": [],
                    "meshes": [], "accessors": [], "bufferViews": [], "buffers": []})

    def accessor(self, i: int, raw: bool = False) -> np.ndarray:
        """The numbers behind accessor `i`. `raw=True` gives them exactly as stored (a normalised list is not turned into
        fractions) — what a list must be read as when it is going to be written back."""
        a = self.j["accessors"][i]
        dt = np.dtype(COMPONENT[a["componentType"]])
        n = WIDTH[a["type"]]
        count = int(a["count"])
        if "bufferView" not in a:                          # sparse-only or all zeros
            return np.zeros((count, n), dtype=dt)
        bv = self.j["bufferViews"][a["bufferView"]]
        start = int(bv.get("byteOffset", 0)) + int(a.get("byteOffset", 0))
        stride = int(bv.get("byteStride") or dt.itemsize * n)
        if stride == dt.itemsize * n:
            arr = np.frombuffer(self.bin, dtype=dt, count=count * n, offset=start).reshape(count, n)
        else:
            raw = np.frombuffer(self.bin, dtype=np.uint8, count=stride * (count - 1) + dt.itemsize * n, offset=start)
            arr = np.lib.stride_tricks.as_strided(raw, shape=(count, dt.itemsize * n), strides=(stride, 1)).copy()
            arr = arr.view(dt).reshape(count, n)
        if a.get("normalized") and dt.kind in "iu" and not raw:
            arr = arr.astype(np.float64) / float(np.iinfo(dt).max)
        return arr

    def image_bytes(self, image_index: int) -> bytes:
        im = self.j["images"][image_index]
        if "bufferView" in im:
            bv = self.j["bufferViews"][im["bufferView"]]
            o = int(bv.get("byteOffset", 0))
            return bytes(self.bin[o: o + int(bv["byteLength"])])
        uri = im.get("uri", "")
        if uri.startswith("data:"):
            import base64
            return base64.b64decode(uri.split(",", 1)[1])
        raise ValueError("this .glb points at a texture outside the file; only self-contained .glb files are read")

    def texture_image(self, material: dict | None, slot: str):
        """The picture behind a material's texture slot ('baseColorTexture', 'metallicRoughnessTexture' — both inside
        pbrMetallicRoughness — or 'normalTexture', 'emissiveTexture', 'occlusionTexture'), as a Pillow RGB(A) image."""
        from PIL import Image
        if not material:
            return None
        pbr = material.get("pbrMetallicRoughness") or {}
        ref = pbr.get(slot) if slot in ("baseColorTexture", "metallicRoughnessTexture") else material.get(slot)
        if not ref or "textures" not in self.j:
            return None
        tex = self.j["textures"][ref["index"]]
        src = tex.get("source")
        if src is None:
            return None
        return Image.open(io.BytesIO(self.image_bytes(src)))

    def world_matrices(self) -> dict[int, np.ndarray]:
        nodes = self.j.get("nodes", [])
        parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}
        out = {}
        for i in range(len(nodes)):
            m = node_matrix(nodes[i])
            k = i
            while k in parent:
                k = parent[k]
                m = node_matrix(nodes[k]) @ m
            out[i] = m
        return out

    def mesh(self) -> dict:
        """Every triangle of every mesh node, positions in world space (a skinned mesh as it was bound).

        Returns {"P": (n,3) float64, "F": (m,3) int64, "UV": (n,2), "N": (n,3) or None, "face_material": (m,) int,
        "materials": [the material dicts]}."""
        nodes = self.j.get("nodes", [])
        meshes = self.j.get("meshes", [])
        skinned = {n.get("mesh") for n in nodes if "skin" in n}
        world = self.world_matrices()
        P, F, UV, N, FM = [], [], [], [], []
        base = 0
        for i, n in enumerate(nodes):
            if "mesh" not in n or n["mesh"] >= len(meshes):
                continue
            m = np.eye(4) if n["mesh"] in skinned else world[i]
            for prim in meshes[n["mesh"]].get("primitives", []):
                if prim.get("mode", 4) != 4 or "POSITION" not in prim.get("attributes", {}):
                    continue                                  # only triangle lists carry a surface
                p = self.accessor(prim["attributes"]["POSITION"]).astype(np.float64)
                p = (np.c_[p, np.ones(len(p))] @ m.T)[:, :3]
                f = (self.accessor(prim["indices"]).reshape(-1, 3).astype(np.int64) if "indices" in prim
                     else np.arange(len(p) - len(p) % 3, dtype=np.int64).reshape(-1, 3))
                at = prim["attributes"]
                uv = self.accessor(at["TEXCOORD_0"]).astype(np.float64) if "TEXCOORD_0" in at else np.zeros((len(p), 2))
                if "NORMAL" in at:
                    nn = self.accessor(at["NORMAL"]).astype(np.float64) @ m[:3, :3].T
                    nn /= np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-12)
                else:
                    nn = None
                P.append(p)
                F.append(f + base)
                UV.append(uv)
                N.append(nn)
                FM.append(np.full(len(f), -1 if prim.get("material") is None else int(prim["material"]), dtype=np.int64))
                base += len(p)
        if not P:
            return {"P": np.zeros((0, 3)), "F": np.zeros((0, 3), dtype=np.int64), "UV": np.zeros((0, 2)), "N": None,
                    "face_material": np.zeros(0, dtype=np.int64), "materials": self.j.get("materials", [])}
        normals = np.concatenate(N) if all(x is not None for x in N) else None
        return {"P": np.concatenate(P), "F": np.concatenate(F), "UV": np.concatenate(UV), "N": normals,
                "face_material": np.concatenate(FM), "materials": self.j.get("materials", [])}

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        P = self.mesh()["P"]
        if not len(P):
            return np.zeros(3), np.zeros(3)
        return P.min(0), P.max(0)

    # ------------------------------------------------------------------ writing
    def _ensure_buffer(self) -> None:
        if not self.j.get("buffers"):
            self.j["buffers"] = [{"byteLength": 0}]

    def add_view(self, data: bytes, target: int | None = None) -> int:
        self._ensure_buffer()
        self.bin = bytearray(_pad(self.bin, b"\x00"))
        view = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(data)}
        if target:
            view["target"] = target
        self.bin += data
        self.j.setdefault("bufferViews", []).append(view)
        return len(self.j["bufferViews"]) - 1

    def add_accessor(self, arr: np.ndarray, kind: str, target: int | None = None, minmax: bool = False) -> int:
        arr = np.ascontiguousarray(arr)
        v = self.add_view(arr.tobytes(), target)
        a = {"bufferView": v, "componentType": CODE[arr.dtype], "count": int(arr.shape[0]), "type": kind}
        if minmax:
            flat = arr.reshape(arr.shape[0], -1)
            a["min"] = [float(x) for x in flat.min(0)]
            a["max"] = [float(x) for x in flat.max(0)]
        self.j.setdefault("accessors", []).append(a)
        return len(self.j["accessors"]) - 1

    def add_image(self, img, sampler: dict | None = None) -> int:
        """A Pillow image as a PNG texture inside the file; returns the texture index."""
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=True)
        v = self.add_view(buf.getvalue())
        self.j.setdefault("images", []).append({"bufferView": v, "mimeType": "image/png"})
        smp = sampler or {"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}
        samplers = self.j.setdefault("samplers", [])
        if smp in samplers:
            si = samplers.index(smp)
        else:
            samplers.append(smp)
            si = len(samplers) - 1
        self.j.setdefault("textures", []).append({"source": len(self.j["images"]) - 1, "sampler": si})
        return len(self.j["textures"]) - 1

    def replace_image(self, texture_index: int, img) -> None:
        """Put a new picture behind an existing texture (the old bytes stay in the buffer, unreferenced: harmless)."""
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=True)
        v = self.add_view(buf.getvalue())
        src = self.j["textures"][texture_index]["source"]
        self.j["images"][src] = {"bufferView": v, "mimeType": "image/png"}

    def add_mesh_node(self, P, F, UV, material: dict, name: str, normals=None, translation=None, rotation=None,
                      parent: int | None = None) -> int:
        """One triangle mesh as a new node (in the scene, or under `parent`). Returns the node index."""
        P = np.asarray(P, dtype=np.float32)
        F = np.asarray(F, dtype=np.uint32).reshape(-1)
        UV = np.asarray(UV, dtype=np.float32)
        attrs = {"POSITION": self.add_accessor(P, "VEC3", 34962, minmax=True), "TEXCOORD_0": self.add_accessor(UV, "VEC2", 34962)}
        if normals is not None:
            attrs["NORMAL"] = self.add_accessor(np.asarray(normals, dtype=np.float32), "VEC3", 34962)
        idx = self.add_accessor(F.reshape(-1, 1), "SCALAR", 34963)
        self.j.setdefault("materials", []).append(material)
        self.j.setdefault("meshes", []).append({"name": name, "primitives": [{"attributes": attrs, "indices": idx, "mode": 4,
                                                                              "material": len(self.j["materials"]) - 1}]})
        node = {"name": name, "mesh": len(self.j["meshes"]) - 1}
        if translation is not None:
            node["translation"] = [float(x) for x in translation]
        if rotation is not None:
            node["rotation"] = [float(x) for x in rotation]
        self.j.setdefault("nodes", []).append(node)
        ni = len(self.j["nodes"]) - 1
        if parent is None:
            self.j["scenes"][self.j.get("scene", 0)].setdefault("nodes", []).append(ni)
        else:
            self.j["nodes"][parent].setdefault("children", []).append(ni)
        return ni

    def wrap(self, scale: float | list = 1.0, rotation=None, translation=None, name: str = "forge_root") -> int:
        """One new node holding every root node of the scene, with this transform. Returns its index."""
        scene = self.j["scenes"][self.j.get("scene", 0)]
        roots = list(scene.get("nodes", []))
        node = {"name": name, "children": roots}
        if rotation is not None:
            node["rotation"] = [float(x) for x in rotation]
        if scale != 1.0:
            node["scale"] = [float(scale)] * 3 if np.isscalar(scale) else [float(x) for x in scale]
        if translation is not None:
            node["translation"] = [float(x) for x in translation]
        self.j.setdefault("nodes", []).append(node)
        ni = len(self.j["nodes"]) - 1
        scene["nodes"] = [ni]
        return ni

    def drop_faces(self, drop) -> dict:
        """Take triangles out of the file (BUILD 84, 2f: a slab of ground left under a model). `drop` is a mask over the
        triangles in the order `mesh()` gives them. A primitive that loses triangles gets a new index list, and its vertex
        lists are written again without the vertices nothing uses any more — so the thing's box, and the floor it is stood
        on, stop counting what was taken off. A primitive that loses every triangle leaves its mesh; a mesh left with
        nothing leaves its node. A mesh used by more than one node loses a triangle only where every use of it would.
        The old numbers stay in the buffer, unreferenced (harmless, as with `replace_image`). Refuses what it cannot
        rewrite safely — morph targets, a sparse list — with ValueError, and then nothing has been changed."""
        drop = np.asarray(drop, dtype=bool)
        nodes, meshes = self.j.get("nodes", []), self.j.get("meshes", [])
        plan: dict[tuple[int, int], np.ndarray] = {}
        at = 0
        for n in nodes:
            if "mesh" not in n or n["mesh"] >= len(meshes):
                continue
            for pi, prim in enumerate(meshes[n["mesh"]].get("primitives", [])):
                if prim.get("mode", 4) != 4 or "POSITION" not in prim.get("attributes", {}):
                    continue
                if "indices" in prim:
                    nf = int(self.j["accessors"][prim["indices"]]["count"]) // 3
                else:
                    nf = int(self.j["accessors"][prim["attributes"]["POSITION"]]["count"]) // 3
                seg = drop[at: at + nf]
                if len(seg) != nf:
                    raise ValueError("the mask does not cover the file's triangles")
                key = (int(n["mesh"]), pi)
                plan[key] = seg.copy() if key not in plan else (plan[key] & seg)
                at += nf
        if at != len(drop):
            raise ValueError(f"the mask is for {len(drop)} triangles; the file has {at}")
        todo = {k: v for k, v in plan.items() if v.any()}
        for (mi, pi), seg in todo.items():                   # look before anything is changed
            prim = meshes[mi]["primitives"][pi]
            if prim.get("targets"):
                raise ValueError("a mesh with morph targets is not rewritten")
            for ai in list(prim["attributes"].values()) + ([prim["indices"]] if "indices" in prim else []):
                if "sparse" in self.j["accessors"][ai] or "bufferView" not in self.j["accessors"][ai]:
                    raise ValueError("a mesh with a sparse list is not rewritten")
        taken, emptied = 0, []
        for (mi, pi), seg in todo.items():
            prim = meshes[mi]["primitives"][pi]
            attrs = prim["attributes"]
            nv = int(self.j["accessors"][attrs["POSITION"]]["count"])
            f = (self.accessor(prim["indices"], raw=True).reshape(-1, 3).astype(np.int64) if "indices" in prim
                 else np.arange(nv - nv % 3, dtype=np.int64).reshape(-1, 3))
            taken += int(seg.sum())
            keep = f[~seg]
            if not len(keep):
                emptied.append((mi, pi))
                continue
            used = np.unique(keep)
            remap = np.full(nv, -1, dtype=np.int64)
            remap[used] = np.arange(len(used))
            for name, ai in list(attrs.items()):
                a = self.j["accessors"][ai]
                arr = np.ascontiguousarray(self.accessor(ai, raw=True)[used])
                ni = self.add_accessor(arr, a["type"], 34962, minmax=(name == "POSITION"))
                if a.get("normalized"):
                    self.j["accessors"][ni]["normalized"] = True
                attrs[name] = ni
            prim["indices"] = self.add_accessor(remap[keep].astype(np.uint32).reshape(-1, 1), "SCALAR", 34963)
        if emptied:
            gone = set(emptied)
            for mi in {m for m, _ in gone}:
                meshes[mi]["primitives"] = [p for pi, p in enumerate(meshes[mi]["primitives"]) if (mi, pi) not in gone]
            dead = [mi for mi, me in enumerate(meshes) if not me.get("primitives")]
            if dead:
                new_index, k = {}, 0
                for mi in range(len(meshes)):
                    if mi in dead:
                        continue
                    new_index[mi] = k
                    k += 1
                self.j["meshes"] = [me for mi, me in enumerate(meshes) if mi not in dead]
                for n in nodes:
                    if "mesh" in n:
                        if n["mesh"] in new_index:
                            n["mesh"] = new_index[n["mesh"]]
                        else:
                            n.pop("mesh")
                            n.pop("skin", None)
        return {"faces": taken, "primitives_out": len(emptied)}

    def move_faces(self, sel, offset) -> dict:
        """Move the vertices of the triangles `sel` (a mask in `mesh()`'s order) by `offset`, given in world space (BUILD 84,
        2f: a piece that stands a little through the floor, stood on it). The piece must be a piece: a vertex it shares
        with a triangle that is not moving is refused, and so is a mesh more than one node uses, a skinned mesh or a
        position list that is not plain floats (ValueError; nothing has been changed then). The triangles keep their
        order, so a mask made before still fits afterwards."""
        sel = np.asarray(sel, dtype=bool)
        off = np.asarray(offset, dtype=np.float64).reshape(3)
        nodes, meshes = self.j.get("nodes", []), self.j.get("meshes", [])
        skinned = {n.get("mesh") for n in nodes if "skin" in n}
        uses: dict[int, int] = {}
        for n in nodes:
            if "mesh" in n:
                uses[n["mesh"]] = uses.get(n["mesh"], 0) + 1
        world = self.world_matrices()
        jobs, at = [], 0
        for i, n in enumerate(nodes):
            if "mesh" not in n or n["mesh"] >= len(meshes):
                continue
            for prim in meshes[n["mesh"]].get("primitives", []):
                if prim.get("mode", 4) != 4 or "POSITION" not in prim.get("attributes", {}):
                    continue
                pa = self.j["accessors"][prim["attributes"]["POSITION"]]
                nv = int(pa["count"])
                nf = int(self.j["accessors"][prim["indices"]]["count"]) // 3 if "indices" in prim else nv // 3
                seg = sel[at: at + nf]
                at += nf
                if len(seg) != nf:
                    raise ValueError("the mask does not cover the file's triangles")
                if not seg.any():
                    continue
                if uses.get(n["mesh"], 0) > 1 or n["mesh"] in skinned:
                    raise ValueError("a mesh used by more than one node, or a skinned one, is not moved")
                if pa.get("componentType") != 5126 or "sparse" in pa or "bufferView" not in pa or prim.get("targets"):
                    raise ValueError("these positions cannot be rewritten")
                f = (self.accessor(prim["indices"], raw=True).reshape(-1, 3).astype(np.int64) if "indices" in prim
                     else np.arange(nv - nv % 3, dtype=np.int64).reshape(-1, 3))
                moving = np.zeros(nv, dtype=bool)
                moving[f[seg].ravel()] = True
                if moving[f[~seg].ravel()].any():
                    raise ValueError("the piece shares a vertex with a part that is not moving")
                jobs.append((prim, moving, np.linalg.solve(world[i][:3, :3], off)))
        if at != len(sel):
            raise ValueError(f"the mask is for {len(sel)} triangles; the file has {at}")
        moved = 0
        for prim, moving, local in jobs:
            pos = np.array(self.accessor(prim["attributes"]["POSITION"], raw=True), dtype=np.float32)
            pos[moving] += local.astype(np.float32)
            prim["attributes"]["POSITION"] = self.add_accessor(pos, "VEC3", 34962, minmax=True)
            moved += int(moving.sum())
        return {"vertices": moved}

    def use_extension(self, name: str) -> None:
        used = self.j.setdefault("extensionsUsed", [])
        if name not in used:
            used.append(name)

    def save(self, path) -> Path:
        self._ensure_buffer()
        binb = _pad(self.bin, b"\x00")
        self.j["buffers"][0]["byteLength"] = len(binb)
        for b in self.j["buffers"][1:]:                      # only one buffer is kept in a .glb
            b.setdefault("byteLength", 0)
        js = _pad(json.dumps(self.j, separators=(",", ":")).encode("utf-8"), b" ")
        total = 12 + 8 + len(js) + (8 + len(binb) if binb else 0)
        out = struct.pack("<4sII", MAGIC, 2, total) + struct.pack("<II", len(js), JSON_CHUNK) + js
        if binb:
            out += struct.pack("<II", len(binb), BIN_CHUNK) + binb
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".part")
        tmp.write_bytes(out)
        tmp.replace(p)
        return p


# ------------------------------------------------------------------------------------------------ on the way out
SIZE_ORDER = ("height", "length", "width", "depth")     # which of an entry's measures a thing is scaled by: the first it gives


def size_factor(lo: np.ndarray, hi: np.ndarray, size: dict | None) -> tuple[float, str | None]:
    """The scale that gives a thing its real size: `size` is {"height" | "length" | "width" | "depth": metres}. Height
    first (the measure the eye judges against a person); then length — the LONGER side on the ground, whichever way the
    model turned out (BUILD 84 part 6: a streetcar asked "depth 14" came out lying along the other axis and was made six
    times too big); then a named side."""
    if not size:
        return 1.0, None
    ext = {"width": hi[0] - lo[0], "height": hi[1] - lo[1], "depth": hi[2] - lo[2]}
    ext["length"] = max(ext["width"], ext["depth"])
    for k in SIZE_ORDER:
        v = size.get(k)
        if v not in (None, "", 0) and ext[k] > 1e-9:
            return float(v) / float(ext[k]), k
    return 1.0, None


def place(src, dst, size: dict | None = None, rotation=None, floor: bool = True, centre: bool = True) -> dict:
    """Real size in metres, straightened by `rotation` (a quaternion) when given, standing on the floor (y = 0) and
    centred over the origin — all as one node above the model, the mesh untouched. Returns what was done."""
    g = Glb.load(src)
    P = g.mesh()["P"]
    if not len(P):
        raise ValueError(f"{Path(src).name} has no triangles")
    R = quat_matrix(rotation) if rotation is not None else np.eye(3)
    Q = P @ R.T
    lo, hi = Q.min(0), Q.max(0)
    k, axis = size_factor(lo, hi, size)
    lo, hi = lo * k, hi * k
    t = np.zeros(3)
    if centre:
        t[0] = -(lo[0] + hi[0]) / 2
        t[2] = -(lo[2] + hi[2]) / 2
    if floor:
        t[1] = -lo[1]
    g.wrap(scale=k, rotation=rotation, translation=t.tolist())
    g.save(dst)
    after = {"width": round(float(hi[0] - lo[0]), 4), "height": round(float(hi[1] - lo[1]), 4), "depth": round(float(hi[2] - lo[2]), 4)}
    return {"scale": round(k, 6), "by": axis, "size_m": after, "straightened": rotation is not None}


def angle_deg(q) -> float:
    return math.degrees(2 * math.acos(max(-1.0, min(1.0, abs(float(q[3]))))))
