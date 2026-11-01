# First 3D gallery — garage assembly and loading

The first visit is implemented in `docs/halle.html`, linked from the 2D gallery. The architecture uses the purchased garage by [TH-Studio](https://www.cgtrader.com/designers/th-studio), supplied in `res/3d/garage/`. Original FBXs and 4K maps stay outside the published directory. The supplied preview includes props which are not present as separate objects in these five FBXs; the implementation uses the geometry actually supplied.

## Assembly

Blender 4.0.2 imports the five FBXs and exports five geometry-only GLBs, preserving the existing common coordinate system and first UV layer. All five meshes are assembled in a single scene before baking. The scene is approximately 40 × 23 × 11 metres. Source collision objects (`UCX_*`) are omitted. The supplied second UV layer is replaced with a non-overlapping AO layout: one source part contains UVs outside the unit square. Both surface UVs and AO UVs are exported.

The roof (`SM_set_c`) has a source object translation of approximately −9.589 m vertically. Its mesh vertices already describe the roof at its assembled elevation. Resetting this object's translation restores the roof to approximately 7.95–11.23 m; the other four parts retain their existing transforms. Blender's exporter converts Z-up to glTF Y-up. No blind scale fitting or independent recentering is applied to parts.

All exported meshes share a **single `MeshStandardMaterial` instance** at runtime. No GLB contains an image, texture or material. The material receives four shared surface textures plus the filtered interior HDR environment:

| Map | Resolution | Encoding | Role |
| --- | --- | --- | --- |
| `albedo.webp` | 2048² | WebP quality 90 | sRGB colour |
| `normal.webp` | 1024² | Lossless WebP | Linear normal data |
| `surface.webp` | 1024² | Lossless WebP | UV0: green roughness, blue metallic, red unused/white |
| `ao.webp` | 3072 × 2048 | Lossless WebP | UV1: assembled ambient occlusion, red channel |

The roughness and metalness slots reference the **same texture object**, rather than separately decoding an identical URL. The contextual AO uses a separate UV layout and texture: packing it into the red channel of the repeating surface atlas would apply contact shadows to unrelated surfaces. Source normal-map handedness is not documented: the default preserves the source green channel (OpenGL interpretation); `--normal-y directx` explicitly flips it when required. The first visual review used the preserving default. External maps use `flipY=false` for glTF UVs, per the [Three.js GLTFLoader documentation](https://threejs.org/docs/pages/GLTFLoader).

## Assembled ambient occlusion and shader

`prepare_garage.py` bakes every mesh while **all five visible meshes remain in the same Cycles scene**. Collision proxies and movable exhibition panels are excluded. The AO node uses a 1.5 m reach, 64 rays and `only_local=False`; its scalar output is baked through Emission, without colour or lighting baked in. See the [Blender AO node reference](https://docs.blender.org/manual/en/4.2/render/shader_nodes/input/ao.html). The roof correction is applied before baking.

Smart UV projection creates a dedicated layout per part, retaining four-pixel island spacing and a 16px outer gutter. Blender EXTEND padding is set to twice the tile width (2048px at the default resolution), enough to fill every gap and outer gutter: island edge values propagate until they meet, instead of averaging against white at lower mip levels. The UV layout and island spacing are unchanged. Five 1024² tiles form a shared 3 × 2 atlas; the unused sixth tile extends the nearest adjacent populated edge too. Coarse mip levels can still mix neighbouring islands, but no artificial white background is introduced. UV0 retains the original colour/normal/surface layout; UV1 addresses the AO atlas. The geometry remains five separate, progressively loaded GLBs, with a single material and a single copy of every texture on the GPU. Per-part PNGs are inspection outputs, not additional downloads.

`docs/js/garage-material.js` customizes Three's standard PBR shader to sample the shared roughness/metalness map once: G controls roughness, B controls metallic response. Colour is decoded from sRGB; all numerical maps use linear data. Three's AO lighting code attenuates indirect diffuse and applies roughness-aware specular occlusion to environment reflections. It does not multiply the final image or the albedo, and it does not suppress direct sunlight. Normal mapping, direct shadows, tone mapping and standard metallic/dielectric behaviour are retained. This specialization is tied to the pinned Three.js release; browser checks exercise shader compilation.

The saved Blender material keeps albedo and AO separate too. Cycles computes its own light transport in a rendered preview, so the baked AO node is provided for inspection and web use, without multiplying colour and double-darkening the Blender render. The Blender preview and browser use different lighting models and are not pixel-identical.

Bake controls: `--ao-size 512|1024|2048` per tile, `--ao-samples 16|32|64|128`, `--ao-distance 1.5` in metres, `--device CPU|METAL`. CPU is the portable default; Metal is available on this machine. Changing geometry or its assembled placement requires rebuilding the AO. This is static architectural contact shading, not dynamic occlusion from visitors or movable posters.

## HDR sky, atmosphere and interior reflections

The lighting reference is [the interactive exhibition concept](img/Concept-Interactive-Theatre-Poster-Exhibition-1.png). Editable settings live in `res/3d/garage/lighting.json`; rebuilding copies them into the public manifest, so Blender and Three.js use the same sun direction, HDR sky and capture volume.

- Sun intensity is **7**, twice the previous 3.5. The hemisphere fill is 0.5 and interior-probe intensity is 4, so directional environment lighting is visible rather than dominated by a uniform fill. ACES exposure stays at 1.
- A locally generated **512 × 256 Radiance HDR gradient** blends a cool blue zenith into a bright horizon and warm ground. It drives Blender's world and the browser background/environment. It contains linear radiance above 1, rather than a tone-mapped JPEG with an HDR filename. No external sky service or downloaded third-party image is required.
- `FogExp2` uses density **0.006** and a pale grey-blue colour: roughly 2.2% fog at 25 m and 5.6% at 40 m along the view axis. This is a subtle depth haze, not volumetric light shafts.
- `tools/export_garage_environment.py` opens the assembled Blender project and renders **six 512² HDR faces**, with 64 Cycles samples and denoising, from Three-world position `[0, 3, 0]`. Only the five architectural meshes are present. Posters are excluded from the reflection capture.

The HDR output retains scene-linear lighting (see [Blender's colour pipeline](https://developer.blender.org/docs/features/cycles/units/)). The camera conversion is explicit: Three `(x, y, z)` becomes Blender `(x, -z, y)`. External Three cube textures flip X when converted to PMREM; the capture cameras account for that convention. Face order is `px, nx, py, ny, pz, nz`. The browser tests sample each original HDR face off-centre through the actual GPU cube lookup to catch axis swaps or mirrored faces.

Three prefilters the cubemap with PMREM for roughness-dependent reflections. The garage shader intersects each world-space reflection ray with the proxy box `[-20, 0.2, -10]` to `[20, 11.4, 10]`, then samples in the direction from the capture position to that intersection. This is **box-projected environment mapping**: reflections respond to the surface position and viewing direction instead of behaving like an infinitely distant sky. Zero ray components and small geometry protrusions are handled explicitly. Only the specular lookup receives this positional correction; diffuse environment lighting retains the standard irradiance calculation.

This single rectangular proxy approximates the hall's envelope; interior pillars, stairs and the pitched roof are not exact reflection geometry. It is a static reflection capture, not ray tracing or screen-space reflections. No poster reflections are implemented. The supplied surface maps remain shared; the shader increases roughness-map contrast across all architectural surfaces as described below. Metallic values are unchanged.

### Global roughness contrast

The source roughness map remains the input for every architectural surface. A floor-only multiplier made the floor too uniformly glossy, so it has been replaced by a single global contrast curve. The curve in `lighting.json` is applied identically in the web shader and Blender's shared material before the six HDR faces are rendered:

```text
roughness = clamp(0.5 + (source - 0.62) * 3, 0.25, 1.0)
```

The settings are `roughness.contrast`, `pivot`, `minimum` and `maximum`. Contrast is tripled around a pivot of 0.62; the lower bound prevents mirror-like finishes. Example values:

| Source roughness | Rendered roughness |
| ---: | ---: |
| 0.52 | 0.25 |
| 0.62 | 0.50 |
| 0.72 | 0.80 |
| 0.90 | 1.00 |

This retains the texture's spatial pattern, distinguishing smooth patches from matte areas on the floor, walls, roof, stairs and metalwork. The original maps are unchanged. There is no remaining floor-only roughness multiplier. Metallic values remain untouched, and every mesh still shares one material and one set of textures.

The separate normal-detail adjustment remains limited to upward-facing surfaces at `floor.height = 0.2`: `floor.normal_scale = 0.35` gives a normal strength of 0.21 instead of 0.6 there. It does not control roughness. Probe intensity remains 4, hemisphere fill 0.5 and sun intensity 7. Windows still reflect in smoother patches; posters remain absent from the capture. See the [previous versus contrasted roughness comparison](img/hall-roughness-contrast.jpg).

The saved `.blend` includes the updated sky and sun, a capture-position marker and a projection-volume marker. Its camera is restored to the overview after capture. The sky is packed into the project; the six generated reflection faces are published beside the garage models.

## Loading strategy and measured sizes

The model is already inexpensive: **11,764 source triangles**. Heavy geometry compression or a spatial streaming framework would add complexity for little benefit at this size. Keep the five small GLBs separate to open the space progressively, while treating textures as shared resources for the whole garage.

1. Load the local Three.js module, manifests, primary shell (`a`), corrected roof (`c`) and albedo.
2. Enable the visit immediately. Fetch the other three GLBs, normal map, packed surface map, AO atlas, HDR sky and interior cubemap in the background.
3. Load poster thumbnails in small batches. Upgrade only the selected or nearby visible poster to its 2048px variant. Dispose of the previous large poster texture when replacing it. Full-resolution detail images remain in the separate 2D reader.

This is progressive loading of a small complete room, not distance-based unloading of architectural zones. It remains useful on a slow connection: a delayed secondary part does not block the opening of the visit. A missing secondary asset leaves a usable partial scene with an explicit notice. A failed initial load or unavailable WebGL offers retry and a link to the 2D gallery.

Measured raw file sizes including HDR lighting:

| Asset group | Bytes | Approximate MiB |
| --- | ---: | ---: |
| Five GLBs together | 900,076 | 0.86 |
| Shared albedo | 876,426 | 0.84 |
| Shared normal | 1,141,372 | 1.09 |
| Shared packed surface | 325,568 | 0.31 |
| Shared AO atlas | 1,454,536 | 1.39 |
| HDR sky + six reflection faces | 5,026,267 | 4.79 |
| Entire garage with lighting | 9,724,245 | 9.27 |
| Initial shell + roof + albedo | 1,154,342 | 1.10 |
| Vendored Three.js + model/HDR loaders | 804,615 | 0.77 |

These numbers exclude poster images and HTTP compression; they are not elapsed loading times. The original four PNG maps total about 58.6 MiB. The four runtime garage maps represent roughly 64 MiB of decoded RGBA8 GPU data with mipmaps, before posters, environment, shadows and render buffers. Texture sharing saves GPU allocations as well as requests. Pixel ratio is capped at 1.5; static views render only when something changes. A small procedural environment serves as a fallback while the HDR assets load. The temporary source cubemap is disposed after PMREM conversion. A missing reflection face leaves the visit usable with the sky environment and a partial-load notice.

## Visit and provisional poster placement

- Drag with a mouse or one finger to grab the view: scenery follows the gesture horizontally and vertically.
- With the canvas focused, use ZQSD/WASD or arrow keys to move. The wheel moves forwards/backwards. On touch screens, use the poster arrows or selection list to move between viewing positions.
- Select a visible poster, use previous/next or choose a title to move in front of it. “Vue d’ensemble” returns to the entrance view. Reduced-motion preferences disable camera transitions.
- “Lire l’affiche” opens the existing 2D detail viewer for the same public ID. Direct `halle.html#poster=<id>` links are supported.

Posters are simple planes with neutral backs, placed automatically in two rows from the current catalogue. Positions and sizes adapt to the number of posters. Placement is intentionally provisional; no student-specific coordinates or final exhibition arrangement are encoded. Poster materials are unlit and excluded from scene tone mapping to preserve their colours.

Movement is clamped to the main floor rectangle. This version does not provide per-object collision, stairs or a walkable mezzanine. The garage is assembled from the purchased meshes; it is not a reconstruction of every prop or lighting condition shown in the supplier's preview.

## Rebuild

From the repository root, with the Python environment installed:

```sh
.venv/bin/python tools/prepare_posters.py --encoder mozjpeg
.venv/bin/python tools/prepare_garage.py --device METAL
npm --prefix tools ci
npm --prefix tools run vendor:three
python3 tools/version_frontend.py
python3 -m http.server 8000 --bind 127.0.0.1 --directory docs
```

Open `http://127.0.0.1:8000/halle.html`. The default Blender location is `/Applications/Blender.app/Contents/MacOS/Blender`; override with `--blender /path/to/blender`. `--texture-size` controls albedo, `--detail-texture-size` controls normal and packed surface maps. The full collection is rebuilt into staging directories and replaced on success. Originals and other website assets are preserved. The assembly, UV generation, bake and export are reproducible in `tools/export_garage.py`. The editable, compressed `res/3d/garage/baked/garage-assembled.blend` includes the five assembled meshes, a shared PBR material, packed textures, a preview camera and sun. It stays outside the published directory. Per-part PNGs, the full atlas and bake statistics are saved alongside it.

Three.js **0.187.0** and esbuild are pinned in `tools/package-lock.json`. `vendor_three.mjs` builds a local ESM bundle plus GLTFLoader, HDRLoader and HDRCubeTextureLoader, including their helper imports, and preserves the Three.js licence. Only the 3D page loads these modules. There is no runtime CDN, server rendering or asset service. GitHub Pages continues to publish the complete `docs/` directory.

## Validation

```sh
.venv/bin/python -m unittest discover -s tools -p 'test_*.py'
npm --prefix tools run test:gallery
npm --prefix tools run test:hall
/Applications/Blender.app/Contents/MacOS/Blender --background res/3d/garage/baked/garage-assembled.blend --python-exit-code 1 --python tools/check_garage_bake.py
```

The browser checks use real WebGL rendering in Chromium with SwiftShader for repeatable automated runs. Set `PLAYWRIGHT_BROWSER=firefox` to run the same suite in Playwright Firefox; optional `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` and `PLAYWRIGHT_FIREFOX_EXECUTABLE_PATH` select installed test binaries. They check mouse dragging on both axes, native emulated touch dragging in Chromium, asset requests, all five loaded parts, shared material/texture identity, poster navigation, texture eviction, keyboard movement, mobile layout, direct links, a deliberately delayed GLB, and the no-WebGL fallback. Asset tests also verify GLB UVs, absence of embedded textures and collision meshes, roof elevation, file checksums and packed-map channels. Screenshots are saved to a temporary directory and visually reviewed. Software-rendered test results do not constitute a frame-rate benchmark on a phone or a physical GPU.

The Blender check re-bakes a small shell probe twice, first with the assembled neighbours and then with them hidden. It verifies that neighbouring parts actually darken the AO, checks the two UV sets and packed project textures, and does not save the modified scene. A separate constant-colour island probe checks that EXTEND fills the entire image, including the corners; asset checks verify the padded per-part PNGs match the published atlas. Browser screenshots include the same view with a neutral white AO atlas for comparison.

Latest local verification: 13 Python asset/catalogue tests and both browser suites passed. The 256² Blender shell probe found 8,355 pixels whose occlusion increased by more than 0.05 with neighbouring parts present. The browser rendered all five AO-enabled meshes with one shared material and one request per garage texture; the neutral-AO comparison visibly changed architectural contact shading.

Lighting verification also exercises the injected box-projection GLSL on the GPU against analytical ray/box intersections, including parallel rays and a point just outside the proxy. The measured maximum error was below 0.000001 world units; off-centre HDR cube samples matched their source face pixels. Capture and sky radiance both exceeded 1. A failed HDR face was checked separately: navigation remains available with the sky fallback.

## Publishing and browser cache

GitHub Pages serves the HTML, JavaScript and CSS with a ten-minute cache lifetime observed on this deployment. A successful push can therefore coexist with an older module cached in a visitor's browser. Before committing changes to the front end, run `python3 tools/version_frontend.py` (or `npm --prefix tools run version:site`) and commit the updated HTML too. The tool appends each file's content hash to script/style URLs and versions import-map targets, including transitive garage material and HDR loader imports. Dynamic diagnostic imports resolve to the same module instance. Model and image URLs already use manifest hashes. Run `python3 tools/version_frontend.py --check` to detect stale frontend URLs.

After a push, allow the Pages deployment to finish. If a tab still shows the previous view, force reload with Cmd+Shift+R on macOS, or compare in a private window; HTML itself can still be cached briefly. On 2026-11-01, a clean browser session produced pixel-identical local and live screenshots, and all sixteen garage geometry/texture/HDR files matched their manifest hashes. The deployed lighting changes were present; no new deployment was required to recover them.

The global-contrast update passed the complete hall suite in both Chromium and Firefox. GPU checks validate the roughness curve at several heights, and separately verify that the normal-detail mask excludes walls, undersides and mezzanines. The six captured HDR faces were regenerated with the matching Blender material.
