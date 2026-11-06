# Getting started — your first sync (v1.4.3)

This guide is for people who have never used a sync tool. You need a **Windows 10/11 64-bit** computer, two versions of a video, and some free disk space.

**Goal:** take the audio from one video and make it fit the picture of another.

## 1. Download and open AutoSync

1. Open the [AutoSync v1.4.3 release page](https://github.com/EVA0111/AutoSync/releases/tag/v1.4.3).
2. Under **Assets**, download **AutoSync-v1.4.3-Windows-Portable.zip** (not the "Source code" ZIP).
3. Right-click the ZIP and choose **Extract All…**, into a folder you can write to, such as **Documents\AutoSync**.
4. Open the extracted **AutoSync-v1.4.3-Windows-Portable** folder and double-click **AutoSync.exe**.

Python and FFmpeg are already included. If the app opens but says the engine is not ready, open **Settings → Engine → Check / set up engine**.

## 2. The main window at a glance

- **Top bar:** **Audio**, **Subtitles** and **Jobs** tabs, **Settings** on the right.
- **Audio tab, left:** the **Source** list (*audio to transfer*) and the **Target** list (*video to match*).
- **Audio tab, right:** the job settings: **Output**, **Matching**, **Censored or edited dub**, **Save to**, **Audio tracks**.
- **Bottom bar:** tells you the next thing to do (with a **Show me** button), and holds **Preview & Edit** and **Start selected jobs**.

## 3. Add your videos

1. In the **Audio** tab, keep **Include audio jobs** ticked.
2. Under **Source**, click **Add files** and pick the video whose **audio** you want.
3. Under **Target**, click **Add files** and pick the video whose **picture** you want to keep.

You can also drag files into the lists. For several episodes use **Add folder** on both sides: row 1 pairs with row 1, and so on. **Match episode numbers** lines rows up by the numbers in the filenames; check every pair, and use **Reorder rows** if needed. The selected pair is highlighted in both lists.

## 4. Choose the audio tracks

Each file row has its own **track menu** (for example *Track 2 · jpn*). Pick:

- **Source:** the track you want in the result.
- **Target:** the target's soundtrack (used for comparison, and for any scenes only the target has).

Do not assume track 1 is the language you want. For more detail open **Audio tracks → Tracks for the selected pair**.

## 5. Choose the output

- **Output:** pick **Full target audio** for your first try. (The other two cards are explained on the [wiki home page](Home.md).)
- **Censored or edited dub:** leave **Off** unless your source is a dub that cut scenes ([see this page](Censored-and-Edited-Dubs.md)).

## 6. Where the result goes

**Save to → Folder (optional):** leave it blank and AutoSync creates **AutoSync Outputs** beside the target video. Or click **Browse**, or **Use target folder**. Originals are never overwritten.

Large temporary files go to **AutoSync Temp** beside the target video while a job runs and are removed afterwards. To use another drive, set **Settings → Folders → Temporary work folder (optional)**.

## 7. Start

1. When the bottom bar says **Ready to sync the selected jobs.**, click **Start selected jobs**. If it says something is missing, click **Show me**.
2. The bottom bar shows progress. Don't close AutoSync until it finishes.
3. Open the **Jobs** tab. Each job shows **Finished**, **Needs review** or **Failed**; the tab badge counts results that need review. Use **Open output** to find the files.

**Full target audio exports a FLAC audio file**, not a finished video. Mux it with the target video (at 0 ms delay) in your editor or muxing tool. *Main episode only* and some other options also export an edited video; use the FLAC from the same job with it.

## 8. Check the result

Automatic sync is very accurate on most material but not guaranteed. Listen near the start, the middle, the end and across any flagged point. If a job says **Needs review**, check it in **[Preview & Edit](Preview-and-Edit.md)** before using it: select the pair and click **Preview & Edit** in the bottom bar.

Optional: before syncing, the small play icon on a file row lets you mark a range to use from that video (for example to drop a recap). Originals are not changed.

## Next steps

- [Preview & Edit](Preview-and-Edit.md): review and fix by hand.
- [How syncing works](How-Syncing-Works.md): what is measured and what can go wrong.
- [Troubleshooting](Troubleshooting.md).

[← Wiki home](Home.md)
