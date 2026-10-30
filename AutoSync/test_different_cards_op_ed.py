"""Regression: different-edition OP/ED, eyecatches and title cards.

Fixtures derive from the uploaded alignment's structure; synthetic picture
signals deliberately avoid pretending to know private video's exact frames.
"""
import unittest
from unittest.mock import patch
import numpy as np

from visual_cuts import locate_target_insert, locate_visual_insert_island
from autosync import build_plan, requires_explicit_reference_fallback
from continuity_guard import source_rewinds
from main_episode import detect_main, keep_target_outer

class TargetOnlyCards(unittest.TestCase):
    def pair(self,ga=92.,gb=102.,right_offset=10.,audio_offset=10.):
        left=dict(speed=1.,offset=20.,first=80.,last=92.)
        right=dict(speed=1.,offset=right_offset,first=102.,last=125.)
        lo=88.;n=450
        old=np.zeros(n);new=np.zeros(n)
        old[:int(round((ga-lo)*25))]=.99
        new[int(round((gb-lo)*25)):]=.99
        q=np.zeros((n,5));dark=np.zeros(n,bool)  # coloured/lettered cards, not black.
        audio_models=(left,dict(right,offset=audio_offset))
        return left,right,lo,old,new,q,dark,audio_models

    def test_nonblack_target_eyecatch_preserves_target_audio(self):
        left,right,lo,old,new,q,dark,models=self.pair()
        raw=locate_visual_insert_island(old,new,lo,left,right,models)
        self.assertIsNotNone(raw)
        self.assertEqual(raw['target_gap_kind'],'reference')
        self.assertEqual(raw['confidence'],'supported')
        self.assertAlmostEqual(raw['target_gap'][0],92,delta=.10)
        self.assertAlmostEqual(raw['target_gap'][1],102,delta=.10)
        with patch('visual_cuts.frames',side_effect=[(q,dark),q,q]), \
             patch('visual_cuts.compare',side_effect=[old,new]):
            cut=locate_target_insert(left,right,'source.mkv','target.mkv',np.ones(6000)*.01,
                                     audio_models=models)
        self.assertIsNotNone(cut)
        self.assertEqual(cut['target_gap_kind'],'reference')
        self.assertIn('title-card',cut['method'])

    def test_unmatched_pictures_without_matching_source_continuity_rejected(self):
        left,right,lo,old,new,q,dark,models=self.pair(right_offset=13.)
        self.assertIsNone(locate_visual_insert_island(old,new,lo,left,right,models))

    def test_cross_dub_audio_timing_disagreement_cannot_authorize_gap(self):
        left,right,lo,old,new,q,dark,models=self.pair(audio_offset=7.)
        self.assertIsNone(locate_visual_insert_island(old,new,lo,left,right,models))

    def test_merely_different_lettering_without_duration_change_is_not_insert(self):
        left,right,lo,old,new,q,dark,models=self.pair(right_offset=20.)
        self.assertIsNone(locate_visual_insert_island(old,new,lo,left,right))

    def test_brief_or_unbracketed_scene_mismatch_is_not_automatically_cut(self):
        left,right,lo,old,new,q,dark,models=self.pair()
        old[:]=0.
        self.assertIsNone(locate_visual_insert_island(old,new,lo,left,right,models))

    def test_verified_cards_replace_rewinding_audio_with_target_audio(self):
        # A 10-second target-only card originally generated a 10s backwards
        # source jump. Bracketing pictures instead identify a reference interval.
        a=np.asarray([[t,t+20,1.] for t in [20,30,40,50,60,70,80,88]]
                    +[[t,t+10,1.] for t in [105,115,125,135,145,155,165,175]])
        cut=dict(time=92.,target_gap=[92.,102.],target_gap_kind='reference',
                 confidence='supported',method='picture-verified target-only title-card',
                 uncertainty_start=92.,uncertainty_end=102.)
        segments,_,reviews=build_plan(a,1.,190.,300.,None,None,None,lambda *_:cut)
        inserts=[s for s in segments if s['kind']=='reference']
        self.assertEqual(len(inserts),1)
        self.assertTrue(inserts[0]['verified_insert'])
        self.assertAlmostEqual(inserts[0]['target_start'],92.)
        self.assertAlmostEqual(inserts[0]['target_end'],102.)
        self.assertFalse(requires_explicit_reference_fallback(segments))
        self.assertEqual(source_rewinds(segments),[])
        self.assertAlmostEqual(segments[-1]['target_end'],190.)
        self.assertEqual(len(reviews),1)

    def test_unverified_reference_region_still_needs_user_opt_in(self):
        self.assertTrue(requires_explicit_reference_fallback([
            dict(kind='reference',target_start=0.,target_end=5.)]))
        self.assertTrue(requires_explicit_reference_fallback([
            dict(kind='reference',target_start=5.,target_end=8.,verified_insert=False)]))
        self.assertFalse(requires_explicit_reference_fallback([
            dict(kind='reference',target_start=5.,target_end=8.,verified_insert=True)]))


