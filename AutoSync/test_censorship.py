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



def recreate_episode():
    """episode() with the engine's findings: the 2 s dub-only spot is a 1.5 s freeze of
    target 68.0 s then 0.5 s of target 60.0-60.5 s; the dub replaced 52-54 s with a hold."""
    p = episode()
    p['target_video'] = 't.mkv'
    p['segments'][4]['dub_pictures'] = dict(source_length=2., pieces=[
        dict(at=-2., length=1.5, hold=True, sway=[-.5, .4]), dict(at=-10., length=.5, hold=False)])
    p['segments'][3]['dub_replaced'] = [dict(source=35., length=2., pieces=[dict(rel=-1., length=2., hold=True)])]
    return p


class Recreate(unittest.TestCase):
    """Censored-dub "recreate": the dub's own edit, rebuilt from the original's pictures."""
    def test_removed_scenes_are_cut_and_dub_material_is_rebuilt(self):
        p = censorship.annotate(recreate_episode(), 'recreate')
        self.assertEqual(p['segments'][2]['censored_action'], 'cut')
        self.assertTrue(censorship.needs_cut(p))
        found = {x['kind']: x for x in censorship.scenes(p)}
        self.assertEqual(found['dub_only']['action'], 'recreate')
        self.assertEqual(found['replaced']['action'], 'recreate')
        self.assertAlmostEqual(found['replaced']['start'], 52.)
        self.assertTrue(any('rebuilt from held' in line for line in censorship.report(p)))
        edited = remove_missing(p)
        # 10 s removed scene cut, 2 s of dub-only material added: every dub second plays.
        self.assertAlmostEqual(edited['duration'], 92.)
        audio = [s for s in edited['segments'] if s['kind'] == 'audio']
        for a, b in zip(audio, audio[1:]):
            self.assertAlmostEqual(b['target_start'], a['target_end'])
        ends = [(a['source_start'] + (a['target_end'] - a['target_start']) * a['speed'], b['source_start'])
                for a, b in zip(audio, audio[1:])]
        self.assertTrue(all(abs(x - y) < 1e-6 for x, y in ends[1:]))   # only the cut scene's own jump remains
        rebuilt = [k for k in edited['video_edits']['kept'] if k.get('recreated')]
        self.assertEqual([k.get('hold') for k in rebuilt], [51., 68., None])
        self.assertAlmostEqual(rebuilt[0]['output_start'], 42.)     # replaced shot inside the dub's segment
        self.assertAlmostEqual(rebuilt[1]['output_start'], 60.)     # dub-only freeze before the dub resumes
        self.assertAlmostEqual(rebuilt[2]['output_start'], 61.5)
        self.assertAlmostEqual(rebuilt[2]['original_start'], 60.)

    def test_restore_and_cut_ignore_the_rebuild_data(self):
        for action, duration in (('restore', 100.), ('cut', 90.)):
            p = censorship.annotate(recreate_episode(), action)
            if action == 'cut':
                edited = remove_missing(p)
                self.assertAlmostEqual(edited['duration'], duration)
                self.assertFalse(any(k.get('recreated') for k in edited['video_edits']['kept']))
            self.assertEqual({x['action'] for x in censorship.scenes(p) if x['kind'] == 'dub_only'}, {'skip'})

    def test_trimmed_segment_is_not_rebuilt(self):
        p = recreate_episode()
        p['segments'][4].update(target_start=71., source_start=56.)   # its start moved: the skip no longer matches
        p = censorship.annotate(p, 'recreate')
        self.assertEqual([x['action'] for x in censorship.scenes(p) if x['kind'] == 'dub_only'], ['skip'])

    def test_export_graph_has_exact_frame_counts(self):
        import video_edits
        p = remove_missing(censorship.annotate(recreate_episode(), 'recreate'))
        kept = p['video_edits']['kept']
        kept.insert(3, dict(start=0., end=0., output_start=kept[3]['output_start'], recreated=True,
                            length=.01, hold=5.))          # rounds to no frame: left out
        old = video_edits.target_picture
        video_edits.target_picture = lambda path: (64, 48, '1/1', '24000/1001')
        try:
            _, graph = video_edits.media_graph(p)
        finally:
            video_edits.target_picture = old
        import re
        self.assertNotIn('trim=start=4.979', graph)
        counts = [int(x) for x in re.findall(r'trim=end_frame=(\d+)', graph)]
        self.assertEqual(sum(counts), round(92. * 24000 / 1001))
        self.assertIn('setpts=N/(24000/1001)/TB[v]', graph)
        self.assertIn(',reverse,', graph)                  # the freeze plays its shot back and forth
        frozen = remove_missing(censorship.annotate(recreate_episode(), 'recreate', 'freeze'))
        self.assertFalse(any(k.get('sway') for k in frozen['video_edits']['kept']))



