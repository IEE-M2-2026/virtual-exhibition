"""Assemble, bake world-space AO, save the Blender project and export shared-atlas GLBs."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import bpy
import numpy as np
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, required=True)
parser.add_argument('--project-dir', type=Path, required=True)
parser.add_argument('--ao-size', type=int, default=1024)
parser.add_argument('--ao-samples', type=int, default=64)
parser.add_argument('--ao-distance', type=float, default=1.5)
parser.add_argument('--device', choices=('CPU', 'METAL'), default='CPU')
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
args.output_dir.mkdir(parents=True, exist_ok=True)
args.project_dir.mkdir(parents=True, exist_ok=True)
started = time.monotonic()
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = 1  # The AO node itself casts ao_samples rays per shading point.
scene.cycles.seed = 0
if args.device == 'METAL':
    preferences = bpy.context.preferences.addons['cycles'].preferences
    preferences.compute_device_type = 'METAL'
    devices = preferences.get_devices_for_type('METAL')
    if not any(device.type == 'METAL' for device in devices):
        raise RuntimeError('No Metal device available; use --device CPU.')
    for device in devices:
        device.use = device.type == 'METAL'
    scene.cycles.device = 'GPU'
scene.render.bake.use_selected_to_active = False
# Reach every texel of a tile, even from its opposite corner. EXTEND propagates
# edge values until neighbouring islands meet, without moving the UVs.
scene.render.bake.margin = 2 * args.ao_size
scene.render.bake.margin_type = 'EXTEND'
scene.render.bake.use_clear = False
scene.view_settings.view_transform = 'Standard'
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.image_settings.color_depth = '8'
objects = []
for suffix in 'abcde':
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=str(ROOT / f'res/3d/garage/fbx/SM_set_{suffix}.fbx'))
    imported = set(bpy.data.objects) - before
    visible = []
    for obj in imported:
        if obj.type != 'MESH' or obj.name.startswith(('UCX_', 'UBX_', 'USP_')):
            bpy.data.objects.remove(obj, do_unlink=True)
        else:
            visible.append(obj)
    if len(visible) != 1:
        raise RuntimeError(f'Expected one visible mesh in part {suffix}')
    obj = visible[0]
    if suffix == 'c':
        obj.location = (0, 0, 0)  # Roof vertices already carry the assembled height.
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    while len(obj.data.uv_layers) > 1:
        obj.data.uv_layers.remove(obj.data.uv_layers[-1])
    obj.data.uv_layers[0].name = 'SurfaceUV'
    obj.data.uv_layers.new(name='AmbientUV')
    obj.data.uv_layers.active_index = 1
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=4 / args.ao_size,
                             margin_method='FRACTION',
                             area_weight=0.0, correct_aspect=True, scale_to_bounds=True)
    bpy.ops.object.mode_set(mode='OBJECT')
    # Preserve the existing outer gutter; its pixels will be fully dilated.
    border = 16 / args.ao_size
    # Edit mode can replace the UV storage; reacquire the layer afterwards.
    for loop in obj.data.uv_layers['AmbientUV'].data:
        loop.uv = loop.uv * (1 - 2 * border) + Vector((border, border))
    obj.data.materials.clear()
    material = bpy.data.materials.new(f'Bake_{suffix}')
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    output = nodes.new('ShaderNodeOutputMaterial')
    emission = nodes.new('ShaderNodeEmission')
    ao = nodes.new('ShaderNodeAmbientOcclusion')
    ao.samples = args.ao_samples
    ao.only_local = False  # ALL assembled meshes occlude the selected target.
    ao.inputs['Distance'].default_value = args.ao_distance
    links.new(ao.outputs['AO'], emission.inputs['Color'])
    links.new(emission.outputs[0], output.inputs['Surface'])
    target = nodes.new('ShaderNodeTexImage')
    target.image = bpy.data.images.new(f'AO_{suffix}', args.ao_size, args.ao_size, alpha=True)
    target.image.colorspace_settings.name = 'Non-Color'
    target.image.generated_color = (1, 1, 1, 1)
    target.image.pixels.foreach_set(np.ones(args.ao_size * args.ao_size * 4, dtype=np.float32))
    nodes.active = target
    obj.data.materials.append(material)
    objects.append((suffix, obj, target.image))

def uv_coverage(obj, size):
    """Pixel-centre coverage, independent of Blender's opaque bake background."""
    mask = np.zeros((size, size), dtype=bool)
    obj.data.calc_loop_triangles()
    uv = obj.data.uv_layers['AmbientUV'].data
    for triangle in obj.data.loop_triangles:
        a, b, c = [np.array(uv[index].uv) * size for index in triangle.loops]
        low = np.maximum(np.floor(np.minimum(np.minimum(a, b), c)).astype(int), 0)
        high = np.minimum(np.ceil(np.maximum(np.maximum(a, b), c)).astype(int), size)
        if np.any(high <= low):
            continue
        x, y = np.meshgrid(np.arange(low[0], high[0]) + 0.5, np.arange(low[1], high[1]) + 0.5)
        denominator = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(denominator) < 1e-10:
            continue
        u = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / denominator
        v = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / denominator
        mask[low[1]:high[1], low[0]:high[0]] |= (u >= 0) & (v >= 0) & (u + v <= 1)
    return mask


