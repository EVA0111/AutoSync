# AutoSync v1.3.0

Windows x64 portable release by [EVA0111](https://github.com/EVA0111).

## What's new in v1.3.0

### Much more accurate syncing

- **New picture-based engine.** AutoSync now lines the source audio up with the target's *picture*. Earlier versions followed the target's own dub track, which in real releases sits 90–250 ms away from its own picture, so lip-sync was off by that much. The old audio-based engine remains the fallback when a video is missing.
- **Measured, not assumed.** Every change was checked by an independent tool that compares the finished output with the original source, on 8 real episode pairs × 4 output modes × Standard and AI-assisted (64 runs): **64 of 64 pass** (typical error 9–17 ms). The previous release passed 0 of 56.
- **Handles real-world edits:** re-cut and reordered shots, scenes added or removed by one release, frozen shots held longer, gradual picture drift (followed with a gentle, inaudible speed change), different speeds (25/24, NTSC) and frame-accurate main-episode trims.

### Censored or edited dubs

- New **Censored or edited dub** option for old dubs that removed or re-cut scenes (for example an Arabic dub of a Japanese original). AutoSync lists every scene the dub removed and every spot it re-cut, and lets you **restore** each scene with the original audio (loudness-matched to the dub, with soft switches) or **cut** it from the video like the dub did, scene by scene in Preview & Edit. Optional subtitles for the restored scenes.

### Redesigned Preview & Edit

- One screen, no scrolling: a **review list** of every join and flagged point (filters, checked marks, notes), side-by-side / overlay / difference / wipe picture comparison, frame-accurate stepping and nudges, slow playback, "play across join", an overview strip, Ctrl+scroll zoom, waveforms that appear as soon as each track loads, automatic saving of your edits, and a keyboard-shortcut sheet (**?**).

### Cleaner main window

- One top bar (Audio · Subtitles · Jobs · Settings), your files on the left and the job settings on the right, a single bottom bar that tells you the next step, and clearer Settings.

### Reliability

- Fixed exports blocked by Windows briefly locking a just-written video file.
- Fixed AI-assisted runs crashing on RTX 50-series GPUs (falls back to CPU).
- Many smaller timing fixes; all safety checks are kept (no repeated audio, uncertain joins are flagged).

## What's included

- Synchronize audio across differently edited videos and export pitch-preserving FLAC (and, in some modes, an edited video).
- Subtitle syncing using audio, video, saved-map and optional AI workflows.
- Bundled Python 3.12, NumPy, SciPy, FFmpeg and FFprobe: nothing else to install for normal use.

## Installation

1. Download **AutoSync-v1.3.0-Windows-Portable.zip**.
2. Extract it into a writable location.
3. Open **AutoSync.exe** inside the extracted **AutoSync-v1.3.0-Windows-Portable** folder.

New to AutoSync? Read the [wiki](https://github.com/EVA0111/AutoSync/blob/main/docs/Home.md).

Listen across flagged joins before distributing outputs. AutoSync never overwrites your original videos.

## Source

The source repository includes the portable Windows build scripts under `build/windows`. All application windows and package metadata display **v1.3.0**.
