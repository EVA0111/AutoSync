# AutoSync Wiki — v1.2.0

Welcome! This is the beginner-friendly documentation for **AutoSync**, a Windows program that helps line up audio (and, separately, subtitles) between two versions of a video.

**No coding is required** if you download the Windows portable release. Start with **Standard** matching, not the optional AI mode.

## Start here

- **[Getting started: your first audio sync](Getting-Started.md)** — download, unzip, add videos, choose audio tracks, start a sync, and find the result.
- **[AI-assisted matching (optional)](AI-Assisted-Matching.md)** — install the additional models, switch matching methods, and understand the limitations.
- [Subtitle syncing documentation](../AutoSync/README_SUBTITLES.md) — a separate workflow for subtitles.
- [Download AutoSync v1.2.0](https://github.com/EVA0111/AutoSync/releases/tag/v1.2.0)
- [Ask a question / report a problem](https://github.com/EVA0111/AutoSync/issues)

## What do “Source” and “Target” mean?

| Term | Meaning |
| --- | --- |
| **Source** | The video containing the **audio you want to use**. |
| **Target** | The video whose **picture/timing you want to match**. |
| **Output** | A new synchronized audio file (and, in certain modes, an edited video). Your original files are not changed. |

For example, if you want audio from DVD version A to fit Blu-ray version B, add DVD A under **Source** and Blu-ray B under **Target**. Choose the correct language/audio track for each.

**You do not need to make special “source” or “target” folders inside AutoSync.** Keep your media wherever you like and select them from the program.

## Which sync mode should I use?

| Sync mode | When to use it |
| --- | --- |
| **Full target audio** | Best for a first attempt. Sync audio to the entire target video and export a FLAC audio file. |
| **Main episode only** | Remove differing opening and ending material; export a video plus matching FLAC. Reliable boundaries may be required. |
| **Keep opening & ending** | Preserve the target opening/ending sound while synchronizing the main part. Useful for editions with different intros/outros. |

**Matching method** is a separate choice. **Standard (default)** requires no optional AI installation. **AI-assisted (experimental)** requires extra downloads.

## A video walkthrough

[Issue #10](https://github.com/EVA0111/AutoSync/issues/10) requests a recorded step-by-step tutorial. These written pages give the same sequence to follow now, but **a recorded video has not been supplied by this guide**. A future screencast should show download, extraction, choosing files, choosing tracks and mode, clicking **Start selected jobs**, then opening and reviewing the result.

These wiki-style pages live under the repository's **docs/** folder so they can be read without GitHub Wiki-specific tooling.
