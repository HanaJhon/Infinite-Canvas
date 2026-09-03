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
$launcherName = ([char]0x4E00) + ([char]0x952E) + ([char]0x542F) + ([char]0x52A8) + '.exe'
Copy-Item (Join-Path $output 'InfiniteCanvasLauncher.exe') (Join-Path $root $launcherName) -Force
Write-Host "Publish complete: $output\InfiniteCanvasLauncher.exe"
Write-Host "Launcher copy: $root\一键启动.exe"
