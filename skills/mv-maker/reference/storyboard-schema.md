# storyboard.yaml schema

## Top level
| field | default | meaning |
|---|---|---|
| `title`, `slug`, `concept` | | display / output name / one-paragraph idea (shown in storyboard.md) |
| `preset` | | style preset or lyric-video template from `reference/presets.yaml` (`mv presets`); explicit values win, shots opt out with `preset: false` |
| `theme` | | a colour variant of the preset (`themes:` in presets.yaml), e.g. `theme: sunset` |
| `palette` | preset's | list of colours `$1 $2 $3` used by generated backgrounds (`gen:`); pick from the cover with `mv palette` |
| `genre` | | cutting grammar for the edit check: `ballad` `pop` `kpop` `rap` `edm` `rock` `indie` `rnb` (`mv genres`, genres.md) |
| `cut_lead` | 0 | cut picture this much BEFORE each shot boundary: `1f`, `2f` (frames) or seconds (≤ 0.2). Audio/lyrics unchanged |
| `title_card` | | official-MV title: `{artist, title, sub, start, dur, style: official|center|minimal}` (official = lower-left, letter-spaced artist, "Title") |
| `end_card` | | closing card: `{text, sub, dur, start, style}` (default centred, last `dur` seconds) |
| `visualizer` | | audio spectrum on any video: `{type: bars|wave, color, opacity, area: [x0, y0, x1, y1]}` (poster videos use `poster.visualizer`) |
| `lang` | en | language of the `storyboard.md` labels (`en`, `vi`; others fall back to `en`) - set to the user's language |
| `audio` | | song file, relative to project folder |
| `format` | `9:16` | `9:16` 1080x1920 · `16:9` 1920x1080 · `1:1` · `4:5` |
| `fps` | 30 | final fps (proxy always 24) |
| `font` / `font_file` | Arial | caption font name / .ttf used for placeholder labels |
| `song_start` | 0 | offset into the audio file |
| `fade_out` / `audio_fade_out` | 1.0 / 0 | end fades (s) |
| `sources` | | map id -> `{url, section, path, search, note, rights}` |
| `shots` | | list, contiguous in time |
| `captions` | [] | fine-timed lines `{start, end, text, style, anim}` (song time) |
| `caption_anim` | fade | default caption animation: `fade` · `rise` · `pop` · `none` |
| `lyrics_file` | | `lyrics.yaml` from `mv align` (lines with per-word timing) |
| `lyric_style` | subtitle (scroll for poster) | `subtitle` · `karaoke` · `word` · `typewriter` · `stack` · `neon` · `scroll` · `grunge` · `paper` · `marker` · `stagger` (see lyrics.md) |
| `lyric_lead` | 0.15 | seconds a lyric line appears before it is sung (0.25-0.4 for sing-along lyric videos) |
| `lyric_highlight` | line | scroll only: `line` or `karaoke` (fill current line word by word) |
| `lyric_anim` | = caption_anim | subtitle style animation |
| `lyric_area` | auto | `[x0, y0, x1, y1]` fractions of the frame where lyrics live |
| `font` / `display_font` | Be Vietnam Pro / Anton | lyric font / big kinetic (stack) font. Font spec: `"Family"`, `"Family:800"`, `"Family:900i"`, `"Family:900i@125"` - any Google Font, downloaded on demand (see fonts.md) |
| `typo` | | lettering: `{upper, color, outline_color, outline, shadow, shadow_color, spacing, slant, bold, size}` (see fonts.md); `size` scales every lyric style (1.3 = 30 % bigger); `paper` / `paper_text` colour the paper style, `marker_ink` the marker style's inked words |
| `accent` | #FFD24D | accent colour: karaoke fill, neon glow, stack highlight, progress bar |
| `poster` | | poster player: `{title, artist, title_font, artist_font, progress: true, time: true, visualizer: wave|bars|none, visualizer_color}` |
| `song_reading`, `look` | | review only: interpretation of the song / overall palette + signature + motif |
| `technique_plan` | | review only: list of `{section, time, meaning, recommend, why, options: [..]}` |
| `wow_moments` | | review only: list of strings |

Source file lookup: `path` if given, else `sources/<id>.(mp4|mkv|webm|mov|jpg|png...)`. Missing -> placeholder card.
Source extras: `gen: "<kind>:<colours>"` = generated background, no file needed - `solid`, `gradient`, `blocks`, `smoke`,
`particles`, `paper`, `grunge`, `crt`; colours `#hex`, `$1`-`$3` (palette) or `$a` (accent), e.g. `gen: "smoke:$1,$3"`.
`sync: 1.5` = this clip's time at song second 0 (written by `mv sync` into picks.yaml) for `lipsync` layers.
`search:` site keywords (a list = several phrasings), `look_for:` the picture to rank candidates by, `avoid:`, `orient:`
- used by `mv scout` (reference/matching.md).
`picks.yaml` (written by `mv pick` / `mv ingest`) is merged over `sources:` - it adds `url`, `provider`, `creator`,
`rights`, `page` or a local `path` without touching storyboard.yaml.
Images are allowed as sources (stills; combine with `zoom` for Ken Burns).

