# 🎬 Setting up The Reels Editing Engine

**Open this folder in Claude Code and say "set me up."** That is the whole instruction. Claude walks the
steps below with you one at a time, runs the technical parts itself, and only stops when it needs a tap or a
password from you. This page is the same road written out, in the order "set me up" takes it, for when you
want to know what is happening or would rather do a step yourself.

What you get at the end: an engine that turns your footage into vertical reels in three formats.

- **Yap**: you on camera, talking. After your rough cut, the creative plan asks whether it is teaching or
  confessional, and the engine sets how many graphics it carries: teaching gets cards and cutaways, confessional
  stays close to bare.
- **Voiceover**: your voice over your own b-roll, cut to the rhythm of what you say.
- **Animation**: nothing filmed. Designed frames, moving type and motion graphics over your voiceover or
  music.

Each reel comes back as done as you ask for: an editable CapCut draft you finish yourself, or a finished
video ready to post. Mac and Windows both work.

---

## 0. Before anything installs: your computer, and where this folder sits

**Which computer.** "Set me up" checks this first, quietly. On a Mac nothing extra is needed. On Windows the
engine runs inside **Git Bash** (it comes with Git for Windows), never PowerShell and never WSL; "set me up"
makes sure you are in it before anything else, and when a command on this page says `python3`, Windows
types `python`.

**Where the folder sits.** Your footage, your drafts and your finished reels all live inside this folder, so
it needs a home that is not synced to the cloud. When a Mac's drive fills up, iCloud quietly moves big video
files off the computer: the file still shows in Finder, the engine cannot read it, and an edit stops partway.
On Windows, OneDrive does the same with Documents and Desktop. A plain **Projects** folder in your user
folder is the right home: `/Users/your-name/Projects` on a Mac, `C:\Users\your-name\Projects` on Windows.

*Checking a Mac:* **System Settings** → your name at the top → **iCloud** → **iCloud Drive**. If **"Desktop
& Documents Folders"** is on, keep the engine out of both.

> **Making that folder on Windows:** skip the **Home** item in File Explorer. It only shows pinned and recent
> files, and Windows will not let you make a folder there. Click the address bar, clear it, type
> `%USERPROFILE%` and press Enter: that is your real user folder, and **New folder** works there.

Already unzipped it somewhere synced? "Set me up" notices before it installs anything and offers to move the
folder for you. Saying **"move my engine"** does the same at any time later.

---

## 1. The tools

Every install starts from the engine's own checker. It changes nothing: it works out which computer it is
on, lists what is missing, and prints the exact line that installs each piece there. "Set me up" runs it,
installs what it flags, and runs it again until everything passes.

```bash
./check-setup.sh
```

### 1a. The base tools

Five pieces, each with one job in your reel:

| Tool | Its job in your reel | On a Mac |
|---|---|---|
| ffmpeg | cuts, joins and levels your footage and sound, and writes every video file | `brew install ffmpeg` |
| uv | builds the speech tools the rough cut uses to hear every word you say | `brew install uv` |
| Node | runs the graphics renderer behind cards, captions and Animation reels | `brew install node` |
| Python | runs most of the engine's own steps | `brew install python` |
| Pillow | draws caption and text images | `brew install pillow` |

On Windows the checker prints the Windows line for each one instead (a `winget` line for most). Windows asks "allow this app
to make changes?" for each install, and a newly installed tool shows up only after Git Bash is closed and
opened again.

On a Mac those lines need **Homebrew**, and installing Homebrew is the one step you do yourself: it asks for
your Mac password, typed into Terminal. It also needs an administrator account on the Mac. "Set me up" tells
you when it is time and gives you the line. Already have Homebrew? Skip it.

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**The render browser, once.** The graphics renderer draws in a browser of its own, fetched one time (about
150 MB):

```bash
npx hyperframes@0.9.6 browser ensure   # fetches it; later runs find it already there
npx hyperframes@0.9.6 doctor           # only reports on Node, memory and disk; downloads nothing
```

On Windows these are typed `npx.cmd`. The version number is fixed on purpose: the style packs and the
engine's render checks are tested against exactly that release, and moving to a newer one arrives as part
of an engine update, never in the middle of your reel.

### 1b. The editing engine (VectCut) — required for editable CapCut drafts

The Yap reel builds (`cleanyap.py` / `superyap.py`) assemble your **editable CapCut draft** through **VectCut**, a small local server at `product/engine/VectCutAPI/`. "Set me up" does this part for you. By hand it is one script, run once, on a Mac or in Git Bash on Windows:

```bash
bash product/engine/VectCutAPI/setup-editor-engine.sh
```

It builds the engine's own workspace (`venv-capcut/`) on a Python new enough for it (3.10 or newer; it
looks past the Mac's built-in 3.9 on its own), installs `requirements.txt` into it (never `pyproject.toml`,
and never `pip install pyJianYingDraft`: that ships inside the folder), and makes sure `config.json` points
the engine at your own computer (`http://localhost:9001`). The package already carries that `config.json`;
the script writes it only if it is missing and never overwrites yours. Anything already done is skipped, so
it is safe to run again.

