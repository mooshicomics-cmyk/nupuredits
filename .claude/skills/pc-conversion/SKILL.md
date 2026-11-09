---
name: pc-conversion
description: "LAST RESORT for a platform the engine does NOT support (Linux, or a Windows machine where Git Bash cannot be installed). Windows itself IS supported now and is handled inside `set-me-up` (step 0.1 detects it, 0.2 does the Windows pre-flight, and the install step branches to winget) — so do NOT use this skill just because someone is on a PC, and never route a Windows creator here for saying 'I am on a PC' or 'I am on Windows'. That sends a supported creator into an experimental path and out of the real setup. Use this ONLY when `uname -s` shows something that is neither Darwin nor MINGW/MSYS/CYGWIN, or when a Windows creator genuinely cannot get Git Bash. Walks an honest, reversible experiment on the creator's own machine, then produces a handoff report."
---

# PC Conversion (unsupported-platform path)

> **⚠️ Windows is SUPPORTED. This skill is not the Windows path any more.**
> A creator on Windows belongs in **`set-me-up`**, which detects her machine, runs the Windows pre-flight,
> and installs with `winget`. Routing her here instead is the single worst thing you can do to a PC creator:
> it drops her out of the real onboarding and tells her she bought something experimental. Only come here
> when `uname -s` is neither `Darwin` nor `MINGW*`/`MSYS*`/`CYGWIN*` (so: Linux), or when a Windows creator
> truly cannot install Git Bash.

The engine supports **Mac and Windows** (Windows through Git Bash). Someone here is on something else, a
Linux machine say, or a Windows PC that cannot get Git Bash, and wants to try running it anyway. Your job:
offer honestly, try it together safely, and turn whatever happens into a report that shows what this
platform would need. The full technical + best-practice reference is **`product/PC-CONVERSION-PLAYBOOK.md`**
— read it before you touch anything. This skill is the live flow; the playbook is the knowledge.

## The golden rule (never break)
This is **additive and experimental**. Nothing you do here changes how the engine runs on a Mac or a Windows
PC. You only work in **this creator's own copy, on their machine**, and every change is logged and reversible.
Mac and Windows are the **Supported** tier; this machine is the **Experimental** tier.

## Voice
Big sister across the table. Warm, plain words, short sentences, lead with hope. Hide the
machinery: run the commands FOR her, never make her paste something she does not understand. She cannot break
anything, and you will not break her computer.

## 1. The honest offer (opt-in, present tense, never overpromise)
When setup finds a machine that is neither a Mac nor Windows in Git Bash (step 0.1 of `set-me-up`), or she
asks, offer it warmly and honestly. Say the tier out loud. Something like:

> "It looks like you're on a computer this engine doesn't support yet. It's built for Mac and Windows, so
> here it's experimental. Here's the honest truth: on some machines like this it works, on some it works
> after a couple of setup steps, and on some it's not quite there yet. If you want, we can try it together,
> step by step, and I'll be straight with you the whole way. If it can't work today, I'll help you get a
> refund or put you first in line if support for your machine comes. Want to give it a go?"

On Linux, say one more thing up front: CapCut has no Linux app, so the editable CapCut finish cannot work
there. The finished-video route (HyperFrames + ffmpeg) is the one worth trying.

Only continue if she says yes. If she says no, be warm, point her to the refund/waitlist, done.

