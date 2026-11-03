"""Preview & Edit imported clips: rendered audio and exported picture."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np


def make(path, args):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', *args, str(path)], check=True)


def frame_rgb(path, t):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(t), '-i', str(path), '-frames:v', '1', '-vf', 'scale=8:6',
                          '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, 3).mean(axis=0)


def dominant_hz(path, t0, t1):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(t0), '-t', str(t1 - t0), '-i', str(path), '-ac', '1',
                          '-ar', '48000', '-f', 'f32le', '-'], stdout=subprocess.PIPE, check=True).stdout
    x = np.frombuffer(raw, np.float32)
    if not len(x) or np.abs(x).max() < 1e-4:
        return 0.
    return float(np.argmax(np.abs(np.fft.rfft(x))) * 48000 / len(x))


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg unavailable')
class ImportedClips(unittest.TestCase):
    def test_target_import_image_target(self):
        from autosync import render
        from video_edits import export_video
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            target, clip, still = td / 'target.mkv', td / 'clip.mp4', td / 'still.png'
            make(target, ['-f', 'lavfi', '-i', 'color=c=green:s=320x240:r=25:d=4', '-f', 'lavfi', '-i',
                          'sine=frequency=440:sample_rate=48000:duration=4', '-c:v', 'libx264', '-c:a', 'flac', '-shortest'])
            make(clip, ['-f', 'lavfi', '-i', 'color=c=red:s=640x360:r=30:d=3', '-f', 'lavfi', '-i',
                        'sine=frequency=880:sample_rate=44100:duration=3', '-c:v', 'libx264', '-c:a', 'aac', '-shortest'])
            make(still, ['-f', 'lavfi', '-i', 'color=c=blue:s=200x200', '-frames:v', '1'])
            plan = dict(
                audio=str(target), audio_stream=0, target_video=str(target), duration=5.5, review=[],
                segments=[dict(kind='audio', target_start=0, target_end=2, source_start=0, speed=1),
                          dict(kind='media', target_start=2, target_end=3.5, media=str(clip), media_start=.5, media_stream=0),
                          dict(kind='media', target_start=3.5, target_end=4.5, media=str(still), media_start=0, media_stream=None),
                          dict(kind='audio', target_start=4.5, target_end=5.5, source_start=3, speed=1)],
                video_edits=dict(original_target_duration=4, removed=[], kept=[
                    dict(start=0, end=2, output_start=0, original_start=0, original_end=2),
                    dict(start=2, end=3.5, output_start=2, media=str(clip), media_start=.5),
                    dict(start=3.5, end=4.5, output_start=3.5, media=str(still), media_start=0),
                    dict(start=4.5, end=5.5, output_start=4.5, original_start=3, original_end=4)]))
            out = td / 'out'; out.mkdir()
            audio = render(plan, out, False)
            video = export_video(plan, audio, out)
            dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0',
                                        str(video)], stdout=subprocess.PIPE, text=True).stdout)
            self.assertAlmostEqual(dur, 5.5, delta=.15)
            r, g, b = frame_rgb(video, 1.); self.assertGreater(g, r + 50)      # target (green)
            r, g, b = frame_rgb(video, 2.7); self.assertGreater(r, g + 50)     # imported clip (red, letterboxed)
            r, g, b = frame_rgb(video, 4.0); self.assertGreater(b, r + 30)     # still image (blue, pillarboxed)
            r, g, b = frame_rgb(video, 5.0); self.assertGreater(g, r + 50)     # back to target
            self.assertAlmostEqual(dominant_hz(video, .5, 1.5), 440, delta=10)
            self.assertAlmostEqual(dominant_hz(video, 2.2, 3.3), 880, delta=10)
            self.assertEqual(dominant_hz(video, 3.7, 4.3), 0.)                 # image: silence

    def test_missing_import_is_refused(self):
        from autosync import render
        plan = dict(audio='x', audio_stream=0, duration=1, review=[],
                    segments=[dict(kind='media', target_start=0, target_end=1, media='nope.mp4', media_stream=0)])
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError, 'missing'):
                render(plan, Path(td), False)


if __name__ == '__main__':
    unittest.main()
