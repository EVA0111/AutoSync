# AutoSync v1.2.5 — engineering review and debugging

This report separates **confirmed bugs**, **confirmed safety behavior**, **remaining algorithm risks**, and **tests not yet run**. It is not a release approval.

## Pipeline reviewed

1. Decode 8 kHz audio and calculate approximately 50 Hz STFT feature/energy windows (`wav_features`).
2. Match video scenes, estimate speed ratio, propose audio matches (optionally using AST/DINOv2).
3. Remove isolated audio anchors, split offset regimes, robustly fit a speed/offset model independently within each group (`remove_outliers`, `group_anchors`, `robust_fit`).
4. Estimate transition times from dense audio and, when needed, picture checks (`locate_cut`, `refine_cut`, `build_plan`).
5. Apply output-mode transformation, audit backward source mappings (`annotate_rewinds`), generate a report, render pitch-preserving FLAC or edited video, and optionally sample-check the export.

## Confirmed defects fixed in this review branch

| Severity | Problem | Change | Regression coverage |
| --- | --- | --- | --- |
| High | Desktop could not supply `--main-start` / `--main-end` even when the engine explicitly required them. The job builder always overwrote both with empty strings. | Expose **Main start** and **Main end** (target seconds) under Advanced audio settings. Preserve them in main-episode modes and ignore them when switching to Full target audio. Improve the boundary error. | `test_gui.py` and `desktop/ai-sync-ui.test.cjs` |
| Medium | AI-assisted audio-anchor jobs skipped `verify_export` because their method label starts with `AI-assisted: `. | Run the existing sampled output check for both Standard and AI-assisted audio-anchor methods, unless video was edited. | `test_gui.py` |
| CI | A Linux desktop test constructed a Windows `D:` target path with native POSIX `path.join`, causing a false failure. | Use a platform-native absolute test path and check drive-letter paths only on Windows; add a Windows desktop CI job. | `temp-directory.test.cjs`, CI on Linux and Windows |

### Why the Zorro audio rewind remains unresolved

The uploaded v1.2.5 plan reports these adjacent mapping boundaries:

- **Target join:** 86.160 s
- **End of preceding source mapping:** 90.8320746667 s
- **Start of following source mapping:** 90.1534970756 s
- **Unverified replay:** approximately 0.6785775910 s

The algorithm fits different groups independently. In `build_plan`, adjacent models are joined at `locate_cut`'s estimated or verified target time; no constraint requires the two source mappings to be monotone at that join. `annotate_rewinds` and `render` correctly flag and block the resulting unsafe mapping **after** plan construction.

**Do not 'fix' this case by always snapping the next source start to the previous source end.** That would change a fitted correspondence without evidence, could hide a real version-specific edit, and may cause misalignment elsewhere. The correct time/region requires the actual media near 01:23–01:29 or reliable local matching evidence.

Recommended follow-up algorithm work:

1. During candidate-plan construction, score each transition jointly on audio, picture, and source-time continuity.
2. Where the independent fits overlap, reconsider anchors and cut candidates locally; only accept a monotone replacement with supporting evidence on **both** sides.
3. Try target-only insertion detection only when a matching picture interval supports it; do not create target-audio fallback merely to make a plan exportable.
4. If no supported monotone plan exists, retain the original diagnostics and require Preview & Edit. Never silently repeat sound.
5. Compare revised output across all media regression cases before accepting the solver change.

### Why the Zorro main boundary remains unresolved

`boundary_from_scores` intentionally rejects ambiguous opening/ending transitions (weak score contrast, multiple plausible edges, or possible cold opens). The first v1.2.5 Zorro log confirmed a **start boundary is ambiguous** failure; that does not establish the correct start time. The desktop was missing the manual override fields, now corrected in this branch. Users must still verify the boundary in the video before supplying it.

## Remaining verification required

- **Six private media cases:** old v1.2 results reported FLAC exports but not perfect sync; they are **not** current v1.2.5 pass results.
- **Zorro case:** two reported failures exist; this branch has not rerun the actual media.
- **Full matrix:** Standard / AI-assisted across Full target, Main episode, Keep opening & ending, and Remove unmatched video (8 configurations per pair). Private media and AI model weights are not in this repository or GitHub Actions.
- **Accuracy:** exports must be checked for duration, monotonic source mapping, edit handling, source-language integrity, and sampled timing residuals, plus representative listening checks at cut points.
- **Optional real-model inference:** `check-ai-sync.yml` exists separately; its execution on this branch is not implied by core CI.

## Release decision

**No v1.2.6 release should be cut from this review alone.** Unit/CI passes establish the targeted bug fixes but do not resolve the source rewind or certify actual synchronization across the media matrix.
