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
   self.assertEqual(run_managed(request,runner),0);self.assertCountEqual([p.name for p in out.iterdir()],['episode01.synced.flac','episode01.alignment.json']);self.assertEqual(list(work.iterdir()),[])
   request.update(save_reports=True,reports_dir=str(reports));self.assertEqual(run_managed(request,runner),0);self.assertTrue((out/'episode01.synced (2).flac').exists());self.assertTrue(list(reports.glob('*/plan.json')));self.assertTrue(list(reports.glob('*/job-status.json')));self.assertFalse(list(reports.glob('*.wav')))
 def test_each_job_gets_its_own_report_folder_even_with_same_name(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);out=root/'out';reports=root/'AutoSync Reports'
   def runner(job):
    p=Path(job['values']['out']);p.mkdir()
    (p/'plan.json').write_text(json.dumps({'source':'example','status':1}))
    (p/'review.txt').write_text('unique '+job['values']['target'])
    (p/'synced.flac').write_bytes(b'audio')
    return 0
   jobs=[{'task':'Single episode','values':{'target':'EP01.mkv'}},
         {'task':'Single episode','values':{'target':'subdir/EP01.mkv'}}]
   request={'output_dir':str(out),'reports_dir':str(reports),'save_reports':True,'jobs':jobs}
   buf=io.StringIO()
   with contextlib.redirect_stdout(buf):self.assertEqual(run_managed(request,runner),0)
   results=[json.loads(line.split('=',1)[1]) for line in buf.getvalue().splitlines() if line.startswith('AUTOSYNC_RESULT=')]
   self.assertEqual(len(results),2)
   self.assertEqual(len({entry['reports_folder'] for entry in results}),2)
   self.assertTrue(all(Path(entry['reports_folder']).is_dir() for entry in results))
   folders=sorted(p for p in reports.iterdir() if p.is_dir())
   self.assertEqual(len(folders),2)
   self.assertNotEqual(folders[0].name,folders[1].name)
   for p in folders:
    self.assertTrue((p/'plan.json').is_file())
    self.assertTrue((p/'review.txt').is_file())
    self.assertEqual(json.loads((p/'job-status.json').read_text())['status'],'complete')
   self.assertEqual(len(list(reports.glob('*.summary.txt'))),1)
   self.assertEqual(run_managed(request,runner),0)
   self.assertEqual(len([p for p in reports.iterdir() if p.is_dir()]),4)

 def test_failed_job_still_gets_separate_status_folder(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)
   def runner(job):
    p=Path(job['values']['out']);p.mkdir();(p/'error.log').write_text('bad input')
    return 1
   request={'output_dir':str(root/'out'),'reports_dir':str(root/'AutoSync Reports'),
            'save_reports':True,'jobs':[{'task':'Single episode','values':{'target':'failed.mp4'}}]}
   self.assertEqual(run_managed(request,runner),2)
   folders=[p for p in (root/'AutoSync Reports').iterdir() if p.is_dir()]
   self.assertEqual(len(folders),1)
   self.assertTrue((folders[0]/'error.log').is_file())
   self.assertEqual(json.loads((folders[0]/'job-status.json').read_text())['status'],'failed')

 def test_analysis_only_persists_editable_plan_in_user_folder(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);out=root/'wherever'/'I choose'
   def runner(job):
    p=Path(job['values']['out']);p.mkdir()
    (p/'plan.json').write_text(json.dumps({'audio':'original.flac','segments':[]}))
    return 0
   request={'output_dir':str(out),'jobs':[{'task':'Single episode','values':{'target':'case1.mp4','analyze_only':True}}]}
   buf=io.StringIO()
   with contextlib.redirect_stdout(buf):
    result=run_managed(request,runner)
   self.assertEqual(result,0)
   self.assertTrue((out/'case1.alignment.json').exists())
   self.assertIn('AUTOSYNC_PLAN=',buf.getvalue())
   self.assertFalse(list(out.glob('*.flac')))

 def test_two_analysis_runs_do_not_overwrite_previous_plan(self):
  with tempfile.TemporaryDirectory() as td:
   out=Path(td)/'other-drive';out.mkdir()
   def runner(job):
    p=Path(job['values']['out']);p.mkdir()
    (p/'plan.json').write_text('{}')
    return 0
   request={'output_dir':str(out),'jobs':[{'task':'Single episode','values':{'target':'same.mp4','analyze_only':True}}]}
   self.assertEqual(run_managed(request,runner),0)
   self.assertEqual(run_managed(request,runner),0)
   self.assertTrue((out/'same.alignment.json').exists())
   self.assertTrue((out/'same.alignment (2).json').exists())
 def test_missing_destination_and_nested_reports_block_before_work(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);jobs=[{'task':'Single episode','values':{}}]
   self.assertRaisesRegex(ValueError,'specify',run_managed,{'jobs':jobs},lambda _:0)
   self.assertRaisesRegex(ValueError,'cannot be saved inside',run_managed,{'jobs':jobs,'output_dir':str(root/'reports'/'output'),'save_reports':True,'reports_dir':str(root/'reports')},lambda _:0)
   def runner(job):
    p=Path(job['values']['out']);p.mkdir();return 0
   self.assertEqual(run_managed({'jobs':jobs,'output_dir':str(root),'save_reports':True,'reports_dir':str(root/'AutoSync Reports')},runner),0)
   self.assertTrue((root/'AutoSync Reports').is_dir())
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
