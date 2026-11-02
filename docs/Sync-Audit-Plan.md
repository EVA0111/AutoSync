# AutoSync synchronization audit — engineering plan

Branch: `audit/sync-accuracy` (based on PR #21, `review/debug-sync-v125`). No release is cut from this branch until the full matrix below is verified.

## Scope

Every regression pair is treated the same; no case-specific constants.

| Case | Source (dub + its own video) | Target (edition to sync to) | Notes |
| --- | --- | --- | --- |
| 1 | 25 fps, 1474.6 s | 25 fps, 1217.0 s (fre) | Heavily cut target |
| 2 | 23.976 fps mkv, jpn, video PTS 0.104 | 25 fps mp4, ara | On disk the file names are swapped relative to `media_regression_cases.json`. Use manifest hashes. |
| 3 | 23.976 fps | 25 fps, 1244.6 s (eng) | Previously "not exported" |
| 4 | 23.976 fps, jpn | 25 fps, 1340.3 s (eng) | |
| 5 | 23.976 fps, jpn, audio PTS 0.063 | 23.976 fps, 1401.3 s (eng) | Previously "not exported". Source SHA differs from the manifest. |
| 6 | 23.976 fps, video PTS 0.083 | 25 fps, 1409.5 s (ger) | |
| Zorro | 23.976 fps (`2997/125`) avi→mkv, mp3 | 25 fps PAL ffv1, ger ac3 | Known rewind at about 86 s; ambiguous main start |

Matrix: each pair × {Full target, Main episode (`--main-only`), Keep opening & ending (`--keep-target-op-ed`), Remove unmatched video (`--remove-unmatched-video`)} × {Standard, AI-assisted}. That is 56 runs.

## Measurement: independent of the engine

A successful export is not a pass. `sync_accuracy.py` measures the **delivered** A/V sync and uses none of the engine's features, anchors or plan:

1. **Picture ground truth.** Decode the delivered video and the source video at 50 fps, 32×24 grey, on absolute presentation timestamps. For every 2 s output sample, find the source position whose speed-scaled 2 s frame *clip* best matches the output clip, then refine to sub-frame precision. Reject static, low-detail or ambiguous clips (score, margin and peak-sharpness gates).
2. **Audio ground truth.** Locate each 4 s window of the delivered audio inside the original source audio. It is the same recording, so the correlation is strong and precise to 10 ms. The search is centred on the picture position (±8 s), with a global fallback that classifies gross errors and non-source (target) audio.
3. **Error.** `(source_audio_time − source_picture_time) / speed`, in output seconds; positive means audio leads picture. The source file's own A/V timing is the reference, so start-time offsets in either file are measured, not assumed.
4. Delivered file per mode: Full target → target video + `synced.flac` muxed at 0 relative to the first video frame (the documented convention). Other modes → the exported `.mkv` itself, using its own stream timestamps.

Metrics per run: evaluable coverage, median/p95/max |error|, the share of samples within 45 ms and 100 ms, gross spans (>200 ms for ≥2 consecutive samples), non-source-audio spans, and repeated-audio detection (a source-time rewind in the delivered audio).

Pass gate per run: ≥95 % of evaluable samples within ±100 ms, p95 ≤ 100 ms, no gross span, no repeated audio, evaluable coverage ≥ 60 % of the source-audio portion. A run that refuses to export is reported as **blocked** (safety refusal) and kept separate from **wrong output**.

## Areas audited (pipeline order)

1. Feature extraction and start-time conventions (`wav_features`, `refshift`, video PTS origin).
2. Speed estimation (`estimate_rate`), including PAL speed-up vs 23.976.
3. Anchor detection and false-positive rejection (`audio_anchors`, `remove_outliers`, AI `combine_standard_and_learned`).
4. Grouping and model fitting (`group_anchors`, `robust_fit`).
5. Cut, insert and eyecatch location (`locate_cut`, `visual_cuts`), OP/ED boundary (`main_episode`).
6. Continuity and backward-mapping audit (`continuity_guard`): the Zorro rewind and its general cause.
7. Mode transforms (`trim_plan`, `keep_target_outer`, `remove_missing`, `protect_opening`), rendering and `verify_export`.

## Process

1. Baseline: run the full matrix on the unmodified PR #21 engine and measure it.
2. For each failure: find the root cause in the log, plan and diagnostics → apply a general fix → add a synthetic unit regression test → re-measure the affected cases **and** all others.
3. Safety checks stay enabled. There are no timing offsets and no per-episode logic.
4. Final: re-run the full matrix and write a report with the per-run numbers, fixes and remaining limitations.
