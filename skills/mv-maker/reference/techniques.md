# MV technique catalogue

Use this to PROPOSE techniques from the song's meaning (see SKILL.md step 3). Every proposal = technique ID +
one line tying it to the lyric/emotion, written in the user's language. ✅ = `mv` renders it ·
🛠 = manual in CapCut/Resolve, or extend `scripts/mv.py`.

House style: **soft seams by default** - splits use `feather` 0.2 (set `feather: 0` only when a hard,
graphic contrast is the point, e.g. "you / me", before / after, a beat-heavy dance break).

## 1. Composition - two or more videos in one frame
| ID | Name | Meaning / when to use | storyboard | |
|---|---|---|---|---|
| C-SPLIT-SOFT | Soft-seam split | Two worlds / two moments melting together: nostalgia, longing, "in two places" | `layout: split_v` (feather 0.2 default); memory half `fx: [blur:10, warm]` | ✅ |
| C-SPLIT-HARD | Hard split | Clear contrast, strong rhythm, comparison | `split_v` + `feather: 0` | ✅ |
| C-SIDE | Left / right split | Two people facing each other, dialogue, distance | `split_h` (+ `mirror` on one side) | ✅ |
| C-TRIPTYCH | Three rows | Final chorus: every visual thread at once | `split_3v` | ✅ |
| C-PIP | Picture in picture | The present "looking back" at the past, reactions | `pip`, `inset.pos` | ✅ |
| C-DOUBLE-EXPO | Double exposure | A memory haunting the present, missing someone | 2nd layer `blend: screen, opacity: 0.35-0.5, fx: [blur:6-10]` | ✅ |
| C-DREAM-MIX | 50/50 mix + glow | Dream, reminiscence, floating feeling | 2nd layer `blend: normal, opacity: 0.5`, shot `fx: [glow]` | ✅ |
| C-SOFTLIGHT | Keepsake overlay | An old photo / object soaking into the scene | `blend: softlight, opacity: 0.4`, image + `zoom: in` | ✅ |
| C-FIT-BLUR | Landscape on blurred fill | Keep a 16:9 stage/live frame intact in a vertical video | `layout: fit_blur` | ✅ |
| C-LIGHT-LEAK | Light leak / film burn | Warmth, beautiful memories, section changes | stock light-leak clip as `blend: screen` 0.5-0.8 layer | ✅ (needs clip) |

## 2. Rhythm - sync with the music
| ID | Name | Meaning / when to use | storyboard | |
|---|---|---|---|---|
| R-BEAT-CUT | Cut on the beat | The foundation of every MV | cut at `analysis.json` beats/downbeats | ✅ |
| R-ACCEL | Accelerating cuts | Pre-chorus: shots shrink 4→2→1 beats to build tension | decreasing shot length | ✅ |
| R-FLASH-DROP | Flash on the drop | Explosion into the chorus | `transition: flash` | ✅ |
| R-ZOOM-PULSE | Beat zoom pulse | Energetic chorus, dance, cheering crowd | `beat_fx: [zoom]`, `beat_every: 1|2` | ✅ |
| R-BEAT-FLASH | Beat brightness flash | Stage lights, lightsticks, excitement | `beat_fx: [flash]` | ✅ |
| R-SHAKE | Drum-hit shake | Climax, shouting, emotional burst | `beat_fx: [shake]` (sparingly, ≤ 2-4 s) | ✅ |
| R-SLOWMO | Slow motion | Frozen moment, bridge, the key line | `speed: 0.5` (50/60 fps sources look best) | ✅ |
| R-SPEED-RAMP | Speed ramp | A "whoosh" into a line, then slow | layer `ramp: [[0,1],[1.2,3],[2.2,0.4]]` (shot time, speed; interpolated) | ✅ |
| R-FREEZE | Freeze frame + text | Emphasise one line / one look | layer `freeze: [at, hold]` + a caption | ✅ |
| R-SMOOTH-SLOW | Optical-flow slow motion | Silky slow-mo from 24/30 fps footage | layer `speed: 0.4, smooth: true` (CPU heavy) | ✅ |
| R-HANDHELD | Handheld drift | Intimate, documentary, lo-fi | `fx: [handheld]` (`handheld:0.5` subtler) | ✅ |
| R-MOTION-BLUR | Motion blur | Smooth fast movement, ramps, whips | `fx: [motionblur]` | ✅ |
| R-CUT-LEAD | Cut 1-2 frames early | Cuts feel exactly on the beat (the eye lags ~1-2 frames) - every beat-driven MV | `cut_lead: 1f` | ✅ |
| R-LIPSYNC | Lip-synced performance | Artist mimes the song; stays in sync on every cut, multi-cam between takes | `mv sync`, layer `lipsync: true` | ✅ |

