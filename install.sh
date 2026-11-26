#!/usr/bin/env sh
# Install MV Maker as a user-level skill for Claude Code (~/.claude/skills) and Codex (~/.agents/skills).
# Uses symlinks pointing at this clone, so `git pull` updates the skill everywhere.
#   sh install.sh            # both tools
#   sh install.sh claude     # or: codex
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
SRC="$ROOT/skills/mv-maker"
ONLY="${1:-all}"
case "$ONLY" in
  all|claude|codex) ;;
  *) echo "[mv] usage: install.sh [all|claude|codex]" >&2; exit 2 ;;
esac
link() {
  mkdir -p "$(dirname "$1")"
  if [ -L "$1" ]; then rm "$1"; elif [ -e "$1" ]; then echo "[mv] $1 exists and is not a link - skipped"; return; fi
  ln -s "$SRC" "$1" && echo "[mv] linked $1 -> $SRC"
}
[ "$ONLY" = "all" ] || [ "$ONLY" = "claude" ] && link "$HOME/.claude/skills/mv-maker"
[ "$ONLY" = "all" ] || [ "$ONLY" = "codex" ] && link "$HOME/.agents/skills/mv-maker"
chmod +x "$SRC/mv" "$SRC/setup.sh" 2>/dev/null || true
sh "$SRC/setup.sh"
echo "[mv] Done. Restart Claude Code / Codex, or run: $SRC/mv demo story"
