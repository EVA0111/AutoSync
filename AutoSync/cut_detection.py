"""Locate edition cuts using dense evidence under the mappings on each side."""
import numpy as np
from scipy.ndimage import uniform_filter1d


def locate_cut(left, right, ref, energy, source, rate=50):
    lo = max(0., left['last'] - 4.)
    hi = max(lo + 1 / rate, right['first'] + 4.)
    midpoint = (left['last'] + right['first']) / 2
    result = dict(time=midpoint, uncertainty_start=lo, uncertainty_end=hi,
                  confidence='uncertain', method='estimated cut; insufficient audio evidence')
    if ref is None or source is None:
        return result
    hi = min(hi, (ref.shape[1] - 1) / rate)
    ticks = np.arange(int(np.ceil(lo * rate)), int(np.floor(hi * rate)) + 1)
    if len(ticks) < 10:
        return result
    times = ticks / rate
    q = ref[:, ticks]
    qpower = np.sum(q * q, axis=0)
    scores = []
    for m in (left, right):
        pos = (m['speed'] * times + m['offset']) * rate
        valid = (pos >= 0) & (pos <= source.shape[1] - 1)
        p = np.clip(pos, 0, source.shape[1] - 1)
        a = np.floor(p).astype(int); b = np.minimum(a + 1, source.shape[1] - 1)
        x = source[:, a] * (1 - (p - a)) + source[:, b] * (p - a)
        # 100 ms context avoids the previous 1.4 s window blurring a hard cut.
        dot = uniform_filter1d(np.sum(x * q, axis=0), 5)
        denom = np.sqrt(uniform_filter1d(np.sum(x * x, axis=0), 5) *
                        uniform_filter1d(qpower, 5))
        c = np.divide(dot, denom, out=np.zeros_like(dot), where=denom > 1e-8)
        c[~valid] = 0
        if energy is not None:
            e = np.zeros(len(ticks)); ok = ticks < len(energy); e[ok] = energy[ticks[ok]]
            c[e < max(1e-10, float(np.max(e)) * 1e-5)] = 0
        scores.append(c)
    old, new = scores
    evidence = old - new
    # A split uses old correspondence BEFORE it and new correspondence AFTER it.
    objective = np.r_[0., np.cumsum(evidence)] / rate
    best = float(objective.max())
    plausible = np.flatnonzero(objective >= best - .04)
    # A flat maximum (silence/repeated content) stays uncertain, never 'quiet-snapped'.
    k = int(plausible[len(plausible) // 2])
    t = min(hi, float(times[0] + k / rate))
    a = float(times[0] + plausible[0] / rate)
    b = min(hi, float(times[0] + plausible[-1] / rate))
    before = slice(max(0, k - rate * 2), k)
    after = slice(k, min(len(ticks), k + rate * 2))
    def mean(x): return float(np.mean(x)) if len(x) else 0.
    supported = (mean(old[before]) >= .3 and mean(new[after]) >= .3 and
                 mean(evidence[before]) >= .15 and mean(-evidence[after]) >= .15 and
                 k >= rate // 2 and len(ticks) - k >= rate // 2 and b - a <= .3)
    result.update(time=t, uncertainty_start=a if supported else lo,
                  uncertainty_end=b if supported else hi,
                  confidence='supported' if supported else 'uncertain',
                  method='dense audio cut match' if supported else 'estimated cut; weak or ambiguous audio')
    return result


def correspondence(model, ticks, ref, energy, source, rate=50):
    """Per reference tick: local (100 ms) audio similarity under a mapping (0 in silence)."""
    times = ticks / rate
    q = ref[:, ticks]
    pos = (model['speed'] * times + model['offset']) * rate
    valid = (pos >= 0) & (pos <= source.shape[1] - 1)
    p = np.clip(pos, 0, source.shape[1] - 1)
    a = np.floor(p).astype(int); b = np.minimum(a + 1, source.shape[1] - 1)
    x = source[:, a] * (1 - (p - a)) + source[:, b] * (p - a)
    dot = uniform_filter1d(np.sum(x * q, axis=0), 5)
    denom = np.sqrt(uniform_filter1d(np.sum(x * x, axis=0), 5) * uniform_filter1d(np.sum(q * q, axis=0), 5))
    c = np.divide(dot, denom, out=np.zeros_like(dot), where=denom > 1e-8)
    c[~valid] = 0
    if energy is not None:
        e = np.zeros(len(ticks)); ok = ticks < len(energy); e[ok] = energy[ticks[ok]]
        c[e < max(1e-10, float(np.max(e)) * 1e-5)] = 0
    return c


def place_insert(left, right, starts, length, ref, energy, source, rate=50, context=2., margin=.1, near=.25):
    """Index into `starts` (reference seconds) of target-only audio `length` s long
    that the audio singles out: the left mapping's audio matches up to it and the
    right mapping's from its end. None when the audio does not decide (silence,
    music both editions share, a different dub language) or `starts` is empty.

    For target-only footage the pictures cannot place (a held shot shown longer):
    every start fits them, so the audio decides or the caller's fallback does.
    """
    if ref is None or source is None or not len(starts):
        return None
    starts = np.asarray(starts, float)
    t0 = max(0., starts[0] - context); t1 = min((ref.shape[1] - 1) / rate, starts[-1] + length + context)
    ticks = np.arange(int(np.ceil(t0 * rate)), int(np.floor(t1 * rate)) + 1)
    n = int(round(length * rate))
    if len(ticks) < n + rate:
        return None
    ca = np.r_[0., np.cumsum(correspondence(left, ticks, ref, energy, source, rate))] / rate
    cb = np.r_[0., np.cumsum(correspondence(right, ticks, ref, energy, source, rate))] / rate
    i = np.clip(np.round((starts - ticks[0] / rate) * rate).astype(int), 0, len(ticks))
    j = np.clip(i + n, 0, len(ticks))
    score = ca[i] + cb[-1] - cb[j]
    k = int(np.argmax(score))
    far = np.abs(starts - starts[k]) > near
    if not far.any() or score[k] - float(score[far].max()) < margin:
        return None
    # The audio must really match on both sides of the chosen span (a second each).
    before = (ca[i[k]] - ca[max(0, i[k] - rate)]) / (min(rate, i[k]) / rate or 1)
    after = (cb[min(len(ticks), j[k] + rate)] - cb[j[k]]) / (min(rate, len(ticks) - j[k]) / rate or 1)
    if min(i[k], len(ticks) - j[k]) < rate // 2 or before < .3 or after < .3:
        return None
    return k


def source_cuts(segments):
    """Derive skipped source intervals from current edits; never cache stale cuts."""
    cuts = []
    indices=[i for i,s in enumerate(segments) if s['kind']=='audio']
    for li,ri in zip(indices[:-1],indices[1:]):
        if any(s['kind']!='verified_gap' for s in segments[li+1:ri]):continue
        left,right=segments[li],segments[ri]
        if left['kind'] != 'audio' or right['kind'] != 'audio':
            continue
        end = left['source_start'] + (left['target_end'] - left['target_start']) * left['speed']
        start = right['source_start']
        if start - end > .25:
            cuts.append(dict(target_time=left['target_end'], source_start=end,
                             source_end=start, removed_seconds=start-end))
    return cuts
