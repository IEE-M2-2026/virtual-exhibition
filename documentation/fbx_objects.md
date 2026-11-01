# Individual objects from SM_set_a

`res/3d/garage/fbx/SM_set_a_objects/` contains nine FBX files exported from `res/3d/garage/fbx/SM_set_a.fbx`:

- `SM_set_a.fbx`: the complete existing visible mesh, without the collision objects.
- `UCX_SM_set_a_1.fbx` through `UCX_SM_set_a_8.fbx`: one existing collision object per file.

This export separates existing objects only. It does not split the seven disconnected components inside the main mesh. The original file remains unchanged. The output manifest records object names, geometry counts, UV layers, material names, world bounds and checksums.

Each FBX was reimported into Blender 4.0.2 and checked for exactly one mesh object, unchanged geometry counts, world-space corner positions, UVs and material assignments. Existing placement is retained so the files can be reassembled at their exported transforms.

To repeat the export into a new destination, from the repository root:

```sh
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python-exit-code 1 --python tools/split_fbx_objects.py -- \
  res/3d/garage/fbx/SM_set_a.fbx \
  --output-dir res/3d/garage/fbx/SM_set_a_objects_new
```

The script refuses to overwrite an existing destination. Files are staged and reimported for verification before the output directory is created. It exports the source's material assignments without embedding image textures. These working assets stay outside the published `docs/` directory.