atlas_pixels = np.ones((args.ao_size * 2, args.ao_size * 3, 4), dtype=np.float32)
statistics = []
for index, (suffix, obj, image) in enumerate(objects):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    print(f'BAKE {suffix}: all {len(objects)} assembled parts visible', flush=True)
    bpy.ops.object.bake(type='EMIT', uv_layer='AmbientUV')
    pixels = np.empty(args.ao_size * args.ao_size * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    pixels = pixels.reshape(args.ao_size, args.ao_size, 4)
    covered = uv_coverage(obj, args.ao_size)
    values = pixels[:, :, 0][covered]
    if not values.size or values.min() > 0.98:
        raise RuntimeError(f'No useful occlusion baked for {suffix}')
    statistics.append({'part': suffix, 'covered_pixels': int(covered.sum()),
                       'min': float(values.min()), 'mean': float(values.mean()),
                       'occluded_fraction': float((values < 0.9).mean())})
    # Retain the full EXTEND result, including gutters. Restoring white here
    # would reintroduce bright seams when mipmaps average island boundaries.
    pixels[:, :, 3] = 1
    image.pixels.foreach_set(pixels.ravel())
    image.filepath_raw = str(args.project_dir / f'ao-{suffix}.png')
    image.file_format = 'PNG'
    image.save()
    col, row = index % 3, index // 3
    atlas_pixels[row * args.ao_size:(row + 1) * args.ao_size,
                 col * args.ao_size:(col + 1) * args.ao_size] = pixels
    for loop in obj.data.uv_layers['AmbientUV'].data:
        loop.uv = ((loop.uv.x + col) / 3, (loop.uv.y + row) / 2)
    obj.data.uv_layers.active_index = 0
    obj.data.uv_layers[0].active_render = True

# No mesh uses the sixth tile. Continue the closest populated edge into it so
# even coarse atlas mip levels do not average against an artificial white tile.
y, x = np.indices((args.ao_size, args.ao_size))
atlas_pixels[args.ao_size:, 2 * args.ao_size:] = np.where(
    (x <= y)[:, :, None],
    atlas_pixels[args.ao_size:, 2 * args.ao_size - 1][:, None, :],
    atlas_pixels[args.ao_size - 1, 2 * args.ao_size:][None, :, :])

atlas = bpy.data.images.new('Garage assembled AO atlas', args.ao_size * 3, args.ao_size * 2, alpha=False)
atlas.colorspace_settings.name = 'Non-Color'
atlas.pixels.foreach_set(atlas_pixels.ravel())
atlas.filepath_raw = str(args.project_dir / 'ao-atlas.png')
atlas.file_format = 'PNG'
atlas.save()

# One inspectable PBR material in the saved Blender scene. Cycles computes its
# own indirect visibility; the baked AO remains separate, as it does on the web.
material = bpy.data.materials.new('Garage shared PBR')
material.use_nodes = True
nodes, links = material.node_tree.nodes, material.node_tree.links
bsdf = nodes.get('Principled BSDF')
bsdf.location = (400, 100)
nodes.get('Material Output').location = (700, 100)
surface_uv = nodes.new('ShaderNodeUVMap')
surface_uv.uv_map = 'SurfaceUV'
surface_uv.location = (-800, 100)
for name, y in [('albedo', 500), ('normal', 100), ('surface', -300)]:
    node = nodes.new('ShaderNodeTexImage')
    node.name = name
    node.location = (-550, y)
    node.image = bpy.data.images.load(str(args.output_dir / f'{name}.webp'))
    node.image.colorspace_settings.name = 'sRGB' if name == 'albedo' else 'Non-Color'
    links.new(surface_uv.outputs['UV'], node.inputs['Vector'])
links.new(nodes['albedo'].outputs['Color'], bsdf.inputs['Base Color'])
normal = nodes.new('ShaderNodeNormalMap')
normal.uv_map = 'SurfaceUV'
normal.location = (-150, 100)
normal.inputs['Strength'].default_value = 0.6
links.new(nodes['normal'].outputs['Color'], normal.inputs['Color'])
links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
separate = nodes.new('ShaderNodeSeparateColor')
separate.location = (-150, -200)
links.new(nodes['surface'].outputs['Color'], separate.inputs[0])
links.new(separate.outputs['Green'], bsdf.inputs['Roughness'])
links.new(separate.outputs['Blue'], bsdf.inputs['Metallic'])
uv = nodes.new('ShaderNodeUVMap')
uv.uv_map = 'AmbientUV'
uv.location = (-800, -650)
node = nodes.new('ShaderNodeTexImage')
node.image = atlas
node.label = 'Baked AO for web indirect lighting (not albedo)'
node.location = (-550, -650)
links.new(uv.outputs['UV'], node.inputs['Vector'])
parts = []
for suffix, obj, _ in objects:
    obj.data.materials.clear()
    obj.data.materials.append(material)
    obj.data.calc_loop_triangles()
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    points = [Vector((p.x, p.z, -p.y)) for p in points]
    target = args.output_dir / f'garage-{suffix}.glb'
    bpy.ops.export_scene.gltf(filepath=str(target), export_format='GLB', use_selection=True,
        export_materials='NONE', export_animations=False, export_cameras=False, export_lights=False,
        export_texcoords=True, export_normals=True, export_yup=True, export_extras=False, export_apply=True)
    source = ROOT / f'res/3d/garage/fbx/SM_set_{suffix}.fbx'
    parts.append({'id': suffix, 'src': f'./models/garage/{target.name}', 'bytes': target.stat().st_size,
        'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'triangles': len(obj.data.loop_triangles),
        'bounds': [[round(min(p[i] for p in points), 5) for i in range(3)],
                   [round(max(p[i] for p in points), 5) for i in range(3)]]})
(args.output_dir / 'geometry.json').write_text(json.dumps(parts, indent=2) + '\n')
report = {'tile_size': args.ao_size, 'atlas_size': [args.ao_size * 3, args.ao_size * 2],
          'samples': args.ao_samples, 'distance_metres': args.ao_distance, 'device': args.device,
          'all_parts_occlude': True, 'uv_channel': 1, 'parts': statistics,
          'padding': 'EXTEND to tile edges; nearest adjacent edge in unused tile',
          'margin_pixels': scene.render.bake.margin,
          'seconds': round(time.monotonic() - started, 2)}
(args.project_dir / 'bake.json').write_text(json.dumps(report, indent=2) + '\n')
scene['ao_bake'] = json.dumps(report)
scene.world = bpy.data.worlds.new('Garage sky')
scene.world.use_nodes = True
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.6, 0.7, 0.85, 1)
scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.5
bpy.ops.object.light_add(type='SUN', location=(4, -12, 17))
sun = bpy.context.object
sun.name = 'Preview sun'
sun.rotation_euler = (math.radians(25), math.radians(-20), math.radians(-25))
sun.data.energy = 3
bpy.ops.object.camera_add(location=(16, 0, 2.1))
camera = bpy.context.object
camera.rotation_euler = (Vector((-8, 0, 2)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
camera.data.lens = 22
scene.camera = camera
scene.cycles.samples = 64
bpy.ops.object.select_all(action='DESELECT')
for _, obj, _ in objects:
    obj.select_set(True)
bpy.context.view_layer.objects.active = objects[0][1]
# Purge imported orphan meshes/materials too: their stale texture paths refer to
# absent supplier TGAs, and must not be included in the portable project.
bpy.data.orphans_purge(do_recursive=True)
bpy.ops.file.pack_all()
for image in bpy.data.images:
    if image.packed_file:
        image.filepath = '//' + Path(image.filepath).name
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.region_3d.view_perspective = 'CAMERA'
bpy.ops.wm.save_as_mainfile(filepath=str(args.project_dir / 'garage-assembled.blend'), compress=True)
print('BAKE COMPLETE', json.dumps(report), flush=True)
