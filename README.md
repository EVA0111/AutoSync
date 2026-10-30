# AutoSync — source and Windows portable build

An Electron + Python/FFmpeg tool for matching audio and subtitles between
different video editions, including different playback speeds, openings,
scene edits and missing footage.

## Build the portable app

On Windows 10/11 x64, extract this source repository and run:

```bat
build\windows\build-portable.cmd
```

The builder installs dependencies in a private build environment and produces
`dist/AutoSync-Source-Windows-Portable.zip`. Unzip the result and run
`AutoSync.exe`; the finished portable application includes Electron,
Python 3.12, NumPy, SciPy, FFmpeg and FFprobe.

See [build/windows/README.md](build/windows/README.md) for requirements,
custom destinations and CI build instructions. There are no application
patchers or merges involved.

## Use

1. Select source and target videos (single pair or batch). Choose audio tracks.
2. **Save output** is optional: it defaults beside the target video in
   `AutoSync Outputs`. Browse or enter any other drive/folder instead.
3. Click **Preview & Edit** to automatically analyze the selected pair, inspect
   its three-track timeline, and listen across joins; no plan.json is required.
   A saved plan can also be opened explicitly.
4. Review flagged joins, drag/split/nudge regions, compare source, target and
   edited output audio, copy/paste audio clips, mark In/Out and trim without
   shifting video timing, and choose **Save As…** to write a corrected project
   and exported audio in a separate location.
5. Click Start to run a normal job. The sync plan is always saved with the
   output, even when optional full diagnostic reports are disabled.

No original input is modified. If a cut/trim changes the video timeline,
use its matching synced audio with the exported video.

## Safeguards and limits

- Shared opening music is checked *before* destructive unmatched-video
  removal. Verified matching source music is mapped; inconclusive openings
  retain their target footage and music for manual review.
- The algorithm still has limits for different language tracks, repeated OP
  themes, mixed timing, silence and source-specific edits. Review warnings.

## Source organization

- `AutoSync/*.py` — sync algorithms, output management, regression tests.
- `AutoSync/desktop/` — Electron app, waveform/editor interaction and tests.
- `AutoSync/sushi/` — Sushi support and bundled notices.
- `build/windows/` — reproducible source-to-portable builder.
- `.github/workflows/build-windows-portable.yml` — CI using the same builder.

Run tests from an activated Python 3.12 environment with requirements
installed: `python -m unittest discover -s AutoSync -p test_*.py -v`.
Editor tests: `cd AutoSync && npm install && npm run test:editor`.

By [EVA0111](https://github.com/EVA0111). Built using Electron, Python,
NumPy, SciPy and FFmpeg; optional subtitle workflows support Sushi.
