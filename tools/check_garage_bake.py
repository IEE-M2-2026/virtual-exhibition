"""Blender validation: rebake a small probe with/without neighbouring parts.

Run: Blender --background res/3d/garage/baked/garage-assembled.blend
     --python-exit-code 1 --python tools/check_garage_bake.py
The loaded project is never saved or changed on disk.
"""
import json

import bpy
import numpy as np

scene = bpy.context.scene
meshes = [obj for obj in scene.objects if obj.type == 'MESH']
assert len(meshes) == 5
assert len({obj.data.materials[0].as_pointer() for obj in meshes}) == 1
for obj in meshes:
    assert [uv.name for uv in obj.data.uv_layers] == ['SurfaceUV', 'AmbientUV']
    assert all(0 <= value <= 1 for loop in obj.data.uv_layers[1].data for value in loop.uv)
    index = 'abcde'.index(obj.name[-1])
    col, row = index % 3, index // 3
    for loop in obj.data.uv_layers[1].data:
        assert col / 3 < loop.uv.x < (col + 1) / 3
        assert row / 2 < loop.uv.y < (row + 1) / 2
for image in bpy.data.images:
    if image.source == 'FILE' and image.users:
        assert image.packed_file, image.name
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 1
scene.cycles.seed = 0
scene.render.bake.margin = 0
scene.render.bake.use_clear = True
scene.render.bake.use_selected_to_active = False
obj = next(obj for obj in meshes if obj.name == 'SM_set_a')
for loop in obj.data.uv_layers['AmbientUV'].data:
    loop.uv.x *= 3
    loop.uv.y *= 2
material = bpy.data.materials.new('Context verification only')
material.use_nodes = True
nodes, links = material.node_tree.nodes, material.node_tree.links
nodes.clear()
output = nodes.new('ShaderNodeOutputMaterial')
emission = nodes.new('ShaderNodeEmission')
ao = nodes.new('ShaderNodeAmbientOcclusion')
ao.samples = 64
ao.only_local = False
ao.inputs['Distance'].default_value = json.loads(scene['ao_bake'])['distance_metres']
links.new(ao.outputs['AO'], emission.inputs['Color'])
links.new(emission.outputs[0], output.inputs['Surface'])
node = nodes.new('ShaderNodeTexImage')
node.image = bpy.data.images.new('Context probe', 256, 256, alpha=True, float_buffer=True)
node.image.colorspace_settings.name = 'Non-Color'
nodes.active = node
obj.data.materials.clear()
obj.data.materials.append(material)
bpy.ops.object.select_all(action='DESELECT')
obj.select_set(True)
bpy.context.view_layer.objects.active = obj

def bake():
    bpy.ops.object.bake(type='EMIT', uv_layer='AmbientUV')
    data = np.empty(256 * 256 * 4, dtype=np.float32)
    node.image.pixels.foreach_get(data)
    return data.reshape(-1, 4)

assembled = bake()
for other in meshes:
    if other != obj:
        other.hide_render = True
isolated = bake()
covered = (assembled[:, 3] > 0.5) & (isolated[:, 3] > 0.5)
delta = isolated[covered, 0] - assembled[covered, 0]
affected = int((delta > 0.05).sum())
assert affected > 50, f'Expected neighbouring meshes to occlude the shell; affected={affected}'
assert delta.max() > 0.2
print('CONTEXT VERIFIED', json.dumps({'probe_pixels': int(covered.sum()),
    'pixels_darkened_by_neighbours_over_5_percent': affected,
    'largest_neighbour_occlusion': float(delta.max()),
    'mean_neighbour_occlusion': float(delta.mean())}), flush=True)

# Regression probe: a small dark island must dilate across the entire image.
# A white untouched gutter would brighten this constant map in coarse mipmaps.
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 1
scene.render.bake.margin = 2 * 64
scene.render.bake.margin_type = 'EXTEND'
scene.render.bake.use_clear = False
bpy.ops.mesh.primitive_plane_add()
obj = bpy.context.object
for loop in obj.data.uv_layers[0].data:
    loop.uv = loop.uv * 0.25
    loop.uv.x += 0.375
    loop.uv.y += 0.375
material = bpy.data.materials.new('Padding probe')
material.use_nodes = True
nodes, links = material.node_tree.nodes, material.node_tree.links
nodes.clear()
output = nodes.new('ShaderNodeOutputMaterial')
emission = nodes.new('ShaderNodeEmission')
emission.inputs['Color'].default_value = (0.25, 0.25, 0.25, 1)
links.new(emission.outputs[0], output.inputs['Surface'])
node = nodes.new('ShaderNodeTexImage')
node.image = bpy.data.images.new('Padding probe', 64, 64, alpha=True, float_buffer=True)
node.image.colorspace_settings.name = 'Non-Color'
node.image.pixels.foreach_set(np.ones(64 * 64 * 4, dtype=np.float32))
nodes.active = node
obj.data.materials.append(material)
bpy.ops.object.bake(type='EMIT')
pixels = np.empty(64 * 64 * 4, dtype=np.float32)
node.image.pixels.foreach_get(pixels)
assert np.allclose(pixels.reshape(-1, 4)[:, :3], 0.25, atol=0.001)
print('PADDING VERIFIED: island values reach all texels, including image corners', flush=True)
