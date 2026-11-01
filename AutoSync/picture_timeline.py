"""Dense picture timeline: map every target moment to the source picture.

The source audio belongs to the source picture. When both videos are present,
the timing that keeps it lip-synced on the target is the target->source
PICTURE correspondence, not the target's own (often re-laid or delayed) dub.
This module finds that correspondence densely and globally:

1. one low-resolution decode per video; letterbox/pillarbox and aspect crops
   are tested and the best shared geometry kept;
2. the edition rate is estimated from strong single-frame matches;
3. every 0.5 s of target gets source-offset candidates scored with
   speed-scaled 2 s clips (plus offsets popular nearby, for static shots);
4. a Viterbi pass over the whole episode chooses one offset per sample, or a
   target-only state, with penalties for cuts, backward and far jumps; so
   several edits inside one region are found jointly;
5. target-only runs are classified by source continuity: picture-match
   failures are bridged with source audio, genuine target-only footage is
   a picture-verified insert;
6. offsets are refined to sub-frame precision and cuts placed per frame.

No per-episode constants: all thresholds are similarity/score levels.
"""
import json
import subprocess
import numpy as np
from scipy import ndimage

FPS = 25                 # decode grid
W, H = 64, 48            # decode size (full frame; crops applied in numpy)
STEP = .5                # target sample spacing (s)
CLIP = np.arange(-25, 26, 5)          # +-1 s every 0.2 s, in frames
KNOWN = (1., 25 / 24, 25025 / 24000, 24 / 25, 24000 / 25025)
MATCH = .82              # clip score above which a match is evidence
JUMP, BACK, FAR, NULL = 1.5, 3.0, 4.0, .6


def _run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        raise RuntimeError(p.stderr.decode(errors='replace')[-2000:])
    return p.stdout


