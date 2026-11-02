"""A shared opening with a short differing title card is not an outer sequence.

Measured on Zorro (and case 6): target and source share the opening pictures
except a ~5 s German title card; Main episode / Keep OP/ED stopped with 'start
boundary is ambiguous'. Long differing runs (cold open + new OP) must still
require a manual boundary. Synthetic score profiles only.
"""
import unittest
import numpy as np
from main_episode import boundary_from_scores
from visual_cuts import RATE


def profile(spec):
    return np.concatenate([np.full(int(sec * RATE), v) for sec, v in spec])


class SharedEdge(unittest.TestCase):
    def test_title_card_inside_shared_opening_is_kept(self):
        s = profile([(1, .45), (19, .88), (5, .41), (12, .8)])
        r = boundary_from_scores(s, np.zeros(len(s), bool), 0., 'start')
        self.assertEqual(r['status'], 'kept'); self.assertEqual(r['time'], 0.)

    def test_cold_open_then_new_opening_still_needs_manual(self):
        s = profile([(3, .9), (40, .2), (20, .9)])
        with self.assertRaises(ValueError):
            boundary_from_scores(s, np.zeros(len(s), bool), 0., 'start')

    def test_differing_opening_is_still_trimmed(self):
        s = profile([(30, .2), (20, .92)])
        r = boundary_from_scores(s, np.zeros(len(s), bool), 0., 'start')
        self.assertEqual(r['status'], 'supported'); self.assertAlmostEqual(r['time'], 30., delta=.1)

    def test_ending_side(self):
        s = profile([(20, .92), (4, .3), (16, .9)])
        r = boundary_from_scores(s, np.zeros(len(s), bool), 100., 'end')
        self.assertEqual(r['status'], 'kept')


if __name__ == '__main__':
    unittest.main()
