"""Censored / re-edited dubs (case 3: Arabic dub as source, Japanese original as target).

The dub removed six scenes (1.4-13.7 s) and re-cut others with 1-5 s of other
footage. Scenes are found from the picture timeline's plan, each gets a
restore / cut action on its segment, cuts are applied only at render time,
restored scenes match the dub's loudness, and a subtitle file covers them.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

import censorship
from video_edits import remove_missing


def seg(kind, a, b, src=None, **kw):
    s = dict(kind=kind, target_start=a, target_end=b, **kw)
    if kind == 'audio':
        s.update(source_start=src, speed=1.)
    return s


def episode():
    """Outer OP (target-only), dub, removed scene (dub shows 3 s of other footage), dub,
    a 2 s dub-only spot, dub, outer ED."""
    return dict(duration=100., segments=[
        seg('reference', 0, 10, picture_outer='outer_start'),
        seg('audio', 10, 40, 0.),
        seg('reference', 40, 50, picture_outer=None, verified_insert=True),
        seg('audio', 50, 70, 33.),          # dub resumes 3 s later: replaced with other footage
        seg('audio', 70, 90, 55.),          # 2 s skip: dub-only material
        seg('reference', 90, 100, picture_outer='outer_end'),
    ], review=[])


class Scenes(unittest.TestCase):
    def test_removed_scenes_get_the_action_and_outer_sections_are_kept(self):
        p = censorship.annotate(episode(), 'cut')
        actions = [s.get('censored_action') for s in p['segments']]
        self.assertEqual(actions, ['restore', None, 'cut', None, None, 'restore'])
        found = censorship.scenes(p)
        self.assertEqual([x['kind'] for x in found], ['removed', 'dub_only'])
        self.assertAlmostEqual(found[0]['length'], 10.)
        self.assertAlmostEqual(found[0]['dub_replacement_s'], 3.)
        self.assertAlmostEqual(found[1]['start'], 70.)
        self.assertAlmostEqual(found[1]['length'], 2.)
        self.assertTrue(any('removed by the dub' in line for line in censorship.report(p)))

    def test_cut_removes_only_scenes_marked_cut(self):
        p = censorship.annotate(episode(), 'cut')
        edited = remove_missing(p)
        self.assertEqual([(k['start'], k['end']) for k in edited['video_edits']['removed']], [(40, 50)])
        self.assertAlmostEqual(edited['duration'], 90.)
        p['segments'][2]['censored_action'] = 'restore'      # changed in Preview & Edit
        self.assertFalse(censorship.needs_cut(p))
        self.assertEqual(remove_missing(p)['video_edits']['removed'], [])

    def test_invalid_action_is_refused(self):
        with self.assertRaises(ValueError):
            censorship.annotate(episode(), 'mute')


class RestoredSubtitles(unittest.TestCase):
    def test_only_lines_inside_restored_scenes_at_output_time(self):
        with tempfile.TemporaryDirectory() as d:
            srt = Path(d) / 'original.srt'
            srt.write_text('1\n00:00:05,000 --> 00:00:06,000\nOpening line\n\n'
                           '2\n00:00:42,000 --> 00:00:44,000\nRestored line\n\n'
                           '3\n00:01:00,000 --> 00:01:01,000\nDubbed scene line\n\n', encoding='utf-8')
            p = censorship.annotate(episode(), 'restore')
            # A main-episode trim of 10 s: plan time 30 = original time 40.
            p['segments'] = [dict(s, target_start=s['target_start'] - 10, target_end=s['target_end'] - 10)
                             for s in p['segments'][1:5]]
            out, n = censorship.restored_subtitles(srt, p, d, original_shift=10.)
            self.assertEqual(n, 1)
            text = out.read_text(encoding='utf-8')
            self.assertIn('Restored line', text)
            self.assertIn('00:00:32,000 --> 00:00:34,000', text)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'needs ffmpeg')
class SmoothSwitch(unittest.TestCase):
    """A restored scene's original audio is matched to the dub's loudness and the
    language switch is faded, without changing durations."""
    def render(self, original_amp):
        import autosync
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            def tone(name, amp, seconds=30):
                subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                                f'sine=frequency=440:sample_rate=48000:duration={seconds}', '-af', f'volume={amp}',
                                '-ac', '2', str(d / name)], check=True)
                return str(d / name)
            dub, original = tone('dub.wav', .5), tone('orig.wav', original_amp)
            plan = dict(duration=12., audio=dub, audio_stream=0, reference=original, reference_stream=0,
                        segments=[seg('audio', 0, 4, 0.), seg('reference', 4, 8, picture_outer=None, verified_insert=True),
                                  seg('audio', 8, 12, 8.)], review=[])
            plan = censorship.annotate(plan, 'restore')
            out = d / 'out'; out.mkdir()
            flac = autosync.render(plan, out, False)
            x = np.frombuffer(subprocess.run(['ffmpeg', '-v', 'error', '-i', str(flac), '-f', 'f32le', '-ac', '1', '-'],
                                             stdout=subprocess.PIPE, check=True).stdout, np.float32)
            self.assertAlmostEqual(len(x) / 48000, 12., delta=.01)
            return lambda a, b: float(np.sqrt(np.mean(x[int(a * 48000):int(b * 48000)] ** 2)))

    def test_restored_scene_matches_dub_loudness(self):
        rms = self.render(.2)                                                 # 8 dB quieter
        self.assertAlmostEqual(rms(5, 7) / rms(1, 3), 1., delta=.05)
        # 25 ms fade at the switch: near-silent exactly at the join, full level 40 ms away.
        self.assertLess(rms(3.999, 4.001), .2 * rms(1, 3))
        self.assertGreater(rms(4.03, 4.05), .8 * rms(1, 3))

    def test_large_level_difference_is_matched(self):
        rms = self.render(.1)                                                 # 14 dB quieter (case 3: ~17 dB)
        self.assertAlmostEqual(rms(5, 7) / rms(1, 3), 1., delta=.05)

    def test_gain_never_exceeds_20_db(self):
        rms = self.render(.025)                                               # 26 dB quieter
        self.assertAlmostEqual(rms(5, 7) / rms(1, 3), .5, delta=.05)          # 10x = +20 dB at most


if __name__ == '__main__':
    unittest.main()


class DesktopOption(unittest.TestCase):
    """The main window's option reaches the engine, and conflicting choices are refused."""
    def values(self, d, **kw):
        from gui_config import FIELDS
        for name in ('s.mp4', 't.mp4', 'subs.srt'):
            (Path(d) / name).write_bytes(b'x')
        v = {k: dflt for k, _, dflt in FIELDS}
        v.update(source=str(Path(d) / 's.mp4'), target=str(Path(d) / 't.mp4'), audio='', reference='',
                 out=str(Path(d) / 'out'), mode='Sync full target audio', video_codec='h264', video_preset='veryfast',
                 audio_only=False, analyze_only=False, reference_fallback=False, remove_unmatched_video=False,
                 allow_uncertain_cuts=False, censored_dub='', restored_subtitles='')
        v.update(kw)
        return v

    def test_flags_are_passed(self):
        from gui_config import build_command
        with tempfile.TemporaryDirectory() as d:
            cmd, _ = build_command(self.values(d, censored_dub='restore', restored_subtitles=str(Path(d) / 'subs.srt')), 'Single episode')
            self.assertEqual(cmd[cmd.index('--censored-dub') + 1], 'restore')
            self.assertIn('--restored-subtitles', cmd)

    def test_conflicts_are_refused(self):
        from gui_config import build_command
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                build_command(self.values(d, censored_dub='cut', remove_unmatched_video=True), 'Single episode')
            with self.assertRaises(ValueError):
                build_command(self.values(d, restored_subtitles=str(Path(d) / 'subs.srt')), 'Single episode')
            with self.assertRaises(ValueError):
                build_command(self.values(d, censored_dub='mute'), 'Single episode')
