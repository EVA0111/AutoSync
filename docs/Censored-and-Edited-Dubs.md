# Censored and edited dubs (v1.4.1)

Many older dubs (for example Arabic dubs of Japanese anime) **removed scenes** the studio considered unsuitable, or **re-cut** them from other shots so the story still flowed. If you want the dub's audio on the original, uncut video, AutoSync can find every such change and let you decide what happens to each one.

Put the **dub as the Source** and the **original as the Target**.

## What AutoSync finds

- **Removed scenes:** footage the original has and the dub does not. For each one AutoSync also notes when the dub shows some other footage in its place.
- **Dub-only material:** footage the dub has and the original does not (re-created or extended scenes, reused shots). There is no original picture to put this audio on, so it is listed for you but not used.

Example (one real test episode): 6 removed scenes of 1.4–13.7 s (44 s in total) and 11 dub-only spots of 1–5 s.

## Turning it on

In the **Audio** tab, find the **Censored or edited dub** card and choose:

| Choice | What happens to each removed scene |
| --- | --- |
| **Off (the source is complete)** | Normal behaviour. |
| **Restore with the original audio** | The uncensored scene stays in the video and plays the **original audio**. Its loudness is matched to the dub around it (old originals are often much quieter) and the switches between languages are softened. |
| **Cut from the video** | The scene is removed from the exported video, as the dub did. The output is shorter by exactly those scenes. |
| **Recreate the dub's version** | The scene is cut, and what the dub showed instead (a held frame, a repeated shot, a replaced shot) is rebuilt from the original's own pictures, with gentle motion instead of a frozen frame. The result looks like the dub's edit, in the original's picture quality. |

With **Restore**, you can also give **Subtitles for restored scenes (optional)**: subtitles of the original version. AutoSync writes **restored_scenes.srt** containing only the lines inside the restored scenes, timed to the output, so viewers can follow the original-language parts.

## Deciding scene by scene

Open **[Preview & Edit](Preview-and-Edit.md)** and click the **Censorship** filter in the review list. It lists every removed scene ("Removed · restored" or "Removed · cut") and every dub-only spot. Click a scene and use **Restore (original audio)** or **Cut from video** under the list. Scenes set to be cut are hatched "cut on export" on the picture track. Changes can be undone and are kept when you save and export.

## Reports

Each job writes **censorship_report.txt** (and **censorship.json**) with every scene: time, length, what the dub did and what AutoSync did. The same summary is at the top of **report.txt**.

## Limits

- Dub-only material is reported, not used: the original has no picture for it.
- The original audio of a restored scene is in the original language; the optional subtitle file helps viewers.
- Loudness matching is limited to ±20 dB and never clips.

[← Wiki home](Home.md)
