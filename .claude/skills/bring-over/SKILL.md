---
name: bring-over
description: "Brings everything that is hers from her OLD engine folder into this new version: brand kit, creator profile, the style packs she built, what she taught it, favorite sounds, her words, settings and keys, and her projects. THE command when she says 'bring over my old engine', 'move my stuff from my old engine', 'merge my old engine', 'copy my packs from the beta', 'copy my settings from the beta', 'pull everything from my old engine into the new one', or has just downloaded the final version and wants her work in it. A preview first, then her yes, then it copies. The old folder is only ever read."
---

# Bring over your old engine

The final version arrives as a fresh download, so it starts empty of her: no brand kit, no packs, nothing
she taught it. This is the one step that pulls everything she built in her old engine into the new one.
**The command is "bring over my old engine."**

**Audience:** a creator who is not technical. Do the technical part FOR her, in plain words. Reassure her
early and once: her old folder is only read, never changed, and nothing is moved out of it.

## What to do

> **🔴 Working directory (do this first, so the very first command can't fail).** Run every command below
> from the **NEW engine's project root**: the folder she opened in Claude Code (it holds `product.json` and
> `scripts/`). That is already your working directory in a normal session, so run the commands as written;
> do NOT `cd` into this skill's folder, and never run them from inside the OLD folder.
>
> **On Windows use `python`, not `python3`.** Windows ships a decoy at the name `python3` that only points at
> the Microsoft Store, so a pasted `python3 ...` line fails in a way that looks like the engine is broken.
> Check with `uname -s` (MINGW/MSYS/CYGWIN means Windows). Step 0 hands you the right one either way.

0. **Make sure there is a Python to run it with.** Same first step as `/update`:
   ```bash
   PY="$(bash scripts/ensure-python.sh)" && echo "$PY"
   ```
   Use the path it prints wherever a command below says `"$PY"` (keep the quotes: a Windows path can hold a
   space), or start each command with this step. On a brand-new computer it fetches a small private Python
   first (about two minutes, no password); say one warm line before it runs.

   **Do this before onboarding.** If the new engine asks to be set up ("set me up", the brand kit), this
   comes first: her brand kit, voice and packs are about to arrive from the old folder, and filling them in
   by hand would be work she has already done.

1. **Find her old engine folder.** Ask once, plainly: "Where is your old engine folder?" If she is not sure,
   look for her:
   ```bash
   "$PY" scripts/bring-over.py --find
   ```
   It lists the older engine folders in her home folder (the ones that can be brought over), with each one's
   version and the date it last changed. One: confirm it with her. More than one: show them as ONE clean pick-one prompt (path, version, date, the
   likely one marked) and let her choose. Never guess between two. None found: ask where she unzipped it
   (Downloads, Documents and the Desktop are the usual places).

