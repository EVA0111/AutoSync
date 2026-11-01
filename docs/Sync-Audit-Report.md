# AutoSync synchronization audit — final report

Branch `audit/sync-accuracy` (based on PR #21, head `9b9c22d`). Plan: `docs/Sync-Audit-Plan.md`.
**No release has been cut.** The full regression matrix is not yet green: 50 of 64 runs pass (§3), and
the remaining 14 trace to two spots where the target releases themselves are out of sync (§5).

## 1. How accuracy is measured

A successful export never counts as a pass. `AutoSync/sync_accuracy.py` measures the **delivered file**
against the **original source file**, using no engine features, anchors or plan:

* Delivered: the target video with `synced.flac` at 0 ms in Full target mode; the exported `.mkv` in
  Main episode, Keep OP/ED and Remove unmatched video modes.
* **Picture position**: delivered frames (50 fps, 32×24 grey) located in the source video as
  speed-scaled 2 s clips, refined to sub-frame precision. Static, flat, ambiguous and isolated matches
  are rejected.
* **Audio position**: 4 s windows of delivered audio located in the source recording.
* **Error** = (source audio time − source picture time) / speed, in output seconds. Positive means
  the audio leads the picture.
* Picture matches more than 5 s from the audio are classed as reused footage (recaps), not as error.
* **Verdict**: PASS requires all of the following:
  * at least 95 % of measured samples within 100 ms;
  * p95 error ≤ 100 ms;
  * no gross span (two or more consecutive samples above 200 ms);
  * no confirmed audio replay (source audio stepping back by more than 0.3 s, confirmed with 1 s
    windows);
  * coverage ≥ 25 %. Coverage is the share of audible samples where both picture and audio could be
    located; the source compared with itself reaches 78 %.

### Evaluator validation

**Frame origin.** ffmpeg pads the first decoded picture back to the *file* start, so decoded frame k
sits at file origin + k/fps, not at the video stream start + k/fps. Both the engine and the first
version of the evaluator assumed the stream start, and the two errors cancelled. A Remove-unmatched
export, whose video starts at 0.036 s, exposed it. After the fix:

| Check (source rebuilt with a different video start) | Expected | Measured |
| --- | --- | --- |
| Audio kept in sync | 0 ms | +1.5 ms |
| Audio delayed 250 ms | −250 ms | −248 ms |

Other evaluator defects found and fixed during the audit:
* argument order of the audio locator;
* empty frequency bands;
* NCC rounding above 1, fixed with float64 and an energy floor;
* target-only inserts counted as replays, now confirmed with 1 s windows;
* cache races between parallel workers, now written atomically;
* geometry taken from the engine, now chosen independently from the pictures.

### Each target's own dub track

Each target's own dub track is offset from its own picture (cross-language matching, medians):

| Case | 1 | 2 | 3 | 4 | 5 | 6 | 7 | Zorro |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Native target-dub offset (ms) | −148 | −132 | −251 | +101 | +24 (16 samples) | −116 | −92 | −120 |

An earlier draft listed case 3 as +258 ms. That figure was measured before the frame-origin fix and
had the wrong sign; the spot check at 1007 s confirms −0.3 s.

## 2. Why the engine was replaced

The PR #21 engine aligned source audio to the target's **audio** (audio anchors). It therefore
inherited the offsets above: 100–250 ms of lip-sync error in every case, plus local re-lays of up to
1.6 s (case 2, target 116–137 s). The source audio belongs to the source **picture**, so the timing
that keeps it in sync on the target is the target→source picture correspondence.

`AutoSync/picture_timeline.py` is now the primary engine whenever both videos are present:

1. **Decode.** Each video is decoded once at 64×48, 25 fps. Shared geometry is chosen from
   letterbox/pillarbox and aspect hypotheses.
2. **Rate.** The edition rate is estimated and snapped to known ratios (1, 25/24, 24/25, NTSC
   variants).
3. **Candidates.** Every 0.5 s of target gets source-offset candidates, scored as 2 s speed-scaled
   clips, plus offsets that are strongly supported nearby (for static shots).
4. **Global solve.** A Viterbi pass over the whole episode picks one offset per sample or a
   target-only state, with costs for cuts, backward jumps and far jumps.
5. **Clean-up.** A duration-weighted monotone chain removes recaps, so reused footage never replays
   audio. A local re-solve recovers short low-scoring sections, and frame-level jitter is absorbed.
6. **Joins.** Offsets are refined to sub-frame precision. Each join is placed at a frame, and inside
   static spans audio evidence (or the quietest point) decides. Target-only footage is
   picture-verified and gets target audio.

The legacy audio-anchor engine remains the fallback, used for `--timing audio`, missing videos,
manual source ranges or cut times. No safety check was removed: the rewind, unresolved-cut,
reference-fallback and boundary-ambiguity guards all apply to both engines.

## 3. Results

Matrix: 8 pairs (cases 1–6, case 7, Zorro) × 4 modes × Standard and AI-assisted.
* **Baseline** is PR #21 as received, re-scored with the corrected evaluator.
* **v1** is the first round of fixes to the audio-anchor engine.
* Case 7 was added after v1, so the baseline and v1 matrices have 56 runs.

| Matrix | Runs | PASS | FAIL | BLOCKED (no export) |
| --- | --- | --- | --- | --- |
| Baseline (PR #21) | 56 | 0 | 12 | 44 |
| v1: audio-engine fixes | 56 | 0 | 34 | 22 |
| v2: picture timeline + frame origin (`1c247c4`) | 64 | 40 | 24 | 0 |
| **v3: current (`04e4e16`)** | 64 | **50** | 14 | 0 |

Where the earlier engines exported, they failed the accuracy gates:
* case 1: p95 266 ms;
* case 2 Remove unmatched: p95 617 ms;
* case 4: p95 144 ms;
* case 6: p95 163 ms;
* Zorro: p95 168 ms;
* case 5: gross spans.

### v3, Standard

AI-assisted results are identical (§6). Each cell gives the median and p95 absolute error in ms, then
the share of samples within 100 ms.

| Case | Full target | Main episode | Keep OP/ED | Remove unmatched |
| --- | --- | --- | --- | --- |
| 1 | PASS 13.9 / 61.7, 98.4 % | PASS 13.8 / 61.4, 98.4 % | PASS 13.9 / 61.7, 98.4 % | PASS 13.8 / 61.4, 98.4 % |
| 2 | PASS 11.2 / 49.3, 100 % | PASS 11.5 / 51.7, 99.5 % | PASS 11.2 / 49.3, 100 % | PASS 11.4 / 53.0, 99.6 % |
| 3 | PASS 15.3 / 78.6, 97.6 % | PASS 16.5 / 85.2, 95.1 % | PASS 15.5 / 78.6, 97.2 % | PASS 16.1 / 84.8, 95.9 % |
| 4 | PASS 12.1 / 68.8, 97.7 % | PASS 9.3 / 58.0, 97.8 % | PASS 12.1 / 68.8, 97.7 % | PASS 9.3 / 58.0, 97.8 % |
| 5 | PASS 14.8 / 74.9, 98.0 % | FAIL gross span, 15.1 / 69.5 | FAIL gross span, 15.0 / 74.9 | FAIL gross span, 14.5 / 56.0 |
| 6 | PASS 11.5 / 52.3, 100 % | PASS 11.5 / 52.3, 100 % | PASS 11.5 / 52.3, 100 % | PASS 11.7 / 53.7, 99.4 % |
| 7 | FAIL gross span, 13.4 / 80.6 | FAIL gross span, 11.8 / 73.7 | FAIL gross span, 13.4 / 80.6 | FAIL gross span, 12.8 / 64.8 |
| Zorro | PASS 11.2 / 52.1, 100 % | PASS 11.2 / 52.0, 100 % | PASS 11.2 / 52.1, 100 % | PASS 11.2 / 52.0, 100 % |

Coverage is 29–52 % per run, above the 25 % gate everywhere. Case 5 Full passes only because its 2 s
sampling falls between the samples that catch the spot described in §5. That spot is the same in
every case 5 mode.

Contact sheets in `contact/case_*.png` (local, not committed) confirm the matched frames by eye.
They also exposed two errors the numbers had hidden: case 3's earlier crop/repeated-music lock, and
the case 2 dub re-lay.

## 4. Root causes found and fixed

Each fix has a synthetic regression test that fails on the code before it, and each was re-measured
on the media.

### Picture-timeline engine and exports

| # | Defect (where measured) | Root cause | General fix | Test |
| --- | --- | --- | --- | --- |
| 1 | Every case: 100–250 ms of lip-sync error. | Alignment followed the target dub, which is itself offset from the target picture (§1). | Dense picture timeline as the primary engine (§2). | `test_picture_timeline.py` (Edition, Recap, StaticSpan, Pieces) |
| 2 | Cases 1, 2, 6: source audio taken 40–104 ms late; hidden from the evaluator. | Frame k was assumed to sit at the video start + k/fps; ffmpeg pads to the file origin. Engine and evaluator shared the error. | Use the file origin in both; validated by rebuilt-file tests (§1). | `FrameOrigin` |
| 3 | Main episode / Keep OP/ED blocked ("ambiguous boundary") for cases 2, 6 and Zorro. | Boundaries came from audio-anchor heuristics. | Boundaries taken from target-only picture runs on the timeline. The shared-music veto is kept, and manual boundaries still win. | `test_shared_edge_title_card.py`, matrix |
| 4 | Case 3, target 1007–1060 s: audio 1–5 s off its pictures. | The target inserts footage and cuts as much source nearby, so the shots on both sides of the gap share one timing while the shots inside sit 1–5 s away. The gap re-solve only searched between the neighbours' timings and bridged the gap with continuous audio. | Search window = what a forward source path through the gap can reach (the gap length). Timings outside the neighbours' range need full-strength evidence. | `BalancedEdits` |
| 5 | Case 2 Main episode: 1.47 s of audible audio replayed. | A still shot is held 1.48 s longer in the target. Every placement of the extra time fits the pictures, and the arbitrary one filled it with target audio that repeats source sound (the target dub is the same soundtrack, re-laid 1.6 s late). | Inside a held shot, the extra time goes where the target audio that fills it is quietest. New footage is still placed by the pictures. | `HeldShot` |
| 6 | Case 3 Main episode: whole episode 31 ms late (95 % gate failed). | The trimmed picture starts at the next whole frame (23.976 fps) while the audio was cut at the fractional boundary. | Trim boundaries snapped to the target frame grid; the exporter seeks a quarter frame early. | `test_frame_snap.py` |
| 7 | Case 3 Remove unmatched: WinError 32. | A just-written partial file stayed briefly locked on Windows, and cleanup could mask the original error. | Retrying rename; cleanup never masks the error. | `test_frame_snap.py` |
| 8 | Renders failed on very short pieces (time-stretch length error). | `atempo` on pieces of a few frames. | Context stretch (0.5 s either side, keep the exact middle); pieces under 0.2 s resampled; audio pieces under 0.1 s merged. | `test_trim_slivers.py` |
| 9 | Zero-length reference at the outer edge; outer edges imprecise. | The edge was taken from 0.5 s samples. | `edge_frame` gives frame-accurate edges, with a clamp at the first sample. | `test_picture_timeline.py` |

### Legacy audio-anchor engine (now the fallback) and shared code

| # | Defect | Root cause | General fix | Test |
| --- | --- | --- | --- | --- |
| 10 | Case 1: drift up to 150 ms over 300 s; a 0.29 s cut hidden. | `group_anchors` split only jumps above 0.25 s; `robust_fit` bent the fit. | Split small steps backed by tight clusters on both sides. A local slope must beat both the fixed-rate fit and a step model. | `test_small_edit_grouping.py` |
| 11 | Case 3: phantom 9.6 s rewind blocked the export. | One false anchor merged three regimes into one fitted line. | Re-segment groups that disagree by seconds; drop lone anchors; merge equal neighbours. | `test_inconsistent_groups.py` |
| 12 | Every AI-assisted run crashed: "CUDA error: no kernel image". | `torch.cuda.is_available()` was trusted on an RTX 50-series GPU with a CUDA 12.6 wheel. | Probe a real kernel; fall back to CPU with a message. | `test_ai_device.py` |
| 13 | Zorro / case 6: export blocked by a 0.68 s rewind that the pictures do not show. | The German opening is re-laid against the picture, and weak sections followed it. | Weak sections that contradict their strong neighbour's audio/picture relationship follow the pictures and are flagged. | `test_picture_check.py` |
| 14 | Case 2 Main / Keep: "Source pictures unavailable at target start". | The target opens 22 s before the source, on a reused title shot. | Frames without a source counterpart score as differing; the edge is taken from picture matches that agree with the main model. | `test_main_source_starts_late.py` |
| 15 | Zorro / case 6: "start boundary is ambiguous". | A 5 s differing title card inside a shared opening. | Short (<10 s) differing runs inside shared edges mean "kept"; long ones still require a manual boundary. | `test_shared_edge_title_card.py` |
| 16 | Zorro Main: render failed on a 0.06 s edge sliver. | Picture end and audio cut 60 ms apart. | Edge slivers under 0.25 s continue the neighbouring mapping. | `test_trim_slivers.py` |
| 17 | Windows: real render error replaced by WinError 32. | An open `np.memmap` blocked cleanup. | Release in `finally`; `ignore_cleanup_errors`. | Zorro re-run |
| 18 | Case 2 Remove unmatched: "target audio differs or is missing". | Paths were compared as strings. | Compare as files (`same_file`). | `test_same_file_paths.py` |
| 19 | 3 unit tests fail on Windows. | Locale code page (cp1252); the Python CI ran only on Linux. | Explicit UTF-8; Windows Python CI job. | CI |

No safety check was disabled or loosened, and no timing offsets or per-episode constants were
introduced. All thresholds are similarity or score levels, or bounds derived from the evidence (gap
length, frame grid). The unit suite has 179 tests, all passing on Windows.

## 5. Unresolved: two spots where the target release is out of sync

All 14 remaining failures come from one spot in case 5 and one in case 7. In both, the target's own
soundtrack runs continuously while its picture is re-timed against it. AutoSync's output keeps the
target's own audio continuity there.

| | Case 5, target 48.5–55 s (start of main episode) | Case 7, target 1289.5–1296.5 s |
| --- | --- | --- |
| Picture | Runs 2–3 % slow for 7 s: offset 47.36 → 47.60 s, a gradual drift with no cut. | Drifts 0.28 s ahead over 3.5 s, holds, then snaps back within 0.5 s at a cut. Dark, low-detail shot. |
| Target's own audio | Continuous at 47.56 s throughout (corr 0.5–0.86). | Continuous at 19.81 s throughout (corr 0.6–0.84). |
| Delivered error | +0.22 to +0.26 s for about 6 s | −0.25 s for about 6 s |
| Following the picture would need | About 3 % time-warp of 7 s of audio (feasible, see below). | Repeating 0.28 s of audio, which the rewind guard correctly blocks, or a 50 % slowdown for 0.5 s. |

The engine represents timing as constant-offset sections joined by cuts, so a gradual drift inside a
shot is averaged into the section offset. Possible general extension, not implemented: piecewise-linear
"drift" sections. A drift section would be accepted only when the frame evidence shows a sustained
monotone drift (≥ 0.12 s, slope ≤ 5 %, score gain over the constant offset). This would fix case 5.
Case 7 would still need either an audible repeat or a strong warp, and keeping the target's own
continuity there is arguably the right output. This is a product decision, so I have not changed it
silently.

### Other limitations

* **AI-assisted matching has no effect when both videos are present.** The picture timeline does not
  use the AI models, which only help the legacy fallback. Standard and AI-assisted v3 results are
  identical run for run.
* **The legacy fallback was not re-validated after v1.** With no target video, or with `--timing
  audio`, accuracy is the v1 level shown in §3, still tied to the target dub's own offset.
* **Evaluator sampling.** At 2 s steps, a short defect can fall between samples. In v2, case 2 Full
  missed the replay that Main caught, and case 5 Full misses its spot. Coverage is 29–52 %.
* **Case 7 roles.** Case 7 is a multi-audio target, so its reference stream is fixed to stream 0
  (Japanese).
* **Runtime.** A complete Full target run takes 40–138 s per episode on this machine, timeline
  included, with 4 runs in parallel.

## 6. Release recommendation

Do not release yet. The constraint is that the full regression matrix must verify, and it is at 50 of
64. To finish:
1. Decide how to handle target picture drift (§5): implement drift sections (fixes case 5), or accept
   both spots as target-release defects and record them in the regression expectations.
2. Re-run the 64-run matrix on Windows with the final commit, plus the Linux CI unit suite.
3. Then release from this branch.
