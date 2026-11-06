"""Regression guard for the edits found in real episode pairs (censored / re-edited dubs).

Real dubs keep inventing edits no synthetic case has, so every edit AutoSync
reports on the real test pairs is recorded once (after it was checked by eye)
and must keep being reported. Each case is analysed (analyze-only), its
censorship.scenes are compared with the recorded list:

* an edit in the record that is no longer reported (by any kind, including an
  unexplained difference) is a MISS and fails the check;
* a report that matches nothing in the record is NEW: it fails until it is
  checked and recorded (or fixed), so no change slips by unseen.

Edges may move by up to --edge seconds. Usage:
  real_edits.py --cases cases_edits.json --out DIR            check
  real_edits.py --cases cases_edits.json --out DIR --record   (re)write the record from this run
The record lives in the cases file: each case has "edits": [[kind, start, end], ...].
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def analyse(case, out):
    plan = out / 'plan.json'
    if not plan.exists():
        cmd = [sys.executable, str(ROOT / 'autosync.py'), '--source', case['source'], '--audio', case['source'],
               '--target', case['target'], '--reference', case['target'], '--audio-stream', '0',
               '--reference-stream', '0', '--out', str(out), '--analyze-only']
        log = out.with_suffix('.log')
        with open(log, 'w', encoding='utf-8') as f:
            if subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode:
                raise RuntimeError(f'analysis failed, see {log}')
    return json.loads(plan.read_text(encoding='utf-8'))


def found(plan):
    import censorship
    return [[s['kind'], round(s['start'], 2), round(s['end'], 2)] for s in censorship.scenes(plan)]


def overlap(a, b, edge):
    return min(a[2], b[2]) - max(a[1], b[1]) > -edge


def compare(record, now, edge):
    miss = [r for r in record if not any(overlap(r, n, edge) for n in now)]
    new = [n for n in now if not any(overlap(r, n, edge) for r in record)]
    return miss, new


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--cases', required=True, type=Path); p.add_argument('--out', required=True, type=Path)
    p.add_argument('--record', action='store_true'); p.add_argument('--edge', type=float, default=.5)
    p.add_argument('--only')
    a = p.parse_args()
    cases = json.loads(a.cases.read_text(encoding='utf-8'))
    a.out.mkdir(parents=True, exist_ok=True)
    failed = 0
    for case in cases:
        if a.only and case['name'] not in a.only.split(','):
            continue
        plan = analyse(case, a.out / case['name'])
        now = found(plan)
        check = plan.get('picture_check') or {}
        if a.record:
            case['edits'] = now
            print(f"{case['name']:>4}: recorded {len(now)} edits")
            continue
        miss, new = compare(case.get('edits', []), now, a.edge)
        ok = not miss and not new
        failed += not ok
        print(f"{case['name']:>4}: {'PASS' if ok else 'FAIL'}  {len(now)} edits, picture check "
              f"{check.get('confirmed_share', 0):.1%}" + ''.join(f'\n      MISS {m}' for m in miss)
              + ''.join(f'\n      NEW  {n}' for n in new))
    if a.record:
        a.cases.write_text(json.dumps(cases, indent=1), encoding='utf-8')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
