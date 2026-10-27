import unittest,copy
from types import SimpleNamespace
import input_trims as it

class InputTrimsTest(unittest.TestCase):
 def test_independent_ranges(self):
  args=SimpleNamespace()
  self.assertEqual(it.range_for(dict(source_trim_start='0',source_trim_end='12'),args,'source'),(0,12))
  self.assertIsNone(it.range_for(dict(source_trim_start='0',source_trim_end='12'),args,'target'))
 def test_invalid_ranges(self):
  for a,b in [(1,''),(1,1),(4,2),(-1,10),(float('nan'),10),(0,float('inf'))]:
   with self.assertRaises(ValueError):it.range_for(dict(target_trim_start=a,target_trim_end=b),SimpleNamespace(),'target')
 def test_flatten_preserves_ranges_per_episode(self):
  from output_jobs import flatten
  jobs=flatten([dict(task='Folder batch',reviewed=True,values={},pairs=[dict(source='a',target='b',source_trim_start='2',source_trim_end='30'),dict(source='c',target='d',target_trim_start='4',target_trim_end='32')])])
  self.assertEqual(jobs[0]['values']['source_trim_start'],'2');self.assertNotIn('target_trim_start',jobs[0]['values'])
  self.assertEqual(jobs[1]['values']['target_trim_start'],'4');self.assertNotIn('source_trim_start',jobs[1]['values'])
 def test_rebase_originals_not_temporary_files(self):
  p=dict(audio='tmp',audio_stream=0,target_video='tmpT',reference='tmpT',reference_shift=-3,outer_shift=0,models=[dict(offset=4)],segments=[dict(kind='audio',target_start=0,target_end=10,source_start=1,speed=1)],video_edits=dict(kept=[dict(original_start=2,original_end=12)]))
  meta=dict(source=dict(original='source',start=8),target=dict(original='target',start=20),audio=dict(original='dub',stream=2,offset=7),reference=dict(original='ref',stream=3,offset=19),outer=dict(stream=1,offset=20))
  q=it.rebase(p,meta)
  self.assertEqual(q['audio'],'dub');self.assertEqual(q['segments'][0]['source_start'],8)
  self.assertEqual(q['reference_shift'],-22);self.assertEqual(q['outer_shift'],-20)
  self.assertEqual(q['video_edits']['kept'][0]['original_start'],22)
  self.assertEqual(q['models'][0]['offset'],11)
  self.assertEqual(it.rebase(q,meta),q);self.assertEqual(p['audio'],'tmp')
 def test_wrapper_prepares_before_matching(self):
  from unittest.mock import patch
  from contextlib import contextmanager
  from autosync import run_job
  @contextmanager
  def prep(job,args):yield dict(job,source='trimmed-source')
  with patch('input_trims.prepare',prep),patch('autosync._run_job',return_value='done') as run:
   self.assertEqual(run_job(dict(source='original'),SimpleNamespace()),'done')
   self.assertEqual(run.call_args.args[0]['source'],'trimmed-source')

if __name__=='__main__':unittest.main()
