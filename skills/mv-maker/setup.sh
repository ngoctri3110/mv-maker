#!/usr/bin/env sh
# mv-maker setup (macOS / Linux / Git-Bash). Installs Python deps + font pack.
#   sh setup.sh          .venv inside this skill folder - touches nothing outside it
#   sh setup.sh shared   one runtime in ~/.mv-maker/venv shared by every mv-maker copy (plugin, project, Codex)
set -e
cd "$(dirname "$0")"
SCOPE="${1:-local}"
case "$SCOPE" in
  local|shared) ;;
  *) echo "[mv] usage: setup.sh [local|shared]" >&2; exit 2 ;;
esac
HAS_FFMPEG=1
if ! command -v ffmpeg >/dev/null 2>&1; then
  HAS_FFMPEG=0
  echo "[mv] FFmpeg not found. Setup will continue, but rendering stays unavailable until you install it."
  echo "      brew install ffmpeg  |  sudo apt install ffmpeg"
fi
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; assert sys.version_info >= (3, 10)' 2>/dev/null; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "[mv] Python 3.10+ not found"; exit 1; }
if [ "$SCOPE" = "shared" ]; then VENV="${MV_MAKER_HOME:-$HOME/.mv-maker}/venv"; else VENV=.venv; fi
[ -d "$VENV" ] || { mkdir -p "$(dirname "$VENV")"; "$PY" -m venv "$VENV"; }
if [ -x "$VENV/bin/python" ]; then VPY="$VENV/bin/python"; else VPY="$VENV/Scripts/python.exe"; fi
"$VPY" -m pip install --upgrade pip -q
"$VPY" -m pip install -r requirements.txt -q
[ "$SCOPE" = "shared" ] && printf '%s' "$(cd "$(dirname "$VPY")" && pwd)/$(basename "$VPY")" > runtime.txt
if ! "$VPY" scripts/mv.py fonts; then
  echo "[mv] WARNING: font pack download failed; install later with: mv fonts" >&2
fi
if ! "$VPY" scripts/mv.py doctor --quick; then
  echo "[mv] WARNING: machine check failed; run 'mv doctor' after setup." >&2
fi
if [ "$HAS_FFMPEG" -eq 0 ]; then
  echo "[mv] Python runtime is ready. Install FFmpeg later, then run:  $(pwd)/mv doctor"
fi
echo "[mv] ready. Try:  $(pwd)/mv demo story"
