# First 3D gallery — garage assembly and loading

The first visit is implemented in `docs/halle.html`, linked from the 2D gallery. The architecture uses the purchased garage by [TH-Studio](https://www.cgtrader.com/designers/th-studio), supplied in `res/3d/garage/`. Original FBXs and 4K maps stay outside the published directory. The supplied preview includes props which are not present as separate objects in these five FBXs; the implementation uses the geometry actually supplied.

## Assembly

Blender 4.0.2 imports the five FBXs and exports five geometry-only GLBs, preserving the existing common coordinate system and first UV layer. The scene is approximately 40 × 23 × 11 metres. Source collision objects (`UCX_*`) and the unused second/lightmap UV layer are omitted from the visible export.

The roof (`SM_set_c`) has a source object translation of approximately −9.589 m vertically. Its mesh vertices already describe the roof at its assembled elevation. Resetting this object's translation restores the roof to approximately 7.95–11.23 m; the other four parts retain their existing transforms. Blender's exporter converts Z-up to glTF Y-up. No blind scale fitting or independent recentering is applied to parts.

All exported meshes share a **single `MeshStandardMaterial` instance** at runtime. No GLB contains an image, texture or material. The material receives three external texture objects once:

| Map | Resolution | Encoding | Role |
| --- | --- | --- | --- |
| `albedo.webp` | 2048² | WebP quality 90 | sRGB colour |
| `normal.webp` | 1024² | Lossless WebP | Linear normal data |
| `surface.webp` | 1024² | Lossless WebP | Green: roughness; blue: metallic; red: white |

The roughness and metalness slots reference the **same texture object**, rather than separately decoding an identical URL. There is no supplied ambient-occlusion map, so the red channel is not presented as baked AO. Source normal-map handedness is not documented: the default preserves the source green channel (OpenGL interpretation); `--normal-y directx` explicitly flips it when required. The first visual review used the preserving default. External maps use `flipY=false` for glTF UVs, per the [Three.js GLTFLoader documentation](https://threejs.org/docs/pages/GLTFLoader).

## Loading strategy and measured sizes

The model is already inexpensive: **11,764 source triangles**. Heavy geometry compression or a spatial streaming framework would add complexity for little benefit at this size. Keep the five small GLBs separate to open the space progressively, while treating textures as shared resources for the whole garage.

1. Load the local Three.js module, manifests, primary shell (`a`), corrected roof (`c`) and albedo.
2. Enable the visit immediately. Fetch the other three GLBs, normal map and packed surface map in the background.
3. Load poster thumbnails in small batches. Upgrade only the selected or nearby visible poster to its 2048px variant. Dispose of the previous large poster texture when replacing it. Full-resolution detail images remain in the separate 2D reader.

This is progressive loading of a small complete room, not distance-based unloading of architectural zones. It remains useful on a slow connection: a delayed secondary part does not block the opening of the visit. A missing secondary asset leaves a usable partial scene with an explicit notice. A failed initial load or unavailable WebGL offers retry and a link to the 2D gallery.

Measured raw file sizes for the first export:

| Asset group | Bytes | Approximate MiB |
| --- | ---: | ---: |
| Five GLBs together | 681,024 | 0.65 |
| Shared albedo | 876,426 | 0.84 |
| Shared normal | 1,141,372 | 1.09 |
| Shared packed surface | 325,568 | 0.31 |
| Entire garage | 3,024,390 | **2.88** |
| Initial shell + roof + albedo | 1,104,770 | **1.05** |
| Vendored Three.js + GLTFLoader | 796,720 | 0.76 |

These numbers exclude poster images and HTTP compression; they are not elapsed loading times. The original four PNG maps total about 58.6 MiB. The three runtime garage maps represent roughly 32 MiB of decoded RGBA8 GPU data with mipmaps, before posters, environment, shadows and render buffers. Texture sharing saves GPU allocations as well as requests. Pixel ratio is capped at 1.5; static views render only when something changes. A procedural reflection environment avoids an additional HDR download.

## Visit and provisional poster placement

- Drag with a mouse or one finger to look around.
- With the canvas focused, use ZQSD/WASD or arrow keys to move. The wheel moves forwards/backwards. On touch screens, use the poster arrows or selection list to move between viewing positions.
- Select a visible poster, use previous/next or choose a title to move in front of it. “Vue d’ensemble” returns to the entrance view. Reduced-motion preferences disable camera transitions.
- “Lire l’affiche” opens the existing 2D detail viewer for the same public ID. Direct `halle.html#poster=<id>` links are supported.

Posters are simple planes with neutral backs, placed automatically in two rows from the current catalogue. Positions and sizes adapt to the number of posters. Placement is intentionally provisional; no student-specific coordinates or final exhibition arrangement are encoded. Poster materials are unlit and excluded from scene tone mapping to preserve their colours.

Movement is clamped to the main floor rectangle. This version does not provide per-object collision, stairs or a walkable mezzanine. The garage is assembled from the purchased meshes; it is not a reconstruction of every prop or lighting condition shown in the supplier's preview.

## Rebuild

From the repository root, with the Python environment installed:

```sh
.venv/bin/python tools/prepare_posters.py --encoder mozjpeg
.venv/bin/python tools/prepare_garage.py
npm --prefix tools ci
npm --prefix tools run vendor:three
python3 -m http.server 8000 --bind 127.0.0.1 --directory docs
```

Open `http://127.0.0.1:8000/halle.html`. The default Blender location is `/Applications/Blender.app/Contents/MacOS/Blender`; override with `--blender /path/to/blender`. `--texture-size` controls albedo, `--detail-texture-size` controls normal and packed surface maps. The full collection is rebuilt into staging directories and replaced on success. Originals and other website assets are preserved. No `.blend` project needs to be edited manually: the assembly correction is reproducible in `tools/export_garage.py`.

Three.js **0.187.0** and esbuild are pinned in `tools/package-lock.json`. `vendor_three.mjs` builds a local ESM bundle plus GLTFLoader, including its helper imports, and preserves the Three.js licence. Only the 3D page loads these modules. There is no runtime CDN, server rendering or asset service. GitHub Pages continues to publish the complete `docs/` directory.

## Validation

```sh
.venv/bin/python -m unittest discover -s tools -p 'test_*.py'
npm --prefix tools run test:gallery
npm --prefix tools run test:hall
```

The browser checks use real WebGL rendering in Chromium with SwiftShader for repeatable automated runs. They check asset requests, all five loaded parts, shared material/texture identity, poster navigation, texture eviction, keyboard movement, mobile layout, direct links, a deliberately delayed GLB, and the no-WebGL fallback. Asset tests also verify GLB UVs, absence of embedded textures and collision meshes, roof elevation, file checksums and packed-map channels. Screenshots are saved to a temporary directory and visually reviewed. Software-rendered test results do not constitute a frame-rate benchmark on a phone or a physical GPU.
