import unittest
from types import SimpleNamespace
import numpy as np
import manual_ranges as mr
class ManualRangesTest(unittest.TestCase):
 def bounds(self):return dict(source_start=20.,source_end=80.,target_start=10.,target_end=70.)
 def plan(self,trim=False):
  a,b=(0.,60.) if trim else (10.,70.)
  p=dict(segments=[dict(kind='audio',target_start=a,target_end=b,source_start=21.,speed=1.)],review=[])
  if trim:p['main_trim']={}
  return p
 def test_estimates_preserve_automatic_audio(self):
  import copy
  p=self.plan();original=copy.deepcopy(p['segments'])
  mr.apply(p,self.bounds(),np.array([[20,31,1],[60,71,1]]))
  self.assertEqual(p['segments'],original)
  self.assertEqual(p['manual_range']['points']['start']['source_used'],21)
  self.assertTrue(all(r['confidence']=='estimated' for r in p['review']))
 def test_trimmed_coordinates(self):
  p=self.plan(True);p['main_trim']={'target_start':10,'target_end':70}
  mr.apply(p,self.bounds(),np.array([[20,31,1],[60,71,1]]))
  self.assertEqual(p['manual_range']['points']['start']['target_used'],0)
  self.assertEqual(p['manual_range']['points']['end']['target_used'],60)
 def test_filter_includes_nearby_matches(self):
  a=np.array([[0,0,1],[20,30,1],[30,100,1],[80,40,1],[81,40,1]])
  np.testing.assert_array_equal(mr.select(a,self.bounds()),[[20,30,1],[80,40,1]])
 def test_conflicting_estimate_does_not_stretch_audio(self):
  p=self.plan();b=self.bounds();b['source_start']=79
  mr.apply(p,b,np.array([[20,31,1],[60,71,1]]))
  self.assertEqual(p['segments'][0]['speed'],1)
  self.assertEqual(p['manual_range']['points']['start']['source_adjustment'],-58)
 def test_unmatched_endpoint_flagged(self):
  p=self.plan();p['segments'][0]['kind']='reference'
  mr.apply(p,self.bounds(),np.empty((0,3)))
  self.assertNotIn('source_used',p['manual_range']['points']['start'])
  self.assertEqual(len(p['review']),2)
 def test_per_file_marks_survive_managed_queue(self):
  from output_jobs import flatten
  rows=[dict(source='a.mkv',target='b.mkv',main_start='0',main_end='40',source_main_start='2',source_main_end='42'),dict(source='c.mkv',target='d.mkv')]
  jobs=flatten([dict(task='Folder batch',reviewed=True,values={'main_start':'','main_end':''},pairs=rows)])
  self.assertEqual(jobs[0]['values']['source_main_start'],'2');self.assertEqual(jobs[0]['values']['main_start'],'0')
  self.assertNotIn('source_main_start',jobs[1]['values']);self.assertEqual(jobs[1]['values']['main_start'],'')
 def test_delay_validation(self):
  a=SimpleNamespace(source_main_start=20,source_main_end=80,main_start=10,main_end=70,main_only=True,keep_target_op_ed=False)
  self.assertEqual(mr.validate(a,100,100,100,2)['source_start'],18)
  a.main_start=None
  with self.assertRaises(ValueError):mr.validate(a,100,100,100,2)
if __name__=='__main__':unittest.main()
