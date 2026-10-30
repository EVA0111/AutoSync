# Build a complete portable Windows x64 application from THIS source tree.
# No patcher and no pre-existing AutoSync installation required.
param(
  [string]$OutputDirectory = "",
  [switch]$SkipTests
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-StrictMode -Version Latest
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$source = Join-Path $repo 'AutoSync'
if (-not (Test-Path -LiteralPath (Join-Path $source 'package.json'))) {
  throw 'Run the builder from a complete source checkout.'
}
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $repo 'dist' }
$output = [IO.Path]::GetFullPath($OutputDirectory.Trim('"'))
New-Item -ItemType Directory -Force -Path $output | Out-Null
$bundle = Join-Path $output 'AutoSync-win32-x64'
$zip = Join-Path $output 'AutoSync-Source-Windows-Portable.zip'
if ((Test-Path -LiteralPath $bundle) -or (Test-Path -LiteralPath $zip)) {
  throw "Build output already exists. Choose another -OutputDirectory or move the previous build: $output"
}

function Test-Python312 {
  if (Get-Command python -ErrorAction SilentlyContinue) {
    & python -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3,12) else 1)' 2>$null
    if ($LASTEXITCODE -eq 0) { return @('python') }
  }
  if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.12 -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3,12) else 1)' 2>$null
    if ($LASTEXITCODE -eq 0) { return @('py','-3.12') }
  }
  return @()
}
function Refresh-Path {
  $env:PATH = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' +
    [Environment]::GetEnvironmentVariable('Path','User') + ';' + $env:PATH
}
function Ensure-Dependency([string]$name,[string]$wingetId) {
  if (Get-Command $name -ErrorAction SilentlyContinue) { return }
  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "$name is required to build from source. Install $wingetId or install winget to let this script bootstrap it."
  }
  Write-Host "Installing build tool $name using winget..."
  & winget install --id $wingetId --exact --silent --accept-source-agreements --accept-package-agreements
  if ($LASTEXITCODE -ne 0) { throw "winget failed to install $wingetId" }
  Refresh-Path
  if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
    throw "$name was installed but is not available on PATH yet. Open a fresh terminal and rerun."
  }
}
Ensure-Dependency 'node' 'OpenJS.NodeJS.LTS'
Ensure-Dependency 'npm' 'OpenJS.NodeJS.LTS'
$pythonLauncher = @(Test-Python312)
if (-not $pythonLauncher.Count) {
  Ensure-Dependency 'py' 'Python.Python.3.12'
  Refresh-Path
  $pythonLauncher = @(Test-Python312)
  if (-not $pythonLauncher.Count) { throw 'Python 3.12 is required for the embedded runtime.' }
}
$nodeVersion = ((& node --version).TrimStart('v').Split('.'))[0]
if ([int]$nodeVersion -lt 22) { throw 'Node.js >=22 is required. Update Node.js LTS and rerun.' }
$work = Join-Path $env:TEMP ('autosync-source-build-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $work | Out-Null
$createdBundle = $false
try {
  Write-Host '[1/7] Installing build-only Python dependencies (isolated venv)...'
  if ($pythonLauncher[0] -eq 'py') {
    & py -3.12 -m venv (Join-Path $work 'venv')
  } else {
    & python -m venv (Join-Path $work 'venv')
  }
  if ($LASTEXITCODE -ne 0) { throw 'Cannot create isolated Python build environment.' }
  $py = Join-Path $work 'venv\Scripts\python.exe'
  & $py -m pip install --disable-pip-version-check -r (Join-Path $source 'requirements.txt')
  if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }

  Write-Host '[2/7] Downloading portable FFmpeg and FFprobe...'
  $ffmpegZip = Join-Path $work 'ffmpeg.zip'
  $unpack = Join-Path $work 'ffmpeg'
  Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile $ffmpegZip
  Expand-Archive -LiteralPath $ffmpegZip -DestinationPath $unpack
  $ffmpeg = Get-ChildItem -LiteralPath $unpack -Recurse -File -Filter ffmpeg.exe | Select-Object -First 1
  $ffprobe = Get-ChildItem -LiteralPath $unpack -Recurse -File -Filter ffprobe.exe | Select-Object -First 1
  if (-not $ffmpeg -or -not $ffprobe) { throw 'FFmpeg archive lacks its required executables.' }
  $env:PATH = $ffmpeg.DirectoryName + ';' + $env:PATH

  Write-Host '[3/7] Testing source engine and desktop editor...'
  if (-not $SkipTests) {
    & $py -m unittest discover -s $source -p 'test_*.py' -v
    if ($LASTEXITCODE -ne 0) { throw 'Python regression tests failed; build stopped.' }
  }
  Push-Location $source
  try {
    & npm install --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Electron dependency installation failed.' }
    if (-not $SkipTests) {
      & npm run test:editor
      if ($LASTEXITCODE -ne 0) { throw 'Editor regression tests failed; build stopped.' }
    }
    Write-Host '[4/7] Packaging Electron user interface...'
    & npx --yes '@electron/packager' . AutoSync --platform=win32 --arch=x64 --out=$work --overwrite --asar
    if ($LASTEXITCODE -ne 0) { throw 'Electron packaging failed.' }
  } finally { Pop-Location }
  $packaged = Join-Path $work 'AutoSync-win32-x64'
  if (-not (Test-Path (Join-Path $packaged 'resources\app.asar'))) {
    throw 'Packaged Electron application is incomplete.'
  }
  Move-Item -LiteralPath $packaged -Destination $bundle
  $createdBundle = $true

  Write-Host '[5/7] Embedding Python 3.12, source engine, and numerical libraries...'
  $resources = Join-Path $bundle 'resources'
  $engine = Join-Path $resources 'engine'
  $python = Join-Path $resources 'python'
  New-Item -ItemType Directory -Force -Path $engine,$python | Out-Null
  Copy-Item -Path (Join-Path $source '*.py') -Destination $engine
  Copy-Item -Path (Join-Path $source 'requirements.txt') -Destination $engine
  Copy-Item -Path (Join-Path $source 'jobs_example.csv') -Destination $engine
  Copy-Item -Path (Join-Path $source 'README.md') -Destination $engine
  if (Test-Path (Join-Path $source 'sushi')) {
    Copy-Item -LiteralPath (Join-Path $source 'sushi') -Destination $engine -Recurse
  }
  $embedZip = Join-Path $work 'python-embed.zip'
  Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip' -OutFile $embedZip
  Expand-Archive -LiteralPath $embedZip -DestinationPath $python
  @('python312.zip', '.', 'Lib\site-packages', '..\engine', 'import site') |
    Set-Content -LiteralPath (Join-Path $python 'python312._pth') -Encoding ascii
  $sitePackages = Join-Path $python 'Lib\site-packages'
  New-Item -ItemType Directory -Force -Path $sitePackages | Out-Null
  & $py -m pip install --disable-pip-version-check --no-compile --only-binary=:all: --target $sitePackages -r (Join-Path $source 'requirements.txt')
  if ($LASTEXITCODE -ne 0) { throw 'Portable Python dependency bundling failed.' }
  Copy-Item -LiteralPath $ffmpeg.FullName -Destination (Join-Path $engine 'ffmpeg.exe')
  Copy-Item -LiteralPath $ffprobe.FullName -Destination (Join-Path $engine 'ffprobe.exe')

  Write-Host '[6/7] Checking bundled runtime...'
  & (Join-Path $python 'python.exe') -c 'import numpy, scipy, main_episode, video_edits, output_jobs'
  if ($LASTEXITCODE -ne 0) { throw 'Embedded Python import check failed.' }
  & (Join-Path $python 'python.exe') (Join-Path $engine 'autosync.py') --help | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'Embedded AutoSync CLI failed.' }
  & (Join-Path $engine 'ffmpeg.exe') -hide_banner -version | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'Bundled FFmpeg failed.' }

  Write-Host '[7/7] Creating portable ZIP...'
  Compress-Archive -LiteralPath $bundle -DestinationPath $zip -CompressionLevel Optimal
  if (-not (Test-Path -LiteralPath $zip)) { throw 'Portable ZIP was not created.' }
  $hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
  Write-Host 'Portable app: ' $bundle
  Write-Host 'Portable ZIP: ' $zip
  Write-Host 'SHA-256: ' $hash
  Write-Host 'Done. Extract the ZIP and run AutoSync.exe; no Python/Node installs needed to use it.'
} catch {
  if ($createdBundle -and (Test-Path -LiteralPath $bundle)) {
    Remove-Item -LiteralPath $bundle -Recurse -Force -ErrorAction SilentlyContinue
  }
  if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue }
  throw
} finally {
  Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}
