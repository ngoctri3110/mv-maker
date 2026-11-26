---
name: mv-maker
description: Turn a song (audio + lyrics + the user's scene ideas, or just a cover/poster image) into a music video or lyric video for TikTok/Reels/Shorts/YouTube - beat/lyric analysis, lyric timing, technique proposals from the song's meaning, storyboard for approval, sourcing clips from YouTube/TikTok, and FFmpeg rendering with soft split-screens, overlays, film looks, beat-synced effects, animated lyric styles (karaoke, kinetic stack, neon, scrolling) and poster-player lyric videos. Use when the user wants a music video, lyric video, fan edit, a lyric video from a poster/cover image, or to cut clips to a song - in any language.
---

# MV Maker

Storyboard-driven pipeline. **`storyboard.yaml` is the contract**: the human approves it, the renderer
executes it deterministically. Never download footage or render a final before the storyboard is approved.

**Tool.** `SKILL_DIR` = the folder containing this SKILL.md (in Claude Code: `${CLAUDE_SKILL_DIR}`).
Run `SKILL_DIR/mv <cmd>` on macOS/Linux/Git-Bash or `SKILL_DIR\mv.cmd <cmd>` on Windows - below, `mv` means that.
The first run installs everything into `SKILL_DIR/.venv` (Python deps + font pack); it needs
FFmpeg on PATH and Python 3.10+. If setup fails, tell the user the exact missing prerequisite.
Projects live in the user's working directory: `projects/<slug>/` (audio, sources, storyboard, outputs).
New user / "does it work?" → `mv demo story` (also `blur`, `lyric-poster`, `lyric-styles`, `all`) renders a demo
with synthetic media in `projects/demo-*`.

References (read when needed):
- `reference/storyboard-schema.md` - every field, layout, fx, transition the renderer supports
- `reference/techniques.md` - **technique catalogue with IDs** (composition, rhythm, transitions, looks, lyrics,
  storytelling devices), mood → quick picks, platform specs. Read it before proposing techniques.
- `reference/lyrics.md` - **lyric styles catalogue** (subtitle, karaoke, word, typewriter, stack, neon, scroll),
  MV-with-lyrics vs lyric video vs **poster player** (one cover image -> lyric video), fonts, readability rules
- `reference/fonts.md` - **fonts & lettering**: any Google Font by spec (`"Kanit:900i"`), catalogue by look and
  language, matching lyric lettering to a poster (recipe + mappings), `typo` (case, colour, outline, shadow, slant)
- `reference/storyboard-template.yaml` - worked example of every layout

**Language.** These instructions are in English, but talk to the user in *their* language and write everything they
read in it: chat summaries, `storyboard.yaml` text fields (`intent`, `note`, `song_reading`, `technique_plan`, `alt`,
captions) and therefore `storyboard.md` (also set `lang:` so its headings match). Lyrics stay exactly as sung. Pick fonts that cover the lyric language.

## Workflow (machine check + 8 steps, approval gates)

### 0. Machine check -> GATE 0 (first use on a machine, or when `SKILL_DIR/machine.json` is missing / > 30 days old)
Run `mv doctor` (~10 s: hardware, FFmpeg features, encoders that actually work, Python deps, render benchmark).
It writes `machine.json`; `render` (`--encoder auto`) and `analyze` (`--model auto`) then use the best settings found.
Report to the user in their language, briefly:
- a small table: CPU / RAM / GPU / disk, chosen encoder, Whisper model + device, tier (light / standard / strong)
  and the estimated time for a 4-minute 1080p final;
- what that means for the plan (e.g. tier light → storyboard + proxies here, final on a stronger machine);
- the recommendations grouped **required / recommended / optional**, each with what it improves, size/time cost and
  whether it is automatic (`mv doctor --install <id>`) or a manual system step (driver, FFmpeg, app).
Then **ask which ones to install** (multi-select; required items first). **Never install anything, change drivers or
system packages without an explicit yes.** Install the approved automatic items with `mv doctor --install id1,id2`;
for approved manual items run the shown system command (e.g. `winget`, `brew`, `apt`) or guide the user, then re-run
`mv doctor` and confirm. If the user declines, continue with what works (everything has a CPU fallback).
Re-run `mv doctor` whenever a render/encode or Whisper step fails with a hardware/driver error.

### 1. Intake
`mv new projects/<slug>` then collect into `brief.md`: audio file (put in `audio/`), full lyrics, the user's
scene ideas per section, platform/aspect (9:16 vs 16:9), full song or a 60s cut. Ask only for what is missing.

Decide the **video type** early, it changes everything (details in `reference/lyrics.md`):
A. music MV with lyrics (footage-led) · B. lyric video (text-led) · C. poster player (one cover image + lyric panel).
If the user only has a poster/cover image, propose C (and B as an upgrade if they want footage).

### 2. Analyze the song + time the lyrics
`mv analyze projects/<slug> --lyrics` -> `analysis.json`: tempo, beat times, downbeats, energy sections,
and Whisper word timestamps (`--model auto` picks from `machine.json`: `large-v3` on CUDA, else `medium`/`small`;
`--language` = the song's language code, default `vi`). Whisper on sung
vocals is approximate: align the user's real lyrics to those timestamps, don't trust Whisper's text.
If timing is poor, isolate vocals first (`demucs --two-stems vocals audio/song.mp3`) and pass `--audio` the vocal stem.
Put the user's lyrics in `lyrics.txt` (one sung line per line, repeats written out), then `mv align projects/<slug>`
-> `lyrics.yaml` with per-word timing. Report the match % and spot-check a few lines against the audio.
Setup installs a small default font pack; any other Google Font is fetched on demand by spec (`font: "Kanit:900i"`),
including Japanese, Korean, Chinese, Thai, Arabic and Devanagari families - see `reference/fonts.md`.

### 3. Read the song & propose techniques -> part of GATE 1
Before choosing shots, interpret the song and turn meaning into edit ideas. The user should come away with
ideas they would not have thought of - not just their own description played back.
1. **Song reading** (`song_reading:`): theme, who sings to whom, the emotional arc section by section
   (intro → verse → pre → chorus → bridge → outro), key images/metaphors in the lyrics, the 1-2 lines that matter most.
2. **Look** (`look:`): one overall palette + one signature technique + one visual motif (S-MOTIF) that ties the MV together.
3. **Per-section proposals** (`technique_plan:`): for every section give `meaning`, a ⭐ `recommend` combo of technique IDs
   from `reference/techniques.md`, `why` (one line linking it to the lyric/emotion - e.g. "the line 'back in those days'
   → top half blurred and warm because it is a memory"), and 1-2 `options` that feel different (softer vs. punchier).
4. **Lyric treatment**: pick `lyric_style` per section from `reference/lyrics.md` (calm verse vs loud chorus).
   **Lettering**: if there is a poster/cover/artwork, open it and match its title lettering (`reference/fonts.md`
   recipe): shortlist 4-7 Google Fonts that cover the lyric language, `mv palette` for colours, render
   `mv fonts preview` with the real lyric line, show the image with your pick and let the user choose; then set
   `font` / `display_font` / `poster.title_font` / `typo` / `accent`. Without artwork, pick fonts from the song's mood.
   Offer one alternative style for the chorus. For poster videos also choose 9:16 vs 16:9 and visualizer on/off.
5. **Wow moments** (`wow_moments:`): 2-3 signature edits worth the effort (the hook in the first 3 seconds for TikTok,
   the drop into the first chorus, the most important lyric line).
6. Respect the user's own ideas first; propose techniques that make them land harder, and add alternatives around them.
   House style: splits use soft seams (feather 0.2) unless hard contrast is the point.
7. Each shot gets `technique: [IDs]` and, where a real choice exists, `alt: ["option 2: ..."]`.

### 4. Storyboard -> GATE 1
Write `storyboard.yaml`:
- One shot per lyric line or musical phrase; cut points **on beats/downbeats** from `analysis.json`
  (snap to the nearest beat). Shots must be contiguous.
- Map each moment to a technique using `reference/techniques.md` (nostalgia -> split singer/fans + warm grain + dissolve,
  chorus/drop -> faster cuts + flash, bridge -> bw/slow-mo, memory -> screen-blend overlay ...).
- Every footage need becomes a `sources:` entry with `note` + `search` (what to find). No URLs yet is fine.
Then `mv review projects/<slug>` -> `storyboard.md`, and `mv render projects/<slug> --mode proxy` -> an
**animatic** (missing footage shows as labelled cards, real audio + captions + transitions).
Show the user `storyboard.md` + the animatic path, and summarise in chat: the song reading in 2-3 lines,
the ⭐ recommendation per section, the wow moments, and how to pick alternatives (e.g. `S03 -> option 2`).
**Stop and wait for approval / changes.**

### 5. Source footage -> GATE 2
For each source: `mv search "<query>" -n 10`, pick candidates, put `url` (+ `section: "m:ss-m:ss"` to
download only the needed part) and `rights` into the storyboard. Show the source list to the user
(rights matter - see below) and wait for OK. Then `mv fetch projects/<slug>`.
TikTok/Facebook/Instagram links work with yt-dlp too (search only works for YouTube - ask the user for links).

### 6. Pick exact moments
`mv sheet projects/<slug> <source_id> --every 2` makes `refs/sheet_<id>.jpg` with timecodes - **open the image and look**
to choose `in:` points (e.g. the exact frame the door opens, the singer's close-up). `mv scenes ... <id>` lists hard cuts
inside a source so a shot doesn't straddle an unwanted cut. Set `focus: [x, y]` to keep the subject in a 9:16 crop of 16:9 footage.

### 7. Proxy edit loop
`mv render projects/<slug> --mode proxy` (540x960, fast, shots cached - only changed shots re-render).
Check by extracting frames (`ffmpeg -ss <t> -i out/... -frames:v 1 x.jpg`) and looking at them; iterate with the user.

### 8. Final render (strong machine)
Install the skill on the render machine, copy `projects/<slug>` (incl. `audio/`, `sources/`, `analysis.json`,
`lyrics.yaml`), then `mv doctor` on that machine, then `mv render projects/<slug> --mode final` (encoder auto = fastest working one).
For maximum quality when time allows: `--encoder libx264`. Explicit choices: `h264_nvenc` (NVIDIA), `h264_qsv` (Intel),
`h264_amf` (AMD), `h264_videotoolbox` (Mac).
Output: `projects/<slug>/out/<slug>_final_<aspect>.mp4`. For a 16:9 YouTube version, copy the storyboard, set
`format: "16:9"`, re-check `focus`/captions, render again.

## Rules
- Times in storyboard = song time. `in:` = time in the ORIGINAL source video (even when only a `section` was downloaded).
- Don't invent effects the renderer lacks; extend `scripts/mv.py` (fx_filters / slots_for) and document it in the schema.
- Rights: footage from other people's YouTube/TikTok and commercial songs are copyrighted. Platforms Content-ID
  match both; expect claims, muting, blocks, no monetization. Record `rights:` per source; prefer the artist's own
  material with permission, licensed/stock (Pexels, Pixabay, Mixkit), Creative Commons, or the user's own footage.
  Tell the user plainly before publishing; never present downloaded clips as cleared.