## Shot
| field | meaning |
|---|---|
| `id` | S01... (auto if omitted) |
| `start`, `end` | song time, seconds or `m:ss.xx` |
| `section`, `lyric`, `intent` | documentation for review; `section` also picks preset section extras (intro, verse, pre, chorus/hook, drop, bridge, outro) |
| `role` | `performance` · `narrative` · `broll` · `concept` - for the edit check (performance share per section) |
| `look_for` | concrete visual description (string or list of phrasings, English best) for `mv match`; a shot with `look_for` and no layers is matched automatically |
| `avoid` | what must not be in the picture (`"text, logo"`) - lowers matching scores |
| `size` | `ews` `wide` `full` `medium` `mcu` `close` `ecu` `insert` `aerial` `pov` - edit check flags jump cuts / no size variety |
| `layout` | `full` · `split_v` (top/bottom) · `split_h` (left/right) · `split_3v` (3 rows) · `pip` · `fit_blur` (whole source frame centred on its own blurred copy) · `poster` (cover card + blurred cover bg + player UI + lyric panel) |
| `lyric_style` | per-shot override of the lyric style for lines starting inside this shot |
| `ratio` | split position for split_v/split_h (0.5) |
| `feather` | split_v/split_h only: soft seam width as a fraction of frame height/width. **Default 0.2**; `0` = hard cut, 0.3 = very dreamy |
| `beat_fx` | beat-synced punch on the composed frame: `[zoom]`, `[flash]`, `[shake]` (any mix). Needs `analysis.json` |
| `beat_every` | 1 = every beat, 2 = every other, 4 ≈ downbeats only (1) |
| `beat_zoom`, `beat_flash` | pulse strength (0.07 / 0.3) |
| `caption_anim` | per-shot override: `fade` · `rise` · `pop` · `none` |
| `technique`, `alt` | review only: technique IDs from techniques.md / alternative options shown to the user |
| `inset` | pip only: `{w: 0.5, aspect: "16:9", pos: tr|tl|br|bl|c}` |
| `layers` | list (see below). First N un-blended layers fill the layout slots in order. `layers: auto` = the scene `mv match` chose (`matches.yaml`, `use:`) |
| `fx` | effects on the composed frame |
| `transition` | into the NEXT shot (see below) |
| `caption`, `caption_style` | text for the whole shot; style `lyric` (default) · `title` · `credit` |

## Layer
| field | meaning |
|---|---|
| `src` | source id; `auto` = filled by `mv match` (keeps the layer's other settings, e.g. `fx`) |
| `in` | start time inside the original source video |
| `lipsync` | `true` = `in` follows the song (song time + the source's `sync`), so a performance clip stays lip-synced on every cut; a number = explicit offset. Speed must stay 1 |
| `speed` | 0.5 = slow-mo, 2 = fast |
| `focus` | `[x, y]` 0..1 crop anchor when aspect differs (e.g. `[0.5, 0.3]` keep faces) |
| `zoom` | `in` / `out` Ken Burns; `zoom_amount` (0.12) |
| `fx` | per-layer effects |
| `ramp` | speed ramp keyframes `[[shot_time, speed], ...]`, linearly interpolated (replaces `speed`) |
| `freeze` | `[at, hold]` - hold the frame at shot second `at` for `hold` seconds |
| `smooth` | `true` = optical-flow frame interpolation for slow motion / ramps (CPU heavy) |
| `blend` | makes this an overlay over the whole frame: `screen` `overlay` `softlight` `lighten` `darken` `multiply` `addition` `hardlight` `difference` `normal` |
| `opacity` | overlay strength (0.4) |
| `note` | label shown on the placeholder card |

## fx names
`bw` · `vintage` · `oldfilm` · `vhs` · `grain[:n]` · `vignette` · `warm[:x]` · `cool[:x]` · `blur[:sigma]` ·
`bright[:x]` · `contrast[:x]` · `sat[:x]` · `rgbsplit[:px]` · `mirror` · `glow[:opacity]` ·
`grade:<teal-orange|kodak|golden|moody|bleach|noir|pastel|matte|cyberpunk|cold-blue>` · `letterbox[:0.1]` ·
`leak[:0.4]` · `bloom[:0.3]` · `handheld[:1]` · `motionblur` · `sharpen[:0.8]` · `chroma[:4]`
(shot-level `fx` apply to the composed frame; put `grade:` first)

## transition (into next shot)
- `cut` (default)
- `flash[:d]` - next shot starts from white
- `fadeblack[:d]` - dip to black
- `dissolve[:d]` - crossfade
- `flashblack[:d]` - quick dip to black · `glitch[:d]` - RGB split/noise/hue burst across the cut ·
  `whip[:d]` - fast whip slide · `zoom[:d]` - zoom-through
- any FFmpeg xfade name with duration: `circleopen:0.5`, `wipeleft:0.4`, `slideup:0.4`, `radial:0.6`, `pixelize:0.5`,
  `hblur:0.4`, `zoomin:0.5`, `fadewhite:0.5`, `smoothleft:0.5`, `squeezev:0.4` ...

xfade/dissolve shots get an automatic tail so music sync is kept.

## lyrics.yaml line extras
`emph: "word"` - the key word of the line for `stagger` (default: the longest word). `section` - from `[Chorus]`
headers in lyrics.txt; `mv auto` uses it to start new scenes.
