"""Audio with a hole in its packet timestamps (DVD/TV rips) must stay on its timeline."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

from pcm_audio import PCMCache


def gapped_file(path):
    """6 s of 1 kHz tone, with the packets for 2-4 s missing (timestamps jump)."""
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=1000:sample_rate=48000:duration=6',
                    '-af', "aselect='not(between(t,2,4))'", '-c:a', 'flac', str(path)], check=True)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg unavailable')
class AudioGapTests(unittest.TestCase):
    def test_gap_decodes_as_silence_in_place(self):
        with tempfile.TemporaryDirectory() as td:
            media = Path(td) / 'gap.mka'
            gapped_file(media)
            cache = PCMCache(td, 1)
            self.assertAlmostEqual(cache.length(media, 0), 6., delta=.05)
            out = Path(td) / 'cut.f32'
            cache.cut(media, 0, 2.2, 1.6, out)  # inside the hole: silence
            self.assertLess(np.abs(np.fromfile(out, np.float32)).max(), 1e-3)
            cache.cut(media, 0, 4.2, 1., out)  # after the hole: the tone, not 2 s early
            self.assertGreater(np.abs(np.fromfile(out, np.float32)).max(), .1)

    def test_evaluator_features_keep_the_timeline(self):
        import sync_accuracy
        with tempfile.TemporaryDirectory() as td:
            media = Path(td) / 'gap.mka'
            gapped_file(media)
            frames = sync_accuracy.decode_audio_features(media, 0, None).shape[1]
            seconds = frames * sync_accuracy.HOP / sync_accuracy.AR
            self.assertAlmostEqual(seconds, 6., delta=.1)


if __name__ == '__main__':
    unittest.main()


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg unavailable')
class LateTargetAudio(unittest.TestCase):
    def test_target_audio_starting_after_its_picture_is_silent_there(self):
        from autosync import render
        with tempfile.TemporaryDirectory() as td:
            td = Path(td); target = td / 'target.mkv'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=s=64x48:r=25:d=3', '-itsoffset', '0.3',
                            '-f', 'lavfi', '-i', 'sine=frequency=1000:sample_rate=48000:duration=2.7', '-c:v', 'libx264',
                            '-c:a', 'flac', str(target)], check=True)
            plan = dict(audio=str(target), audio_stream=0, reference=str(target), reference_stream=0, reference_shift=.3,
                        duration=2., review=[], segments=[dict(kind='reference', target_start=0, target_end=2.,
                                                               verified_insert=True)])
            out = render(plan, td, True)
            x = np.frombuffer(subprocess.run(['ffmpeg', '-v', 'error', '-i', str(out), '-ac', '1', '-f', 'f32le', '-'],
                                             stdout=subprocess.PIPE).stdout, np.float32)
            self.assertEqual(len(x), 96000)
            self.assertLess(np.abs(x[:int(.28 * 48000)]).max(), 1e-3)   # before the target's audio: silence
            self.assertGreater(np.abs(x[int(.35 * 48000):]).max(), .1)    # then the target's own audio

    def test_source_audio_is_never_padded(self):
        from autosync import render
        with tempfile.TemporaryDirectory() as td:
            td = Path(td); src = td / 's.flac'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=duration=2', str(src)], check=True)
            plan = dict(audio=str(src), audio_stream=0, duration=2., review=[],
                        segments=[dict(kind='audio', target_start=0, target_end=2., source_start=.5, speed=1.)])
            with self.assertRaisesRegex(RuntimeError, 'too short|ends too early'):
                render(plan, td, False)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg unavailable')
class EarlyEndingTargetAudio(unittest.TestCase):
    def test_target_audio_ending_before_its_picture_is_silent_there(self):
        from autosync import render
        with tempfile.TemporaryDirectory() as td:
            td = Path(td); target = td / 'target.mkv'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=s=64x48:r=25:d=4', '-f', 'lavfi', '-i',
                            'sine=frequency=1000:sample_rate=48000:duration=2.5', '-c:v', 'libx264', '-c:a', 'flac',
                            str(target)], check=True)
            plan = dict(audio=str(target), audio_stream=0, reference=str(target), reference_stream=0, duration=4.,
                        review=[], segments=[dict(kind='reference', target_start=0, target_end=4., verified_insert=True)])
            x = np.frombuffer(subprocess.run(['ffmpeg', '-v', 'error', '-i', str(render(plan, td, True)), '-ac', '1',
                                              '-f', 'f32le', '-'], stdout=subprocess.PIPE).stdout, np.float32)
            self.assertEqual(len(x), 4 * 48000)
            self.assertGreater(np.abs(x[:2 * 48000]).max(), .1)
            self.assertLess(np.abs(x[int(2.6 * 48000):]).max(), 1e-3)
