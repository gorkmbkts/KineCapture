<#
.SYNOPSIS
    KineCapture Windows kurucusunu tek komutla üretir.

.DESCRIPTION
    Sıra: yayın ortamı (KineSynth klonu) denetimi -> kinecapture tekerleği ->
    tekerleğe karşı testler -> ortamı budama -> öz-denetim -> conda-pack ->
    sahip tohumu -> kurucu derleme -> içerik manifesti ve taramalar.

    Hiçbir şey indirmez; KineSynth ve base ortamlarına paket kurmaz/kaldırmaz.
    Yayın ortamı yoksa release_env.py prepare ile KineSynth'ten klonlanır.

    Sahip tohumu (dist\owner_seed.json) yoksa derleme durur ve tohumu üretecek
    komutu söyler; tohumsuz kurucu için -NoOwnerSeed verin (ilk açılışta
    "Sistem Sahibi oluştur" ekranı çıkar).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\release\build_installer.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\release\build_installer.ps1 -NoOwnerSeed
#>
[CmdletBinding()]
param(
    [string]$Prefix = 'C:\KCBuild\env',
    [string]$Work = 'C:\KCBuild\work',
    [string]$Wheels = 'C:\KCBuild\wheels',
    [string]$Dist = '',
    [string]$OwnerSeed = '',
    [switch]$NoOwnerSeed,
    [string]$Conda = '',
    [string]$PyzedWheel = '',
    [string]$Models = '',
    [switch]$SkipTests,
    [switch]$Fresh
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Dist) { $Dist = Join-Path $repo 'dist' }
if (-not $OwnerSeed) { $OwnerSeed = Join-Path $Dist 'owner_seed.json' }
if (-not $Conda) {
    $candidates = @($env:CONDA_EXE, (Join-Path $env:USERPROFILE 'anaconda3\Scripts\conda.exe'),
                    (Join-Path $env:USERPROFILE 'miniconda3\Scripts\conda.exe')) | Where-Object { $_ -and (Test-Path $_) }
    if (-not $candidates) { throw 'conda.exe bulunamadı; -Conda ile verin.' }
    $Conda = @($candidates)[0]
}
$condaRoot = Split-Path (Split-Path $Conda)
$condaPack = Join-Path $condaRoot 'Scripts\conda-pack.exe'
if (-not $PyzedWheel) { $PyzedWheel = Join-Path $env:USERPROFILE 'pyzed-5.4-cp311-cp311-win_amd64.whl' }
if (-not $Models) { $Models = Join-Path $env:USERPROFILE '.cache\kinecapture\models' }
$python = Join-Path $Prefix 'python.exe'
$started = Get-Date

function Step([string]$text) { Write-Host ''; Write-Host "==> $text" -ForegroundColor Cyan }
function Native([string]$exe, [string[]]$arguments) {
    # Windows PowerShell 5.1 turns a native program's stderr into errors under
    # 'Stop'; the exit code is what decides here.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $exe @arguments 2>&1 | ForEach-Object { Write-Host "    $_" } }
    finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { throw "$([IO.Path]::GetFileName($exe)) başarısız (çıkış kodu $LASTEXITCODE)." }
}

