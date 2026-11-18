#!/usr/bin/env python3
"""Export the existing collective artwork as a public JPEG without private metadata."""
import argparse
import os
from pathlib import Path
import tempfile

from PIL import Image

from prepare_posters import ROOT, encode_jpeg, raster_to_rgb


def export(source, destination):
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve() or destination.is_symlink():
        raise ValueError('The public export must be separate from the original.')
    with raster_to_rgb(source) as image:
        image.thumbnail((2480, 2480), Image.Resampling.LANCZOS)
        payload = encode_jpeg(image, 90, None)
        size = image.size
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Finish conversion before replacing the previous public asset.
    with tempfile.TemporaryDirectory(prefix='.collective-', dir=destination.parent) as temporary:
        stage = Path(temporary) / 'poster.jpg'
        stage.write_bytes(payload)
        with Image.open(stage) as check:
            check.load()
            if check.size != size:
                raise ValueError('Public poster dimensions do not match.')
        os.replace(stage, destination)
    print(f'Collective poster: {destination.name}, {size[0]} × {size[1]}, {len(payload)} bytes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'res/event_poster/event-poster.png')
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/images/affiche-collective.jpg')
    args = parser.parse_args()
    export(args.source, args.output)


if __name__ == '__main__':
    main()
