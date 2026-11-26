# Changelog

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