# 0. The seed decision comes first: a build that would stop at the end
#    should stop before an hour of work.
Step 'Sahip tohumu'
$seedArgs = @()
if (Test-Path $OwnerSeed) {
    Write-Host "    tohum: $OwnerSeed (yalnız özet; içerik yazdırılmaz)"
    $seedArgs = @('--owner-seed', $OwnerSeed)
} elseif ($NoOwnerSeed) {
    Write-Host '    tohumsuz kurucu: ilk açılışta "Sistem Sahibi oluştur" ekranı çıkar.'
} else {
    Write-Host "    Tohum dosyası yok: $OwnerSeed" -ForegroundColor Yellow
    Write-Host '    Kendi terminalinizde çalıştırın (şifre iki kez sorulur, ekrana yazılmaz):' -ForegroundColor Yellow
    Write-Host "      $env:USERPROFILE\anaconda3\envs\KineSynth\python.exe scripts\release\make_owner_seed.py --title `"<unvan>`""
    Write-Host '    Tohumsuz kurucu için: build_installer.ps1 -NoOwnerSeed'
    exit 3
}

Step 'Yayın ortamı (KineSynth klonu)'
if ($Fresh -and (Test-Path (Join-Path $Prefix '.kinecapture-release-env'))) {
    # Only a folder this script made (it carries the marker) is ever removed.
    Write-Host "    -Fresh: $Prefix silinip yeniden klonlanıyor"
    Remove-Item -Recurse -Force $Prefix
}
if (-not (Test-Path (Join-Path $Prefix '.kinecapture-release-env'))) {
    # KineSynth's interpreter only runs the script; the script clones and
    # then changes nothing but the clone.
    $sourcePython = Join-Path $condaRoot 'envs\KineSynth\python.exe'
    Native $sourcePython @('-B', (Join-Path $PSScriptRoot 'release_env.py'), 'prepare',
                           '--prefix', $Prefix, '--conda', $Conda, '--pyzed-wheel', $PyzedWheel, '--wheels', $Wheels)
} else {
    Write-Host "    mevcut: $Prefix"
}

Step 'kinecapture tekerleği'
New-Item -ItemType Directory -Force $Wheels | Out-Null
Get-ChildItem $Wheels -Filter 'kinecapture-*.whl' -ErrorAction SilentlyContinue | Remove-Item -Force
Push-Location $repo
try { Native $python @('-m', 'pip', 'wheel', '.', '--no-deps', '--no-build-isolation', '--no-index', '-w', $Wheels, '--quiet') }
finally { Pop-Location }
$wheel = Get-ChildItem $Wheels -Filter 'kinecapture-*.whl' | Select-Object -First 1
if (-not $wheel) { throw 'tekerlek üretilmedi' }
Native $python @('-m', 'pip', 'install', '--no-deps', '--force-reinstall', '--no-index', '--quiet', $wheel.FullName)
$version = (& $python -B -c 'import kinecapture; print(kinecapture.APP_VERSION)').Trim()
Write-Host "    kinecapture $version ($($wheel.Name))"

if (-not $SkipTests) {
    Step 'Tekerleğe karşı testler (depo kaynağı değil, kurulu paket)'
    & $python -B -c 'import pytest' 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw 'Yayın ortamı zaten budanmış (pytest yok). Testlerle derlemek için -Fresh verin (ortam yeniden klonlanır) ya da -SkipTests.'
    }
    # conftest.py adds nothing to sys.path, and src\ is not on it: from the
    # repository root the clone's interpreter imports the installed wheel.
    Push-Location $repo
    try {
        $where = (& $python -B -c 'import kinecapture, sys; print(kinecapture.__file__)').Trim()
        if ($where -notlike "$Prefix*") { throw "kinecapture tekerlekten değil, buradan yükleniyor: $where" }
        Write-Host "    kinecapture yüklendiği yer: $where"
        Native $python @('-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                         'tests\test_packaging.py', 'tests\test_release_gate_packaging.py', 'tests\test_owner_seed.py',
                         'tests\test_release_gate_export.py', 'tests\test_studio_workload.py',
                         'tests\test_release_installer.py')
    } finally { Pop-Location }
}

Step 'Ortamı budama (yalnız çalışma zamanı kapanışı)'
Native $python @('-B', (Join-Path $PSScriptRoot 'release_env.py'), 'trim', '--prefix', $Prefix, '--conda', $Conda)
Native $python @('-B', (Join-Path $PSScriptRoot 'release_env.py'), 'check', '--prefix', $Prefix,
                 '--baseline-python', (Join-Path $condaRoot 'envs\KineSynth\python.exe'))

Step 'Öz-denetim (budanmış ortam, konsolsuz değil: yalnız derleme doğrulaması)'
$selfCheck = Join-Path $Work 'self-check-build.json'
Native $python @('-B', '-m', 'kinecapture', '--self-check', '--report', $selfCheck, '--expect-zed-sdk', '5.4.1')

Step 'conda-pack'
New-Item -ItemType Directory -Force $Work | Out-Null
$tar = Join-Path $Work 'env.tar'
if (Test-Path $tar) { Remove-Item -Force $tar }
Native $condaPack @('-p', $Prefix, '-o', $tar, '--format', 'tar', '--n-threads', '-1', '--force',
                    '--exclude', '*.pyc', '--exclude', 'conda-meta/history', '--exclude', '.kinecapture-release-env')

Step 'Kurucu: yük, tarama, birleştirme'
New-Item -ItemType Directory -Force $Dist | Out-Null
$installer = Join-Path $Dist "KineCapture-Setup-$version.exe"
$toolArgs = @('-B', (Join-Path $PSScriptRoot 'installer_tools.py'), 'build', '--tar', $tar, '--out', $installer,
              '--work', $Work, '--version', $version, '--models', $Models) + $seedArgs
Native $python $toolArgs

$elapsed = [int]((Get-Date) - $started).TotalMinutes
Step "Bitti ($elapsed dk)"
Get-Item $installer | Select-Object FullName, @{n = 'MB'; e = { [math]::Round($_.Length / 1MB) } } | Format-List
