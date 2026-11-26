---
name: mv-maker
description: Turn a song (audio + lyrics + the user's scene ideas, or just a cover/poster image) into a music video or lyric video for TikTok/Reels/Shorts/YouTube - beat/lyric analysis, lyric timing, technique proposals from the song's meaning, storyboard for approval, sourcing clips from YouTube/TikTok, and FFmpeg rendering with soft split-screens, overlays, film looks, beat-synced effects, animated lyric styles (karaoke, kinetic stack, neon, scrolling) and poster-player lyric videos. Use when the user wants a music video, lyric video, fan edit, a lyric video from a poster/cover image, or to cut clips to a song - in any language.
---

# MV Maker

Storyboard-driven pipeline. **`storyboard.yaml` is the contract**: the human approves it, the renderer executes it.
Never download footage or render a final before the storyboard is approved.

**Tool.** `SKILL_DIR` = the folder of this SKILL.md (in Claude Code: `${CLAUDE_SKILL_DIR}`). Run `SKILL_DIR/mv <cmd>`
(macOS/Linux/Git-Bash) or `SKILL_DIR\mv.cmd <cmd>` (Windows) - below, `mv`. First run installs Python deps + fonts into
`SKILL_DIR/.venv` (Python 3.10+; FFmpeg required for analysis/rendering - `mv doctor` reports it). Projects:
`projects/<slug>/`. "Does it work?" → `mv demo story` (or `all`: synthetic media only).

**Work lean** (same quality, far fewer tokens):
- Start or resume with `mv status <project>` (state + NEXT step) instead of re-reading project files.
- Plan with `mv context --project <p> --type mv|lyric|poster [--genre g] [--platforms ...] [--mood ...]` - a digest of
  the genre grammar, presets, techniques for the mood, platform plan and fields. Open a full reference only for a
  specific question, and only the section you need.
- Footage MV: write a short `plan.yaml` per section (`reference/plan-template.yaml`) and `mv auto <p> --plan plan.yaml`
  - not one storyboard entry per shot by hand. Edit single shots afterwards.
- Look at edits with `mv proof <p>` (one labelled sheet, every shot) and `--only S03,S07` after fixes - not frame by frame.
- Command output is terse; add `--verbose` only when you need every line. `mv review` prints the warnings - no need to
  re-open storyboard.md yourself (it is for the user).

**References** (open when needed): `storyboard-schema.md` (every field) · `genres.md` (pro MV cutting per genre) ·
`techniques.md` (technique IDs, mood picks) · `lyrics.md` (lyric styles, lyric-video templates, poster player) ·
`fonts.md` (any Google Font, matching a poster's lettering) · `matching.md` (`look_for`, `mv scout`, `mv match`) ·
`platforms.md` (platform specs + pre-production plan) · `setup.md` (machine check, final-render machine) ·
`plan-template.yaml` · `storyboard-template.yaml`.

**Language.** Talk to the user in *their* language and write everything they read in it: chat, `storyboard.yaml` text
fields (`intent`, `note`, `song_reading`, `technique_plan`, `alt`, captions) and so `storyboard.md` (set `lang:`).
Lyrics stay exactly as sung; pick fonts that cover the lyric language. `look_for` / `search` stay in English.

## Workflow (approval gates)
**0. Machine check → GATE 0** (first use on a machine): `mv doctor`, report briefly, ask before installing anything -
details and the duplicate-install check in `reference/setup.md`.

**1. Intake.** `mv new projects/<slug>`; collect only what is missing: audio (`audio/`), lyrics, scene ideas, full song
or a short cut. **Platforms first, before any footage** (`mv platforms --for <list>`, `platforms.md`): versions (one per
aspect ratio + a short cut where a platform caps length), master `format:`, which source footage fits, safe zones, hook
- set `platforms:` / `format:`. **Video type**: A footage MV · B lyric video · C poster player (only a cover → C).
For A settle the **genre** (`genres.md`) and what footage exists (performance shot to playback, story, b-roll).
For B without footage: `mv auto <p> --template lv-<look>` (`lyrics.md`).

**2. Analyze + time lyrics.** `mv analyze <p> --lyrics` (beats, sections, Whisper words; `--language` = song language).
Released song: `mv lyrics fetch <p> --artist .. --title ..` (LRCLIB). Else `lyrics.txt` (one sung line per line, repeats
written out) → `mv align <p>`; it reports the match % and the weak lines to spot-check. Poor timing → demucs vocal stem.

**3. Read the song & propose → part of GATE 1.** The user should get ideas they would not have had:
1. `song_reading`: theme, who sings to whom, emotional arc per section, key images, the 1-2 lines that matter most.
2. `look`: one palette + one signature technique + one visual motif (S-MOTIF).
3. `technique_plan` per section: `meaning`, ⭐ `recommend` (technique IDs), `why` (tie it to the lyric/emotion),
   1-2 different `options`. Base it on a fitting `preset`; respect the user's own ideas first, make them land harder.
   Shots carry `technique: [IDs]` and, where a real choice exists, `alt: ["option 2: ..."]`.
4. Lyric treatment: `lyric_style` per section; with artwork, match its lettering (`fonts.md`: shortlist, `mv palette`,
   `mv fonts preview`, let the user pick).
5. `wow_moments`: 2-3 signature edits (hook in the first seconds, drop into the first chorus, the key line).
6. Type A pro grammar (`genres.md`): role mix per section, `role` + `size` per shot, size change on every cut from one
   source, genre shot lengths, last chorus fastest, `cut_lead: 1f`, `title_card` / `end_card`.

**4. Storyboard → GATE 1.** Write it (A: `plan.yaml` → `mv auto --plan`; cuts on beats, shots contiguous). Footage
needs become `sources:` with `note` + `search` (site keywords) + `look_for` (the concrete picture); shots to fill from
the user's clips get `layers: auto` + `look_for` (`matching.md`). `mv review <p>` (edit + platform checks - fix real
problems) and `mv render <p> --mode proxy` (animatic: missing footage = labelled cards). Show `storyboard.md` + the
animatic, summarise the reading, ⭐ per section, wow moments, how to choose alternatives. **Stop and wait for approval.**

**5. Footage → GATE 2** (safest rights first; ranking needs `mv doctor --install match`):
1. User's clips: `mv ingest <p> <folder>` → `mv match <p>` fills `layers: auto` shots → **look at**
   `refs/match_all.jpg`, swap with `--pick S07:2`.
2. Stock / CC and online: `mv scout <p>` (every source with `search:`; ranks by `look_for`, finds the moment inside
   YouTube videos so only that section is downloaded) or `mv find ... --rank --deep 5`; **look at** `refs/cand_*.jpg`,
   `mv pick <p> <source> <slot>:<n>`. TikTok/Facebook/Instagram: rank links the user pasted (`--links`).
Show the chosen list with licences and **wait for OK**, then `mv fetch <p>`. Performance clips: `mv sync <p> <id>` →
layers `{src: <id>, lipsync: true}`. Exact in-points by hand: `mv sheet <p> <id>`; `focus: [x, y]` for crops.

**6. Proxy loop.** `mv render <p> --mode proxy` (cached per shot) → `mv proof <p>` → fix → `mv proof <p> --only ...`.
Make it look like one film: footage presets match colour across sources (`color_match`); fix weak clips per layer -
`focus: auto` (16:9 → 9:16 follows the subject), `fx: [stabilize, denoise]`, `upscale: true`; review's **Footage
quality** lists over-enlarged sources. Finishing, transitions, velocity, `lyric_beat`, `behind`: `techniques.md`.

**7. Final + delivery** (`setup.md`): `mv deliver <p>` renders every platform version and the short cut (first chorus,
cut points on bar lines with audio fades; `short_cut:` or `--cut` to choose), SRT captions, thumbnails (open
`refs/thumb_candidates.jpg`; redo with `mv thumbnail <p> --at m:ss`), credits + a description draft (write the text in
the user's language), and runs `mv qa` on every file (black / frozen frames, A/V sync, loudness, limits) →
`out/deliver.md`. Fix every QA warning before handing over.

## Rules
- Times in storyboard = song time. `in:` = time in the ORIGINAL source video (even when only a `section` was downloaded).
- Don't invent effects the renderer lacks; extend `scripts/mv.py` and document it in the schema.
- Testing / demos use synthetic media (`mv demo`); never download real footage just to try a feature.
- Rights: other people's footage and commercial songs are copyrighted; platforms fingerprint both (claims, muting,
  blocks, no monetisation). Record `rights:` per source; prefer the user's own, licensed/stock or CC material. Tell the
  user plainly before publishing; never present downloaded clips as cleared.
