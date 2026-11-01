# 2D theatre poster gallery

The gallery follows [the supplied mockup](img/Concept-Paris-8-theatre-poster%20exhibition-2.png): white page, IEE / Paris 8 header, five poster columns on wide screens, a responsive grid and restrained captions. “La halle 3D”, “Le projet” and the hall entry button are visible but inactive.

The current source collection contains eight posters. The *En attendant Godot* original was removed in commit `77e67f3`; its stale catalogue entry and generated images have been removed as well. There is no fallback to an obsolete export.

## Build and preview

```sh
.venv/bin/python tools/prepare_posters.py --encoder mozjpeg
.venv/bin/python -m http.server 8000 --bind 127.0.0.1 --directory docs
```

Open `http://127.0.0.1:8000/`. Install the Python dependencies first if needed, as described in [the pipeline guide](poster_pipeline.md). Every reconstruction regenerates and replaces the poster collection. The interface files are preserved. No JavaScript build step or runtime CDN is needed.

## GitHub Pages

The entire public site is `docs/`, including HTML, CSS, JavaScript, normalized JPEGs and the public JSON catalogue. In repository **Settings → Pages**, select **Deploy from a branch**, branch **main**, folder **/docs**, then save. Commit and push the reviewed website files to publish updates; this implementation does not perform that push or change repository settings.

`.nojekyll` disables Jekyll processing. All asset paths are relative, so the same directory works beneath `/virtual-exhibition/` or at a domain root. Keep original files, tooling, design references, task records and documentation outside `docs/`.

## Interactions

- Initial order follows the source catalogue, matching the reference sequence for the remaining posters.
- The title-sort button toggles alphabetical ascending/descending order. Both versions of *4.48 Psychose* remain distinct.
- Select an artwork to open its detail viewer. High-resolution images load only when the viewer opens.
- Use previous/next buttons or left/right arrow keys to browse. In zoom mode, arrow keys scroll the image instead. “Agrandir” / “Vue entière” toggles zoom.
- Escape or “Fermer” closes the viewer and restores focus. Hash links (`#poster=<id>`) open an artwork directly; browser history is supported.
- Missing author/year fields are omitted. The public catalogue never includes the original filenames or other private editorial fields. Credits already printed within artwork are unchanged.
- Loading, empty-collection and request-error states are explicit; a failed catalogue request offers “Réessayer”.

## Validation

Browser checks require Node.js 20 or newer; these development dependencies are not included in the published site.

```sh
.venv/bin/python -m unittest discover -s tools -p 'test_*.py'
cd tools
npm ci
npx playwright install chromium
npm run test:gallery
```

Browser tests run against a temporary local HTTP server under a repository-style prefix, then stop it. They check desktop/mobile layout, available posters, inactive navigation, sorting, detail viewing and keyboard/focus behavior, direct links, loading errors and missing metadata. Set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to use an existing Chromium binary. Test screenshots are temporary files outside the repository.

HTML/CSS were prepared through the Codex/Copilot-Ollama duo, then reviewed and integrated by Codex. See [the task and progress records](duo/progress.md).
