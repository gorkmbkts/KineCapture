<#
.SYNOPSIS
    Run the test suite inside the existing KineSynth conda environment.

.DESCRIPTION
    By default every test file runs in its own pytest process, one after the
    other, and a summary table is printed at the end. That is the project's
    rule (knowledge/protocols/test-and-measurement.md), and since the
    23 September 2026 release gate it has a measured reason: in one process,
    windows the GUI tests closed but never deleted pile up - 320 top-level
    windows and 15 343 widgets by the time the sign-in tests start - and every
    application-wide stylesheet change re-polishes all of them. The run slows
    down test by test until a single fixture sits in apply_application_theme
    for more than ten minutes (faulthandler dump in the gate report).

    -SingleProcess keeps the old behaviour for anyone who needs it.

.EXAMPLE
    .\scripts\run_tests.ps1
    .\scripts\run_tests.ps1 -Filter "export"
    .\scripts\run_tests.ps1 -Files tests\test_export.py,tests\test_identity.py
    .\scripts\run_tests.ps1 -SingleProcess -Verbose2
#>
[CmdletBinding()]
param(
    [string] $Filter,
    [string[]] $Files,
    [switch] $Verbose2,
    [switch] $Quiet,
    [switch] $SingleProcess,
    [string] $Report,
    [string] $LogDir
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
    if ($SingleProcess) {
        & $python @arguments
        $code = $LASTEXITCODE
        Write-Host ''
        if ($code -eq 0) {
            Write-Host 'Testler gecti.' -ForegroundColor Green
        } else {
            Write-Host "Testler basarisiz (cikis kodu $code)." -ForegroundColor Red
        }
        exit $code
    }

    if ($Files) {
        # "-File" hands a comma list over as one string; split it either way.
        $targets = $Files | ForEach-Object { $_ -split ',' } | Where-Object { $_ } |
            ForEach-Object { Get-Item $_.Trim() }
    } else {
        $targets = Get-ChildItem -Path 'tests' -Filter 'test_*.py' | Sort-Object Name
    }
    $results = @()
    $started = Get-Date
    $index = 0
    foreach ($file in $targets) {
        $index += 1
        $relative = Join-Path 'tests' $file.Name
        $begin = Get-Date
        # A native command's stderr becomes an error record under 2>&1 in
        # Windows PowerShell, and _common.ps1 makes errors terminating. Qt
        # prints warnings to stderr, so the capture runs with 'Continue'.
        $previous = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $output = & $python @arguments $relative '-rfEs' 2>&1 | ForEach-Object { "$_" }
            $code = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $previous
        }
        $seconds = [math]::Round(((Get-Date) - $begin).TotalSeconds, 1)
        if ($LogDir) {
            New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
            $output | Out-File -FilePath (Join-Path $LogDir ($file.BaseName + '.txt')) -Encoding utf8
        }
        $tail = ($output | Where-Object { $_ -match '(passed|failed|error|skipped|no tests ran|deselected)' } | Select-Object -Last 1)
        # 5 = no tests collected, which is what -k does to a file it does not match.
        $ok = ($code -eq 0) -or ($code -eq 5 -and $Filter)
        $results += [pscustomobject]@{
            File = $file.Name; Code = $code; Seconds = $seconds; Summary = "$tail".Trim(); Ok = $ok
        }
        $mark = if ($ok) { 'OK  ' } else { 'FAIL' }
        $colour = if ($ok) { 'Gray' } else { 'Red' }
        Write-Host ("[{0,3}/{1}] {2} {3,-48} {4,7}s  {5}" -f $index, $targets.Count, $mark, $file.Name, $seconds, "$tail".Trim()) -ForegroundColor $colour
        if (-not $ok) {
            $output | Where-Object { $_ -match '^(FAILED|ERROR)' } | ForEach-Object { Write-Host "        $_" -ForegroundColor Red }
        }
    }
    $total = [math]::Round(((Get-Date) - $started).TotalSeconds)
    $failed = @($results | Where-Object { -not $_.Ok })
    Write-Host ''
    Write-Host ("{0}/{1} dosya yesil, {2} sn." -f ($results.Count - $failed.Count), $results.Count, $total)
    if ($Report) {
        $results | ConvertTo-Json -Depth 3 | Out-File -FilePath $Report -Encoding utf8
    }
    if ($failed.Count -eq 0) {
        Write-Host 'Testler gecti.' -ForegroundColor Green
        exit 0
    }
    Write-Host ("Basarisiz dosyalar: {0}" -f (($failed | ForEach-Object { $_.File }) -join ', ')) -ForegroundColor Red
    exit 1
} finally {
    Pop-Location
}
