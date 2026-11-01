"""Regression from Zorro DVD (23.976 -> 25 fps) v1.2.5 diagnostics.

This fixture proves the reported unsafe join is detected and blocked.
It does NOT claim to have solved the correct audio mapping or validated media.
"""
import copy
import tempfile
import unittest
from pathlib import Path
from continuity_guard import source_rewinds, annotate_rewinds
from autosync import render

ZORRO_SEGMENTS = [
    dict(kind="audio", target_start=0.0, target_end=86.16,
         source_start=1.1720041666666692, speed=1.0406229166666665),
    dict(kind="audio", target_start=86.16, target_end=150.56,
         source_start=90.15349707561727, speed=1.042515239197531),
    dict(kind="audio", target_start=150.56, target_end=1351.5,
         source_start=158.28147480072477, speed=1.0425949954710143),
    dict(kind="audio", target_start=1351.5, target_end=1409.52,
         source_start=1440.993988751447, speed=1.0404636140046277),
]

class ZorroRewindRegression(unittest.TestCase):
    def setUp(self):
        self.plan = {
            "duration": 1409.52,
            "segments": copy.deepcopy(ZORRO_SEGMENTS),
            "review": [], "warnings": [], "source_cuts": [],
            "audio": "KaiketsuZorro_01.mkv", "reference": "zorro_01.mkv",
        }

    def test_exact_rewind_is_recognized(self):
        issues = source_rewinds(self.plan["segments"])
        self.assertEqual(len(issues), 1)
        self.assertAlmostEqual(issues[0]["target_time"], 86.16, places=3)
        self.assertAlmostEqual(issues[0]["previous_source_end"], 90.8320746667, places=5)
        self.assertAlmostEqual(issues[0]["next_source_start"], 90.1534970756, places=5)
        self.assertAlmostEqual(issues[0]["replayed_source_seconds"], .6785775910, places=5)

    def test_warning_survives_reaudit_but_is_not_duplicated(self):
        annotate_rewinds(self.plan)
        annotate_rewinds(self.plan)
        self.assertEqual(len(self.plan["source_rewinds"]), 1)
        self.assertEqual(len([r for r in self.plan["review"]
                              if r.get("issue_type") == "source_rewind"]), 1)

    def test_safe_export_refuses_replay_without_requiring_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "backwards source-audio joins"):
                render(self.plan, Path(tmp), reference_fallback=False)

    def test_correcting_join_removes_rewind_warning(self):
        annotate_rewinds(self.plan)
        end0 = self.plan["segments"][0]["source_start"] + (
            self.plan["segments"][0]["target_end"] -
            self.plan["segments"][0]["target_start"]
        ) * self.plan["segments"][0]["speed"]
        # Synthetic repair for guard testing ONLY, not a proposed real media fix.
        self.plan["segments"][1]["source_start"] = end0
        annotate_rewinds(self.plan)
        self.assertEqual(self.plan["source_rewinds"], [])
        self.assertFalse(any(r.get("issue_type") == "source_rewind"
                             for r in self.plan["review"]))

if __name__ == "__main__":
    unittest.main()
