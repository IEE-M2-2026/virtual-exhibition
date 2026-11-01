"""Blender script: export each existing mesh object to its own validated FBX.

Usage: blender -b --factory-startup --python-exit-code 1
       --python tools/split_fbx_objects.py -- input.fbx --output-dir output/
"""

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

import bpy


def snapshot(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    # Compare actual world-space geometry and per-corner UVs after round-trip.
    vertices = [obj.matrix_world @ vertex.co for vertex in mesh.vertices]
    corners = Counter(
        tuple(round(value, 4) for value in vertices[loop.vertex_index])
        + tuple(round(value, 5) for layer in mesh.uv_layers for value in layer.data[loop.index].uv)
        for loop in mesh.loops
    )
    return {
        'vertices': len(mesh.vertices), 'polygons': len(mesh.polygons),
        'triangles': len(mesh.loop_triangles),
        'uv_layers': [layer.name for layer in mesh.uv_layers],
        'materials': [material.name if material else None for material in mesh.materials],
        'world_bounds': [[min(point[i] for point in vertices) for i in range(3)],
                         [max(point[i] for point in vertices) for i in range(3)]],
        'corners': corners,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    source, output = args.source.resolve(), args.output_dir.resolve()
    if output.exists():
        raise ValueError(f'Output directory already exists; choose a new directory: {output}')
    original_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(source))
    objects = sorted(bpy.context.scene.objects, key=lambda obj: obj.name)
    if not objects or any(obj.type != 'MESH' for obj in objects):
        raise ValueError('This splitter requires a scene containing only mesh objects.')
    output.parent.mkdir(parents=True, exist_ok=True)
    expected, records, filenames = {}, [], set()
    with tempfile.TemporaryDirectory(prefix='.fbx-objects-', dir=output.parent) as temporary:
        stage = Path(temporary) / 'exports'
        stage.mkdir()
        for obj in objects:
            filename = re.sub(r'[^A-Za-z0-9_.-]', '_', obj.name) + '.fbx'
            if filename.casefold() in filenames:
                raise ValueError(f'Output filename collision: {filename}')
            filenames.add(filename.casefold())
            expected[filename] = snapshot(obj)
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            bpy.ops.export_scene.fbx(
                filepath=str(stage / filename), use_selection=True, object_types={'MESH'},
                use_mesh_modifiers=False, bake_anim=False, add_leaf_bones=False,
                path_mode='RELATIVE', embed_textures=False,
                axis_forward='-Z', axis_up='Y')
            records.append({'filename': filename, 'object': obj.name, 'type': obj.type,
                            'collision': obj.name.startswith('UCX_')})

        for record in records:
            path = stage / record['filename']
            bpy.ops.wm.read_factory_settings(use_empty=True)
            bpy.ops.import_scene.fbx(filepath=str(path))
            restored = list(bpy.context.scene.objects)
            if len(restored) != 1 or restored[0].type != 'MESH':
                raise ValueError(f'{path.name}: expected exactly one mesh object.')
            if restored[0].name != record['object']:
                raise ValueError(f'{path.name}: object name changed on reimport.')
            actual, before = snapshot(restored[0]), expected[path.name]
            for field in ('vertices', 'polygons', 'triangles', 'uv_layers', 'materials', 'corners'):
                if actual[field] != before[field]:
                    raise ValueError(f'{path.name}: {field} changed on reimport.')
            if any(abs(a-b) > 0.0001 for old, new in zip(before['world_bounds'], actual['world_bounds'])
                   for a, b in zip(old, new)):
                raise ValueError(f'{path.name}: world-space bounds changed on reimport.')
            record.update({key: value for key, value in actual.items() if key != 'corners'})
            record['bytes'] = path.stat().st_size
            record['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            print(f'Verified {path.name}: one object, geometry and UVs preserved.')

        if hashlib.sha256(source.read_bytes()).hexdigest() != original_digest:
            raise ValueError('Original file changed during export.')
        (stage / 'manifest.json').write_text(json.dumps({
            'source': source.name, 'source_sha256': original_digest,
            'blender_version': bpy.app.version_string,
            'split_mode': 'existing_objects', 'exports': records,
        }, ensure_ascii=False, indent=2) + '\n')
        os.rename(stage, output)
    print(f'Exported and verified {len(records)} FBXs: {output}')


if __name__ == '__main__':
    main()
