#!/usr/bin/env python3
"""Render the poster catalogue as web JPEGs and a static JSON manifest."""

import argparse
from contextlib import closing
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from importlib.metadata import version

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED = {'.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.webp'}


def bounded_integer(low, high):
    def parse(value):
        number = int(value)
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f'Expected {low}–{high}, got {value}')
        return number
    return parse


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, default=ROOT / 'res/posters')
    parser.add_argument('--catalog', type=Path, default=ROOT / 'res/posters.json')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'docs',
                        help='Website root; writes posters/ and data/posters.json')
    parser.add_argument('--encoder', choices=('auto', 'mozjpeg', 'pillow'), default='auto')
    parser.add_argument('--cjpeg', type=Path, help='Explicit path to MozJPEG cjpeg')
    parser.add_argument('--quality', type=bounded_integer(1, 95), default=88)
    for name, size in [('thumbnail', 512), ('texture', 2048), ('detail', 4096)]:
        parser.add_argument(f'--{name}-size', type=bounded_integer(1, 8192), default=size,
                            help=f'Maximum long edge in pixels (default: {size})')
    return parser.parse_args()


def select_encoder(args):
    if args.encoder == 'pillow':
        if args.cjpeg:
            raise ValueError('--cjpeg cannot be combined with --encoder pillow')
        return None, f'Pillow {version("Pillow")}'
    candidates = [args.cjpeg] if args.cjpeg else [
        shutil.which('cjpeg'),
        '/opt/homebrew/opt/mozjpeg/bin/cjpeg',
        '/usr/local/opt/mozjpeg/bin/cjpeg',
    ]
    for candidate in candidates:
        if not candidate or not Path(candidate).is_file():
            continue
        result = subprocess.run([str(candidate), '-version'], capture_output=True, text=True)
        identity = (result.stdout + result.stderr).strip()
        if result.returncode == 0 and 'mozjpeg' in identity.lower():
            return str(Path(candidate).resolve()), identity
    if args.encoder == 'mozjpeg' or args.cjpeg:
        raise ValueError('MozJPEG cjpeg not found. Install MozJPEG and pass --cjpeg /path/to/cjpeg.')
    print('MozJPEG not found; using Pillow (optimized progressive JPEG).', file=sys.stderr)
    return None, f'Pillow {version("Pillow")}'


def load_catalog(catalog_path, source_dir):
    entries = json.loads(catalog_path.read_text(encoding='utf-8'))
    if not isinstance(entries, list) or not entries:
        raise ValueError('The catalogue must be a non-empty JSON array.')
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('Each catalogue entry must be an object.')
        name = entry.get('filename')
        if not isinstance(name, str) or not name or Path(name).name != name or '\\' in name:
            raise ValueError(f'Expected a filename without a directory: {name!r}')
        normalized = unicodedata.normalize('NFC', name)
        if normalized in seen:
            raise ValueError(f'Duplicate catalogue filename: {name}')
        seen.add(normalized)
        source = source_dir / name
        if source.suffix.lower() not in SUPPORTED or not source.is_file():
            raise ValueError(f'Missing or unsupported poster: {source}')
        if not source.resolve().is_relative_to(source_dir.resolve()):
            raise ValueError(f'Poster points outside the source directory: {name}')
    unlisted = [p.name for p in source_dir.iterdir()
                if p.is_file() and not p.name.startswith('.') and p.suffix.lower() in SUPPORTED
                and unicodedata.normalize('NFC', p.name) not in seen]
    if unlisted:
        raise ValueError(f'Add these files to the catalogue first (filename alone is enough): {unlisted}')
    return entries


