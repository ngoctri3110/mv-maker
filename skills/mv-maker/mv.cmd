@echo off
rem mv-maker launcher (Windows). Python: %MV_PYTHON% > runtime.txt > .venv > %USERPROFILE%\.mv-maker\venv > first-run setup.
setlocal
set "D=%~dp0"
set "PY="
if defined MV_PYTHON set "PY=%MV_PYTHON%"
if not defined PY if exist "%D%runtime.txt" set /p PY=<"%D%runtime.txt"
if defined PY if not exist "%PY%" (
  echo [mv] runtime "%PY%" not found - falling back
  set "PY="
)
if not defined PY if exist "%D%.venv\Scripts\python.exe" set "PY=%D%.venv\Scripts\python.exe"
if not defined PY if exist "%USERPROFILE%\.mv-maker\venv\Scripts\python.exe" set "PY=%USERPROFILE%\.mv-maker\venv\Scripts\python.exe"
if not defined PY (
  echo [mv] first run - installing dependencies into this skill folder ^(see: mv doctor --use-shared to share one runtime^)...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%D%setup.ps1" || exit /b 1
  set "PY=%D%.venv\Scripts\python.exe"
)
"%PY%" "%D%scripts\mv.py" %*
