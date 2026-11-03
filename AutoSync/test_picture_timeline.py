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


def noisy(T, level, seed=9):
    """Re-encoded target: clip scores ~0.91 at the true offset, as measured on the media."""
    rng = np.random.default_rng(seed)
    n = rng.normal(size=T.shape).astype(np.float32)
    n = sum(np.roll(n, k, 0) for k in range(4))
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    x = T + level * n
    x -= x.mean(axis=1, keepdims=True)
    return x / np.linalg.norm(x, axis=1, keepdims=True)


def source_at(segs, t):
    seg = next(s for s in segs if s['target_start'] <= t < s['target_end'])
    return None if seg['kind'] != 'audio' else seg['source_start'] + (t - seg['target_start']) * seg['speed']


class BalancedEdits(unittest.TestCase):
    """Case 3 (1007-1060 s): the target adds a few seconds of its own footage and
    cuts as much source nearby, so the shots on both sides of the gap share one
    timing while the shots inside sit 1-5 s away. Restricting the gap re-solve
    to the neighbours' range bridged them with continuous source audio, 1-5 s
    away from the pictures (and from the target's own soundtrack)."""
    @classmethod
    def setUpClass(cls):
        S = unique_frames(220 * FPS, 11); X = unique_frames(40 * FPS, 12)
        T = np.vstack([S[:100 * FPS], X[:3 * FPS], S[100 * FPS:106 * FPS], S[109 * FPS:150 * FPS],
                       X[10 * FPS:15 * FPS], S[150 * FPS:157 * FPS], S[162 * FPS:]])
        cls.segs = plan(solve(S, noisy(T, .45)), len(T) / FPS)

    def test_shots_inside_the_gap_follow_their_pictures(self):
        for t, want in [(50., 50.), (105., 102.), (130., 130.), (158., 153.), (190., 190.)]:
            self.assertAlmostEqual(source_at(self.segs, t), want, delta=.05)

    def test_inserted_footage_uses_target_audio(self):
        refs = [s for s in self.segs if s['kind'] == 'reference']
        self.assertEqual([(round(s['target_start']), round(s['target_end'])) for s in refs], [(100, 103), (150, 155)])
        from continuity_guard import source_rewinds
        self.assertEqual(source_rewinds(self.segs), [])


class HeldShot(unittest.TestCase):
    """Case 2 (target 128-138 s): a still shot is held 1.48 s longer in the target.
    Every placement of the extra time fits the pictures; it was put at an
    arbitrary point where the target audio (here the same soundtrack, offset)
    repeated 1.5 s of audible source sound. It now goes where the target audio
    that fills it is quietest."""
    def setUp(self):
        S = unique_frames(120 * FPS, 13)
        S[50 * FPS:58 * FPS] = S[50 * FPS]                      # 8 s still shot
        self.T = np.vstack([S[:53 * FPS], np.repeat(S[50 * FPS][None], int(1.5 * FPS), 0), S[53 * FPS:]])
        self.tl = solve(S, self.T)
        self.energy = np.ones(len(self.T) * 2)                 # 50 Hz loudness
        self.energy[int(55.2 * 50):int(57.2 * 50)] = 0.          # a pause inside the held shot

    def quiet(self, starts, length):
        c = np.r_[0., np.cumsum(self.energy)]
        i0 = np.round(np.asarray(starts) * 50).astype(int); i1 = i0 + int(round(length * 50))
        return (c[i1] - c[i0]) / (i1 - i0)

    def test_extra_time_goes_to_the_quietest_point(self):
        segs = pt.to_plan_segments(self.tl, len(self.T) / FPS, 120., 0., quiet=self.quiet)[0]
        ref = [s for s in segs if s['kind'] == 'reference']
        self.assertEqual(len(ref), 1)
        self.assertTrue(55.1 <= ref[0]['target_start'] and ref[0]['target_end'] <= 57.3, ref[0])
        self.assertAlmostEqual(source_at(segs, 40.), 40., delta=.05)
        self.assertAlmostEqual(source_at(segs, 80.), 78.5, delta=.05)

    def test_new_footage_is_still_placed_by_pictures(self):
        S = unique_frames(180 * FPS, 1); extra = unique_frames(10 * FPS, 2)
        T = np.vstack([S[:60 * FPS], extra, S[60 * FPS:]])
        loud = lambda starts, length: np.abs(np.asarray(starts) - 20.)    # 'quietest' far away
        segs = pt.to_plan_segments(solve(S, T), len(T) / FPS, 180., 0., quiet=loud)[0]
        ref = next(s for s in segs if s['kind'] == 'reference')
        self.assertAlmostEqual(ref['target_start'], 60., delta=.3)


