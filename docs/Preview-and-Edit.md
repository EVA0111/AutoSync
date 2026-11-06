# Preview & Edit (v1.4.3)

Preview & Edit lets you see and hear exactly what AutoSync did, and fix anything by hand. Nothing is changed until you save; the target's picture is never changed, only the timing of the audio.

**Open it:** select a pair in the **Audio** tab and click **Preview & Edit** in the bottom bar. AutoSync analyses the pair (or reuses a finished analysis) and opens the editor. You can also open a saved plan from a job's output folder.

## The screen

| Area | What it does |
| --- | --- |
| **Top bar** | File name, a chip with how many flagged points are left to check, the save state, **Undo/Redo**, **Save As…**, **Export corrected audio**, and **?** for shortcuts. |
| **Review list** (left) | Every join and flagged point with its time and reason. Filters: **All**, **Flagged**, **Not checked**, and **Censorship** when the censored-dub option was used. Click a point to jump there. **✓ Checked** (or **R**) ticks it off; a progress bar shows how many are done. Each point can have a note. |
| **Pictures** (centre) | Source and target at the playhead. Views: **Side by side**, **Overlay**, **Difference** and **Wipe**. In *Difference*, matching pictures go dark; edges that jump with motion mean the timing is off (steady outlines are only framing differences). |
| **Playback bar** | Step 1 or 10 frames, **Play**, listen to **Output**, **Source** or **Target** (A swaps output/target), **▶ Across join** (2 s either side), **Loop**, and **Speed** 1× / 0.5× / 0.25×. |
| **Clip panel** (right) | The selected clip: **Timing** (typed values, and move audio −1 frame / −10 ms / +10 ms / +1 frame), **Edit** (split, join, trim), **Audio for this clip** (source or target audio), **Clipboard** (In/Out, copy, cut, paste) and the **Review point**. |
| **Timeline** (bottom) | **V1** target picture (locked), **A1** source audio, **A2** target audio, **MIX** the result. The strip above it shows the whole episode: click or drag to move. **Ctrl+scroll** zooms; **Fit clip** / **Fit all**. Drag the bar above the timeline to resize it. |

## A typical review

1. Click **Flagged** in the review list.
2. Click the first point (or press **L**). Press **P** to play across it; press **A** to compare with the target's own audio.
3. If it sounds right, press **R**. If the audio is early or late, select the clip and use **−1 fr / +1 fr** or **−10 ms / +10 ms** (keys **, .** and **Alt+, Alt+.**), then play across it again.
4. Repeat until the chip says all flagged points are checked.
5. **Save As…** to a new folder, then **Export corrected audio**. The export log opens at the bottom.

## Editing tools

- **Select (V):** drag a clip to move it; drag its edges on **MIX** to trim. Drag a clip from A1 or A2 onto MIX to place it.
- **Razor (C):** click a clip to cut it.
- **Slip (Y):** drag to move the source audio inside its clip.
- **Snap (N):** snapping to joins and the playhead (hold **Shift** to override).
- Trimmed or cut ranges fall back to the target's own audio; nothing shifts in time.

## Video tracks and media

- **Video tracks:** add tracks above **V1**, or **duplicate** the locked target track and edit the copy. Upper tracks cover lower ones; the export shows the result from top to bottom. Each track can be **locked** or hidden.
- **Media pool:** import video, audio or images (or drag them in from Explorer) and drag them onto a track.
- **Fill motion:** mark a range and fill it with motion from the surrounding picture, for example to replace a frozen shot.

## Safety

- Your edits are saved automatically while you work. If the app closes, the next time you open the same plan it offers to **Restore edits**.
- Export refuses joins that would repeat source audio unless you fix them.

## Keyboard shortcuts

Press **?** in the editor for the full list. The most useful: **Space** play/pause, **← →** one frame, **Shift+← →** ten frames, **J / L** previous/next point, **P** play across join, **A** output/target, **R** mark checked, **S** split, **, .** move audio one frame, **Ctrl+Z / Ctrl+Y** undo/redo, **Ctrl+S** save.

[← Wiki home](Home.md)
