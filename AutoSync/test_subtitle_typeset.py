"""Frame-accurate typesetting placement (subtitle_typeset)."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from subtitle_formats import Document
from subtitle_mapping import Section, TimingMap
from subtitle_typeset import FrameGrid, Placer, plan_map, rebase_ass

NTSC_FILM = 24000 / 1001


def shown(start, end, grid, frames=2000):
    """Frames a renderer shows for a line: start <= pts < end."""
    pts = grid.origin + np.arange(frames) / grid.fps
    return np.flatnonzero((pts >= start - 1e-9) & (pts < end - 1e-9))


class Grid(unittest.TestCase):
    def test_ass_time_lands_inside_its_frame(self):
        for fps in (NTSC_FILM, 25., 30000 / 1001, 60.):
            g = FrameGrid(fps)
            for n in range(1, 3000):
                t = g.ass_time(n)
                self.assertTrue(g.time(n - 1) < t <= g.time(n) + 1e-9, (fps, n, t))

    def test_line_shows_exactly_its_frames(self):
        g = FrameGrid(NTSC_FILM, origin=.0417)
        for a, b in [(10, 11), (100, 148), (1001, 1002)]:
            self.assertEqual(shown(g.ass_time(a), g.ass_time(b), g).tolist(), list(range(a, b)))


def identity(offset=0., scale=1., lo=0., hi=1e5, evidence='visual'):
    return TimingMap([Section(lo, hi, scale, offset, [])], evidence)


class Placement(unittest.TestCase):
    def test_same_picture_after_offset_and_pal_speedup(self):
        src, tgt = FrameGrid(25.), FrameGrid(NTSC_FILM)
        r = 25 / NTSC_FILM  # source runs faster: target seconds per source second
        placer = Placer(identity(offset=2.5, scale=r), src, tgt)
        for k0, k1 in [(250, 300), (1234, 1240), (4000, 4001)]:
            (p,) = placer.place(src.time(k0), src.time(k1))
            frames = shown(p.start, p.end, tgt, 8000)
            # Every frame shown on the target shows a source frame the line covered.
            back = [src.frame_at((tgt.mid(n) - 2.5) / r) for n in frames]
            self.assertEqual(back[0], k0)
            self.assertEqual(back[-1], k1 - 1)

    def test_edge_on_a_cut_snaps_to_the_target_cut(self):
        src = FrameGrid(25., cuts=np.array([400 / 25]))
        # The map is 30 ms late at the cut; the target cut is the truth.
        tgt = FrameGrid(25., cuts=np.array([400 / 25 + 1.]))
        placer = Placer(identity(offset=1.03), src, tgt)
        (p,) = placer.place(src.time(400), src.time(450))
        self.assertEqual(shown(p.start, p.end, tgt, 2000)[0], 425)
        # A start that is not on a source cut is not moved.
        (p,) = placer.place(src.time(410), src.time(450))
        self.assertEqual(shown(p.start, p.end, tgt, 2000)[0], 436)

    def test_cut_times_rounded_to_milliseconds(self):
        # MKV stores 307/23.976 = 12.80462 s as 12.804 s: still frame 307.
        fps = NTSC_FILM
        src = FrameGrid(fps, cuts=np.array([int(307 / fps * 1000) / 1000]))
        tgt = FrameGrid(fps, cuts=np.array([int(307 / fps * 1000) / 1000]))
        (p,) = Placer(identity(), src, tgt).place(src.time(307), src.time(330))
        self.assertEqual(shown(p.start, p.end, tgt, 2000)[0], 307)

    def test_line_across_an_edit_is_split(self):
        # source 0-10 s -> target 0-10 s; source 12-20 s -> target 10-18 s (2 s removed)
        m = TimingMap([Section(0, 10, 1, 0, []), Section(12, 20, 1, -2, [])], 'visual')
        g = FrameGrid(25.)
        pieces = Placer(m, g, g).place(8., 14.)
        self.assertEqual(len(pieces), 2)
        self.assertAlmostEqual(pieces[0].start, 8., places=2); self.assertAlmostEqual(pieces[0].end, 10., places=2)
        self.assertAlmostEqual(pieces[1].start, 10., places=2); self.assertAlmostEqual(pieces[1].end, 12., places=2)
        self.assertAlmostEqual(pieces[1].skip_ms, 4000, delta=1)
        self.assertTrue(pieces[0].keep_in and not pieces[0].keep_out)
        self.assertTrue(pieces[1].keep_out and not pieces[1].keep_in)
        self.assertIn('review', pieces[0].quality)  # 2 s of the line has no target picture


class TimeBases(unittest.TestCase):
    def test_plan_maps_count_source_from_its_audio(self):
        # Source video starts 40 ms after its audio; the plan maps source AUDIO
        # time t to target picture time t. Source frame k shows container
        # 0.04 + k/25 = audio time 0.04 + k/25, so the target shows it at frame k+1.
        m = identity(); m.source_domain, m.target_domain = 'audio', 'picture'
        src, tgt = FrameGrid(25., origin=.04, audio_start=0.), FrameGrid(25.)
        (p,) = Placer(m, src, tgt).place(src.time(500), src.time(550))
        self.assertEqual(shown(p.start, p.end, tgt, 2000).tolist(), list(range(501, 551)))

    def test_container_maps_are_unchanged(self):
        src = tgt = FrameGrid(25., origin=.04)
        (p,) = Placer(identity(), src, tgt).place(src.time(500), src.time(550))
        self.assertEqual(shown(p.start, p.end, tgt, 2000).tolist(), list(range(500, 550)))


class SplitWithFloatNoise(unittest.TestCase):
    def test_section_end_a_hair_past_a_frame_keeps_the_first_piece(self):
        # Plan sections arrive with float noise: 10.00002 for a 10.00 s boundary.
        m = TimingMap([Section(0, 10.00002, 1, 0, []), Section(12.00002, 30, 1, -2, [])], 'visual')
        g = FrameGrid(25.)
        pieces = Placer(m, g, g).place(8., 14.)
        self.assertEqual(len(pieces), 2)
        self.assertEqual(shown(pieces[0].start, pieces[0].end, g).tolist(), list(range(200, 250)))
        self.assertEqual(shown(pieces[1].start, pieces[1].end, g).tolist(), list(range(250, 300)))


class Rebase(unittest.TestCase):
    def test_move_transform_and_fade(self):
        text = r'{\fad(200,300)\move(0,0,100,100,1000,3000)\t(500,1500,\frz10)}Sign'
        out, review = rebase_ass(text, 2000, keep_in=False, keep_out=True)
        self.assertIn(r'\fad(0,300)', out)
        self.assertIn(r'\move(50,50,100,100,0,1000)', out)
        self.assertIn(r'\t(0,1,\frz10)', out)  # finished before the piece: applied at once
        self.assertFalse(review)

    def test_partial_transform_and_karaoke_need_review(self):
        self.assertTrue(rebase_ass(r'{\t(1000,3000,\frz10)}x', 2000)[1])
        self.assertTrue(rebase_ass(r'{\k20}ka{\k30}ra', 100)[1])
        self.assertEqual(rebase_ass(r'{\k20}ka', 0), (r'{\k20}ka', False))

    def test_move_finished_becomes_pos(self):
        self.assertEqual(rebase_ass(r'{\move(1,2,3,4,0,500)}x', 800)[0], r'{\pos(3,4)}x')


ASS = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sign,Arial,40,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,8,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:08.00,0:00:14.00,Sign,,0,0,0,,{\\fad(200,200)\\pos(320,50)}Across the edit
Dialogue: 0,0:00:02.00,0:00:03.00,Sign,,0,0,0,,{\\pos(320,50)}Before
"""