class EditorMotionFill(unittest.TestCase):
    """Preview & Edit "Fill motion" ranges, laid on after censored-dub cuts and rebuilds."""
    def test_fill_lands_on_the_cut_output_and_keeps_the_sound(self):
        from autosync import censored_render_plan
        p = censorship.annotate(recreate_episode(), 'recreate')
        p['video_edits'] = dict(original_target_duration=100., removed=[], kept=[
            dict(start=0., end=60., output_start=0., original_start=0., original_end=60.),
            dict(start=60., end=64., output_start=60., original_start=58., original_end=62., fill='motion', hold=58.),
            dict(start=64., end=100., output_start=64., original_start=64., original_end=100.)])
        with tempfile.TemporaryDirectory() as d:
            r = censored_render_plan(p, d)
        self.assertAlmostEqual(r['duration'], 92.)                       # the cut and the rebuild still apply
        fill = [k for k in r['video_edits']['kept'] if k.get('fill')]
        self.assertEqual(len(fill), 1)
        # Analysed 60-64 s sits after the 10 s cut and the 2 s rebuilt replacement offset: output 50-54 s.
        self.assertAlmostEqual(fill[0]['output_start'], 50.)
        self.assertAlmostEqual(fill[0]['end'] - fill[0]['start'], 4.)
        self.assertAlmostEqual(fill[0]['hold'], 58.)
        audio = [s for s in r['segments'] if s['kind'] == 'audio']
        plain = [s for s in remove_missing(censorship.annotate(recreate_episode(), 'recreate'))['segments'] if s['kind'] == 'audio']
        self.assertEqual([(s['target_start'], s['source_start']) for s in audio], [(s['target_start'], s['source_start']) for s in plain])

    def test_fill_motion_stops_at_a_camera_move(self):
        import video_edits
        p = dict(target_video='t.mkv', video_edits=dict(kept=[
            dict(start=0., end=2., output_start=0., original_start=5., original_end=7., fill='motion', hold=5.)]))
        import picture_timeline as pt
        old = pt.stream_info, pt.fine_decode
        frames = np.zeros((31, pt.FH, pt.FW), np.uint8); frames[:, :, ::7] = 200
        frames[16:] = np.roll(frames[16:], 3, axis=2)                     # a camera move right after the frame
        pt.stream_info = lambda path, ffprobe=None: dict(origin=0., start=0., file_start=0.)
        pt.fine_decode = lambda *a, **k: frames
        try:
            got = video_edits.fill_pieces(p)
        finally:
            pt.stream_info, pt.fine_decode = old
        self.assertTrue(got[0]['recreated'])
        self.assertAlmostEqual(got[0]['length'], 2.)
        self.assertLessEqual(got[0].get('sway', [5., 5.])[1], 5.)          # stops where the camera move starts



class EditorBlackFill(unittest.TestCase):
    def test_black_fill_is_a_colour_source_with_exact_frames(self):
        import video_edits, re
        p = dict(target_video='t.mkv', duration=10., video_edits=dict(kept=[
            dict(start=0., end=4., output_start=0., original_start=0., original_end=4.),
            dict(start=4., end=6., output_start=4., original_start=4., original_end=6., fill='black', hold=4.),
            dict(start=6., end=10., output_start=6., original_start=6., original_end=10.)]))
        old = video_edits.target_picture
        video_edits.target_picture = lambda path: (64, 48, '1/1', '25/1')
        try:
            _, graph = video_edits.media_graph(p)
        finally:
            video_edits.target_picture = old
        self.assertIn('color=c=black:s=64x48', graph)
        self.assertEqual(sum(int(x) for x in re.findall(r'trim=end_frame=(\d+)', graph)), 250)


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
