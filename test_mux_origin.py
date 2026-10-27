import unittest,tempfile
from pathlib import Path
import visual_core as vc
from main_episode import export_full_video
class MuxOrigin(unittest.TestCase):
 def test_video_and_synced_audio_share_zero(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);video=p/'input.mkv';audio=p/'audio.flac'
   vc.run([vc.binary('ffmpeg'),'-v','error','-f','lavfi','-i','color=size=32x32:rate=25:duration=2','-vf','setpts=PTS+0.08/TB','-c:v','libx264','-bf','0',str(video)])
   vc.run([vc.binary('ffmpeg'),'-v','error','-f','lavfi','-i','sine=duration=2','-c:a','flac',str(audio)])
   out=export_full_video({'target_video':str(video),'duration':2},audio,p)
   s=vc.probe(out)['streams'];self.assertAlmostEqual(float(s[0]['start_time']),float(s[1]['start_time']),places=3)
