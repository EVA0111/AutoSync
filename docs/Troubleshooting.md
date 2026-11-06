# Troubleshooting (v1.4.2)

| Problem | Try this |
| --- | --- |
| **Start selected jobs** is greyed out | Read the message in the bottom bar and click **Show me**. Usually a list is empty, the two lists have different numbers of files, or **Include audio jobs** is off. |
| The Subtitles tab says syncing is turned off | Click **Turn on subtitle syncing**. |
| The wrong language is in the result | Check the **track menu** on each file row (Source = the track you want). |
| Episodes are paired wrongly | Check each row pair; use **Match episode numbers** or **Reorder rows**. |
| I can't find the output | **Jobs** tab → **Open output**. A blank **Save to** folder means **AutoSync Outputs** beside the target video. |
| I only got a FLAC, not a video | Full target audio exports FLAC. Mux it with the target video at 0 ms delay. |
| A job says **Needs review** | Open it in [Preview & Edit](Preview-and-Edit.md), click **Flagged** and check each point. |
| The disk fills up while syncing | **Settings → Folders → Temporary work folder (optional)**: choose a drive with more space. |
| "Unverified backwards source-audio joins" | A join would repeat audio. Open [Preview & Edit](Preview-and-Edit.md), go to the point and fix the clip timing. |
| "Source-only cut positions are unresolved" | The picture could not place a cut. Review it in Preview & Edit. |
| The opening/ending is cut wrongly in *Main episode only* | Try **Keep opening & ending**, or set the boundaries by hand (Settings → *Enable advanced audio settings*). |
| A target video won't play in Preview & Edit | Some formats (for example FFV1) can't play directly; AutoSync builds a preview copy in the background. Wait for it. |
| Restored censored scenes are much quieter or louder | Loudness is matched automatically (limit ±20 dB). Check the gain in the job log; adjust the clip in Preview & Edit if needed. |

Still stuck? [Open an issue](https://github.com/EVA0111/AutoSync/issues) with the job's **report.txt**.

[← Wiki home](Home.md)
