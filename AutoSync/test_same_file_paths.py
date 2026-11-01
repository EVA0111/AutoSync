"""Reference and target given with different path spellings are one file.

Measured on case 2 (Remove unmatched video): the engine resolves the reference
path but keeps the target spelling (other slash style); the string comparison in
protect_opening concluded the target audio 'differs or is missing' and
refused. Temporary files only.
"""
import os, tempfile, unittest
from pathlib import Path
from video_edits import same_file


class SameFile(unittest.TestCase):
    def test_spellings_of_one_file(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'target.mp4'; f.write_bytes(b'x')
            self.assertTrue(same_file(str(f.resolve()), str(f).replace(os.sep, '/')))
            self.assertTrue(same_file(str(f), str(Path(d) / 'sub' / '..' / 'target.mp4')))
            self.assertFalse(same_file(str(f), str(Path(d) / 'other.mp4')))
            self.assertFalse(same_file('', str(f)))


if __name__ == '__main__':
    unittest.main()
