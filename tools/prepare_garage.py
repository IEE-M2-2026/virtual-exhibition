#!/usr/bin/env python3
"""Export five geometry-only GLBs and one shared texture set for the 3D hall."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]


def file_info(path):
    return {'src': f'./models/garage/{path.name}', 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blender', default=shutil.which('blender') or '/Applications/Blender.app/Contents/MacOS/Blender')
    parser.add_argument('--texture-size', type=int, choices=(1024, 2048, 4096), default=2048)
    parser.add_argument('--detail-texture-size', type=int, choices=(512, 1024, 2048, 4096), default=1024,
                        help='Normal and packed surface map size; default 1024 keeps the initial visit light.')
    parser.add_argument('--normal-y', choices=('opengl', 'directx'), default='opengl',
                        help='Source normal convention; default preserves the supplied green channel.')
    args = parser.parse_args()
    destination = ROOT / 'docs/models/garage'
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError('Generated garage directory must not be a symlink.')
    maps = ROOT / 'res/3d/garage/maps'
    with tempfile.TemporaryDirectory(prefix='.garage-', dir=destination.parent) as temporary:
        stage = Path(temporary)
        assets = stage / 'assets'
        subprocess.run([args.blender, '--background', '--factory-startup', '--python-exit-code', '1',
                        '--python', str(ROOT / 'tools/export_garage.py'), '--',
                        '--output-dir', str(assets)], check=True)
        parts = json.loads((assets / 'geometry.json').read_text())
        (assets / 'geometry.json').unlink()

        def load_map(name, size):
            with Image.open(maps / name) as original:
                return original.convert('RGB').resize((size, size), Image.Resampling.LANCZOS)

        albedo = load_map('T_Garage_02_albedo.png', args.texture_size)
        albedo.save(assets / 'albedo.webp', 'WEBP', quality=90, method=6)
        normal = load_map('T_Garage_02_normal.png', args.detail_texture_size)
        if args.normal_y == 'directx':
            red, green, blue = normal.split()
            normal = Image.merge('RGB', (red, ImageOps.invert(green), blue))
        normal.save(assets / 'normal.webp', 'WEBP', lossless=True, method=6)
        roughness = load_map('T_Garage_02_roughness.png', args.detail_texture_size).getchannel('R')
        metallic = load_map('T_Garage_02_Metallic.png', args.detail_texture_size).getchannel('R')
        # One shared GPU texture: G=roughness, B=metallic, R=white (no AO supplied).
        orm = Image.merge('RGB', (Image.new('L', roughness.size, 255), roughness, metallic))
        orm.save(assets / 'surface.webp', 'WEBP', lossless=True, method=6)
        textures = {name: file_info(assets / f'{name}.webp') for name in ('albedo', 'normal', 'surface')}
        manifest = {
            'schema_version': 1, 'credit': 'TH-Studio',
            'credit_url': 'https://www.cgtrader.com/designers/th-studio',
            'texture_size': args.texture_size, 'detail_texture_size': args.detail_texture_size,
            'normal_source_convention': args.normal_y,
            'parts': parts, 'textures': textures,
            'initial_parts': ['a', 'c'], 'remaining_parts': ['b', 'd', 'e'],
            'floor_y': 0.2, 'walk_bounds': {'x': [-17.5, 17.5], 'z': [-7.8, 7.8]},
            'overview': {'position': [16, 2.1, 0], 'target': [-8, 2.0, 0]},
        }
        (assets / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        backup = stage / 'previous'
        if destination.exists():
            os.replace(destination, backup)
        try:
            os.replace(assets, destination)
        except OSError:
            if backup.exists():
                os.replace(backup, destination)
            raise
    total = sum(p['bytes'] for p in parts) + sum(t['bytes'] for t in textures.values())
    print(f'Garage: {sum(p["triangles"] for p in parts):,} triangles, {len(parts)} GLBs, 3 shared textures, {total / 1024**2:.2f} MiB')
    print(destination / 'manifest.json')


if __name__ == '__main__':
    main()
