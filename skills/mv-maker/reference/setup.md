# Machine setup (GATE 0) and the final render machine

## GATE 0 - machine check (first use on a machine, or `SKILL_DIR/machine.json` missing / older than 30 days)
Run `mv doctor` (~10 s: hardware, FFmpeg features, encoders that actually work, Python deps, render benchmark).
It writes `machine.json`; `render` (`--encoder auto`) and `analyze` (`--model auto`) then use the best settings found.
Report to the user in their language, briefly:
- a small table: CPU / RAM / GPU / disk, chosen encoder, Whisper model + device, tier (light / standard / strong) and
  the estimated time for a 4-minute 1080p final;
- what that means for the plan (e.g. tier light → storyboard + proxies here, final on a stronger machine);
- the recommendations grouped **required / recommended / optional**, each with what it improves, size/time cost and
  whether it is automatic (`mv doctor --install <id>`) or a manual system step (driver, FFmpeg, app). Offer `match`
  (semantic footage matching, ~1-4 GB) when the user has a clip library or wants footage found online; it may be
  installed only on the render machine.

**Avoid duplicate installs.** `mv doctor` also prints a *project-scope* reuse check (this skill's folders, the shared
runtime `~/.mv-maker`, the current project, tools on PATH). Tools may already exist elsewhere - another mv-maker copy
(plugin cache, `~/.claude/skills`, `~/.agents/skills`, a project's `.claude/skills`), another skill's venv, conda, a
fuller FFmpeg, system fonts, downloaded Whisper/Demucs models. Looking for those is outside the project, so **ask
first** ("May I do a read-only check of your machine for tools you already have, to avoid installing them twice?
Nothing is changed.") - and if the session runs in a permission mode that prompts for commands, let that prompt
happen. Only with a yes run `mv doctor --scan machine`. Then offer, per suggestion, **reuse** vs **new install**:
- `use-shared` - one runtime `~/.mv-maker/venv` for every mv-maker copy (`mv doctor --use-shared`; afterwards
  `mv doctor --remove-local-venv` frees the old copy's space) - recommended when 2+ copies exist;
- `reuse-python` - point mv-maker at a complete existing env (`mv doctor --use-python <path>`); mv-maker never installs
  into or deletes environments it did not create, and warns that the owner's upgrades could affect it;
- `use-ffmpeg` - use an already installed full FFmpeg for mv-maker only (`mv doctor --use-ffmpeg <path>`);
- cached models / installed fonts are reused automatically (information only).
If the user wants it limited to the project, keep the default local `.venv` and do not scan.

Then **ask which ones to install** (multi-select; required items first). **Never install anything, change drivers or
system packages, or write outside the project/skill folder (e.g. `~/.mv-maker`) without an explicit yes.** Install the
approved automatic items with `mv doctor --install id1,id2`; for approved manual items run the shown system command
(e.g. `winget`, `brew`, `apt`) or guide the user, then re-run `mv doctor` and confirm. If the user declines, continue
with what works (everything has a CPU fallback). Re-run `mv doctor` whenever a render/encode or Whisper step fails with
a hardware/driver error. Free stock keys (`PEXELS_API_KEY`, `PIXABAY_API_KEY`) widen footage search - suggest them here.

## Final render on a stronger machine
Install the skill on the render machine, copy `projects/<slug>` (incl. `audio/`, `sources/`, `analysis.json`,
`lyrics.yaml`, `picks.yaml`, `matches.yaml`), run `mv doctor` there, then `mv render projects/<slug> --mode final`
(encoder auto = fastest working one). Maximum quality when time allows: `--encoder libx264`. Explicit choices:
`h264_nvenc` (NVIDIA), `h264_qsv` (Intel), `h264_amf` (AMD), `h264_videotoolbox` (Mac).
Output: `projects/<slug>/out/<slug>_final_<aspect>.mp4`. Other versions from the platform plan, same edit:
`--format 16:9` (re-check `focus` / captions in the new crop with `mv proof --mode final --format 16:9`) and short cuts
`--cut 0:45-1:30` (→ `<slug>_cut45-90_final_9x16.mp4`). `out/credits.txt` lists attributions for the description.
