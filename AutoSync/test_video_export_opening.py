"""Synthetic-media check: FFmpeg must retain the opening frames after the audio guard."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

import visual_core as vc
from video_edits import export_video, protect_opening, remove_missing


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg/FFprobe needed")
class PreserveOpeningVideoExport(unittest.TestCase):
    def test_shared_music_opening_frames_reach_edited_mkv(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "target.mkv"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=64x48:rate=10:duration=12",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=12",
                "-c:v", "mpeg4", "-q:v", "6", "-c:a", "flac", str(target)
            ], check=True, timeout=60)

            rng = np.random.default_rng(1224)
            source_features = rng.standard_normal((24, 1100)).astype(np.float32)
            target_features = rng.standard_normal((24, 650)).astype(np.float32)
            target_features[:, :320] = source_features[:, 150:470]
            plan = dict(
                duration=12., audio=str(target), reference=str(target),
                target_video=str(target), source_video=str(target),
                models=[dict(speed=1.)], review=[], warnings=[],
                reference_shift=0., reference_stream=0,
                segments=[
                    dict(kind="reference", target_start=0., target_end=5.8),
                    dict(kind="audio", target_start=5.8, target_end=12.,
                         source_start=8.8, speed=1.),
                ],
            )
            preserved = protect_opening(plan, source_features, target_features, 22.)
            self.assertEqual(preserved["segments"][0]["kind"], "audio")
            edited_plan = remove_missing(preserved)
            self.assertAlmostEqual(edited_plan["duration"], 12.)
            self.assertFalse(edited_plan["video_edits"]["removed"])
            output = export_video(edited_plan, target, root)
            self.assertTrue(output.is_file())
            self.assertAlmostEqual(vc.video_duration(output), 12., delta=.15)


if __name__ == "__main__":
    unittest.main()
