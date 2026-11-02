"""A single false anchor must not merge timing regimes into one fitted line.

Measured on regression case 3: an anchor contradicting the pictures by ~10 s
blocked group splitting; one group then mixed three regimes (p90 residual
9.6 s) and the plan rewound source audio by 9.6 s. Synthetic anchors only.
"""
import unittest
import numpy as np
from autosync import remove_outliers, group_anchors, robust_fit


def regime(t0, t1, offset, step=6.):
    t = np.arange(t0, t1 + .1, step)
    return np.c_[t, t + offset, np.full(len(t), .5)]


class InconsistentGroups(unittest.TestCase):
    def setUp(self):
        a = np.vstack([regime(10, 268, 93.48), regime(406, 418, 103.8), regime(448, 454, 103.4),
                       regime(526, 532, 93.5), np.array([[538., 641.08, .5]]),  # false anchor
                       regime(550, 610, 93.48), regime(670, 1228, 101.6)])
        self.anchors = a[np.argsort(a[:, 0])]

    def test_regimes_are_separated_and_false_anchor_dropped(self):
        groups = group_anchors(remove_outliers(self.anchors, 1.), 1.)
        offsets = [round(float(np.median(g[:, 1] - g[:, 0])), 1) for g in groups]
        self.assertEqual(offsets, [93.5, 103.8, 103.4, 93.5, 101.6])
        self.assertFalse(any(538. in g[:, 0] for g in groups))
        for g in groups:
            self.assertLess(robust_fit(g, 1.)[2], .05)

    def test_consistent_groups_are_untouched(self):
        a = regime(10, 600, 50.)
        self.assertEqual(len(group_anchors(a, 1.)), 1)


if __name__ == '__main__':
    unittest.main()
