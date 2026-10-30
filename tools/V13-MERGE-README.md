# Combine the actual AutoSync v1.3 engine with Preview & Edit

The public Preview & Edit GitHub release was built from the old v1.1 engine.
**Do not mistake that ZIP for v1.3.**

To preserve the real v1.3 installation, the Windows helper in this folder
copies the actual `resources/engine` and `resources/python` folders from an
existing **AutoSync v1.3 portable** installation into a fresh copy of the
Preview & Edit desktop shell. It does not modify the original v1.3 directory.

## Use on Windows

1. Make sure your existing AutoSync v1.3 portable folder contains
   `AutoSync.exe`, `resources/engine/autosync.py`, and `resources/python/python.exe`.
2. Download `Make-AutoSync-v1.3-PreviewEdit.ps1` and
   `Make-AutoSync-v1.3-PreviewEdit.cmd` from this `tools` folder,
   then place both files directly next to the existing v1.3 `AutoSync.exe`.
3. Double-click `Make-AutoSync-v1.3-PreviewEdit.cmd`. The launcher passes a
   path ending in `\\.` to avoid a Windows trailing-backslash quoting bug.
   A folder whose name explicitly says v1.2 is rejected rather than being
   incorrectly packaged as v1.3.
4. The script creates a **new** `AutoSync-v1.3-PreviewEdit-Windows-Portable`
   folder and same-named ZIP beside your v1.3 folder.
5. Run the `AutoSync.exe` inside the **new** folder. Open Preview & Edit,
   save a corrected alignment, and listen to the result before exporting.

The helper downloads the Preview & Edit GUI from the existing
`preview-edit-20261030` GitHub release. It will stop if the output folder or ZIP
already exists. The original v1.3 engine files are compared byte-for-byte using
SHA-256 after copying. Engine and Python command-line startup are checked before
the ZIP is produced.

## Limitations

- **This is a merge helper, not a prebuilt v1.3 download.** The user's true v1.3
  engine is needed, because the GitHub repo does not contain the v1.3 source
  archive.
- PowerShell parsing has been checked in Windows CI, but the merge and
  interactive editor have **not** been tested against the user's genuine v1.3
  media and executable. Compatibility is therefore not guaranteed.
- The desktop shell still includes legacy v1.1 version wording. The merged
  Python engine is taken from v1.3 regardless of that label.
- This merges installed portable engines, not source branches. A proper source
  merge still requires importing the actual v1.3 source files into GitHub and
  running full media regression tests.
- Do not run the helper on your only copy of an unfinished job. Original input
  and output files are not altered, but you should still keep the v1.3 backup.

For a fully integrated GitHub source release, the actual v1.3 engine sources must
first be made accessible to the GitHub build environment; no earlier v1.1 code
should be represented as v1.3.