2. **Preview it. Nothing is written.**
   ```bash
   "$PY" scripts/bring-over.py "<old engine folder>"
   ```
   Keep the quotes: folder names often have spaces. Read the whole output, then tell her in ONE short plain
   summary what comes across, by name where it helps: her brand kit and profile, her packs ("Sunday Best,
   Sunrise, and Old Friend, which an old update had lost"), what she taught it, her words and settings, her
   keys, and her projects with their size. Say what it means for room on her disk in one line (the output
   has it; on a Mac her footage copies as clones, which take almost no extra room). If anything is listed
   under **Needs a hand**, say so in one line ("two changes you made to the engine itself are saved, and I'll
   go through them with you after"). No file paths unless she asks.

   If it refuses, it says why in plain words: the folder is not an engine, it is this same folder, or it is
   already the new version. Tell her the reason and go back to step 1.

3. **Her yes, then bring it over.**
   ```bash
   "$PY" scripts/bring-over.py "<old engine folder>" --apply
   ```
   If she would rather leave her footage where it is (her projects and inbox clips), add `--no-projects`.
   Offer that only if she raises room on her disk or asks; the default is that everything comes across. It
   checks for room before it copies anything, and stops with a plain message if it will not fit.

   **On a PC (or a Mac copying to another drive) ask first.** There the footage cannot be cloned, so bringing
   it over makes a second full copy of every clip. The preview then ends with "pick one" and two commands
   instead of one, and `--apply` on its own stops before copying anything. Ask her as ONE clean pick-one,
   with the size from the preview: bring her projects too (`--apply --projects`, uses that much more disk)
   or leave them in the old folder (`--apply --no-projects`, they keep working from there; the recommended
   one when disk space is tight). Then run the one she picked.

   It finishes with what came across, what was already there, what needs a hand, and anything it left in the
   old folder for her to decide. Tell her in one line that it worked. If a line says something did not come
   across this time, run the same command again: it picks up where it stopped and never brings anything twice.

4. **Walk anything under "Needs a hand" with her.** The same list is written down in
   `_local/my-changes.md` (the newest section). Ask once: "a couple of things you changed in your old engine
   are saved. Want me to bring them into the new version now?" On a yes, see **Bringing a change forward**
   below. Anything under **Left in your old folder for you to decide**: read her the list and ask whether she
   wants any of it here; copy only what she names.

5. **Close it out.** Tell her she is set: her brand kit, packs and settings are live in the new engine, and
   her next reel is built here. Then say, plainly and once: **keep the old folder until every reel she started
   in it is finished.** CapCut drafts built there can still point at footage inside it, and deleting it early
   is what turns a draft into "media missing". If she wants the old folder gone sooner, a draft whose media
   still lives there can be pointed at the copy in the new folder first (`product/CAPCUT-SELF-HEAL-PLAYBOOK.md`,
   "Media path broken"), one draft at a time, with CapCut quit.

## Bringing a change forward

For each item under **Needs a hand** in the newest section of `_local/my-changes.md`:
1. Read what she had: her saved copy is under `_local/my-changes/from-v1/`, at the same path as the file it
   belongs to. A `.diff` beside it, when there is one, shows exactly what she changed. Then read the NEW file
   in the engine. When a file has a new name in this version, the entry names both: the new file is the one
   to change, and the old name is only there so she recognizes it.
   No `.diff` is the usual case: an old engine seldom still has the original her change started from. Then
   compare her whole saved copy with the new file. Most of the difference is the new version's own work; her
   change is the part that reads like her (a number she tuned, a rule she added, a line about her content).
   If it is not clear which part is hers, ask her what she remembers changing before you touch anything.
2. Make the same change on the new version, by intent: the same behavior, fitted to the new code. Never copy
   her old file over the new one; that would undo everything the new version fixed in that file.
3. If what she changed and what the new version changed pull in different directions, ask her one plain
   question before choosing.
4. Run the quickest check that touches it (that file's test in `product/tests/` if there is one, otherwise
   `bash scripts/smoke-test.sh`), then tell her in one line that it's back.
5. Under that item in `_local/my-changes.md`, add `  - ✓ brought forward <date>`.

What the items usually are, and what each needs:
- **An engine file she changed** (a builder, a skill, a preset): steps 1 to 5 above.
- **CLAUDE.md, lines of her own**: the `.diff` shows the lines she added to the old instructions. Put each one
  where it belongs in the new CLAUDE.md, outside her creator profile block (that block already came across).
- **Besides your settings, this file had other changes**: her settings (hook defaults, headline font) already
  came across on their own; the saved copy holds the rest of her edit. Steps 1 to 5.
- **A style pack saved as a file** (`_local/my-changes/from-v1/style-packs/<name>.json`): the new engine already
  had a different pack with that name. Ask her which she wants to keep under that name, and save the other one
  under a new name through `"$PY" product/pack_write.py --name "<new name>" --block <file>` (the pack's
  `block`; its colors come along with `--recipe` when it has them). Never edit style-packs.json by hand.
- **Your settings were not written over** (`_local/my-changes/from-v1/kept-settings.json`): the new engine
  already had settings of its own. Read her both and ask which to keep; `product/settings_persist.py` is what
  puts a setting into the engine's files.
- **A file under `_local/`**: the new engine already had its own copy of it. Combine the two with her.
- **No longer part of the engine**: the new version does not have that file at all. Tell her what it did and
  ask whether she still wants it, rather than restoring it on your own.

## The safety promises (say these if she's nervous)

- **Her old folder is only read.** Everything comes across as a copy; nothing is moved or changed there.
- **Nothing of hers is lost.** Anything that could not simply come across is saved in the new engine and
  listed for her, never dropped.
- **The new version stays the new version.** Her own files and settings come in; the old engine's own files
  do not, so every fix in the new version is kept.
- **It never deletes anything, anywhere.**
- **It is safe to run again.** A second run brings nothing twice and says so.

## Notes for you (Claude)

- The script is deterministic and does the real work. Don't copy files by hand, don't edit the pack files
  yourself, don't "help" by moving her projects: run it and interpret its output for her.
- It tells the old engine's own files from hers with fingerprints of every file the old versions shipped
  (`product/templates/v1-history.json`: hashes only). If the output says that record is missing, everything
  else still came across; say so plainly, and do not try to sort the old files by hand.
- It never touches CapCut or its drafts, and CapCut can stay open while it runs.
- A style pack an earlier update deleted can still come across (it looks in the old engine's update backups);
  one she deleted for good stays deleted. A pack of hers that shares its name with one the new engine ships
  comes across as "My <name>", and one of the engine's own packs she changed in place comes across as her own
  pack ("My Butter"), made her default if it was.
- `"$PY"` from step 0 is the interpreter on every computer. A pasted bare `python3 ...` line is never the
  answer on Windows.
