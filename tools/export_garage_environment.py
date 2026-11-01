"""Blender: render a linear HDR sky and six static garage reflection faces."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import bpy
import numpy as np
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, required=True)
parser.add_argument('--project', type=Path, required=True)
parser.add_argument('--device', choices=('CPU', 'METAL'), default='CPU')
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
config = json.loads((ROOT / 'res/3d/garage/lighting.json').read_text())
args.output_dir.mkdir(parents=True, exist_ok=True)
started = time.monotonic()
bpy.ops.wm.open_mainfile(filepath=str(args.project))
scene = bpy.context.scene
assert len([obj for obj in scene.objects if obj.type == 'MESH']) == 5
scene.render.engine = 'CYCLES'
scene.cycles.samples = config['probe']['samples']
scene.cycles.use_denoising = True
scene.cycles.seed = 0
scene.cycles.max_bounces = 8
if args.device == 'METAL':
    preferences = bpy.context.preferences.addons['cycles'].preferences
    preferences.compute_device_type = 'METAL'
    devices = preferences.get_devices_for_type('METAL')
    if not any(device.type == 'METAL' for device in devices):
        raise RuntimeError('Metal device unavailable')
    for device in devices:
        device.use = device.type == 'METAL'
    scene.cycles.device = 'GPU'
else:
    scene.cycles.device = 'CPU'

# One original, linear HDR gradient drives Blender's world and the web sky.
width, height = 512, 256
altitude = np.sin(((np.arange(height) + 0.5) / height - 0.5) * math.pi)
horizon = np.array(config['sky']['horizon'])
zenith = np.array(config['sky']['zenith'])
ground = np.array(config['sky']['ground'])
amount = np.sqrt(np.abs(altitude))[:, None]
colors = np.where((altitude >= 0)[:, None], horizon * (1 - amount) + zenith * amount,
                  horizon * (1 - amount) + ground * amount)
pixels = np.ones((height, width, 4), dtype=np.float32)
pixels[:, :, :3] = colors[:, None, :]
sky = bpy.data.images.new('Garage gradient sky HDR', width, height, float_buffer=True)
sky.colorspace_settings.name = 'Non-Color'
sky.pixels.foreach_set(pixels.ravel())
sky.filepath_raw = str(args.output_dir / 'sky.hdr')
sky.file_format = 'HDR'
sky.save()
world = scene.world
world.use_nodes = True
nodes, links = world.node_tree.nodes, world.node_tree.links
nodes.clear()
output = nodes.new('ShaderNodeOutputWorld')
background = nodes.new('ShaderNodeBackground')
background.inputs['Strength'].default_value = config['sky']['intensity']
environment = nodes.new('ShaderNodeTexEnvironment')
environment.image = sky
links.new(environment.outputs['Color'], background.inputs['Color'])
links.new(background.outputs[0], output.inputs[0])
output.location = (450, 0)
background.location = (200, 0)

# glTF/Three world (x,y,z) maps back to Blender (x,-z,y).
def blender(vector):
    x, y, z = vector
    return Vector((x, -z, y))

sun = next(obj for obj in scene.objects if obj.type == 'LIGHT' and obj.data.type == 'SUN')
sun.location = blender(config['sun']['position'])
sun.rotation_euler = (-sun.location).to_track_quat('-Z', 'Y').to_euler()
sun.data.energy = config['sun']['intensity']
sun.data.color = config['sun']['linear_color']
sun.data.angle = math.radians(0.53)
scene.render.resolution_x = scene.render.resolution_y = config['probe']['face_size']
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'HDR'
scene.render.image_settings.color_mode = 'RGB'
scene.render.film_transparent = False
scene.view_settings.view_transform = 'Standard'
scene.view_settings.look = 'None'
scene.view_settings.exposure = 0
scene.view_settings.gamma = 1
preview_camera = scene.camera
probe_camera = bpy.data.objects.new('Reflection probe camera', bpy.data.cameras.new('Reflection probe'))
scene.collection.objects.link(probe_camera)
probe_camera.location = blender(config['probe']['position'])
probe_camera.data.type = 'PERSP'
probe_camera.data.lens_unit = 'FOV'
probe_camera.data.angle = math.pi / 2
probe_camera.data.clip_start = 0.01
probe_camera.data.clip_end = 200
scene.camera = probe_camera

# External Three cube maps use a left-handed X convention (PMREM flips X).
# Forward/up below are in the actual Three world, with this correction already
# applied. Positive 90-degree cameras and HDR top-to-bottom rows need no flips.
faces = [
    ('px', (-1, 0, 0), (0, 1, 0)), ('nx', (1, 0, 0), (0, 1, 0)),
    ('py', (0, 1, 0), (0, 0, -1)), ('ny', (0, -1, 0), (0, 0, 1)),
    ('pz', (0, 0, 1), (0, 1, 0)), ('nz', (0, 0, -1), (0, 1, 0)),
]
for name, forward, up in faces:
    direction, vertical = blender(forward), blender(up)
    right = direction.cross(vertical)
    probe_camera.rotation_euler = Matrix((right, vertical, -direction)).transposed().to_euler()
    scene.render.filepath = str(args.output_dir / f'hall-{name}.hdr')
    print(f'RENDER reflection face {name}', flush=True)
    bpy.ops.render.render(write_still=True)

# Restore the editing view and pack the sky alongside the existing textures.
scene.camera = preview_camera
bpy.data.objects.remove(probe_camera, do_unlink=True)
probe = bpy.data.objects.new('Reflection capture position', None)
probe.empty_display_type = 'SPHERE'
probe.empty_display_size = 0.3
probe.location = blender(config['probe']['position'])
scene.collection.objects.link(probe)
box = bpy.data.objects.new('Reflection projection volume', None)
box.empty_display_type = 'CUBE'
low, high = Vector(config['probe']['box_min']), Vector(config['probe']['box_max'])
box.location = blender((low + high) / 2)
half = (high - low) / 2
box.scale = (half.x, half.z, half.y)
scene.collection.objects.link(box)
scene['lighting'] = json.dumps(config)
sky.pack()
sky.filepath = '//sky.hdr'
scene.render.resolution_x, scene.render.resolution_y = 1440, 900
scene.render.filepath = '//preview.png'
scene.render.image_settings.file_format = 'PNG'
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(args.project), compress=True)

def info(path):
    return {'src': './models/garage/' + path.name, 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

config['sky']['texture'] = info(args.output_dir / 'sky.hdr')
config['probe']['faces'] = [dict(info(args.output_dir / f'hall-{name}.hdr'), face=name,
                                    world_forward=forward, world_up=up) for name, forward, up in faces]
config['probe']['includes_posters'] = False
config['probe']['encoding'] = 'Radiance RGBE, linear scene radiance'
config['probe']['capture_seconds'] = round(time.monotonic() - started, 2)
(args.output_dir / 'lighting.json').write_text(json.dumps(config, indent=2) + '\n')
print('ENVIRONMENT COMPLETE', config['probe']['capture_seconds'], 'seconds', flush=True)
