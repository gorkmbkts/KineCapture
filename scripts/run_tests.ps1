<#
.SYNOPSIS
    Run the test suite inside the existing KineSynth conda environment.

.EXAMPLE
    .\scripts\run_tests.ps1
    .\scripts\run_tests.ps1 -Filter "export"
    .\scripts\run_tests.ps1 -Verbose2
#>
[CmdletBinding()]
param(
    [string] $Filter,
    [switch] $Verbose2,
    [switch] $Quiet
)

. (Join-Path $PSScriptRoot '_common.ps1')

$python = Get-KineSynthPython
Write-EnvBanner -Python $python
Assert-KineCaptureInstalled -Python $python

$arguments = @('-m', 'pytest')
if ($Filter)   { $arguments += @('-k', $Filter) }
if ($Verbose2) { $arguments += '-v' }
if ($Quiet)    { $arguments += '-q' }

# Qt must not try to open a window on a build agent or over a bare SSH session.
$env:QT_QPA_PLATFORM = 'offscreen'

Push-Location (Get-RepoRoot)
try {
    & $python @arguments
    $code = $LASTEXITCODE
    Write-Host ''
    if ($code -eq 0) {
        Write-Host 'Testler gecti.' -ForegroundColor Green
    } else {
        Write-Host "Testler basarisiz (cikis kodu $code)." -ForegroundColor Red
    }
    exit $code
} finally {
    Pop-Location
}
