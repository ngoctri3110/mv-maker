# Fonts & lettering

Lyrics look best when they **echo the artwork's lettering** (poster, cover, title card) and **cover the lyric
language**. Any Google Fonts family works (free, OFL); the curated catalogue below adds look/mood tags.

## Font spec
`"Family"` · `"Family:800"` (weight) · `"Family:900i"` (italic) · `"Archivo:900i@125"` (+ width axis, 125 = expanded).
Used in `font:` (lyrics), `display_font:` (stack / big words), `poster.title_font`, `poster.artist_font`.
Fonts download on first use into `SKILL_DIR/fonts/gf/` as static TTFs (cached). Plain names of installed
system fonts also work (`font: "Arial"`).

## Commands
| Command | Does |
|---|---|
| `mv fonts list [--lang vietnamese] [--tag "speed italic"]` | browse the catalogue by script and look |
| `mv fonts get "Kanit:900i" "Exo 2:800i"` | download + print the font name libass will use |
| `mv fonts check "Bebas Neue" --project projects/x` | glyph coverage of the real lyrics (catches missing diacritics) |
| `mv fonts preview projects/x --fonts "A:900i,B:900 +0.2,..." [--text "..."]` | specimen image `refs/fonts_preview.jpg`: the real lyric line in each candidate over the blurred poster, with typo applied and a coverage OK/missing label. `+0.2` = preview that font with a synthetic slant |
| `mv palette <image>` | main tones + vivid accent colours of the artwork |

## Matching a poster - recipe
1. **Look at the image** (open it). Describe the title lettering on 6 axes:
   - *classification*: sans / serif / slab / script / handwriting / graffiti / pixel / blackletter
   - *weight*: thin … black · *width*: condensed / normal / wide-expanded
   - *posture*: upright / italic / extreme slant · *case*: UPPER / mixed · *spacing*: tight / normal / wide
   - *finish*: colour, outline, drop shadow, glow, gradient, texture
2. **Map to tags** and shortlist 4-7 candidates with `mv fonts list --lang <lyric script> --tag "<look>"`
   plus your own knowledge of Google Fonts. Always include at least one safe, highly readable option.
   Upright-only fonts can get the slant from `typo.slant` - preview them with `"Font:900 +0.2"`.
3. `mv palette` → choose `accent` from the vivid list (karaoke fill, progress bar, glow) and text/outline/shadow
   colours from the lettering itself.
4. `mv fonts preview projects/<slug> --fonts "..."` with the real lyric line; open the image, discard rows marked
   `missing`, and show it to the user with your top pick and why. Let the user choose (part of GATE 1).
5. Write the choice into the storyboard: `font`, `display_font`, `poster.title_font`, `typo`, `accent`.

Typical mappings
| Poster lettering | Candidates (Latin + Vietnamese) |
|---|---|
| Heavy wide italic, speed / cars / sport titles | `Archivo:900i@125`, `Kanit:900i`, `Unbounded:900 +0.22`, `Encode Sans Expanded:900 +0.22`, `Exo 2:900i`, `Saira:900i` |
| Tall condensed caps, cinematic / news | `Anton`, `Oswald:700`, `Barlow Condensed:800`, `Big Shoulders Display:900` (`Bebas Neue` = Latin only) |
| Clean geometric pop | `Montserrat:800`, `Plus Jakarta Sans:800`, `Be Vietnam Pro:800` |
| Elegant high-contrast serif, luxury / romance | `Playfair Display:700i`, `Prata`, `Cormorant Garamond:600i` |
| Handwritten / diary / acoustic | `Patrick Hand`, `Dancing Script:700`, `Caveat:700` (Latin only - no Vietnamese) |
| Script retro / summer | `Pacifico`, `Lobster` |
| Street / graffiti / hip-hop | `Bungee`, `Sedgwick Ave Display`, `Permanent Marker` (Latin only) |
| Techno / gaming / EDM | `Chakra Petch:700`, `Exo 2:800`, `Orbitron:900` (Latin only) |
| Retro pixel / terminal | `Press Start 2P`, `VT323` |
| Japanese / Korean / Chinese / Thai / Arabic / Hindi lyrics | `Dela Gothic One`, `M PLUS Rounded 1c`, `Noto Sans JP` · `Black Han Sans`, `Noto Sans KR` · `ZCOOL KuaiLe`, `Noto Sans SC/TC` · `Kanit`, `Prompt`, `Mitr` · `Cairo`, `Noto Sans Arabic` · `Hind`, `Noto Sans Devanagari` |

## typo - poster-matched lettering (storyboard)
```yaml
font: "Archivo:900i@125"
display_font: "Archivo:900i@125"
typo:
  upper: true            # force UPPERCASE
  color: "#FFFFFF"       # text fill
  outline_color: "#000000"
  outline: 0.4           # outline width multiplier (0 = none)
  shadow: 2.2            # drop-shadow multiplier (0 = none)
  shadow_color: "#1A1A1A"
  spacing: 2             # letter spacing in px at 1080 (negative = tighter)
  slant: 0.22            # synthetic italic for upright fonts (0.15-0.3 typical)
  bold: true             # false = use the font's own weight exactly
poster: {title_font: "Archivo:900i@125", artist_font: "Archivo:700", ...}
```
Rules: readability beats likeness - if the poster font is very thin, decorative or tightly spaced, use it for
`display_font` / titles only and a cleaner sibling for running lyrics. Check coverage for every font the lyrics use;
`render` warns when a font lacks characters of the lyrics.
