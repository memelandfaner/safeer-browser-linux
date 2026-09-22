import os, tempfile, unittest
from pathlib import Path
from unittest import mock
from core import os_media

class MediaTest(unittest.TestCase):
    def test_catalog_is_bounded_and_classifies(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'a.mp3').write_bytes(b'x'); (p/'b.mkv').write_bytes(b'x'); (p/'x.txt').write_text('x')
            with mock.patch.object(os_media, '_roots', return_value=[p]):
                got=os_media.katalog()['vnosi']
            self.assertEqual({x['vrsta'] for x in got},{'glasba','video'})
            self.assertEqual(len(got),2)
    def test_open_rejects_non_media(self):
        with tempfile.NamedTemporaryFile(suffix='.txt') as f:
            self.assertFalse(os_media.odpri(f.name))
