---
name: voiceover-reel
description: Make a VOICEOVER (Family B) — a faceless, cinematic reel where the creator's voiceover is the spine and her existing b-roll is dressed onto it. Use when the creator says "make my voiceover reel", "make my vo reel", "voiceover reel", "make a faceless reel", "turn my voiceover into a reel", or drops a voiceover + b-roll. ALSO the front half of an ANIMATION reel ("make an animation reel", "animate my voiceover", "animation reel from my voiceover"), which runs the same voiceover cut and then the animation branch below instead of b-roll. NOT a talking-head Yap. Runs the whole pipeline end to end into a finished reel.
---

# Voiceover — the builder

A faceless reel: her **voiceover is the spine**, her **own b-roll is the picture**, cut to the voice.
Two inputs, not one. Full spec: [`product/VO-REEL.md`](../../../product/VO-REEL.md).

## Two roads: her visual editor, or made for her
When `python3 product/visual_editor.py mode` prints `visual` or `ask` (her editor is on), the FIRST thing is ONE
clickable pick-one: **Edit it in my visual editor** (she trims her voiceover herself on the Cut tab, then fills it
with her clips on Visuals; recommended when the editor is her default) · **Make it for me** (this whole pipeline,
hands-off). `text` = no question, this pipeline. The animation branch below is always this pipeline.
- **Visual editor:** `python3 product/visual_editor.py vo-start <job> <her recording>` (the intake below decides the
  recording), then the `rough-cut` skill takes it from the transcript (its "A voiceover she wants to edit in her
  visual editor" bullet: punchy or emotional, the cut, the review gate). Don't ask where her footage is: she picks the
  folder on Visuals (**Fill with my b-roll**), and "fill my b-roll" is the `rough-cut` skill's step. Captions there
  follow this skill's locked rules.
- **Made for her:** the pipeline below, unchanged.

## Inputs
- `audio/vo.*` — the voiceover recording (the spine). **Default source = the newest audio file in `inbox/`**
  (`.m4a .mp3 .wav .aac .caf`, or a video she recorded it on, audio only). **Copy** it to
  `projects/<job>/audio/vo.<ext>` (never move it), same intake rule as every other format.
- **Footage: ALWAYS ASK where it is.** Two options, she picks: **this reel's folder** (a folder she points at,
  or `projects/<job>/broll/`) OR **her general b-roll library** (a standing folder she reuses across reels,
  configured once — e.g. `~/Movies/b-roll`). That folder becomes `broll-select.py --lib <folder>`. Never
  assume a location, but DO suggest the likely one: `inbox/b-roll/grabs/` (clips she already prepped and
  culled with `broll-prep`) is the best answer when it exists, then `inbox/b-roll/`. **She does NOT
  hand-curate** — she dumps what she has, the engine picks the best.
- **Say up front that this takes longer than a talking-head reel**, because every clip has to be watched
  before anything can be placed. One plain line, before step 3 starts.
- **Clip catalog.** If the footage folder holds a `clip-catalog.md`, READ IT FIRST and only watch clips that
  are not in it (new or changed files). See step 3c.

## Run it (the pipeline)
1. **Transcribe the VO** — `uv run product/vo-cutgrid.py --job <job>` → `vo-grid.json` (words + phrases + timings).
   The language is detected from her voice, never assumed; it says so when it hears something other than
   English. If it guessed wrong, run it again with `REELS_ENGINE_LANGUAGE=<code>` (es, fr, ...) in front.
