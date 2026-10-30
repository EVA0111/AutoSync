# AutoSync v1.2.0

Windows x64 portable release by [EVA0111](https://github.com/EVA0111).

## What's included

- Synchronize audio across differently edited videos, including playback-speed and scene-timing differences, with pitch-preserving FLAC export.
- Match subtitles using supported audio, video, saved-map, and optional subtitle workflows.
- **Preview & Edit** opens the complete target timeline even when the selected export mode requires an uncertain opening/ending boundary.
- Four-lane visual editor (V1/A1/A2/MIX) with playback, clip dragging, snapping, razor cuts, edge trimming, copy/paste, and source-audio slip.
- Choose a custom output location. Reports are stored under **AutoSync Reports** beside the application by default, with separate subfolders for each job.
- Bundled Python 3.12, NumPy, SciPy, FFmpeg and FFprobe: no separate runtimes needed to use the Windows portable application.

## Installation

1. Download **AutoSync-v1.2.0-Windows-Portable.zip**.
2. Extract it into a writable location.
3. Open **AutoSync.exe** inside the extracted **AutoSync-v1.2.0-Windows-Portable** folder.

Optional subtitle AI models and components may require additional downloads through the application.

Review flagged joins and uncertain timing before distributing outputs. The app does not overwrite your original source or target videos.

## Source

The source repository includes the portable Windows build scripts under `build/windows`. All main application windows and package metadata display **v1.2.0**.
