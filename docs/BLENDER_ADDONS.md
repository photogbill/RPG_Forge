# Blender add-ons on William's PC (Blender 5.3)

*Inventory by Claude Opus, 2026-11-21 01:50 (William, 01:46: "Every tool I can give you to help, I will … take an inventory"). The forge's own background runs use `--factory-startup`, so none of these load there unless a job names a profile (BUILD 98 Part 1a). Keep this list current when anything is added or removed.*

## Installed by Opus, 2026-11-21 (extensions.blender.org, GPL, free)

| Profile | Add-ons |
|---|---|
| buildings | Archimesh, Arch Generator, HiFi Architecture Builder, Gorani, TRZX Megacity, Bagapie |
| interiors | Home Builder 5, Archimesh |
| trees | Sapling Tree Gen, Modular Tree, Easy Tree, Space Colonization Tree Generator, IvyGen, Tree Wind Paint |
| scatter | Place Helper, Scatter Objects, Bagapie |
| ruins | Cell Fracture, H-Style RBD Nodes |
| materials | BAM AutoMat, BAM Decalit, Mat-Baker, The Better Baker, Texture Mixer, Material Randomizer Pro, PropGon UV Trim, Texel Kit |
| retopo_bake | CurioMesh, Relief Rebake, LODGen, Bake To Single Material, NK Combine & Bake |
| terrain | Erosion Terrain, PTerrain, SRTM Terrain Importer |
| godot_export | Goblend, OMI Physics Body glTF, Bezier Curves to Godot Path3D |
| animals / motion | Animal Animator, OpenVAT, Dynamic Skinning |
| cloth | ClothDrop Reborn |
| sky | Dynamic Sky, Sun Position |
| hard surface | CAD Sketcher, Bool Tool, Extra Mesh Objects, Edit Mesh Tools, F2, Snap Line, Tissue, Node Arrange |
| libraries | Poly Haven Lite, ambientCG Lite: in Blender 5.3 these are remote libraries in the Asset Browser, not add-ons (both CC0) |

## Installed by Opus from their authors, 2026-11-21 (William: "Go ahead an fetch each that you recommend")

