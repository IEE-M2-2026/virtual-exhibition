# Theatre posters — exhibition brief

Status: the 2D gallery, image pipeline and first 3D garage visit are implemented. The collective composition and final poster arrangement remain future work. The 2D visual reference is [the Paris 8 gallery mockup](img/Concept-Paris-8-theatre-poster%20exhibition-2.png); the 3D architecture is the supplied TH-Studio garage.

## Purpose and visual direction

Present the students' theatre posters as one collective work and as individual designs. Both experiences must share the same catalogue and connect directly to each other.

The collective **meta-poster** takes its cue from [the reference photograph](img/exemple.jpg): a dense accumulation of posters, with varied scales and a strong overall silhouette. Compose it deliberately rather than randomly. Every poster must appear, remain identifiable and link to its individual view. Keep artwork proportions; avoid clipping titles or credits. Offer a downloadable composite later, once its layout and export dimensions are approved.

The **3D exhibition** evokes a repurposed industrial hall, following the atmosphere suggested by the STRAAT Museum reference: generous volumes, exposed structure, subdued materials and large freestanding display panels. This is an original space inspired by that setting. Keep architecture quiet enough for the students' work to dominate.

## Visitor experience

- Open on the collective composition with two clear actions: explore the posters or enter the hall.
- Start the hall visit at an overview. Select a poster to move to a comfortable viewing position; provide previous/next controls and an overview button. Guided viewpoints are the initial navigation model. Free walking is optional later.
- Open a flat, zoomable detail view for reading typography without perspective distortion. Show the play title, playwright and premiere year only when known. Student identities remain outside public metadata; any future publication of design credits requires a separate editorial decision.
- Connect each poster across the collective view, hall and detail view using the same public ID, derived from the play title, playwright and source-content checksum. It remains stable while those inputs are unchanged. Support a hash link such as `#poster=<id>` so direct links need no server routing.
- Provide keyboard controls, visible focus, labelled buttons, touch navigation, reduced-motion transitions and a responsive 2D catalogue when 3D is unavailable or unwanted. Essential information belongs in HTML as well as in the scene.

## Technical approach

Use plain HTML, CSS and JavaScript ES modules. The 2D gallery has no runtime dependencies; the separate 3D page uses locally vendored Three.js. No backend, database or runtime image conversion is required. Python and Blender run at build time to prepare assets. GitHub Pages serves the complete `docs/` directory, using the repository's branch deployment option with `/docs` selected.

