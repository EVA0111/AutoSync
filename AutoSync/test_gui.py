import csv,tempfile,unittest
from pathlib import Path
from gui_config import build_command,FIELDS,MODES

class GUICommands(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.file=self.root/'日本語 source with spaces.mp4';self.file.touch()
        self.v={k:d for k,_,d in FIELDS}
        self.v.update(source=str(self.file),target=str(self.file),audio='',reference='',out=str(self.root/'out'),batch='',plan='',mode=list(MODES)[0],video_codec='h264',video_preset='veryfast')
        self.v.update({k:False for k in ['audio_only','analyze_only','reference_fallback','allow_uncertain_cuts']})
    def tearDown(self):self.tmp.cleanup()
    def test_modes_and_optional_embedded_audio(self):
        for mode,(flag,_) in MODES.items():
            self.v['mode']=mode;cmd,_=build_command(self.v,'Single episode')
            self.assertEqual(cmd[cmd.index('--audio')+1],str(self.file))
            self.assertEqual(cmd[cmd.index('--reference')+1],str(self.file))
            self.assertEqual('--main-only' in cmd,flag=='--main-only')
            self.assertEqual('--keep-target-op-ed' in cmd,flag=='--keep-target-op-ed')
    def test_reject_invalid_boundary_mode_and_existing_plan(self):
        self.v['main_start']='12'
        with self.assertRaises(ValueError):build_command(self.v,'Single episode')
        self.v['main_start']='';out=Path(self.v['out']);out.mkdir();(out/'plan.json').touch()
        with self.assertRaises(ValueError):build_command(self.v,'Single episode')
    def test_saved_plan_skips_input_validation(self):
        self.v.update(source='',target='',plan=str(self.file),video_codec='ffv1')
        cmd,_=build_command(self.v,'Saved plan');self.assertIn('--render-plan',cmd);self.assertNotIn('--audio',cmd);self.assertIn('ffv1',cmd)
    def test_batch_relative_paths_and_duplicates(self):
        path=self.root/'jobs.csv';self.v['batch']=str(path)
        def write(rows):
            with path.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=['source','target','audio','out']);w.writeheader();w.writerows(rows)
        row=dict(source=self.file.name,target=self.file.name,audio=self.file.name,out='episode1')
        write([row]);cmd,out=build_command(self.v,'Batch CSV');self.assertIn('--batch',cmd);self.assertEqual(out,self.root/'episode1')
        write([row,row])
        with self.assertRaises(ValueError):build_command(self.v,'Batch CSV')

    def test_desktop_bridge_renders_saved_plan(self):
        import json,subprocess,sys,shutil
        import numpy as np
        from scipy.io import wavfile
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):self.skipTest('FFmpeg unavailable')
        audio=self.root/'source.wav';wavfile.write(audio,48000,np.zeros((96000,2),np.float32))
        plan=self.root/'plan.json';plan.write_text(json.dumps(dict(audio=str(audio),audio_stream=0,duration=1,review=[],segments=[dict(kind='audio',target_start=0,target_end=1,source_start=0,speed=1)])))
        result=subprocess.run([sys.executable,str(Path(__file__).parent/'desktop_bridge.py')],input=json.dumps(dict(task='Saved plan',values=dict(plan=str(plan)))),text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('AUTOSYNC_OUTPUT=',result.stdout);self.assertTrue((self.root/'synced.flac').is_file())

if __name__=='__main__':unittest.main()
