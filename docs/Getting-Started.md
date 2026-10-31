# Getting started — your first AutoSync audio sync (v1.2.0)

This guide is for people who have never used a sync tool or written code. You only need a **Windows 10/11 64-bit** computer, two video versions, and enough free disk space for output.

**Goal:** take audio from one video and make it line up with the picture of another video.

## 1. Download AutoSync

1. Open the [AutoSync v1.2.0 release page](https://github.com/EVA0111/AutoSync/releases/tag/v1.2.0).
2. Under **Assets**, download **AutoSync-v1.2.0-Windows-Portable.zip**. Do not download the repository's **Source code** ZIP for this beginner workflow.
3. In Windows File Explorer, right-click the downloaded ZIP and choose **Extract All…**.
4. Extract everything into a folder you can write to, such as **Documents\AutoSync**. **Do not run the app from inside the ZIP** or move only the EXE out of the extracted folder.
5. Open the extracted **AutoSync-v1.2.0-Windows-Portable** folder and double-click **AutoSync.exe**.

The portable download already includes the regular Python and FFmpeg components. **You do not need Python, a coding editor, or a command prompt** for normal Standard audio sync. You also do not have to build AutoSync from source.

**If the program does not start:** confirm you extracted the entire ZIP, use Windows x64, and keep the application files together. You can open **Settings → Setup → Check / set up engine** if the app itself opens but says its engine is not ready. Only run downloads you trust from the project's release page.

## 2. Keep your input videos wherever you like

There is **no required folder structure** for the media files. For convenience, you might organize them like this (these are only examples):

    Videos\
      Source\
        Episode 01.mkv
      Target\
        Episode 01.mkv

Do **not** copy the videos into the AutoSync program folder. Select them from their existing locations.

Remember the difference:

- **Source = the audio you want.** For example, an older DVD with the language or dub you want to transfer.
- **Target = the picture/timing to fit.** For example, a newer Blu-ray video.

If you accidentally swap them, you may sync in the wrong direction.

## 3. Add your first pair of videos

1. Open AutoSync and select the **Audio** tab near the top.
2. Make sure **Include audio jobs** is checked. Leave **Include subtitle jobs** unchecked if you are only syncing audio.
3. In the **Source** column (**Audio to transfer**), click **Add files** and choose your source video.
4. In the **Target** column (**Video to match**), click **Add files** and choose the target video.
5. Allow the program to finish reading the files and detecting their audio tracks.

You can also drag videos into the correct columns. For a first test, use **one video in each column**.

**Working with several episodes?** Use **Add folder** on each side, then open **Review pairing & reorder**. Source row 1 is paired with target row 1, etc. **Match episode numbers** can help when filenames include recognizable episode numbers. **Check every pair** before starting, especially if numbering or filenames differ.

## 4. Choose the correct audio tracks

If a video contains multiple audio tracks (for example, Japanese, English and commentary), choose which track the program should use.

1. Find the audio-track selector next to each file, or expand **Track settings for selected pair**.
2. For **Source audio**, select the track you want in the result.
3. For **Target reference audio**, select the target's soundtrack that is most useful for comparison. Where possible, choose a track sharing the same sounds/music as the source.
4. If using **Keep opening & ending**, check the **Target opening / ending** audio track too.

If you do not change the track selection, the app may use the first detected track. **Do not assume track 1 has the language you want.** Some editions have different dubs or sound effects, making automatic matching harder.

## 5. Choose a sync mode and matching method

In the **Audio** area:

1. Under **Sync mode**, select **Full target audio** for your first test.
2. Under **Matching method**, leave **Standard (default)** selected.
3. Leave advanced settings at their defaults until you have completed one simple sync.

The three output modes are:

| Mode | Result and purpose |
| --- | --- |
| **Full target audio** | Sync to the whole target and write a pitch-preserving **FLAC** audio file. Best place to begin. |
| **Main episode only** | Remove differing opening/ending sections and export **video + FLAC**. Uncertain boundaries may require manual review. |
| **Keep opening & ending** | Use the target opening/ending audio and synchronize the main episode. Useful for different OP/ED music, titles or timing. |

**Important:** **Sync mode** controls what is exported; **Matching method** controls how AutoSync searches for corresponding material. They are independent choices. The default sync mode in the interface may be **Keep opening & ending**, so explicitly select **Full target audio** when following this first-run example.

## 6. Decide where the result will go

Find **Save output** and its **Folder (optional)** field.

- **Simplest:** leave this field blank. AutoSync makes an **AutoSync Outputs** folder beside the target video.
- **Choose a folder:** click the folder/Browse control and select a writable destination on any drive.
- The **Use target folder** button chooses the target's parent folder directly.

You do not need to create an output directory by hand. The app does **not overwrite your original source or target video**. Keep output separate from inputs when possible, and make sure there is enough free disk space.

## 7. Start synchronization

1. Look at the readiness message. When the inputs are ready, it says **Ready to sync the selected jobs.**
2. If it instead explains something missing, click **Show me**, fix that field, and check again.
3. Click **Start selected jobs**.
4. Watch the progress/status bar; do not close AutoSync before the job finishes.
5. Open the **Jobs** tab to view the result. You may see **Finished**, **Needs review**, or **Failed**.
6. Use **Open output** to go to the generated files. If reports were enabled, use **Open reports** beside a job to inspect its report.

**For Full target audio:** the synchronized result is a **FLAC audio file**, not necessarily a new finished video containing that audio. Bring the FLAC into your video editor or muxing tool along with the target video if you want a final combined video. Check that their starting times and lengths match.

The application stores a sync plan along with audio output. Optional detailed reports can be enabled under **Settings → Save reports and timing plans**; the default reports location is **AutoSync Reports** beside the application, with a folder for each job. You can choose another reports location in Settings.

## 8. Listen and check the result

**Automatic sync is not guaranteed to be perfect.** Listen near the beginning, middle and end and across any cut, particularly if the two versions have different openings, songs, silence, missing scenes, or languages.

If the job says **Needs review**, do not assume the result is finished.

To inspect or fix a difficult pair:

1. Select the source and target pair in **Audio**.
2. Click **Preview & Edit**. AutoSync analyzes the complete target timeline for review.
3. In the editor, play around flagged transitions, compare the corrected sound to the target, and use **Previous issue**, **Next issue**, **Listen across join**, or the **A/B** comparison.
4. The **MIX** lane is the corrected audio; audio clips can be moved, trimmed or split. The target video lane **V1** stays locked.
5. Use **Save As…** in the editor to save the corrected project/output to a chosen location.

You can also use a video's small preview icon **before** syncing to set source or target trim points. This is optional and separate from **Preview & Edit**. Trims keep only the marked range; original media are unchanged.

## 9. Optional: try AI-assisted matching

**You do not need AI mode for normal synchronization.** If Standard struggles, read **[AI-assisted matching](AI-Assisted-Matching.md)**. AI requires extra model installation and may not improve the result.

## Troubleshooting for beginners

| Problem | Try this |
| --- | --- |
| **Start selected jobs** is disabled | Read the readiness message, press **Show me**, verify **Include audio jobs**, and make sure both Source and Target contain the same number of videos. |
| I can add files but nothing happens | Adding files only builds a job. Select a mode and click **Start selected jobs**. |
| The wrong language is used | Check **Source audio** and **Target reference audio** in the track selectors before syncing. |
| Episodes are paired incorrectly | Expand **Review pairing & reorder** and inspect each source/target row. |
| I cannot find my output | Check **Save output**, the **Jobs** tab, and **Open output**. Blank destination defaults to **AutoSync Outputs** next to the target. |
| Audio drifts at opening/ending or cuts | Review the selected mode, try **Preview & Edit**, and inspect any flagged joins. |
| I just want a new video with the new audio | Full-target mode exports **FLAC**. You must combine it with the target video in your editor/muxer. |
| AI setup is confusing | Keep **Standard (default)** until the basic workflow succeeds. See the separate AI page for the optional install. |

## What is not yet completely documented?

This guide follows the v1.2.0 release notes, README, and current interface labels. The repository still does **not** provide all of these beginner-facing details:

- **A recorded video tutorial** showing actual clicks and a complete successful run (requested in [issue #10](https://github.com/EVA0111/AutoSync/issues/10)). This is a written guide, not a video.
- A validated **disk-space / RAM / first-run duration** estimate for typical jobs, especially AI model downloads.
- A novice-friendly, tested procedure for **muxing** the exported FLAC back into an MKV or MP4 in a chosen editor.
- A screenshot-by-screenshot walkthrough of selecting the correct audio stream, responding to a manual OP/ED boundary request, and fixing a **Needs review** output.

For the latest instructions and any changes after v1.2.0, check the [repository README](../README.md) and [releases](https://github.com/EVA0111/AutoSync/releases).

[← Wiki home](Home.md) · [Optional AI-assisted mode →](AI-Assisted-Matching.md)
