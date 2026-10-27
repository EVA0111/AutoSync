import unittest
from unittest.mock import patch
import numpy as np
import main_episode as m

class EstimatedBoundariesTest(unittest.TestCase):
 def plan(self):return dict(duration=100,target_video='target',source_video='source',models=[dict(speed=1,first=10,last=40)])
 def test_no_evidence_keeps_estimate(self):
  r=m.refine_estimated_boundary(self.plan(),np.empty((0,3)),0,20,'start')
  self.assertEqual(r['status'],'estimated');self.assertEqual(r['time'],20)
 def test_supported_nearby_boundary_refines(self):
  matches=np.array([[20,20,1],[23,23,1],[26,26,1]])
  scores=np.r_[np.full(12*25,.2),np.full(8*25,.95)]
  with patch.object(m,'frames',side_effect=[(np.zeros((500,1)),np.zeros(500,bool)),np.zeros((500,1))]),patch.object(m,'compare',return_value=scores):
   r=m.refine_estimated_boundary(self.plan(),matches,0,20,'start')
  self.assertEqual(r['time'],22);self.assertEqual(r['status'],'supported')
 def test_shared_pictures_without_boundary_stay_estimated(self):
  matches=np.array([[20,20,1],[23,23,1],[26,26,1]])
  with patch.object(m,'frames',side_effect=[(np.zeros((500,1)),np.zeros(500,bool)),np.zeros((500,1))]),patch.object(m,'compare',return_value=np.full(500,.95)):
   r=m.refine_estimated_boundary(self.plan(),matches,0,20,'start')
  self.assertEqual(r['time'],20);self.assertEqual(r['status'],'estimated')

if __name__=='__main__':unittest.main()
