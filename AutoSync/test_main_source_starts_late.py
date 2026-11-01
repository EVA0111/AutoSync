"""Main-episode start when the target begins before the source has pictures.

Measured on regression case 2: the target opens with 22.4 s that map before
source time 0. detect_main refused ('Source pictures unavailable at target
start') in Main episode and Keep OP/ED modes, although frames with no source
counterpart are differing outer footage by definition. Synthetic frames only.
"""
import unittest
import numpy as np
from main_episode import unmatched_prefix, boundary_from_scores, edge_matches
from visual_cuts import RATE


def frames(n, seed):
    x = np.random.default_rng(seed).normal(size=(n, 504)).astype(np.float32)
    return x / np.linalg.norm(x, axis=1, keepdims=True)


class SourceStartsLate(unittest.TestCase):
    def test_boundary_found_where_source_pictures_begin(self):
        missing, length = 22.4, 60.
        main = frames(int((length - missing) * RATE), 1)
        q = np.vstack([frames(int(missing * RATE), 2), main])
        scores = unmatched_prefix(q, main, missing)
        self.assertEqual(len(scores), len(q))
        self.assertTrue(np.all(scores[:int(missing * RATE)] == 0))
        result = boundary_from_scores(scores, np.zeros(len(q), bool), 0., 'start')
        self.assertEqual(result['status'], 'supported')
        self.assertAlmostEqual(result['time'], missing, delta=1 / RATE + 1e-9)

    def test_no_missing_prefix_is_plain_comparison(self):
        q = frames(100, 3)
        self.assertTrue(np.allclose(unmatched_prefix(q, q, 0.), unmatched_prefix(q, q, .001)))


class EdgeMatches(unittest.TestCase):
    def test_recap_at_start_is_not_the_edge(self):
        # Case 2: a title shot at 37-42 s maps 16 s away from the main timing.
        title = np.c_[np.arange(37, 42, .5), np.arange(37, 42, .5) - 5.96, np.ones(10)]
        main = np.c_[np.arange(50, 400, 4.), np.arange(50, 400, 4.) - 22.15, np.ones(88)]
        visual = np.vstack([title, main])
        model = dict(speed=1., offset=-22.42)
        edge = edge_matches(visual, model, 'start')
        self.assertTrue(np.all(np.abs(edge[:, 1] - edge[:, 0] + 22.15) < .01))
        self.assertEqual(edge[0, 0], 50.)

    def test_falls_back_when_model_has_too_few_pictures(self):
        visual = np.c_[np.arange(0, 60, 4.), np.arange(0, 60, 4.) + 3, np.ones(15)]
        edge = edge_matches(visual, dict(speed=1., offset=0.), 'end')
        self.assertEqual(len(edge), 15)


if __name__ == '__main__':
    unittest.main()
