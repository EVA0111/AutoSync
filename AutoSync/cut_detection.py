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
