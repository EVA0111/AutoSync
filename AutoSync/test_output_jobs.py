import json,tempfile,unittest,io,contextlib
from pathlib import Path
from output_jobs import run_managed,publish
from desktop_bridge import run_request
class OutputTests(unittest.TestCase):
 def test_audio_media_flat_reports_optional_and_duplicates_safe(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);out=root/'media';reports=root/'reports';work=root/'work';work.mkdir()
   def runner(job):
    p=Path(job['values']['out']);p.mkdir();(p/'synced.flac').write_bytes(b'media');(p/'plan.json').write_text(json.dumps({'audio':'original.flac'}));(p/'scratch.wav').write_bytes(b'cache');return 0
   request={'output_dir':str(out),'work_root':str(work),'jobs':[{'task':'Single episode','values':{'target':'episode01.mkv'}}]}
   self.assertEqual(run_managed(request,runner),0);self.assertEqual([p.name for p in out.iterdir()],['episode01.synced.flac']);self.assertEqual(list(work.iterdir()),[])
   request.update(save_reports=True,reports_dir=str(reports));self.assertEqual(run_managed(request,runner),0);self.assertTrue((out/'episode01.synced (2).flac').exists());self.assertTrue(list(reports.glob('*.plan.json')));self.assertFalse(list(reports.glob('*.wav')))
 def test_missing_destination_and_nested_reports_block_before_work(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);jobs=[{'task':'Single episode','values':{}}]
   self.assertRaisesRegex(ValueError,'specify',run_managed,{'jobs':jobs},lambda _:0)
   self.assertRaisesRegex(ValueError,'separate',run_managed,{'jobs':jobs,'output_dir':str(root),'save_reports':True,'reports_dir':str(root/'reports')},lambda _:0)
 def test_real_subtitle_one_file_uses_flat_output_and_progress(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);src=root/'Episode01.srt';ref=root/'reference.srt'
   lines=['Please close the large window','We are leaving tomorrow morning','The garden is behind the house','You should read this interesting letter','Everyone is ready for the journey']
   def txt(shift):return ''.join(f'{i+1}\n00:00:{5+i*10+shift:02},000 --> 00:00:{7+i*10+shift:02},000\n{t}\n\n' for i,t in enumerate(lines))
   src.write_text(txt(0));ref.write_text(txt(2));out=root/'out';buf=io.StringIO()
   with contextlib.redirect_stdout(buf):code=run_managed({'output_dir':str(out),'jobs':[{'task':'Subtitle batch','reviewed':True,'values':{'mode':'reference'},'rows':[{'subtitle':str(src),'reference_subtitle':str(ref)}]}]},run_request)
   self.assertEqual(code,0);self.assertEqual([p.name for p in out.iterdir()],['Episode01.synced.srt']);self.assertIn('00:00:07,000',(out/'Episode01.synced.srt').read_text());self.assertIn('AUTOSYNC_PROGRESS=',buf.getvalue())
 def test_drafts_stay_named_even_without_reports(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);out=root/'out'
   def runner(job):
    p=Path(job['values']['out']);p.mkdir();dest=p/'DRAFT-review-required.ass';dest.write_text('draft');(p/'subtitle_report.json').write_text(json.dumps({'output':str(dest),'needs_review':True}));return 0
   self.assertEqual(run_managed({'output_dir':str(out),'jobs':[{'task':'Subtitles','values':{'subtitle':'ep01.ass'}}]},runner),0);self.assertTrue((out/'ep01.DRAFT-review-required.ass').is_file())