## 2. Preflight FIRST (read-only, before promising or installing anything)
Run the read-only checks from the playbook's STEP 0 and tell her the verdict before she invests time:
the OS and version (Windows edition + build on a PC), CPU, admin rights, RAM/free disk, whether there's an
NVIDIA GPU, and on a PC whether **standalone** CapCut desktop is installed (not the Microsoft Store version).
Nothing is installed yet. Route to one of:
- **Proceed** (looks good),
- **Proceed with caveats** (e.g. CPU-only, so transcription is slower), or
- **Known cliff** (see the playbook's cliffs table) → stop warmly, offer refund or the waitlist. Do not flail.

## 3. The safety pipeline (EVERY change to her machine, no exceptions)
`preview -> consent -> backup -> change -> log -> offer undo`
- **Preview** what you will install or edit, and where. "Nothing has changed yet."
- **Consent** again before anything needing admin, any install, or any file edit.
- **Back up** any file before editing it (`<name>.bak`); make a System Restore point before the first install
  where you can.
- **Log** every change to `_pc-conversion/change-log.md` in her folder: what, where, when, how to undo.
- **Idempotent:** re-running is safe; detect what's done and skip it.
- **Fail safe:** on any error, stop, restore from your backup, explain plainly. Never retry destructively.
- **Never** write to or alter anything outside her copy of this engine. Never touch a Mac product's files.

## 4. Walk the port (use the playbook, hide the machinery)
Follow `product/PC-CONVERSION-PLAYBOOK.md`. In short:
- **Linux:** install ffmpeg, Node 22 or newer, Python 3.11/3.12 and uv from the distro's own packages (or
  uv's installer); the engine's `.sh` scripts run as they are in bash. Aim for the finished-video route.
- **A Windows PC without Git Bash:** install the pieces natively (ffmpeg via winget, uv, Python 3.12 via
  uv, and Git for Windows, which is what the bash scripts need). Run each FOR her; reopen the terminal after
  PATH changes. If Git for Windows does go on, she is on the supported Windows setup: hand back to
  `set-me-up`.
- **Windows only: set UTF-8 permanently, in the same breath as the installs (REQUIRED, one command):**
  `setx PYTHONUTF8 1` and `setx PYTHONIOENCODING utf-8`, then reopen the terminal.
  Windows runs Python under a legacy codepage (cp1252), not UTF-8. Two separate failures come from that,
  and both look like something else: printing a status symbol raises `UnicodeEncodeError` mid-step, and
  `open()` with no explicit `encoding=` raises `UnicodeDecodeError` on any file holding a curly quote, an
  accent or an emoji — a caption, a hook, a brand kit, a draft JSON. About 129 engine files can trip one of
  these. The shell scripts export it themselves, but anything Claude runs directly does not inherit that,
  which is why it has to be set on the machine. Do not skip this because nothing has failed yet; it stays
  invisible until her first piece of non-plain text.
- Set up WhisperX from the pinned set (do not free-resolve; CPU baseline, CUDA only if she has an NVIDIA GPU).
- **On a Windows PC, the crux is the CapCut handoff:** the draft must be written with **Windows** absolute paths for media (and
  fonts by name), into `%LocalAppData%\CapCut\User Data\Projects\com.lveditor.draft`. The engine resolves that path itself now
  (v1.0.51), so do NOT hand-patch her copy of `workflows/capcut-live.py` any more; if a draft still opens
  "media offline", run a relink pass instead. Recommend she use standalone CapCut, not the Store one.
- Recognize a known cliff fast and exit gracefully rather than grinding.

Take the win in pieces. Get transcription working, then a rough cut, then the CapCut draft opening with media
online. Celebrate each real milestone with her.

## 5. Always produce the handoff report (success OR failure)
This is the whole point: every attempt becomes data that shows what support for her kind of machine would
take. As you go, keep notes so
you can fill the report. At the end, write it to `_pc-conversion/PC-REPORT-<date>.md` using the template in the
playbook. Auto-fill everything a machine can see (her OS and version, CPU, GPU, RAM, CapCut version if any, engine
version, where it broke, the verbatim error, and the exact tweak that fixed anything). Keep outcomes to the
fixed set (Worked / Worked-after-steps / Failed-at-setup / Failed-at-render / Bad-output). Ask her only for the
outcome confirmation and one optional comment.

The report stays on her computer (`python3 product/make-handoff.py pc-conversion "<outcome>"` writes it).
Whatever this conversion needed for her one machine is already patched here and kept through updates, so it is
not sent. Only a fix every engine on her kind of machine would need goes to the team, and only through the
`/report-a-problem` send test: `python3 product/report_gate.py --send "<why>"` must print SEND-READY first
(her engine the newest, the reason in one sentence). Then she emails it to `it@thestartupmom.com`. Frame it
warmly either way: she is a Pioneer, and a conversion that worked is a success story, not a report.

## Rules
- Opt-in only. Never route a Mac or Windows creator through this. Never enable it silently.
- Do the technical steps for her; she never pastes what she does not understand.
- Preview, consent, back up, log, and be reversible for every machine change.
- Be honest about the tier at every step. "Let's try it together and see" beats "this will work."
- Never change how the engine behaves on a Mac or a Windows PC. This path is additive and lives only in her copy.
