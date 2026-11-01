#!/usr/bin/env python3
"""Compose complete original posters and coloured event tiles into a regular grid."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import sys
import tempfile

from PIL import Image, ImageCms, ImageDraw, ImageFont, ImageOps

from prepare_posters import ROOT, bounded_integer, load_catalog, poster_ids, render_source

PALETTE = ('#f5c842', '#ec674e', '#293db4', '#c9dc72', '#b5a0d6', '#191919')


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, default=ROOT / 'res/posters')
    parser.add_argument('--catalog', type=Path, default=ROOT / 'res/posters.json')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'res/event_poster')
    parser.add_argument('--width', type=bounded_integer(64, 16000), default=3508)
    parser.add_argument('--height', type=bounded_integer(64, 16000), default=4961)
    parser.add_argument('--dpi', type=bounded_integer(1, 1200), default=300)
    parser.add_argument('--margin', type=bounded_integer(0, 4000), default=0)
    parser.add_argument('--gutter', type=bounded_integer(0, 1000), default=0)
    parser.add_argument('--min-fillers', type=bounded_integer(1, 1000), default=1)
    parser.add_argument('--seed', type=int, default=2026)
    parser.add_argument('--hashtag', default='#IEE 2026')
    parser.add_argument('--title', default='CRÉATIONS SUR SCÈNES')
    parser.add_argument('--font', type=Path, help='TrueType/OpenType font file')
    return parser.parse_args(argv)


def choose_grid(count, aspect, width, height, margin=0, gutter=0, min_fillers=1):
    """Balance aspect-ratio mismatch against empty cells, with at least one event tile."""
    if count < 1 or aspect <= 0 or min_fillers < 1:
        raise ValueError('At least one poster and one filler, and a positive aspect ratio are required.')
    usable_w, usable_h = width - 2 * margin, height - 2 * margin
    if min(usable_w, usable_h) < 64:
        raise ValueError('Margins leave insufficient image space.')
    needed = count + min_fillers
    candidates = []
    for columns in range(1, min(needed, (usable_w + gutter) // (64 + gutter)) + 1):
        minimum_rows = math.ceil(needed / columns)
        # Exact ideal accounts for gutters: cell width / cell height = aspect.
        ideal_rows = (usable_h + gutter) / (
            (usable_w - (columns - 1) * gutter) / columns / aspect + gutter)
        for rows in {minimum_rows, max(minimum_rows, math.floor(ideal_rows)),
                     max(minimum_rows, math.ceil(ideal_rows))}:
            cell_w = (usable_w - (columns - 1) * gutter) / columns
            cell_h = (usable_h - (rows - 1) * gutter) / rows
            if min(cell_w, cell_h) < 64 or columns * rows > 2 * needed:
                continue
            capacity = columns * rows
            score = abs(math.log((cell_w / cell_h) / aspect)) + .6 * (capacity - count) / capacity
            candidates.append((score, capacity, columns, rows))
    if not candidates:
        raise ValueError('Grid cells would be smaller than 64 px; increase dimensions or reduce spacing.')
    _, _, columns, rows = min(candidates)
    return columns, rows


def cell_boxes(columns, rows, width, height, margin, gutter):
    """Half-open pixel bounds; distribute rounding pixels without gaps or overflow."""
    available_w = width - 2 * margin - (columns - 1) * gutter
    available_h = height - 2 * margin - (rows - 1) * gutter
    for row in range(rows):
        y0 = margin + row * available_h // rows + row * gutter
        y1 = margin + (row + 1) * available_h // rows + row * gutter
        for column in range(columns):
            x0 = margin + column * available_w // columns + column * gutter
            x1 = margin + (column + 1) * available_w // columns + column * gutter
            yield (x0, y0, x1, y1)


def select_font(explicit=None):
    candidates = [str(explicit)] if explicit else [
        '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        'C:/Windows/Fonts/arialbd.ttf',
        'DejaVuSans-Bold.ttf',
    ]
    for candidate in candidates:
        try:
            ImageFont.truetype(candidate, 20)
            return candidate
        except OSError:
            pass
    if explicit:
        raise ValueError(f'Cannot load font: {explicit}')
    return None


def text_colour(background):
    rgb = tuple(int(background[i:i + 2], 16) / 255 for i in (1, 3, 5))
    linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
    luminance = sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))
    return '#191919' if luminance > .2 else '#ffffff'


def draw_text_block(draw, text, box, colour, font_path, max_size):
    """Fit wrapped text using real glyph bounds, including accents and long words."""
    if not text.strip():
        return
    left, top, right, bottom = box
    for size in range(max(1, int(max_size)), 0, -1):
        font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default(size=size)
        lines = []
        for paragraph in text.splitlines():
            line = ''
            for word in paragraph.split():
                candidate = f'{line} {word}'.strip()
                if line and draw.textbbox((0, 0), candidate, font=font)[2] > right - left:
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            lines.append(line)
        content = '\n'.join(lines)
        spacing = max(1, round(size * .18))
        bounds = draw.multiline_textbbox((0, 0), content, font=font, spacing=spacing)
        if bounds[2] - bounds[0] <= right - left and bounds[3] - bounds[1] <= bottom - top:
            draw.multiline_text((left - bounds[0], top - bounds[1]), content,
                                font=font, fill=colour, spacing=spacing)
            return
    raise ValueError('Event text cannot fit; shorten it or increase image dimensions.')


def event_tile(size, background, mode, hashtag, title, font):
    tile = Image.new('RGB', size, background)
    draw = ImageDraw.Draw(tile)
    width, height = size
    pad = max(4, round(width * .085))
    colour = text_colour(background)
    # The year gets its own line for the default hashtag.
    heading = '\n'.join(hashtag.split())
    if mode == 'both':
        draw_text_block(draw, heading, (pad, pad, width - pad, height * .58),
                        colour, font, width * .28)
        draw_text_block(draw, title, (pad, height * .70, width - pad, height - pad),
                        colour, font, width * .105)
    else:
        draw_text_block(draw, heading if mode == 'hashtag' else title,
                        (pad, pad, width - pad, height - pad), colour, font,
                        width * (.28 if mode == 'hashtag' else .18))
    return tile


def prepare(args):
    source_dir = args.source_dir.resolve()
    output_dir = args.output_dir.resolve()
    entries = load_catalog(args.catalog, source_dir)
    # The output folder cannot coincide with, contain or sit inside the originals.
    if (source_dir.is_relative_to(output_dir) or output_dir.is_relative_to(source_dir)
            or args.catalog.resolve().is_relative_to(output_dir)):
        raise ValueError('Output directory must be separate from originals and catalogue.')
    if args.output_dir.is_symlink():
        raise ValueError('Output directory must not be a symlink.')
    if args.width * args.height > 100_000_000:
        raise ValueError('Output is limited to 100 million pixels.')
    font = select_font(args.font)
    ratios, digests = [], []
    for entry in entries:
        source = source_dir / entry['filename']
        digests.append(hashlib.sha256(source.read_bytes()).hexdigest())
        with render_source(source, 128) as preview:
            ratios.append(preview.width / preview.height)
    identifiers = poster_ids(entries, digests)
    columns, rows = choose_grid(len(entries), statistics.median(ratios), args.width, args.height,
                                args.margin, args.gutter, args.min_fillers)
    rng = random.Random(args.seed)
    slots = list(range(len(entries))) + [None] * (columns * rows - len(entries))
    rng.shuffle(slots)
    modes = (['both', 'hashtag', 'title'] if args.hashtag.strip() and args.title.strip()
             else ['hashtag'] if args.hashtag.strip() else ['title'])
    placements = []
    filler_number = 0
    colours = list(PALETTE)
    rng.shuffle(colours)
    canvas = Image.new('RGB', (args.width, args.height), 'white')
    for index, (slot, box) in enumerate(zip(slots, cell_boxes(
            columns, rows, args.width, args.height, args.margin, args.gutter))):
        x0, y0, x1, y1 = box
        cell_size = (x1 - x0, y1 - y0)
        placement = {'row': index // columns, 'column': index % columns, 'box': list(box)}
        if slot is None:
            mode = modes[0] if filler_number == 0 else rng.choice(modes)
            background = colours[filler_number % len(colours)]
            with event_tile(cell_size, background, mode, args.hashtag, args.title, font) as tile:
                canvas.paste(tile, (x0, y0))
            placement.update(kind='event', background=background, text_mode=mode)
            filler_number += 1
        else:
            with render_source(source_dir / entries[slot]['filename'], max(cell_size)) as original:
                with ImageOps.contain(original, cell_size, Image.Resampling.LANCZOS) as fitted:
                    x = x0 + (cell_size[0] - fitted.width) // 2
                    y = y0 + (cell_size[1] - fitted.height) // 2
                    canvas.paste(fitted, (x, y))
                    placement.update(kind='poster', id=identifiers[slot],
                                     image_box=[x, y, x + fitted.width, y + fitted.height])
        placements.append(placement)
    layout = {
        'schema_version': 1,
        'image': 'event-poster.png', 'width': args.width, 'height': args.height, 'dpi': args.dpi,
        'columns': columns, 'rows': rows, 'poster_count': len(entries), 'filler_count': filler_number,
        'seed': args.seed, 'margin': args.margin, 'gutter': args.gutter,
        'min_fillers': args.min_fillers, 'hashtag': args.hashtag, 'title': args.title,
        'font': Path(font).name if font else 'Pillow default', 'palette': list(PALETTE),
        'cells': placements,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    # Complete the render and decode check before replacing the previous image.
    with tempfile.TemporaryDirectory(prefix='.event-poster-', dir=output_dir) as temporary:
        stage = Path(temporary)
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        canvas.save(stage / 'event-poster.png', dpi=(args.dpi, args.dpi), icc_profile=profile)
        canvas.close()
        with Image.open(stage / 'event-poster.png') as check:
            check.load()
            if check.size != (args.width, args.height):
                raise ValueError('Generated image dimensions do not match.')
        (stage / 'layout.json').write_text(json.dumps(layout, ensure_ascii=False, indent=2) + '\n',
                                         encoding='utf-8')
        for name in ('event-poster.png', 'layout.json'):
            os.replace(stage / name, output_dir / name)
    print(f'{len(entries)} affiches + {filler_number} aplats ; grille {columns} × {rows} ; graine {args.seed}')
    print(f'{args.width} × {args.height} px, {args.dpi} dpi : {output_dir / "event-poster.png"}')
    return layout


def main():
    try:
        prepare(arguments())
    except (OSError, ValueError, RuntimeError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
