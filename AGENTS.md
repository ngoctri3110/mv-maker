# AGENTS.md

This repository is **MV Maker**, an agent skill that turns a song into a music video or lyric video.

## Using it (any agent: Codex, Claude Code, others)
- The skill lives in `skills/mv-maker/`. When the user asks for a music video, lyric video, fan edit,
  "video lyric", or to cut clips to a song, **read `skills/mv-maker/SKILL.md` and follow its workflow**
  (it has two approval gates - do not skip them).
- Run the tool with `skills/mv-maker/mv <cmd>` (macOS/Linux/Git-Bash) or `skills\mv-maker\mv.cmd <cmd>` (Windows).
  The first run installs Python deps into `skills/mv-maker/.venv`. Needs FFmpeg + Python 3.10+.
- User projects go in `projects/<slug>/` (git-ignored).
- Smoke test: `skills/mv-maker/mv demo story`.

## Developing it
- Renderer: `skills/mv-maker/scripts/mv.py` (CLI, FFmpeg graph builder) and `scripts/lyrics.py` (ASS lyric styles,
  poster geometry, lyric alignment). Standard library + PyYAML at import time; heavy deps (librosa, faster-whisper,
  scenedetect) are imported lazily inside their commands.
- Every new storyboard field must be documented in `skills/mv-maker/reference/storyboard-schema.md`; new techniques
  in `reference/techniques.md`, lyric styles in `reference/lyrics.md`.
- Before committing, render all demos: `mv demo all --force`, then look at frames of the outputs
  (`ffmpeg -ss <t> -i <out.mp4> -frames:v 1 frame.jpg`) - rendering without errors is not enough.
- Keep the skill agent-neutral: no tool-specific instructions in SKILL.md except the `${CLAUDE_SKILL_DIR}` hint.
