"""Trimming must not keep a few-frame sliver of the outer section.

Measured on Zorro (Main episode, Keep OP/ED): the picture-verified main end
(1351.56 s) and the audio cut (1351.50 s) differ by 60 ms, so the trimmed plan
kept a 0.06 s segment mapped to the source ENDING 89 s away; rendering then
failed ('Unexpected time-stretch length error'), previously masked on Windows
by a temp-file cleanup error.
"""
import unittest
from main_episode import absorb_edge_slivers, trim_plan


def audio(a, b, ss, sp=1.0427):
    return dict(kind='audio', target_start=a, target_end=b, source_start=ss, speed=sp)


class TrimSlivers(unittest.TestCase):
    def test_trailing_sliver_extends_previous_mapping(self):
        segs = [audio(0., 1351.5, 1.), audio(1351.5, 1351.56, 1440.994)]
        out = absorb_edge_slivers(segs)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['target_end'], 1351.56)
        self.assertEqual(out[0]['source_start'], 1.)

    def test_leading_sliver_extends_next_mapping_backwards(self):
        out = absorb_edge_slivers([audio(0., .1, 900.), audio(.1, 50., 10.)])
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out[0]['source_start'], 10. - .1 * 1.0427)

    def test_real_segments_untouched(self):
        segs = [audio(0., 5., 1.), audio(5., 60., 20.)]
        self.assertEqual(absorb_edge_slivers(segs), segs)

    def test_trim_plan_end_to_end(self):
        plan = dict(segments=[audio(0., 1351.5, 1.), audio(1351.5, 1409.52, 1440.994, 1.0405)],
                    review=[], models=[], duration=1409.52)
        trim = dict(target_start=0., target_end=1351.56, duration=1351.56, boundaries={})
        p = trim_plan(plan, trim)
        self.assertEqual(len(p['segments']), 1)
        self.assertAlmostEqual(p['segments'][-1]['target_end'], 1351.56)


if __name__ == '__main__':
    unittest.main()
