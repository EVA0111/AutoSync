# Merge the user's genuine installed AutoSync v1.3 engine into the
# separate Preview & Edit desktop shell. Never replace the user's installation.
# Run with Make-AutoSync-v1.3-PreviewEdit.cmd from the v1.3 portable directory.
param(
  [string]$V13Directory = $PSScriptRoot,
  [string]$Destination = ""
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Assert-File([string]$Path, [string]$Message) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw $Message }
}

$source = (Resolve-Path -LiteralPath $V13Directory).Path.TrimEnd('\')
$engine = Join-Path $source 'resources\engine'
$python = Join-Path $source 'resources\python'
Assert-File (Join-Path $source 'AutoSync.exe') 'Run this inside your already installed AutoSync v1.3 portable folder.'
Assert-File (Join-Path $engine 'autosync.py') 'The original AutoSync engine was not found under resources\engine.'
Assert-File (Join-Path $engine 'desktop_bridge.py') 'The original engine bridge was not found.'
Assert-File (Join-Path $python 'python.exe') 'The embedded Python runtime was not found.'

if (-not $Destination) {
  $Destination = Join-Path (Split-Path $source -Parent) 'AutoSync-v1.3-PreviewEdit-Windows-Portable'
}
$destinationPath = [IO.Path]::GetFullPath($Destination).TrimEnd('\')
if ($destinationPath.Equals($source, [StringComparison]::OrdinalIgnoreCase)) {
  throw 'The destination must not be the original v1.3 folder.'
}
if (Test-Path -LiteralPath $destinationPath) {
  throw "Destination already exists; for safety this script will not overwrite it: $destinationPath"
}
$zipOutput = $destinationPath + '.zip'
if (Test-Path -LiteralPath $zipOutput) {
  throw "Output ZIP already exists. Remove or rename it first: $zipOutput"
}

$releaseUrl = 'https://github.com/EVA0111/AutoSync/releases/download/preview-edit-20261030/AutoSync-PreviewEdit-Windows-Portable.zip'
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('autosync-v13-merge-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary -Force | Out-Null
$previewArchive = Join-Path $temporary 'preview.zip'
$expanded = Join-Path $temporary 'expanded'
$createdOutput = $false
try {
  Write-Host '[1/6] Downloading the Preview & Edit GUI ...'
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  Invoke-WebRequest -Uri $releaseUrl -OutFile $previewArchive -UseBasicParsing
  Expand-Archive -LiteralPath $previewArchive -DestinationPath $expanded -Force

  $preview = Get-ChildItem -LiteralPath $expanded -Filter AutoSync.exe -Recurse -File |
    Where-Object { (Test-Path -LiteralPath (Join-Path $_.DirectoryName 'resources\app.asar')) } |
    Select-Object -First 1
  if (-not $preview) { throw 'Preview archive does not contain a complete Electron application.' }

  Write-Host '[2/6] Copying the Preview & Edit desktop shell ...'
  Copy-Item -LiteralPath $preview.DirectoryName -Destination $destinationPath -Recurse -Force
  $createdOutput = $true
  $destinationResources = Join-Path $destinationPath 'resources'
  $destinationEngine = Join-Path $destinationResources 'engine'
  $destinationPython = Join-Path $destinationResources 'python'
  Assert-File (Join-Path $destinationResources 'app.asar') 'The new Preview & Edit shell is missing.'

  # Preserve FFmpeg packaged with the preview in case the genuine v1.3
  # installation relies on an external FFmpeg instead of bundled executables.
  $ffmpegFallback = @{}
  foreach ($file in @('ffmpeg.exe','ffprobe.exe')) {
    $found = Join-Path $destinationEngine $file
    if (Test-Path -LiteralPath $found) { $ffmpegFallback[$file] = $found }
  }

  Write-Host '[3/6] Preserving the complete v1.3 engine and Python runtime ...'
  if (Test-Path -LiteralPath $destinationEngine) {
    Remove-Item -LiteralPath $destinationEngine -Recurse -Force
  }
  if (Test-Path -LiteralPath $destinationPython) {
    Remove-Item -LiteralPath $destinationPython -Recurse -Force
  }
  New-Item -ItemType Directory -Path $destinationEngine, $destinationPython -Force | Out-Null
  foreach ($file in Get-ChildItem -LiteralPath $engine -Force) {
    Copy-Item -LiteralPath $file.FullName -Destination $destinationEngine -Recurse -Force
  }
  foreach ($file in Get-ChildItem -LiteralPath $python -Force) {
    Copy-Item -LiteralPath $file.FullName -Destination $destinationPython -Recurse -Force
  }
  foreach ($file in @('ffmpeg.exe','ffprobe.exe')) {
    $dest = Join-Path $destinationEngine $file
    if (-not (Test-Path -LiteralPath $dest) -and $ffmpegFallback.ContainsKey($file)) {
      $backup = Join-Path $preview.DirectoryName ('resources\engine\' + $file)
      Copy-Item -LiteralPath $backup -Destination $dest -Force
    }
  }

  # Include v1.3-specific runtime resources without replacing the Preview GUI.
  $originalResources = Join-Path $source 'resources'
  foreach ($item in Get-ChildItem -LiteralPath $originalResources -Force) {
    if ($item.Name -in @('engine','python','app.asar','app.asar.unpacked')) { continue }
    $dest = Join-Path $destinationResources $item.Name
    Copy-Item -LiteralPath $item.FullName -Destination $dest -Recurse -Force
  }

  Write-Host '[4/6] Verifying v1.3 engine preservation ...'
  foreach ($name in @('autosync.py','desktop_bridge.py')) {
    $before = (Get-FileHash -LiteralPath (Join-Path $engine $name) -Algorithm SHA256).Hash
    $after = (Get-FileHash -LiteralPath (Join-Path $destinationEngine $name) -Algorithm SHA256).Hash
    if ($before -ne $after) { throw "The v1.3 engine file $name changed during the merge." }
  }
  $embeddedPython = Join-Path $destinationPython 'python.exe'
  & $embeddedPython -c 'import numpy,scipy;print("v1.3 Python imports OK")'
  if ($LASTEXITCODE -ne 0) { throw 'The copied Python runtime failed its dependency check.' }
  & $embeddedPython (Join-Path $destinationEngine 'autosync.py') '--help' | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'The v1.3 engine did not start successfully.' }
  foreach ($name in @('ffmpeg.exe','ffprobe.exe')) {
    Assert-File (Join-Path $destinationEngine $name) "Missing $name for the Preview & Edit window."
  }

  @'
AutoSync v1.3 + Preview & Edit (locally combined)
================================================
The complete original v1.3 resources/engine and resources/python folders
were copied from your installed v1.3 package. Critical engine files
were verified byte-for-byte against the originals.

The Electron Preview & Edit GUI is derived from the 2026-10-30 preview
release, which was originally built against the public v1.1 source tree.
Some legacy window labels may still mention v1.1. That does not indicate
the copied Python engine was downgraded.

IMPORTANT:
- This combination has NOT been fully regression-tested end-to-end.
- Open a NEW case 1 plan to benefit from the updated opening logic.
- Verify all joins by listening in the editor before relying on exports.
- Your original v1.3 directory was not changed.
'@ | Set-Content -LiteralPath (Join-Path $destinationPath 'VERSION-AND-TESTING.txt') -Encoding UTF8

  Write-Host '[5/6] Packing the merged portable application ...'
  Compress-Archive -LiteralPath $destinationPath -DestinationPath $zipOutput -CompressionLevel Optimal
  Write-Host '[6/6] Finished.'
  Write-Host "Folder: $destinationPath"
  Write-Host "ZIP: $zipOutput"
  Write-Host 'The original v1.3 engine was preserved. Audio/editor integration still requires your real-media verification.'
}
catch {
  Write-Host ('FAILED: ' + $_.Exception.Message) -ForegroundColor Red
  Write-Host 'The original v1.3 installation is unchanged.' -ForegroundColor Yellow
  throw
}
finally {
  if (Test-Path -LiteralPath $temporary) {
    Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue
  }
}
