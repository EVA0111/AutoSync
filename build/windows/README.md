# Build AutoSync Windows portable directly from source

This folder replaces the old patcher/merge workflows. No previously installed
AutoSync is needed, and the original source files are never patched in place.

**Windows 10/11 x64:**
1. Download the repository source ZIP and extract it.
2. Double-click `build/windows/build-portable.cmd`.
3. The builder checks Node.js 22 LTS and Python 3.12. It can install missing
   build tools via Windows Package Manager (winget), or tells you what to install.
4. It installs build-time dependencies, runs **all Python unit tests** and the
   desktop editor tests, downloads FFmpeg and the Python 3.12 embeddable runtime,
   then produces `dist/AutoSync-Source-Windows-Portable.zip`.
5. Extract that ZIP and run `AutoSync.exe`. The finished application bundles
   Electron, Python, NumPy, SciPy, FFmpeg and FFprobe; the recipient doesn't
   need Node/Python.

Run PowerShell directly with:
```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File build/windows/build-portable.ps1 -OutputDirectory "D:\Builds"
```
Each build refuses to overwrite an existing output, so use an empty build
destination or move the previous output first. Internet access is needed for
dependencies. GitHub Actions uses this same script; the tests must pass before
the ZIP artifact is uploaded. Publishing GitHub Releases is manual.

Project organization:
- `AutoSync/*.py`: syncing core, audio/video algorithms and regression tests
- `AutoSync/desktop/`: Electron interface and interactive editor
- `AutoSync/sushi/`: bundled subtitle-related assets
- `build/windows/`: reproducible self-contained Windows build
- `.github/workflows/`: automated CI using the same build script
