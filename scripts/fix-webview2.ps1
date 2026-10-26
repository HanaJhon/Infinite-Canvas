# Fix WebView2 Runtime (launcher error 0x800736B1 / "side-by-side configuration is incorrect")
#
# Symptom: double-clicking the launcher shows
#   "launcher UI init failed: The application has failed to start because its
#    side-by-side configuration is incorrect (0x800736B1)"
# Windows Event Log (Application / SideBySide) shows:
#   "Activation context generation failed for msedgewebview2.exe.
#    Could not find dependent assembly <version>"
#
# Root cause: the WebView2 runtime version folder is missing its own-name subfolder
# (that subfolder IS the side-by-side assembly the manifest depends on).
# Usually an interrupted Edge/WebView2 background update: old files deleted, new ones not laid down.
#
# IMPORTANT: `winget install --force` alone does NOT help -- the same version is still registered,
# so the installer only updates the registry and does not re-copy files.
# You MUST move the broken version folder away first.
#
# Run as Administrator (this script touches C:\Program Files (x86)).
# Easiest: double-click 修复WebView2.bat in the project root -- it self-elevates.

$ErrorActionPreference = 'Stop'

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host 'ERROR: Administrator privileges required.' -ForegroundColor Red
    Write-Host 'Please double-click 修复WebView2.bat in the project root (it self-elevates).' -ForegroundColor Yellow
    exit 1
}

$app = 'C:\Program Files (x86)\Microsoft\EdgeWebView\Application'
Write-Host "== WebView2 folder: $app" -ForegroundColor Cyan

if (-not (Test-Path $app)) {
    Write-Host "ERROR: folder not found. WebView2 runtime is not installed at all." -ForegroundColor Red
    exit 1
}

# Step 0: kill whatever is holding the WebView2 folder open.
# Otherwise Rename/Remove fails with "Access denied".
# NOTE: we also kill any process that has EdgeWebView modules loaded (e.g. GameViewer,
# game boosters, remote-control tools) - they keep the folder locked even when no
# msedgewebview2.exe is visible.
Write-Host 'Killing processes that hold WebView2...' -ForegroundColor Cyan
foreach ($n in @('msedgewebview2', 'Lochou启动器')) {
    Get-Process -Name $n -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            $_.Kill()
            Write-Host ("  killed {0} (PID {1})" -f $n, $_.Id)
        } catch {
            Write-Host ("  cannot kill {0} (PID {1}): {2}" -f $n, $_.Id, $_.Exception.Message) -ForegroundColor Yellow
        }
    }
}
# Anything with EdgeWebView loaded (GameViewer etc.)
Get-Process -ErrorAction SilentlyContinue | Where-Object {
    try { $_.Modules.FileName -like '*EdgeWebView*' } catch { $false }
} | ForEach-Object {
    try {
        $_.Kill()
        Write-Host ("  killed {0} (PID {1}) - had EdgeWebView loaded" -f $_.ProcessName, $_.Id)
    } catch {
        Write-Host ("  cannot kill {0} (PID {1}): {2}" -f $_.ProcessName, $_.Id, $_.Exception.Message) -ForegroundColor Yellow
    }
}
Start-Sleep -Seconds 3

# Step 1: move away every version folder that lacks its own-name subfolder
$broken = @()
Get-ChildItem $app -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^\d+\.\d+\.\d+\.\d+$' } |
    ForEach-Object {
        $sub = Join-Path $_.FullName $_.Name
        if (-not (Test-Path $sub)) { $broken += $_ }
    }

