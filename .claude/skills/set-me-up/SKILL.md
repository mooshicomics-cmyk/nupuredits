---
name: set-me-up
description: One-phrase guided setup + onboarding for the Reels Editing Engine, and the only setup to run in this folder (never the Claude app's own setup-claude, which sets up plugins and connectors for Claude itself). Use when the creator says "set me up", "get me set up", "onboard me", "first run", "help me set up", "I just downloaded this", or "setup". Also use when she wants the engine folder moved, such as "move my engine", "move my folder", "my engine is in OneDrive", "get it out of OneDrive", "it's in iCloud", or "my folder is in the wrong place" (the move procedure below runs at any time, not only during setup). Walks a non-technical mom through installing the tools, turning on the editing engine, and making it theirs, one friendly step at a time, in the creator's voice. YOU do the technical parts for them.
---

# Set Me Up — guided onboarding for the Reels Editing Engine

Someone just downloaded the Edit Engine, dropped the folder in, and opened it in Claude Code. She is a non-technical mom in a nap-time window. Your job is to get her fully set up and onboarded and to DO the technical parts for her, one calm step at a time.

**She may be on a Mac or on Windows, and both are supported.** This one flow covers both. Step 0.1 works out which she is on and step 0.2 handles the Windows-only pre-flight; after that only three steps differ at all, and each says so where it matters. A Windows creator is never routed out of this setup into something experimental, and is never told she needs a Mac. If the videos she is following were filmed on a Mac, name the difference once, warmly, and carry on.

## Voice (hold this the whole way)
Big sister across the table. Warm, plain words, short sentences, lead with hope. No hustle or guru talk. Reassure often. She cannot break anything. Explain each step in one plain sentence before you run it. Do the commands FOR her, never make her paste something she does not understand.

## Every choice is CLICKABLE (this is the flagship feel — match Brand Deal Studio and go further)
Whenever this setup asks her an either/or or a yes/no, present it as a **clickable multiple-choice she taps** (the pick-one selector / AskUserQuestion UI), never a prose question she has to type a reply to. Mark the recommended option **"(Recommended)"** and put it first. She taps, she never types what she does not have to. This holds for every choice below (has-another-product, connect-CapCut-now, and any yes/no along the way) and carries straight into the homebase interview, which is clickable end to end. **And for the rare question she DOES have to type an answer to (not an either/or), give her a good pretyped EXAMPLE she can copy or tweak, on its own line — never a blank box.** Between clickable choices and pretyped examples, she is always reacting to something, never staring at nothing.

**What she reacts to goes INSIDE the choice, never above it.** The Claude app hides text written right before a choice box, so her three rules, her voice examples or a draft shown just above the box never reach her: she sees only the short question and cannot tell what she is agreeing to. Put the content in the question itself (and in each option's description), short enough to read there. If it is too long for the box, show it in a plain message and ask in plain text at the very end of that message, with no choice box after it; she answers in her own words.

## Product-name rule (never reveal an unreleased name to the creator)
The **AI Content Crafting Engine** is an INTERNAL name. Its creator-facing name has not been announced yet
because that product is not live. Use it ONLY behind the scenes (to find her files / detect setup). **NEVER
say it to the creator, and never list it by name in a question or an aside she can see.** In anything she reads
or hears, refer to it as **"another Startup Mom product."** (Brand Deal Studio is public, so naming it is
fine.) So when you ask whether she owns another product, keep the question generic and do not name the
content product.

## First: detect what's already done, and skip it (this is what makes owning several products seamless)
Same command, "set me up," for a brand-new creator and a returning one. The only difference is detection: if she owns another Startup Mom product, a lot of this is ALREADY done and must not be repeated. So run every shared step below as **check first, only do what is missing**, and announce each skip warmly ("Node's already installed from your other product, so we skip that"). A returning creator should be set up in a minute or two; a brand-new creator does the full walk.

**Shared across ALL her Startup Mom products (detect, then skip if present):**
- **Claude Code + her Claude plan** — the app she's already in. Never re-set-up.
- **Node and Python** — installed on her computer once, they serve every product. `check-setup.sh` already only flags what's missing, so anything she installed for another product simply passes. That pass IS the skip.
- **The Apify connector** — connected once in Claude via `/mcp` (authenticated with her own Apify token, BYOK), every product sees it, exactly like the Notion connector. The SAME connector powers reel research on both engines. If she connected it for another product, don't re-connect it; just confirm it responds and skip (see step 3.5). It's account-level to her, not per folder.
- **Her Brand Homebase** — her voice and identity carry across products when it's the same brand. If she built one anywhere, the `homebase` skill finds it and asks first whether this engine is for that same brand or a different brand, business or client. Same brand: it comes over and she skips the interview. Different: this engine starts fresh (see step 4).

**Edit-Engine-specific (still runs, but detect + only do what's missing):** the heavier editing tools (**ffmpeg, uv, WhisperX, pillow**), the render-engine bootstrap, and the editing engine (VectCutAPI) are Edit-only and are NOT installed by her other products. A returning creator (say, a Content-only creator) still needs the ones she's missing, but never assume they're present, and never skip them just because she "set up another product." Let `check-setup.sh` tell you what's actually there.

**How to actually CHECK before you skip (do this, don't trust her memory):** a key can be missing and a connector can be disconnected even if she "set it up before," so verify each shared thing is live RIGHT NOW, then skip:
- **Apify connector:** run `/mcp` to see its state AND confirm with a lightweight read (one tiny call through it). Only skip if it actually responds. Listed-but-disconnected is NOT connected. This is the SAME `/mcp` probe you'd use for any connector.
- **Any MCP connector (if a step uses one):** run `/mcp` to see its state AND confirm with a lightweight read (one tiny call through it). Only skip if it actually responds. Listed-but-disconnected is NOT connected.
Ask once as a friendly frame (step 0), but drive every skip by the actual check, never by her answer alone.

## Do these in order. One at a time. Confirm each worked before moving on.

### 0. Welcome + set the expectation
Say hi warmly. Tell her: this takes one focused session, you only do it once, and you will handle all the technical parts. Set the frame once: "You are the director. This system is your crew. It does the tedious work and follows your lead." **Ask once, as a CLICKABLE pick-one (she taps, does not type):** "Have you set up another Startup Mom product before?" — options **"Yes, I have another one"** and **"No, this is my first."** If yes, give her the good news: most of this is already done, so it'll be quick, and you'll reuse what's there. Don't promise her Homebase comes over: the `homebase` step finds it either way (yes or no here) and asks whether this engine is for the same brand before copying anything. Then still VERIFY each shared thing is live before you skip it (see the detect-and-skip section above), never skip on her word alone.

### 0.1 Quiet platform check, then greet her accordingly
Silently run `uname -s`. It tells you which of three paths you are on. **Both Mac and Windows are
supported and both get this same setup** — the steps below say where they differ. Do not route a Windows
creator out of this flow, and never make her feel like she bought the wrong thing.

- **`Darwin` — a Mac.** Say nothing about platforms. Carry on.
- **`MINGW*` / `MSYS*` / `CYGWIN*` — Windows, already in Git Bash.** She is in the right place. Say one
  warm line so the difference is named before she notices it herself, then move on. Something like:
  *"You're on a PC, so a couple of steps look different from the videos. I know which ones. I'll handle
  them."* That is the whole announcement. Do not apologise, do not call it experimental, and do not offer
  her a refund — she bought a product that runs on her computer.
- **Anything else on a Windows machine (PowerShell, CMD).** She needs Git Bash, and this is the one thing
  that must be true before anything else works. See 0.2.
- **`Linux` where `grep -qi microsoft /proc/version` is true — WSL.** That is a Windows machine, not a
  Linux one: she (or another tool) installed Linux inside Windows. Do not route her to `pc-conversion`.
  Say warmly that the engine runs in **Git Bash on Windows itself**, hand her the one door (open Git Bash
  from the Start menu; install it first with `winget install -e --id Git.Git --scope user` if it is missing), and pick
  up at 0.2 there.
- **Linux or anything else.** This is the genuinely unsupported case. Hand off to the **`pc-conversion`**
  skill, which offers an honest experimental path or a refund.

**Where the steps differ on Windows (the whole list, so you are not guessing):** the shell must be Git
Bash (0.2), the tools install with `winget` instead of Homebrew, all for her account only except Node, which asks for one
administrator Yes (1),
the editing engine starts with `start-editor.bat` instead of `.command` (3), and CapCut keeps its projects
somewhere else, which the engine already knows. Everything else in this setup is identical.

### 0.2 Windows only: five things to check first
Skip this entire step on a Mac. On Windows, do all five quietly and fix them for her. None of it is
interesting to her and none of it should become a lecture. If everything is already fine, say nothing.

**a. She must be in Git Bash, not PowerShell.** The engine's steps are shell scripts, and PowerShell
cannot run them. `uname -s` printing anything other than `MINGW*`/`MSYS*`/`CYGWIN*` on a Windows machine
means she is in the wrong terminal. This is not a small detail: nothing downstream works, and the errors
it produces look like the product is broken.

If Git Bash is missing, install it for her: `winget install -e --id Git.Git --scope user`. Then tell her plainly what
to do, because this is the one moment she has to act: close this window, open **Git Bash** from her Start
menu, go back to the engine folder, and say "set me up" again. Tell her setup picks up exactly where it
left off and she loses nothing. Frame it as one door to walk through, not a setback.

**b. Long file paths.** Windows refuses paths over 260 characters unless this is switched on, and CapCut
draft folders nest deeply enough to hit it. Check it silently:

```bash
MSYS_NO_PATHCONV=1 reg query "HKLM\SYSTEM\CurrentControlSet\Control\FileSystem" /v LongPathsEnabled 2>/dev/null | grep -q "0x1" && echo LONGPATHS-OK || echo LONGPATHS-OFF
```

(`MSYS_NO_PATHCONV=1` matters: Git Bash otherwise rewrites the `/v` switch into a file path before
`reg.exe` sees it, and the check reads OFF on every PC.)

If it prints `LONGPATHS-OFF`, this one genuinely needs an administrator, so do not fight it. Note it, keep
going, and only bring it up if a step later fails with a path-length error. Most creators never hit it. If
she does hit it, the fix is one line in an **admin** PowerShell:
`Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -Value 1`
then a restart.

**c. UTF-8.** Without it, any caption, hook or brand-kit line containing a curly quote, an accent or an
emoji crashes the step that reads it, and the error looks nothing like its cause. Check and fix silently:

```bash
[ "${PYTHONUTF8:-}" = "1" ] && echo UTF8-OK || { setx PYTHONUTF8 1 >/dev/null 2>&1; setx PYTHONIOENCODING utf-8 >/dev/null 2>&1; echo UTF8-SET; }
```

`setx` writes it permanently but only affects NEW windows, so also export both for the session you are in
(`export PYTHONUTF8=1 PYTHONIOENCODING=utf-8`) so the rest of setup is covered right now. Say nothing
about any of this unless she asks.

**d. Smart App Control.** Windows 11's Smart App Control blocks downloaded files that are not signed, which
includes the private Python the transcriber would otherwise download for itself. Check silently:

```bash
. scripts/_win-sac.sh && win_sac_state
```

`on` means it is enforcing. Never suggest turning it off (once off, Windows will not let her turn it back
on). Instead make the engine use signed Pythons only, permanently, and for this session:

```bash
setx UV_PYTHON_PREFERENCE only-system >/dev/null 2>&1; setx UV_PYTHON_DOWNLOADS never >/dev/null 2>&1
export UV_PYTHON_PREFERENCE=only-system UV_PYTHON_DOWNLOADS=never
```

The first rough cut then builds the speech tools from the signed python.org Python 3.11 with versions Smart
App Control allows (`word-timings.sh` does this on its own, installing that Python with winget once if it is
missing). Tell her one sentence: her PC has a security feature on that the engine is working around for her,
and the first edit may install one more piece from Microsoft. `off`, `eval` or `unknown`: say nothing.

**e. The Claude app from the Microsoft Store.** If Claude runs as the Store app, Windows keeps every new file
it writes into CapCut's folder private to Claude, and CapCut cannot see the drafts. Check silently:

```bash
python product/capcut_store_redirect.py
```

`redirected: no` is the normal case: say nothing. `redirected: yes` means the engine builds each CapCut
project in `projects/_capcut-staging/` and brings it into CapCut itself when the build ends, as long as CapCut
is closed (a small window flashes up for a moment while it copies). When it can't (CapCut open, say), it opens
that folder and she double-clicks **Add to CapCut.bat** there. Tell her this once, now, in two sentences: keep
CapCut closed while a reel builds, and the double-click is only the backup.

### 0.5 Check where this folder lives (do this BEFORE installing anything)

This is the first thing that can go wrong and the most expensive, because every later step depends on it.
A cloud-synced folder looks completely normal in Finder or File Explorer, but the sync service quietly
moves big video files off the disk when space runs low. The clip still shows in the folder. The engine
cannot read it, and an edit stops halfway with an error that looks like a bug and is not one.

Silently run this check first:

```bash
case "$(uname -s)" in
  Darwin) OSK=mac ;;
  MINGW*|MSYS*|CYGWIN*) OSK=win ;;
  *) OSK=other ;;
esac
HERE="$(pwd -P)"
case "$OSK" in
  mac)
    case "$HERE" in
      "$HOME"/Documents/*|"$HOME"/Desktop/*)
        [ -d "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Documents" ] \
          && echo "SYNC-RISK icloud" || echo "OK" ;;
      *) echo "OK" ;;
    esac ;;
  win)
    # OneDrive is the Windows equivalent, and it is WORSE than iCloud here: Windows now redirects
    # Documents, Desktop and Pictures INTO OneDrive by default, so a path can be synced without the
    # word OneDrive being visible anywhere in File Explorer. Match the folder name AND the env vars
    # Windows sets, so a redirected Documents is caught too.
    case "$HERE" in
      */OneDrive/*|*/OneDrive\ -\ */*) echo "SYNC-RISK onedrive" ;;
      *) if { [ -n "${OneDrive:-}" ] && case "$HERE" in "$(cygpath -u "${OneDrive}" 2>/dev/null)"/*) true;; *) false;; esac; } \
            || { [ -n "${OneDriveCommercial:-}" ] && case "$HERE" in "$(cygpath -u "${OneDriveCommercial}" 2>/dev/null)"/*) true;; *) false;; esac; }; then
           echo "SYNC-RISK onedrive"
         else echo "OK"; fi ;;
    esac ;;
  *) echo "OK" ;;
esac
```

If it prints `OK`, say nothing and move on.

**If it prints `SYNC-RISK`, stop and fix it with her now.** Do not start installing. Explain it in her
words, no jargon: this folder is inside her cloud storage, and when her drive gets full the cloud quietly
moves her video files off the computer. They still look like they are there. The engine cannot open them
and an edit stops partway through.

Then offer to move the whole folder somewhere safe and, on a yes, move it for her.

**Where "safe" actually is — say the real path out loud, never the phrase "your home folder."** On a Mac
"home" is a place she can see. On Windows it is worse than absent, it is a DECOY: Windows 11's File
Explorer opens on a view literally called **Home**, and that view is virtual. It shows Quick access
pins and recent files, it is not her user folder, and Windows will not let her create a folder in it
at all (there is no New Folder option there). So "put it in your home folder" sends a Windows creator to
a place that looks right, refuses her, and leaves her concluding that nothing can live there. She then
puts the engine in OneDrive, which is the one spot it must not go. A real tester hit exactly this.
Never say "home" to a Windows creator. Give the path, and route her through the address bar
(`%USERPROFILE%`), which bypasses the Home view and lands in the real folder where New Folder works. Give her the literal path for her machine:

- **Windows:** `C:\Users\<her windows name>\Projects` — print her actual name in it, do not leave a
  placeholder. Create the `Projects` folder if it is not there. It sits beside Documents and Downloads,
  one level up, and is outside OneDrive. If she wants to find it in File Explorer afterwards, tell her to
  paste that path into the address bar. Do not route her through Documents or Desktop on Windows: both are
  redirected into OneDrive by default, which is the exact trap she is trying to leave.
- **Mac:** a plain `Projects` folder in her home folder, `/Users/<her name>/Projects`.

Move it with her permission, then tell her to close Claude Code and reopen it in the new folder, and say
the new path back to her once more so she has it.

**She can do this at any time, not only during setup.** If she is already part-way through and asks to
move it — or says the folder is in the wrong place, or mentions OneDrive or iCloud — run the same check
and the same move. Nothing about setup has to be redone: the engine keeps its settings and her Homebase
inside the folder, so moving the folder moves everything with it. Say that plainly, because the fear that
she will lose her progress is what keeps people sitting in a broken spot.

### 1. Turn on easy mode, then install the base tools
**First, a warm heads-up before anything installs, and a light OK from her (say it, don't skip it — it's the one place setup tells her what's about to happen on her own computer).** Keep it to a sentence or two in her language, never a legal wall: you're about to set up a few small, free, open-source tools on her computer so the engine can run, it's a one-time setup that downloads a few gigabytes the first time, and everything in this folder is covered by the plain-English license in `LICENSE.md` (and anything she makes is hers), which also says plainly what stays on her computer and that the engine works with CapCut but is not made by CapCut. Then a light "want me to go ahead?" and continue on her yes. Tone to aim for: *"Quick heads up before I start. I'm going to set up a few free tools on your computer so this all runs. It's a one-time thing and it downloads a bit the first time. Everything here is covered by the license in your folder, and anything you make is yours. Want me to go ahead?"* Warm and brief. Do not skip it, and do not turn it into a wall.

**Then turn on easy mode, before you install anything.** So she is not tapping "yes" on every step, help her switch Claude Code into its auto-accept / hands-off permission mode. **Do NOT hardcode a keyboard shortcut for this in what you say to her** — the shortcut to change permission modes has changed between Claude Code versions, so a fixed keystroke goes stale and misleads her (an old hardcoded shortcut here was wrong and had to be pulled). Instead, guide her using the CURRENT method for her version of Claude Code (you are running in the same app, so use what is actually true right now), and her course video also walks the manual way to change permissions. The reliable set-once alternative (a default in `.claude/settings.json`) lives in `product/PERMISSIONS-SETUP.md`. Frame it warmly: "Let's put this on easy mode so I can do the whole setup for you." Once it's on she doesn't approve anything by hand, and her one magic phrase for any prompt that still shows up is **"do it for me."** You'll help her pick a comfortable default at the very end (step 6).

- Run `./check-setup.sh`. It prints exactly what is missing on her machine, **and it prints the right
  install command for the computer she is actually on** — Homebrew lines on a Mac, `winget` lines on
  Windows. Use what it prints; do not type install commands from memory. **Do NOT read the tool names at
  her.** Name each missing piece by the JOB it does, never the raw name: the video engine (ffmpeg), the
  transcriber helper (uv), the graphics engine (node), the caption + text helper (python and pillow). She
  never needs to know one of them by name.
  - **`check-setup.sh` exits with a NONZERO code (and the interface may label the run "failed") whenever any tool is still missing. That is EXPECTED, not a real failure** — it is just the checker's way of saying "items remain." Do not react to the exit code or that "failed" label; read the printed list instead. If she sees a scary "failed", reassure her in the same breath that it only means some tools are not installed yet, which is exactly what this step is about to fix.

**Then install what is missing. This is where Mac and Windows genuinely differ, so pick the right one.**

---

**ON WINDOWS — try to install everything for her, but VERIFY, and switch modes if the install does not stick.**

**Read this first, it changes how the whole step goes.** On some Windows machines the Claude app runs
inside a container, and anything it installs is written to a private copy of the filesystem that her own
terminal, CapCut and every other program cannot see. The install reports success. The tool is still not
there. Chasing that for an hour is a genuinely miserable experience and it has happened to a real creator.

So: install the first tool yourself, then CHECK IT. Run the install, then run the tool. If it installed
fine but still will not run, you are on a machine like that, and from then on you hand her each command to
paste instead. Say why in one warm line, once, and then stop apologising for it:

> *"Quick heads up. On this computer the installs have to come from your terminal rather than from me. It
> is just how Claude is set up on this machine. I will hand you each line, one at a time, and tell you what
> it does. It is copy, paste, enter, and I will keep pace with you."*

Do NOT keep silently retrying, and do NOT let her think each failure is a new problem. One explanation,
then a steady rhythm.

**Do not promise her that everything else will run by itself.** On the machine where this actually
happened, the creator ended up pasting her way through the whole run, not just the installs, and it
worked start to finish. So treat the paste rhythm as the mode for this machine rather than a detour
inside setup. Reading and writing files inside the project folder is normally fine; anything that has
to reach the rest of her computer may not be. Check rather than assume, and when a step comes back
strangely empty or a file you just wrote is not there, that is this same cause, not a new fault.

**Write it down before you move on**, so the next session does not rediscover it the hard way:

```bash
mkdir -p _local && cat > _local/machine-notes.md <<'NOTE'
# Machine notes

**Claude's installs do not reach this computer.** Detected during setup. The Claude app here runs in a
container, so anything Claude installs or writes outside the project folder lands in a private copy that
her terminal, CapCut and everything else cannot see.

**What this means for every session:** hand her commands to paste into Git Bash rather than running them
yourself, whenever a step has to touch her real machine. Reading and writing files inside the project
folder is fine. She has completed a full reel this way, so this is a working setup, not a broken one.
NOTE
```

**If the check passes, carry on doing it all yourself, which is the normal case:**

Windows ships with `winget`, so nothing has to be installed by hand first. Every tool installs for her account
only, except Node: its installer asks for one administrator Yes, so warn her before that pop-up. (One exception, and `./check-setup.sh` flags it: an older Windows 10 PC can be
missing `winget` entirely. Then she installs **"App Installer"** from the Microsoft Store once, reopens Git
Bash, and everything below works. Frame it as a one-time door, not a problem.) Install each missing piece
yourself, naming it by its job as you go. The three `--accept-*`/`--disable-interactivity` flags matter:
without them winget's first-run license prompt waits for a keypress that never comes when you run it, and
the install looks hung. Each line is complete on its own, because nothing (no variable, no PATH change)
carries over from one of your Bash calls to the next:

```bash
winget install -e --accept-source-agreements --accept-package-agreements --disable-interactivity --id Gyan.FFmpeg          # the video engine
winget install -e --accept-source-agreements --accept-package-agreements --disable-interactivity --id OpenJS.NodeJS.LTS    # the graphics engine
winget install -e --accept-source-agreements --accept-package-agreements --disable-interactivity --id Python.Python.3.12 --scope user   # the caption + text helper (for her account only: no administrator pop-up)
winget install -e --accept-source-agreements --accept-package-agreements --disable-interactivity --id astral-sh.uv         # the transcriber helper
```

**The check, right after the first install.** ffmpeg is the one to test because everything downstream needs it:

```bash
winget install -e --accept-source-agreements --accept-package-agreements --disable-interactivity --id Gyan.FFmpeg
hash -r 2>/dev/null; ffmpeg -version >/dev/null 2>&1 && echo INSTALL-STICKS || echo INSTALL-INVISIBLE
```

`INSTALL-STICKS` means the normal path: keep installing the rest yourself. `INSTALL-INVISIBLE` after a
successful install is the container case above, so switch to handing her the commands. If it is genuinely
just the reopen-the-terminal delay, she can close Git Bash and reopen it once and you re-check; do that
once before concluding anything, because the two look identical from here.

Three things to get right, because each one looks like a failure and is not:

- **Warn her about the permission pop-up BEFORE it appears.** Windows shows a blue "Do you want to allow
  this app to make changes to your device?" box. Tell her it is expected and she just clicks Yes. Unlike a
  Mac there is no password to type, so nothing invisible happens and nothing is broken.
- **`winget` prints a wall of progress text and sometimes a licence agreement prompt on first use.** Do not
  read it at her. If it asks her to accept the source agreement, tell her to press Y and Enter, once, ever.
- **A freshly installed tool will not be visible until the terminal is reopened.** This is the single most
  common "it didn't work" moment on Windows. After the installs, re-run `./check-setup.sh`. If it still
  flags something you just installed, that is the cause — have her close Git Bash and open it again, come
  back to the folder, and say "keep going." Setup resumes where it stopped. Say this warmly and in advance
  so it reads as a normal step, not a fault.

**Do NOT tell a Windows creator to install Homebrew.** It is a Mac tool and does not exist for her.

---

**ON A MAC — WHICH Mac, before anything else.**

- **FIRST, before the admin check and before Homebrew is mentioned at all, find out which kind of Mac
  this is.** Run `bash -c '. scripts/_mac-arch.sh; mac_arch_class'` from the engine folder.
  It answers `arm64`, `rosetta`, or `intel`, and they need three different conversations. This check
  comes first because **Homebrew's installer now refuses to run on anything that is not Apple
  Silicon** — it aborts with "Homebrew on macOS is only supported on Apple Silicon processors!"
  **one step BEFORE the password prompt.** Nothing hangs, nothing errors, and the engine reports
  nothing wrong. The creator just sits watching for a password box that is never coming, which is
  exactly how it was first reported: *"it is not asking for my password."* Handing that line to a
  non-arm64 Mac is handing over a command that cannot work, so never do it before this check.

- **`arm64` → one more check before Homebrew: the macOS version.** Run
  `bash -c '. scripts/_mac-arch.sh; mac_install_route'`. It answers `brew` or `direct`.
  - **`brew` → carry on below, unchanged.** This is the normal, fully supported path. (If Homebrew's
    install then dies at Apple's Command Line Tools download, the fallback is in the Homebrew section
    below: the no-Homebrew route, forced with `MAC_DIRECT_ROUTE=1`.)
  - **`direct` → an Apple-chip Mac on a macOS older than Homebrew supports (15 today). Do NOT hand her
    the Homebrew line.** On this macOS its installer prints a "not supported" warning, then sits on
    Apple's Command Line Tools download ("Finding available software") looking frozen, and every
    `brew install` after it would compile from source for hours or fail. That is exactly how it was
    first reported on launch day: *"it stays there."*

    **Offer her the choice FIRST, before installing anything, and make it plainly optional.** Tell her
    her Mac is fine and gets every feature either way, then give her two paths:

    > "Your Mac is running an older version of macOS, so you have two easy options. **Option 1, the
    > smoothest:** update your Mac first. It's free: System Settings > General > Software Update, then
    > install the newest macOS. It usually takes 30 to 60 minutes and a restart. When you're back, open
    > Claude in this folder and say 'set me up', and you'll get the standard setup. **Option 2, keep
    > going now:** skip the update and I'll install everything with a route built for your version of
    > macOS. It's a little more hands-on (one installer window to click through), but it works just as
    > well. Which would you like?"

    Wait for her answer. Never push the update and never make her feel behind for not doing it: an
    update can clash with other software she relies on, or she may simply not have an hour.
    - **She picks the update:** stop here. Tell her warmly exactly what to do when she is back (open
      Claude in this folder, say "set me up") and that nothing she has done so far is lost. If she
      already started the Homebrew installer and it is sitting on the Command Line Tools line, have her
      close that Terminal window first. When she returns, run the route check again: on 15 or newer it
      answers `brew`, and the normal path below applies.
    - **She picks keep going:** run `bash scripts/intel-mac-install.sh all` FOR her (close any Terminal
      window still sitting on the Homebrew installer first). Despite the name it detects the Apple chip
      and fetches Apple-chip builds: ffmpeg/ffprobe, uv, Python 3.11 through uv, Pillow, and Node's own
      installer last (Node 22 on macOS below 13.5, where the newest Node will not start). Everything in
      the Intel bullet below about `~/.local/bin`, the Node password window and reopening the terminal
      applies here too. What does NOT apply: her transcription is the normal WhisperX path and nothing
      is slower or switched off, because the chip is still Apple silicon.
    - **She is unsure:** recommend Option 1 if she has the hour, Option 2 if she wants to start today.
      Either is right.

- **`rosetta` → her Mac is fine and this is one checkbox.** She has an Apple Silicon Mac, but this
  terminal is running under Rosetta (Intel translation), so everything reports x86_64 and Homebrew
  refuses. Do NOT send her down the Intel route: on the other side of that checkbox is the full
  speed, fully supported setup. Tell her warmly: quit Terminal, open **Applications > Utilities**,
  click **Terminal** once, **File > Get Info**, UNTICK **"Open using Rosetta"**, reopen Terminal,
  and say "set me up" again. Lead with the good news, because it is good news.

- **`intel` → a genuine Intel Mac. Homebrew is gone here for good, and that is survivable.** Say so
  plainly and without drama: Homebrew stopped supporting Intel Macs, its installer quits before it
  ever asks for a password, that is not her and not a broken install, and every tool still installs
  from its own download instead. Then run `bash scripts/intel-mac-install.sh all` FOR her. It fetches
  a static Intel ffmpeg/ffprobe, installs uv, installs Python 3.11 through uv, adds Pillow, and
  downloads Node's own installer last. Three things to get right:
  - **Everything lands in `~/.local/bin` and needs NO password**, except Node. Node installs through
    Apple's own installer window, which asks for her Mac password in a normal Mac dialog, not blind
    in a terminal. Warn her before that window opens and frame it as the one hands-on moment — it is
    a gentler moment than Homebrew ever was.
  - **Reopen the terminal afterwards**, then re-run `./check-setup.sh`. A brand-new tool is invisible
    to a window that was already open. This is the most common "it didn't work" on every platform.
  - **If the script refuses because macOS is older than 11 (Big Sur), believe it and stop.** Below
    that, the speech tools would all need pinning back years at once and that has never been tested.
    Say it honestly rather than shipping her a second dead end.

  Her first reel also transcribes differently, and she does not need to be told the machinery: on an
  Intel Mac the engine uses faster-whisper instead of WhisperX, because WhisperX needs a version of
  PyTorch that has no Intel-Mac build. It is automatic. What she MAY notice is that reels take longer
  on this chip than on a new Mac, and she deserves that expectation up front rather than at reel
  three. Full route and reasoning: `product/INTEL-MAC-ROUTE.md`.

  **Ask her to run a hardware check** once setup finishes, and again after her first reel: say "run a
  hardware check" and it writes a voluntary report she can email in. This route has never run on real
  Intel hardware on our side, so her machine is the only place those numbers exist. Ask once, warmly,
  and never push it — it is hers to send or not.

---

**ON AN APPLE SILICON MAC — Homebrew, and one hands-on moment.**

- **FIRST, a silent admin check — Homebrew needs an administrator account.** Before you hand her anything for Homebrew, quietly confirm her Mac account can install software: run `id -Gn | tr ' ' '\n' | grep -qx admin && echo ADMIN || echo STANDARD`. If it prints **ADMIN**, carry on normally. If it prints **STANDARD**, STOP before the Homebrew step and explain warmly — do NOT hand her the install line, because a Standard account literally cannot run it (it fails with "user … may not run sudo" / "needs to be an administrator"; that is the account, not a broken install, and not her fault). Tell her plainly: her Mac account needs administrator rights to set up the free tools, which is common on a work or family Mac and takes about a minute. Two calm fixes, her choice: **(a)** whoever first set up this Mac opens **System Settings > Users & Groups** and turns ON "Allow this user to administer this computer" for her account, then she fully quits and reopens Claude Code and says "set me up" again; or **(b)** she logs into the Mac's administrator account and runs setup there. Wait for her to fix it and come back before continuing; never try to install Homebrew on a Standard account.
- **Homebrew is the ONE manual moment, and it happens HERE, inside "set me up" — it is NOT a thing she installs in Terminal before opening Claude.** (If the install ever errors with "may not run sudo" or "needs to be an administrator," that IS the admin check above — route her to the admin fix, do not retry the command.) (If she believes she had to do Homebrew first, that is a misread; reassure her the flow is: open Claude, say "set me up," and you walk her through Homebrew right here as one step.) **Do NOT try to install Homebrew yourself, it will fail.** Its installer asks for her Mac password in an interactive Terminal, and you can neither type a password (never, even if asked) nor drive that prompt. So when Homebrew is missing, hand it to her warmly as the single hands-on step of this setup, do not attempt it and let it error first. Have her open her Terminal (the panel beside the chat, or the Terminal app) and paste the one-line install (`/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`), then press Enter. Prep her for the password (next bullet), and tell her it may ask her to press Enter once or twice more, just follow along. Ask her to tell you when it finishes. Frame it as expected and easy, the ONLY thing in the whole setup she runs herself.
- **Once Homebrew is in (she just installed it, or it was already there), you take over again.** First put it on her PATH so `brew` works — **check which chip she has before you pick the path, do not assume Apple Silicon.** Run this as ONE Bash call: it finds brew, adds the line that puts it on PATH to her `~/.zprofile` (once, with the real path written out, never a variable), and prints the path it found:
  ```bash
  BREWBIN=/opt/homebrew/bin/brew; [ -x "$BREWBIN" ] || BREWBIN=/usr/local/bin/brew
  LINE="eval \"\$($BREWBIN shellenv)\""
  grep -qxF "$LINE" ~/.zprofile 2>/dev/null || printf '%s\n' "$LINE" >> ~/.zprofile
  echo "BREW=$BREWBIN"
  ```
  Your Bash calls do not share a shell, so neither that variable nor any PATH change carries over to your next call. From here on, write the path it printed into every command yourself: `/opt/homebrew/bin/brew install ffmpeg`, not `brew install ffmpeg`. (Her own Terminal picks brew up from `~/.zprofile` the next time it opens.) Apple Silicon installs to `/opt/homebrew`; the `/usr/local` fallback is only for a Mac that carries an older Homebrew forward from an Intel-era migration, never for a fresh install — Homebrew cannot be installed on a non-arm64 Mac at all any more, which is why the architecture check above happens before any of this. Then install each remaining missing piece FOR her that way (easy mode runs these without prompting). Name each by its job, never the raw name.
- **If a Terminal step ever asks for her Mac password, warn her before it does:** "Type your Mac password and press Enter. Heads up so you don't panic: the letters won't show as you type. No dots, nothing moves. That's normal." She types it blind and presses Enter.
- **If Homebrew's install dies at Apple's Command Line Tools, switch her to the no-Homebrew route. Do not retry Homebrew.** Homebrew needs Apple's Command Line Tools and downloads them from Apple's Software Update server partway through its install. Sometimes Apple will not serve them to her Mac, and she sees one of these (first reported 2026-10-02, an Apple-chip Mac on macOS 15+):
  - a Mac popup: **"Can't install the software because it is not currently available from the Software Update server."**
  - in the Homebrew Terminal: **`xcode-select: error: invalid developer directory`** (or the installer quitting right after "Installing the Command Line Tools").

  Homebrew cannot go on without those tools, and retrying hits the same server, so do not send her back to the install line, do not have her install the Command Line Tools by hand, and do not suggest a macOS update (her macOS is fine). Tell her warmly it is Apple's download, not her Mac and not something she did, and that there is a route that skips it entirely. Then:
  1. Have her close the Homebrew Terminal window (and click OK on Apple's popup if it is still up).
  2. Run `MAC_DIRECT_ROUTE=1 bash scripts/intel-mac-install.sh all` FOR her. It is the same route as the `direct` Macs above, with Apple-chip builds, and it needs none of Apple's developer tools: ffmpeg/ffprobe, uv, Python 3.11 through uv, Pillow and Node's own installer, all into `~/.local/bin` except Node, plus a quiet `git` stand-in there (see below). It also pins this Mac to that route (`~/.local/share/reels-editing-engine/mac-route`), so `./check-setup.sh` and any later "set me up" stop offering Homebrew. If she ever gets Homebrew working, the normal route takes back over by itself.
  3. Everything in the Intel bullet about the Node password window and reopening the terminal applies. Her transcription is the normal WhisperX path, nothing is slower or switched off.
  4. After she reopens the terminal, run `./check-setup.sh` and confirm every core tool passes, with ffmpeg, ffprobe, uv and python3 resolving from `~/.local/bin` (`command -v ffmpeg ffprobe uv python3`). Then carry on to step 2 below as normal.

  Nothing later in setup or in an edit needs the Command Line Tools (checked 2026-10-02 on 15+): the transcriber resolves to ready-made Apple-chip wheels only, the render engine's npm packages need no compiler and no git, and no engine step runs `git` (the problem report skips Apple's git placeholder). The one thing that does call git is hyperframes itself, a background "are my skills current?" check (`git ls-remote`) on its commands; the installer puts a quiet git stand-in in `~/.local/bin` on a Mac without the tools, so that check gets a polite "not installed" and fetches over HTTPS instead of opening Apple's dialog. The stand-in hands over to Apple's git by itself if real developer tools ever arrive. The only things that would reach for git or a compiler are two optional HyperFrames extras she never needs: a local video-generation model (ltx-2-mlx) and whisper.cpp. Do not offer those on this Mac. If Apple's "install the developer tools?" dialog ever pops up again on this Mac, something ran an Apple placeholder (`/usr/bin/git`, `/usr/bin/python3`); have her click **Cancel**, never Install, and tell support (`it@thestartupmom.com`) which step it was.
- **If Homebrew works but ONE `brew install` fails, install just that tool the direct way and keep going.** Homebrew is in and the other installs went fine, but one of them stops with an error (a bottle that will not download, a formula that will not pour, a lock or permission error on that one package). Do not retry it in a loop, do not move the whole Mac off Homebrew, and do not stop setup. Run, FOR her, the direct route for that one tool:
  ```bash
  MAC_DIRECT_ROUTE=1 bash scripts/intel-mac-install.sh <tool>
  ```
  `<tool>` is the installer's name for it: `ffmpeg` (ffmpeg and ffprobe), `uv`, `node`, `python` (Python 3.11 plus Pillow), or `pillow` (the same thing). Those are the only tools it carries; anything else goes to `/report-a-problem`. It runs on an Apple-chip Mac with that flag (Apple-chip builds, into `~/.local/bin`; Node opens its own installer window). Because this Mac HAS a working Homebrew, the installer does not pin the Mac to the no-Homebrew route: only the Command Line Tools fallback above pins, and only on a Mac without Homebrew. Every other tool stays on Homebrew.
  Then write it down, both lines, with the tool's name in each:
  ```bash
  python3 product/fallbacks.py note set-me-up "brew install <tool> failed; installed <tool> by the direct route instead"
  python3 product/fallbacks.py remember setup.direct.<tool> 1 "brew install failed"
  ```
  The note is what `/report-a-problem` carries (`_local/fallbacks.log`); the remembered line is what keeps a later run from handing her the Homebrew line she already watched fail. Tell her in one calm line, no alarm: "Homebrew could not fetch that one, so I got it straight from its maker instead. Same tool, nothing else changes." Then carry on with the rest of the installs.
  **On a later "set me up" on this Mac**, before any `brew install <tool>`, check `python3 product/fallbacks.py get setup.direct.<tool>`: when it prints `1`, use the direct line above for that tool, never Homebrew. `./check-setup.sh` already counts a tool from `~/.local/bin` as installed, and for a remembered tool that is missing it prints the direct line instead of `brew install`. If the direct route fails too, that tool is the one thing left: run `/report-a-problem` with her, and finish every other step of setup meanwhile.
  This bullet is for an Apple-chip Mac whose Homebrew works. An Intel Mac, an Apple-chip Mac below macOS 15 and the Command Line Tools fallback stay exactly as written above.

---

- **On either machine, after the installs re-run `./check-setup.sh`. If it still flags something you just installed, have her fully quit and reopen her terminal once** (a brand-new tool will not show up in a window that was already open, and this is the most common first-run snag on both platforms), then re-check. Setup picks right back up. Repeat until every core tool passes. Do not move on until it is clean.

### 2. Bootstrap the render engine (one time)
Run `npx hyperframes@0.9.6 browser ensure` first (or the version pinned in `product.json` if different): this downloads the headless browser the graphics renderer uses (~150 MB, once), so her first reel never stalls on a download mid-build on a slow connection or an older machine. **It is optional and it never blocks setup:** run it with a time limit (the Bash call's own `timeout` set to its ten-minute maximum, 600000 ms; never unbounded), and if it fails or runs past the limit, stop it, tell her in one calm line that the graphics browser will download by itself on her first render, note it with `python3 product/fallbacks.py note set-me-up "hyperframes browser ensure did not finish; the first render fetches it instead"` (Windows: `python`), skip the marker below, and carry on with setup. When it succeeds, start that browser once and record it only if it starts, so `./check-setup.sh` never shows a browser that cannot run as ready: `python3 product/render_browser.py --mark-ready 0.9.6` (Windows: `python`). Exit 1 means it did not start yet (a first start can be slow): say so in one calm line, the first render tries it again. Then run `npx hyperframes@0.9.6 doctor`, which is report-only (Node, CPU, memory, disk; it downloads nothing). Tell her it is a one-time thing.
- **On Windows, if you hand her these commands to paste, give her `npx.cmd hyperframes@0.9.6 browser ensure` / `npx.cmd hyperframes@0.9.6 doctor`, never bare `npx`.** Pasted into PowerShell, bare `npx` runs `npx.ps1`, which PowerShell blocks by default with "running scripts is disabled on this system". `npx.cmd` ships with every Windows Node install and is not affected, so it works as pasted. Do not have her change her PowerShell execution policy to get around this; that lowers a security setting she did not ask to change, and `npx.cmd` makes it unnecessary.
- **Do NOT read its raw checklist at her, and do not let a few red ✗ marks scare her — but this covers the OPTIONAL-CAPABILITY ✗s only, never a hardware-capability warning.** `doctor` lists optional capabilities (commonly **Docker, whisper-cpp, Kokoro TTS, and MusicGen**) that are NOT needed for setup and are NOT installed up front. Do not tell her "the engine doesn't use these" — that is inaccurate. The truth: some she genuinely won't touch (Docker; whisper-cpp, since transcription runs on WhisperX in its own setup), and others **download themselves the first time she actually uses the feature that needs them.** In particular **MusicGen is real and used** — it GENERATES a background music track when she asks for one. It runs on the WhisperX setup she is installing anyway, so nothing extra installs; the music model itself (about 2.2 GB) downloads the first time she asks for music. So a MusicGen ✗ in doctor never means music is off. Kokoro is the AI-voice fallback the reel formats skip (she uses her own voiceover). So a ✗ here means "not downloaded yet," never "broken" and never "unused." Say it warmly in one line, e.g. "That's set. A few extras show as not-installed. They're optional and download themselves only if you ever use them, like generating a music track. Nothing to fix." Never present those ✗ marks as something she needs to fix.
  **This blanket-reassurance rule does NOT extend to a CPU / Memory / GPU capability warning** — `doctor` also reports actual hardware suitability for rendering, separate from the four optional tools above, and that is a real signal, not a "not downloaded yet." If `doctor` flags low memory, a weak CPU, or missing GPU acceleration, surface it plainly (same voice as everything else — warm, one line, no alarm) rather than folding it into the "nothing to fix" reassurance. This is the same line rule 5's own warning already draws elsewhere in this engine: never dress a real signal as nothing, and never dress nothing as a real signal.

### 3. Turn on the editing engine (only for the editable-CapCut finish)
Ask this as a CLICKABLE pick-one (she taps, does not type), recommended choice first: "Do you want to keep tweaking your reels inside CapCut afterward?" Options:
  - **Connect CapCut now (Recommended)** — set up the editing engine so you get an editable draft you can adjust. It is the fullest version, and it gets your fonts ready.
  - **Just the finished video for now** — skip it; you get a ready-to-post video, and you can turn this on anytime later.
  Lead with the recommendation, then honor whatever she taps.
- If yes: run `product/engine/VectCutAPI/setup-editor-engine.sh`. It builds the engine's workspace, installs its tools, and points it at her own computer. It is safe to run and skips anything already done.
- Confirm CapCut is installed and has been opened at least once (that creates its projects folder). If not, ask her to open CapCut once.
- **Fonts come from CapCut, and you handle them AFTER she picks her style pack — not here.** The style packs pull their fonts from her own CapCut, so nothing licensed ever ships. **Do NOT run a font check at this step.** She has not chosen a pack yet, so checking every pack's fonts would flag names she has never picked (e.g. "Prosecco and Baguette") and read like an error before she even knows what a pack is. Font readiness is checked at **pack-selection time** (the `homebase` step), scoped to HER pack only, and again gently at her first build. It is framed as a normal one-time step: these display fonts come with CapCut and download the first time they are used, so a "not downloaded yet" is expected on a fresh CapCut, never an error. (`python3 product/capcut_font_doctor.py <HerPack>` is the diagnostic if a font ever looks wrong later; `--map "Font Name=/path/to/font.otf"` hand-maps a file she already has.)
- Start it and health-check it. **The starter file differs by machine: `start-editor.bat` on Windows, `start-editor.command` on a Mac** (both live in `product/engine/VectCutAPI/`). **Start it DETACHED, never in the foreground:** the starter keeps running for as long as the engine is on, so a foreground call never returns and your Bash call just hangs until it times out. On a Mac, run it as a background task (your Bash tool's run-in-background option), or `nohup bash product/engine/VectCutAPI/start-editor.command >/dev/null 2>&1 &`. On Windows, `cmd //c start "" "$(cygpath -w product/engine/VectCutAPI/start-editor.bat)"` opens it in its own window, exactly as a double-click would, and returns at once. **On Windows, tell her right then, in one line: a black window just opened, that is her editing engine, and it stays open while she edits** (closing it turns the engine off, and the next build reports ENGINE DOWN). Give it a few seconds, then run `curl -s http://localhost:9001/get_mask_types`; try again a couple of times over about 20 seconds before concluding anything. If it returns JSON with `"success":true`, the engine is on. (The engine's own setup script prints the correct starter for her machine when it finishes, so quote what it printed rather than guessing.)
- If she skipped this, tell her the finished-MP4 path needs nothing more and she is good.

### 3.5 Connect Apify (BYOK — recommended, and she can do it later)
Apify is what lets the engine **read your own recent Instagram captions to learn your voice** in the very next step (the Homebase interview), and later **pull an inspo reel by link to study its editing style** (the `reference-reel` skill). It's an account-level MCP connector in Claude: connect it once via `/mcp` and every Startup Mom product reuses it, exactly like Notion. The SAME connector carries over from her other Startup Mom products. It is **strongly recommended, not required** — she can connect it now or skip it and add it the moment it pays off. Do not gate finishing setup on it.
- **ALWAYS check first, before you offer to connect anything.** Run `/mcp` and confirm with a lightweight
  read whether Apify is already connected (it is account-level, so it carries over from another Startup Mom
  product). **If it responds, it is already connected: do NOT ask her to connect it and do NOT show any
  connect steps.** Just warmly acknowledge it and move on, e.g. "Good news, your Apify is already connected,
  so there's nothing to do here. I'll use that same connection to learn your voice in the next step." Then
  continue. The connect question and steps below are ONLY for someone who does not have Apify yet.
- **ONLY if the check shows Apify is NOT connected, ask as a CLICKABLE pick-one (she taps, does not type), recommended first:** "Want to connect Apify now, so I can learn your voice from your Instagram in the next step?" Options:
  - **Connect Apify now (Recommended)** — takes a minute, and it means I can pull your recent captions for you next instead of you pasting them in.
  - **Set it up later** — no problem. We'll do it the first moment it helps (when you pick "learn my voice from Instagram," or when you want to study an inspo reel). Keep going for now.
- **If she connects now:** help her make a free Apify account, then type `/mcp`, add Apify (`https://mcp.apify.com`), and connect. If it asks for an API token, have her copy her Personal API token from her Apify account (Settings > Integrations > API tokens) and paste it into the `/mcp` prompt when asked. Her own token on her own account, public data only (bring your own key).
- **If she defers:** do not push, and do not treat setup as unfinished. The Homebase voice step offers it again exactly where it pays off, and pasting a few captions is always there as the no-Apify path.
- **How to frame the cost (say it plainly, it removes the fear):** everyone gets **$5 of free credit every month**, and pulling your captions to learn your voice, or a reel to study, costs **just a few pennies**, so that free credit covers normal use with room to spare. She never pays Apify a subscription; it's her own free account.

### 4. Build her Brand Homebase (make it yours)
Run the **`homebase`** skill. It always looks for a Homebase she built in another Startup Mom product or another copy of this engine first (whatever she answered in step 0), and if it finds one it asks, as a clickable choice, whether this engine is for the same brand or a different brand, business or client. Same brand: no file hunting, no re-interview; it reuses her voice and identity and only asks the Edit-specific pieces (her style pack, which sets her fonts and colors together in one pick, and whether her reels lean teaching or confessional). If she's new, say **"build my homebase"** for the full interview that fills `brand-kit.md` Part A (who she is, her voice and rules, her style pack and fonts), and the skill writes each answer where Part B of the file names. If she edits the file by hand later, **"update my homebase"** writes her changes in the same way. Different brand: it starts fresh and nothing comes over. This is the part that makes every reel look and sound like her. One question at a time. Do not finish setup while `brand-kit.md` still has any blank `{{...}}` field (or an older copy's `<<...>>` one).

### 5. The "you're set up" checkpoint
**Run the machine health check behind the scenes first — do NOT make her run it or read a checklist.** Quietly run `scripts/smoke-test.sh` (no clip needed: it confirms the tools are installed, her style-pack fonts resolve, and nothing points at a path that does not exist on her machine). If it comes back clean, say nothing about it. If it flags something, it has already written a report to `_handoff/` and prints the support email to send it to (`it@thestartupmom.com`). Gently tell her one small thing needs a look, point her to the report file, and let her email it in whenever she has a minute. Nothing is ever sent automatically. Either way she never has to stress about it. (The same tool has a voluntary, no-failure-needed mode for later: if a rough cut ever feels slow on her machine and she wants to help tune the engine for machines like hers, `python3 product/make-handoff.py hardware-diagnostic` writes a hardware-and-timing-only report she reads first and emails only if she chooses. Never run it unprompted, and never present it as something she owes anyone.)

Then confirm out loud: base tools all pass, the render engine is bootstrapped, (if she chose it) the editing engine answered its health check, and `brand-kit.md` has no blank `{{...}}` or `<<...>>` fields left. Tell her plainly: "You are set up." Celebrate it.

Then give her the community hashtag, in one warm line of its own: **"When you post a reel you made with this, tag it #startupmomedit so we can see it."** Setup always says it. After this it shows at the end of each reel's workflow until she says she doesn't need the reminder (`product/hashtag.py`, rule in `CLAUDE.md`).

### 6. What's next — end on a CLICKABLE choice (this is the capstone, never skip it)
Do NOT end setup with a paragraph of options she has to read. End it the flagship way: hand her the wheel with ONE clean **clickable pick-one** (she taps, does not type), warm and celebratory: **"You're all set 🎉 What do you want to do first?"** Offer these as tappable choices:

- **🎬 Show me everything this can do** → OPEN the effects library for her, right now: `product/effects-library.html`. Open it in her own browser, never the app's Browser pane (the pane cannot play the library's sounds): `bash scripts/open-library.sh`, on a Mac and on Windows (never a bare `open`: Safari will not play the sounds of a page opened as a file). Say it plainly: "This is the whole menu. Every move I can make, playing live. Browse it, tap the name of what you want, and just ask me for it by name." This is how she discovers moves she'd never know to ask for (movement on the footage, a slow push-in, a cinematic grade, animated stat cards). She can reopen it anytime by saying "show me what you can do."
- **✂️ Help me make my first reel** → recommend the first-reel script, `product/FIRST-REEL-SCRIPT.md`: open it for her. It is about 30 seconds (short on purpose, because the first run sets up the editing tools and a short clip keeps that wait small), and every line names an effect, so her first build shows the whole effects menu on her own face. She films it, drops it in `inbox/`, and says "edit this reel." Any short clip she already has works too. Or, if she already has a **folder of b-roll she filmed**, drop the whole batch in `inbox/` and say **"make b-roll reels"** — the engine hooks each clip, bakes the text on in her style pack, and hands her a numbered posting queue. Same drop spot, no filming step.

Make it a REAL tappable pick-one (same clickable feel as every other choice in this setup), never buried in prose. Whichever she taps, do that thing right then. She is never locked in — she can do the other one right after.

Then, once she's picked, these are hers whenever she wants them (mention lightly, do not lecture):
- **Pick your comfort level (optional).** You put setup on easy mode so it would run smoothly. Now she chooses what she wants day to day: keep auto-accept for speed, or dial it back so Claude checks with her before it changes anything. Walk her to `product/PERMISSIONS-SETUP.md` (set a default in `.claude/settings.json`, or use the current in-app permission-mode toggle). Her call; she's always in control.
- **It learns her pattern.** Say it plainly: her editable CapCut draft always comes back fully placed, she just nudges the layout to perfection, and when she likes a change she tells Claude to keep it. A plain nudge fixes THIS reel; a **stick-phrase** makes it her permanent default — **"learn my pattern for the next reel," "remember this," "make this my default," "always do it this way," "from now on…"** Claude saves it (into `brand-kit.md` Part C reel-style memory) and confirms what it saved, so the next reel needs fewer tweaks. She can also **"build my own style pack"** to save a whole look, or **"add that to my word list"** for caption spellings. It gets more like her every time. (Full lesson: E10.8.)
- **/studio everywhere (her choice, ask before doing it).** Studio's finishing commands work inside this engine folder already. Offer, as a clickable yes/no, to make `/studio` work in every Claude project on her computer too, and say plainly that it then loads in all her projects. Only on her yes, run `./install-studio.sh`. Never link it without that yes.
- **CapCut time-savers** live in `product/CAPCUT-TIME-SAVING-HACKS.md` (vertical-once, safe-zone guides, saved styles, favorites, hotkeys) — only if she finishes in CapCut.
- **If CapCut ever glitches a draft** after an update, she just says **"Claude, my draft won't open, fix it"** (the self-heal playbook). Normal and fixable, not her fault.

Point her to the creator's community as the place to get unstuck. Warm close.

## Rules
- DO the technical steps for her. She should never paste a command she does not understand. You run it and report back in plain words.
- One step at a time. Verify each worked before the next.
- If a step fails, stay calm, explain simply, offer the fix, and point to the community if it is still stuck.
- Beyond her Claude plan, the only outside account is her **own free Apify account (BYOK)**, connected once via the `/mcp` connector — the SAME connector as the Content Crafting Engine. Apify powers **reel research on both engines** (`reference-reel` here; `decode`/`research-ig-inspo` on the content side). Free tier (~$5/mo credit) covers normal use; pulls cost pennies. Never use the creator's token. Everything else is local, no other tokens.
- Mac and Windows are both supported, and this one flow covers both (step 0.1 works out which she is on). Only a platform that is neither, Linux for example, goes to the `pc-conversion` skill (see step 0.1).
