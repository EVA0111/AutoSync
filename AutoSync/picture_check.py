"""Cross-check weakly supported timing sections against picture correspondence.

Audio anchors align the source soundtrack to the TARGET SOUNDTRACK. A target
soundtrack keeps a locally constant relationship to its picture (a dub delay;
it may change between reels, so it is not assumed constant per episode). A
weakly supported section whose audio/picture relationship differs strongly
from its nearest well-supported neighbour is matching a re-laid target track,
for example a re-recorded opening theme, not the picture the source audio
belongs to. Following it repeats or skips source audio.

Such a section is re-anchored on its pictures plus the neighbour's measured
audio/picture relationship and is always flagged for review. Well-supported
sections are never changed; nothing changes without dense, mutually
consistent picture matches inside the section.
"""
import numpy as np

DEVIATION = .25      # seconds of disagreement with the neighbouring relationship
AGREE = .10          # picture matches must agree within this
MIN_PICTURES = 3
STRONG = 8           # anchors for a section to serve as a reference


def _picture_offset(model, visual, speed):
    inside = visual[(visual[:, 0] >= model['first'] - 2) & (visual[:, 0] <= model['last'] + 2)]
    if len(inside) < MIN_PICTURES:
        return None
    off = inside[:, 1] - speed * inside[:, 0]
    med = float(np.median(off))
    agreeing = np.abs(off - med) <= AGREE
    if agreeing.sum() < MIN_PICTURES or agreeing.mean() < .6:
        return None
    return float(np.median(off[agreeing])), int(agreeing.sum())


def picture_checked_models(models, visual, speed):
    """Return (models, notes). Models are copied; unchecked ones are unchanged."""
    if visual is None or len(visual) < 8 or len(models) < 2:
        return models, []
    rows = []
    for m in models:
        p = _picture_offset(m, visual, speed)
        audio_off = m['offset'] + (m['speed'] - speed) * (m['first'] + m['last']) / 2
        rows.append(None if p is None else (audio_off - p[0], p[0], p[1]))
    out, notes = [], []
    for i, (m, r) in enumerate(zip(models, rows)):
        m = dict(m)
        refs = [(abs((x['first'] + x['last']) / 2 - (m['first'] + m['last']) / 2), j)
                for j, (x, q) in enumerate(zip(models, rows))
                if j != i and q is not None and x['anchors'] >= max(STRONG, 2 * m['anchors'])]
        if r is not None and refs:
            relation = rows[min(refs)[1]][0]
            if abs(r[0] - relation) > DEVIATION:
                notes.append(dict(start=m['first'], end=m['last'], confidence='estimated',
                                  reason=f'Audio timing disagrees with pictures by {r[0]-relation:+.3f}s '
                                         '(different target soundtrack here, e.g. re-laid theme song); '
                                         f'aligned to {r[2]} picture matches with the neighbouring audio/picture '
                                         f'offset {relation:+.3f}s; listen to this section'))
                m.update(speed=speed, offset=r[1] + relation, picture_checked=True)
        out.append(m)
    return out, notes