def poster_ids(entries, digests):
    """Use only public metadata and the shortest unique source prefix (min. 6)."""
    slugs = []
    for entry in entries:
        parts = []
        for field in ('title', 'author'):
            value = entry.get(field)
            if value is not None and not isinstance(value, str):
                raise ValueError(f'{field} must be a string when provided.')
            if value:
                ascii_value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode()
                part = re.sub(r'[^a-z0-9]+', '-', ascii_value.lower()).strip('-')
                if part:
                    parts.append(part)
        slugs.append('-'.join(parts)[:140].rstrip('-') or 'poster')
    pairs = list(zip(slugs, digests))
    if len(set(pairs)) != len(pairs):
        raise ValueError('Identical originals with the same public title/author; remove the duplicate entry.')
    identifiers = []
    for slug, digest in pairs:
        length = 6
        while any(other_slug == slug and other_digest != digest
                  and other_digest[:length] == digest[:length]
                  for other_slug, other_digest in pairs):
            length += 1
        identifiers.append(f'{slug}-{digest[:length]}')
    return identifiers


def raster_to_rgb(source):
    from PIL import Image, ImageCms, ImageOps

    with Image.open(source) as original:
        if getattr(original, 'n_frames', 1) != 1:
            raise ValueError(f'{source.name}: multiple frames; export one poster per file.')
        oriented = ImageOps.exif_transpose(original)
        alpha = oriented.convert('RGBA').getchannel('A')
        profile = oriented.info.get('icc_profile')
        color = oriented if oriented.mode in ('RGB', 'CMYK', 'L', 'LAB') else oriented.convert('RGB')
        if profile:
            # A failed profile conversion is an error, never a silent colour change.
            color = ImageCms.profileToProfile(
                color, ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                ImageCms.createProfile('sRGB'), outputMode='RGB')
        elif color.mode in ('CMYK', 'LAB'):
            raise ValueError(f'{source.name}: {color.mode} without an ICC profile; export as sRGB first.')
        else:
            color = color.convert('RGB')  # Untagged RGB/gray inputs are assumed to be sRGB.
        flattened = Image.new('RGB', color.size, 'white')
        flattened.paste(color, mask=alpha)
        return flattened


def render_source(source, max_size):
    if source.suffix.lower() != '.pdf':
        return raster_to_rgb(source)
    import pypdfium2 as pdfium

    with pdfium.PdfDocument(source) as pdf:
        if len(pdf) != 1:
            raise ValueError(f'{source.name}: {len(pdf)} PDF pages; export one poster per file.')
        pdf.init_forms()
        with closing(pdf[0]) as page:
            width, height = page.get_size()
            if min(width, height) <= 0:
                raise ValueError(f'{source.name}: invalid PDF page dimensions.')
            with closing(page.render(scale=max_size / max(width, height),
                                     fill_color=(255, 255, 255, 255))) as bitmap:
                # PDFium owns the buffer; copy before closing the document.
                return bitmap.to_pil().convert('RGB').copy()


def encode_jpeg(image, quality, cjpeg):
    stream = io.BytesIO()
    if cjpeg:
        image.save(stream, format='PPM')
        result = subprocess.run(
            [cjpeg, '-quality', str(quality), '-sample', '1x1', '-progressive', '-optimize'],
            input=stream.getvalue(), capture_output=True)
        if result.returncode:
            raise ValueError(f'MozJPEG failed: {result.stderr.decode(errors="replace").strip()}')
        return result.stdout
    image.save(stream, format='JPEG', quality=quality, subsampling=0,
               optimize=True, progressive=True)
    return stream.getvalue()


