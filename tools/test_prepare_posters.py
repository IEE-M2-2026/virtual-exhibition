"""Exercise the converter's public CLI with small, temporary source collections."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image, JpegImagePlugin
from prepare_posters import poster_ids

SCRIPT = Path(__file__).with_name('prepare_posters.py')


class PosterPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sources = self.root / 'originals'
        self.sources.mkdir()
        self.catalog = self.root / 'catalog.json'
        self.output = self.root / 'site'

    def write_catalog(self, entries):
        self.catalog.write_text(json.dumps(entries, ensure_ascii=False), encoding='utf-8')

    def run_converter(self, *extra):
        return subprocess.run(
            [sys.executable, str(SCRIPT), '--source-dir', str(self.sources),
             '--catalog', str(self.catalog), '--output-dir', str(self.output),
             '--encoder', 'pillow', '--thumbnail-size', '32', '--texture-size', '128',
             '--detail-size', '256', *extra],
            cwd=self.root, capture_output=True, text=True)

    def output_snapshot(self):
        return {p.relative_to(self.output): p.read_bytes()
                for p in self.output.rglob('*') if p.is_file()}

    def test_unicode_transparency_no_upscale_and_missing_metadata(self):
        name = 'Affiche e\u0301tudiante [essai].png'
        with Image.new('RGBA', (80, 120), (0, 0, 0, 0)) as image:
            image.paste((255, 0, 0, 255), (20, 20, 60, 100))
            image.save(self.sources / name)
        (self.sources / '.DS_Store').write_bytes(b'ignored')
        entries = [{'filename': name, 'title': 'Unconfirmed author', 'private_note': 'Private student name'}]
        self.write_catalog(entries)
        result = self.run_converter()
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((self.output / 'data/posters.json').read_text())
        poster = manifest['posters'][0]
        self.assertEqual(poster['metadata'], {'title': 'Unconfirmed author'})
        public_json = json.dumps(manifest, ensure_ascii=False)
        self.assertNotIn(name, public_json)
        self.assertNotIn('Private student name', public_json)
        self.assertNotIn('filename', public_json)
        digest = hashlib.sha256((self.sources / name).read_bytes()).hexdigest()
        self.assertEqual(poster['id'], f'unconfirmed-author-{digest[:6]}')
        self.assertTrue(poster['id'].isascii())
        self.assertEqual(poster['images']['detail']['width'], 80)
        self.assertEqual(poster['images']['detail']['height'], 120)
        for variant, edge in [('thumbnail', 32), ('texture', 128), ('detail', 256)]:
            info = poster['images'][variant]
            path = self.output / info['src']
            data = path.read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), info['sha256'])
            self.assertEqual(len(data), info['bytes'])
            with Image.open(path) as image:
                self.assertEqual(image.size, (info['width'], info['height']))
                self.assertLessEqual(max(image.size), edge)
                self.assertTrue(image.info.get('progressive'))
                self.assertEqual(JpegImagePlugin.get_sampling(image), 0)
                # Allow JPEG ringing around the red block at thumbnail scale.
                self.assertTrue(all(channel >= 240 for channel in image.getpixel((0, 0))))
        snapshot = self.output_snapshot()
        self.assertEqual(self.run_converter().returncode, 0)
        self.assertEqual(self.output_snapshot(), snapshot)

    def test_rebuild_cleans_old_iteration_and_preserves_other_site_files(self):
        for name, color in [('student-one.png', 'blue'), ('student-two.png', 'red')]:
            with Image.new('RGB', (80, 120), color) as image:
                image.save(self.sources / name)
        entries = [{'filename': name, 'title': 'Une pièce', 'author': 'Une Autrice'}
                   for name in ('student-one.png', 'student-two.png')]
        self.write_catalog(entries)
        self.assertEqual(self.run_converter().returncode, 0)
        previous = set((self.output / 'posters').rglob('*.jpg'))
        (self.output / 'posters/student-private-name.jpg').write_bytes(b'legacy output')
        (self.output / 'index.html').write_text('Keep site')
        (self.output / 'data/other.json').write_text('{}')
        (self.sources / 'student-two.png').unlink()
        with Image.new('RGB', (80, 120), 'green') as image:
            image.save(self.sources / 'student-one.png')
        self.write_catalog(entries[:1])
        result = self.run_converter()
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((self.output / 'data/posters.json').read_text())
        poster = manifest['posters'][0]
        expected = {self.output / info['src'] for info in poster['images'].values()}
        actual = {p for p in (self.output / 'posters').rglob('*') if p.is_file()}
        self.assertEqual(actual, expected)
        self.assertFalse(actual & previous)
        self.assertEqual((self.output / 'index.html').read_text(), 'Keep site')
        self.assertEqual((self.output / 'data/other.json').read_text(), '{}')
        self.assertTrue(poster['id'].startswith('une-piece-une-autrice-'))
        # Renaming a source must not expose its name or change the public ID.
        (self.sources / 'student-one.png').rename(self.sources / 'private-new-name.png')
        entries[0]['filename'] = 'private-new-name.png'
        self.write_catalog(entries[:1])
        self.assertEqual(self.run_converter().returncode, 0)
        renamed = json.loads((self.output / 'data/posters.json').read_text())
        self.assertEqual(renamed, manifest)

    def test_short_checksum_collision_extends_only_as_needed(self):
        entries = [{'title': 'A', 'author': 'B'}] * 2
        digests = ['abcdef1' + '0' * 57, 'abcdef2' + '0' * 57]
        self.assertEqual(poster_ids(entries, digests), ['a-b-abcdef1', 'a-b-abcdef2'])
        with self.assertRaisesRegex(ValueError, 'Identical originals'):
            poster_ids(entries, [digests[0]] * 2)

    def test_cleanup_rejects_output_symlink(self):
        with Image.new('RGB', (8, 8), 'white') as image:
            image.save(self.sources / 'one.png')
        self.write_catalog([{'filename': 'one.png'}])
        self.output.mkdir()
        (self.output / 'posters').symlink_to(self.sources, target_is_directory=True)
        result = self.run_converter()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not a file or symlink', result.stderr)
        self.assertTrue((self.sources / 'one.png').is_file())

    def test_exif_orientation(self):
        with Image.new('RGB', (120, 80), 'green') as image:
            exif = image.getexif()
            exif[274] = 6
            image.save(self.sources / 'rotated.jpg', exif=exif)
        self.write_catalog([{'filename': 'rotated.jpg'}])
        result = self.run_converter()
        self.assertEqual(result.returncode, 0, result.stderr)
        poster = json.loads((self.output / 'data/posters.json').read_text())['posters'][0]
        self.assertEqual((poster['images']['detail']['width'], poster['images']['detail']['height']), (80, 120))

    def test_later_conversion_failure_keeps_previous_output(self):
        with Image.new('RGB', (80, 120), 'blue') as image:
            image.save(self.sources / 'first.png')
        self.write_catalog([{'filename': 'first.png'}])
        self.assertEqual(self.run_converter().returncode, 0)
        snapshot = self.output_snapshot()
        with Image.new('RGB', (80, 120), 'red') as image:
            image.save(self.sources / 'first.png')
        (self.sources / 'broken.png').write_bytes(b'not an image')
        self.write_catalog([{'filename': 'first.png'}, {'filename': 'broken.png'}])
        result = self.run_converter()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output_snapshot(), snapshot)

    def test_multipage_pdf_is_not_silently_truncated(self):
        with Image.new('RGB', (60, 90), 'white') as first, Image.new('RGB', (60, 90), 'black') as second:
            first.save(self.sources / 'two.pdf', save_all=True, append_images=[second])
        self.write_catalog([{'filename': 'two.pdf'}])
        result = self.run_converter()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('2 PDF pages', result.stderr)
        self.assertFalse((self.output / 'data/posters.json').exists())

    def test_single_page_pdf_renders_to_requested_dimensions(self):
        with Image.new('RGB', (60, 90), 'blue') as image:
            image.save(self.sources / 'one.pdf')
        self.write_catalog([{'filename': 'one.pdf'}])
        result = self.run_converter()
        self.assertEqual(result.returncode, 0, result.stderr)
        poster = json.loads((self.output / 'data/posters.json').read_text())['posters'][0]
        info = poster['images']['detail']
        self.assertEqual(info['height'], 256)
        self.assertLessEqual(abs(info['width'] / info['height'] - 2 / 3), 1 / 256)
        with Image.open(self.output / info['src']) as image:
            self.assertGreater(image.getpixel((50, 50))[2], 240)

    def test_catalog_rejects_missing_unlisted_and_duplicate_files(self):
        self.write_catalog([{'filename': 'missing.png'}])
        self.assertIn('Missing or unsupported', self.run_converter().stderr)
        with Image.new('RGB', (8, 8), 'white') as image:
            image.save(self.sources / 'one.png')
            image.save(self.sources / 'two.png')
        self.write_catalog([{'filename': 'one.png'}])
        self.assertIn('Add these files to the catalogue', self.run_converter().stderr)
        self.write_catalog([{'filename': 'one.png'}, {'filename': 'one.png'}])
        self.assertIn('Duplicate catalogue filename', self.run_converter().stderr)


if __name__ == '__main__':
    unittest.main()
