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
    parser.add_argument('--ao-size', type=int, choices=(512, 1024, 2048), default=1024)
    parser.add_argument('--ao-samples', type=int, choices=(16, 32, 64, 128), default=64)
    parser.add_argument('--ao-distance', type=float, default=1.5, help='AO reach in metres.')
    parser.add_argument('--device', choices=('CPU', 'METAL'), default='CPU')
    args = parser.parse_args()
    if not 0 < args.ao_distance < 100:
        parser.error('--ao-distance must be between 0 and 100 metres')
    destination = ROOT / 'docs/models/garage'
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError('Generated garage directory must not be a symlink.')
    maps = ROOT / 'res/3d/garage/maps'
    with tempfile.TemporaryDirectory(prefix='.garage-', dir=destination.parent) as temporary:
        stage = Path(temporary)
        assets = stage / 'assets'
        assets.mkdir()
        project = stage / 'baked'

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
        # Surface UVs repeat: contextual AO must use its own atlas and UV channel.
        orm = Image.merge('RGB', (Image.new('L', roughness.size, 255), roughness, metallic))
        orm.save(assets / 'surface.webp', 'WEBP', lossless=True, method=6)
        subprocess.run([args.blender, '--background', '--factory-startup', '--python-exit-code', '1',
                        '--python', str(ROOT / 'tools/export_garage.py'), '--',
                        '--output-dir', str(assets), '--project-dir', str(project),
                        '--ao-size', str(args.ao_size), '--ao-samples', str(args.ao_samples),
                        '--ao-distance', str(args.ao_distance), '--device', args.device], check=True)
        parts = json.loads((assets / 'geometry.json').read_text())
        (assets / 'geometry.json').unlink()
        with Image.open(project / 'ao-atlas.png') as baked:
            baked.convert('RGB').save(assets / 'ao.webp', 'WEBP', lossless=True, method=6)
        textures = {name: file_info(assets / f'{name}.webp') for name in ('albedo', 'normal', 'surface', 'ao')}
        manifest = {
            'schema_version': 2, 'credit': 'TH-Studio',
            'credit_url': 'https://www.cgtrader.com/designers/th-studio',
            'texture_size': args.texture_size, 'detail_texture_size': args.detail_texture_size,
            'normal_source_convention': args.normal_y,
            'ao': {'size': [args.ao_size * 3, args.ao_size * 2], 'uv_channel': 1,
                   'distance_metres': args.ao_distance, 'samples': args.ao_samples},
            'parts': parts, 'textures': textures,
            'initial_parts': ['a', 'c'], 'remaining_parts': ['b', 'd', 'e'],
            'floor_y': 0.2, 'walk_bounds': {'x': [-17.5, 17.5], 'z': [-7.8, 7.8]},
            'overview': {'position': [16, 2.1, 0], 'target': [-8, 2.0, 0]},
        }
        (assets / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        project_destination = ROOT / 'res/3d/garage/baked'
        if project_destination.is_symlink():
            raise ValueError('Generated Blender directory must not be a symlink.')
        backup = stage / 'previous'
        project_backup = stage / 'previous-baked'
        moved, installed = [], []
        try:
            for current, old in ((project_destination, project_backup), (destination, backup)):
                if current.exists():
                    os.replace(current, old)
                    moved.append((current, old))
            for prepared, current in ((project, project_destination), (assets, destination)):
                os.replace(prepared, current)
                installed.append(current)
        except OSError:
            for current in reversed(installed):
                shutil.rmtree(current)
            for current, old in reversed(moved):
                os.replace(old, current)
            raise
    total = sum(p['bytes'] for p in parts) + sum(t['bytes'] for t in textures.values())
    print(f'Garage: {sum(p["triangles"] for p in parts):,} triangles, {len(parts)} GLBs, 4 shared textures, {total / 1024**2:.2f} MiB')
    print(destination / 'manifest.json')


if __name__ == '__main__':
    main()
