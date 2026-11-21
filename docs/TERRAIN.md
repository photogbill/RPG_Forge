# Terrain — real ground from DTED Level 0 (BUILD 77)

The forge reads DTED Level 0 itself (`forge/terrain/dted.py`, numpy only) and bakes windows of it into pictures a game can
use. Nothing of the data is ever committed: the cells stay where the person keeps them (`forge.json` → `"dted_dir"`,
default `local/dted`, a folder or a zip read in place), and `.gitignore` refuses `*.dt0`–`*.dt2` and `*.hgt`. The
graphics card is never used.

## Reading a cell

A cell is one degree square, named by its south-west corner (`w078/n38.dt0`). Header: UHL (80 bytes: origin, post spacing
in tenths of a second — read from each cell, never assumed — and the counts), DSI (648: the product level at byte 59),
ACC (2,700). Then one record a longitude line, west to east: `0xAA`, block count, longitude and latitude counts, the posts
south to north as big-endian 16-bit **sign-and-magnitude** words (not two's complement), and a checksum (the sum of the
record's bytes). The null post, −32767, is kept as null and never read as a pit. Every checksum is verified; a bad cell
is reported and skipped. A Level 1 or 2 file is skipped and reported, never read.

## The proof against known ground (2026-11-17, William's DTED0-World zip: 25,663 cells)

| place | published | the reader | difference | highest post within 2 km | cell |
|---|---|---|---|---|---|
| Mount Mitchell, North Carolina | 2037 m | 1909 m | -128 m | 1954 m | w083/n35.dt0 |
| Mount Elbert, Colorado | 4401 m | 4177 m | -224 m | 4229 m | w107/n39.dt0 |
| Mount Whitney, California | 4421 m | 4165 m | -256 m | 4285 m | w119/n36.dt0 |
| Pikes Peak, Colorado | 4302 m | 4125 m | -177 m | 4125 m | w106/n38.dt0 |
| Mount Washington, New Hampshire | 1917 m | 1750 m | -167 m | 1820 m | w072/n44.dt0 |
| Spruce Knob, West Virginia | 1482 m | 1469 m | -13 m | 1469 m | w080/n38.dt0 |
| Mont Ross, Kerguelen | 1850 m | 1270 m | -580 m | 1671 m | e069/s50.dt0 |
| Badwater Basin, Death Valley | -86 m | -27 m | +59 m |  | w117/n36.dt0 |
| New Orleans, Louisiana (city centre) | 0 m | 2 m | +2 m |  | w091/n29.dt0 |
| Denver, Colorado (State Capitol step) | 1609 m | 1606 m | -3 m |  | w105/n39.dt0 |

Summits read low by 221 m on average (worst 580 m): Level 0's posts are about 900 m apart and a sharp summit falls between them. Low ground agrees within 59 m. Badwater reads below sea level: the sign-and-magnitude words are read right.

Level 0 gives the big shapes: ranges, basins, the fall line, the Mississippi's flat. It gives nothing a person walks on.
So the world map and the far horizon come from it; the ground under a foot is it plus detail added on top (`detail_m`,
seeded and marked as invented); a town's pad is the place plan's (`flatten`). A window sampled much finer than the data's
posts is softened to the data's own scale first, so it has no facets. True scale looks flat: relief is exaggerated by a
dial and read mostly through light. DTED has no sea — the ocean is missing cells — so the sea is what a missing cell or the
window's edge reaches through ground at or below sea level (a basin below sea level that the sea cannot reach stays dry).

## The bakes (`forge/terrain/bake.py`; `terrain_bake.bat`; 3D → Terrain)

| job | what it writes |
|---|---|
| `terrain_window` | a 16-bit height picture; pixel 0 = `base_m`, 65535 = `base_m + range_m`; in game units divide by `shrink` |
| `terrain_shade` | a shaded relief from a chosen sun, hypsometric tint optional; with it, a picture of how each height was made — **blue measured, amber invented, red edited** |
| `terrain_water` | coast, rivers and lakes from Natural Earth (public domain) GeoJSON dropped in `local/natural_earth/` (`ne_10m_coastline`, `ne_10m_rivers_lake_centerlines`, `ne_10m_lakes`); without them it says which it wants |
| `terrain_edit` | the story's changes as data: a crater (centre, radius, depth, rim — nothing outside 1.6 radii touched), a flattened pad |
| `terrain_profile` | the ground along a straight line: the highest point, where a line at a grade goes in and comes out, the rock over it, where the cover is thinnest (where a shaft would really go), how far the ground falls away in front |

Dials: `posts`, `shrink`, `exaggerate` (a number or a curve `[[metres, factor], …]`), `sea_level`, `smooth`, `detail_m`
+ `seed`, `relief_x`, `sun_az`, `sun_el`, `tint`. Every output has a provenance file naming the window, the dials, the
source, the credit and the disclaimer.

A game's windows are geography only (`games/<id>/terrain/world.json`, public). Its story's edits and lines live in the
game's own folder (`terrain/story.json`), never in the forge.

## Credit and disclaimer (the release's own terms — NOAA/NGDC GLOBE report, chapter 12, read 2026-11-17)

DTED Level 0 was released to the public by NIMA as a derivative set. Products made with it carry the credit line —
*"This product was developed using DTED Level 0, a product of the National Imagery and Mapping Agency."* — and a disclaimer
that its use does not indicate endorsement or approval by the Secretary of Defense, the former Defense Mapping Agency or
NIMA; the data is provided as is, and DMA/NIMA names and seals may not be used to imply approval. A baked height picture is
a derived product; the release sets no other condition on it.
