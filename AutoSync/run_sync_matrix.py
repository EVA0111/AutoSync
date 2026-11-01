#!/usr/bin/env python3
"""Run every case x output mode x matching method and MEASURE delivered sync.

Cases come from a local JSON file (private media is never committed):
  {"cases": [{"name": "1", "source": "...", "target": "...",
              "audio": "<optional, defaults to source>",
              "audio_stream": 0, "reference_stream": 0}]}

Each run: autosync.py -> exit status/log -> sync_accuracy.py on the delivered
file (target + synced.flac at 0 ms for Full target; the exported .mkv for the
other modes). A run that refuses to export is BLOCKED, never a pass.
"""
import argparse, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODES = {
    'full': ([], None),
    'main': (['--main-only'], 'main_episode.mkv'),
    'keep_op_ed': (['--keep-target-op-ed'], 'full_episode.mkv'),
    'remove_unmatched': (['--remove-unmatched-video'], 'edited_episode.mkv'),
}
METHODS = ('standard', 'ai_assisted')


def last_error(log):
    lines = [x for x in log.splitlines() if x.startswith(('ERROR', 'FAILED'))]
    return lines[-1][:600] if lines else log.strip().splitlines()[-1][:600] if log.strip() else ''


def run_one(case, mode, method, out_root, cache, extra):
    out = out_root / f"{case['name']}_{mode}_{method}"
    result = dict(case=case['name'], mode=mode, method=method, out=str(out))
    if (out / 'result.json').exists():
        return json.loads((out / 'result.json').read_text())
    out.mkdir(parents=True, exist_ok=True)
    audio = case.get('audio') or case['source']
    cmd = [sys.executable, str(ROOT / 'autosync.py'), '--source', case['source'], '--audio', audio,
           '--target', case['target'], '--reference', case['target'],
           '--audio-stream', str(case.get('audio_stream', 0)), '--reference-stream', str(case.get('reference_stream', 0)),
           '--out', str(out / 'engine'), '--sync-method', method, *MODES[mode][0], *extra]
    t0 = time.time()
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=ROOT)
    log = p.stdout.decode('utf-8', errors='replace')
    (out / 'engine.log').write_text(log, encoding='utf-8')
    result.update(exit_code=p.returncode, engine_seconds=round(time.time() - t0, 1))
    eng = out / 'engine'
    plan = json.loads((eng / 'plan.json').read_text()) if (eng / 'plan.json').exists() else {}
    result['review_count'] = len(plan.get('review', []))
    result['rewinds'] = len(plan.get('source_rewinds', []))
    if p.returncode or not (eng / 'synced.flac').exists():
        result.update(status='BLOCKED', error=last_error(log))
    else:
        exported = MODES[mode][1]
        if exported and not (eng / exported).exists():
            # Some combinations (e.g. Full target with nothing to remove) export FLAC only.
            exported = None
        if exported:
            video, audio_args = eng / exported, []
        else:
            video, audio_args = Path(case['target']), ['--audio', str(eng / 'synced.flac'), '--audio-offset', '0']
        ev = [sys.executable, str(ROOT / 'sync_accuracy.py'), '--video', str(video), *audio_args,
              '--source', audio, '--source-stream', str(case.get('audio_stream', 0)),
              '--video-crop', plan.get('target_crop') or '', '--source-crop', plan.get('source_crop') or '',
              '--cache-dir', str(cache), '--out', str(out / 'accuracy')]
        q = subprocess.run(ev, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if q.returncode:
            result.update(status='EVAL_ERROR', error=q.stdout.decode(errors='replace')[-600:])
        else:
            acc = json.loads((out / 'accuracy' / 'accuracy.json').read_text())
            result.update(status=acc['verdict'], delivered=str(video), accuracy=acc)
    (out / 'result.json').write_text(json.dumps(result, indent=2))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--cases', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--cache', type=Path, help='Evaluator decode cache (default: <out>/.cache)')
    p.add_argument('--only-cases'); p.add_argument('--modes', default=','.join(MODES))
    p.add_argument('--methods', default=','.join(METHODS))
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--engine-arg', action='append', default=[], help='Extra autosync.py argument (repeatable)')
    a = p.parse_args()
    cases = json.loads(a.cases.read_text())['cases']
    if a.only_cases:
        keep = set(a.only_cases.split(',')); cases = [c for c in cases if c['name'] in keep]
    a.out.mkdir(parents=True, exist_ok=True)
    cache = a.cache or a.out / '.cache'
    rev = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, stdout=subprocess.PIPE, text=True).stdout.strip()
    dirty = bool(subprocess.run(['git', 'status', '--porcelain', '--', '.'], cwd=ROOT, stdout=subprocess.PIPE, text=True).stdout.strip())
    # Case varies fastest: concurrent runs never compute the same AI embeddings.
    jobs = [(c, m, k) for k in a.methods.split(',') for m in a.modes.split(',') for c in cases]
    with ThreadPoolExecutor(a.workers) as pool:
        futures = [pool.submit(run_one, c, m, k, a.out, cache, a.engine_arg) for c, m, k in jobs]
        results = []
        for f in futures:
            r = f.result(); results.append(r)
            acc = r.get('accuracy') or {}
            print(f"{r['case']:>6} {r['mode']:<17} {r['method']:<11} {r['status'][:48]:<48} "
                  f"med={acc.get('median_abs_ms')} p95={acc.get('p95_abs_ms')} in100={acc.get('within_100ms')} "
                  f"cov={acc.get('coverage')}", flush=True)
    summary = dict(engine_revision=rev + ('+dirty' if dirty else ''), results=results)
    (a.out / 'matrix.json').write_text(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
