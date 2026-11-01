"""Validate the actual generated garage, including its shared-texture contract."""

import hashlib
import json
from pathlib import Path
import struct
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


class GarageAssetTests(unittest.TestCase):
    def setUp(self):
        self.directory = ROOT / 'docs/models/garage'
        self.manifest = json.loads((self.directory / 'manifest.json').read_text())

    def test_all_geometry_is_external_texture_free_and_has_uvs(self):
        self.assertEqual({part['id'] for part in self.manifest['parts']}, set('abcde'))
        total_triangles = 0
        for part in self.manifest['parts']:
            data = (ROOT / 'docs' / part['src']).read_bytes()
            self.assertEqual(data[:4], b'glTF')
            self.assertEqual(struct.unpack_from('<I', data, 4)[0], 2)
            length = struct.unpack_from('<I', data, 12)[0]
            gltf = json.loads(data[20:20 + length])
            self.assertFalse(gltf.get('images'))
            self.assertFalse(gltf.get('textures'))
            self.assertFalse(gltf.get('materials'))
            self.assertFalse(any(node.get('name', '').startswith('UCX_') for node in gltf['nodes']))
            for mesh in gltf['meshes']:
                for primitive in mesh['primitives']:
                    self.assertIn('TEXCOORD_0', primitive['attributes'])
                    self.assertIn('NORMAL', primitive['attributes'])
                    total_triangles += gltf['accessors'][primitive['indices']]['count'] // 3
        self.assertEqual(total_triangles, sum(part['triangles'] for part in self.manifest['parts']))
        roof = next(part for part in self.manifest['parts'] if part['id'] == 'c')
        self.assertGreater(roof['bounds'][0][1], 7, 'Roof must be assembled above the floor')
        self.assertLess(roof['bounds'][1][1], 12)

    def test_manifest_checksums_and_generated_inventory(self):
        assets = self.manifest['parts'] + list(self.manifest['textures'].values())
        expected = {self.directory / 'manifest.json'}
        for asset in assets:
            path = ROOT / 'docs' / asset['src']
            expected.add(path)
            data = path.read_bytes()
            self.assertEqual(len(data), asset['bytes'])
            self.assertEqual(hashlib.sha256(data).hexdigest(), asset['sha256'])
        self.assertEqual(expected, {p for p in self.directory.rglob('*') if p.is_file()})

    def test_one_shared_surface_map_has_expected_channels_and_sizes(self):
        self.assertEqual(set(self.manifest['textures']), {'albedo', 'normal', 'surface'})
        for name, asset in self.manifest['textures'].items():
            with Image.open(ROOT / 'docs' / asset['src']) as image:
                size = self.manifest['texture_size'] if name == 'albedo' else self.manifest['detail_texture_size']
                self.assertEqual(image.size, (size, size))
                if name == 'surface':
                    self.assertEqual(image.getchannel('R').getextrema(), (255, 255))
                    self.assertNotEqual(image.getchannel('G').getextrema()[0], image.getchannel('G').getextrema()[1])
                    self.assertNotEqual(image.getchannel('B').getextrema()[0], image.getchannel('B').getextrema()[1])


if __name__ == '__main__':
    unittest.main()
