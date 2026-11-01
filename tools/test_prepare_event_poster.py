"""Check coverage, no cropping, repeatability and failure preservation."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

import prepare_event_poster as poster


class GridTests(unittest.TestCase):
    def test_changing_counts_and_formats(self):
        for count in list(range(1, 101)) + [127, 200, 257, 500]:
            for aspect in (.5, 2 ** -.5, 1, 1.5):
                with self.subTest(count=count, aspect=aspect):
                    columns, rows = poster.choose_grid(count, aspect, 3508, 4961, 19, 7)
                    self.assertGreaterEqual(columns * rows, count + 1)
                    boxes = list(poster.cell_boxes(columns, rows, 3508, 4961, 19, 7))
                    self.assertEqual(boxes[0][:2], (19, 19))
                    self.assertEqual(boxes[-1][2:], (3508 - 19, 4961 - 19))
                    widths, heights = set(), set()
                    for i, (x0, y0, x1, y1) in enumerate(boxes):
                        widths.add(x1 - x0)
                        heights.add(y1 - y0)
                        self.assertGreaterEqual(min(x1 - x0, y1 - y0), 64)
                        if i % columns:
                            self.assertEqual(x0 - boxes[i - 1][2], 7)
                        if i >= columns:
                            self.assertEqual(y0 - boxes[i - columns][3], 7)
                    self.assertLessEqual(max(widths) - min(widths), 1)
                    self.assertLessEqual(max(heights) - min(heights), 1)

    def test_impossible_geometry(self):
        for options in ({'margin': 500}, {'gutter': 400}, {'min_fillers': 100}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                poster.choose_grid(11, .707, 400, 600, **options)


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sources = self.root / 'originals'
        self.sources.mkdir()
        entries = []
        # Three ratios with a thick red border: a crop would lose an edge.
        for i, size in enumerate(((100, 200), (220, 100), (150, 150))):
            name = f'private-student-{i}.png'
            with Image.new('RGB', size, 'blue') as image:
                ImageDraw.Draw(image).rectangle((0, 0, size[0] - 1, size[1] - 1),
                                                outline='red', width=12)
                image.save(self.sources / name)
            entries.append({'filename': name, 'title': f'Play {i}', 'student': 'PRIVATE'})
        self.catalog = self.root / 'catalog.json'
        self.catalog.write_text(json.dumps(entries))
        self.args = poster.arguments([
            '--source-dir', str(self.sources), '--catalog', str(self.catalog),
            '--output-dir', str(self.root / 'output'), '--width', '800', '--height', '1000',
            '--margin', '13', '--gutter', '7',
        ])

    def render(self):
        with redirect_stdout(io.StringIO()):
            return poster.prepare(self.args)

    def test_every_original_once_complete_and_private_fields_omitted(self):
        layout = self.render()
        cells = [cell for cell in layout['cells'] if cell['kind'] == 'poster']
        self.assertEqual(len(cells), 3)
        self.assertEqual(len({cell['id'] for cell in cells}), 3)
        self.assertNotIn('private-student', json.dumps(layout))
        self.assertNotIn('PRIVATE', json.dumps(layout))
        self.assertIn('both', [cell.get('text_mode') for cell in layout['cells']])
        with Image.open(self.args.output_dir / 'event-poster.png') as image:
            self.assertEqual(image.size, (800, 1000))
            self.assertEqual(image.mode, 'RGB')
            self.assertAlmostEqual(image.info['dpi'][0], 300, places=1)
            self.assertIn('icc_profile', image.info)
            for cell in cells:
                x0, y0, x1, y1 = cell['image_box']
                left, top, right, bottom = cell['box']
                self.assertTrue(left <= x0 < x1 <= right and top <= y0 < y1 <= bottom)
                for point in ((x0, (y0 + y1) // 2), (x1 - 1, (y0 + y1) // 2),
                              ((x0 + x1) // 2, y0), ((x0 + x1) // 2, y1 - 1)):
                    r, g, b = image.getpixel(point)
                    self.assertGreater(r, 240)
                    self.assertLess(max(g, b), 15)

    def test_seed_and_failure_preserve_previous_output(self):
        first = self.render()
        image_path = self.args.output_dir / 'event-poster.png'
        with Image.open(image_path) as image:
            pixels = image.tobytes()
        sentinel = self.args.output_dir / 'keep.txt'
        sentinel.write_text('unrelated asset')
        self.assertEqual(self.render(), first)
        with Image.open(image_path) as image:
            self.assertEqual(image.tobytes(), pixels)
        self.args.seed = 17
        self.assertNotEqual(self.render()['cells'], first['cells'])
        before = {p.name: p.read_bytes() for p in self.args.output_dir.iterdir()}
        (self.sources / 'private-student-1.png').write_bytes(b'broken image')
        with self.assertRaises(OSError):
            self.render()
        after = {p.name: p.read_bytes() for p in self.args.output_dir.iterdir()}
        self.assertEqual(before, after)
        self.assertEqual(sentinel.read_text(), 'unrelated asset')

    def test_single_poster_has_event_tile(self):
        entries = json.loads(self.catalog.read_text())[:1]
        for path in self.sources.iterdir():
            if path.name != entries[0]['filename']:
                path.unlink()
        self.catalog.write_text(json.dumps(entries))
        self.args.hashtag = ''
        layout = self.render()
        self.assertEqual(layout['poster_count'], 1)
        self.assertGreaterEqual(layout['filler_count'], 1)
        self.assertTrue(all(cell['text_mode'] == 'title' for cell in layout['cells']
                            if cell['kind'] == 'event'))


if __name__ == '__main__':
    unittest.main()
