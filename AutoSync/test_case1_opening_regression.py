"""Regression tests for case 1: shared-music opening must survive video trimming."""
import unittest
import numpy as np

from video_edits import protect_opening, remove_missing


class OpeningCutRegression(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(401)
        self.source = rng.standard_normal((24, 1400)).astype(np.float32)
        self.target = rng.standard_normal((24, 1000)).astype(np.float32)
        # Two separate opening windows share music, but the video is from a different edition.
        self.target[:, :350] = self.source[:, 150:500] + .012 * rng.standard_normal((24, 350))
        self.plan = {
            'duration': 30., 'source_video': 'source.mp4', 'target_video': 'target.mp4',
            'reference': 'target.mp4', 'reference_stream': 0, 'reference_shift': 0.,
            'review': [], 'warnings': [], 'models': [{'speed': 1.}],
            'segments': [
                {'kind': 'reference', 'target_start': 0., 'target_end': 5.8,
                 'reason': 'Source starts late according to the picture alignment'},
                {'kind': 'audio', 'target_start': 5.8, 'target_end': 30.,
                 'source_start': 7.8, 'speed': 1.},
            ],
        }

    def test_case_one_shared_opening_is_kept_and_source_audio_matched(self):
        original = self.plan['segments'][0].copy()
        protected = protect_opening(self.plan, self.source, self.target, 28.)
        self.assertEqual(self.plan['segments'][0], original)
        self.assertEqual(protected['segments'][0]['kind'], 'audio')
        self.assertAlmostEqual(protected['segments'][0]['source_start'], 3., delta=.08)
        result = remove_missing(protected)
        self.assertAlmostEqual(result['duration'], 30.)
        self.assertEqual(result['video_edits']['removed'], [])
        self.assertTrue(result['review'])

    def test_no_audio_evidence_keeps_target_video_and_music(self):
        protected = protect_opening(self.plan, None, None, 28.)
        self.assertEqual(protected['segments'][0]['kind'], 'target_outer')
        self.assertAlmostEqual(remove_missing(protected)['duration'], 30.)

    def test_silent_opening_does_not_count_as_different(self):
        silent = self.target.copy()
        silent[:, :290] = 0
        protected = protect_opening(self.plan, self.source, silent, 28.)
        self.assertEqual(protected['segments'][0]['kind'], 'target_outer')
        self.assertAlmostEqual(remove_missing(protected)['duration'], 30.)

    def test_genuinely_unrelated_opening_can_be_removed(self):
        rng = np.random.default_rng(890)
        unrelated = rng.standard_normal(self.target.shape).astype(np.float32)
        protected = protect_opening(self.plan, self.source, unrelated, 28.)
        self.assertEqual(protected['segments'][0]['kind'], 'reference')
        result = remove_missing(protected)
        self.assertAlmostEqual(result['duration'], 24.2)
        self.assertEqual(len(result['video_edits']['removed']), 1)

    def test_inconclusive_opening_cannot_be_dropped_if_target_audio_missing(self):
        plan = dict(self.plan)
        plan['reference'] = 'separate_audio.wav'
        with self.assertRaisesRegex(ValueError, 'cannot be safely removed'):
            protect_opening(plan, None, None, 28.)

    def test_missing_source_length_preserves_target_audio(self):
        protected = protect_opening(self.plan, self.source, self.target, 4.)
        self.assertEqual(protected['segments'][0]['kind'], 'target_outer')
        self.assertAlmostEqual(remove_missing(protected)['duration'], 30.)

    def test_middle_reference_gap_still_removed(self):
        modified = dict(self.plan)
        modified['segments'] = [
            {'kind': 'audio', 'target_start': 0., 'target_end': 8.,
             'source_start': 3., 'speed': 1.},
            {'kind': 'reference', 'target_start': 8., 'target_end': 10.},
            {'kind': 'audio', 'target_start': 10., 'target_end': 30.,
             'source_start': 12., 'speed': 1.},
        ]
        modified['duration'] = 30.
        kept = protect_opening(modified, self.source, self.target, 28.)
        self.assertAlmostEqual(remove_missing(kept)['duration'], 28.)


if __name__ == '__main__':
    unittest.main()
