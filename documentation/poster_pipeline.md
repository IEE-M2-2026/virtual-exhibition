# Preparing posters for the website

`tools/prepare_posters.py` reads `res/posters.json` and the originals in `res/posters/`. It writes three JPEG variants per poster and `docs/data/posters.json`. It does not modify the originals or editorial catalogue.

## Install and run

Use Python 3.11 or newer. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r tools/requirements.txt
.venv/bin/python tools/prepare_posters.py
```

On Windows, use `.venv\Scripts\python.exe` instead of `.venv/bin/python`. Pillow handles raster images; pypdfium2 renders PDFs without requiring a separate Poppler or Ghostscript installation.

For Mozilla's encoder on macOS:

```sh
HOMEBREW_NO_INSTALL_CLEANUP=1 brew install mozjpeg
.venv/bin/python tools/prepare_posters.py --encoder mozjpeg
```

The script detects MozJPEG on `PATH` and in standard Apple Silicon/Intel Homebrew locations. It checks `cjpeg -version`: a libjpeg-turbo binary with the same name is **not** treated as MozJPEG. For another installation location or platform, pass the executable explicitly:

```sh
.venv/bin/python tools/prepare_posters.py --encoder mozjpeg --cjpeg /path/to/mozjpeg/cjpeg
```

`--encoder auto` is the default: prefer MozJPEG, otherwise report the fallback and use Pillow. Explicit `--encoder mozjpeg` fails if unavailable; it never silently falls back. Use that option when regenerating a consistent collection. The manifest records the encoder and dependency versions. [MozJPEG](https://github.com/mozilla/mozjpeg) is Mozilla's JPEG encoder; its [command-line options](https://github.com/mozilla/mozjpeg/blob/master/usage.txt) document progressive encoding and sampling controls. Pillow's [JPEG documentation](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#jpeg) describes the fallback settings.

## Output contract

| Variant | Maximum long edge | Intended use |
| --- | ---: | --- |
| `thumbnail` | 512 px | Collective composition and catalogue |
| `texture` | 2048 px | 3D display panel |
| `detail` | 4096 px | Flat reading and zoom view |

All variants use progressive JPEG, quality 88 and 4:4:4 sampling. Each variant is made from the decoded original, never from another JPEG variant. Images retain their proportions without cropping or stretching. Raster sources are never enlarged; a small original can therefore produce texture and detail variants of the same dimensions. PDFs are rendered to the largest requested size before resizing.

EXIF orientation is applied. Embedded raster ICC profiles are converted to sRGB, then metadata is stripped. Untagged RGB/gray images are assumed to be sRGB; untagged CMYK/Lab images are rejected instead of guessing. Transparency is flattened onto white. PDFs use PDFium's RGB rendering; inspect unusual print colours or spot inks against the source, as this is a web rendition rather than a print proof.

Each output poster contains:

- `id`: the play title and playwright as an ASCII slug, followed by the first six hexadecimal characters of the original file's SHA-256. A conflicting prefix is extended only as far as necessary to distinguish files with the same slug. Exact duplicate originals with the same public slug are rejected. Unknown fields are omitted; if neither field yields a usable slug, use the neutral fallback `poster`. Original filenames never contribute to public names or IDs.
- `metadata`: only the public fields `title`, `author` and `premiere_year`, when present. `author` is the playwright; `premiere_year` is the year of first stage production. The original `filename` and any other local fields are excluded through an explicit allowlist.
- `source_sha256`: a checksum of the original file.
- `images`: `thumbnail`, `texture` and `detail`, each with `src`, `width`, `height`, `bytes` and `sha256`.

The manifest uses `schema_version: 2` and records generation settings. Each filename contains only the public ID and `.jpg`, for example `antigone-jean-anouilh-<checksum>.jpg`. Variants live in separate `posters/thumbnail/`, `posters/texture/` and `posters/detail/` directories.

The source checksum is recalculated on every run. It changes when the original bytes change, not merely because the converter was run again. Renaming an original does not change it. Changing a title or author changes the slug. No random generation suffix is added. To invalidate cached images when encoder settings change without modifying an original, the gallery appends a short prefix of the image's `sha256` as a query parameter.

The `src` paths are relative to the **website root**, not to `data/posters.json` or the JavaScript module:

```js
// Called from docs/index.html, including at /repository-name/ on Pages.
const siteRoot = new URL('./', document.baseURI);
const catalog = await fetch(new URL('./data/posters.json', siteRoot)).then(r => r.json());
const asset = catalog.posters[0].images.texture;
const imageURL = new URL(asset.src, siteRoot);
imageURL.searchParams.set('v', asset.sha256.slice(0, 8));
```

## Update the collection

For the complete site, run `./tools/rebuild.sh`: see [the rebuild guide](rebuild.md). It first runs `prepare_posters.py --check-catalog` and stops if any source is missing from the manually maintained catalogue. Neither command modifies `res/posters.json`. The manual workflow remains:

1. Add originals to `res/posters/` and add entries to `res/posters.json`. A `filename` alone is valid when nothing else is confirmed. Names must match exactly, including accents and spaces.
2. Run the converter. It validates catalogue coverage, rejects missing files, duplicate entries and multi-page/frame inputs, and ignores hidden system files such as `.DS_Store`. Supported sources are PDF, PNG, JPEG, TIFF and WebP.
3. Review the JPEGs and commit the new manifest with the images it references, including deletions from the previous iteration. Generated assets can be tracked for review, but every future site rebuild must rerun normalization before publishing.

Each successful run replaces the entire `docs/posters/` directory and `docs/data/posters.json`: a clean slate with no files left from previous normalization runs, including old filenames containing personal data. `posters/` is exclusively generated output; never keep hand-authored files there. Other website files, including other files under `data/`, are preserved.

Conversions are staged before replacement. If a conversion fails, the previous output manifest and images remain intact, and the site build must stop without deploying. The old poster directory is removed after successful replacement. Symlink output directories are rejected. Concurrent runs against the same output directory and serving files during replacement are not supported; complete the offline build before deploying the whole site artifact.

Before each site reconstruction, install the pinned Python dependencies and selected encoder, run `prepare_posters.py`, then publish only the complete `docs/` directory. The existing HTML, CSS and JavaScript need no bundler. The public manifest and asset paths must never contain original filenames or local student identity fields. This normalization does not edit any credits already visible inside the artwork.

Re-running converts the whole collection; there is no incremental cache. To compare encoders without touching the website output:

```sh
.venv/bin/python tools/prepare_posters.py --encoder pillow --output-dir /tmp/posters-pillow
.venv/bin/python tools/prepare_posters.py --encoder mozjpeg --output-dir /tmp/posters-mozjpeg
```

### Initial collection measurement

Historical measurement of the initial nine-poster collection, before removal of the *En attendant Godot* original: MozJPEG 4.1.5 and Pillow 13.0.0, using pypdfium2 5.14.0, quality 88 and identical dimensions and 4:4:4 sampling. The current collection is listed in `res/posters.json`.

| All nine posters | MozJPEG | Pillow |
| --- | ---: | ---: |
| Thumbnails | 0.410 MiB | 0.422 MiB |
| Textures | 3.508 MiB | 3.953 MiB |
| Detail images | 9.374 MiB | 11.042 MiB |
| Total: 27 JPEGs | 13.29 MiB | 15.42 MiB |

MozJPEG produced approximately 14% fewer bytes on this collection. The shared quality number is not an equal-perceptual-quality benchmark. The exported overview was visually inspected and all 27 JPEGs were decoded and checked against their manifest dimensions and checksums. The generated web assets use MozJPEG; further typography review can use the full-resolution detail files.

Other options include `--source-dir`, `--catalog`, `--quality`, `--thumbnail-size`, `--texture-size` and `--detail-size`. Default paths are anchored to the repository, so launching the script from another working directory is safe. Explicit relative paths are relative to the working directory.

## Verification and preview

```sh
.venv/bin/python -m unittest discover -s tools -p 'test_*.py'
.venv/bin/python -m http.server 8000 --bind 127.0.0.1 --directory docs
```

Open `http://127.0.0.1:8000/` to view the gallery. `docs/` is the complete directory published by GitHub Pages; the former `static/` output has been removed. See [the gallery guide](gallery.md) for deployment and interaction checks.