Also needs **ffmpeg** (from 1a) and **CapCut 9.1.0+ opened once**, which creates its projects folder
(`~/Movies/CapCut/User Data/Projects/com.lveditor.draft/` on a Mac,
`%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft` on Windows). Use the desktop CapCut; on
Windows that means not the Microsoft Store one.

**Start it before you edit, and leave it running.** In `product/engine/VectCutAPI/`, double-click
**`start-editor.command`** on a Mac or **`start-editor.bat`** on Windows. It opens its own window: keep that
window open while you edit, and close it when you are done.

Confirm it's up: `curl -s http://localhost:9001/get_mask_types` should return JSON with `"success":true`.

> Full step-by-step + every gotcha: see the **VectCut Clean Install Guide + Holes Audit** (in the course docs). A finished video (rendered with HyperFrames and ffmpeg) needs **neither** VectCut nor CapCut: that is the route for watching a reel without CapCut.

### 1c. Apify, for Instagram research (recommended, and fine to do later)

Apify lets the engine read your own recent Instagram captions to learn how you sound (the next step uses
it), and pull an inspiration reel by its link to study how it was edited. It is a connector you add in
Claude once with `/mcp` (https://mcp.apify.com), signed in with your own free Apify account. Nothing to put
in a file, and no step here depends on it.

---

## 2. Your Homebase: make it sound and look like you

`brand-kit.md` is your Homebase: who your reels are for, how you talk, the rules your copy keeps, and the
names the transcriber tends to mishear. Say **"build my homebase"** and Claude interviews you one question
at a time and fills it in. Built one in another Startup Mom product already? **"Sync my homebase"** asks
whether this engine is for the same brand. Same brand, it pulls yours in and you only answer the reel-specific
questions. A different brand or client, this engine starts fresh.

The interview also has you pick a **style pack** (Butter, Editorial or Playful). The pack is your look: its
palette, and a font for each job on screen (captions, hook, takeover, thoughts). Those fonts come through
CapCut: each one downloads the first time CapCut uses it, so "not downloaded yet" on a fresh CapCut is a
normal one-time step. A few open-license faces ship in `assets/fonts/` for the rendered graphics to fall
back on (Inter, in the weights the packs use; Butter's thoughts fall back to Inter Bold).

Edited `brand-kit.md` by hand instead? Say **"update my homebase"** and Claude writes your answers into the places Part B of the file lists. The Homebase is strongly
recommended and never required: until it is filled in, Claude offers it at the start of each session, and
any reel you ask for still builds as soon as a style pack is picked.

---

## 3. Your first reel

1. **Film the first-reel script,** [`product/FIRST-REEL-SCRIPT.md`](product/FIRST-REEL-SCRIPT.md). It runs
   about 30 seconds, and every line in it names an effect, so the finished reel shows you the effects menu
   on your own face. Any short clip you already have works too.
2. **Drop the clip in `inbox/`** and say **"edit this reel."** It takes the newest clip there. For one
   somewhere else, name it: **"edit the clip called the-pricing-one.mov"**, or give its full path.
3. **The first rough cut sets up the speech tools,** once: about 3 GB on most computers (about 175 MB on an
   Intel Mac), so it needs internet and several minutes. Every reel after that starts straight away.
4. **Then the road every reel takes.** Claude copies the clip into its own job folder (your original stays
   where it was), cuts it, and shows you the style plan to approve. Two quick taps follow: teaching or
   confessional, and how done you want it (raw, medium, well-done or hands-off). Then the creative plan, one
   build, and your finish.
5. **Where it lands.** The cut is `projects/<job>/outputs/<job>.mp4`. On raw and medium your finish is the
   CapCut draft: polish it there and export. When the reel is done, `scripts/name-final.sh <job>` names the
   one you post `projects/<job>/outputs/<job>.final.mp4`.

**Export settings that keep it sharp:** 1080p, 30 fps, bit rate **Higher** in CapCut, and in Instagram turn
on **Upload at highest quality** (Settings › Data usage and media quality).

How the edit runs, phase by phase, is in `CLAUDE.md`.

**If anything goes wrong**, say **"/report-a-problem"**. It looks at what actually happened on your computer,
tries the engine's own fix first, and only then writes a report you can send.

---

## Your engine folder

Every effect and the words that ask for it: say **"library"**, or open
[`product/BUILD-VOCABULARY.md`](product/BUILD-VOCABULARY.md).

| Folder or file | What it holds |
|---|---|
| `inbox/` | clips you drop in for the next reel |
| `projects/<job>/` | one folder per reel: the footage copy, its cut, plans, graphics and outputs |
| `brand-kit.md` | your Homebase, the one file that is yours to fill in |
| `_local/` | what the engine has learned about you and your saved settings; updates never touch it |
| `CLAUDE.md` | how the engine edits: the formats, the phases and the rules |
| `.claude/skills/` | the skills that run each step, from "set me up" to the export |
| `product/` | the builders, the style packs and the effects library |
| `presets/` | the Clean Captions look, the fallback headline type and the transcriber's word corrections |
| `workflows/` | layout and safe zones for vertical reels, and the CapCut handoff |
| `assets/` | the bundled fonts, and your logos once you add them |
| `scripts/` | upkeep: naming the final export, freeing disk space, updates |
| `check-setup.sh` | the checker from step 1 |
| `CHANGELOG.md` | what each update changed (it appears with your first update) |
