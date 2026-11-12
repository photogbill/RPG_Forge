"""The two pictures a plan comes with, pixel-aligned with its rows (cell x, y covers pixels x*px … x*px+px-1).

  greybox     walkable vs blocking at a glance — or the game's own placeholder tiles when its adapter offers them
  paint guide flat colour regions (tiles.PAINT) with the story element in magenta — what the scene kit repaints
"""
from __future__ import annotations
from PIL import Image, ImageDraw

from . import tiles as T
from .plan import Plan


def _story_cells(p: Plan) -> set:
    s = p.story
    if not s:
        return set()
    return {(x, y) for y in range(s["y"], s["y"] + s["h"]) for x in range(s["x"], s["x"] + s["w"])}


def paint_guide(p: Plan, px: int = 32) -> Image.Image:
    g = p.grid
    im = Image.new("RGB", (g.w * px, g.h * px))
    d = ImageDraw.Draw(im)
    story = _story_cells(p)
    for y in range(g.h):
        for x in range(g.w):
            col = T.STORY_COLOUR if (x, y) in story else T.PAINT[g.c[y][x]]
            d.rectangle([x * px, y * px, x * px + px - 1, y * px + px - 1], fill=col)
    return im


def greybox(p: Plan, px: int = 32, tile_image=None) -> Image.Image:
    """tile_image(semantic tile, px) → an RGB(A) image of px×px, or None for the flat grey."""
    g = p.grid
    im = Image.new("RGB", (g.w * px, g.h * px))
    d = ImageDraw.Draw(im)
    cache: dict = {}
    for y in range(g.h):
        for x in range(g.w):
            t = g.c[y][x]
            tile = None
            if tile_image is not None:
                if t not in cache:
                    cache[t] = tile_image(t, px)
                tile = cache[t]
            if tile is not None:
                im.paste(tile.convert("RGB"), (x * px, y * px))
            else:
                d.rectangle([x * px, y * px, x * px + px - 1, y * px + px - 1], fill=T.GREY[t])
    # a hairline grid, so a cell is easy to count (drawn on the cell's last pixel row/column only)
    if px >= 8:
        for x in range(g.w):
            d.line([(x * px + px - 1, 0), (x * px + px - 1, g.h * px - 1)], fill=(40, 40, 44))
        for y in range(g.h):
            d.line([(0, y * px + px - 1), (g.w * px - 1, y * px + px - 1)], fill=(40, 40, 44))
    return im
