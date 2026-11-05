"""Audio placement of target-only footage the pictures cannot place (a held shot shown longer)."""
import unittest
import numpy as np
from cut_detection import place_insert

R = 50


def audio(n, seed):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(16, n + 4))
    return sum(x[:, k:k + n] for k in range(4))     # 50 Hz features, a little smooth


class PlaceInsert(unittest.TestCase):
    """Source (dub) audio: 40 s. Target: source 0-20 s, 3 s of its own audio, source 20-40 s."""
    def setUp(self):
        self.src = audio(40 * R, 1)
        self.extra = audio(3 * R, 2)
        self.ref = np.hstack([self.src[:, :20 * R], self.extra, self.src[:, 20 * R:]])
        self.left = dict(speed=1., offset=0.)
        self.right = dict(speed=1., offset=-3.)
        self.starts = np.arange(17., 21.01, .04)        # every start the pictures allow

    def test_audio_singles_out_the_start(self):
        k = place_insert(self.left, self.right, self.starts, 3., self.ref, None, self.src)
        self.assertAlmostEqual(self.starts[k], 20., delta=.05)

    def test_unrelated_audio_decides_nothing(self):
        other = audio(43 * R, 3)                         # a dub in another language: nothing matches
        self.assertIsNone(place_insert(self.left, self.right, self.starts, 3., other, None, self.src))

    def test_a_single_start_is_no_choice(self):
        self.assertIsNone(place_insert(self.left, self.right, self.starts[:1], 3., self.ref, None, self.src))


if __name__ == '__main__':
    unittest.main()
