# mv-maker setup (Windows). Creates .venv inside this skill folder, installs Python deps and the font pack.
# Run:  powershell -ExecutionPolicy Bypass -File setup.ps1     (mv.cmd runs it automatically on first use)
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
if (-not (Test-Path .venv\Scripts\python.exe)) { & ([scriptblock]::Create("$py -m venv .venv")) }
.\.venv\Scripts\python.exe -m pip install --upgrade pip -q
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -q
.\.venv\Scripts\python.exe scripts\mv.py fonts
.\.venv\Scripts\python.exe scripts\mv.py doctor
Write-Host "`n[mv] ready. Try:  $PSScriptRoot\mv.cmd demo story"
