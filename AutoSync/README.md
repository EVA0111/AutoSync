# AutoSync v1.1

By [EVA0111](https://github.com/EVA0111).

AutoSync is a Windows desktop app that syncs audio and subtitles between different editions of a video. It compares pictures and sound, adjusts timing and audio speed while preserving pitch, and flags uncertain sections for review.

## Download and use

Download **AutoSync-v1.1-Windows-Portable.zip** from this repository's **Releases** page. Extract the entire ZIP to a new folder, then open **AutoSync.exe**. The portable download includes Python, FFmpeg, and the core dependencies.

1. Drop source videos into the left column and matching target videos into the right column. One pair or many pairs use the same workflow.
2. Choose audio tracks and an output mode: full target, main episode only, or keep target opening/ending.
3. Optionally click a video's preview icon to trim it before syncing. Source and target trims are independent. Seek by timestamp or frame number; frames start at 1. End marks exclude the selected frame.
4. Choose an output folder, check the pairs, and start.
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

The first command creates a local `.venv` and installs NumPy/SciPy. For optional subtitle AI, use the Settings button or `python runtime_setup.py --ai`. Sushi mode additionally needs the upstream Sushi executable at `sushi/sushi.exe`; see `sushi/UPSTREAM.txt`. Use the portable release if you want the already bundled Windows app.

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
- Choose the single **Output folder** and confirm the pairs before starting. **Settings** controls optional reports, advanced options, CSV import, and saved plans.
- **Jobs** shows completed results, failures, and items that need review. It also contains the optional activity log. Progress stays visible at the bottom.

The preview shows individual frames and is silent. The synchronization engine and its formats are unchanged in this interface update.

## Preview & Edit (feature branch)

Click **Preview & Edit** and choose the `plan.json` saved by a previous AutoSync analysis. The editor displays aligned Source, Target and Output waveforms and source/target video frames, with audible source, target and reconstructed output previews. Drag a source region to shift its source audio, drag a shared boundary to retime adjacent regions, or use the inspector to set source position and speed. Split, merge, switch source/target audio, loop, zoom and undo/redo are available.

**Save edited plan** creates a distinct `AutoSync_Edited_*` output folder. **Export corrected audio** renders the edited plan without replacing the original. The plan's existing video cuts/trims still apply; the editor does not automatically recover footage already excluded from a previously trimmed plan. Re-analyze to benefit from the conservative shared-music opening guard.

This editor requires the bundled FFmpeg and Python sync engine; it is not a standalone browser application. Direct MP4/MKV playback is not assumed: previews are decoded by FFmpeg. Review the join positions and listen before using the output. This branch currently needs validation on Windows before a portable release.
