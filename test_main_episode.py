import unittest
import numpy as np
from main_episode import boundary_from_scores,trim_plan

class MainEpisodeTests(unittest.TestCase):
    def test_differing_opening(self):
        s=np.r_[np.full(20*25,.2),np.full(30*25,.95)]
        self.assertAlmostEqual(boundary_from_scores(s,np.zeros(len(s),bool),0,'start')['time'],20)
    def test_differing_ending_keeps_fade(self):
        s=np.r_[np.full(30*25,.95),np.zeros(20*25)];dark=np.zeros(len(s),bool);dark[750:758]=True
        self.assertAlmostEqual(boundary_from_scores(s,dark,100,'end')['time'],130.32)
    def test_common_outer_content_kept(self):
        s=np.full(50*25,.95);d=np.zeros(len(s),bool)
        self.assertEqual(boundary_from_scores(s,d,0,'start')['status'],'kept')
        self.assertEqual(boundary_from_scores(s,d,0,'end')['status'],'kept')
    def test_cold_open_not_silently_removed(self):
        s=np.r_[np.full(10*25,.95),np.full(30*25,.2),np.full(30*25,.95)]
        with self.assertRaises(ValueError):boundary_from_scores(s,np.zeros(len(s),bool),0,'start')
    def test_ambiguous_boundary_stops(self):
        s=np.r_[np.full(20*25,.7),np.full(30*25,.81)]
        with self.assertRaises(ValueError):boundary_from_scores(s,np.zeros(len(s),bool),0,'start')
    def test_trim_preserves_cut_and_reference_timing(self):
        p=dict(duration=100,reference_shift=.1,segments=[dict(kind='audio',target_start=0,target_end=50,source_start=3,speed=1.04),dict(kind='audio',target_start=50,target_end=100,source_start=60,speed=1.04)],review=[dict(start=48,end=52,splice=50,confidence='supported')])
        q=trim_plan(p,dict(target_start=10,target_end=90))
        self.assertEqual(q['duration'],80);self.assertAlmostEqual(q['segments'][0]['source_start'],13.4)
        self.assertEqual(q['segments'][1]['target_start'],40);self.assertEqual(q['review'][0]['splice'],40)
        self.assertAlmostEqual(q['reference_shift'],-9.9);self.assertEqual(p['duration'],100)

if __name__=='__main__':unittest.main()
