import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from pcm_audio import PCMCache
from main_episode import keep_target_outer

class PCMCutsTests(unittest.TestCase):
    def test_decode_once_and_exact_sample_slices(self):
        data=np.arange(48000*5*2,dtype=np.float32).reshape(-1,2)
        calls=[]
        def decode(cmd):calls.append(cmd);data.tofile(cmd[-1]);return b''
        with tempfile.TemporaryDirectory() as td,patch('pcm_audio.vc.run',side_effect=decode),patch('pcm_audio.vc.binary',return_value='ffmpeg'):
            cache=PCMCache(td,2);out=Path(td)/'cut.f32'
            for start in [2.125,.125]:
                cache.cut('source.wmv',0,start,1.25,out)
                np.testing.assert_array_equal(np.fromfile(out,np.float32).reshape(-1,2),data[round(start*48000):round((start+1.25)*48000)])
            self.assertEqual(len(calls),1);self.assertNotIn('-ss',calls[0]);self.assertNotIn('-t',calls[0])
            with self.assertRaisesRegex(RuntimeError,'ends too early'):cache.cut('source.wmv',0,4.5,1.,out)
    def test_unity_speed_preserves_audio_samples(self):
        import shutil,subprocess
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):self.skipTest('FFmpeg unavailable')
        from scipy.io import wavfile
        from autosync import render
        data=np.random.default_rng(42).uniform(-.1,.1,(96000,2)).astype(np.float32)
        with tempfile.TemporaryDirectory() as td:
            td=Path(td);src=td/'source.wav';wavfile.write(src,48000,data)
            p=dict(audio=str(src),audio_stream=0,duration=1,segments=[dict(kind='audio',target_start=0,target_end=1,source_start=.125,speed=1)],review=[])
            output=render(p,td,False)
            raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(output),'-f','f32le','-'])
            actual=np.frombuffer(raw,np.float32).reshape(-1,2)
            np.testing.assert_allclose(actual,data[6000:54000],atol=2e-7,rtol=0)

    def test_target_tail_and_pcm_join_preserve_timing(self):
        import shutil,subprocess
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):self.skipTest('FFmpeg unavailable')
        from scipy.io import wavfile
        from autosync import render
        data=np.random.default_rng(7).uniform(-.1,.1,(72000-200,2)).astype(np.float32)
        with tempfile.TemporaryDirectory() as td:
            td=Path(td);src=td/'source.wav';wavfile.write(src,48000,data)
            p=dict(audio=str(src),audio_stream=0,target_video=str(src),duration=1.5,segments=[dict(kind='audio',target_start=0,target_end=.50313,source_start=0,speed=1),dict(kind='target_outer',target_start=.50313,target_end=1.5)],review=[])
            output=render(p,td,False)
            raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(output),'-f','f32le','-'])
            actual=np.frombuffer(raw,np.float32).reshape(-1,2)
            self.assertEqual(len(actual),72000)
            np.testing.assert_allclose(actual[30000:60000],data[30000:60000],atol=2e-7,rtol=0)
            self.assertTrue(np.all(actual[-200:]==0))

    def test_outer_mode_keeps_full_timeline(self):
        plan=dict(duration=100,reference_shift=0,target_video='target.mkv',models=[],segments=[dict(kind='audio',target_start=0,target_end=100,source_start=5,speed=1)],review=[dict(start=40,end=45)])
        probe=dict(streams=[dict(codec_type='video'),dict(codec_type='audio')])
        with patch('main_episode.vc.probe',return_value=probe):
            p=keep_target_outer(plan,dict(target_start=10,target_end=90))
        self.assertEqual(p['duration'],100);self.assertNotIn('main_trim',p)
        self.assertEqual([(s['kind'],s['target_start'],s['target_end']) for s in p['segments']],[('target_outer',0,10),('audio',10,90),('target_outer',90,100)])
        self.assertEqual(p['segments'][1]['source_start'],15)
        self.assertEqual(p['review'],plan['review']);self.assertEqual(plan['segments'][0]['target_start'],0)

if __name__=='__main__':unittest.main()
