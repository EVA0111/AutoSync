#!/usr/bin/env python3
"""Independent measurement of delivered audio/picture sync for AutoSync output.

Nothing here uses the engine's features, anchors, models or plan. Two
independent positions are measured inside the ORIGINAL source file, whose own
audio and picture are the timing reference:

* picture: where the delivered frames appear in the source video, from dense
  speed-scaled frame clips (sub-frame refined);
* audio: where the delivered audio appears in the source recording (same
  recording, so correlation is strong and precise).

error = (source_audio_time - source_picture_time) / speed, in output seconds;
positive means the audio leads the picture. A successful export is not a pass.
"""
import argparse, csv, hashlib, json, os, subprocess, sys, threading
from pathlib import Path
import numpy as np
from scipy import signal, ndimage

FPS = 50          # picture sampling grid
AR = 16000        # audio decode rate
HOP = 160         # 100 Hz audio features
KNOWN = (1., 25/24, 25025/24000, 24/25, 24000/25025)


def _run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        raise RuntimeError(p.stderr.decode(errors='replace')[-3000:])
    return p.stdout


def probe(path):
    return json.loads(_run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))


def starts(path, audio_index=0):
    """First video PTS and the selected audio stream's start, in seconds."""
    p = probe(path)
    v = next(s for s in p['streams'] if s['codec_type'] == 'video')
    a = [s for s in p['streams'] if s['codec_type'] == 'audio']
    v0 = float(v.get('start_time') or 0)
    a0 = float(a[audio_index].get('start_time') or 0) if a else None
    return v0, a0


def _cache(path, tag, cache_dir):
    if cache_dir is None:
        return None
    st = Path(path).stat()
    key = hashlib.sha1(json.dumps([str(Path(path).resolve()), st.st_size, st.st_mtime_ns, tag]).encode()).hexdigest()[:24]
    return Path(cache_dir) / (key + '.npy')


def _save(path, array):
    # Parallel matrix workers may cache the same source: write atomically.
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f'{path.stem}.{os.getpid()}.{threading.get_ident()}.tmp.npy')
    np.save(tmp, array); os.replace(tmp, path)


def decode_frames(path, crop='', cache_dir=None):
    """50 fps grey 32x24 frames (subtitle rows dropped), unit-normalized."""
    c = _cache(path, ['frames3', crop], cache_dir)
    if c is not None and c.exists():
        raw = np.load(c)
    else:
        vf = f'fps={FPS},' + (f'crop={crop},' if crop else '') + 'scale=32:24:flags=area,format=gray'
        out = _run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(path), '-map', '0:v:0', '-an', '-sn',
                    '-vf', vf, '-f', 'rawvideo', '-pix_fmt', 'gray', '-'])
        raw = np.frombuffer(out, np.uint8).reshape(-1, 24, 32)[:, 1:18, 1:31].copy()
        if c is not None:
            _save(c, raw)
    f = raw.reshape(len(raw), -1).astype(np.float32)
    detail = f.std(axis=1)
    f -= f.mean(axis=1, keepdims=True)
    f /= np.maximum(np.linalg.norm(f, axis=1, keepdims=True), 1e-6)
    return f, detail


def decode_audio_features(path, stream=0, cache_dir=None):
    c = _cache(path, ['audio2', stream], cache_dir)
    if c is not None and c.exists():
        return np.load(c)
    out = _run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(path), '-map', f'0:a:{stream}', '-ac', '1',
                '-ar', str(AR), '-f', 'f32le', '-'])
    a = np.frombuffer(out, np.float32)
    f, _, z = signal.stft(a, AR, nperseg=512, noverlap=512 - HOP, boundary=None, padded=False)
    # Log-spaced bands; bins are grouped so every band holds at least one bin.
    band = np.digitize(f, np.geomspace(80, 7000, 41))
    mag = np.abs(z)
    feat = np.array([np.log1p(mag[band == b].mean(axis=0) * 1000) for b in np.unique(band[(f >= 80) & (f < 7000)])],
                    dtype=np.float32)
    loud = feat.mean(axis=0)
    feat -= ndimage.gaussian_filter1d(feat, 50, axis=1)
    feat /= np.maximum(feat.std(axis=1, keepdims=True), .01)
    feat = np.vstack([feat, loud[None]]).astype(np.float32)  # last row: loudness, for silence gating
    if c is not None:
        _save(c, feat)
    return feat


