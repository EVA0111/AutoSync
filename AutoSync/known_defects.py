"""Expected defects of a TARGET RELEASE in the regression matrix.

Some target releases are themselves out of sync in places: their own picture
is re-timed against their own soundtrack (case 7, source 1255-1265 s: the
picture drifts 0.28 s ahead and snaps back while the target's own audio is
continuous). AutoSync keeps the soundtrack continuous there, as the target
does; following the picture would repeat audio.

Such a spot may be declared per case in the local cases file:

  "known_target_defects": [{"source_start": 1255, "source_end": 1265,
                            "max_error_s": 0.30, "reason": "..."}]

Windows are in SOURCE seconds (the evaluator's picture position), so one
declaration covers every output mode. The evaluator's measurement and verdict
are never changed. A run is reported as passing with a known target defect
only if its ONLY failures are gross spans whose every measured sample lies
inside a declared window and within that window's maximum error. Any other
failure, a larger error, or a span reaching outside the window still fails.
"""
import csv
from pathlib import Path


def problems(verdict):
    return [] if verdict == 'PASS' else verdict.split(':', 1)[1].strip().strip(',').split(',')


def explain(summary, rows, defects):
    """(status, explained) for one measured run.

    summary: accuracy.json dict; rows: accuracy.csv rows (t, status,
    picture_src, error); defects: the case's known_target_defects.
    """
    verdict = summary['verdict']
    found = [p for p in problems(verdict) if p]
    if not found or not defects or found != ['gross_spans']:
        return verdict, []
    explained = []
    for t0, t1, median in summary['gross_spans']:
        span = [r for r in rows if r.get('status') == 'measured' and t0 - 1e-6 <= float(r['t']) <= t1 + 1e-6]
        match = None
        for d in defects:
            if span and all(d['source_start'] <= float(r['picture_src']) <= d['source_end'] and
                            abs(float(r['error'])) <= d['max_error_s'] for r in span):
                match = d
                break
        if match is None:
            return verdict, []
        explained.append(dict(output_span=[t0, t1], median_error_s=median, reason=match.get('reason', '')))
    return 'PASS (known target defect)', explained


def read_rows(path):
    with Path(path).open(newline='') as f:
        return list(csv.DictReader(f))
