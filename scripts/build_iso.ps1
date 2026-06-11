<#
.SYNOPSIS
    PRADY OS — one-command bootable-ISO build from Windows (runs in WSL).

.DESCRIPTION
    Launches scripts/build_iso.sh as root inside a WSL Debian distro. The
    heavy work happens on the WSL-native filesystem; only source-in and
    ISO-out cross /mnt/c. Produces dist/pradyos-sovereign.iso.

.EXAMPLE
    .\scripts\build_iso.ps1                # build the ISO
    .\scripts\build_iso.ps1 -Verify       # build, then boot-test it in QEMU
    .\scripts\build_iso.ps1 -VerifyOnly   # boot-test an already-built ISO
#>
[CmdletBinding()]
param(
    [switch]$Verify,
    [switch]$VerifyOnly,
    [string]$Distro = 'Debian'
)
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path $PSScriptRoot -Parent

# Make sure the distro exists. `wsl -l -q` emits UTF-16 with stray NULs; strip
# them, trim, and match the EXACT name (a substring match would let 'Deb' pass
# for 'Debian' and then fail later on `wsl -d Deb`).
$distros = (wsl -l -q) -replace "`0", '' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
if ($distros -notcontains $Distro) {
    throw "WSL distro '$Distro' not found. Installed: $($distros -join ', '). Install it:  wsl --install -d $Distro"
}

# Translate the repo path for WSL.
$wslRoot = (wsl -d $Distro -u root -- wslpath -a "$($RepoRoot -replace '\\', '/')").Trim()
if (-not $wslRoot) { throw "wslpath failed for $RepoRoot" }

if (-not $VerifyOnly) {
    Write-Host ">> Building PradyOS Sovereign ISO inside WSL ($Distro)..." -ForegroundColor Cyan
    wsl -d $Distro -u root -- bash "$wslRoot/scripts/build_iso.sh"
    if ($LASTEXITCODE -ne 0) { throw "ISO build failed (exit $LASTEXITCODE)" }
    Write-Host ">> ISO ready: $RepoRoot\dist\pradyos-sovereign.iso" -ForegroundColor Green
}

if ($Verify -or $VerifyOnly) {
    Write-Host ">> Boot-verifying the ISO in QEMU (headless integration test)..." -ForegroundColor Cyan
    wsl -d $Distro -u root -- bash "$wslRoot/scripts/verify_boot.sh"
    if ($LASTEXITCODE -ne 0) { throw "Boot verification FAILED (exit $LASTEXITCODE)" }
    Write-Host ">> Boot verification PASSED" -ForegroundColor Green
}
