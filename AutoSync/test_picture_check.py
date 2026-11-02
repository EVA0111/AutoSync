"""Audio sections contradicting the pictures must not create source rewinds.

Measured on Zorro (and case 6, the same episode): the German opening theme is
re-laid relative to the picture. Audio anchors there implied a target-audio /
picture relationship +0.55 s and -0.44 s away from the episode-wide one; the
plan rewound source audio by 0.68 s at 86.16 s, while the pictures show only
forward cuts. Synthetic anchors only.
"""
import unittest
import numpy as np
from picture_check import picture_checked_models
from autosync import build_plan
from continuity_guard import source_rewinds

SPEED = 25 / 23.976
D = -.05   # episode-wide audio/picture relationship


def pictures(spans):
    rows = []
    for a, b, off in spans:
        for t in np.arange(a, b, 4.):
            rows.append([t, SPEED * t + off, .9])
    return np.array(rows)


VISUAL = pictures([(2, 78, .60), (90, 140, .75), (154, 1340, 1.34)])


def model(first, last, off, n, speed=SPEED):
    return dict(speed=speed, offset=off, first=first, last=last, anchors=n, p90_residual=.02)


class PictureCheck(unittest.TestCase):
    def test_relaid_opening_follows_pictures(self):
        models = [model(4, 82, 1.13, 4, 1.0406), model(88, 148, .313, 4), model(154, 1348, 1.29, 94)]
        out, notes = picture_checked_models(models, VISUAL, SPEED)
        self.assertAlmostEqual(out[0]['offset'], .60 + D, delta=.02)
        self.assertAlmostEqual(out[1]['offset'], .75 + D, delta=.02)
        self.assertEqual(out[0]['speed'], SPEED)
        self.assertEqual(out[2], models[2])
        self.assertEqual(len(notes), 2)
        self.assertTrue(all('disagrees with pictures' in n['reason'] for n in notes))

    def test_reference_is_the_nearest_strong_section(self):
        # Measured on Zorro: the dub delay changes by 0.16 s between reels.
        visual = pictures([(2, 78, .60), (154, 1340, 1.34)])
        models = [model(4, 82, 1.13, 4), model(154, 820, 1.34 + .10, 36), model(826, 1348, 1.34 - .06, 59)]
        out, notes = picture_checked_models(models, visual, SPEED)
        self.assertAlmostEqual(out[0]['offset'], .60 + .10, delta=.02)
        self.assertEqual(out[1:], models[1:])   # strong sections are never changed

    def test_consistent_relationship_is_untouched(self):
        models = [model(4, 82, .55, 6), model(88, 148, .70, 8), model(154, 1348, 1.29, 94)]
        out, notes = picture_checked_models(models, VISUAL, SPEED)
        self.assertEqual(out, models); self.assertEqual(notes, [])

    def test_sections_without_pictures_or_majority_are_untouched(self):
        models = [model(4, 82, 1.13, 4), model(88, 148, .313, 4), model(154, 1348, 1.29, 94)]
        sparse = VISUAL[VISUAL[:, 0] > 150]
        out, _ = picture_checked_models(models, sparse, SPEED)
        self.assertEqual(out[:2], models[:2])
        # Two sections, two different relationships: no majority, no change.
        two = [model(4, 82, 1.13, 10), model(154, 1348, 1.29, 10)]
        self.assertEqual(picture_checked_models(two, VISUAL, SPEED)[0], two)

    def test_plan_has_no_rewind(self):
        rows = []
        for a, b, off in [(4, 83, 1.13), (88, 149, .313), (154, 1348, 1.293)]:
            for t in np.arange(a, b, 6.):
                rows.append([t, SPEED * t + off, .6])
        anchors = np.array(rows)
        cut = dict(time=0., confidence='uncertain', method='test', uncertainty_start=0, uncertainty_end=0)
        def refine(left, right, c): return dict(cut, time=(left['last'] + right['first']) / 2)
        segments, models, notes = build_plan(anchors, SPEED, 1400., 1500., None, None, None, refine, visual=VISUAL)
        self.assertEqual(source_rewinds(segments), [])
        self.assertTrue(any('disagrees with pictures' in n['reason'] for n in notes))
        without, _, _ = build_plan(anchors, SPEED, 1400., 1500., None, None, None, refine)
        self.assertTrue(source_rewinds(without))   # the measured failure, without the check


if __name__ == '__main__':
    unittest.main()
