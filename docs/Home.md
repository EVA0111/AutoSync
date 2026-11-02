# AutoSync Wiki — v1.3.0

**AutoSync** is a Windows program that takes the audio from one version of a video and fits it to the picture of another version, even when the two releases are edited differently. It can also sync subtitles.

No coding is needed: download the Windows portable release, unzip it and run **AutoSync.exe**.

## Pages

| Page | Read it when |
| --- | --- |
| **[Getting started](Getting-Started.md)** | You are new: download, add two videos, choose tracks, sync, find the result. |
| **[Preview & Edit](Preview-and-Edit.md)** | You want to check a result, listen across joins and fix anything by hand. |
| **[Censored and edited dubs](Censored-and-Edited-Dubs.md)** | Your source is an old dub that removed or re-cut scenes. |
| **[How syncing works](How-Syncing-Works.md)** | You want to know what AutoSync does, how accurate it is and where it can go wrong. |
| **[AI-assisted matching](AI-Assisted-Matching.md)** | Optional extra models. Not needed for normal use. |
| **[Troubleshooting](Troubleshooting.md)** | Something did not work. |
| [Subtitle syncing](../AutoSync/README_SUBTITLES.md) | A separate workflow for subtitles. |

- [Download AutoSync v1.3.0](https://github.com/EVA0111/AutoSync/releases/tag/v1.3.0)
- [Ask a question / report a problem](https://github.com/EVA0111/AutoSync/issues)

## Source and target

| Term | Meaning |
| --- | --- |
| **Source** | The video with the **audio you want** (for example an old DVD with your language). |
| **Target** | The video whose **picture you want to keep** (for example a newer Blu-ray). |
| **Output** | A new synced audio file (FLAC), and in some modes an edited video. Your original files are never changed. |

Keep your videos wherever you like; you do not need special folders.

## What's new in v1.3.0

- **Much more accurate.** AutoSync now matches the source audio to the target's *picture*. Earlier versions followed the target's own dub track, which is often 90–250 ms off its own picture. Checked on 8 real episode pairs in every mode: typical error 9–17 ms, 64 of 64 runs pass. See [How syncing works](How-Syncing-Works.md).
- **Handles messy edits:** re-cut and reordered shots, added or removed scenes, frozen shots held longer, slow picture drift, different playback speeds.
- **Censored or edited dubs:** restore or cut every scene a dub removed, scene by scene. See [Censored and edited dubs](Censored-and-Edited-Dubs.md).
- **Redesigned Preview & Edit:** everything on one screen with a review list of every join. See [Preview & Edit](Preview-and-Edit.md).
- **Cleaner main window:** your files on the left, the job settings on the right, one bar at the bottom that tells you the next step.

## Which output mode?

| Output | Use it when |
| --- | --- |
| **Full target audio** | Best first try. Syncs audio to the whole target; exports FLAC. |
| **Main episode only** | The releases have different openings/endings and you want only the episode; exports video + FLAC. |
| **Keep opening & ending** | Keep the target's own opening/ending audio and sync the episode in between. |

**Matching method** is a separate choice. **Standard** is the default and needs nothing extra; **AI-assisted** is optional (see its page).

**Always listen across flagged joins before using a result.** AutoSync marks anything it is unsure about.
