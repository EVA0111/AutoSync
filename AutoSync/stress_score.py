#!/usr/bin/env python3
"""Run the engine on stress_cases.py targets and score its plan against the truth.

    python stress_score.py --source S.mp4 --cases DIR [--only NAME,...] [--method standard]

For every 0.25 s of target time it compares the plan's source time with the
true one. Source pieces must map within 40 ms (timing share and p95 reported);
"none" pieces (inserted footage, black) must not be mapped to source audio.
Holds and the 0.3 s around every true edit are not scored: what is right
there is a placement choice, not a timing fact. Writes DIR/<name>/score.json
and prints one line per case; exit status 1 when any case fails.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
STEP, EDGE, TOL = .25, .3, .04


def plan_source_times(plan, times):
    """Source time the plan plays at each target time (nan when it keeps target audio)."""
    out = np.full(len(times), np.nan)
    for s in plan['segments']:
        if s['kind'] != 'audio':
            continue
        sel = (times >= s['target_start']) & (times < s['target_end'])
        out[sel] = s['source_start'] + (times[sel] - s['target_start']) * s.get('speed', 1.)
    return out


def truth_source_times(truth, times):
    """True source time per target time; nan for non-source; None-mask for unscored."""
    src = np.full(len(times), np.nan)
    scored = np.zeros(len(times), bool)
    for p in truth['pieces']:
        inside = (times >= p['start'] + EDGE) & (times < p['end'] - EDGE)
        if p['kind'] == 'src':
            src[inside] = p['source_start'] + (times[inside] - p['start']) * p.get('speed', truth['speed'])
        if p['kind'] != 'hold':
            scored |= inside
    return src, scored


def score(plan, truth, video_start=0.):
    """Truth is in target container time; plans count from the first target frame."""
    end = max(p['end'] for p in truth['pieces'])
    t = np.arange(0, end, STEP)
    pred = plan_source_times(plan, t - video_start)
    true, scored = truth_source_times(truth, t)
    is_src = scored & ~np.isnan(true)
    is_none = scored & np.isnan(true)
    err = np.abs(pred[is_src] - true[is_src])
    mapped = ~np.isnan(err)
    good = mapped & (err <= TOL)
    res = dict(
        source_seconds=float(is_src.sum() * STEP),
        within_40ms=float(good.mean()) if len(err) else 1.,
        unmatched_source=float((~mapped).mean()) if len(err) else 0.,
        p95_ms=float(np.percentile(err[mapped], 95) * 1000) if mapped.any() else None,
        max_ms=float(err[mapped].max() * 1000) if mapped.any() else None,
        false_match_seconds=float((~np.isnan(pred[is_none])).sum() * STEP),
    )
    bad = t[is_src][mapped & (err > TOL)]
    res['wrong_at'] = [round(float(x), 2) for x in bad[:12]]
    res['pass'] = bool(res['within_40ms'] >= .97 and res['false_match_seconds'] <= 1. and
                       (res['p95_ms'] or 0) <= 40)
    return res


def video_start(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=start_time',
                          '-of', 'csv=p=0', str(path)], stdout=subprocess.PIPE, text=True).stdout.strip()
    return float(out or 0)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--source', required=True); p.add_argument('--cases', required=True, type=Path)
    p.add_argument('--only'); p.add_argument('--method', default='standard')
    p.add_argument('--rerun', action='store_true', help='Run the engine again even if a plan exists')
    a = p.parse_args()
    names = a.only.split(',') if a.only else sorted(d.name for d in a.cases.iterdir() if (d / 'truth.json').exists())
    failed = 0
    for name in names:
        case = a.cases / name
        engine = case / f'engine_{a.method}'
        if a.rerun and engine.exists():
            shutil.rmtree(engine)
        if not (engine / "plan.json").exists():
            cmd = [sys.executable, str(ROOT / 'autosync.py'), '--source', a.source, '--audio', a.source,
                   '--target', str(case / 'target.mkv'), '--reference', str(case / 'target.mkv'),
                   '--out', str(engine), '--sync-method', a.method, '--analyze-only']
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=ROOT, text=True,
                               encoding='utf-8', errors='replace')
            (case / f'engine_{a.method}.log').write_text(r.stdout, encoding='utf-8')
            if not (engine / 'plan.json').exists():
                print(f'{name:24} NO PLAN  {r.stdout.strip().splitlines()[-1][:200] if r.stdout.strip() else ""}')
                failed += 1
                continue
        plan = json.loads((engine / 'plan.json').read_text(encoding='utf-8'))
        res = score(plan, json.loads((case / 'truth.json').read_text(encoding='utf-8')), video_start(case / 'target.mkv'))
        (case / f'score_{a.method}.json').write_text(json.dumps(res, indent=1), encoding='utf-8')
        failed += not res['pass']
        print(f"{name:24} {'PASS' if res['pass'] else 'FAIL'}  in40={res['within_40ms']:.3f} "
              f"unmatched={res['unmatched_source']:.3f} p95={res['p95_ms']} max={res['max_ms']} "
              f"false={res['false_match_seconds']} wrong_at={res['wrong_at'][:6]}", flush=True)
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