class Writer(unittest.TestCase):
    def test_ass_split_writes_two_lines(self):
        m = TimingMap([Section(0, 10, 1, 0, []), Section(12, 20, 1, -2, [])], 'visual')
        g = FrameGrid(25.)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'in.ass'; p.write_text(ASS, encoding='utf-8')
            doc = Document(p)
            report = doc.write(Path(td) / 'out.ass', m, placer=Placer(m, g, g))
            out = (Path(td) / 'out.ass').read_text(encoding='utf-8')
        lines = [x for x in out.splitlines() if x.startswith('Dialogue:')]
        self.assertEqual(len(lines), 3)
        self.assertIn('0:00:08.00,0:00:10.00', lines[0]); self.assertIn(r'\fad(200,0)', lines[0])
        self.assertIn('0:00:10.00,0:00:12.00', lines[1]); self.assertIn(r'\fad(0,200)', lines[1])
        self.assertIn('0:00:02.00,0:00:03.00,Sign', lines[2])
        self.assertEqual(report[0]['pieces'], 2)


class PlanMap(unittest.TestCase):
    def plan(self, td, audio, segments):
        p = Path(td) / 'plan.json'
        p.write_text(json.dumps(dict(audio=audio, source_video='S.mkv', target_video='T.mkv', segments=segments)))
        return p

    def test_picture_plan_is_visual_evidence_and_drops_replays(self):
        segs = [dict(kind='audio', target_start=0, target_end=100, source_start=10, speed=1),
                dict(kind='reference', target_start=100, target_end=110),
                dict(kind='audio', target_start=110, target_end=115, source_start=50, speed=1),  # replayed
                dict(kind='audio', target_start=115, target_end=200, source_start=110, speed=1)]
        with tempfile.TemporaryDirectory() as td:
            m = plan_map(self.plan(td, 'S.mkv', segs))
            self.assertEqual(m.evidence, 'visual')
            self.assertEqual(len(m.sections), 2)
            self.assertAlmostEqual(m.interval(20, 20)[0], 10.)
            self.assertAlmostEqual(m.interval(150, 150)[0], 155.)
            # A join where the source ranges overlap by 11 ms keeps both pieces.
            jitter = [dict(kind='audio', target_start=0, target_end=25, source_start=86.512, speed=1),
                      dict(kind='audio', target_start=25, target_end=50, source_start=111.501, speed=1)]
            self.assertEqual(len(plan_map(self.plan(td, 'S.mkv', jitter)).sections), 2)
            other = plan_map(self.plan(td, 'dub.flac', segs[:1]))
            self.assertEqual(other.evidence, 'audio-plan')


if __name__ == '__main__':
    unittest.main()