Vendor a pinned Three.js release under `docs/vendor/three/`, retaining its licence. Copy the required build modules and selected addons **with their transitive dependencies** from that same release; use a local import map. This keeps runtime requests on the site's own host. Static hosting alone does not require vendoring, but self-contained dependencies suit the exhibition's preservation goals. See the [Three.js installation guide](https://threejs.org/manual/pages/installation.html).

Use relative URLs throughout so the site works beneath a GitHub Pages repository prefix. Publish only `docs/`; original PDFs, tools and documentation stay outside the deployed artifact. GitHub documents the [branch and folder publishing configuration](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

## Repository structure

```text
documentation/                 Brief, operating guide and visual references
res/
  posters/                     Untouched student originals
  posters.json                 Editorial source of truth
tools/
  prepare_posters.py           Offline conversion and manifest generation
  requirements.txt            Pinned Python dependencies
  test_prepare_posters.py      Pipeline regression checks
docs/                         Complete deployment root
  data/posters.json            Generated web catalogue
  posters/thumbnail/*.jpg      Generated thumbnails
  posters/texture/*.jpg        Generated 3D textures
  posters/detail/*.jpg         Generated reading images
  index.html                  Gallery entry point
  .nojekyll                   Serve the directory as plain static files
  css/gallery.css             Responsive gallery and detail viewer
  js/gallery.js               Catalogue loading, sorting and detail navigation
  halle.html                  First 3D garage visit
  css/hall.css                3D page layout and controls
  js/hall.js                  Shared materials, progressive loading and navigation
  models/garage/              Five geometry-only GLBs, four shared maps, HDR environments and manifest
  vendor/three/               Pinned Three.js bundle, GLTFLoader and licence
```

The “La halle 3D” navigation link and hall entry action now open `halle.html`. “Le projet” remains inactive. The initial 2D gallery order follows the editorial catalogue, with an optional alphabetical sort. Each poster opens a flat detail viewer with zoom, previous/next controls and an addressable hash. Escape closes the viewer and returns focus to the gallery. The 3D page provides guided poster viewpoints, drag-to-look, keyboard movement and a link back to each flat detail view.

## Public filenames and clean builds

Normalized filenames must contain only the play title, its playwright when known, and a short checksum derived from the original file's bytes. Use an ASCII slug and a six-character SHA-256 prefix, extending it only on collision. Store each image size in its own directory. Recompute the checksum on every generation; unchanged originals produce unchanged checksums. Never copy original filenames, paths or private student metadata into public asset names, IDs or JSON. Public editorial fields are restricted to `title`, `author` and `premiere_year`. Keep the complete source catalogue under `res/`, outside the deployed site.

Every site reconstruction must run normalization from a clean slate: replace all generated poster images and the public manifest, removing the previous iteration and any obsolete filenames. Stage and validate conversions first; a failed conversion must stop the build without deployment. The cleanup owns only `docs/posters/` and `docs/data/posters.json`, preserving originals and other website assets. Run this step before committing and publishing the completed `docs/` directory through GitHub Pages. Branch deployment serves these prebuilt files; it does not execute Python. Do not retain an archive of older normalized images in the deployment.

When an encoder setting changes but the original does not, use an image-checksum query parameter to refresh browser caches without adding extra data to filenames. Visible credits printed inside the artworks are not changed by the normalization process.

## Assets and performance

The pipeline produces progressive JPEGs with maximum long edges of 512, 2048 and 4096 pixels, preserving aspect ratios and never enlarging raster originals. Prefer MozJPEG, with Pillow available as a fallback. Both use quality 88 and 4:4:4 colour sampling as initial settings for typography and coloured edges. These are starting settings to evaluate on the artwork, not a guarantee of identical appearance across encoders. Details are in [the pipeline guide](poster_pipeline.md).

Load thumbnails for the collective view, load 3D textures as needed, and request a detail image only when its viewer opens. Dispose of unused GPU textures; compressed JPEG size does not represent GPU memory use. Use sRGB colour textures and avoid lighting or tone mapping that alters the posters' intended colours.

The first hall assembles the five supplied garage FBXs through Blender into separate geometry-only GLBs. A single shared material uses one albedo, one normal map and one packed roughness/metallic map and one assembled AO atlas on dedicated UVs. A reproducible Blender scene bakes contact occlusion with all five parts present; its packed project stays in `res/3d/garage/baked/`. The shell, roof and albedo open first; remaining pieces, surface detail, HDR sky and a Blender-rendered interior cubemap arrive in the background. Reflections use box projection based on surface position; a doubled sun and subtle fog refine the atmosphere. The shared roughness map has stronger contrast across the building, preserving matte areas and soft window reflections in smoother floor patches; poster reflections remain deferred. The complete garage is about 9.27 MiB, excluding Three.js and posters. Poster planes remain separate and are placed automatically in two provisional rows. Only the selected or nearby poster receives a higher-resolution texture; the previous high-resolution texture is disposed. See [the 3D implementation guide](hall_3d.md) for assembly, measured sizes and reproduction commands. Phone frame rate remains to be measured on physical hardware.

## Acceptance and open decisions

The initial website is ready when every catalogued poster is reachable from both views, its proportions and public metadata are correct, keyboard/touch and the 2D fallback work, and all assets load under a repository subpath without external runtime services. A rebuild must leave no obsolete poster files, and public asset paths and JSON must contain no original filenames or private student identity fields.

Before final design: confirm the exhibition title and student credits, identify the author and premiere year of *La Mouche*, refine the poster arrangement in the chosen garage, and decide the meta-poster's final composition and export format. Missing editorial information remains absent from JSON until confirmed.
