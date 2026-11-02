"""Small edition edits must split timing groups instead of bending the slope.

Measured on regression case 1 (Standard, Full target): a ~0.18 s target-side
cut inside one >0.25 s-threshold group was absorbed into a 0.07 % slope error,
drifting delivered sync by up to 150 ms over 300 s. Synthetic anchors only.
"""
import unittest
import numpy as np
from autosync import group_anchors, robust_fit

SPEED = 25 / 23.976


def anchors(offset_fn, noise, seed=1, start=10, stop=600):
    rng = np.random.default_rng(seed)
    t = np.arange(start, stop, 6.)
    off = np.array([offset_fn(x) for x in t]) + rng.uniform(-noise, noise, len(t))
    off = np.round(off / .02) * .02  # 50 Hz feature quantization
    return np.c_[t, SPEED * t + off, np.full(len(t), .6)]


class SmallEditGrouping(unittest.TestCase):
    def test_small_step_splits_and_keeps_exact_rate(self):
        a = anchors(lambda t: 100. if t < 300 else 100.18, .012)
        groups = group_anchors(a, SPEED)
        self.assertEqual(len(groups), 2)
        self.assertGreaterEqual(groups[1][0, 0], 298)
        for g in groups:
            sp, off, res = robust_fit(g, SPEED)
            self.assertAlmostEqual(sp, SPEED, places=9)
            self.assertLess(res, .04)

    def test_step_with_stray_anchor_still_splits(self):
        # Case 1 had a -0.25 s stray anchor right after the step.
        a = anchors(lambda t: 100. if t < 300 else 100.18, .012)
        k = int(np.flatnonzero(a[:, 0] >= 300)[1]); a[k, 1] -= .25
        groups = group_anchors(a, SPEED)
        self.assertEqual(len(groups), 2)
        self.assertGreaterEqual(groups[1][0, 0], 298)
        self.assertLess(groups[1][0, 0], 305)

    def test_ordinary_scatter_never_splits(self):
        for seed in range(20):
            a = anchors(lambda t: 100., .035, seed)
            self.assertEqual(len(group_anchors(a, SPEED)), 1, seed)

    def test_genuine_drift_keeps_fitted_slope(self):
        a = anchors(lambda t: 100. + .0004 * t, .01)
        groups = group_anchors(a, SPEED)
        self.assertEqual(len(groups), 1)
        sp, off, res = robust_fit(groups[0], SPEED)
        self.assertAlmostEqual(sp, SPEED + .0004, delta=.00005)

    def test_unsplit_step_is_not_bridged_by_a_slope(self):
        # Fitting one group across a step must not trade a step for drift.
        a = anchors(lambda t: 100. if t < 300 else 100.18, .012)
        sp, off, res = robust_fit(a, SPEED)
        self.assertAlmostEqual(sp, SPEED, places=9)


if __name__ == '__main__':
    unittest.main()
