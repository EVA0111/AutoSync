#!/usr/bin/env python3
"""Check typesetting placement frame by frame on stress_cases.py targets.

    python stress_typeset.py --source S.mp4 --cases DIR [--only NAME,...]

Writes signs.ass timed to the source: one sign per shot (from a scene cut to
the next, the classic sign) plus a mid-shot sign in each. It syncs them with
subtitle_sync.py (encode-to-encode, reusing the stress engine's plan) and
checks every target frame each sign is shown on against truth.json:
the frame must show a source frame the sign covered. Prints, per case, the
share of signs with every frame right and the edge errors in frames.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from subtitle_formats import Document
from subtitle_typeset import FrameGrid, scene_cuts, video_grid

ROOT = Path(__file__).resolve().parent
HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 480

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sign,Arial,30,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,8,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def ass_time(t):
    cs = int(round(t * 100))
    return f'{cs // 360000}:{cs // 6000 % 60:02}:{cs // 100 % 60:02}.{cs % 100:02}'


def make_signs(source, lo, hi, path):
    g = video_grid(source)
    cuts = [c for c in scene_cuts(source) if lo <= c <= hi]
    lines, truth = [], []
    for a, b in zip(cuts, cuts[1:]):
        k0, k1 = g.first_shown(a + g.origin), g.first_shown(b + g.origin)
        if k1 - k0 < 12:
            continue
        for f0, f1, kind in [(k0, k1, 'shot'), (k0 + (k1 - k0) // 3, k0 + 2 * (k1 - k0) // 3, 'mid')]:
            lines.append(f'Dialogue: 0,{ass_time(g.ass_time(f0))},{ass_time(g.ass_time(f1))},Sign,,0,0,0,,'
                         f'{{\\pos(320,40)}}{kind} {f0}')
            truth.append((f0, f1, kind))
    path.write_text(HEAD + '\n'.join(lines) + '\n', encoding='utf-8')
    return g, truth


def true_source_frame(truth, grid_src, t):
    """Source frame shown at target container time t (truth is in container time)."""
    for p in truth['pieces']:
        if p['start'] <= t < p['end']:
            if p['kind'] == 'src':
                return grid_src.frame_at(p['source_start'] + (t - p['start']) * truth['speed'] - grid_src.origin)
            return None
    return None


def check(case, source, method='standard'):
    out = case / 'typeset'
    if out.exists():
        import shutil
        shutil.rmtree(out)
    signs = case / 'signs.ass'
    pieces = json.loads((case / 'truth.json').read_text())
    srcs = [p for p in pieces['pieces'] if p['kind'] == 'src']
    lo = min(p['source_start'] for p in srcs)
    hi = max(p['source_start'] + (p['end'] - p['start']) * pieces['speed'] for p in srcs)
    gs, want = make_signs(source, lo, hi, signs)
    cmd = [sys.executable, str(ROOT / 'subtitle_sync.py'), '--mode', 'encodes', '--subtitle', str(signs),
           '--source-video', source, '--target-media', str(case / 'target.mkv'), '--out', str(out),
           '--picture-plan', str(case / f'engine_{method}' / 'plan.json')]
    r = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                       errors='replace')
    files = sorted(out.glob('*.ass')) if out.exists() else []
    files = [f for f in files if f.name != 'input_subtitle.ass']
    if not files:
        return dict(error=r.stdout.strip().splitlines()[-1] if r.stdout.strip() else 'no output')
    gt = video_grid(case / 'target.mkv')
    doc = Document(files[0])
    end = max(q['end'] for q in pieces['pieces'])
    true = np.array([true_source_frame(pieces, gs, gt.mid(n) + gt.origin) if gt.mid(n) < end else None
                     for n in range(int(end * gt.fps) + 2)], dtype=object)
    true = np.array([-1 if k is None else k for k in true])
    by_label = {}
    for c in doc.cues:
        by_label.setdefault(c.plain, []).append(c)
    report = json.loads((out / 'subtitle_report.json').read_text(encoding='utf-8'))
    unmapped = {r['cue'] for r in report['items'] if r['status'] == 'unmapped'}
    ok = missing = wrong = absent = 0
    dropped_right = dropped_wrong = 0
    errors = []
    for i, (f0, f1, kind) in enumerate(want, 1):
        cues = by_label.get(f'{kind} {f0}', [])
        should = set(np.flatnonzero((true >= f0) & (true < f1)).tolist())
        if i in unmapped:
            # Left at its original time in the DRAFT and reported: right only if the
            # target really has none of its frames.
            if should:
                dropped_wrong += 1; errors.append((kind, f0, 'unmapped', len(should)))
            else:
                dropped_right += 1; ok += 1
            continue
        if not cues:
            missing += bool(should)
            continue
        shown = set()
        for c in cues:
            shown |= set(range(gt.first_shown(c.start), gt.first_shown(c.end)))
        extra, lacking = len(shown - should), len(should - shown)
        ok += not extra and not lacking
        wrong += extra; absent += lacking
        if extra or lacking:
            errors.append((kind, f0, extra, lacking))
    return dict(signs=len(want), all_frames_right=ok, unmapped_correctly=dropped_right, unmapped_wrongly=dropped_wrong,
                missing=missing, extra_frames=wrong, absent_frames=absent,
                examples=errors[:8])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--source', required=True); p.add_argument('--cases', required=True, type=Path)
    p.add_argument('--only')
    a = p.parse_args()
    names = a.only.split(',') if a.only else sorted(d.name for d in a.cases.iterdir()
                                                    if (d / 'engine_standard' / 'plan.json').exists())
    for name in names:
        res = check(a.cases / name, a.source)
        (a.cases / name / 'typeset.json').write_text(json.dumps(res, indent=1))
        print(f'{name:24} {res}', flush=True)


if __name__ == '__main__':
    main()
