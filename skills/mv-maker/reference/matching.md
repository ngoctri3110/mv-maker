# Finding and choosing footage by description

mv-maker matches pictures to words with **Google SigLIP 2**, a free vision-language model that runs locally
(installed with `mv doctor --install match`; ~0.8 GB PyTorch CPU or ~3 GB CUDA, plus the model: `base` ~1.5 GB,
`large` ~4.5 GB, downloaded on first use; `mv doctor` picks `large` on a GPU with >= 16 GB RAM). It understands many
languages, but **English visual descriptions match best**. Without it every command still works, just unranked.

The agent stays the final judge: the model shortlists, the agent **opens the contact sheets and looks**, the user approves.

## 1. Writing `look_for` - the most important step
A lyric is a feeling; the model can only match what a camera sees. Translate meaning into a concrete picture:
| lyric / idea | weak `look_for` | strong `look_for` |
|---|---|---|
| "nhớ em" (missing you) | "missing someone" | "a young woman alone by a rainy window at night, looking outside, warm lamp light" |
| "mùa hè rực rỡ" (bright summer) | "summer" | "friends laughing on a sunny beach, golden hour backlight, slow motion" |
| "đường về nhà" (the way home) | "home" | "a motorbike riding down a narrow street at dusk, city lights, shot from behind" |
Rules: subject + action + place + light/time + camera (wide shot, close-up, aerial, from behind, slow motion).
One picture per description. Give 2-3 phrasings as a list when unsure - they are averaged:
`look_for: ["rain drops on a window at night", "blurry city lights through a wet window"]`.
`avoid:` removes what you do not want: `avoid: "text, logo, watermark, cartoon"`.

## 2. Online footage (before downloading anything) - `mv scout`
Give every source that needs footage `search:` (keywords for the site search, a list = several phrasings) and
`look_for:` (the picture to rank by):
```yaml
sources:
  rain_window:
    search: ["rain window night", "raindrops glass city lights"]
    look_for: "rain drops running down a window at night, blurred city lights behind"
    avoid: "text, watermark"
    orient: portrait            # optional
```
`mv scout projects/<slug>` searches Pexels / Pixabay (with free keys), Wikimedia Commons and YouTube, ranks every
candidate by its thumbnail, then **deep-scans the best YouTube videos**: it reads their preview storyboard (the hover
thumbnails, a few hundred KB, no video download), finds the moment that matches, and suggests a `section` around it.
Output: `refs/cand_<source>.jpg` per source (numbered best-first) + `refs/scout.md`. Look, show the user (GATE 2),
then `mv pick <project> <source> <source>:<n>` - a deep-scanned pick keeps its section, so `mv fetch` downloads only
those seconds. One-off searches: `mv find "<keywords>" --describe "<picture>" --rank --deep 5`.

**TikTok / Facebook / Instagram / X**: these sites cannot be searched through yt-dlp. Ask the user for links (or a
profile / hashtag / playlist page yt-dlp can open) and rank them: `mv find --links links.txt --describe "..." --rank`.
Metadata and thumbnails only until the user approves; rights are unknown - say so (SKILL.md rules).

## 3. Your own footage - `mv ingest` + `mv match`
1. `mv ingest projects/<slug> <folder>` registers clips/photos as `own1..ownN` and splits them into scenes.
2. In the storyboard give shots `layers: auto` (or a layer `{src: auto, fx: [...]}` to keep per-layer settings) and a
   `look_for` (a shot with `look_for` and no layers counts as auto). `mv auto <project> --template <footage preset>
   --genre <g>` writes such a skeleton cut to the genre grammar - replace each `look_for: TODO ...`.
3. `mv match projects/<slug>` samples 3 frames per scene, scores them against each shot, sets the in-point so the
   best frame sits a third into the shot, and assigns scenes globally (no scene twice, never the same scene in two
   neighbouring shots; `--reuse` relaxes the first). Restrict the pool with `--sources own,story`.
   Output: `matches.yaml` (top candidates per shot, `use:` = the chosen one) and `refs/match_all.jpg` (chosen frames
   in shot order; `--sheets` adds one sheet of alternatives per shot). **Open match_all.jpg**; swap a shot with
   `mv match <project> --pick S07:2` or by editing `use:`. Rendering reads matches.yaml - storyboard.yaml is untouched.
4. Downloaded online picks are part of the pool too: scout → pick → fetch → match mixes both.
5. Then the usual loop: `mv review` (edit check), proxy render, look at frames, adjust, final render. The preset and
   genre give the cutting rhythm and effects; performance clips still use `mv sync` + `lipsync: true`.

Frame embeddings are cached in `build/match/` - re-running after editing `look_for` only embeds the new text.
