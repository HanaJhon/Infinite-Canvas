$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$project = Join-Path $root 'launcher\InfiniteCanvasLauncher.csproj'
$output = Join-Path $root 'dist'

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    throw 'dotnet SDK was not found. Install the .NET 8 SDK and run this script again.'
}

Write-Host 'Publishing InfiniteCanvasLauncher.exe ...'
dotnet publish $project -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o $output
if ($LASTEXITCODE -ne 0) {
    throw "dotnet publish failed with exit code $LASTEXITCODE."
}

$launcherName = [System.Text.Encoding]::UTF8.GetString([byte[]]@(0xE4, 0xB8, 0x80, 0xE9, 0x94, 0xAE, 0xE5, 0x90, 0xAF, 0xE5, 0x8A, 0xA8, 0x2E, 0x65, 0x78, 0x65))
$srcPath = Join-Path $output 'InfiniteCanvasLauncher.exe'
$destPath = Join-Path $root $launcherName

[System.IO.File]::Copy($srcPath, $destPath, $true)
Write-Host "Publish complete: $srcPath"
Write-Host "Launcher copy: $destPath"
