import unittest
from unittest.mock import patch
import numpy as np
from visual_cuts import locate_visual_cut
from cut_detection import source_cuts
from autosync import render
from pathlib import Path

class EditionGapTests(unittest.TestCase):
    def probe(self,energy):
        n=300;q=np.tile([1.,0.],(n,1));q[100:150]=0
        old=q.copy();old[150:]=[0.,1.]
        new=q.copy();new[:100]=[0.,1.]
        dark=np.zeros(n,bool);dark[100:150]=True
        with patch('visual_cuts.frames',side_effect=[(q,dark),(old,np.zeros(n,bool)),(new,np.zeros(n,bool))]):
            return locate_visual_cut(dict(last=4,speed=1,offset=10),dict(first=8,speed=1,offset=15),'s','t',target_energy=energy)
    def test_verified_black_pause(self):
        r=self.probe(np.full(600,1e-7));self.assertEqual(r['target_gap'],[4,6]);self.assertEqual(r['confidence'],'supported')
    def test_black_pause_with_sound_is_not_automatically_replaced(self):
        self.assertNotIn('target_gap',self.probe(np.full(600,.01)))
    def test_cut_audit_includes_whole_removed_eyecatch(self):
        s=[dict(kind='audio',target_start=0,target_end=4,source_start=10,speed=1),dict(kind='verified_gap',target_start=4,target_end=6),dict(kind='audio',target_start=6,target_end=12,source_start=21,speed=1)]
        c=source_cuts(s)[0];self.assertEqual(c['removed_seconds'],7);self.assertEqual(c['target_time'],4)
    def test_unreviewed_gap_cannot_bypass_export_guard(self):
        s=[dict(kind='audio',target_start=0,target_end=4,source_start=10,speed=1),dict(kind='verified_gap',target_start=4,target_end=6),dict(kind='audio',target_start=6,target_end=12,source_start=21,speed=1)]
        with self.assertRaisesRegex(RuntimeError,'unresolved'):render(dict(segments=s,review=[]),Path('.'),False)

if __name__=='__main__':unittest.main()