def _ncc(src, q):
    """Normalized cross-correlation of query q (bands, n) along src (bands, m)."""
    n = q.shape[1]
    if src.shape[1] < n:
        return np.empty(0)
    src = src.astype(np.float64); q = q.astype(np.float64)
    c = signal.fftconvolve(src, q[:, ::-1], mode='valid', axes=1).sum(axis=0)
    e = np.r_[0, np.cumsum((src * src).sum(axis=0))]
    w = e[n:] - e[:-n]
    qq = float((q * q).sum())
    # Near-empty windows give round-off ratios far above 1; they carry no evidence.
    floor = max(1e-9, .05 * qq)
    out = np.zeros_like(c)
    ok = w > floor
    out[ok] = c[ok] / np.sqrt(w[ok] * qq)
    return np.clip(out, -1, 1)


def _parabola(y, k):
    if 0 < k < len(y) - 1:
        a, b, c = y[k - 1], y[k], y[k + 1]
        d = a - 2 * b + c
        if d < 0:
            return float(np.clip(.5 * (a - c) / d, -.5, .5))
    return 0.


CLIP = np.arange(-50, 51, 5)   # +-1 s, every 0.1 s


def clip_score(O, S, i, j, r):
    idx_o = i + CLIP
    idx_s = np.round(j + r * CLIP).astype(int)
    ok = (idx_o >= 0) & (idx_o < len(O)) & (idx_s >= 0) & (idx_s < len(S))
    if ok.sum() < len(CLIP) * .8:
        return -1.
    return float(np.mean(np.sum(O[idx_o[ok]] * S[idx_s[ok]], axis=1)))


def picture_positions(O, Od, S, Sd, times_u, r_list):
    """Per sample: (source frame index float, score, margin, ratio) or None."""
    idx = np.round(times_u * FPS).astype(int)
    valid = (idx >= 50) & (idx < len(O) - 50)
    results = [None] * len(times_u)
    q = O[np.clip(idx, 0, len(O) - 1)]
    for start in range(0, len(q), 64):
        sims = q[start:start + 64] @ S.T
        for row in range(len(sims)):
            k = start + row
            i = idx[k]
            if not valid[k] or Od[i] < 6:
                continue
            # Static clips cannot fix time: require change across the clip.
            change = 1 - float(np.mean(O[i + CLIP] @ O[i]))
            if change < .04:
                continue
            s = sims[row]
            order = np.argpartition(-s, 60)[:60]
            order = order[np.argsort(-s[order])]
            cands = []
            for j in order:
                if all(abs(j - c) > FPS * 1.5 for c in cands):
                    cands.append(int(j))
                if len(cands) >= 8:
                    break
            scored = []
            for j in cands:
                best = (-2, j, 1.)
                for r in r_list:
                    for jj in range(j - 8, j + 9):
                        v = clip_score(O, S, i, jj, r)
                        if v > best[0]:
                            best = (v, jj, r)
                scored.append(best)
            scored.sort(key=lambda x: -x[0])
            v, j, r = scored[0]
            margin = v - max([x[0] for x in scored[1:] if abs(x[1] - j) > FPS * 1.5] or [-1])
            if v < .80 or margin < .03 or Sd[min(j, len(Sd) - 1)] < 6:
                continue
            curve = np.array([clip_score(O, S, i, jj, r) for jj in range(j - 10, j + 11)])
            if curve[10] - max(curve[0], curve[-1]) < .01:
                continue          # flat in time: slow pan / static
            kk = int(np.argmax(curve))
            results[k] = (j - 10 + kk + _parabola(curve, kk), v, margin, r)
    return results


def estimate_ratio(times_u, pos):
    pts = [(u, p[0] / FPS) for u, p in zip(times_u, pos) if p is not None]
    slopes = []
    for a in range(len(pts)):
        for b in range(a + 1, min(len(pts), a + 30)):
            du = pts[b][0] - pts[a][0]
            if 15 < du < 120:
                sl = (pts[b][1] - pts[a][1]) / du
                if .8 < sl < 1.25:
                    slopes.append(sl)
    if not slopes:
        return None
    med = float(np.median(slopes))
    near = min(KNOWN, key=lambda x: abs(x - med))
    return near if abs(near - med) < 1e-3 else med


