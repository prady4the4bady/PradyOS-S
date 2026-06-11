<#
.SYNOPSIS
    PRADY OS — run the built ISO in a VM from Windows (QEMU inside WSL).

.DESCRIPTION
    Console-mode QEMU on this terminal; the Sovereign Web dashboard is
    reachable from Windows at http://localhost:<Port>/ (WSL2 forwards
    localhost automatically). Ctrl-A X quits the VM.

.EXAMPLE
    .\scripts\run_vm.ps1
    .\scripts\run_vm.ps1 -Port 8080 -Mem 8192
    .\scripts\run_vm.ps1 -Gui          # graphical window via WSLg
#>
[CmdletBinding()]
param(
    [int]$Port = 8000,
    [int]$Mem = 4096,
    [int]$Smp = 4,
    [switch]$Gui,
    [string]$Distro = 'Debian'
)
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path $PSScriptRoot -Parent
$wslRoot = (wsl -d $Distro -u root -- wslpath -a "$($RepoRoot -replace '\\', '/')").Trim()
if (-not $wslRoot) { throw "wslpath failed for $RepoRoot" }

Write-Host ">> PradyOS VM — dashboard will be at http://localhost:$Port/  (Ctrl-A X quits)" -ForegroundColor Cyan
# Pass env + script path as discrete argv entries (not a bash -c string), so a
# repo path containing a quote or space can't break the command's quoting.
$wslArgs = @(
    '-d', $Distro, '-u', 'root', '--',
    'env', "PRADYOS_VM_PORT=$Port", "PRADYOS_VM_MEM=$Mem", "PRADYOS_VM_SMP=$Smp",
    'bash', "$wslRoot/scripts/run_vm.sh"
)
if ($Gui) { $wslArgs += '--gui' }
& wsl @wslArgs
exit $LASTEXITCODE
