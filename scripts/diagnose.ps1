<#
.SYNOPSIS
    Check the environment, packages, ZED SDK, pyzed and camera availability.

.DESCRIPTION
    Runs three layers of checks:
      1. the KineSynth interpreter itself,
      2. the application's own diagnostics report,
      3. a live comparison of this build's ZED skeleton tables against the
         installed SDK, so a future SDK upgrade that reorders joints is caught
         instead of silently producing mislabelled data.

.EXAMPLE
    .\scripts\diagnose.ps1
    .\scripts\diagnose.ps1 -Backend zed
#>
[CmdletBinding()]
param(
    [ValidateSet('mock', 'zed')]
    [string] $Backend = 'zed'
)

. (Join-Path $PSScriptRoot '_common.ps1')

$python = Get-KineSynthPython
Write-Host '=== 1. Python ortami ===' -ForegroundColor Cyan
Write-EnvBanner -Python $python

Write-Host '=== 2. Kurulu paketler ===' -ForegroundColor Cyan
& $python -m pip list --format=columns | Select-String -Pattern '^(PySide6|numpy|PyYAML|opencv-python|pytest|pyzed)\s' | ForEach-Object { "  $_" }
Write-Host ''

& $python -c "import kinecapture" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "UYARI: 'kinecapture' kurulu degil; asagidaki adimlar atlaniyor." -ForegroundColor Yellow
    Write-Host "Kurmak icin: & '$python' -m pip install -e "".[dev]"""
    exit 1
}

Push-Location (Get-RepoRoot)
try {
    Write-Host '=== 3. Uygulama tanilamasi ===' -ForegroundColor Cyan
    & $python -m kinecapture --diagnose --backend $Backend
    $diagnoseCode = $LASTEXITCODE
    Write-Host ''

    Write-Host '=== 4. ZED cihaz listesi ===' -ForegroundColor Cyan
    & $python -m kinecapture --list-devices
    Write-Host ''

    Write-Host '=== 5. ZED iskelet tablosu dogrulamasi ===' -ForegroundColor Cyan
    & $python -m kinecapture.tools.verify_zed_topology
    $topologyCode = $LASTEXITCODE

    if ($diagnoseCode -ne 0) { exit $diagnoseCode }
    exit $topologyCode
} finally {
    Pop-Location
}
