# Changelog

## [0.10.0] - 2026-11-26

### Added

- Colour matching across sources (`color_match`, default 0.6 with footage presets; `match: false` per layer) and any
  `.cube` LUT (`lut:<file>[@strength]`).
- `focus: auto`: the 9:16 crop of 16:9 footage follows the subject (faces, else motion), smoothed like a calm operator.
- Footage repair per layer: `stabilize` (vidstab two-pass, cached; deshake fallback), `denoise`, `denoise_hq`,
  `clarity`; optional AI upscale `upscale: true` (Real-ESRGAN, `mv doctor --install upscale`).
- Footage-quality check in `mv review` / `check` / `status`: sources enlarged more than 1.5x for their slot.
- Velocity edit (`velocity: true` / `ramp: beat`), transitions `zoomblur`, `spin`, `burn`, `strobe`.
- `lyric_beat: pulse|glow`: lyrics react to the beat.
- Film finishing fx: `filmgrain`, `halation`, `flare`, `dust`, `weave`, `lens`; presets use some of them.
- Text behind the person: shot `behind: true` (MediaPipe matte, `mv doctor --install segment`).

### Fixed

- Scene scoring (`mv ingest`) and subject tracking read frames forward instead of seeking each sample: seeks snap to
  keyframes, so motion was often measured as zero.
- The shot cache now includes the colour-match settings.

## [0.9.0] - 2026-11-26

### Added

- Token-lean workflow for agents (same checks, far fewer tokens):
  - `mv proof <p> [--only S03,S07]`: one labelled frame per shot in a single sheet instead of many frames.
  - `plan.yaml` + `mv auto <p> --plan plan.yaml`: a short per-section plan (look_for lists, role / size cycles, fx,
    `shot_len`, `chorus@last` overrides, a lip-synced `performance` source) expanded into every shot
    (`reference/plan-template.yaml`).
  - `mv status <p>`: project state and the next step in a few lines.
  - `mv context`: a digest of the genre grammar, presets / templates, techniques for a mood, the platform plan and
    the fields to use, instead of reading every reference file.
- `mv align` reports per-line match and prints only weak lines (`--verbose` for all); `mv analyze` no longer prints the
  Whisper transcript unless `--verbose`; `mv review` prints its warnings.

### Changed

- SKILL.md rewritten from ~19 KB to ~8 KB; machine setup and the final-render machine moved to `reference/setup.md`.

## [0.8.0] - 2026-11-26

### Added

- Platform planning before editing: `reference/platforms.yaml` + `platforms.md` (TikTok, Instagram Reels, Facebook
  Reels / feed, YouTube Shorts, YouTube: format, length, safe zones, hook, loudness), `mv platforms [--for ...]`
  prints the specs or a production plan (versions, master format, which source footage fits, short cut, safe zones).
- Storyboard `platforms:` - lyrics and title cards move inside the strictest safe zone of the format; `mv review` /
  `mv check` add a platform check (missing versions, length limits, hook, lyric area outside the safe zone).
- `mv render --format 16:9` (another aspect version of the same edit) and `--cut m:ss-m:ss` (short versions).
- Optional `loudness:` (loudnorm) for mixes far from the platforms' ~-14 LUFS.
- README quick start (English + Vietnamese): what to install, what to give the agent, the two approval gates,
  example prompts, planning for the platform.

## [0.7.0] - 2026-11-26

### Added

- Footage chosen by meaning with a free local model (Google SigLIP 2 via transformers, `mv doctor --install match`,
  imported lazily): shot / source `look_for` + `avoid` descriptions (`reference/matching.md`).
- `mv scout`: for every source with `search:`, search stock + YouTube, rank candidates by thumbnail, and deep-scan the
  best YouTube videos through their preview storyboards to find the matching moment before downloading; picks keep
  the suggested `section`, so only those seconds are fetched. `refs/scout.md` summary.
- `mv find --describe --rank --deep N --avoid` and `--links` (rank TikTok / Facebook / Instagram / any yt-dlp links).
- `mv match`: choose a scene and in-point from the user's clip library (and downloaded picks) for every shot with
  `layers: auto` / `{src: auto}`; global assignment without reusing scenes; `matches.yaml` (`use:`, `--pick S03:2`),
  `refs/match_all.jpg`; embeddings cached in `build/match/`.
- `mv auto` with a footage preset + `--genre`: a shot skeleton cut to the genre grammar with `layers: auto`.

### Changed

- The edit check's 3-second hook warning allows a 3.2 s opening shot.

## [0.6.0] - 2026-11-26

### Added

- Professional MV grammar per genre (`genre:` ballad, pop, kpop, rap, edm, rock, indie, rnb): `reference/genres.md` +
  `genres.yaml`, shot `role` (performance / narrative / broll / concept) and `size`, and an edit check (`mv check`,
  also in `storyboard.md`) for shot length per section, performance share, jump cuts, size variety, off-beat cuts,
  the 3-second hook and the energy build into the last chorus. `mv genres` lists them.
- Lip-sync: `mv sync <project> <source>` finds a performance clip's offset by matching its sound to the song;
  layers with `lipsync: true` stay in sync on every cut.
- `cut_lead` (cut picture 1-2 frames before the beat), official-style `title_card` and `end_card`.
- Lyric styles `grunge`, `paper`, `marker` and `stagger` (key word via `emph:`), `lyric_lead`, `typo.size`.
- Generated backgrounds (`gen:` sources): solid, gradient, colour blocks, smoke, particles/bokeh, paper, grunge, CRT.
- Eight lyric-video templates (`lv-kinetic`, `lv-grunge`, `lv-cozy`, `lv-paper`, `lv-glow`, `lv-minimal`,
  `lv-cinematic`, `lv-retro`) with colour `themes` and `palette`, and `mv auto` to build a lyric-video storyboard
  from `lyrics.yaml` in one step. Top-level `visualizer:` (audio spectrum / wave) on any video.
- Presets `rock-grunge`, `rnb-night`, `pop-bright`; demos `genre-mv`, `lyric-kinetic`, `lyric-template`.

### Changed

- Preset section extras match canonical section names (a pre-chorus no longer picks up chorus settings).
- `lofi-chill` uses Patrick Hand: Caveat has no Vietnamese glyphs (catalogue corrected).

## [0.5.1] - 2026-11-26

### Added

- Core unit tests for lyric alignment, storyboard validation, source search/download, and FFmpeg graph generation.
- GitHub Actions CI on Windows and Ubuntu for Python compilation, tests, CLI help, and POSIX shell syntax.

### Changed

- Installers can prepare the Python runtime and font pack when FFmpeg is not installed yet; `mv doctor` reports the missing renderer and install command.
- PowerShell setup now fails clearly when the Python environment or dependency installation fails.
- Installer arguments are validated before making changes.

### Fixed

- Documented the toolchain bootstrap path for machines that are not ready to render yet.

