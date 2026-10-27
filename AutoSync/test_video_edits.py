import unittest
import numpy as np
from video_edits import remove_missing,map_anchors

class VideoEditsTest(unittest.TestCase):
 def plan(self):
  return dict(duration=30,review=[],segments=[dict(kind='audio',target_start=0,target_end=10,source_start=0,speed=1),dict(kind='reference',target_start=10,target_end=15),dict(kind='audio',target_start=15,target_end=25,source_start=10,speed=1),dict(kind='target_outer',target_start=25,target_end=30)])
 def test_cut_and_outer_positions(self):
  p=self.plan();q=remove_missing(p)
  self.assertEqual(q['duration'],25);self.assertEqual(p['duration'],30)
  self.assertEqual(q['segments'][1]['source_start'],10)
  self.assertEqual(q['segments'][-1]['target_start'],20)
  self.assertEqual(q['segments'][-1]['reference_target_start'],25)
  self.assertEqual(q['video_edits']['removed'][0]['start'],10)
  self.assertEqual(remove_missing(q),q)
 def test_trimmed_original_coordinates(self):
  p=self.plan();p['main_trim']={'target_start':50}
  q=remove_missing(p)
  self.assertEqual(q['video_edits']['kept'][1]['original_start'],65)
 def test_anchors_and_review_retimed(self):
  p=self.plan();p['review']=[dict(start=16,end=18,splice=17,reason='Check',confidence='estimated')]
  q=remove_missing(p)
  np.testing.assert_equal(map_anchors(np.array([[2,2,1],[12,10,1],[16,11,1]]),q),[[2,2,1],[11,11,1]])
  self.assertEqual(q['review'][0]['splice'],12)
 def test_uncertain_audio_kept(self):
  p=self.plan();p['segments'][1]=dict(kind='audio',target_start=10,target_end=15,source_start=10,speed=1,confidence='estimated')
  self.assertEqual(remove_missing(p)['duration'],30)
 def test_verified_gap_removed(self):
  p=self.plan();p['segments'][1]['kind']='verified_gap'
  self.assertEqual(remove_missing(p)['duration'],25)
 def test_all_missing_rejected(self):
  with self.assertRaises(ValueError):remove_missing(dict(duration=10,segments=[dict(kind='reference',target_start=0,target_end=10)]))

if __name__=='__main__':unittest.main()
