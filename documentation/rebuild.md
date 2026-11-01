# Rebuild the static exhibition

After adding or modifying an original in **`res/posters/`**, update **`res/posters.json`** manually if needed, then run:

```sh
./tools/rebuild.sh
```

The executable script also works from another working directory when invoked by its absolute path. It rebuilds all poster variants, the shared catalogue used by both galleries, the locally bundled Three.js modules and the frontend cache hashes. The complete website remains in `docs/`. It does not commit, push or start a web server.

## One-time setup

Use Python 3.11+ and Node.js 20+:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r tools/requirements.txt
npm ci --prefix tools
brew install mozjpeg
```

MozJPEG is required by default. For a deliberate Pillow fallback, run `./tools/rebuild.sh --encoder pillow`. `--encoder auto` prefers MozJPEG and reports a Pillow fallback when necessary. No dependencies are installed automatically. `PYTHON=/path/to/python ./tools/rebuild.sh` selects another prepared Python environment.

## New posters and editorial metadata

The script checks supported files directly inside `res/posters/` (PDF, PNG, JPEG, TIFF and WebP); it does not scan unrelated files throughout `res/`. Hidden files, including `.DS_Store`, are ignored. PDFs must contain exactly one page.

The private `res/posters.json` catalogue is **entirely manual and never modified by the script**. If any original is missing from the JSON, the script lists it and exits with a nonzero status before reconstruction, including before a requested Blender bake. It compares filenames, not just counts: two collections of equal size can still disagree. Add the missing entries yourself and rerun the script. A `filename` alone is valid when metadata is unconfirmed; otherwise fill in verified `title`, `author` and `premiere_year` fields. Original filenames remain private.

Modified originals are converted again and their source checksums determine the new public filenames. Every successful run replaces the entire generated `docs/posters/` collection, removing obsolete images. If an original has been removed or renamed, update its catalogue entry first: missing catalogued originals stop the build rather than silently deleting editorial information.

Conversion failures preserve the previous poster images and public manifest. The build stops on any error; review and publish only after it reports success. Two simultaneous runs of this wrapper are prevented by `.rebuild-lock/`. After a forced termination, remove an abandoned empty lock directory with `rmdir .rebuild-lock` once no build is running. Do not run the individual converters concurrently with the wrapper.

## Rebuild the architecture too

An ordinary poster update reuses and validates the existing 3D assets: poster panels load the shared catalogue at runtime, and posters are excluded from the reflection probe. There is no reason to repeat the Blender bake for a new PDF.

To rebuild from the garage sources as well, including the assembled Blender project, five GLBs, shared textures, AO and six HDR reflection faces:

```sh
./tools/rebuild.sh --full
# Optional on a Mac with supported Metal hardware:
BLENDER_DEVICE=METAL ./tools/rebuild.sh --full
```

Blender is required for this option. It is found on `PATH` or at `/Applications/Blender.app/Contents/MacOS/Blender`; `BLENDER=/path/to/blender` overrides this. CPU is the default rendering device. The full bake takes substantially longer. Use it after modifying garage geometry, source maps or `res/3d/garage/lighting.json`, or if the generated garage assets are missing. See [the 3D pipeline](hall_3d.md) for advanced bake settings.

## Preview and publish

```sh
.venv/bin/python -m http.server 8000 --bind 127.0.0.1 --directory docs
```

Open `http://127.0.0.1:8000/` and `http://127.0.0.1:8000/halle.html`. Review the result, then commit the source/catalogue changes and all generated changes in `docs/`, including deletions. Push normally; GitHub Pages publishes the complete `docs/` directory. See [gallery validation](gallery.md#validation) for optional browser checks.
