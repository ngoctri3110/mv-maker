# Plan for the platform before you edit

Decide **where the video will be posted before choosing footage**: the platform sets the aspect ratio, the length,
where text may sit and what the first seconds must do - and therefore which sources are usable. Numbers:
`platforms.yaml` (checked 2026-11; platforms change limits often - verify in their help centres before publishing).
`mv platforms` prints the table; `mv platforms --for tiktok,youtube` (or `--project <p>` with `platforms:` in the
storyboard) prints a production plan.

## Specs at a glance
| | TikTok | Instagram Reels | Facebook Reels | Facebook feed | YouTube Shorts | YouTube |
|---|---|---|---|---|---|---|
| format | 9:16 1080x1920 | 9:16 1080x1920 | 9:16 1080x1920 | 4:5 1080x1350 (1:1 ok) | 9:16 1080x1920 | 16:9 1920x1080 / 3840x2160 |
| max length | 10 min (in-app) | 3 min to reach new viewers | ~90 s | long | 3 min | 12 h |
| performs best | 15-60 s | 15-90 s | 15-60 s | 30 s-3 min | 20-60 s | full song |
| keep clear (top/bottom/sides) | 10 % / 25 % / right 14 % | 14 % / 35 % / 6 % | 14 % / 35 % / 6 % | small | 10 % / 25 % / right 14 % | title-safe 5 %, controls 10 % |
| hook | 1-2 s | 1-2 s | 3 s | 3 s (often muted) | 1-2 s | first 10 s |
Audio: every platform normalises loudness to about **-14 LUFS** (louder is turned down). Leave a finished master as
it is; `loudness: -14` in the storyboard only fixes a mix that is far too quiet or loud.

## The plan, step by step (before the storyboard)
1. **Platforms** - ask the user; "all" = TikTok + Reels + Facebook Reels + Shorts + YouTube. Set `platforms:`.
2. **Versions** - one per aspect ratio: 9:16 (TikTok, Reels, Shorts), 4:5 (Facebook feed), 16:9 (YouTube).
   One edit, re-framed: `mv render <p> --format 16:9`. Short versions for platforms with a length cap or a short
   sweet spot: pick the section (usually the first chorus or the hook) now and render it with
   `mv render <p> --cut 0:45-1:30` - plan the edit so that section opens on a strong image.
3. **Master format** - one platform: its own. Mixed: edit in the format you care most about and keep subjects in the
   centre third so the other crop works; `focus: [x, y]` per layer fixes individual shots.
4. **Sources to look for** (scout / own footage):
   - vertical only: vertical clips are best; landscape works when the subject is centred (it is cropped to the middle
     third) - or use `layout: fit_blur` to show the whole frame;
   - vertical + YouTube: landscape 4K (or 1080p at least) with centred subjects crops to both; portrait-only clips
     need `fit_blur` in 16:9;
   - resolution: at least the version's height (1920 for 9:16) after cropping - 1080p landscape cropped to 9:16 is
     only 608 px wide, so prefer 4K landscape or native vertical for the vertical version;
   - `orient: portrait` on a source (or `--orient portrait`) limits stock results to vertical clips.
5. **Safe zones** - with `platforms:` set, lyrics and title cards are placed inside the strictest safe zone of the
   platforms sharing the format (e.g. above the 35 % Reels caption area). Faces and key action belong there too:
   choose shots and `focus` accordingly.
6. **Hook** - the first 1-3 s decide a vertical video: open on the best image or the hook line, not on a slow intro.
   For a full-song YouTube video the intro may breathe, but the short versions must not.
7. **Rights** - commercial songs and other people's footage are matched by Content ID (YouTube) and the platforms'
   audio fingerprinting: expect muting, blocks or no monetisation; TikTok/Instagram's own music library avoids muting
   for the short versions.
`mv review` adds a **Platform check** (versions missing, length vs limit, hook, lyric area inside the safe zone).
