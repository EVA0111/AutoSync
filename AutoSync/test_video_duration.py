import unittest,tempfile
from pathlib import Path
import visual_core as vc
class VideoDurationTests(unittest.TestCase):
 def test_b_frames_nonzero_start_and_vfr(self):
  self.assertAlmostEqual(vc.packet_video_span([{'pts_time':'10.1','duration_time':'.3'},{'pts_time':'10','duration_time':'.1'},{'pts_time':'10.4','duration_time':'.2'}]),.6)
 def test_missing_final_duration(self):
  self.assertAlmostEqual(vc.packet_video_span([{'pts_time':str(t)} for t in [2,2.04,2.08]]),.12)
 def test_invalid_timestamps_fail(self):
  for packets in [[],[{}],[{'pts_time':'NaN'}]]:
   with self.assertRaises(RuntimeError):vc.packet_video_span(packets)
 def test_single_packet_duration(self):
  self.assertAlmostEqual(vc.packet_video_span([{'pts_time':'1','duration_time':'.1'}]),.1)
 def test_other_tracks_do_not_extend_video(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'long-audio.mkv'
   vc.run([vc.binary('ffmpeg'),'-v','error','-f','lavfi','-i','color=size=32x32:rate=25:duration=2','-f','lavfi','-i','sine=duration=4','-map','0:v','-map','1:a','-vf','setpts=PTS+0.08/TB','-c:v','libx264','-bf','2','-c:a','pcm_s16le',str(p)])
   self.assertGreater(float(vc.probe(p)['format']['duration']),3.9)
   self.assertAlmostEqual(vc.video_duration(p),2.,places=3)
   from pcm_audio import PCMCache
   audio=Path(d)/'short.wav';vc.run([vc.binary('ffmpeg'),'-v','error','-f','lavfi','-i','sine=duration=2.08','-c:a','pcm_s16le',str(audio)])
   pcm=PCMCache(d,1);pcm.cut(audio,0,.08,vc.video_duration(p),Path(d)/'cut.f32')
   self.assertEqual((Path(d)/'cut.f32').stat().st_size,2*48000*4)
   with self.assertRaises(RuntimeError):pcm.cut(audio,0,.08,4.,Path(d)/'bad.f32')
if __name__=='__main__':unittest.main()
