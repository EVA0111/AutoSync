# AutoSync — engine and desktop source

By [EVA0111](https://github.com/EVA0111).

AutoSync is a Windows desktop app that syncs audio and subtitles between different editions of a video. It compares pictures and sound, adjusts timing and audio speed while preserving pitch, and flags uncertain sections for review.

## Download and use

Build the complete application from this source repository using **`build/windows/build-portable.cmd`** (at the repository root). Extract the entire ZIP to a new folder, then open **AutoSync.exe**. The portable download includes Python, FFmpeg, and the core dependencies.

1. Drop source videos into the left column and matching target videos into the right column. One pair or many pairs use the same workflow.
2. Choose audio tracks and an output mode: full target, main episode only, or keep target opening/ending.
3. Optionally click a video's preview icon to trim it before syncing. Source and target trims are independent. Seek by timestamp or frame number; frames start at 1. End marks exclude the selected frame.
4. Output is optional: if blank, files go into `AutoSync Outputs` next to the target. Choose any other folder or drive using Browse.
5. Review flagged sections and joins before using the result.

Settings enables optional reports, advanced options, saved plans, and subtitle AI setup. Reports use a separate folder. Subtitle jobs have their own section with batch pairing and track selection.

## Features

- Audio and picture matching across different edits and playback speeds.
- Pitch-preserving synced FLAC output.
- Exact video/audio trims applied before matching; original files are preserved.
- Frame preview, frame-number seeking, and per-file trim ranges.
- Optional removal of target sections with no corresponding source audio, exporting edited video plus matching FLAC.
- Subtitle sync using another subtitle, two encodes, speech recognition, a saved timing map, or the optional Sushi engine.
- Progress, input checks, optional reports, and uncertain-section indicators.

## Limits

Automatic matching is not a guarantee of lip sync. Different soundtracks, silent signs, missing scenes, and heavily changed pictures can require review. Typesetting positions are preserved, not resized for new crops/aspect ratios. Some subtitle outputs are marked DRAFT when timing is uncertain. See README_SUBTITLES.md for format-specific support and limits.

Trimming the target or removing unmatched video produces a new video timeline; use its matching FLAC with that video. New trimmed/edited video exports are re-encoded using H.264 or FFV1 and do not carry embedded subtitles/chapters. Subtitle jobs remain separate. Temporary lossless trims can require substantial disk space. Optional AI dependencies and models download when installed/first used.

## Run the source

The source repository excludes bundled runtimes and media files. Install Node.js, Python 3.12, and FFmpeg/FFprobe (available on PATH), then run in the project folder:

```powershell
python runtime_setup.py
npm install
npm start
```

The first command creates a local `.venv` and installs NumPy/SciPy. For optional subtitle AI, use the Settings button or `python runtime_setup.py --ai`. Sushi mode additionally needs the upstream Sushi executable at `sushi/sushi.exe`; see `sushi/UPSTREAM.txt`. Use the source build script for a portable Windows app with dependencies bundled.

Tests:

```powershell
.venv\Scripts\python.exe -m unittest discover -p "test_*.py"
```

## Credits

Project profile: [EVA0111](https://github.com/EVA0111).

Built with Electron, Python, NumPy, SciPy, and FFmpeg. Optional subtitle matching integrates [tp7/Sushi](https://github.com/tp7/Sushi). Keep the bundled third-party license notices with redistributed binaries. This source package does not assign a new license to the project's own code; the owner can add their chosen license separately.

## Updated interface

The interface is English-only.

- **Audio**: drop one file or a folder into Source and Target, select each file's audio track, and open its preview icon to trim before syncing. Open **Review pairing & reorder** for manual ordering. Opening/ending track selection is under **Track settings for selected pair**.
- **Subtitles**: choose a timing reference and add the matching files. The existing subtitle modes, including Sushi, remain available.
- **Include audio jobs / Include subtitle jobs** determine which sections are processed. Both can run in the same queue; switching tabs does not clear files or enable a section automatically.
- Choose an **Output folder** or use the automatic target-adjacent default. **Settings** controls optional reports, advanced options, CSV import, and saved plans.
- **Jobs** shows completed results, failures, and items that need review. It also contains the optional activity log. Progress stays visible at the bottom.

Preview & Edit supports real-time playback and non-destructive clip editing.

## Preview & Edit (integrated)

Select source/target videos and click **Preview & Edit**. AutoSync analyzes
the selected pair automatically and saves a lasting alignment plan; no
separate `plan.json` selection is required. You can also open a saved plan
from the Saved plan workspace.

The editor has synchronized real-time source/target video playback, a three-track
waveform timeline, audio auditioning and non-destructive editing. Formats that
the built-in player cannot decode use a reusable lower-resolution MP4 proxy
created automatically; your source video is not modified.

Use **Split (S)**, **Copy (Ctrl+C)**, **Paste (Ctrl+V)**, **Cut (Ctrl+X)**,
**Set In/Out (I/O)** and **Trim Start/End (Q/W)** to edit audio mappings.
Pasting overwrites the target time span without shifting the video; a trimmed
or cut portion uses the target soundtrack. Undo/redo remains available. Use **Previous issue**
or **Next issue** to jump through suspected splices, **Listen across join**
to hear the transition, and **A/B** to switch output/target audio quickly.
Press Space to play/pause, J/L to navigate issues, and A to switch A/B.

**Save As…** lets you name the edited output and choose any directory or
drive. Export renders a new output without modifying the original inputs.
The normal output folder also accepts any destination and remembers your
previous choice; leave it blank to use the target-adjacent default.

### Opening cuts and tests

With destructive unmatched-video removal enabled, AutoSync verifies the
first unmatched segment using actual audio features. Shared opening music
is mapped back to the source when the evidence supports it; inconclusive
music keeps the target video/audio for manual review. Truly unrelated
audio can still be removed by the explicitly selected video-removal mode.


### Building Windows portable

See [the repository source-build guide](../build/windows/README.md).
The build includes Electron, embedded Python 3.12, NumPy, SciPy, FFmpeg
and FFprobe. The historical patcher and merge-helper scripts are no
longer part of the active source tree.