if ($broken.Count -eq 0) {
    Write-Host 'No version folder is missing its subfolder. This may not be the cause.' -ForegroundColor Yellow
} else {
    foreach ($d in $broken) {
        $stamp = Get-Date -Format 'yyyyMMddHHmmss'
        $bak = "$($d.FullName).broken-$stamp"
        $moved = $false
        try {
            Rename-Item $d.FullName $bak -ErrorAction Stop
            Write-Host "Moved broken folder: $($d.Name) -> $(Split-Path $bak -Leaf)" -ForegroundColor Green
            $moved = $true
        } catch {
            Write-Host "Rename failed for $($d.Name): $($_.Exception.Message)" -ForegroundColor Yellow
        }
        if (-not $moved) {
            # Fall back to deleting it outright. The folder is already broken (missing its
            # SideBySide subfolder), so deleting loses nothing.
            try {
                Remove-Item $d.FullName -Recurse -Force -ErrorAction Stop
                Write-Host "Deleted broken folder: $($d.Name)" -ForegroundColor Green
            } catch {
                Write-Host "Cannot delete $($d.Name) either: $($_.Exception.Message)" -ForegroundColor Red
                Write-Host 'Please close GameViewer / other tools that use WebView2, or reboot and run this again.' -ForegroundColor Yellow
            }
        }
    }
}

# Step 2: force a real reinstall.
# winget install --force alone does NOT copy files when the same version is still registered
# in the registry (it only refreshes the registry entry), so we must:
#   a) delete the WebView2 registry key  -> installer no longer thinks it is installed
#   b) run the installer                -> it copies ALL files from scratch
Write-Host ''
Write-Host 'Removing WebView2 registry entries...' -ForegroundColor Cyan
$clientGuid = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
$regKeys = @(
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$clientGuid",
    "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$clientGuid"
)
foreach ($k in $regKeys) {
    if (Test-Path $k) {
        try {
            Remove-Item $k -Recurse -Force -ErrorAction Stop
            Write-Host "  removed $k" -ForegroundColor Green
        } catch {
            Write-Host "  cannot remove $k : $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}

Write-Host 'Uninstalling WebView2 Runtime (best effort)...' -ForegroundColor Cyan
winget uninstall --id Microsoft.EdgeWebView2Runtime --silent --accept-source-agreements 2>&1 | ForEach-Object { "  $_" }
Start-Sleep -Seconds 3

Write-Host 'Installing WebView2 Runtime (~200 MB, needs internet)...' -ForegroundColor Cyan
winget install --id Microsoft.EdgeWebView2Runtime --force --accept-source-agreements --accept-package-agreements 2>&1 | ForEach-Object { "  $_" }

# Step 3: verify
# NOTE: WebView2 does NOT use a self-named subfolder. The SideBySide assembly it needs is
# described by a sibling file `<version>.manifest` (which points at `msedge_elf.dll`).
# So the correct check is: exe + <version>.manifest + msedge_elf.dll, all in the same folder.
Write-Host ''
Write-Host '== Verify ==' -ForegroundColor Cyan
$ok = $false
Get-ChildItem $app -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^\d+\.\d+\.\d+\.\d+$' } |
    ForEach-Object {
        $exe = Join-Path $_.FullName 'msedgewebview2.exe'
        $mf = Join-Path $_.FullName "$($_.Name).manifest"
        $elf = Join-Path $_.FullName 'msedge_elf.dll'
        $hasExe = Test-Path $exe
        $hasMf = Test-Path $mf
        $hasElf = Test-Path $elf
        if ($hasExe -and $hasMf -and $hasElf) { $ok = $true }
        Write-Host ("  {0}  exe={1}  manifest={2}  msedge_elf={3}" -f $_.Name, $hasExe, $hasMf, $hasElf)
    }

Write-Host ''
if ($ok) {
    Write-Host 'OK: WebView2 is fixed. You can start Lochou启动器.exe now.' -ForegroundColor Green
} else {
    Write-Host 'FAILED: still broken.' -ForegroundColor Red
    Write-Host 'Manual option: download the Evergreen Standalone Installer from'
    Write-Host 'https://developer.microsoft.com/microsoft-edge/webview2/'
    exit 1
}

Write-Host ''
if ($ok) {
    Write-Host 'SUCCESS: WebView2 is repaired. You can start Lochou启动器.exe now.' -ForegroundColor Green
} else {
    Write-Host 'FAILED: still broken.' -ForegroundColor Red
    Write-Host 'Manual option: download the Evergreen Bootstrapper from' -ForegroundColor Yellow
    Write-Host 'https://developer.microsoft.com/microsoft-edge/webview2/' -ForegroundColor Yellow
    exit 1
}
