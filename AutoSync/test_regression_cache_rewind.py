"""Regression tests for cache integrity and repeatable rewind diagnostics."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import ai_sync
from continuity_guard import annotate_rewinds


class AICacheIntegrity(unittest.TestCase):
    def test_invalid_cached_timestamps_are_recomputed(self):
        with tempfile.TemporaryDirectory() as temp:
            media = Path(temp) / "input.mkv"
            media.write_bytes(b"fixture")
            with patch.object(ai_sync, "CACHE", Path(temp)):
                key = ai_sync._key(media, 0, ai_sync.AUDIO_MODEL, "audio")
                cache = Path(temp) / (key + ".npz")
                vectors = np.eye(3, dtype=np.float32)
                for times in (
                    [0., float("nan"), 16.],
                    [0., 16., 8.],
                    [-1., 8., 16.],
                    [0., float("inf"), 16.],
                ):
                    with self.subTest(times=times):
                        np.savez_compressed(cache, times=np.array(times),
                                            vectors=vectors)
                        self.assertIsNone(ai_sync._load_cached(
                            media, 0, ai_sync.AUDIO_MODEL, "audio"))

    def test_valid_cache_still_reused(self):
        with tempfile.TemporaryDirectory() as temp:
            media = Path(temp) / "input.mkv"
            media.write_bytes(b"fixture")
            with patch.object(ai_sync, "CACHE", Path(temp)):
                expected_times = np.array([4., 12., 20.], dtype=np.float32)
                vectors = np.eye(3, dtype=np.float32)
                ai_sync._save_cached(media, 0, ai_sync.AUDIO_MODEL,
                                     "audio", expected_times, vectors)
                cached = ai_sync._load_cached(
                    media, 0, ai_sync.AUDIO_MODEL, "audio")
                self.assertIsNotNone(cached)
                np.testing.assert_array_equal(cached[0], expected_times)
                np.testing.assert_array_equal(cached[1], vectors)


class RewindDiagnosticRefresh(unittest.TestCase):
    @staticmethod
    def plan():
        return dict(duration=20., segments=[
            dict(kind="audio", target_start=0., target_end=10.,
                 source_start=10., speed=1.),
            dict(kind="audio", target_start=10., target_end=20.,
                 source_start=17., speed=1.),
        ], review=[dict(start=1., end=2., confidence="manual",
                       reason="Keep user's review")],
            warnings=["Keep unrelated warning"])

    def test_double_audit_does_not_duplicate_warnings(self):
        plan = self.plan()
        annotate_rewinds(plan)
        annotate_rewinds(plan)
        self.assertEqual(len(plan["source_rewinds"]), 1)
        self.assertEqual(len([x for x in plan["review"]
                              if x.get("issue_type") == "source_rewind"]), 1)
        self.assertEqual(len(plan["warnings"]), 2)
        self.assertIn("Keep unrelated warning", plan["warnings"])

    def test_corrected_join_clears_only_generated_diagnostics(self):
        plan = self.plan()
        annotate_rewinds(plan)
        plan["segments"][1]["source_start"] = 20.
        annotate_rewinds(plan)
        self.assertEqual(plan["source_rewinds"], [])
        self.assertFalse(any(x.get("issue_type") == "source_rewind"
                             for x in plan["review"]))
        self.assertEqual(plan["warnings"], ["Keep unrelated warning"])
        self.assertEqual(len(plan["review"]), 1)
        self.assertEqual(plan["review"][0]["confidence"], "manual")

    def test_moved_join_replaces_old_review_time(self):
        plan = self.plan()
        annotate_rewinds(plan)
        plan["segments"][1]["target_start"] = 11.
        plan["segments"][0]["target_end"] = 11.
        annotate_rewinds(plan)
        flags = [x for x in plan["review"]
                 if x.get("issue_type") == "source_rewind"]
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["splice"], 11.)
        self.assertEqual(len(plan["warnings"]), 2)


if __name__ == "__main__":
    unittest.main()
