# Shared helpers for the KineCapture scripts.
#
# Policy (PROMPT section 2): this project runs ONLY in the pre-existing
# 'KineSynth' conda environment. These scripts never create an environment and
# never fall back to another one - if KineSynth is missing they stop with an
# explanation, because silently using 'base' would install packages into the
# wrong place and produce results that do not match what the app really runs on.

$ErrorActionPreference = 'Stop'

$script:EnvName = 'KineSynth'

function Get-KineSynthPython {
    <#
    .SYNOPSIS
    Resolve the KineSynth interpreter, or stop with an actionable message.
    #>

    $candidates = @()

    # 1) Ask conda where its environments live.
    $condaCmd = Get-Command conda -ErrorAction SilentlyContinue
    if ($null -ne $condaCmd) {
        try {
            $listing = & conda env list
            foreach ($line in $listing) {
                if ($line -match '^\s*#') { continue }
                $parts = ($line -split '\s+') | Where-Object { $_ -ne '' }
                if ($parts.Count -ge 2 -and $parts[0] -ieq $script:EnvName) {
                    $candidates += (Join-Path $parts[-1] 'python.exe')
                }
            }
        } catch {
            Write-Verbose "conda env list basarisiz: $_"
        }
    }

    # 2) The conventional Anaconda location.
    $candidates += (Join-Path $env:USERPROFILE "anaconda3\envs\$($script:EnvName)\python.exe")
    $candidates += (Join-Path $env:USERPROFILE "miniconda3\envs\$($script:EnvName)\python.exe")

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return (Resolve-Path $candidate).Path
        }
    }

    Write-Host ''
    Write-Host "HATA: '$($script:EnvName)' conda environment'i bulunamadi." -ForegroundColor Red
    Write-Host ''
    Write-Host 'Bu proje YALNIZCA mevcut KineSynth environment ile calisir.'
    Write-Host 'Betikler baska bir environment kullanmaz ve yeni environment olusturmaz.'
    Write-Host ''
    Write-Host 'Kontrol edin:'
    Write-Host '  conda env list'
    Write-Host ''
    Write-Host 'Aranan konumlar:'
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        Write-Host "  $candidate"
    }
    Write-Host ''
    throw "KineSynth environment bulunamadi."
}

function Assert-KineCaptureInstalled {
    param([Parameter(Mandatory = $true)][string] $Python)

    & $Python -c "import kinecapture" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host ''
        Write-Host "UYARI: 'kinecapture' paketi $($script:EnvName) icinde kurulu degil." -ForegroundColor Yellow
        Write-Host 'Kurmak icin:'
        Write-Host "  & '$Python' -m pip install -e "".[dev]"""
        Write-Host ''
        throw "kinecapture paketi kurulu degil."
    }
}

function Write-EnvBanner {
    param([Parameter(Mandatory = $true)][string] $Python)

    $version = & $Python -c "import sys; print(sys.version.split()[0])"
    $executable = & $Python -c "import sys; print(sys.executable)"
    Write-Host "Environment : $($script:EnvName)" -ForegroundColor Cyan
    Write-Host "Python      : $version" -ForegroundColor Cyan
    Write-Host "Interpreter : $executable" -ForegroundColor Cyan
    Write-Host ''
}

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}
