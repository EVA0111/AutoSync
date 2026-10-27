import json,tempfile,unittest
from pathlib import Path
from subtitle_batch import run_batch
class SubtitleBatchTests(unittest.TestCase):
 def test_batch_runs_pairs_and_reports_individual_failures(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'source.srt';ref=root/'ref.srt';bad=root/'bad.srt'
   lines=['Please close the large window','We are leaving tomorrow morning','The garden is behind the house','You should read this interesting letter','Everyone is ready for the journey']
   def text(shift):return ''.join(f'{i+1}\n00:00:{5+i*10+shift:02},000 --> 00:00:{7+i*10+shift:02},000\n{t}\n\n' for i,t in enumerate(lines))
   source.write_text(text(0));ref.write_text(text(2));bad.write_text('not a subtitle')
   job={'values':{'mode':'reference','out':str(root/'out')},'rows':[{'subtitle':str(source),'reference_subtitle':str(ref)},{'subtitle':str(bad),'reference_subtitle':str(ref)}],'reviewed':True}
   self.assertEqual(run_batch(job),2);report=json.loads((root/'out/batch_report.json').read_text());self.assertEqual([r['status'] for r in report],['complete','failed']);self.assertIn('00:00:07,000',(Path(report[0]['out'])/'synced.srt').read_text());self.assertRaises(ValueError,run_batch,job)
 def test_requires_review_before_writing(self):
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'out';self.assertRaises(ValueError,run_batch,{'values':{'out':str(out)},'rows':[{}],'reviewed':False});self.assertFalse(out.exists())

 def test_combined_queue_runs_audio_then_subtitles(self):
  from unittest.mock import patch
  from desktop_bridge import run_request
  with tempfile.TemporaryDirectory() as d:
   calls=[]
   with patch('desktop_bridge.build_command',return_value=(['audio-engine'],Path(d))),patch('desktop_bridge.subprocess.call',side_effect=lambda *a,**k:calls.append('audio') or 0),patch('subtitle_sync.run',side_effect=lambda args:calls.append('subtitles') or 0):
    self.assertEqual(run_request({'task':'Queue','jobs':[{'task':'Single episode','values':{}},{'task':'Subtitles','values':{'mode':'reference'}}]}),0)
   self.assertEqual(calls,['audio','subtitles'])
