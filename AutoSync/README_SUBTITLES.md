# Subtitle sync — AutoSync v4.0.0

Open `AutoSync.exe`, enable **Subtitles** in **Sync jobs**, choose a timing reference and add one file or many to the lists. Choose the global Output folder before starting. Enable advanced subtitle options and optional report saving in Settings. The same lists handle one episode or multiple episodes.

## Three workflows

1. **Another already-synced subtitle:** select the subtitle to retime and the reference subtitle already matching your target. Either can be a sidecar or a supported embedded track in MKV/MP4. The reference timing is authoritative; an audio track in that container is not needed or analyzed in this mode.
2. **Source encode → target encode:** choose your subtitle, its original video, and the target video. The engine matches distinctive pictures, estimates speed and delay within continuous sections, and leaves uncertain cut boundaries unresolved. Use this mode for signs and frame-sensitive typesetting. Black borders are detected; manual matching crops are available for reframed editions.
3. **Target audio, no subtitles:** choose the subtitle and the target video/audio. Speech recognition finds spoken words and matches them against subtitle dialogue. Select the correct audio track (the menu shows language and format; command-line track numbering starts at 0). Audio-only input is supported. Different wording, songs, short phrases, and recognition errors can leave gaps.

A fourth **Saved timing map** option reuses `subtitle_map.json` or an existing AutoSync audio plan. Imported audio plans are flagged for review because dub timing may differ from picture timing.

## Optional AI setup

In the app, open **Setup → Install subtitle AI** once for audio matching or the **Different languages / translated dialogue** checkbox. It installs faster-whisper and sentence-transformers into AutoSync's bundled Python environment. Models download on first use, requiring internet and additional disk space. Media processing runs locally on CPU. Default speech model: `small`; changing it can affect speed, downloads, and accuracy.

Same-language subtitle matching and picture matching do not require the optional AI packages. Cross-language matching is approximate and depends on the translation; it can reject a job if it cannot establish enough consistent matches. We have not validated speech recognition or multilingual model accuracy against your actual episodes.

## Typesetting and formats

Original text, styles, layers, margins, resolution, drawing coordinates, embedded ASS font sections, and other non-timing content are retained. ASS/SSA start/end timestamps and timed move, fade, transform, and karaoke tags are scaled together. Cumulative rounding limits karaoke drift. Container font attachments are extracted into a fonts folder; install or attach these fonts when playing/muxing the result. External fonts for sidecar subtitles must still be supplied separately.

Supported without flattening to SRT:

| Format | Scope |
| --- | --- |
| ASS / SSA | Styled dialogue, drawings and timed overrides; legacy Effect speed changes require review |
| SRT | Timing replacement; markup retained |
| WebVTT | Styles, settings and inline timestamps; X-TIMESTAMP-MAP rejected |
| SBV | Text and timestamps |
| MicroDVD text SUB | Explicit source FPS required; optional target FPS and header updated |
| MPL2 | Text and decisecond timestamps |
| SAMI / SMI | SYNC timestamps; layout retained |
| TTML / DFXP / XML | Flat paragraphs with explicit absolute begin/end only; inherited, nested and duration timing rejected |
| PGS SUP | Native packet timestamps; image payload unchanged; encode or saved-map modes only |
| Embedded tracks | ASS, SSA, SubRip, WebVTT and PGS can be extracted losslessly from supported media containers |

This is **not universal format support**. Binary VobSub SUB/IDX, broadcast STL/SCC and other unsupported formats need an external conversion or a dedicated future adapter. Bitmap subtitles cannot be text-matched without OCR, which is not included. SUP timestamp wrapping/reordering is rejected. A bitmap display crossing an unresolved cut is rejected rather than exporting partial output.

Positions and drawing geometry are preserved, **not repositioned** for a different crop or aspect ratio. Audio cannot establish when a silent sign appears. Recognized typesetting in nonvisual modes is flagged for review. Plain text signs without distinguishing tags/styles may not be identifiable as signs. Picture matches also require checking: there is no guarantee of frame-perfect output on every edition.

## Output and uncertainty

The desktop app puts final subtitles directly in the global Output folder using source-based filenames. Internal names below apply to CLI/engine jobs. Reports/maps are only retained when Save reports is enabled; the desktop app prefixes their names and places them directly in your separate reports folder. DRAFT names remain marked regardless of report saving.

The engine builds monotonic piecewise speed/offset sections, rejects ambiguous text/picture matches, and avoids interpolating across detected discontinuities. At least four consistent text/speech anchors are required (picture matching needs at least six unique scene matches). Distant anchors, inconsistent picture timing, nonvisual typesetting, and unsupported spans are reported.

- `synced.<original extension>`: output when no cues are flagged.
- `DRAFT-review-required.<extension>`: output requiring inspection. **Unmapped text cues retain their ORIGINAL source timing. Do not mux a draft before resolving these cues.** They are not silently removed or moved across cuts.
- `report.txt`: readable review list with source times.
- `subtitle_report.json`: each cue's original and mapped times, status and reason.
- `subtitle_map.json`: reusable source-to-target map.
- `anchors.json` for text matching; `transcript.json` for audio mode.

A saved native map uses seconds:

```json
{"direction":"source_to_target","evidence":"manual","sections":[{"start":0,"end":120,"scale":1.0,"offset":2.0,"anchors":[],"quality":"estimated: manual map"}]}
```

Target time = source time × scale + offset. Sections must be ordered, positive-speed, and non-overlapping in both timelines. Split sections at cuts. Never label an unverified manual map as visual evidence.

## Command line

```bat
.venv\Scripts\python.exe subtitle_sync.py --mode reference --subtitle input.ass --reference-subtitle reference.srt --out subtitle_job
.venv\Scripts\python.exe subtitle_sync.py --mode encodes --subtitle input.ass --source-video source.mkv --target-media target.mkv --out subtitle_job
.venv\Scripts\python.exe subtitle_sync.py --mode audio --subtitle input.srt --target-media target.mkv --audio-track 0 --out subtitle_job
```

Use a different new output folder for each run. `--help` lists all options. Original input files are never modified.

## Sushi subtitle mode

Select **Sushi — audio matching (ASS / SRT)** in Subtitles. Drop subtitles timed to the source into the first column, the source audio/video into the second, and the target audio/video into the third. Check pairing and choose each audio track before starting. One or many episodes use the same lists. Both versions need recognizable shared audio; this mode does not work with only a subtitle and target audio.

The Windows package includes the unmodified [tp7/Sushi 0.5.1](https://github.com/tp7/Sushi/releases/tag/0.5.1) prerelease under its MIT license. AutoSync decodes selected tracks, imports Sushi's cue timings, and keeps the original subtitle text and styles. It does not enable keyframe snapping. Results are marked DRAFT-review-required because audio alone cannot verify silent signs or frame-by-frame typesetting. Search windows are available when advanced subtitle settings are enabled. Other AutoSync modes remain available for other formats.
