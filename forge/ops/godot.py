"""Writers for Godot 4 resources the engine loads directly."""
from __future__ import annotations
from pathlib import Path


def tileset_tres(res_png_path: str, tile_size: int, count: int, blocking: list[bool],
                 collision_layer: int = 1, collision_mask: int = 1) -> str:
    """A TileSet with one atlas source over a horizontal strip of `count` tiles; `blocking[i]` adds a
    full-square collision polygon to tile i. Same shape the Turing Accords greybox uses."""
    half = tile_size // 2
    lines = ['[gd_resource type="TileSet" load_steps=3 format=3]', '',
             f'[ext_resource type="Texture2D" path="{res_png_path}" id="1_tiles"]', '',
             '[sub_resource type="TileSetAtlasSource" id="TileSetAtlasSource_1"]',
             'texture = ExtResource("1_tiles")', f'texture_region_size = Vector2i({tile_size}, {tile_size})']
    for i in range(count):
        lines.append(f"{i}:0/0 = 0")
        if i < len(blocking) and blocking[i]:
            lines.append(f"{i}:0/0/physics_layer_0/polygon_0/points = PackedVector2Array(-{half}, -{half}, {half}, -{half}, {half}, {half}, -{half}, {half})")
    lines += ['', '[resource]', f'tile_size = Vector2i({tile_size}, {tile_size})',
              f'physics_layer_0/collision_layer = {collision_layer}', f'physics_layer_0/collision_mask = {collision_mask}',
              'sources/0 = SubResource("TileSetAtlasSource_1")', '']
    return "\n".join(lines)


def write(path: Path, text: str) -> Path:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8", newline="\n")
    return Path(path)
