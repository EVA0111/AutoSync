"""Main-episode trims sit on the target frame grid; partial exports survive brief Windows locks.

Measured on case 3 (23.976 fps, trim start 93.52 s): the trimmed picture began
at the next whole frame (93.552 s) while the audio began at 93.52 s, so the
whole main episode played 31 ms late. Case 3 Remove-unmatched failed with
WinError 32 on its just-written partial file.
"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import main_episode as me
import visual_core as vc

FPS = 24000 / 1001


class FrameSnap(unittest.TestCase):
    def test_start_moves_to_the_first_whole_frame(self):
        t = me.snap_to_frames(dict(target_start=93.52, target_end=1330.8, duration=1237.28), FPS)
        self.assertAlmostEqual(t['target_start'], 2243 / FPS, places=9)
        self.assertGreaterEqual(t['target_start'], 93.52)
        self.assertLess(t['target_start'] - 93.52, 1 / FPS)
        self.assertAlmostEqual(t['target_end'], 31907 / FPS, places=9)
        self.assertAlmostEqual(t['duration'], t['target_end'] - t['target_start'], places=9)

    def test_boundary_already_on_a_frame_is_kept(self):
        t = me.snap_to_frames(dict(target_start=2243 / FPS + 1e-7, target_end=3000 / FPS, duration=0), FPS)
        self.assertAlmostEqual(t['target_start'], 2243 / FPS, places=9)

    def test_unknown_rate_leaves_the_trim_alone(self):
        trim = dict(target_start=93.52, target_end=1330.8, duration=1237.28)
        self.assertEqual(me.snap_to_frames(trim, None), trim)


class PartialExport(unittest.TestCase):
    def test_rename_retries_while_the_file_is_locked(self):
        with tempfile.TemporaryDirectory() as d:
            tmp, dest = Path(d) / 'a.partial.mkv', Path(d) / 'a.mkv'
            tmp.write_bytes(b'x')
            real = Path.replace
            calls = []

            def flaky(self, target):
                calls.append(1)
                if len(calls) < 3:
                    raise PermissionError(32, 'in use')
                return real(self, target)
            with mock.patch.object(Path, 'replace', flaky):
                vc.finish_partial(tmp, dest, sleep=lambda s: None)
            self.assertTrue(dest.exists()); self.assertEqual(len(calls), 3)

    def test_long_lock_falls_back_to_copying(self):
        # Zorro remove-unmatched: the rename was refused for more than 5 s.
        with tempfile.TemporaryDirectory() as d:
            tmp, dest = Path(d) / 'a.partial.mkv', Path(d) / 'a.mkv'
            tmp.write_bytes(b'video')
            def locked(self, target):
                raise PermissionError(32, 'in use')
            with mock.patch.object(Path, 'replace', locked):
                vc.finish_partial(tmp, dest, sleep=lambda s: None)
            self.assertEqual(dest.read_bytes(), b'video')

    def test_cleanup_never_masks_the_original_error(self):
        with mock.patch.object(Path, 'unlink', side_effect=PermissionError(32, 'in use')):
            vc.discard_partial(Path('missing.partial.mkv'))


if __name__ == '__main__':
    unittest.main()