def stream_info(path, ffprobe='ffprobe'):
    d = json.loads(_run([ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))
    v = next(s for s in d['streams'] if s['codec_type'] == 'video')
    w, h = int(v['width']), int(v['height'])
    sar = v.get('sample_aspect_ratio', '1:1')
    try:
        a, b = map(float, sar.split(':')); sar = a / b if a > 0 and b > 0 else 1.
    except ValueError:
        sar = 1.
    # Decoded frame k sits at origin + k/FPS: ffmpeg rebases to the FILE start
    # and pads the first picture back to it, whatever the video stream's start.
    return dict(start=float(v.get('start_time') or 0), origin=float(d.get('format', {}).get('start_time') or 0),
                aspect=w * sar / h, width=w, height=h,
                audio_starts=[float(s.get('start_time') or 0) for s in d['streams'] if s['codec_type'] == 'audio'])


def decode(path, ffmpeg='ffmpeg'):
    """uint8 (n, H, W) frames on a fixed 25 fps grid from the first video PTS."""
    out = _run([ffmpeg, '-v', 'error', '-nostdin', '-i', str(path), '-map', '0:v:0', '-an', '-sn',
                '-vf', f'fps={FPS},scale={W}:{H}:flags=area,format=gray', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'])
    return np.frombuffer(out, np.uint8).reshape(-1, H, W)


def active_rect(frames):
    """Fractional bounding box of non-black picture (letterbox/pillarbox removed)."""
    sample = frames[::max(1, len(frames) // 600)].astype(np.float32)
    bright = np.quantile(sample, .95, axis=0)
    rows = np.flatnonzero(bright.mean(axis=1) > 22); cols = np.flatnonzero(bright.mean(axis=0) > 22)
    if len(rows) < H // 3 or len(cols) < W // 3:
        return (0., 0., 1., 1.)
    return (cols[0] / W, rows[0] / H, (cols[-1] + 1) / W, (rows[-1] + 1) / H)


def geometry_candidates(rect, aspect, other_aspect):
    x0, y0, x1, y1 = rect
    out = [rect]
    a = aspect * (x1 - x0) / (y1 - y0)
    if a > other_aspect * 1.08:          # wider: centre crop to the other aspect
        keep = (x1 - x0) * other_aspect / a; m = (x0 + x1) / 2
        out.append((m - keep / 2, y0, m + keep / 2, y1))
    elif a < other_aspect / 1.08:        # taller: centre band at the other aspect
        keep = (y1 - y0) * a / other_aspect; m = (y0 + y1) / 2
        out.append((x0, m - keep / 2, x1, m + keep / 2))
    return out


def features(frames, rect):
    """Unit-norm zero-mean 24x16 vectors; bottom fifth (subtitles) dropped."""
    x0, y0, x1, y1 = rect
    a, b = int(round(y0 * H)), int(round(y1 * H)); c, d = int(round(x0 * W)), int(round(x1 * W))
    b = a + max(4, int((b - a) * .8))
    f = frames[:, a:b, c:d].astype(np.float32)
    f = ndimage.zoom(f, (1, 16 / f.shape[1], 24 / f.shape[2]), order=1)
    f = f.reshape(len(f), -1)
    detail = f.std(axis=1)
    f -= f.mean(axis=1, keepdims=True)
    f /= np.maximum(np.linalg.norm(f, axis=1, keepdims=True), 1e-6)
    return f, detail


def _best_geometry(S, T, s_info, t_info):
    s_rects = geometry_candidates(active_rect(S), s_info['aspect'], t_info['aspect'] * 1.)
    t_rects = geometry_candidates(active_rect(T), t_info['aspect'], s_info['aspect'] * 1.)
    ts = T[np.linspace(FPS * 5, len(T) - FPS * 5, 160).astype(int)]
    ss = S[::FPS // 2]
    best = None
    for sr in s_rects:
        fs, ds = features(ss, sr)
        for tr in t_rects:
            ft, dt = features(ts, tr)
            sim = ft[dt > 6] @ fs.T
            if not len(sim):
                continue
            score = float(np.mean(np.sort(sim.max(axis=1))[len(sim) // 3:]))
            if best is None or score > best[0]:
                best = (score, sr, tr)
    return best


def estimate_ratio(FT, DT, FS, DS):
    """Edition rate from strong, unambiguous single-frame matches (1 per second)."""
    idx = np.arange(FPS * 2, len(FT) - FPS * 2, FPS)
    idx = idx[DT[idx] > 6]
    pts = []
    for start in range(0, len(idx), 256):
        sim = FT[idx[start:start + 256]] @ FS.T
        for row, i in enumerate(idx[start:start + 256]):
            j = int(np.argmax(sim[row])); v = sim[row, j]
            alt = sim[row].copy(); alt[max(0, j - FPS * 2):j + FPS * 2] = -1
            if v > .93 and v - alt.max() > .05 and DS[j] > 6:
                pts.append((i / FPS, j / FPS))
    slopes = []
    for a in range(len(pts)):
        for b in range(a + 1, min(len(pts), a + 40)):
            du = pts[b][0] - pts[a][0]
            if 20 < du < 200:
                sl = (pts[b][1] - pts[a][1]) / du
                if .8 < sl < 1.25:
                    slopes.append(sl)
    if len(slopes) < 10:
        raise RuntimeError('Too few unambiguous picture matches to establish the edition rate.')
    med = float(np.median(slopes))
    near = min(KNOWN, key=lambda x: abs(x - med))
    return near if abs(near - med) < 1.5e-3 else med


def clip_scores(FT, FS, i, offsets_frames, r):
    """Mean clip similarity of target frame i against source at each offset (in source frames)."""
    ti = i + CLIP
    ok_t = (ti >= 0) & (ti < len(FT))
    q = FT[ti[ok_t]]
    out = np.full(len(offsets_frames), -1.)
    for k, o in enumerate(offsets_frames):
        sj = np.round(r * ti[ok_t] + o).astype(int)
        ok = (sj >= 0) & (sj < len(FS))
        if ok.sum() >= len(CLIP) * .7:
            out[k] = float(np.mean(np.sum(q[ok] * FS[sj[ok]], axis=1)))
    return out


def candidates(FT, DT, FS, DS, r, samples, top=8):
    """Per sample: dict offset(frames, int) -> clip score."""
    cand = [dict() for _ in samples]
    for start in range(0, len(samples), 256):
        idx = samples[start:start + 256]
        sim = FT[idx] @ FS.T
        for row, i in enumerate(idx):
            s = sim[row]
            order = np.argpartition(-s, 80)[:80]; order = order[np.argsort(-s[order])]
            chosen = []
            for j in order:
                if all(abs(j - c) > FPS for c in chosen):
                    chosen.append(int(j))
                if len(chosen) >= top:
                    break
            offs = [int(round(j - r * i)) for j in chosen]
            for o, v in zip(offs, clip_scores(FT, FS, i, offs, r)):
                cand[start + row][o] = v
    # Static shots: the true offset may not be a top single-frame match. Offer
    # every offset that is strongly supported within +-30 s to all samples there.
    strong = [(k, max(c, key=c.get)) for k, c in enumerate(cand) if c and max(c.values()) > .9]
    span = int(30 / STEP)
    for k, i in enumerate(samples):
        local = {o for kk, o in strong if abs(kk - k) <= span}
        extra = [o for o in local if all(abs(o - x) > 1 for x in cand[k])]
        for o, v in zip(extra, clip_scores(FT, FS, i, extra, r)):
            cand[k][o] = v
    return cand


def solve(cand, r, match=MATCH, jump=JUMP, allowed=None):
    """Viterbi over offsets (+ target-only state None). Returns offset or None per sample."""
    n = len(cand)
    states = [sorted(o for o in c if allowed is None or allowed(o)) + [None] for c in cand]
    def reward(k, o):
        return 0. if o is None else float(np.clip(cand[k][o] - match, -.5, .2))
    def cost(a, b):
        if a is None or b is None:
            return 0. if a is b else NULL
        d = (b - a) / FPS          # source seconds
        if abs(d) <= 1.5 / FPS:
            return .02 * abs(b - a)
        c = jump if d > 0 else BACK
        return c + (FAR if abs(d) > 60 else 0.)
    score = np.array([reward(0, o) for o in states[0]])
    back = []
    for k in range(1, n):
        prev = states[k - 1]; cur = states[k]
        trans = np.array([[cost(a, b) for a in prev] for b in cur])
        total = score[None, :] - trans
        arg = total.argmax(axis=1)
        score = total[np.arange(len(cur)), arg] + np.array([reward(k, o) for o in cur])
        back.append(arg)
    path = [int(np.argmax(score))]
    for arg in reversed(back):
        path.append(int(arg[path[-1]]))
    path.reverse()
    return [states[k][s] for k, s in enumerate(path)]


def runs_from_path(path, samples):
    """[(kind, first_sample, last_sample, offset_frames)] with +-1 frame jitter merged."""
    runs = []
    for k, o in enumerate(path):
        if runs and ((o is None and runs[-1][3] is None) or
                     (o is not None and runs[-1][3] is not None and abs(o - runs[-1][3]) <= 1)):
            runs[-1][2] = k
        else:
            runs.append(['match' if o is not None else 'none', k, k, o])
    return runs


def refine_offset(FT, FS, DT, r, sample_frames, offset):
    """Sub-frame offset (source frames, float) maximizing clip similarity."""
    idx = [i for i in sample_frames if DT[i] > 6]
    if len(idx) > 80:
        idx = list(np.array(idx)[np.linspace(0, len(idx) - 1, 80).astype(int)])
    if not idx:
        return float(offset)
    grid = np.arange(-1.5, 1.51, .25)
    scores = []
    for g in grid:
        o = offset + g; tot = 0.; cnt = 0
        for i in idx:
            ti = i + CLIP; pos = r * ti + o
            a = np.floor(pos).astype(int); w = (pos - a)[:, None]
            ok = (a >= 0) & (a + 1 < len(FS)) & (ti >= 0) & (ti < len(FT))
            if ok.sum() < 5:
                continue
            x = FS[a[ok]] * (1 - w[ok]) + FS[a[ok] + 1] * w[ok]
            x /= np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-6)
            tot += float(np.mean(np.sum(FT[ti[ok]] * x, axis=1))); cnt += 1
        scores.append(tot / max(cnt, 1))
    scores = np.array(scores); k = int(np.argmax(scores))
    shift = 0.
    if 0 < k < len(scores) - 1:
        a, b, c = scores[k - 1:k + 2]; d = a - 2 * b + c
        if d < 0:
            shift = float(np.clip(.5 * (a - c) / d, -.5, .5))
    return float(offset + grid[k] + shift * .25)


def frame_scores(FT, FS, r, lo, hi, offset):
    """Per target frame in [lo, hi): similarity under a mapping (+-1 frame tolerance)."""
    ti = np.arange(lo, hi)
    out = np.zeros(len(ti))
    for d in (-1, 0, 1):
        sj = np.round(r * ti + offset + d).astype(int)
        ok = (sj >= 0) & (sj < len(FS))
        v = np.full(len(ti), -1.); v[ok] = np.sum(FT[ti[ok]] * FS[sj[ok]], axis=1)
        out = np.maximum(out, v)
    return out


def place_cut(FT, FS, DT, r, lo, hi, oa, ob):
    """Switch frame from mapping a to b in [lo, hi), and the span the pictures bound it to.

    The span runs from the last informative frame favouring a to the first
    favouring b; inside it (static or dark frames) pictures cannot tell.
    """
    lo = max(0, lo); hi = min(len(FT), hi)
    if hi - lo < 2:
        return lo, lo, lo
    a = frame_scores(FT, FS, r, lo, hi, oa); b = frame_scores(FT, FS, r, lo, hi, ob)
    informative = (DT[lo:hi] > 6) & (np.abs(a - b) > .05)
    diff = np.where(informative, a - b, 0.)
    obj = np.r_[0., np.cumsum(diff)]
    k = int(np.argmax(obj))
    before = np.flatnonzero(informative[:k] & (diff[:k] > 0))
    after = np.flatnonzero(informative[k:] & (diff[k:] < 0)) + k
    s0 = lo + (int(before[-1]) + 1 if len(before) else 0)
    s1 = lo + (int(after[0]) if len(after) else hi - lo)
    return lo + k, min(s0, lo + k), max(s1, lo + k)


def monotone_chain(sections, r):
    """Keep the duration-weighted longest source-monotone chain of matched runs.

    A recap or 'next time' preview reuses footage from far elsewhere in the
    source; following it would replay or pre-play source audio. Runs off the
    chain become target-only.
    """
    idx = [i for i, x in enumerate(sections) if x['kind'] == 'match']
    if len(idx) < 2:
        return sections
    start = {i: r * sections[i]['first'] + sections[i]['offset'] for i in idx}
    end = {i: r * sections[i]['last'] + sections[i]['offset'] for i in idx}
    best, prev = {}, {}
    for n, i in enumerate(idx):
        best[i], prev[i] = sections[i]['samples'], None
        for j in idx[:n]:
            # Small overlaps are target-only inserts; anything larger is a replay.
            if start[i] >= end[j] - 1.5 * FPS and best[j] + sections[i]['samples'] > best[i]:
                best[i], prev[i] = best[j] + sections[i]['samples'], j
    i = max(best, key=best.get); keep = set()
    while i is not None:
        keep.add(i); i = prev[i]
    out = [dict(x) for x in sections]
    for i in idx:
        if i not in keep:
            out[i]['kind'] = 'none'; out[i]['reused'] = True
    return out


def refine_gaps(sections, cand, samples, FT, FS, r):
    """Re-solve unmatched gaps between two matched runs, locally and monotonically.

    Inside such a gap the source must move from one neighbour's offset to the
    other's; short sections there often score only ~0.8 (dark, soft, fast)
    and lose to the global target-only state. Pool every candidate offset in
    the gap within that range, rescore all gap samples, and re-solve with a
    relaxed threshold. New runs still need several solid samples.
    """
    out = []
    far = 120 * FPS
    for i, x in enumerate(sections):
        prev_m = i > 0 and sections[i - 1]['kind'] == 'match'
        next_m = i < len(sections) - 1 and sections[i + 1]['kind'] == 'match'
        if x['kind'] != 'none' or not (prev_m or next_m):
            out.append(x); continue
        if prev_m and next_m:
            # An insert and a cut inside one gap can cancel, so the neighbours
            # may agree while the shots between them sit seconds away. A
            # forward source path through the gap deviates from the neighbours
            # by at most the gap length (an insert is no longer than the gap,
            # and a cut is bounded by the insert that compensates it).
            oa, ob = sections[i - 1]['offset'], sections[i + 1]['offset']
            span = r * (x['last'] - x['first']) + FPS
            lo, hi = min(oa, ob) - span, max(oa, ob) + span
        elif next_m and i == 0:
            # Opening before the first match (shared OP under credit overlays):
            # source must not run past the first match.
            oa = ob = sections[i + 1]['offset']; lo, hi = ob - far, ob + 2
        elif prev_m and i == len(sections) - 1:
            oa = ob = sections[i - 1]['offset']; lo, hi = oa - 2, oa + far
        else:
            out.append(x); continue
        ks = [k for k in range(len(samples)) if x['first'] <= samples[k] <= x['last']]
        pool = sorted({o for k in ks for o in cand[k] if lo <= o <= hi} | {int(round(oa)), int(round(ob))})
        local = []
        for k in ks:
            c = dict(cand[k])
            missing = [o for o in pool if o not in c]
            for o, v in zip(missing, clip_scores(FT, FS, samples[k], missing, r)):
                c[o] = v
            local.append(c)
        path = solve(local, r, match=.74, jump=.6, allowed=lambda o: lo <= o <= hi)
        runs = runs_from_path(path, samples[ks])
        pieces = []
        inner_lo, inner_hi = min(oa, ob) - 2, max(oa, ob) + 2
        for kind, a, b, o in runs:
            first, last = int(samples[ks[a]]), int(samples[ks[b]])
            # Timing outside the neighbours' range needs full-strength evidence.
            outside = o is not None and not inner_lo <= o <= inner_hi
            level = MATCH if outside else .78
            solid = int(sum(local[k].get(o, -1) > level for k in range(a, b + 1))) if o is not None else 0
            if kind == 'match' and solid >= (4 if outside else 3):
                pieces.append(dict(kind='match', first=first, last=last, offset=float(o), samples=b - a + 1,
                                   strong=solid, gap_refined=True))
            else:
                pieces.append(dict(kind='none', first=first, last=last, samples=b - a + 1))
        merged = []
        for pc in pieces:
            if merged and pc['kind'] == merged[-1]['kind'] == 'none':
                merged[-1].update(last=pc['last'], samples=merged[-1]['samples'] + pc['samples'])
            else:
                merged.append(pc)
        out.extend(merged)
    return out


def absorb_jitter(sections, short=20, near=6, agree=1.5):
    """A short run a few frames off two agreeing neighbours is matching noise.

    Resampling 23.976 fps material onto the decode grid makes isolated clips
    prefer an offset 2-4 frames away. Real edits persist; an excursion that
    returns to the same timing within 10 s is not an edit.
    """
    s = [dict(x) for x in sections]
    changed = True
    while changed:
        changed = False
        matches = [i for i, x in enumerate(s) if x['kind'] == 'match']
        for a, b, c in zip(matches, matches[1:], matches[2:]):
            L, M, N = s[a], s[b], s[c]
            if (M['samples'] < short and abs(L['offset'] - N['offset']) <= agree and
                    abs(M['offset'] - L['offset']) <= near):
                M['offset'] = L['offset'] if M['samples'] else M['offset']
                M['jitter'] = True
                changed = True
        merged = []
        for x in s:
            if (merged and x['kind'] == merged[-1]['kind'] == 'match' and
                    abs(x['offset'] - merged[-1]['offset']) <= agree):
                m = merged[-1]; n = m['samples'] + x['samples']
                m.update(last=x['last'], offset=(m['offset'] * m['samples'] + x['offset'] * x['samples']) / n,
                         samples=n, strong=m['strong'] + x['strong'])
                changed = changed or False
            else:
                merged.append(x)
        if len(merged) == len(s):
            changed = False
        s = merged
    return s


class Timeline:
    """Result in target-video time (s) and SOURCE-PICTURE time (s, video-relative)."""
    def __init__(self, ratio, geometry, sections, diagnostics):
        self.ratio, self.geometry, self.sections, self.diagnostics = ratio, geometry, sections, diagnostics


def build(source_video, target_video, ffmpeg='ffmpeg', ffprobe='ffprobe', progress=print):
    s_info, t_info = stream_info(source_video, ffprobe), stream_info(target_video, ffprobe)
    progress('Picture timeline: decoding source and target pictures...')
    S, T = decode(source_video, ffmpeg), decode(target_video, ffmpeg)
    if min(len(S), len(T)) < FPS * 60:
        raise RuntimeError('Videos are too short for picture timing.')
    geo = _best_geometry(S, T, s_info, t_info)
    if geo is None or geo[0] < .75:
        raise RuntimeError('Source and target pictures do not match under any tested framing.')
    FS, DS = features(S, geo[1]); FT, DT = features(T, geo[2]); del S, T
    progress(f'Picture timeline: framing score {geo[0]:.3f}; source crop {np.round(geo[1], 3).tolist()}, target crop {np.round(geo[2], 3).tolist()}')
    return from_features(FS, DS, FT, DT, dict(score=geo[0], source=geo[1], target=geo[2]), s_info, t_info, progress)


def from_features(FS, DS, FT, DT, geometry, s_info, t_info, progress=print, ratio=None):
    """Solve the timeline from unit-norm frame features (25 fps grids)."""
    r = ratio or estimate_ratio(FT, DT, FS, DS)
    progress(f'Picture timeline: source/target rate {r:.9f}')
    samples = np.arange(int(FPS * STEP), len(FT) - int(FPS * STEP), int(FPS * STEP))
    cand = candidates(FT, DT, FS, DS, r, samples)
    path = solve(cand, r)
    runs = runs_from_path(path, samples)
    sections = []
    for kind, a, b, o in runs:
        first, last = int(samples[a]), int(samples[b])
        if kind == 'match':
            strong = [samples[k] for k in range(a, b + 1) if cand[k].get(o, -1) > MATCH]
            o = refine_offset(FT, FS, DT, r, strong or [samples[a]], o)
            sections.append(dict(kind='match', first=first, last=last, offset=o, samples=b - a + 1,
                                 strong=len(strong)))
        else:
            sections.append(dict(kind='none', first=first, last=last, samples=b - a + 1))
    # Drop weak match runs (a few samples, little strong evidence) into 'none'.
    for s in sections:
        if s['kind'] == 'match' and s['strong'] < 3 and s['samples'] < 8:
            s['kind'] = 'none'
    sections = monotone_chain(sections, r)
    sections = monotone_chain(refine_gaps(sections, cand, samples, FT, FS, r), r)
    for x in sections:
        if x.get('gap_refined'):
            strong = [samples[k] for k in range(len(samples)) if x['first'] <= samples[k] <= x['last']]
            x['offset'] = refine_offset(FT, FS, DT, r, strong, x['offset'])
    sections = absorb_jitter(sections)
    merged = []
    for s in sections:
        if merged and s['kind'] == merged[-1]['kind'] == 'none':
            merged[-1].update(last=s['last'], samples=merged[-1]['samples'] + s['samples'])
        elif merged and s['kind'] == merged[-1]['kind'] == 'match' and abs(s['offset'] - merged[-1]['offset']) <= 1.:
            m = merged[-1]; n = m['samples'] + s['samples']
            m.update(last=s['last'], offset=(m['offset'] * m['samples'] + s['offset'] * s['samples']) / n,
                     samples=n, strong=m['strong'] + s['strong'])
        else:
            merged.append(dict(s))
    return Timeline(r, geometry, merged,
                    dict(FT=FT, FS=FS, DT=DT, DS=DS, samples=samples, s_info=s_info, t_info=t_info,
                         target_frames=len(FT), source_frames=len(FS)))


def edge_frame(FT, FS, r, lo, hi, offset, side):
    """First (start) / one past last (end) frame that matches under a mapping, sustained 0.5 s."""
    lo = max(0, lo); hi = min(len(FT), hi)
    sc = frame_scores(FT, FS, r, lo, hi, offset) > MATCH
    k = FPS // 2
    good = np.flatnonzero(np.convolve(sc, np.ones(k), 'valid') >= k - 1)
    if not len(good):
        return lo if side == 'start' else hi
    return lo + int(good[0]) if side == 'start' else lo + int(good[-1]) + k


def held_span(FT, FS, r, lo, hi, oa, ob, limit=30):
    """Widen [lo, hi) over adjacent frames that fit both mappings equally (a held shot)."""
    def held(x0, x1):
        if x0 < 0 or x1 > len(FT) or x1 <= x0:
            return False
        a = frame_scores(FT, FS, r, x0, x1, oa); b = frame_scores(FT, FS, r, x0, x1, ob)
        return bool(np.min(np.minimum(a, b)) > MATCH and np.mean(np.abs(a - b)) < .03)
    k = 0
    while k < limit and held(lo - FPS, lo):
        lo -= FPS; k += 1
    k = 0
    while k < limit and held(hi, hi + FPS):
        hi += FPS; k += 1
    return lo, hi


def to_plan_segments(tl, duration, source_audio_length, audio_shift, place=place_cut, audio_cut=None, target_shift=0.,
                     quiet=None):
    """Convert sections into contiguous AutoSync segments in target seconds.

    Internally times are decoded-frame seconds (frame k = k/FPS).
    audio_shift: source audio time = source frame seconds + audio_shift.
    target_shift: target time (video-relative) = target frame seconds + target_shift.
    quiet(starts, length): mean target-audio loudness of windows starting at the
    given frame seconds, or None; places inserts inside held shots.
    Returns (segments, models, notes).
    """
    d = tl.diagnostics; FT, FS, DT = d['FT'], d['FS'], d['DT']; r = tl.ratio
    secs = tl.sections
    notes, models = [], []
    matches = [s for s in secs if s['kind'] == 'match']
    if not matches:
        raise RuntimeError('No source pictures correspond to the target.')
    # Boundaries between consecutive matched sections, with what lies between.
    pieces = []          # (target_start_s, target_end_s, kind, offset_frames or None, info)
    cursor = 0.
    for k, m in enumerate(matches):
        if k == 0:
            start = edge_frame(FT, FS, r, m['first'] - 2 * FPS, m['first'] + FPS, m['offset'], 'start') / FPS
            if start <= 1.:
                start = 0.
            elif start > 0:
                pieces.append([0., start, 'outer_start', None, {}])
            cursor = start
            continue
        p = matches[k - 1]
        gap_lo, gap_hi = p['last'], m['first']          # target frames
        oa, ob = p['offset'], m['offset']
        # Source-time accounting across the gap.
        sa_end = r * gap_lo + oa; sb_start = r * gap_hi + ob
        L = (gap_hi - gap_lo) / FPS
        insert = L - (sb_start - sa_end) / FPS / r       # target seconds without source
        if insert < .25:
            # Continuous or a source-only cut: switch once, frame-accurately.
            f, s0, s1 = place(FT, FS, DT, r, gap_lo - FPS, gap_hi + FPS, oa, ob)
            t, method = f / FPS, 'picture-located join'
            span = (s1 - s0) / FPS
            if span > .2 and audio_cut is not None:
                # Static/dark frames between the evidence: audio decides inside the span.
                got = audio_cut(p, m, t, s0 / FPS, s1 / FPS)
                if got is not None:
                    t, method = got
            # Joins bounded by picture evidence within 3 s are located; wider spans
            # remain uncertain (and block when they skip source audio).
            conf = 'supported' if span <= 3. else 'uncertain'
            pieces.append([cursor, t, 'audio', oa, {}])
            skipped = (ob - oa) / FPS
            notes.append(dict(start=max(0, t - 1), end=t + 1, splice=t, confidence=conf,
                              reason=(f'Source-only section: skip {skipped:.3f}s; ' if skipped > .25 else 'Timing change; ') +
                                     (method if conf == 'supported' else f'join estimated in a {span:.1f}s low-motion span') +
                                     '; preview the join'))
            cursor = t
        else:
            # Target-only footage of length `insert` lies in the gap. Place it where
            # neither mapping matches; source continues on both sides.
            lo, hi = held_span(FT, FS, r, max(0, gap_lo - FPS), min(len(FT), gap_hi + FPS), oa, ob)
            lo = max(lo, int(np.ceil(cursor * FPS)), p['first']); hi = min(hi, m['last'])
            a = frame_scores(FT, FS, r, lo, hi, oa)
            b = frame_scores(FT, FS, r, lo, hi, ob)
            n = int(round(insert * FPS))
            how = 'no source picture'
            if n >= len(a):
                x = 0
            else:
                # choose x so that [0,x) follows a, [x,x+n) is insert, [x+n,...) follows b
                ca = np.r_[0., np.cumsum(a)]; cb = np.r_[0., np.cumsum(b[::-1])][::-1]
                vals = np.array([ca[x] + cb[x + n] - .5 * n for x in range(0, len(a) - n + 1)])
                x = int(np.argmax(vals))
                # A held (static) shot shown longer: every placement inside it fits
                # the pictures. Put the extra time where the target audio, which
                # fills it, is quietest, so no audible sound is doubled or cut.
                tied = np.flatnonzero(vals >= vals[x] - .5)
                if quiet is not None and len(tied) >= FPS // 2:
                    loud = quiet((lo + tied) / FPS, n / FPS)
                    if loud is not None:
                        x = int(tied[int(np.argmin(loud))]); how = 'held shot shown longer, placed at the quietest target audio'
            t1 = (lo + x) / FPS; t2 = t1 + n / FPS
            pieces.append([cursor, t1, 'audio', oa, {}])
            pieces.append([t1, t2, 'insert', None, {}])
            notes.append(dict(start=t1, end=t2, splice=t1, confidence='supported',
                              reason=f'Picture-verified target-only footage ({t2-t1:.2f}s): {how}; target audio used; preview'))
            cursor = t2
        if k == len(matches) - 1:
            pass
    last = matches[-1]
    end = edge_frame(FT, FS, r, last['last'] - FPS, last['last'] + 2 * FPS, last['offset'], 'end') / FPS
    if duration - end <= 1.:
        end = duration
    pieces.append([cursor, end, 'audio', last['offset'], {}])
    if end < duration:
        pieces.append([end, duration, 'outer_end', None, {}])
    # A join a frame or two after another leaves a piece too short to carry
    # timing (and to time-stretch); the previous mapping simply continues.
    kept = []
    for pc in pieces:
        if kept and pc[2] == 'audio' and pc[1] - pc[0] < .1 and kept[-1][2] == 'audio':
            kept[-1][1] = pc[1]
        else:
            kept.append(pc)
    pieces = kept
    # Build segments.
    segments = []
    out_pieces = []
    for a, b, kind, o, info in pieces:
        # Frame seconds -> target video time; keep the cover exactly [0, duration].
        a2 = 0. if a <= 0 else min(duration, a + target_shift)
        b2 = duration if b >= duration - 1e-6 else min(duration, b + target_shift)
        if b2 - a2 > 1e-3:
            out_pieces.append((a2, b2, kind, o, a2 - target_shift))
    for a, b, kind, o, frame_a in out_pieces:
        if kind == 'audio':
            pic = r * frame_a + o / FPS      # source frame seconds
            ss = pic + audio_shift
            if -.05 < ss < 0:
                ss = 0.                      # rounding at the source's first sample
            if ss < 0:
                stop = min(b, a - ss / r)
                segments.append(dict(kind='reference', target_start=a, target_end=stop, reason='source starts late'))
                notes.append(dict(start=a, end=stop, reason='source audio unavailable; reference fallback needed'))
                a, ss = stop, 0.
            supported_end = min(b, a + max(0., source_audio_length - ss) / r)
            if supported_end > a:
                segments.append(dict(kind='audio', target_start=a, target_end=supported_end, source_start=ss, speed=r))
            if b > supported_end:
                segments.append(dict(kind='reference', target_start=supported_end, target_end=b, reason='source ends early'))
                notes.append(dict(start=supported_end, end=b, reason='source audio unavailable; reference fallback needed'))
        else:
            # Leading/trailing target-only runs are picture-verified too: the
            # solver found no source picture for them anywhere.
            verified = True
            segments.append(dict(kind='reference', target_start=a, target_end=b, verified_insert=verified,
                                 picture_outer=kind if kind.startswith('outer') else None,
                                 reason='Picture-verified target-only footage; use selected target audio' if verified else
                                        'Target opening/ending with no source pictures'))
    for m in matches:
        models.append(dict(speed=r, offset=m['offset'] / FPS + audio_shift - r * target_shift,
                           first=m['first'] / FPS + target_shift, last=m['last'] / FPS + target_shift,
                           anchors=m['strong'], p90_residual=0.))
    for n in notes:
        for k in ('start', 'end', 'splice'):
            if k in n:
                n[k] = n[k] + target_shift
    return segments, models, notes
