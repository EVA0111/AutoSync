import unittest,json
from unittest.mock import patch
from chapter_boundaries import explicit_outer_chapters
class Chapters(unittest.TestCase):
 def call(self,items):
  d={'streams':[{'codec_type':'video','start_time':'.083'}],'chapters':[{'start_time':str(a),'end_time':str(b),'tags':{'title':t}} for a,b,t in items]}
  with patch('chapter_boundaries.vc.run',return_value=json.dumps(d).encode()):return explicit_outer_chapters('x',1000)
 def test_explicit_labels_and_video_origin(self):
  r=self.call([(0,66.108,'Opening Credits'),(66.108,900,'Part 1'),(900,920,'Next Episode Preview'),(920,1000,'Ending Credits')]);self.assertAlmostEqual(r['start']['time'],66.025);self.assertAlmostEqual(r['end']['time'],919.917)
 def test_generic_labels_are_not_guessed(self):
  self.assertEqual(self.call([(0,60,'Chapter 1'),(60,1000,'Chapter 2')]),{})
 def test_cold_open_is_not_removed(self):
  self.assertNotIn('start',self.call([(0,30,'Cold open'),(30,90,'Opening'),(90,1000,'Episode')]))
 def test_epilogue_is_not_removed(self):
  self.assertNotIn('end',self.call([(0,900,'Episode'),(900,970,'Ending'),(970,1000,'Epilogue')]))

 def test_preview_before_ending_remains_inside_main_range(self):
  r=self.call([(0,850,'Episode'),(850,930,'Next Episode Preview'),(930,1000,'Ending')])
  self.assertAlmostEqual(r['end']['time'],929.917)
  self.assertEqual(r['end']['chapter'],'ending')
 def test_preview_after_ending_is_not_discarded_by_chapters(self):
  self.assertNotIn('end',self.call([(0,850,'Episode'),(850,950,'Ending'),(950,1000,'Next Episode Preview')]))
 def test_manual_end_still_takes_priority(self):
  from main_episode import detect_main
  import numpy as np
  plan={'source_video':'s','target_video':'t','duration':1000}
  r=detect_main(plan,np.empty((0,3)),manual_start=60,manual_end=900)
  self.assertEqual(r['target_end'],900)
