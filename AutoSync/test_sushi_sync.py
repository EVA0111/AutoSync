import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from subtitle_sync import parser
from sushi_sync import run_sushi,read_timings,timed_wave
from subtitle_formats import Document
class SushiTests(unittest.TestCase):
 def test_adapter_uses_selected_tracks_and_keeps_ass_payload(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);src=root/'in.ass';src.write_text('[Script Info]\nPlayResX: 640\n[Events]\nFormat: Layer, Start, End, Style, Text\nDialogue: 2,0:00:01.00,0:00:03.00,Sign,{\\pos(30,40)\\t(0,500,\\fscx120)}مرحبا\n',encoding='utf-8')
   exe=root/'sushi.exe';exe.write_bytes(b'fixture');out=root/'job';out.mkdir()
   args=parser().parse_args(['--mode','sushi','--subtitle',str(src),'--source-video','source.mkv','--target-media','target.mkv','--source-audio-track','1','--audio-track','2'])
   def factory(cmd,**kwargs):
    self.assertEqual(cmd[cmd.index('--src')+1],str(out/'sushi-source.wav'));self.assertIn('--chapters',cmd)
    Path(cmd[cmd.index('--output')+1]).write_text('1\n00:00:03,000 --> 00:00:05,000\nAutoSync cue 000001\n',encoding='utf-8')
    class Child:
     stdout=io.StringIO('Sushi matching finished\n')
     def wait(self):return 0
    return Child()
   with patch('sushi_sync.timed_wave') as wave:
    self.assertEqual(run_sushi(args,src,out,exe,factory),0)
    self.assertEqual(wave.call_args_list[0].args[1],1);self.assertEqual(wave.call_args_list[1].args[1],2)
   text=(out/'DRAFT-review-required.ass').read_text();self.assertIn('0:00:03.00,0:00:05.00',text);self.assertIn(r'{\pos(30,40)\t(0,500,\fscx120)}مرحبا',text);self.assertTrue(json.loads((out/'subtitle_report.json').read_text())['needs_review'])
 def test_missing_cues_are_not_silently_dropped(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'out.srt';p.write_text('1\n00:00:01,000 --> 00:00:03,000\nAutoSync cue 000002\n');cues=Document(p).cues
   self.assertRaises(ValueError,read_timings,p,cues)
 def test_decoder_keeps_selected_track_offset(self):
  with tempfile.TemporaryDirectory() as td:
   media=Path(td)/'video.mkv';media.touch();info={'streams':[{'codec_type':'video','start_time':'0'},{'codec_type':'audio','start_time':'0'},{'codec_type':'audio','start_time':'0.250'}]}
   with patch('sushi_sync.vc.probe',return_value=info),patch('sushi_sync.vc.binary',return_value='ffmpeg'),patch('sushi_sync.vc.run') as run:
    timed_wave(str(media),1,Path(td)/'out.wav');args=run.call_args.args[0];self.assertEqual(args[args.index('-map')+1],'0:a:1');self.assertIn('adelay=250.000000',args[args.index('-af')+1])
