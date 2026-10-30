"""Regression: uploaded DBZ alignment had two backward source-audio joins.

Timing values are derived from the alignment JSON; private media are not
committed to the source tree. Tests do not claim to identify the true edits.
"""
import copy
import tempfile
import unittest
from pathlib import Path

from continuity_guard import source_rewinds,annotate_rewinds
from cut_detection import source_cuts
from autosync import render


EXAMPLE=[
    dict(kind='audio',target_start=0.,target_end=195.6,
         source_start=39.19054279054282,speed=0.9589077589077588),
    dict(kind='audio',target_start=195.6,target_end=745.1,
         source_start=218.6037962037961,speed=0.9590409590409594),
    dict(kind='audio',target_start=745.1,target_end=1350.959,
         source_start=734.4911088911092,speed=0.9590409590409573),
    dict(kind='target_outer',target_start=1350.959,target_end=1476.975,
         reason='Keep target ending audio')
]


class RepeatedSourceAudioRegression(unittest.TestCase):
    def setUp(self):
        self.plan=dict(duration=1476.975,segments=copy.deepcopy(EXAMPLE),review=[],
                       warnings=[],source_cuts=[],audio='source_test.mkv',
                       reference='target_test.mkv')

    def test_detects_both_unflagged_backward_joins(self):
        self.assertEqual(source_cuts(self.plan['segments']),[])
        problems=source_rewinds(self.plan['segments'])
        self.assertEqual(len(problems),2)
        self.assertAlmostEqual(problems[0]['target_time'],195.6)
        self.assertAlmostEqual(problems[0]['replayed_source_seconds'],8.1491042291,places=5)
        self.assertAlmostEqual(problems[1]['target_time'],745.1)
        self.assertAlmostEqual(problems[1]['replayed_source_seconds'],11.1056943057,places=5)
        self.assertGreater(problems[1]['estimated_target_equivalent_seconds'],11.)

    def test_plan_records_uncertainty_at_both_joins(self):
        plan=annotate_rewinds(self.plan)
        self.assertEqual(len(plan['source_rewinds']),2)
        flags=[x for x in plan['review'] if x.get('issue_type')=='source_rewind']
        self.assertEqual(len(flags),2)
        self.assertTrue(all(x['confidence']=='uncertain' for x in flags))
        self.assertEqual([x['splice'] for x in flags],[195.6,745.1])
        self.assertEqual(len(plan['warnings']),2)
        annotate_rewinds(plan)
        self.assertEqual(len(plan['review']),2)

    def test_default_render_cannot_silently_repeat_audio(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError,'backwards source-audio joins'):
                render(self.plan,Path(td),reference_fallback=False)

    def test_forward_source_cut_is_not_a_rewind(self):
        parts=[dict(kind='audio',target_start=0.,target_end=10.,source_start=5.,speed=1.),
               dict(kind='audio',target_start=10.,target_end=20.,source_start=19.,speed=1.)]
        self.assertEqual(source_rewinds(parts),[])
        self.assertEqual(len(source_cuts(parts)),1)

    def test_reference_gap_does_not_hide_replayed_source_audio(self):
        parts=[dict(kind='audio',target_start=0.,target_end=10.,source_start=10.,speed=1.),
               dict(kind='reference',target_start=10.,target_end=15.),
               dict(kind='audio',target_start=15.,target_end=20.,source_start=17.,speed=1.)]
        result=source_rewinds(parts)
        self.assertEqual(len(result),1)
        self.assertAlmostEqual(result[0]['replayed_source_seconds'],3.)

    def test_tiny_float_rounding_does_not_trigger_false_positive(self):
        parts=[dict(kind='audio',target_start=0.,target_end=10.,source_start=5.,speed=.959),
               dict(kind='audio',target_start=10.,target_end=15.,source_start=14.58,speed=.959)]
        self.assertEqual(source_rewinds(parts),[])


if __name__=='__main__':
    unittest.main()
