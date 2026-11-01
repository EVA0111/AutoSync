#!/usr/bin/env python3
"""Summarize a run_sync_matrix.py folder: delivered vs engine-induced error.

Delivered error is measured against the source's own audio/picture timing.
The target's native dub track can itself be offset from its picture; that
offset is measured separately (sync_accuracy.py on the untouched target) and
subtracted locally (nearest native samples by source position), leaving the
engine-induced error that the synchronizer actually controls.
"""
import argparse, csv, json
from pathlib import Path
import numpy as np


def rows(path):
    with open(path, newline='') as f:
        return [r for r in csv.DictReader(f) if r['status'] == 'measured']


def native_profile(path):
    if not Path(path).exists():
        return None
    r = rows(path)
    if len(r) < 10:
        return None
    a = np.array([[float(x['picture_src']), float(x['error'])] for x in r])
    return a[np.argsort(a[:, 0])]


def local_offset(profile, ps):
    for width in (30, 120):
        near = profile[np.abs(profile[:, 0] - ps) <= width, 1]
        if len(near) >= 3:
            return float(np.median(near))
    return float(np.median(profile[:, 1]))


def engine_stats(run_csv, profile):
    r = rows(run_csv)
    if not r or profile is None:
        return None
    e = np.array([float(x['error']) - local_offset(profile, float(x['picture_src'])) for x in r])
    a = np.abs(e)
    return dict(median_ms=round(float(np.median(a)) * 1000, 1), p95_ms=round(float(np.quantile(a, .95)) * 1000, 1),
                within_100=round(float(np.mean(a <= .1)), 4), within_45=round(float(np.mean(a <= .045)), 4))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('matrix', type=Path); p.add_argument('--native', type=Path, help='Folder of <case>/accuracy.csv native-target measurements')
    p.add_argument('--markdown', type=Path)
    a = p.parse_args()
    results = []
    for f in sorted(a.matrix.glob('*/result.json')):
        results.append(json.loads(f.read_text()))
    order = {'full': 0, 'main': 1, 'keep_op_ed': 2, 'remove_unmatched': 3}
    results.sort(key=lambda r: (r['case'], r['method'], order.get(r['mode'], 9)))
    lines = ['| Case | Method | Mode | Status | Delivered median / p95 ms | ≤100 ms | Coverage | Engine-induced median / p95 ms | Engine ≤100 ms | Notes |',
             '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in results:
        acc = r.get('accuracy') or {}
        prof = native_profile(a.native / r['case'] / 'accuracy.csv') if a.native else None
        eng = engine_stats(Path(r['out']) / 'accuracy' / 'accuracy.csv', prof) if acc else None
        r['engine_induced'] = eng
        note = (r.get('error') or '')[:140].replace('|', '/')
        if acc.get('replays'): note += f" replays={len(acc['replays'])}"
        if acc.get('gross_spans'): note += f" gross_spans={len(acc['gross_spans'])}"
        status = r['status'].split(':')[0]
        lines.append(f"| {r['case']} | {r['method']} | {r['mode']} | {status} | "
                     f"{acc.get('median_abs_ms', '–')} / {acc.get('p95_abs_ms', '–')} | {acc.get('within_100ms', '–')} | {acc.get('coverage', '–')} | "
                     f"{eng['median_ms'] if eng else '–'} / {eng['p95_ms'] if eng else '–'} | {eng['within_100'] if eng else '–'} | {note.strip()} |")
    text = '\n'.join(lines)
    print(text)
    if a.markdown:
        a.markdown.write_text(text + '\n', encoding='utf-8')
    (a.matrix / 'summary.json').write_text(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
