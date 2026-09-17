$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$project = Join-Path $root 'launcher\InfiniteCanvasLauncher.csproj'
$output = Join-Path $root 'dist'
$launcherWebSrc = 'E:\claude\skill\canvas-launcher\dist'

# Locate the dotnet CLI: prefer PATH, fall back to well-known install locations.
$dotnetExe = (Get-Command dotnet -ErrorAction SilentlyContinue).Source
if (-not $dotnetExe) {
    $dotnetCandidates = @(
        'C:\Program Files\dotnet\dotnet.exe',
        'C:\Program Files (x86)\dotnet\dotnet.exe',
        (Join-Path $env:LOCALAPPDATA 'Microsoft\dotnet\dotnet.exe')
    ) | Where-Object { $_ -and (Test-Path $_) }
    $dotnetExe = $dotnetCandidates | Select-Object -First 1
}
if (-not $dotnetExe) {
    throw 'dotnet SDK was not found. Install the .NET 8 SDK and run this script again.'
}
Write-Host "Using dotnet: $dotnetExe"

# Sync web assets to all target locations
if (Test-Path $launcherWebSrc) {
    Write-Host "Syncing launcher web assets from $launcherWebSrc ..."
    $targetDistLauncher = Join-Path $root 'dist\launcher'
    $targetLauncherDist = Join-Path $root 'launcher\dist'

    if (-not (Test-Path $targetDistLauncher)) { New-Item -ItemType Directory -Path $targetDistLauncher -Force | Out-Null }
    if (-not (Test-Path $targetLauncherDist)) { New-Item -ItemType Directory -Path $targetLauncherDist -Force | Out-Null }

    Copy-Item -Path "$launcherWebSrc\*" -Destination $targetDistLauncher -Recurse -Force
    Copy-Item -Path "$launcherWebSrc\*" -Destination $targetLauncherDist -Recurse -Force
    Copy-Item -Path "$launcherWebSrc\*" -Destination $output -Recurse -Force
}

Write-Host 'Publishing InfiniteCanvasLauncher.exe ...'
$publishArgs = @(
    $project,
    '-c', 'Release',
    '-r', 'win-x64',
    '--self-contained', 'true',
    '-p:PublishSingleFile=true',
    '-p:IncludeNativeLibrariesForSelfExtract=true',
    '-o', $output
)

& $dotnetExe publish @publishArgs
if ($LASTEXITCODE -ne 0) {
    # Some .NET SDK builds fail restore with:
    #   NuGet.targets(...): error : Value cannot be null. (Parameter 'path1')
    # The existing obj/project.assets.json is still valid in that case, so retry without restore.
    Write-Warning "dotnet publish failed with exit code $LASTEXITCODE; retrying with --no-restore ..."
    & $dotnetExe publish @publishArgs --no-restore
}

if ($LASTEXITCODE -ne 0) {
    throw "dotnet publish failed with exit code $LASTEXITCODE."
}

# Output launcher name = "Lochou" + U+542F U+52A8 U+5668 + ".exe"  (kept as UTF-8 bytes to stay ASCII-safe in this script)
$launcherName = [System.Text.Encoding]::UTF8.GetString([byte[]]@(0x4C, 0x6F, 0x63, 0x68, 0x6F, 0x75, 0xE5, 0x90, 0xAF, 0xE5, 0x8A, 0xA8, 0xE5, 0x99, 0xA8, 0x2E, 0x65, 0x78, 0x65))
$srcPath = Join-Path $output 'InfiniteCanvasLauncher.exe'
$destPath = Join-Path $root $launcherName

[System.IO.File]::Copy($srcPath, $destPath, $true)
Write-Host "Publish complete: $srcPath"
Write-Host "Launcher copy: $destPath"
