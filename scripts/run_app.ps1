<#
.SYNOPSIS
    Start KineCapture Studio using the existing KineSynth conda environment.

.DESCRIPTION
    Never creates or modifies a conda environment. If KineSynth is missing the
    script stops with an explanation instead of falling back to another one.

.EXAMPLE
    .\scripts\run_app.ps1
    .\scripts\run_app.ps1 -Backend zed
    .\scripts\run_app.ps1 -Diagnose
#>
[CmdletBinding()]
param(
    [ValidateSet('mock', 'zed')]
    [string] $Backend,

    [ValidateSet('dark', 'light')]
    [string] $Theme,

    [ValidateSet('DEBUG', 'INFO', 'WARNING', 'ERROR')]
    [string] $LogLevel,

    [switch] $Diagnose,
    [switch] $ListDevices,
    [switch] $SelfTest
)

. (Join-Path $PSScriptRoot '_common.ps1')

$python = Get-KineSynthPython
Write-EnvBanner -Python $python
Assert-KineCaptureInstalled -Python $python

$arguments = @('-m', 'kinecapture')
if ($Backend)    { $arguments += @('--backend', $Backend) }
if ($Theme)      { $arguments += @('--theme', $Theme) }
if ($LogLevel)   { $arguments += @('--log-level', $LogLevel) }
if ($Diagnose)   { $arguments += '--diagnose' }
if ($ListDevices){ $arguments += '--list-devices' }
if ($SelfTest)   { $arguments += '--self-test' }

Push-Location (Get-RepoRoot)
try {
    & $python @arguments
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
