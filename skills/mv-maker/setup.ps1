# mv-maker setup (Windows). Installs Python deps + font pack.
#   -Scope local  (default) .venv inside this skill folder - touches nothing outside it
#   -Scope shared one runtime in %USERPROFILE%\.mv-maker\venv shared by every mv-maker copy (plugin, project, Codex)
# Run:  powershell -ExecutionPolicy Bypass -File setup.ps1 [-Scope shared]   (mv.cmd runs it on first use)
param([ValidateSet("local", "shared")] [string]$Scope = "local")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "[mv] FFmpeg not found on PATH. Install it, then re-open the terminal:"
    Write-Host "     winget install --id Gyan.FFmpeg -e"
    exit 1
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
& $vpy -m pip install --upgrade pip -q
& $vpy -m pip install -r requirements.txt -q
if ($Scope -eq "shared") { Set-Content -Path (Join-Path $PSScriptRoot "runtime.txt") -Value $vpy -Encoding ascii -NoNewline }
& $vpy scripts\mv.py fonts
& $vpy scripts\mv.py doctor
Write-Host "`n[mv] ready. Try:  $PSScriptRoot\mv.cmd demo story"