2. **ASK the register — "punchy or emotional?"** (the VO's teaching-vs-confessional). Infer a default from
   the delivery/words and confirm. It drives PACING, mainly the dead space between lines:
   **punchy → trim the gaps (tight, energetic, sharper burst); emotional → leave breathing room (preserve
   the pauses, longer holds, gentle open).**
3. **PREP the footage, THEN pick from it — never select straight off raw clips.** Two steps, in this order,
   every time (locked by the creator 2026-09-14 after a build chose weak moments from long raw takes):
   - **(a) Prep** — run the **`broll-prep`** skill over her footage folder. It reads timecoded contact
     sheets of every clip and pulls the 3-4 BEST moments per clip as short named grabs (`sink-full-scrub`,
     `walk-away-wide`), named by what is actually in frame. 🔴 **Watch the sheets. Filenames lie, and so does
     one summary sheet of one frame per clip** — that is exactly how a build ends up on the dull middle of a
     good take. A clip with an arc (a sink going from full to clean) must be sampled ACROSS that arc so the
     story is readable in the b-roll itself.
   - **(b) Select** — `uv run product/broll-select.py --lib <grabs folder> --job <job>` (no `--need`; it
     keeps every usable grab) → `broll-select.json` + `broll-candidates.jpg`. Each pick carries
     `windows[]`: up to 3 clean non-overlapping windows per clip at two lengths, `kind: "burst"` (short,
     for the opener) and `kind: "hold"` (longer, for beats that sit on a shot). Author the shot plan from
     those windows. Rejects flicker (oscillation, native-fps) + blur/dark, and each dropped clip's line says
     which. **`--allow-flicker`**: when a clip she wants is dropped for flicker that is really a look (sun
     glare, golden-hour flare, dappled light), run the selector again with `--allow-flicker`. The clip is then
     kept and flagged `[FLICKER KEPT]` instead of dropped; never try to deflicker it. Leave it off otherwise,
     so real LED/fluorescent strobe still fails loudly. A Cinematic-mode pair (`IMG_1234.MOV` +
     `IMG_E1234.MOV`) is scored once, on the rendered `E` twin.
   - **(c) Offer the catalog (ask, don't assume).** After prep, ask ONE pick-one: *"Want me to catalog
     these clips so you can reuse them later? I'll save a list of every clip and what's in it, and next time
     I read that instead of rewatching everything."* On yes, write `<footage folder>/clip-catalog.md`: one
     row per grab (file name · what's in frame · best moment(s) with timecodes · the mood or kind of line it
     suits · flags like flicker or subject leaving frame). On later runs, append new clips and drop rows for
     deleted files. On no, don't raise it again this run.
4. **Render the LISTENABLE cut, then the STYLE PLAN widget (⏸ she approves) — the SAME widget as the Yaps,**
   including her on/off switch (`python3 product/build-style-plan.py --which`, see `product/style-plan-widget.md`).
   🔴 A VO has no picture yet at this gate, but she still has to HEAR the cut before approving it, exactly
   the way she watches a Yap rough cut. So splice first (step 5's tool, run early with your recommended
   cuts), then `python3 product/vo-listen.py --job <job>` → `outputs/<job>.mp4`, a 9:16 follow-along with
   the line number + text + beat tag on screen. End the gate with the markdown link
   (`python3 product/style_plan_link.py <job>`) in the final message, after the widget (text above a tool
   call is folded away in the app), so it opens in the side-panel player. NEVER hand her an
   audio file to open elsewhere, and never `open` it in another app.
   Assume the recording is
   NOT perfect. Deliver the locked style-plan widget (delete/trash + note + attach + length meter) showing
   the **VO transcript line by line**, numbered the way `vo-splice.py --cut` counts: the lines of
   `vo-grid.json`, from 1. The listenable cut labels every slide with that same number, lines already cut
   included in the count, so "cut line 7" always means the same line. She does BOTH jobs in one gate:
   - **DELETE bad lines** (stumbles / filler / worse takes). Kept lines = the clean VO.
   - **DIRECT footage** — a NOTE or attached clip per line. Her pick wins; any kept line she leaves blank,
     YOU pick the best window (read `broll-candidates.jpg` — match by meaning; energy-match; end on the peak).
   - **Or the interview.** If she says "ask me which clips go where" (or wants help deciding), go line by
     line: read the line, offer 2 or 3 candidate clips by name with a few words on why each fits, she picks
     one or says "you pick". Batch it (several lines per question) so it never becomes 30 prompts.
5. **Splice the VO** — drop the trashed lines from the VO audio, concat, re-derive word timings (arithmetic
   remap, like `stitch-cut.sh`). **Apply the register's pacing to inter-line gaps: punchy trims to ~0.1–0.15s;
   emotional keeps/extends the pauses.** = clean VO spine + updated grid. Write `shot-plan.json`
   (`{ "burst_stab":<punchy .35 / emotional .55>, "burst":[{path,in}...], "holds":[{path,in,out}...], "takeover_from_phrase":-1 }`).
6. **Music bed: settle it BEFORE the build, never by dropping the flag.** A music bed is part of the format,
   so the default is to include one. If there is already a track in `projects/<job>/audio/` (anything other than
   `vo.*` / `vo.clean.wav` / `ambience.wav`), use it. If not, ask ONE clean pick-one: **make me options
   to try a vibe (recommended) / I'll drop in my own track / no music**.
   - **Make options:** `python3 product/gen-music.py <job> --check` first. Exit 3 means this machine cannot
     generate (Intel Mac): say so in one plain line and offer the own-track route, nothing else. Otherwise, if
     it reports the model is not downloaded yet, say once, before running, that the first time downloads
     the music model (about 2.2 GB, one time) and takes a few minutes. Then run
     `python3 product/gen-music.py <job> --vibe "<mood matched to the reel>"`. It writes three options to
     `audio/`. Link them in chat (never auto-play) and she picks one. Say in one plain line that these are
     for trying a vibe: the music model is licensed for non-commercial use, so for the reel she posts, a
     track she has the rights to (or music she adds inside CapCut) is the safe choice.
   - It runs on the WhisperX setup she already has. There is nothing extra to install, and no account.
   - **Never build without music she did not decline.** The build prints `[vo] music bed: <file>` when a bed
     went in, and a plain "no music bed on this one" line when it did not. If you see the second line and
     she never said no music, stop and fix it before handing over.
7. **Build** — `uv run product/vo-build.py --job <job> --pack <Editorial|Playful|Butter> --accent <hex|none> --pace <punchy|emotional> --music <bed.mp3>`
   → `projects/<job>/outputs/<job>.vo.mp4`. One pass: reframe to 9:16, hook-burst (sharper if punchy),
   phrase holds, spliced VO spine, music bed, karaoke-build + takeover captions in the pack fonts + accent.
   - `--caption-band lower` moves the caption out of the subject's face and off any full-screen graphic;
     `--reserve-top <px>` tells the build a persistent banner already owns the top of the safe zone.
   - `"takeover_text"` in the shot plan names the payoff FRAGMENT for the takeover. It stacks one word per
     line, so a whole sentence shrinks every word below reading size; the build warns past 7 words.
8. **Graphics ride ON the footage, never instead of it.** Build every graphic (screen demo, card, panel,
   persistent banner) as ONE transparent composition the length of the reel, with a clip per beat at its
   real `data-start`, then stack it:
   `python3 product/reel_render.py composite --base <job>.vo.mp4 --layers graphics.mov -o <job>.ov.mp4`.
   🔴 Before stacking, prove it never lands on the captions:
   `python3 product/caption_guard.py <graphics.mov> --band-top <top> --band-bottom <bottom>`. Caption line
   COUNT varies through a reel, so checking a few frames by eye cannot catch this; the guard measures every
   frame. Panels sit on a scrim derived from the pack's own dark, so her footage still reads underneath.
9. **Lay the real room sound back under it** — `python3 product/vo-ambience.py --job <job> --pace <punchy|emotional>
   --in <ov.mp4> --out <final.mp4>`, with the SAME `--pace` the build used (it sets the burst length when
   the shot plan names none). Reframing drops the source audio, and for a documentary VO the water, dishes
   and broom are half of what sells it. Every sound is cut to its shot's exact length on screen, so it stays
   on the shot that made it all the way through.

## Animation branch — the voiceover cut first, then animate (no footage)

An Animation reel is footageless: designed frames + animated type + motion graphics in the style pack's
look, over her own voice. **The voiceover cut comes FIRST and is locked before anything is animated**,
because every beat is timed to the voice and a line changed after animating means re-rendering. Trigger:
"make an animation reel", "animate my voiceover", or she says "animate it" after a voiceover cut.

1. **Same front half.** Intake from `inbox/` (Inputs above), step 1 transcribe, step 2 punchy or emotional.
   **Skip step 3 entirely** (no footage, no `broll-prep`, no catalog offer) and don't ask where footage is.
2. **Same cut gate (step 4), minus footage.** Render the listenable cut, deliver the line-by-line style plan,
   she deletes lines. There is no footage to direct: the per-line NOTE is for what should be ON SCREEN on
   that line ("the number counts up here", "just the word 'enough'"), which feeds the scene plan.
   Say plainly before she approves: *"Get the words right now. The animation is timed to your voice, so
   changing a line after it's animated means rendering it again."*
3. **Splice (step 5)** → `audio/vo.clean.wav` + `vo-grid.clean.json`. This is the locked spine. Every scene
   is timed from the clean grid's phrase timings, never the raw recording.
4. **Style pack.** Ask which pack (no default; `product/stylepack.py` / the packs in
   `product/creative-vault/style-packs.json`, her own packs included). Every font and color comes from it
   (the cross-format font-by-job rule in `CLAUDE.md`).
5. **Music (step 6), same rules.** Make options / her own track / no music, Intel limit included. Music-only
   (no voice) is also allowed for Animation: then skip 1-3, beat-sync to the track.
6. **Build with the full treatment by default, then tell her in ONE line what you did** (per
   `product/CAPABILITY-OFFERS.md` → Animation: continuous camera with matched transitions ON; type,
   imagery and data treatments chosen to fit the line). Do NOT quiz her on these as gates. She changes
   anything in plain words ("type only", "add backgrounds and icons", "count that number up", "hard cuts
   instead").
   - Load `reel-layout-rules` FIRST (operating rule 9: measured geometry, never eyeballed), then author the
     scenes as one HyperFrames composition (`faceless-explainer` for the scene-per-line explainer shape,
     `motion-graphics` for kinetic type / stat hits), 1080x1920, one scene per phrase group off the clean grid.
   - Audio in the composition: `vo.clean.wav` as the spine plus the bed under it (`hyperframes-audio` for the
     carve under the voice). Captions follow the Voiceover caption rules above (karaoke + one takeover).
   - Render through the enforced gate: `python3 product/reel_render.py render <comp_dir> -o projects/<job>/outputs/<job>.anim.mp4 --strict`
     (every word must read). It refuses on check errors; fix and re-run, never bypass.
7. **Finish = a finished MP4** (like well-done), not a CapCut draft. Rendering takes minutes, so ask her to
   batch change notes into one message, and re-render only what changed (the cache skips the rest).

## Locked rules (do not violate — see the spec + vo reel format)
- **Captions = karaoke build + one takeover. NO hook card, NO fades, NO single-snap.**
- **Accent = the creator's own color OR none (all white). NEVER impose one.** Ask which pack + accent (or none).
- **NO color grade. NO deflicker** (both removed — deflicker is a trap; keep native color).
- **Flicker = hard reject the window** (broll-select does this; a clip can flicker in one spot, be clean in
  another). Never trust catalog labels for a timestamp — read the frames.
- **The b-roll is the picture; text is captions on top.** Voiceover-led, not "faceless", not animated-text-led.
- Restricted display fonts resolve from the creator's CapCut; only OFL ships (vo-build falls back to the pack's
  OFL font if a restricted one is absent).

## Finish
Default is a baked MP4 (Route A). Offer a cover (`cover-thumbnail`) and export like any reel.

**Route B/C, the SLIP finish, is the one to offer whenever the b-roll choice is the part she is least sure
about.** It is the only finish that leaves that decision open after the build. A baked MP4 locks every shot
to the exact window the engine picked; the slip finish hands her the reel in CapCut with **every beat as a
compound clip holding its WHOLE source**, so she can double-click a beat, drag the clip inside, and play a
different moment while the beat keeps its position and length. CapCut ships no slip tool; this is what
replaces it.

Two things make it safe for her to slip freely, and both are worth telling her:
- the **voiceover is one unbroken audio track**, so nothing she does to the picture can pull it out of sync
- **graphics are timed to the VOICE, not the picture**, so slipping a shot never drags a caption with it

Build it with:
```
product/engine/VectCutAPI/venv-capcut/bin/python product/capcut-slip-reel.py \
    --job <job> --name "<job> slip" --plan shot-plan.capcut.json [--graphics <graphics.mov>]
```
CapCut MUST be quit first (the script refuses otherwise), and it will refuse to overwrite an existing draft
name rather than destroy edits she already made in CapCut. Route captions through `build-hf-captions`
(STYLE_PACK) for this finish.
