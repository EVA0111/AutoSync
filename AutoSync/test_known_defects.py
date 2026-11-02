"""A declared target-release defect explains only the failure it describes."""
import unittest

from known_defects import explain

DEFECT = [dict(source_start=1255, source_end=1265, max_error_s=.30, reason='target picture out of sync')]


def rows(errors, start_t=1290., start_src=1257.):
    return [dict(t=str(start_t + 2 * i), status='measured', picture_src=str(start_src + 1.92 * i), error=str(e))
            for i, e in enumerate(errors)]


def summary(verdict, spans):
    return dict(verdict=verdict, gross_spans=spans)


class KnownDefects(unittest.TestCase):
    def test_gross_span_inside_the_window_is_explained(self):
        status, why = explain(summary('FAIL: gross_spans', [[1292., 1296., -.246]]),
                              rows([-.08, -.25, -.26, -.20]), DEFECT)
        self.assertEqual(status, 'PASS (known target defect)')
        self.assertEqual(len(why), 1)

    def test_larger_error_still_fails(self):
        status, _ = explain(summary('FAIL: gross_spans', [[1292., 1296., -.4]]), rows([-.08, -.45, -.4, -.2]), DEFECT)
        self.assertEqual(status, 'FAIL: gross_spans')

    def test_span_outside_the_window_still_fails(self):
        status, _ = explain(summary('FAIL: gross_spans', [[1292., 1296., -.25]]),
                            rows([-.08, -.25, -.26, -.2], start_src=1300.), DEFECT)
        self.assertEqual(status, 'FAIL: gross_spans')

    def test_other_failures_are_never_explained(self):
        for verdict in ('FAIL: gross_spans,replayed_audio', 'FAIL: within100<95%,gross_spans', 'FAIL: coverage<25%'):
            status, _ = explain(summary(verdict, [[1292., 1296., -.25]]), rows([-.08, -.25, -.26, -.2]), DEFECT)
            self.assertEqual(status, verdict)

    def test_no_declaration_changes_nothing(self):
        status, _ = explain(summary('FAIL: gross_spans', [[1292., 1296., -.25]]), rows([-.08, -.25, -.26, -.2]), [])
        self.assertEqual(status, 'FAIL: gross_spans')

    def test_pass_stays_pass(self):
        self.assertEqual(explain(summary('PASS', []), [], DEFECT), ('PASS', []))


if __name__ == '__main__':
    unittest.main()