def locate_audio(qfeat, Z, centre, half_search):
    """Return (source zoomed index of window start, corr, margin) near centre, or None."""
    lo = max(0, int(centre - half_search)); hi = min(Z.shape[1], int(centre + half_search) + qfeat.shape[1])
    c = _ncc(Z[:, lo:hi], qfeat)
    if len(c) == 0:
        return None
    k = int(np.argmax(c)); v = float(c[k])
    alt = c.copy(); alt[max(0, k - 30):k + 31] = -2
    margin = v - float(alt.max()) if len(c) > 61 else v
    return lo + k + _parabola(c, k), v, margin


def measure(video, audio, audio_stream, audio_offset, source, source_stream, video_crop='', source_crop='',
            step=2., cache_dir=None, source_audio_offset=None):
    """audio_offset: delivered audio t=0 position on the delivered video timeline (seconds after first frame)."""
    sv0, sa0 = starts(source, source_stream)
    if source_audio_offset is not None:
        sa0 = sv0 + source_audio_offset
    O, Od = decode_frames(video, video_crop, None)
    S, Sd = decode_frames(source, source_crop, cache_dir)
    Fo = decode_audio_features(audio, audio_stream, None)
    Fs = decode_audio_features(source, source_stream, cache_dir)
    dur = len(O) / FPS
    times_u = np.arange(2., dur - 2., step)
    # Pass 1 across candidate ratios on a subsample, then the full pass at one ratio.
    sub = times_u[::4]
    p1 = picture_positions(O, Od, S, Sd, sub, KNOWN)
    r = estimate_ratio(sub, p1) or 1.
    pos = picture_positions(O, Od, S, Sd, times_u, (r,))
    # Isolated picture positions (no agreeing neighbour) are treated as false matches.
    off = [None if p is None else p[0] / FPS - r * u for u, p in zip(times_u, pos)]
    for k, o in enumerate(off):
        if o is None:
            continue
        nb = [off[m] for m in range(max(0, k - 3), min(len(off), k + 4)) if m != k and off[m] is not None]
        if not any(abs(o - x) < .15 for x in nb):
            pos[k] = None
    Z = ndimage.zoom(Fs[:-1], (1, 1 / r), order=1).astype(np.float32)   # Z index m <-> source audio time sa0 + m*r/100
    W = 400
    rows = []
    for u, p in zip(times_u, pos):
        row = dict(t=round(float(u), 3), picture_src=None, audio_src=None, error=None, status='')
        i0 = int(round((u - audio_offset - W / 200) * 100))
        if i0 < 0 or i0 + W > Fo.shape[1]:
            row['status'] = 'outside_audio'; rows.append(row); continue
        q = Fo[:-1, i0:i0 + W]
        if float(np.median(Fo[-1, i0:i0 + W])) < .02:
            row['status'] = 'silent'; rows.append(row); continue
        ps = None if p is None else sv0 + p[0] / FPS
        row['picture_src'] = None if ps is None else round(ps, 4)
        found = None
        if ps is not None:
            centre = (ps - r * W / 200 - sa0) * 100 / r
            found = locate_audio(q, Z, centre, 800)
            if found and not (found[1] >= .5 and found[2] >= .08):
                found = None
        if found is None:
            g = locate_audio(q, Z, Z.shape[1] / 2, Z.shape[1])
            if g and g[1] >= .6 and g[2] >= .12:
                found = g; row['global'] = True
        if found is None:
            row['status'] = 'non_source_audio' if ps is not None else 'no_reference'
            rows.append(row); continue
        a_src = sa0 + (found[0] * r) / 100 + r * W / 200
        row['audio_src'] = round(a_src, 4); row['audio_corr'] = round(found[1], 3)
        if ps is None:
            row['status'] = 'audio_only'
        else:
            row['error'] = round((a_src - ps) / r, 4)
            # Seconds apart is not a timing error: the delivered picture is
            # footage reused from elsewhere (recap, preview, clip-built OP).
            row['status'] = 'reused_picture' if abs(row['error']) > 5 else 'measured'
        rows.append(row)
    return summarize(rows, r, dur), rows


