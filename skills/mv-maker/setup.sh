#!/usr/bin/env sh
# mv-maker setup (macOS / Linux / Git-Bash). Creates .venv inside this skill folder, installs deps and fonts.
set -e
cd "$(dirname "$0")"
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[mv] FFmpeg not found. Install it first:  brew install ffmpeg  |  sudo apt install ffmpeg"
  exit 1
fi
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; assert sys.version_info >= (3, 10)' 2>/dev/null; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "[mv] Python 3.10+ not found"; exit 1; }
[ -d .venv ] || "$PY" -m venv .venv
if [ -x .venv/bin/python ]; then VPY=.venv/bin/python; else VPY=.venv/Scripts/python.exe; fi
"$VPY" -m pip install --upgrade pip -q
"$VPY" -m pip install -r requirements.txt -q
"$VPY" scripts/mv.py fonts
echo "[mv] hardware encoders available:"
ffmpeg -hide_banner -encoders 2>/dev/null | grep -E "nvenc|qsv|amf|videotoolbox" || true
echo "[mv] ready. Try:  $(pwd)/mv demo story"
