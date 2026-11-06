# AutoSync v1.4.3

Windows x64 portable release by [EVA0111](https://github.com/EVA0111).

v1.4.3 finds more of what censored and edited dubs changed, and always shows it. It contains everything in v1.4.2, v1.4.1 and v1.4, listed below.

### Censored and edited dubs

- **Replaced shots the dub filled with other material are found.** Before, a replaced shot was only reported when the dub reused a picture from close by (a freeze or a repeat). Shots replaced with the dub's own footage (for example a new title card) or with a shot from far away in the episode were missed. They are now reported, with where the shot comes from when the original has it. On the test episodes this finds 1 more change in one episode and 4 more in another, and no false reports on a tinted, low-quality dub.
- **Every edit is listed even with the censored-dub option off.** The report and Preview & Edit's *Censorship* list now show removed scenes, dub-only material and replaced shots whenever they are found; the option still decides whether removed scenes are restored or cut.
- Sync results are unchanged: these are reports only.

## v1.4.2: faster Preview & Edit

### Faster Preview & Edit

- **Opens about 4 times faster.** The picture analysis behind Preview & Edit does the same work with far fewer calculations. Sync results are identical to v1.4.1.
- **Hard pairs no longer stall.** On pairs where the pictures barely match (for example a low frame rate dub with replaced shots), picture matching could keep trying thousands of positions and appear to never open. It now keeps the most promising ones.
- **Shows its progress.** While it prepares, Preview & Edit says which of its 4 steps it is on (reading the audio, decoding the pictures, matching the pictures, opening the editor), in every interface language.

## Fixes in v1.4.1

v1.4.1 replaced v1.4.0, which was withdrawn because of problems in Preview & Edit.

- **Fits smaller windows.** The timeline takes a share of the window (at most half) and follows resizing; on a 1280×720 screen it used to take most of the window and shrink the pictures to thumbnails.
- **Always shows the right pictures.** A still frame loaded while a video was starting could stay on top of it, so one viewer kept showing an old or black frame at every jump.
- **Split (S) and trim (Q / W) work at the playhead**, whichever clip is selected; before, they could do nothing after the playhead moved.
- **Play across join (P)** plays the join nearest the playhead.
- The clip panel no longer cuts off its fields in Arabic and Persian.

## What's new in v1.4

### Cleaner, more accurate sound

- **No more dips at joins.** Every point where the synced audio jumps used to fade to silence for a moment (10 ms, 50 ms where a censored dub switches language). Joins are now smooth crossfades placed at the exact same time, so continuous audio stays seamless and every sample stays in sync.
- **Tiny cuts are found.** When a release removes only a few frames, the join could land seconds away from the real cut. AutoSync now searches past the matched sections when the pictures do not pin the cut, and lets the audio decide inside that span.
- **Safer rate detection.** The playback speed is chosen by which speed keeps the matched pictures steady, and single acts at another standard speed (for example one taken from a PAL master) are followed.
- More engine fixes found by a new suite of synthetic test videos with exact known answers: picture timing now starts at the first frame FFmpeg shows, a target whose audio ends before its picture keeps its own silence there, and four smaller timing errors.

### More than twice as fast

- Analysing a 20-minute episode took 74 s and now takes 32 s on the test machine (the picture matching itself is 3 to 8 times faster). Results are identical to before: the speed comes from doing the same work more efficiently and solving candidate playback speeds side by side on several CPU cores.

### Censored or edited dubs

- New **Recreate the dub's version** option: removed scenes are cut, and the freezes, repeats and replaced shots the dub used to cover them are rebuilt from the original's own pictures, with natural motion instead of frozen frames.
- **Better censorship detection.** Removed scenes now include the frames the dub covered with its own freeze or repeat; a mosaic, blur or painted patch over part of the frame is no longer mistaken for a different scene; slow or near-still shots no longer produce false "removed scene" reports; and removed footage inside a held shot is placed by the audio. Measured on a new set of 15 synthetic censored dubs (removed and trimmed scenes, freezes, mosaics, patches, zooms): 12 pass, up from 4 of the first 11.

### Preview & Edit

- A full video editor: any number of **video tracks** (duplicate a track and edit the copy above the locked original), a **media pool** with import and drag and drop from Explorer, **track locks**, a menu bar, and **Fill motion** for a marked range.
- Smooth, gapless playback and a faster timeline.
- The review list now flags only the joins that really need checking (before, every join was listed as needing review).

### Interface languages

- The whole app is available in **Arabic, German, Spanish, Persian, French, Hindi, Japanese, Korean, Portuguese and Chinese**, chosen from the top bar (right-to-left for Arabic and Persian).

### Removed

- **AI-assisted sync** (pretrained audio and scene models) is removed: the picture-based engine gives the same or better results without it, and nothing extra needs to be downloaded. **Subtitle AI** (speech recognition and translated-dialogue matching) is unchanged.

### Verification

- Regression matrix on 9 real episode pairs in all 4 output modes: **36 of 36 runs pass**, measured by an independent tool that compares the finished output with the original source.

## What's included

- Synchronize audio across differently edited videos and export pitch-preserving FLAC (and, in some modes, an edited video).
- Subtitle syncing using audio, video, saved-map and optional AI workflows.
- Bundled Python 3.12, NumPy, SciPy, FFmpeg and FFprobe: nothing else to install for normal use.

## Installation

1. Download **AutoSync-v1.4.3-Windows-Portable.zip**.
2. Extract it into a writable location.
3. Open **AutoSync.exe** inside the extracted **AutoSync-v1.4.3-Windows-Portable** folder.

New to AutoSync? Read the [wiki](https://github.com/EVA0111/AutoSync/blob/main/docs/Home.md).

Listen across flagged joins before distributing outputs. AutoSync never overwrites your original videos.

## Source

The source repository includes the portable Windows build scripts under `build/windows`. All application windows and package metadata display **v1.4.3**.
