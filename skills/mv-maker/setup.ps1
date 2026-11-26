# mv-maker setup (Windows). Installs Python deps + font pack.
#   -Scope local  (default) .venv inside this skill folder - touches nothing outside it
#   -Scope shared one runtime in %USERPROFILE%\.mv-maker\venv shared by every mv-maker copy (plugin, project, Codex)
# Run:  powershell -ExecutionPolicy Bypass -File setup.ps1 [-Scope shared]   (mv.cmd runs it on first use)
param([ValidateSet("local", "shared")] [string]$Scope = "local")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$hasFfmpeg = [bool](Get-Command ffmpeg -ErrorAction SilentlyContinue)
if (-not $hasFfmpeg) {
    Write-Warning "FFmpeg not found on PATH. Setup will continue, but rendering stays unavailable until you install it."
    Write-Host "     winget install --id Gyan.FFmpeg -e"
}
$py = $null
foreach ($c in @("py -3", "python")) {
    try { & ([scriptblock]::Create("$c -c `"import sys; assert sys.version_info >= (3, 10)`"")) 2>$null; if ($LASTEXITCODE -eq 0) { $py = $c; break } } catch {}
}
if (-not $py) { Write-Host "[mv] Python 3.10+ not found. Install from https://www.python.org/ or: winget install Python.Python.3.12"; exit 1 }
$sharedHome = if ($env:MV_MAKER_HOME) { $env:MV_MAKER_HOME } else { Join-Path $HOME ".mv-maker" }
$venv = if ($Scope -eq "shared") { Join-Path $sharedHome "venv" } else { Join-Path $PSScriptRoot ".venv" }
$vpy = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $vpy)) { & ([scriptblock]::Create("$py -m venv `"$venv`"")) }
if (-not (Test-Path $vpy)) { throw "Could not create Python environment at $venv" }
& $vpy -m pip install --upgrade pip -q
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed in $venv" }
& $vpy -m pip install -r requirements.txt -q
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed in $venv" }
if ($Scope -eq "shared") { Set-Content -Path (Join-Path $PSScriptRoot "runtime.txt") -Value $vpy -Encoding ascii -NoNewline }
try {
    & $vpy scripts\mv.py fonts
    if ($LASTEXITCODE -ne 0) { Write-Warning "Font pack download failed; fonts can be installed later with: mv fonts" }
} catch {
    Write-Warning "Font pack download failed; fonts can be installed later with: mv fonts"
}
try {
    & $vpy scripts\mv.py doctor --quick
    if ($LASTEXITCODE -ne 0) { Write-Warning "Machine check failed; run 'mv doctor' after setup." }
} catch {
    Write-Warning "Machine check failed; run 'mv doctor' after setup."
}
if (-not $hasFfmpeg) {
    Write-Host "[mv] Python runtime is ready. Install FFmpeg later, then run:  $PSScriptRoot\mv.cmd doctor"
}
Write-Host "`n[mv] ready. Try:  $PSScriptRoot\mv.cmd demo story"
