# How syncing works (v1.4.1)

## The idea

The source audio belongs to the source **picture**. So AutoSync finds, for every moment of the target video, which moment of the source shows the same picture, and plays the source audio from there.

Earlier versions lined the source audio up with the target's **own soundtrack**. That sounds equivalent but is not: in real releases a dub track is often 90–250 ms off its own picture, and sometimes re-laid by over a second in places. Following the picture removes that error.

## Step by step

1. **Pictures.** Both videos are decoded once at low resolution. AutoSync tries letterbox, pillarbox and crop variants to find the framing the two share, and works out the speed difference (for example 25 vs 24 fps).
2. **Timeline.** For every half second of the target it finds candidate source positions, then chooses the best path through the whole episode at once, allowing for cuts, added footage and removed footage. Recaps and previews that reuse footage are recognised so source audio is never replayed.
3. **Edits.** Each change in the path becomes a frame-accurate join. Where the picture can't tell (a still or dark shot), the audio decides; footage only the target has is filled with the target's own audio. Slow picture drift inside a shot is confirmed on a 50 fps check and followed with a gentle speed change of at most 5 %.
4. **Safety.** Joins that would repeat source audio are refused, uncertain joins are flagged for review, and nothing is guessed silently.
5. **Export.** Audio is cut by sample and re-timed pitch-preserving; video edits are frame-exact.

If one of the videos is missing (audio-only jobs), the older audio-matching engine is used.

## How accurate is it?

AutoSync v1.4.1 was measured on 9 real episode pairs (anime and live action; DVD and Blu-ray; 25/24 fps speed-ups; different openings, recaps, censored scenes) in all 4 output modes, **36 runs**. An independent tool compares every finished output with the original source (picture against sound), without using anything AutoSync computed.

| | Runs passing |
| --- | --- |
| v1.2.5 | 0 of 56 |
| v1.3.0 | 64 of 64 (8 pairs, two matching methods) |
| **v1.4.1** | **36 of 36** |

Passing means at least 95 % of measured moments within 100 ms, no 2 s or longer stretch more than 200 ms off, and no repeated audio. Typical error in v1.4.1 is **9–17 ms**. Two test episodes pass with declared exceptions: spots where the target release itself has its picture out of sync with its own soundtrack. AutoSync follows the soundtrack there, as the target does.

Full details: [Sync audit report](Sync-Audit-Report.md).

## Where it can still go wrong

- **Frozen or very dark shots:** the picture cannot place a join precisely; the audio decides and the point is flagged.
- **Very short re-timed shots** (a couple of seconds shifted by a fraction of a second) may be left at the surrounding timing.
- **A target that is itself out of sync** with its own soundtrack: AutoSync cannot fix the target's picture.
- **Audio-only jobs** (no video) use the older engine and are less accurate.

Always listen across flagged points in [Preview & Edit](Preview-and-Edit.md).

[← Wiki home](Home.md)