def slow_frames(n, seed, width=60):
    """Slow motion: a few frames' offset still scores ~0.9, as in real footage."""
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n + width, 384)).astype(np.float32)
    c = np.cumsum(x, 0); x = c[width:] - c[:-width]
    x -= x.mean(axis=1, keepdims=True)
    return x / np.linalg.norm(x, axis=1, keepdims=True)


def resample(S, pos):
    a = np.floor(pos).astype(int); w = (pos - a)[:, None]
    x = S[a] * (1 - w) + S[a + 1] * w
    return x / np.linalg.norm(x, axis=1, keepdims=True)


class Drift(unittest.TestCase):
    """Gradual picture drift against continuous sound, inside one matched section.

    Case 5 (target 48.5-59 s): the picture runs 2-3 % slow for 7 s (0.26 s at
    worst) and steps back by 0.13 s at 55.6 s; a constant offset left
    0.22-0.26 s of lip error. The drift is followed with a continuous speed
    change and the forward step becomes a cut. The 25 fps grid only proposes
    drifts; a FINE (50 fps) decode confirms them. Must NOT be followed: steady
    footage (case 1 showed false 0.16 s proposals there), a shot displaced by a
    backward step (case 1, 197.6-200 s) and a snap-back (case 7): both would
    need repeated audio or a curve that departs early and returns late.
    """
    @classmethod
    def setUpClass(cls):
        cls.S50 = slow_frames(200 * pt.FINE, 31, width=120)
        cls.S = cls.S50[::2]
        cls.DT = np.full(150 * FPS, 20.)

    def make(self, knots_t, knots_d):
        d = lambda t: np.interp(t, knots_t, knots_d)
        t25 = np.arange(150 * FPS) / FPS; t50 = np.arange(150 * pt.FINE) / pt.FINE
        T = noisy(resample(self.S50, (t25 + 30 + d(t25)) * pt.FINE), .3)
        T50 = noisy(resample(self.S50, (t50 + 30 + d(t50)) * pt.FINE), .3, seed=10)
        def verify(t0, t1, s0, s1):
            return (T50[int(round(t0 * pt.FINE)):int(round(t1 * pt.FINE))],
                    self.S50[int(round(s0 * pt.FINE)):int(round(s1 * pt.FINE))])
        x = dict(kind='match', first=12, last=len(T) - 13, samples=len(T) // 12, strong=len(T) // 12)
        x['offset'] = pt.refine_offset(T, self.S, self.DT, 1., list(range(12, len(T) - 13, 12)), 30 * FPS)
        return T, d, verify, x

    def plan_for(self, T, sections):
        tl = pt.Timeline(1., {}, sections, dict(FT=T, FS=self.S, DT=self.DT))
        return pt.to_plan_segments(tl, len(T) / FPS, 200., 0.)[0]

    def check_safe(self, segs):
        from continuity_guard import source_rewinds
        self.assertEqual(source_rewinds(segs), [])
        self.assertTrue(all(abs(s['speed'] - 1) <= pt.DRIFT_SLOPE + 1e-9 for s in segs if s['kind'] == 'audio'))

    def test_gradual_drift_with_a_forward_step_is_followed(self):
        T, d, verify, x = self.make([0, 20, 26, 26.4, 150], [-.26, -.24, -.13, 0, 0])
        got = pt.follow_drift(x, T, self.S, self.DT, 1., verify)
        self.assertIsNotNone(got)
        segs = self.plan_for(T, got)
        self.check_safe(segs)
        for tt in np.arange(2., 148., .5):
            if not 25.6 <= tt <= 27.:           # the cut is placed within the step
                self.assertAlmostEqual(source_at(segs, tt), tt + 30 + d(tt), delta=.07, msg=tt)

    def test_no_drift_next_to_a_cut(self):
        # Case 6: a ramp in the last seconds before a cut to another matched
        # section is the cut's transition; the join placement handles it.
        T, d, verify, x = self.make([0, 140, 146, 150], [0, 0, -.2, -.2])
        self.assertIsNone(pt.follow_drift(x, T, self.S, self.DT, 1., verify, cut_after=True))

    def test_no_verifier_follows_nothing(self):
        T, d, verify, x = self.make([0, 20, 27, 150], [-.24, -.24, 0, 0])
        self.assertIsNone(pt.follow_drift(x, T, self.S, self.DT, 1.))

    def test_steady_footage_has_no_drift(self):
        T, d, verify, x = self.make([0, 150], [0, 0])
        self.assertIsNone(pt.follow_drift(x, T, self.S, self.DT, 1., verify))

    def test_displaced_shot_and_snap_back_are_not_followed(self):
        for knots in (([0, 60, 60.05, 62.5, 62.55, 150], [0, 0, -.35, -.35, 0, 0]),     # case 1
                      ([0, 60, 63.5, 66.5, 67, 150], [0, 0, .28, .28, 0, 0])):           # case 7
            T, d, verify, x = self.make(*knots)
            got = pt.follow_drift(x, T, self.S, self.DT, 1., verify)
            segs = self.plan_for(T, got or [x])
            self.check_safe(segs)
            tt = np.arange(2., 148., .5)
            err = np.abs([source_at(segs, v) - (v + 30 + d(v)) for v in tt]); const = np.abs([d(v) for v in tt])
            self.assertLessEqual(float(np.max(err - const)), .06)


class SourceEnd(unittest.TestCase):
    """A frame-sized overrun past the source's last sample is not a fallback section.

    Seen on CI (HeldShot, other numpy build): the last join landed one frame
    later, the final audio section ran 20 ms past the source's end, and a 20 ms
    "source ends early" target-audio sliver was added at the very end.
    """
    def test_small_overrun_extends_the_last_section(self):
        S = unique_frames(120 * FPS, 5)
        tl = solve(S, S[:120 * FPS])
        segs = pt.to_plan_segments(tl, 120., 119.98, 0.)[0]
        self.assertEqual([s['kind'] for s in segs], ['audio'])
        self.assertAlmostEqual(segs[-1]['target_end'], 120.)

    def test_real_shortfall_still_uses_the_fallback(self):
        S = unique_frames(120 * FPS, 5)
        tl = solve(S, S[:120 * FPS])
        segs = pt.to_plan_segments(tl, 120., 118., 0.)[0]
        self.assertEqual(segs[-1]['kind'], 'reference')
        self.assertAlmostEqual(segs[-1]['target_start'], 118., delta=.05)


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


def sparse_detail(n, every=6):
    """Real footage has an unambiguous frame only every few seconds."""
    d = np.zeros(n)
    d[(np.arange(n) // FPS) % every == 0] = 20.
    return d


class RateWithManyCuts(unittest.TestCase):
    """A target missing 7 % of the source in four cuts still plays at rate 1.

    The median slope of match pairs leaned towards the duration ratio (300/280)
    because most pairs 20-200 s apart straddle a cut.
    """
    def test_rate_is_not_the_duration_ratio(self):
        S = unique_frames(300 * FPS, 5)
        keep = [(0, 50), (56, 110), (112.5, 170), (178, 240), (243, 300)]
        T = np.vstack([S[int(a * FPS):int(b * FPS)] for a, b in keep])
        r = pt.estimate_ratio(T, sparse_detail(len(T)), S, np.full(len(S), 20.))
        self.assertAlmostEqual(r, 1., places=4)

    def test_rate_with_inserts(self):
        S = unique_frames(300 * FPS, 6)
        extra = unique_frames(60 * FPS, 7)
        T = np.vstack([S[:60 * FPS], extra[:8 * FPS], S[60 * FPS:150 * FPS], extra[20 * FPS:35 * FPS],
                       S[150 * FPS:220 * FPS], extra[40 * FPS:52 * FPS], S[220 * FPS:]])
        r = pt.estimate_ratio(T, sparse_detail(len(T)), S, np.full(len(S), 20.))
        self.assertAlmostEqual(r, 1., places=4)


class ZoomedFraming(unittest.TestCase):
    """Source is the target zoomed in 12 % off centre (broadcast overscan / re-framing)."""
    def test_zoomed_side_is_found(self):
        from scipy import ndimage
        rng = np.random.default_rng(3)
        T = np.repeat(ndimage.gaussian_filter(rng.uniform(0, 255, (50, pt.H, pt.W)), (0, 2.5, 2.5)), 12, axis=0)  # held shots
        T = (T - T.min(axis=(1, 2), keepdims=True)) / np.ptp(T, axis=(1, 2), keepdims=True) * 200 + 30
        y0, x0, h, w = 2, 6, int(pt.H * .88), int(pt.W * .88)
        S = ndimage.zoom(T[:, y0:y0 + h, x0:x0 + w], (1, pt.H / h, pt.W / w), order=1)
        info = dict(aspect=4 / 3)
        S, T = S.astype(np.uint8), T.astype(np.uint8)
        plain = pt._framing_score(pt.features(S[::12], (0, 0, 1, 1))[0],
                                  *pt.features(T[np.linspace(pt.FPS * 5, len(T) - pt.FPS * 5, 160).astype(int)], (0, 0, 1, 1)))
        score, sr, tr = pt._best_geometry(S, T, info, info)
        self.assertGreater(score, plain + .02)
        self.assertEqual(tuple(sr), (0, 0, 1, 1))
        self.assertLess(tr[2] - tr[0], .95)  # the target (wider view) is the side cropped


@unittest.skipUnless(__import__('shutil').which('ffmpeg'), 'FFmpeg unavailable')
class OffGridVideoStart(unittest.TestCase):
    """MKV with AAC priming starts its video 0.021 s after the file start.

    The decode grid used to start at the FILE start, so the fps filter put
    every picture in a neighbouring slot (a constant 19-59 ms timing error).
    """
    def test_same_pictures_decode_to_same_frames(self):
        import subprocess, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            a, b = Path(td) / 'a.mp4', Path(td) / 'b.mkv'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=320x240:r=25:d=6', '-f', 'lavfi',
                            '-i', 'sine=d=6', '-c:v', 'libx264', '-g', '1', '-c:a', 'aac', '-shortest', str(a)], check=True)
            subprocess.run(['ffmpeg', '-v', 'error', '-i', str(a), '-c', 'copy', str(b)], check=True)
            ia, ib = pt.stream_info(a), pt.stream_info(b)
            A, B = pt.decode(a).astype(float), pt.decode(b).astype(float)
            n = min(len(A), len(B)) - 2
            same = np.mean([np.abs(A[k] - B[k]).mean() for k in range(1, n)])
            shifted = np.mean([np.abs(A[k] - B[k + 1]).mean() for k in range(1, n)])
            self.assertLess(same, shifted / 5)
            # Picture time 0 is each video's first frame on the container timeline.
            self.assertAlmostEqual(ia['origin'], ia['start']); self.assertAlmostEqual(ib['origin'], ib['start'])
