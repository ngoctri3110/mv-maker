# Changelog

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

