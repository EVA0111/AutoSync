"""Regression coverage for optional model-assisted matching (no model downloads)."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from ai_sync import candidate_pairs, _consistent, verify_audio_candidates, combine_standard_and_learned

class AIAssistedTests(unittest.TestCase):
    def test_learned_embeddings_find_reciprocal_unique_temporal_matches(self):
        rng=np.random.default_rng(35)
        v=rng.normal(size=(10,64)).astype(np.float32)
        target_t=np.arange(10)*18. + 4.
        source_t=target_t*(25/24) + 12.
        match=candidate_pairs(target_t,v,source_t,v+.002*rng.normal(size=v.shape),
                              min_similarity=.88,min_margin=.05)
        self.assertEqual(len(match),10)
        verified=_consistent(match,25/24,tolerance=.3)
        self.assertEqual(len(verified),10)
        self.assertAlmostEqual(float(np.median(verified[:,1]-25/24*verified[:,0])),12.,places=4)

    def test_repeated_or_nonunique_embeddings_do_not_match(self):
        v=np.ones((8,32),dtype=np.float32)
        t=np.arange(8)*24.
        result=candidate_pairs(t,v,t,v,min_similarity=.9,min_margin=.055)
        self.assertEqual(len(result),0)

    def test_embedding_proposal_requires_independent_acoustic_verification(self):
        rng=np.random.default_rng(12)
        source=rng.standard_normal((24,2800)).astype(np.float32)
        target=source[:,500:2000].copy()
        times=np.array([4.,10.,16.,22.,28.])
        proposals=np.column_stack([times,times+10,np.ones(len(times))*.98])
        verified=verify_audio_candidates(proposals,source,target,1.)
        self.assertEqual(len(verified),5)
        np.testing.assert_allclose(verified[:,1],times+10.,atol=.03)
        # High neural confidence is not enough if original sound doesn't match.
        unrelated=rng.standard_normal(target.shape).astype(np.float32)
        bad=verify_audio_candidates(proposals,source,unrelated,1.)
        self.assertEqual(len(bad),0)

    def test_only_verified_consistent_new_anchors_augment_standard(self):
        baseline=np.array([[10.,20.,.9],[30.,40.,.9],[50.,60.,.9],[70.,80.,.9]])
        additional=np.array([[30.1,40.1,.9],[90.,100.,.9],[110.,160.,.9]])
        final=combine_standard_and_learned(baseline,additional,1.)
        self.assertEqual(len(final),5)
        self.assertTrue(any(abs(row[0]-90.)<.01 for row in final))
        self.assertFalse(any(abs(row[0]-110.)<.01 for row in final))

    def test_default_standard_mode_and_explicit_ai_command(self):
        from gui_config import build_command,FIELDS,MODES
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'episode.mkv';source.touch()
            v={k:d for k,_,d in FIELDS}
            v.update(source=str(source),target=str(source),audio='',reference='',
                     out=str(Path(td)/'output'),mode='Sync full target audio',
                     video_codec='h264',video_preset='veryfast',audio_only=False,
                     analyze_only=True,remove_unmatched_video=False,
                     reference_fallback=False,allow_uncertain_cuts=False)
            cmd,_=build_command(v,'Single episode')
            self.assertNotIn('--sync-method',cmd)
            v['sync_method']='ai_assisted'
            cmd,_=build_command(v,'Single episode')
            self.assertEqual(cmd[cmd.index('--sync-method')+1],'ai_assisted')
            v['sync_method']='bogus'
            with self.assertRaisesRegex(ValueError,'Unknown syncing method'):
                build_command(v,'Single episode')

if __name__=='__main__':unittest.main()
