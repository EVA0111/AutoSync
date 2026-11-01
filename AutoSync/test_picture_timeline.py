"""Dense picture timeline solver on synthetic frame features.

Covers the behaviours measured on the media matrix: source-only cuts (cases
1-7), target-only footage (case 3), recaps reusing far footage (case 2),
static spans between joins (case 1), short jitter runs, tiny join pieces
(case 4) and target-only openings (cases 2, 5, 6).
"""
import unittest
import numpy as np
import picture_timeline as pt

FPS = pt.FPS


def unique_frames(n, seed):
    rng = np.random.default_rng(seed)
    # Temporally smooth, like video: each frame mixes its neighbours.
    x = rng.normal(size=(n + 8, 384)).astype(np.float32)
    x = sum(x[k:k + n] for k in range(8))
    x -= x.mean(axis=1, keepdims=True)
    return x / np.linalg.norm(x, axis=1, keepdims=True)


def solve(FS, FT):
    return pt.from_features(FS, np.full(len(FS), 20.), FT, np.full(len(FT), 20.), dict(score=1.),
                            dict(start=0.), dict(start=0.), progress=lambda *_: None, ratio=1.)


def plan(tl, duration):
    return pt.to_plan_segments(tl, duration, len(tl.diagnostics['FS']) / FPS, 0.)[0]


class Edition(unittest.TestCase):
    """target = source[0:60s] + 10s target-only + source[60:100s] + source[108:180s]"""
    @classmethod
    def setUpClass(cls):
        S = unique_frames(180 * FPS, 1)
        extra = unique_frames(10 * FPS, 2)
        T = np.vstack([S[:60 * FPS], extra, S[60 * FPS:100 * FPS], S[108 * FPS:]])
        cls.duration = len(T) / FPS
        cls.segments = plan(solve(S, T), cls.duration)

    def test_contiguous_cover(self):
        segs = self.segments
        self.assertAlmostEqual(segs[0]['target_start'], 0.)
        self.assertAlmostEqual(segs[-1]['target_end'], self.duration)
        for a, b in zip(segs, segs[1:]):
            self.assertAlmostEqual(a['target_end'], b['target_start'])

    def test_insert_is_target_audio_and_cut_is_skipped(self):
        refs = [s for s in self.segments if s['kind'] == 'reference']
        self.assertEqual(len(refs), 1)
        self.assertTrue(refs[0]['verified_insert'])
        self.assertAlmostEqual(refs[0]['target_start'], 60., delta=.3)
        self.assertAlmostEqual(refs[0]['target_end'], 70., delta=.3)
        audio = [s for s in self.segments if s['kind'] == 'audio']
        # Every audio sample maps to the source frame actually shown.
        for t, want in [(30., 30.), (80., 70.), (105., 95.), (150., 148.)]:
            seg = next(s for s in audio if s['target_start'] <= t < s['target_end'])
            self.assertAlmostEqual(seg['source_start'] + (t - seg['target_start']), want, delta=.05)
        cut = next(s for s in audio if s['target_start'] > 100)
        self.assertAlmostEqual(cut['target_start'], 110., delta=.3)


class Recap(unittest.TestCase):
    def test_recap_of_later_footage_is_not_replayed(self):
        S = unique_frames(200 * FPS, 3)
        T = np.vstack([S[150 * FPS:165 * FPS], S[:140 * FPS]])     # 15 s 'previously' from the end
        segs = plan(solve(S, T), len(T) / FPS)
        self.assertEqual(segs[0]['kind'], 'reference')
        self.assertAlmostEqual(segs[0]['target_end'], 15., delta=.6)
        from continuity_guard import source_rewinds
        self.assertEqual(source_rewinds(segs), [])


class StaticSpan(unittest.TestCase):
    def test_cut_inside_a_static_shot_is_bounded(self):
        S = unique_frames(120 * FPS, 4)
        S[50 * FPS:58 * FPS] = S[50 * FPS]                # 8 s static shot in the source
        T = np.vstack([S[:54 * FPS], S[55 * FPS:]])       # 1 s cut inside it
        tl = solve(S, T)
        segs, _, notes = pt.to_plan_segments(tl, len(T) / FPS, 120., 0.)
        audio = [s for s in segs if s['kind'] == 'audio']
        self.assertEqual(len(audio), 2)
        self.assertTrue(50 <= audio[1]['target_start'] <= 57.1)
        self.assertAlmostEqual(audio[1]['source_start'] - audio[1]['target_start'], 1., delta=.05)


class Pieces(unittest.TestCase):
    def test_jitter_runs_are_absorbed_but_real_steps_kept(self):
        def m(first, last, off, n):
            return dict(kind='match', first=first, last=last, offset=off, samples=n, strong=n)
        secs = [m(0, 1000, 10., 80), m(1012, 1100, 13., 8), m(1112, 3000, 10., 150), m(3012, 5000, 15., 160)]
        out = pt.absorb_jitter(secs)
        self.assertEqual([round(x['offset']) for x in out], [10, 15])

    def test_monotone_chain_marks_reused_runs(self):
        def m(first, last, off, n):
            return dict(kind='match', first=first, last=last, offset=off, samples=n, strong=n)
        secs = [m(0, 300, 4000., 30), m(310, 5000, -200., 400)]
        out = pt.monotone_chain(secs, 1.)
        self.assertEqual(out[0]['kind'], 'none'); self.assertTrue(out[0]['reused'])
        self.assertEqual(out[1]['kind'], 'match')


if __name__ == '__main__':
    unittest.main()


class FrameOrigin(unittest.TestCase):
    """Decoded frame k sits at FILE origin + k/fps (ffmpeg pads the first picture
    back to the file start). Measured on the media matrix: assuming the video
    stream start instead took source audio 40-104 ms late (cases 1, 2, 6), and
    the evaluator, sharing the assumption, could not see it."""
    def test_target_shift_moves_segments_but_not_the_mapping(self):
        S = unique_frames(120 * FPS, 5)
        tl = solve(S, S[10 * FPS:110 * FPS])
        base = pt.to_plan_segments(tl, 100., 120., 0.)[0]
        moved = pt.to_plan_segments(tl, 100., 120., 0., target_shift=-.036)[0]
        a = next(s for s in base if s['kind'] == 'audio'); b = next(s for s in moved if s['kind'] == 'audio')
        # Same picture => same source time at the same frame; video time differs by the shift.
        t = 50.
        sa = a['source_start'] + (t - a['target_start']) * a['speed']
        sb = b['source_start'] + (t - .036 - b['target_start']) * b['speed']
        self.assertAlmostEqual(sa, sb, delta=.002)
        self.assertAlmostEqual(moved[0]['target_start'], 0.)
        self.assertAlmostEqual(moved[-1]['target_end'], 100.)
