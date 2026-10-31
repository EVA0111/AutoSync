"""Case 1: recover source opening music in both matching methods and output paths."""
import copy
import unittest
import numpy as np
from video_edits import recover_shared_opening, protect_opening, remove_missing


class SharedOpeningMatrix(unittest.TestCase):
    def setUp(self):
        rng=np.random.default_rng(401)
        self.source=rng.standard_normal((24,1400)).astype(np.float32)
        self.target=rng.standard_normal((24,1000)).astype(np.float32)
        self.target[:,:350]=self.source[:,150:500]+.012*rng.standard_normal((24,350))
        self.base=dict(duration=30.,source_video='source.mp4',target_video='target.mp4',
            reference='target.mp4',reference_stream=0,reference_shift=0.,
            models=[dict(speed=1.)],review=[],warnings=[],
            segments=[dict(kind='reference',target_start=0.,target_end=5.8,
                           reason='Source starts late according to picture alignment'),
                      dict(kind='audio',target_start=5.8,target_end=30.,
                           source_start=8.8,speed=1.)])

    def test_verified_shared_music_across_matching_methods_and_full_target_modes(self):
        for method in ('standard','ai_assisted'):
            for remove_video in (False,True):
                with self.subTest(method=method,remove_unmatched_video=remove_video):
                    plan=copy.deepcopy(self.base)
                    plan['sync_method']=method
                    result=recover_shared_opening(plan,self.source,self.target,28.)
                    if remove_video:
                        result=remove_missing(protect_opening(result,self.source,self.target,28.))
                        self.assertEqual(result['video_edits']['removed'],[])
                    self.assertEqual(result['segments'][0]['kind'],'audio')
                    self.assertAlmostEqual(result['segments'][0]['source_start'],3.,delta=.08)
                    self.assertEqual(result['duration'],30.)
                    self.assertEqual(plan['segments'][0]['kind'],'reference')

    def test_unrelated_music_is_not_replaced_in_either_matching_method(self):
        rng=np.random.default_rng(19)
        other=rng.standard_normal(self.target.shape).astype(np.float32)
        for method in ('standard','ai_assisted'):
            with self.subTest(method=method):
                plan=copy.deepcopy(self.base);plan['sync_method']=method
                result=recover_shared_opening(plan,self.source,other,28.)
                self.assertEqual(result['segments'][0]['kind'],'reference')

    def test_short_or_unavailable_source_opening_is_not_invented(self):
        for length in (2.,4.):
            with self.subTest(source_length=length):
                result=recover_shared_opening(self.base,self.source,self.target,length)
                self.assertEqual(result['segments'][0]['kind'],'reference')

    def test_inconclusive_audio_does_not_change_full_target_plan(self):
        result=recover_shared_opening(self.base,None,None,28.)
        self.assertEqual(result['segments'],self.base['segments'])
        self.assertEqual(result['warnings'],[])


if __name__=='__main__':
    unittest.main()
