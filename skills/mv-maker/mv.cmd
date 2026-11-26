@echo off
rem mv-maker launcher (Windows). First run sets up .venv + fonts next to this file.
setlocal
set "D=%~dp0"
if not exist "%D%.venv\Scripts\python.exe" (
  echo [mv] first run - installing dependencies...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%D%setup.ps1" || exit /b 1
)
"%D%.venv\Scripts\python.exe" "%D%scripts\mv.py" %*
