# AutoSync v1.1

Windows portable release by [EVA0111](https://github.com/EVA0111).

- Audio and subtitle syncing, with single-file and batch workflows.
- Audio-track selection, drag-and-drop pairing, progress and review reporting.
- Exact source/target video and audio trims before syncing.
- Video preview with time and frame-number navigation.
- Full-target, main-episode, and keep-opening/ending modes.
- Optional removal of target sections without source audio, with an edited video and matching FLAC.
- AutoSync v1.1 branding and a GitHub profile link in the GUI.

Download **AutoSync-v1.1-Windows-Portable.zip**, extract the whole folder, and launch **AutoSync.exe**. Core dependencies are included. Optional subtitle AI requires additional downloads. Check flagged sections and joins before using the output.

### Interface remodel

- Replaced the sidebar with Audio, Subtitles, and Jobs tabs.
- Added per-file audio selectors beside the preview controls.
- Moved reordering into an expandable pairing editor and simplified mode selection.
- Kept one output destination, optional settings, and visible progress.
- Added a results table with review and failure states.
- Preserved simultaneous audio/subtitle queues, frame-based trims, and all existing synchronization modes.

Tested in Electron on Linux with media probing, frame trimming, English layout, queue payloads, and settings. The Windows portable package was integrity-checked but not executed on Windows.
