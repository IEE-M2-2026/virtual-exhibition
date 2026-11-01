"""Run with Blender --background --factory-startup --python tools/export_garage.py."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--output-dir', type=Path, required=True)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
args.output_dir.mkdir(parents=True, exist_ok=True)
parts = []

for suffix in 'abcde':
    source = ROOT / f'res/3d/garage/fbx/SM_set_{suffix}.fbx'
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(source))
    for obj in list(bpy.context.scene.objects):
        if obj.type != 'MESH' or obj.name.startswith(('UCX_', 'UBX_', 'USP_')):
            bpy.data.objects.remove(obj, do_unlink=True)
    meshes = list(bpy.context.scene.objects)
    if not meshes:
        raise RuntimeError(f'No visible geometry: {source}')
    for obj in meshes:
        if suffix == 'c':
            # This FBX offsets its roof down by 9.589 m. The vertex coordinates
            # already contain the assembled roof height; restore the common origin.
            obj.location = (0, 0, 0)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        obj.data.materials.clear()
        while len(obj.data.uv_layers) > 1:
            obj.data.uv_layers.remove(obj.data.uv_layers[-1])
        obj.data.calc_loop_triangles()
    points = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    points = [Vector((p.x, p.z, -p.y)) for p in points]  # glTF Y-up, metres.
    target = args.output_dir / f'garage-{suffix}.glb'
    bpy.ops.export_scene.gltf(
        filepath=str(target), export_format='GLB', export_materials='NONE',
        export_animations=False, export_cameras=False, export_lights=False,
        export_texcoords=True, export_normals=True, export_yup=True,
        export_extras=False, export_apply=True)
    parts.append({
        'id': suffix, 'src': f'./models/garage/{target.name}',
        'bytes': target.stat().st_size,
        'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'triangles': sum(len(obj.data.loop_triangles) for obj in meshes),
        'bounds': [[round(min(p[i] for p in points), 5) for i in range(3)],
                   [round(max(p[i] for p in points), 5) for i in range(3)]],
    })

(args.output_dir / 'geometry.json').write_text(json.dumps(parts, indent=2) + '\n')