def prepare(args):
    from PIL import Image

    sizes = {name: getattr(args, f'{name}_size') for name in ('thumbnail', 'texture', 'detail')}
    if not sizes['thumbnail'] <= sizes['texture'] <= sizes['detail']:
        raise ValueError('Sizes must satisfy thumbnail <= texture <= detail.')
    source_dir, output_dir = args.source_dir.resolve(), args.output_dir.resolve()
    # Never allow generated paths to overwrite the original archive or catalogue.
    for destination in (output_dir / 'posters', output_dir / 'data'):
        if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
            raise ValueError(f'Output must be a real directory, not a file or symlink: {destination}')
        if (source_dir.is_relative_to(destination) or destination.is_relative_to(source_dir)
                or args.catalog.resolve().is_relative_to(destination)):
            raise ValueError('Output directories must be separate from the originals and catalogue.')
    entries = load_catalog(args.catalog, source_dir)
    source_digests = [hashlib.sha256((source_dir / entry['filename']).read_bytes()).hexdigest()
                      for entry in entries]
    identifiers = poster_ids(entries, source_digests)
    cjpeg, encoder_version = select_encoder(args)
    manifest = {
        'schema_version': 2,
        'generator': {
            'encoder': 'mozjpeg' if cjpeg else 'pillow',
            'encoder_version': encoder_version,
            'pillow_version': version('Pillow'),
            'pypdfium2_version': version('pypdfium2'),
            'quality': args.quality,
            'subsampling': '4:4:4',
            'progressive': True,
            'color_space': 'sRGB',
            'background': '#ffffff',
            'max_edges': sizes,
        },
        'posters': [],
    }
    print(f'Encoder: {encoder_version}', flush=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    # Finish all conversions before publishing any changed manifest or images.
    with tempfile.TemporaryDirectory(prefix='.posters-', dir=output_dir) as temporary:
        stage = Path(temporary)
        for variant in sizes:
            (stage / 'posters' / variant).mkdir(parents=True)
        for entry, identifier, source_digest in zip(entries, identifiers, source_digests):
            source = source_dir / entry['filename']
            item = {
                'id': identifier,
                # An allowlist prevents local filenames and future private fields leaking.
                'metadata': {key: entry[key] for key in ('title', 'author', 'premiere_year')
                             if key in entry},
                'source_sha256': source_digest,
                'images': {},
            }
            with render_source(source, sizes['detail']) as master:
                for variant, edge in sizes.items():
                    with master.copy() as resized:
                        resized.thumbnail((edge, edge), Image.Resampling.LANCZOS)
                        data = encode_jpeg(resized, args.quality, cjpeg)
                        # Verify the actual JPEG before exposing it to the website.
                        with Image.open(io.BytesIO(data)) as check:
                            check.load()
                            if check.format != 'JPEG' or check.size != resized.size:
                                raise ValueError(f'Invalid JPEG output for {source.name}')
                        digest = hashlib.sha256(data).hexdigest()
                        filename = f'{identifier}.jpg'
                        (stage / 'posters' / variant / filename).write_bytes(data)
                        item['images'][variant] = {
                            'src': f'./posters/{variant}/{filename}',
                            'width': resized.width,
                            'height': resized.height,
                            'bytes': len(data),
                            'sha256': digest,
                        }
                        total_bytes += len(data)
            manifest['posters'].append(item)
            print(f'Prepared {identifier}', flush=True)
        (stage / 'posters.json').write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (output_dir / 'data').mkdir(exist_ok=True)
        destination = output_dir / 'posters'
        backup = stage / 'previous-posters'
        if destination.exists():
            os.replace(destination, backup)
        installed = False
        try:
            os.replace(stage / 'posters', destination)
            installed = True
            os.replace(stage / 'posters.json', output_dir / 'data/posters.json')
        except OSError:
            if installed:
                shutil.rmtree(destination)
            if backup.exists():
                os.replace(backup, destination)
            raise
        # TemporaryDirectory deletes the entire previous iteration, including stale names.
    print(f'{len(entries)} posters, {len(entries) * len(sizes)} JPEGs, {total_bytes / 1024 / 1024:.2f} MiB')
    print(f'Manifest: {output_dir / "data/posters.json"}')


def main():
    args = arguments()
    try:
        prepare(args)
    except ImportError as error:
        print(f'Missing dependency: {error}. Run: python -m pip install -r tools/requirements.txt', file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
