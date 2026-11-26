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
| R-SPEED-RAMP | Speed ramp | A "whoosh" into a line, then slow | | 🛠 |
| R-FREEZE | Freeze frame + text | Emphasise one line / one look | | 🛠 |

## 3. Transitions
| ID | Name | Meaning | storyboard | |
|---|---|---|---|---|
| X-DISSOLVE | Dissolve | Time passing, gentle, memory | `dissolve:0.6` | ✅ |
| X-DIP-BLACK | Dip to black | Closing a chapter, silence before the bridge | `fadeblack:0.8` | ✅ |
| X-DIP-WHITE | Dip to white / flash | Awakening, flashback, heaven | `fadewhite:0.5` / `flash` | ✅ |
| X-CIRCLE | Circle open | "Opening the door", entering a new world | `circleopen:0.5` | ✅ |
| X-BLUR | Blur transition | Dreamy, drunk, dizzy | `hblur:0.4` | ✅ |
| X-SLIDE | Slide / wipe | Energy, fun, dance | `slideup:0.3`, `wipeleft:0.3` | ✅ |
| X-WHIP | Whip pan | Very fast change of place | approx. `smoothleft:0.2`; real one 🛠 | ✅/🛠 |
| X-MATCH-CUT | Match cut | Match shape/motion across two shots (hand pushes a door → door opens in another era) - cinematic | choose `in:` with `mv sheet`, `cut` | ✅ |

## 4. Look / colour
| ID | Look | Emotion | fx |
|---|---|---|---|
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

## 6. Storytelling devices (concept level)
| ID | Device | Description |
|---|---|---|
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
- Average shot: verse 2.5-4 s, chorus 0.8-2 s; vary it.
- Max 2-3 layers at once; overlays at 25-50 % opacity.
- One signature look per section; save the strongest effect (shake, flash burst) for 1-2 moments.
- Keep faces/text out of the bottom ~20 % and right ~12 % in 9:16 (platform UI).

## Platform specs
| Platform | Aspect / size | Notes |
|---|---|---|
| TikTok, Reels, Shorts, FB Reels | 9:16 1080x1920, 30 fps | hook in the first 1-3 s; Shorts ≤ 3 min |
| YouTube | 16:9 1920x1080 / 3840x2160 | full song, lower-third lyrics |
| Facebook feed | 4:5 1080x1350 or 1:1 | |
