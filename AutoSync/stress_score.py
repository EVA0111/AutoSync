#!/usr/bin/env python3
"""Run the engine on stress_cases.py targets and score its plan against the truth.

    python stress_score.py --source S.mp4 --cases DIR [--only NAME,...] [--method standard]

For every 0.25 s of target time it compares the plan's source time with the
true one. Source pieces must map within 40 ms (timing share and p95 reported);
"none" pieces (inserted footage, black) must not be mapped to source audio.
Censored-dub cases (truth "censorship"; built with stress_cases.py --censored)
use their own source.mkv, run with --censored-dub restore, and also score the
censorship report: removed scenes and their edges, replaced shots and false
replacements, dub-only material.
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


CENSOR_EDGE = .1         # removed-scene edges within 0.1 s (2-3 frames) count as found


def _overlap(a, b):
    return min(a[1], b[1]) - max(a[0], b[0])


def score_censorship(plan, truth):
    """Censorship report (censorship.scenes) against truth['censorship'].

    removed: every true removed scene must be reported (overlapping), with
    both edges within CENSOR_EDGE; no report may lie outside a true one.
    replaced: same-length covers must be reported where they are, and nothing
    else may be reported as replaced (a mosaic or zoom is not a replacement).
    A cover reported only as an unexplained difference counts as flagged, not
    missed (it is shown for review); an unexplained difference where nothing was
    edited is a false alarm. A silent miss fails the case.
    dub_only: dub-only material in source seconds (edge errors reported).
    """
    import censorship
    c = truth['censorship']
    found = censorship.scenes(plan)
    res = {}
    for kind, key in (('removed', 'removed'), ('replaced', 'replaced')):
        rep = [(x['start'], x['end']) for x in found if x['kind'] == kind]
        if kind == 'removed':            # adjacent reported pieces of one scene count together
            rep = [r for r in rep if r[1] - r[0] > 1e-3]
        edges, missed = [], 0
        for t in c[key]:
            hit = [r for r in rep if _overlap(r, t) > 0]
            if not hit:
                missed += 1; continue
            edges += [abs(min(h[0] for h in hit) - t[0]), abs(max(h[1] for h in hit) - t[1])]
        false = [r for r in rep if not any(_overlap(r, t) > 0 for t in c[key])]
        res[kind] = dict(true=len(c[key]), missed=missed, false=len(false),
                         false_seconds=round(sum(b - a for a, b in false), 3),
                         edge_max_ms=round(max(edges) * 1000, 1) if edges else None,
                         edge_median_ms=round(float(np.median(edges)) * 1000, 1) if edges else None,
                         edges_ok=round(float(np.mean(np.array(edges) <= CENSOR_EDGE)), 3) if edges else None)
    # Dub-only material is every forward source skip between consecutive audio
    # segments (the report lists one next to a removed scene with that scene).
    audio = [s for s in plan['segments'] if s['kind'] == 'audio']
    rep = []
    for x, y in zip(audio, audio[1:]):
        end = x['source_start'] + (x['target_end'] - x['target_start']) * x.get('speed', 1.)
        if y['source_start'] - end > .25:
            rep.append((end, y['source_start']))
    edges, missed = [], 0
    for t in c['dub_only']:
        hit = [r for r in rep if _overlap(r, t) > 0]
        if not hit:
            missed += 1; continue
        edges += [abs(min(h[0] for h in hit) - t[0]), abs(max(h[1] for h in hit) - t[1])]
    res['dub_only'] = dict(true=len(c['dub_only']), missed=missed,
                           false=sum(not any(_overlap(r, t) > 0 for t in c['dub_only']) for r in rep),
                           edge_max_ms=round(max(edges) * 1000, 1) if edges else None)
    odd = [(x['start'], x['end']) for x in found if x['kind'] == 'unexplained']
    edits = c['removed'] + c['replaced']
    reported = [(x['start'], x['end']) for x in found if x['kind'] == 'replaced']
    silent = [t for t in c['replaced'] if not any(_overlap(r, t) > 0 for r in reported + odd)]
    res['replaced']['flagged_only'] = sum(1 for t in c['replaced'] if not any(_overlap(r, t) > 0 for r in reported)
                                          and any(_overlap(r, t) > 0 for r in odd))
    res['replaced']['silent'] = len(silent)
    res['unexplained'] = dict(count=len(odd), false=sum(1 for r in odd if not any(_overlap(r, t) > 0 for t in edits)))
    rm, rp = res['removed'], res['replaced']
    res['pass'] = bool(rm['missed'] == 0 and rm['false'] == 0 and (rm['edges_ok'] in (None, 1.)) and
                       rp['false'] == 0 and rp['silent'] == 0 and res['unexplained']['false'] == 0 and
                       res['dub_only']['missed'] == 0)
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
        truth = json.loads((case / 'truth.json').read_text(encoding='utf-8'))
        # Censored-dub cases carry their own dub (source.mkv); the target is the clean original.
        source = str(case / 'source.mkv') if (case / 'source.mkv').exists() else a.source
        if not (engine / "plan.json").exists():
            cmd = [sys.executable, str(ROOT / 'autosync.py'), '--source', source, '--audio', source,
                   '--target', str(case / 'target.mkv'), '--reference', str(case / 'target.mkv'),
                   '--out', str(engine), '--analyze-only',
                   *(['--censored-dub', 'restore'] if 'censorship' in truth else [])]
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=ROOT, text=True,
                               encoding='utf-8', errors='replace')
            (case / f'engine_{a.method}.log').write_text(r.stdout, encoding='utf-8')
            if not (engine / 'plan.json').exists():
                print(f'{name:24} NO PLAN  {r.stdout.strip().splitlines()[-1][:200] if r.stdout.strip() else ""}')
                failed += 1
                continue
        plan = json.loads((engine / 'plan.json').read_text(encoding='utf-8'))
        res = score(plan, truth, video_start(case / 'target.mkv'))
        if 'censorship' in truth:
            res['censorship'] = score_censorship(plan, truth)
            res['timing_pass'] = res['pass']; res['pass'] = res['pass'] and res['censorship']['pass']
        (case / f'score_{a.method}.json').write_text(json.dumps(res, indent=1), encoding='utf-8')
        failed += not res['pass']
        print(f"{name:24} {'PASS' if res['pass'] else 'FAIL'}  in40={res['within_40ms']:.3f} "
              f"unmatched={res['unmatched_source']:.3f} p95={res['p95_ms']} max={res['max_ms']} "
              f"false={res['false_match_seconds']} wrong_at={res['wrong_at'][:6]}", flush=True)
        if 'censorship' in res:
            c = res['censorship']
            print(f"{'':24} censor {'PASS' if c['pass'] else 'FAIL'}  " + '  '.join(
                f"{k}: {v['true'] - v['missed']}/{v['true']} false={v['false']} edge_max={v['edge_max_ms']}ms"
                + (f" silent={v['silent']} flagged_only={v['flagged_only']}" if 'silent' in v else '')
                for k, v in c.items() if k not in ('pass', 'unexplained'))
                + f"  unexplained: {c['unexplained']['count']} false={c['unexplained']['false']}", flush=True)
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
