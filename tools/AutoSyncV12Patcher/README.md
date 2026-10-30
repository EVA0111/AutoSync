# AutoSync v1.2 Preview & Edit — One-click Windows patcher

**This is a Windows x64 patcher, not the v1.2 application itself.**

1. Extract your **AutoSync-v1.2-Windows-Portable.rar** folder first.
2. Put \`AutoSync-v1.2-PreviewEdit-Patcher.exe\` inside the extracted folder (beside \`AutoSync.exe\`), or double-click it from anywhere and select the folder.
3. The patcher downloads the Preview & Edit Electron desktop shell, copies your v1.2 engine and Python runtime, runs smoke checks, and makes a fresh **AutoSync-v1.2-PreviewEdit-Windows-Portable.zip** beside your original extracted folder.
4. Extract the new ZIP, then launch its \`AutoSync.exe\`.

The original v1.2 folder is never modified. The new GUI is derived from the public Preview & Edit shell; it may still show legacy v1.1 labels. A precise FFmpeg command-line compatibility fix is applied *only to the copied* \`video_edits.py\`, if needed.

**Limits:** This is a v1.2 engine, not v1.3. It is *not* a verified repair of case 1's opening-removal algorithm. The manual editor cannot restore frames previously removed by an old analysis plan. On first run analyze the original videos again, keep the opening intact, then review the output in Preview & Edit. Real-media editor/export integration remains unverified.

The patcher is self-contained and does not require .NET installed. An internet connection is required to download the Preview & Edit application (~300 MB).