- **BlenderKit** v3.21.7.261119 (github.com/BlenderKit; the free library: CC0 and Royalty-Free; RF is fine in the game as long as files aren't shipped loose). Kept: `_incoming\addons\blenderkit-v3.21.7.261119.zip` (sha256 762c731f…77c5).
- **BlenderGIS** (github.com/domlysz/BlenderGIS, master; GPL): OpenStreetMap, terrain, imagery for reference. On first enable it fetched its own FreeImage DLL (from domlysz/freeimage_bin) into the user's imageio folder. GDAL and PyProj are not present, so its reprojection is limited. Kept: `_incoming\addons\BlenderGIS-master.zip` (sha256 62fe4c73…316b).

## Installed 2026-11-21 01:55 from William's downloads (Gumroad)

- **blosm 2.8.1** (Prochitecture, GPL-3.0, extension): OpenStreetMap streets and buildings, terrain, imagery. Its data folder is set to `D:\RPG_Forge\local\blosm_data`. **Use OpenStreetMap only in the game.** blosm can also import Google 3D Tiles, whose terms don't allow use in a game. OpenStreetMap needs a credit line in the game's credits (ODbL).
- **Buildify 1.0** (Pavel Oliva): a geometry-nodes library in a .blend, not an add-on. It is kept at `D:\RPG_Forge\local\blender_assets\buildify\buildify_1.0.blend` and added to the Asset Browser as the **Buildify** library. Free for commercial work; the node graph itself may not be resold.

The downloads are kept in `D:\RPG_Forge\_incoming\addons\`.

## Installed by William (found 2026-11-21 01:48)

| Add-on | What it gives us |
|---|---|
| MPFB (MakeHuman for Blender) 2.0.18 | Human base bodies with clean topology and rigs, for NPCs and for fitting generated people. Check each asset pack's licence; the base assets are CC0. |
| CloudRig 2.2.32, Mixamo Rig 1.2.3, Wiggle Bones 1.1.2 | Rigging; Mixamo control rigs (William has Mixamo through Adobe); secondary motion for hair, capes (Valkyrie's), tails, ears |
| SMEAR 1.1.8 | Smear frames for fast moves (attack specials) |
| Brushstroke Tools 1.2.3 | Painterly strokes on 3D: candidates for the painted vistas (BUILD 98 Part 5) |
| ND 2.2.1, LoopTools 4.7.7, Cut Plane 1.2.0, EdgeFlow 1.1.2, PolyQuilt 1.46.8, Extra Curve Objects 0.2.0 | Hard-surface modelling and retopology: the motorcycle, the van, hero clean-up |
| Mio3 UV 2.2.0, UniV 4.0.0, Texel Density Checker | UV layout and texel density for hero assets |
| Ucupaint 3.0.2 | Layered texture painting (wear, dirt) |
| 3D Print Toolbox 1.5.0 | Mesh checks (non-manifold, thin walls, intersections): useful on generated models |
| A.N.T. Landscape 0.2.0 | Terrain look-dev |
| MCP 1.0.3 | The Blender connector Claude uses |

Built in and enabled: Cycles, glTF 2.0, FBX, BVH, SVG, UV Layout, Node Wrangler, Pose Library, Rigify.

## Review, 2026-11-21 02:45 (Claude Opus, BUILD 98 lane; William 02:22: "review all the new add-on's to blender")

Read live from William's Blender 5.3: **92 add-on modules, 78 enabled**, newest installed at 01:53 (Blosm). Nothing has been installed into this Blender since then; an add-on downloaded but not yet installed (or installed in another Blender) does not show here.

**Every enabled add-on now has a forge profile** (`forge\threed\blender\profiles.json`, 17 profiles: trees, buildings, interiors, scatter, ruins, materials, retopo_bake, terrain, osm, godot_export, animals, cloth, hard_surface, sky, people, painterly, uv). A job names one, and only that profile's add-ons load, through `blender.run` (connector) or `python -m forge.blenderrun run`. The forge's own world-queue Blender stays `--factory-startup` with none of them.

What each matters for in the Linden Mills slice, the ones that carry the most first:

| For | Add-ons | Notes |
|---|---|---|
| Trees and plants (98 Part 7) | Modular Tree, Sapling, Space Colonization, Easy Tree, IvyGen, **Tree Wind Paint** | Modular Tree for the hero species (dawn redwood, redwood, fruit trees); Sapling for quick bare-winter forms; Tree Wind Paint writes the wind colours Godot's sway shader reads |
| The house kit (98 Part 4) | **Buildify** (Asset Browser), Archimesh, Arch Generator, HiFi Architecture Builder, Bagapie | Buildify's modular graph is the base; Bagapie for railings, fences, ivy, arrays; Archimesh for windows and doors |
| Interiors | Home Builder 5 (with its own asset library), Archimesh | |
| Ground and dressing | Bagapie, Place Helper, Scatter Objects, BAM Decalit | |
| Materials from William's photos (Part 3) | **BAM AutoMat**, Texture Mixer, Material Randomizer Pro, PropGon UV Trim, Texel Kit, Ucupaint, the bakers | AutoMat makes a material from a folder of maps: the scans' last step |
| Generated models made game-ready | **CurioMesh**, PolyQuilt, EdgeFlow, LoopTools, Relief Rebake, **LODGen**, Bake To Single Material, NK Combine & Bake, **3D Print Toolbox** | 3D Print Toolbox's non-manifold and intersection checks are worth running on TRELLIS models (a future world-queue check) |
| Into Godot | **Goblend**, **OMI Physics Body** (collision shapes), Bezier Curves to Path3D | |
| Animals (Part 8) | Animal Animator (0.1.0, young: test before relying on it), OpenVAT, Dynamic Skinning, Wiggle Bones | OpenVAT also for laundry and flags |
| Painted vistas (Part 5) | Brushstroke Tools (+ its library), TRZX Megacity, Gorani, Dynamic Sky, Sun Position | Megacity is for city skylines (Washington, Atlanta), not for Prince William County's horizon |
| The War layer | Cell Fracture, H-Style RBD Nodes, Bool Tool | |
| Hero vehicles (Part 2) | CAD Sketcher, ND, Bool Tool, F2, Snap Line, Tissue, Extra Mesh/Curve Objects, Cut Plane | |
| People | MPFB, CloudRig, Mixamo Rig, Rigify, SMEAR | MPFB's base assets are CC0; check each extra asset pack's own licence before use |
| Real places | Blosm, BlenderGIS, PTerrain, SRTM | OpenStreetMap only, credited (ODbL); never Blosm's Google 3D Tiles |

**Found while reviewing (nothing changed in Blender):**
- **"Blendkit" is BlenderKit, renamed** (June 2026, at the Blender Foundation's request; blendkit.com). The add-on, its repository entry `www.blendkit.com` and its bundled local client (`bk_client-windows-x86_64.exe`, which talks only to blendkit.com) are the real thing. Blendkit also released a **Godot add-on** in August 2026: worth a look for the game side, under the same CC0 / Royalty-Free rules.
- **Poly Haven Lite and ambientCG Lite now load** (they are remote Asset Browser libraries in 5.3, and the restart fixed them).
- **BlenderGIS** put a FreeImage DLL in Blender's user folder on C: when first enabled. That is Blender's own add-on folder, not forge data, so it is left as it is.
- The **User Library** asset folder is on OneDrive (`Documents\Blender\Assets`). Nothing of the forge's goes there; the forge's own Blender assets live in `D:\RPG_Forge\local\blender_assets\`.
- Two profiles were missing add-ons when first written; fixed: PolyQuilt, Cut Plane, EdgeFlow, LoopTools → retopo_bake; Extra Curve Objects, Cut Plane → hard_surface; SMEAR → animals and people; Node Arrange's module name.
