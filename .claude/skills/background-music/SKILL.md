---
name: background-music
description: "The music bed for a finished cut: music held under her voice at one steady level the engine measures for this song, easing out over the last moment. It lifts in her pauses or fades in only when she asks. The track is her own licensed file, or a few options made right on her computer to try a vibe. Only when she wants music, on any format; it comes after captions and before export. Triggers: add a music bed, make me a few music options, try a vibe, use my own song, carve the music under my voice, music under this reel."
---

# Music bed

A bed is her voice with a song held quietly under it, at one level from start to finish. It belongs to the
finish phase of a reel (CLAUDE.md, "From her phone to a finished reel"): the cut is done, the captions are on,
and the export has not run yet. It never runs on its own. *"Add a music bed"* starts it, *"skip the music"*
means nothing runs, and silence is the default. It works on any format, always on the newest finished file,
never on raw footage.

Two places lay music without this skill: a Voiceover reel settles its bed inside its own build (`voiceover-reel`,
`vo-build.py --music`), and on the CapCut route she can add a song from CapCut's own library herself.

## 1 · Which song: one pick-one

Before offering anything, run `python3 product/favorites.py show` and keep to her sound rules there. Then ask
the one pick-one (CLAUDE.md rule 1), default marked:

- **her own track**: a file she has the rights to, dropped into `projects/<job>/audio/`
- **a few options made here**: name a vibe, and three come back to try
- **no music**

When `audio/` already holds more than one track, the pick-one lists them by name. The engine never guesses
which song she meant.

**Options made here** come from the music model on her own computer, on the setup the transcriber already uses:
nothing to install, no account.
1. `python3 product/gen-music.py <job> --check`. Exit 3 means this computer cannot make music (an Intel Mac):
   offer her own track instead. If the model has not been downloaded yet, say once that the first run fetches it
   (about 2.2 GB, one time).
2. `python3 product/gen-music.py <job> --vibe "<mood>"` writes three options into `audio/`. A teaching reel and a
   confessional one want different moods; pick the words from the reel.

Say it plainly when you offer them: the model's licence is non-commercial, so these are for hearing a mood. The
reel she posts carries a track she has the rights to, her own file or a song she adds in CapCut.
`npx hyperframes bgm` can fetch tracks too, but it needs a HeyGen login, so it is never the default.

## 2 · Lay it

```bash
.claude/skills/background-music/scripts/lay-bed.sh projects/<job>/outputs/<newest finished file>.mp4 \
  projects/<job>/audio/<track> projects/<job>/outputs/<job>.bed.mp4
```

Every bed comes out the same way: the song repeats until the picture ends and fades to silence over the last
1.2 seconds, the sum of voice and song goes through the rough cut's own −1 dBFS limiter, the picture is copied
untouched, and the sound is written like every other pass in the engine (AAC 256k, 48 kHz, stereo). The file it
was given stays as it was.

Three settings, each only when she asked for what it does:

| setting | what it does | without it |
|---|---|---|
| `--bed-db N` | sets the song's gain to exactly N dB (negative; lower sits further back). `MUSIC_BED_DB` in the environment does the same; the command line wins. | the gain is measured (below) |
| `--lift` | the song rises in her pauses and is back down before her next word, timed from the transcript beside the cut (`outputs/<job>.transcript.json`; `--transcript FILE` names another). With no transcript there, the bed stays level and the log says why. | the gain never moves |
| `--fade-in S` | the song rises from silence over the first S seconds | it starts at bed level on the first frame |

## 3 · The level

`bed-plan.py` measures the mean level of her cut and of the song, and gives the song the gain that puts its mean
`BED_DUCK_DB` under hers (`product/audio_levels.py`, the same rule the rendered route's bed uses). A loud song
and a quiet one land in the same place behind her, because the song's own level cancels out of the gain. The
last log line gives the gain and says whether it was measured, set by hand, or a fallback for a track that could
not be measured.

The bed holds that one gain because the engine's whole sound chain is static: the rough cut levels her voice with
one fixed gain and a limiter and never with anything that follows the level over time (CLAUDE.md: never
loudnorm). A bed that moved would undo that. So the lift and the fade-in stay hers to ask for, and even the lift
leaves the song untouched while she is talking.

If she hears the song as too present, or too faint, move the whole bed: `--bed-db` a few dB under or over the gain
the log printed. The lift is not a volume control.

## 4 · On to export

`<job>.bed.mp4` is now the newest pass in `outputs/`, so the export step (`scripts/name-final.sh <job>`) makes it
the reel to post. She hears it in her review; there is nothing to measure afterwards (CLAUDE.md rule 5).