def summarize(rows, r, dur, step=2.):
    m = [x for x in rows if x['status'] == 'measured']
    e = np.array([abs(x['error']) for x in m]) if m else np.empty(0)
    gross = []
    run = []
    for x in rows:
        if x['status'] == 'measured' and abs(x['error']) > .2:
            run.append(x)
        elif x['status'] == 'measured':
            if len(run) >= 2:
                gross.append([run[0]['t'], run[-1]['t'], round(float(np.median([y['error'] for y in run])), 3)])
            run = []
    if len(run) >= 2:
        gross.append([run[0]['t'], run[-1]['t'], round(float(np.median([y['error'] for y in run])), 3)])
    # Repeated sound: delivered audio steps back in the source recording.
    # Only well-located audio counts; weak global matches are classification only.
    located = [x for x in rows if x.get('audio_src') is not None and (not x.get('global') or x['audio_corr'] >= .7)]
    replays = []
    for a, b in zip(located[:-1], located[1:]):
        expected = r * (b['t'] - a['t'])
        back = a['audio_src'] + expected - b['audio_src']
        if back > .3 and b['t'] - a['t'] <= 3 * step:
            replays.append([a['t'], b['t'], round(float(back), 3)])
    counts = {}
    for x in rows:
        counts[x['status']] = counts.get(x['status'], 0) + 1
    s = dict(duration=round(dur, 3), ratio=r, samples=len(rows), counts=counts,
             measured=len(m),
             median_abs_ms=round(float(np.median(e)) * 1000, 1) if len(e) else None,
             p95_abs_ms=round(float(np.quantile(e, .95)) * 1000, 1) if len(e) else None,
             max_abs_ms=round(float(e.max()) * 1000, 1) if len(e) else None,
             signed_median_ms=round(float(np.median([x['error'] for x in m])) * 1000, 1) if m else None,
             within_45ms=round(float(np.mean(e <= .045)), 4) if len(e) else None,
             within_100ms=round(float(np.mean(e <= .1)), 4) if len(e) else None,
             gross_spans=gross, replays=replays,
             non_source_audio_s=counts.get('non_source_audio', 0) * step,
             reused_picture_s=counts.get('reused_picture', 0) * step)
    audible = len(rows) - counts.get('silent', 0) - counts.get('outside_audio', 0)
    s['coverage'] = round(len(m) / max(1, audible), 4)
    s['verdict'] = verdict(s)
    return s


def verdict(s):
    if not s['measured']:
        return 'UNMEASURABLE'
    problems = []
    if s['within_100ms'] < .95: problems.append('within100<95%')
    if s['p95_abs_ms'] > 100: problems.append('p95>100ms')
    if s['gross_spans']: problems.append('gross_spans')
    if s['replays']: problems.append('replayed_audio')
    if s['coverage'] < .6: problems.append('coverage<60%')
    return 'PASS' if not problems else 'FAIL: ' + ','.join(problems)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--video', required=True, help='Delivered video (target, or exported mkv)')
    p.add_argument('--audio', help='Delivered audio (defaults to --video)')
    p.add_argument('--audio-stream', type=int, default=0)
    p.add_argument('--audio-offset', type=float, help='Delivered audio start on video timeline; default from stream start times')
    p.add_argument('--source', required=True); p.add_argument('--source-stream', type=int, default=0)
    p.add_argument('--video-crop', default=''); p.add_argument('--source-crop', default='')
    p.add_argument('--cache-dir'); p.add_argument('--out', required=True)
    a = p.parse_args()
    audio = a.audio or a.video
    if a.audio_offset is None:
        if audio == a.video:
            v0, a0 = starts(a.video, a.audio_stream); a.audio_offset = a0 - v0
        else:
            a.audio_offset = 0.
    summary, rows = measure(a.video, audio, a.audio_stream, a.audio_offset, a.source, a.source_stream,
                            a.video_crop, a.source_crop, cache_dir=a.cache_dir)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / 'accuracy.json').write_text(json.dumps(summary, indent=2))
    with (out / 'accuracy.csv').open('w', newline='') as f:
        keys = ['t', 'status', 'picture_src', 'audio_src', 'audio_corr', 'error']
        w = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore'); w.writeheader(); w.writerows(rows)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    sys.exit(main())
