# AutoSync v1.4.2

An Electron + Python/FFmpeg tool for matching audio and subtitles between
different video editions, including different playback speeds, openings,
scene edits, censored scenes and missing footage.

**New in v1.4.2:** Preview & Edit opens about 4 times faster and shows
its progress. **New in v1.4:** smooth crossfaded joins instead of brief dips, tiny cuts
found reliably, more than twice as fast, a "recreate" option for censored
dubs, a full video editor in Preview & Edit and the interface in 10 more
languages. AI-assisted sync is removed. 36 of 36 regression runs pass,
measured independently. See the [release notes](AutoSync/RELEASE_NOTES.md)
and the [wiki](docs/Home.md).

## Build the portable app

On Windows 10/11 x64, extract this source repository and run:

```bat
build\windows\build-portable.cmd
```

The builder installs dependencies in a private build environment and produces
`dist/AutoSync-v1.4.2-Windows-Portable.zip`. Unzip the result and run
`AutoSync.exe`; the finished portable application includes Electron,
Python 3.12, NumPy, SciPy, FFmpeg and FFprobe.

See [build/windows/README.md](build/windows/README.md) for requirements,
custom destinations and CI build instructions. There are no application
patchers or merges involved.

## Wiki (v1.4.2)

New to AutoSync? Start with the **[Wiki](docs/Home.md)**:
[Getting started](docs/Getting-Started.md) ·
[Preview & Edit](docs/Preview-and-Edit.md) ·
[Censored and edited dubs](docs/Censored-and-Edited-Dubs.md) ·
[How syncing works](docs/How-Syncing-Works.md) ·
[Troubleshooting](docs/Troubleshooting.md).
No coding or media folders inside the app are required for the Windows portable release.

## Use

1. Select source and target videos (single pair or batch). Choose audio tracks.
2. **Save output** is optional: it defaults beside the target video in
   `AutoSync Outputs`. Browse or enter any other drive/folder instead.
3. Click **Preview & Edit** to analyze the selected pair and review it on one
   screen: a review list of every join and flagged point, side-by-side /
   overlay / difference / wipe pictures, frame-accurate nudges, slow playback
   and the V1/A1/A2/MIX timeline. A saved plan can also be opened explicitly.
4. Fix anything by hand (move, trim, split, slip, copy/paste audio without
   shifting video timing; restore or cut censored scenes) and choose
   **Save As…** to write a corrected project and exported audio.
5. Click Start to run a normal job. The sync plan is always saved with the
   output. When reports are enabled, AutoSync creates an `AutoSync Reports`
   folder beside the application by default, with a separate folder for
   each job. Choose another reports location in Settings if preferred.

No original input is modified. If a cut/trim changes the video timeline,
use its matching synced audio with the exported video.

## Safeguards and limits

- Destructive unmatched-video decisions use audio evidence as a safeguard. Ambiguous material is preserved for review rather than removed without reliable support.
- Joins that would repeat source audio are refused; uncertain joins are flagged.
- Limits: frozen or very dark shots, very short re-timed shots, targets whose
  own picture is out of sync with their soundtrack, and audio-only jobs (older
  engine). See [How syncing works](docs/How-Syncing-Works.md).

## Source organization

- `AutoSync/*.py` — sync algorithms (`picture_timeline.py` is the main engine), output management, regression tests.
- `AutoSync/sync_accuracy.py`, `run_sync_matrix.py` — independent accuracy evaluator and regression-matrix runner (media stays local).
- `AutoSync/desktop/` — Electron app, waveform/editor interaction and tests.
- `AutoSync/sushi/` — Sushi support and bundled notices.
- `build/windows/` — reproducible source-to-portable builder.
- `.github/workflows/build-windows-portable.yml` — CI using the same builder.

Run tests from an activated Python 3.12 environment with requirements
installed: `python -m unittest discover -s AutoSync -p test_*.py -v`.
Editor tests: `cd AutoSync && npm install && npm run test:editor`.

By [EVA0111](https://github.com/EVA0111). Built using Electron, Python,
NumPy, SciPy and FFmpeg; optional subtitle workflows support Sushi.
