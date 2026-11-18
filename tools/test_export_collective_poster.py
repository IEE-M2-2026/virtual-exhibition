"""Protect the collective artwork and keep private metadata out of its public copy."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from PIL import Image, PngImagePlugin

from export_collective_poster import export


class PublicExportTests(unittest.TestCase):
    def test_public_copy_preserves_artwork_and_omits_source_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'private-student-filename.png'
            destination = root / 'site/images/affiche-collective.jpg'
            metadata = PngImagePlugin.PngInfo()
            metadata.add_text('student', 'PRIVATE STUDENT')
            with Image.new('RGB', (200, 300), 'red') as image:
                image.save(source, pnginfo=metadata)
            original = source.read_bytes()
            with redirect_stdout(io.StringIO()):
                export(source, destination)
            self.assertEqual(source.read_bytes(), original)
            self.assertNotIn(b'PRIVATE', destination.read_bytes())
            self.assertNotIn(source.name.encode(), destination.read_bytes())
            with Image.open(destination) as image:
                self.assertEqual(image.size, (200, 300))
                self.assertEqual(image.mode, 'RGB')
                self.assertGreater(image.getpixel((100, 150))[0], 240)
                self.assertFalse(image.getexif())

    def test_refresh_and_failure_preserve_other_assets_and_previous_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source.png'
            destination = root / 'public/affiche-collective.jpg'
            destination.parent.mkdir()
            sibling = destination.parent / 'keep.svg'
            sibling.write_text('keep this asset')
            with Image.new('RGB', (2800, 3000), 'blue') as image:
                image.save(source)
            with redirect_stdout(io.StringIO()):
                export(source, destination)
            with Image.open(destination) as image:
                self.assertEqual(max(image.size), 2480)
            first = destination.read_bytes()
            with Image.new('RGB', (200, 300), 'green') as image:
                image.save(source)
            with redirect_stdout(io.StringIO()):
                export(source, destination)
            current = destination.read_bytes()
            self.assertNotEqual(current, first)
            source.write_bytes(b'broken image')
            with self.assertRaises(OSError):
                export(source, destination)
            self.assertEqual(destination.read_bytes(), current)
            self.assertEqual(sibling.read_text(), 'keep this asset')
            with self.assertRaises(ValueError):
                export(source, source)


if __name__ == '__main__':
    unittest.main()
