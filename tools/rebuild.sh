#!/usr/bin/env bash
# Rebuild the static website from any working directory.
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$project_root"

usage() {
  cat <<'HELP'
Usage: tools/rebuild.sh [--full] [--encoder mozjpeg|pillow|auto]

Rebuild docs/ after adding or changing originals in res/posters/:
  - check that every original has an entry in res/posters.json (never modified);
  - replace all normalized posters and the shared 2D/3D catalogue;
  - rebuild the locally bundled Three.js modules;
  - refresh and verify frontend cache hashes and existing garage assets.

--full      Also rebuild the Blender scene, GLBs, textures, AO and HDR probe.
            Otherwise, reuse the existing garage assets (checked for integrity).
--encoder   JPEG encoder; default: mozjpeg. Use pillow for an explicit fallback.
--help      Show this help.

Prerequisites:
  python3 -m venv .venv
  .venv/bin/python -m pip install -r tools/requirements.txt
  npm ci --prefix tools
  brew install mozjpeg  # macOS; or use --encoder pillow

Optional environment variables:
  PYTHON          Python executable (default: .venv/bin/python)
  BLENDER         Blender executable for --full (otherwise auto-detected)
  BLENDER_DEVICE  CPU (default) or METAL for --full

Output: docs/, ready for review and GitHub Pages. No commit or push is performed.
HELP
}

full=false
encoder=mozjpeg
while (($#)); do
  case "$1" in
    --full) full=true; shift ;;
    --encoder)
      if (($# < 2)); then usage >&2; exit 2; fi
      encoder="$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done
case "$encoder" in
  mozjpeg|pillow|auto) ;;
  *) printf 'Unknown encoder: %s\n' "$encoder" >&2; exit 2 ;;
esac

python_bin="${PYTHON:-$project_root/.venv/bin/python}"
if ! "$python_bin" -c 'import PIL, pypdfium2' >/dev/null 2>&1; then
  printf 'Python dependencies unavailable. See tools/rebuild.sh --help.\n' >&2
  exit 1
fi
printf '\nChecking originals against res/posters.json…\n'
"$python_bin" tools/prepare_posters.py --check-catalog
if ! command -v node >/dev/null || [[ ! -d tools/node_modules/three || ! -d tools/node_modules/esbuild ]]; then
  printf 'Install Node.js and run: npm ci --prefix tools\n' >&2
  exit 1
fi

# Avoid two normalizations replacing the same generated directories at once.
lock_dir="$project_root/.rebuild-lock"
if ! mkdir "$lock_dir" 2>/dev/null; then
  printf 'Another rebuild is running, or .rebuild-lock remains after an interrupted run.\n' >&2
  exit 1
fi
trap 'rmdir "$lock_dir"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if "$full"; then
  garage_args=(--device "${BLENDER_DEVICE:-CPU}")
  if [[ -n "${BLENDER:-}" ]]; then garage_args+=(--blender "$BLENDER"); fi
  printf '\nRebuilding the garage, AO and HDR probe with Blender…\n'
  "$python_bin" tools/prepare_garage.py "${garage_args[@]}"
fi
# Fail before replacing posters if the reused 3D export is absent or damaged.
"$python_bin" -m unittest discover -s tools -p 'test_garage_assets.py'

printf '\nNormalizing the complete poster collection…\n'
"$python_bin" tools/prepare_posters.py --encoder "$encoder"
printf '\nBundling Three.js and updating frontend versions…\n'
node tools/vendor_three.mjs
"$python_bin" tools/version_frontend.py
"$python_bin" tools/version_frontend.py --check
printf '\nBuild complete: %s/docs/\nReview the site, then commit and push to publish.\n' "$project_root"
