"""Joins in the exported audio are timed crossfades, never a dip to silence."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import wavfile

SR = 48000


def seg(a, b, src, speed=1.):
    return dict(kind='audio', target_start=float(a), target_end=float(b), source_start=float(src), speed=speed)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'needs ffmpeg')
class JoinCrossfade(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import autosync
        cls.dir = Path(tempfile.mkdtemp())
        rng = np.random.default_rng(3)
        # 60 s of band-limited noise: every join point has full, uncorrelated sound.
        noise = rng.standard_normal(60 * SR)
        k = np.hanning(9); k /= k.sum()
        cls.src = (np.convolve(noise, k, mode='same') * .2).astype(np.float32)
        wav = cls.dir / 'source.wav'
        wavfile.write(wav, SR, cls.src)
        cls.segments = [seg(0, 5, 0.), seg(5, 10, 5.),            # zero jump: the audio is continuous
                        seg(10, 15, 10.012),                      # 12 ms forward step (a micro cut)
                        seg(15, 20, 40.),                         # an ordinary cut
                        seg(20, 25, 50., 1.04)]                   # a speed-changed clip
        # Every join located by picture evidence, as the engine reports it.
        review = [dict(start=t - 1, end=t + 1, splice=t, confidence='supported', reason='picture-located join')
                  for t in (5., 10., 15., 20.)]
        plan = dict(duration=25., audio=str(wav), audio_stream=0, segments=cls.segments, review=review)
        out = cls.dir / 'out'; out.mkdir()
        flac = autosync.render(plan, out, False)
        cls.out = np.frombuffer(subprocess.run(['ffmpeg', '-v', 'error', '-i', str(flac), '-f', 'f32le', '-ac', '1', '-'],
                                               stdout=subprocess.PIPE, check=True).stdout, np.float32)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def expected(self, a, b):
        """Source samples for output [a, b) s, for unstretched segments."""
        s = next(x for x in self.segments if x['target_start'] <= a < x['target_end'])
        i = round((s['source_start'] + a - s['target_start']) * SR)
        return self.src[i:i + round((b - a) * SR)]

    def test_exact_length(self):
        self.assertEqual(len(self.out), 25 * SR)

    def test_timing_is_unchanged_away_from_joins(self):
        for a in (1., 6., 12., 16.):
            got, want = self.out[round(a * SR):round((a + 1) * SR)], self.expected(a, a + 1)
            self.assertLess(np.max(np.abs(got - want)), 1e-4, a)

    def test_zero_jump_join_is_seamless(self):
        got, want = self.out[round(4.9 * SR):round(5.1 * SR)], self.src[round(4.9 * SR):round(5.1 * SR)]
        self.assertLess(np.max(np.abs(got - want)), 1e-4)

    def test_no_dip_at_any_join(self):
        rms = lambda a, b: float(np.sqrt(np.mean(self.out[round(a * SR):round(b * SR)] ** 2)))
        for t in (5., 10., 15., 20.):
            around = rms(t - .5, t - .1)
            self.assertGreater(rms(t - .005, t + .005), .75 * around, t)   # a fade to silence gave ~.45


if __name__ == '__main__':
    unittest.main()