class DifferentOpeningEnding(unittest.TestCase):
    def setUp(self):
        self.visual=np.array([[t,t+15.,.99] for t in range(20,81)],dtype=float)
        self.plan=dict(duration=100.,source_video='source.mkv',target_video='target.mkv',
            source_crop='',target_crop='',models=[dict(speed=1.,offset=15.,first=20.,last=80.)],
            segments=[dict(kind='audio',target_start=0.,target_end=100.,
                           source_start=15.,speed=1.)],review=[],reference_shift=0.)
    def frames(self,path,start,length,*args,**kwargs):
        n=int(round(length*25))
        q=np.ones((n,6))
        if kwargs.get('with_dark'):return q,np.zeros(n,dtype=bool)
        return q
    def compare(self,q,x):
        n=min(len(q),len(x))
        self.count+=1
        if self.count%2:
            return np.r_[np.full(8*25,.05),np.full(n-8*25,.99)]
        return np.r_[np.full(n-15*25,.99),np.full(15*25,.05)]

    def test_distinct_op_ed_keeps_target_outer_even_if_music_matches_somewhere(self):
        self.count=0
        # Under the old logic a spurious audio match vetoed the strong
        # picture-derived opening boundary, importing source OP audio.
        with patch('chapter_boundaries.explicit_outer_chapters',return_value={}), \
             patch('main_episode.frames',side_effect=self.frames), \
             patch('main_episode.compare',side_effect=self.compare), \
             patch('main_episode.opening_audio_correspondence',
                   return_value=dict(matched=True,different=False,score=.823)):
            trim=detect_main(self.plan,self.visual,keep_target_outer=True,
                             source_features=np.ones((24,500)),
                             target_features=np.ones((24,500)))
        self.assertAlmostEqual(trim['target_start'],8.,delta=.05)
        self.assertAlmostEqual(trim['target_end'],85.,delta=.05)
        with patch('main_episode.vc.probe',return_value={
             'streams':[dict(codec_type='video',start_time='0'),
                        dict(codec_type='audio',start_time='0')]}):
            plan=keep_target_outer(self.plan,trim)
        self.assertEqual(plan['segments'][0]['kind'],'target_outer')
        self.assertAlmostEqual(plan['segments'][0]['target_end'],8.,delta=.05)
        self.assertEqual(plan['segments'][-1]['kind'],'target_outer')
        self.assertAlmostEqual(plan['segments'][-1]['target_start'],85.,delta=.05)
        self.assertAlmostEqual(plan['segments'][1]['source_start'],23.,delta=.05)

    def test_main_only_retains_shared_audio_veto_for_safety(self):
        self.count=0
        with patch('chapter_boundaries.explicit_outer_chapters',return_value={}), \
             patch('main_episode.frames',side_effect=self.frames), \
             patch('main_episode.compare',side_effect=self.compare), \
             patch('main_episode.opening_audio_correspondence',
                   return_value=dict(matched=True,different=False,score=.823)):
            trim=detect_main(self.plan,self.visual,keep_target_outer=False,
                             source_features=np.ones((24,500)),
                             target_features=np.ones((24,500)))
        self.assertAlmostEqual(trim['target_start'],0.,delta=.05)
        self.assertEqual(trim['boundaries']['start']['status'],'kept')

if __name__=='__main__':unittest.main()
