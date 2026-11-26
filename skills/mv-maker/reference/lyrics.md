# Lyrics guide - styles, lyric videos, poster players

Lyrics are a design element, not an afterthought. Pick the style from the song's energy and the video type,
then keep it consistent per section. Propose 2 options to the user (see SKILL.md step 3) with a one-line reason.

## Pipeline
1. `lyrics.txt` - one SUNG line per text line, in singing order, repeats written out (no "Chorus x2").
   `[Chorus]` headers mark sections. `original line | translated line` adds a translation sub-line.
2. `mv analyze <p> --lyrics` - Whisper word timestamps (approximate on sung vocals; use a demucs vocal stem if poor).
3. `mv align <p>` - maps YOUR lyric text onto Whisper timing -> `lyrics.yaml` (per-word `[word, start, end]`).
   Reports the % of words matched; < 50 % means wrong order/repeats or noisy transcription.
   No Whisper? `mv align <p> --start 0:12 --end 3:40` spreads lines evenly - then fix times by hand.
4. Storyboard: `lyrics_file: lyrics.yaml`, `lyric_style:` (global) and optional per-shot `lyric_style:`.
5. Check timing in the proxy: a line should appear ~0.15 s BEFORE the first sung syllable (built in).
6. `mv fonts` once per machine - downloads the Vietnamese-ready font pack.

## Lyric style catalogue
| ID / `lyric_style` | Look | Best for | Notes |
|---|---|---|---|
| `subtitle` | Clean line, fade (or `lyric_anim: rise/pop`) | Story MV, ballad verses, cinematic edits | Least distracting; supports bilingual `sub` line |
| `karaoke` | Line visible, words fill with the accent colour as sung | Sing-along, fan edits, chorus, TikTok trends | Needs good word timing; accent = brand colour of the MV |
| `word` | Words appear one by one as sung | Rap, spoken parts, emotional slow lines | Strong pull on attention - use for 1-2 sections |
| `typewriter` | Characters type in | Letters / confessions / text-message mood, intros, storytelling | Feels personal; pair with blur/bw background |
| `stack` | BIG uppercase words stacked centre, popping in, longest row in accent | Hook, drop, chorus, viral edits, text-led videos | Display font (Anton). 2-5 words per line work best |
| `neon` | Glow outline in accent colour, flicker-in | Night city, EDM, retro 80s, love songs at night | Needs dark background (`fx: [bright:-0.3]`) |
| `scroll` | Apple-Music style list: current line bright, neighbours dim, scrolls up | Lyric videos, poster players, "full lyric" uploads | `lyric_highlight: karaoke` fills the current line word by word |

Mix rules: one style per section; verse calm (`subtitle`/`typewriter`) → chorus loud (`karaoke`/`stack`);
never more than 3 styles in one MV. Captions (`caption:`) remain for titles/credits/notes.

## Video types
### A. Music MV with lyrics (footage-led)
- Lyrics support the image: `subtitle` or `karaoke`, bottom area (above TikTok/Reels UI), small and steady.
- Chorus/hook can switch to `stack` for 1 line to create a "screenshot moment".
- Hide lyrics during strong visual moments (instrumental, dance break) - just leave those lines out of lyrics.txt.

### B. Lyric video (text-led)
- Text is the hero: `stack`, `word`, `neon`, `typewriter`; background = slow footage, blur, gradient or loop.
- Keep backgrounds low-contrast: `fx: [blur:10, bright:-0.25]`, or `fit_blur`.
- One accent colour taken from the cover/poster.

### C. Poster player (cover + lyric panel) - one poster image → lyric video
`layout: poster` turns one image (or video) into a music-player style video:
blurred cover fills the background, sharp cover card with shadow, title + artist, audio visualizer,
progress bar with elapsed/total time, and a scrolling lyric panel.
- 9:16: card on top, lyrics below. 16:9: card left, lyrics right (YouTube).
- Default `lyric_style` for poster videos is `scroll` with `lyric_highlight: karaoke`.
- `accent:` = a colour picked from the poster (look at the image; e.g. its brightest highlight).
- Card can be a video loop or a slowly zooming poster (`zoom: in, zoom_amount: 0.04`).
```yaml
format: "9:16"            # or "16:9" for YouTube
accent: "#FFB86B"
lyrics_file: lyrics.yaml
lyric_style: scroll
lyric_highlight: karaoke   # or line
poster: {title: "Song title", artist: "Artist", progress: true, time: true, visualizer: wave, visualizer_color: "#FFFFFF"}
sources:
  poster: {path: sources/poster.jpg}
shots:
  - {id: P01, start: 0, end: 3:45, layout: poster, layers: [{src: poster, zoom: in, zoom_amount: 0.04}]}
```
Variants: split the song into several poster shots (e.g. swap to a second artwork at the chorus with
`transition: dissolve:1`), `visualizer: bars` or `none`, add `blend: screen` light-leak layers over the whole frame.

## Typography
Full guide, catalogue and poster matching: **`reference/fonts.md`**. Defaults (installed by setup):
| Font | Character | Use |
|---|---|---|
| Be Vietnam Pro | Modern, very readable, Latin + Vietnamese | default for lyrics/subtitles/scroll |
| Anton | Tall condensed display | `stack`, titles, hooks (uppercase) |
| Montserrat | Geometric, clean | pop/EDM subtitles |
| Playfair Display | Elegant serif | ballad, romantic, cinematic titles |
| Dancing Script / Pacifico | Handwritten | love songs, diary mood, acoustic - short lines only |
Set `font:` (lyrics) and `display_font:` (stack) to any Google Font spec (`"Kanit:900i"`); always check the font
covers the lyric language (`mv fonts check`). With artwork, match its lettering (fonts.md recipe + `typo`).

Readability rules
- 9:16: ≤ ~30 characters per row, max 2 rows; keep text inside x 8-92 %, y below 20 % and above 80 % of height.
- On-screen time ≥ 1.2 s per line; reading speed ≤ ~17 characters/second.
- Contrast: outline/shadow is built in; darken or blur busy backgrounds instead of making text bigger.
- Accent colour on ≤ 1 element at a time (filled word, one stacked row, glow).
