import unittest

import numpy as np
from main_episode import opening_audio_correspondence


class SharedOpeningAudioTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(20261030)
        # Audio feature STFT extracts 50 windows per second, not video fps.
        self.source = rng.standard_normal((24, 1200)).astype(np.float32)
        self.target = rng.standard_normal((24, 650)).astype(np.float32)
        self.target[:, :320] = self.source[:, 150:470] + .025 * rng.standard_normal((24, 320))

    def test_shared_music_vetoes_picture_trim(self):
        result = opening_audio_correspondence(self.source, self.target, 5.8, 1.0)
        self.assertTrue(result["matched"], result)
        self.assertFalse(result["different"], result)
        self.assertAlmostEqual(result["offset"], 3.0, delta=.08)

    def test_shared_music_with_speed_change(self):
        # The actual feature grid is compressed to source/target speed.
        from scipy import ndimage
        speed = 25/24
        source = ndimage.zoom(self.source, (1, speed), order=1)
        target = self.target.copy()
        target[:, :320] = ndimage.zoom(source, (1, 1/speed), order=1)[:, 150:470]
        result = opening_audio_correspondence(source, target, 5.8, speed)
        self.assertTrue(result["matched"], result)
        self.assertFalse(result["different"], result)

    def test_unrelated_music_can_be_different(self):
        rng = np.random.default_rng(128)
        independent = rng.standard_normal(self.target.shape).astype(np.float32)
        result = opening_audio_correspondence(self.source, independent, 5.8, 1.0)
        self.assertFalse(result["matched"], result)
        self.assertTrue(result["different"], result)

    def test_short_opening_cannot_be_safely_discarded(self):
        self.assertIsNone(opening_audio_correspondence(self.source, self.target, 1.1, 1.0))

    def test_silent_audio_is_inconclusive(self):
        target = np.zeros_like(self.target)
        result = opening_audio_correspondence(self.source, target, 5.8, 1.0)
        self.assertFalse(result["different"], result)


if __name__ == "__main__":
    unittest.main()
