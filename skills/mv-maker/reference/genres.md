# Cutting like a professional music video, genre by genre

Read this before planning a footage-led MV (video type A). It is the grammar music-video editors follow; the numbers
live in `genres.yaml` and `mv check` / `mv review` measure the storyboard against them. Set `genre:` in the storyboard.

## 1. How professional MVs are built

**Three kinds of footage, intercut.** Almost every label-released MV mixes:
| `role` | What it is | Job in the edit |
|---|---|---|
| `performance` | The artist singing to camera / the band playing, shot to playback of the song | Connection, lip-sync, energy; carries choruses |
| `narrative` | The story world: characters, situations, a small plot | Meaning; carries verses |
| `broll` / `concept` | Details, symbols, textures, abstract or styled images | Rhythm, breathing room, cutaways that hide jumps |
The usual pattern: verses lean on the story, choruses swing to performance, the bridge breaks the pattern
(a single long shot, black and white, slow motion, silence), and the last chorus braids everything together.

**Coverage and shot size.** Every set-up is filmed wide → medium → close (often ECU and inserts too), so the editor can
change size on each cut. Rules that follow from it:
- Never cut between two shots of the same source at the same size (`size:`) - that is a **jump cut**. Change size by at
  least one step (wide → medium, medium → close), change angle, or put a cutaway (`broll`) between.
- Open sections wide to place the viewer, then move in as the emotion rises; save the closest shot for the key line.
- A run of 3+ shots at the same size flattens the energy.

**Lip-sync (performance).** The artist mimes to the song played on set, and every take covers the whole song. In the
edit the performance clip is locked to the song: cut anywhere and the mouth still matches. In mv-maker:
`mv sync <project> <source>` finds the offset by matching the clip's own sound to the song, then layers use
`{src: perf, lipsync: true}` - no `in:` needed. Several takes (wide / close / side) = several sources, each synced:
cutting between them is a multi-cam edit.

**Rhythm.**
- Cut on the beat; big changes (section starts, location changes) on the downbeat / start of the bar.
- **Cut a frame or two early** (`cut_lead: 1f`-`2f`): the eye needs about 1-2 frames to register a new picture, so
  early cuts feel exactly on the beat, cuts exactly on the beat feel late.
- Shot length is the energy dial: shorter shots = more energy. The final chorus should be the fastest-cut section;
  the bridge the slowest.
- Accelerate into a chorus (R-ACCEL), then let the first chorus shot hold for a beat - the release.
- Cut on action (a turn, a hand moving, a head lifting) to hide the cut; match-cut shapes and motion across locations.

**Story beats.** Hook in the first 1-3 s on vertical video (strongest image or the hook line); the title card over the
intro; a recurring motif that returns at the end (S-MOTIF); a payoff shot in the last chorus.

## 2. Genre grammar
Average shot length per section (seconds) and performance share - the full table is `genres.yaml` (`mv genres`).

| genre | verse | chorus | min shot | cut on | performance | signature moves | presets |
|---|---|---|---|---|---|---|---|
| `ballad` | 2.5-5 | 1.5-3.5 | 1.2 | downbeat | verse 25-60 %, chorus 35-75 % | slow push-ins, dissolves, close-ups on the key line, bridge in black & white or slow motion | cinematic-ballad, wedding-romance |
| `pop` | 1.5-3 | 0.8-2 | 0.5 | beat | verse 30-70 %, chorus 50-90 % | bright grade, colour-coded locations, beat zoom in the chorus, dance cutaways, flash into the chorus | pop-bright, tiktok-remix |
| `kpop` | 1-2.5 | 0.5-1.5 | 0.35 | beat | mostly performance (choreography) | wide for formations, close for each member's line, hard cuts on hits, whip/zoom transitions, set changes per section | kpop-stage, pop-bright |
| `rap` | 0.8-2.5 | 0.5-1.5 | 0.3 | beat (snare) | verse 50-90 % | rapper to camera with wide lenses, crew shots, cut on the snare and on punchlines, shake/flash on hits, word-by-word lyrics | rap-kinetic, tiktok-remix |
| `edm` | 1.5-3 | 0.4-1.2 (drop 0.25-1) | 0.25 | beat | low (crowd, DJ, abstract) | long build with accelerating cuts, black or white flash at the drop, strobe-like bursts only in the drop | edm-neon, tiktok-remix |
| `rock` | 1.2-3 | 0.6-1.5 | 0.3 | beat | verse 50-90 %, chorus 60-95 % | band performance in one location, handheld, cut on drum hits, gritty grade, shake on crashes | rock-grunge, rap-kinetic |
| `indie` | 3-8 | 2-5 | 1.5 | phrase | 10-70 % | long takes, natural light, handheld drift, film grain, few effects | lofi-chill, vintage-90s |
| `rnb` | 2-4 | 1.2-2.5 | 0.8 | downbeat | 40-85 % | low-key night light, slow motion, smooth dissolves, close-ups on texture | rnb-night, cinematic-ballad |

V-pop ballads → `ballad`; V-pop dance tracks → `pop`; Vinahouse / remixes → `edm` with `tiktok-remix`.

## 3. Planning a professional MV in mv-maker
1. `genre:` + one fitting preset from the table (`preset:`); `cut_lead: 1f` for beat-driven genres.
   Shortcut: `mv auto <project> --template <preset> --genre <g>` writes a shot skeleton cut to this grammar
   (`layers: auto` + `look_for` per shot, filled from the user's clips by `mv match` - see matching.md).
2. Per section, decide the role mix (performance vs story vs b-roll) from the table and write `role:` + `size:` on every
   shot. Plan size changes on every cut from the same source.
3. Performance footage: one source per camera set-up, `mv sync` each, `lipsync: true` on the layers.
4. Shot lengths from the genre's range; accelerate into choruses; the last chorus fastest.
5. `title_card:` (artist + "Title", lower-left like official MVs) over the intro; `end_card:` for the last seconds.
6. `mv review` writes the **Edit check** table into storyboard.md (or `mv check <project>`): average shot per section
   vs the genre range, performance share, jump cuts, size variety, cuts off the beat, the 3-second hook and the energy
   build into the last chorus. Fix what matters; the check is advice, not a rule - break it on purpose and say why.

## 4. Lyric videos are a different grammar
Text is the hero, so the cutting follows the lyric lines, not the footage: one scene per 1-2 lines or per section,
backgrounds that change with the song so the eye stays busy, lyrics in early enough to sing along (`lyric_lead`
0.25-0.4 s). See `lyrics.md` (styles + templates) and `mv auto`.
