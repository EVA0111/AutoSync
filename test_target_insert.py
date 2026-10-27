import unittest
from unittest.mock import patch
import numpy as np
from visual_cuts import locate_target_insert
from autosync import build_plan
class TargetInsertTests(unittest.TestCase):
 def detect(self,power=0,black=True):
  n=700;q=np.zeros((n,4));dark=np.zeros(n,bool);dark[200:225]=True
  left=dict(speed=1,offset=10,last=10);right=dict(speed=1,offset=5,first=30)
  old=np.r_[np.full(200,.98),np.zeros(500)];new=np.r_[np.zeros(350),np.full(350,.98)]
  with patch('visual_cuts.frames',side_effect=[(q,dark),q,q,(np.zeros((25,4)),np.full(25,black))]),patch('visual_cuts.compare',side_effect=[old,new]):
   return locate_target_insert(left,right,'src','dst',np.full(5000,power))
 def test_verified_insert_uses_reference(self):
  r=self.detect();self.assertEqual(r['target_gap_kind'],'reference');self.assertEqual(r['target_gap'],[14,20])
 def test_audible_source_gap_rejected(self):self.assertIsNone(self.detect(.001))
 def test_source_picture_content_rejected(self):self.assertIsNone(self.detect(black=False))
 def test_planner_does_not_duplicate_source_over_insert(self):
  a=np.array([[t,t+10,1] for t in [2,4,6,8,10]]+[[t,t+5,1] for t in [22,24,26,28,30]])
  result=self.detect()
  segments,_,_=build_plan(a,1,32,50,None,None,None,lambda *args:result)
  gap=[s for s in segments if s['kind']=='reference'][0]
  self.assertEqual((gap['target_start'],gap['target_end']),(14,20))
  self.assertEqual(sum(s['target_end']-s['target_start'] for s in segments),32)