## 3. Transitions
| ID | Name | Meaning | storyboard | |
|---|---|---|---|---|
| X-DISSOLVE | Dissolve | Time passing, gentle, memory | `dissolve:0.6` | ✅ |
| X-DIP-BLACK | Dip to black | Closing a chapter, silence before the bridge | `fadeblack:0.8` | ✅ |
| X-DIP-WHITE | Dip to white / flash | Awakening, flashback, heaven | `fadewhite:0.5` / `flash` | ✅ |
| X-CIRCLE | Circle open | "Opening the door", entering a new world | `circleopen:0.5` | ✅ |
| X-BLUR | Blur transition | Dreamy, drunk, dizzy | `hblur:0.4` | ✅ |
| X-SLIDE | Slide / wipe | Energy, fun, dance | `slideup:0.3`, `wipeleft:0.3` | ✅ |
| X-WHIP | Whip pan | Very fast change of place | `whip:0.25` (+ `motionblur` on both shots) | ✅ |
| X-GLITCH | Glitch cut | Digital chaos, drops, rap/EDM | `glitch:0.25` (RGB split + noise + hue burst across the cut) | ✅ |
| X-ZOOM | Zoom-through | Punch into the next scene | `zoom:0.4` | ✅ |
| X-MATCH-CUT | Match cut | Match shape/motion across two shots (hand pushes a door → door opens in another era) - cinematic | choose `in:` with `mv sheet`, `cut` | ✅ |

## 4. Look / colour
Colour grades (`fx: ["grade:<name>"]`, put first): `teal-orange` (blockbuster), `kodak` (warm film), `golden`
(golden hour), `moody` (dark, desaturated), `bleach` (bleach bypass, gritty), `noir` (contrasty B&W), `pastel`
(soft idol pop), `matte` (lifted blacks, lo-fi), `cyberpunk` (magenta/cyan night), `cold-blue` (sad, winter).
Finishing: `letterbox[:0.1]` cinema bars · `leak[:0.4]` drifting warm light leak · `bloom[:0.3]` halation ·
`sharpen` · `chroma[:4]` lens fringing · `grain` · `vignette`.

| ID | Look | Emotion | fx |
|---|---|---|---|
| L-GRADE | Colour grade preset | One consistent, graded look across all shots | `grade:<name>` |
| C-LETTERBOX | Cinema bars | "This is a film", ballads, storytelling | `letterbox:0.1` |
| L-LEAK | Light leak | Warm memories, film, love | `leak:0.4` |
| L-BLOOM | Bloom / halation | Dreamy highlights, stage lights, golden hour | `bloom:0.3` |
| L-WARM-FILM | Warm film | Fond nostalgia, youth | `vintage`, `grain:8`, `warm` |
| L-OLDFILM | Faded old film | Distant past, loss | `oldfilm` |
| L-VHS | VHS tape | 90s, family memories, retro | `vhs` |
| L-BW | Black & white | Loneliness, raw truth, bridge | `bw`, `contrast:1.15` |
| L-COOL | Cool | Parting, night, rain | `cool`, `sat:0.85` |
| L-GLOW | Glow | Stage, lightsticks, dream | `glow` |
| L-GLITCH | Glitch | Chaos, inner conflict, electronic beats | `rgbsplit`, `vhs` (short) |

## 5. Lyrics / text  (full guide: `reference/lyrics.md`)
| ID | Style | When | storyboard |
|---|---|---|---|
| K-FADE | Fade in | Verse, ballad | `lyric_style: subtitle` (fade) |
| K-RISE | Drift up | Gentle, narrative lines | `subtitle` + `lyric_anim: rise` |
| K-POP | Pop in | Hook, catchy line | `subtitle` + `lyric_anim: pop` |
| K-KARAOKE | Words fill as sung | Sing-along, fan edits, chorus | `lyric_style: karaoke` |
| K-WORD | Word by word | Rap, slow emotional lines | `lyric_style: word` |
| K-TYPE | Typewriter | Confessions, letters, messages, intro | `lyric_style: typewriter` |
| K-STACK | Big stacked words (kinetic) | Hook/drop, viral lyric videos | `lyric_style: stack` |
| K-NEON | Neon glow | Night, EDM, retro, late-night love | `lyric_style: neon` |
| K-SCROLL | Apple-Music style scrolling list | Lyric videos, poster player | `lyric_style: scroll` |
| K-BILINGUAL | Bilingual lines | International songs, foreign fans | `original | translation` in lyrics.txt |
| K-POSTER | Poster player (cover + lyrics + progress bar) | Only a cover image, quick lyric video | `layout: poster` |
| K-TITLE | Centred title | Open/close, song title | `caption_style: title` |
| K-GRUNGE | Distressed slam-in words | Rock, punk, rap | `lyric_style: grunge` |
| K-PAPER | Paper cut-out strips | Indie, folk, cute | `lyric_style: paper` |
| K-MARKER | Highlighter as sung | Sing-along, emphatic lines | `lyric_style: marker` |
| K-STAGGER | Kinetic key-word layout | Kinetic-typography lyric videos | `lyric_style: stagger` (+ `emph:`) |
| K-TEMPLATE | Lyric-video template | Whole lyric video from a look in one step | `mv auto --template lv-...` |
| K-SPECTRUM | Audio spectrum / wave | Lyric videos, visualizers | `visualizer: {type: bars}` |
| L-GEN-BG | Generated background | No footage: smoke, bokeh, paper, grunge, blocks, CRT, gradient | source `gen: "smoke:$1,$3"` |

## 6. Storytelling devices (concept level)
| ID | Device | Description |
|---|---|---|
| S-INTERCUT | Performance / story intercut | Verses on the story, choruses on the performance, bridge breaks the pattern; `role:` per shot (genres.md) |
| S-COVERAGE | Size progression | Wide → medium → close as emotion rises; change `size:` on every cut from the same source (no jump cuts) |
| S-TITLE-CARD | Official title card | Artist + "Title" lower-left over the intro, end card at the close (`title_card`, `end_card`) |
| S-MOTIF | Recurring image | An object/shape at the start and the end (a door, a piano) → the story closes its loop |
| S-THEN-NOW | Then and now | Same person/place/song at two moments; combine with C-SPLIT-SOFT or C-PIP |
| S-CALLBACK | Callback | Final chorus flashes back through earlier shots (R-ACCEL) |
| S-CALL-RESPONSE | Call and response | Singer sings a line → cut to fans singing along / waving lightsticks |
| S-LITERAL-METAPHOR | Literal vs metaphor | Don't illustrate every word; mix 1 literal line with 2-3 metaphorical ones |
| S-HOOK-3S | 3-second hook | Strongest shot first (best image / the hook line) to hold viewers on TikTok |

## Mood → quick picks
| Song / section feels like | Quick picks |
|---|---|
| Nostalgia, remembering | C-SPLIT-SOFT + L-WARM-FILM + X-DISSOLVE + C-DOUBLE-EXPO |
| Parting, sadness | L-COOL/L-BW + R-SLOWMO + X-DIP-BLACK + K-RISE |
| Sweet love | L-GLOW + C-DREAM-MIX + X-DIP-WHITE + K-FADE |
| Upbeat, dance, party | R-BEAT-CUT + R-ZOOM-PULSE + R-BEAT-FLASH + X-SLIDE + K-POP |
| Climax, emotional burst | R-ACCEL → R-FLASH-DROP + R-SHAKE (short) + C-TRIPTYCH |
| Fan tribute / concert | S-CALL-RESPONSE + C-SPLIT-SOFT (singer / fans) + L-GLOW + R-BEAT-FLASH |
| Storytelling, journey | S-MOTIF + X-MATCH-CUT + X-CIRCLE + S-THEN-NOW |

## Rules of thumb
- Cut on the beat; big changes on downbeats/section starts; never cut mid-word.
- Average shot depends on the genre (`reference/genres.md`, `mv check`): ballad verse 2.5-5 s, pop chorus 0.8-2 s,
  EDM drop 0.25-1 s; the last chorus is the fastest-cut section.
- Change shot size on every cut from the same source; intercut performance / story / b-roll.
- Max 2-3 layers at once; overlays at 25-50 % opacity.
- One signature look per section; save the strongest effect (shake, flash burst) for 1-2 moments.
- Keep faces/text out of the bottom ~20 % and right ~12 % in 9:16 (platform UI).

## Platform specs
See `reference/platforms.md` (TikTok, Reels, Facebook, Shorts, YouTube: format, length, safe zones, hook, loudness)
and `mv platforms`. Plan the platforms before choosing footage.
