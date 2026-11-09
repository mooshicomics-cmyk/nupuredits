---
name: report-a-problem
description: "The engine's diagnostic tool for ANY problem, not only setup. THE command is /report-a-problem. Also runs when she says 'something's broken', 'this isn't working', 'it failed', 'it's stuck', 'it froze', 'it's taking forever', 'it's been rendering for hours', 'nothing happened', 'the engine is down', 'my draft won't open', 'there are no sound effects', 'my edits are gone', 'the text came out in the wrong language', 'report a bug', 'I got an error', or pastes an error message. It looks at what actually happened on her machine (what ran, how far it got, how fast, whether it froze, what is still running), tries the fix the engine already has FIRST (a newer version included), patches her machine's own problems right there, and only asks her to send a report when her engine is the newest one AND every creator's engine needs the fix (product/report_gate.py checks both and stamps the report). One pasteable file, collected automatically, so she never has to answer twenty questions."
---

# Something's not working

**The command is `/report-a-problem`. It is the engine's diagnostic tool for every kind of problem:**
setup, a render that runs for hours, a build that fails, a draft that won't open, missing sounds, lost
edits. Not only setup. Whatever went wrong, start here.

**Audience:** a non-technical mom who is, right now, a little bit frustrated and possibly wondering
whether she wasted her money. Everything below is written for that moment.

**The order matters: fix first, report second.** Most of what gets reported is one thing this engine
already knows how to fix: a machine-shaped setup gap, or one thing that happened (a render left
running, a build engine that went to sleep, a CapCut that updated underneath us). Building a support
report for something you could have solved in forty seconds sends her away to wait for an answer she
did not need. So you try first.

## 1. Say the reassuring thing, then get to work

One short line before any command. Something true, not chirpy:

> "Got it. Let me look at what your computer is actually telling me, then we'll sort it out."

Do **not** apologize repeatedly, do not call it a bug before you know it is one, and do not tell her
this is unusual or surprising. **Never dress a normal state as a fault.** A brand kit that is not
filled in yet, a CapCut folder that does not exist because CapCut has never been opened, a
transcription model that has not downloaded yet, a build engine that stopped when the computer slept:
these are steps not taken, not things broken. Say so plainly and take the step with her.

## 2. Find out what she was doing

Ask **at most two** questions, in plain words, and only what you cannot see for yourself:

- What were you trying to do? (Cutting her footage, making the graphics or the finished video,
  building the CapCut draft, opening it in CapCut, setting up, updating.)
- What did you see instead? (If there is an error on her screen, ask her to paste it. If she has
  already pasted one, do not ask again.)

If she is vague ("it just didn't work"), that is fine and normal. Do not interrogate her. The
collector below answers most of it without her.

## 3. Run the collector

> **🔴 Working directory.** Run this from the **engine's project root** (the folder with
> `product.json` in it). That is already your working directory in a normal session, so just run the
> command as written. Do NOT `cd` into this skill's folder.

```bash
bash scripts/collect-report.sh
```

**🔴 First line to read: "THIS ENGINE IS BEHIND".** When the report's top lines say a newer engine is out,
the fix almost always already exists there: in the launch weeks most reports were bugs a later version had
fixed. Before anything else, tell her in one line ("There's a newer version with fixes, let's get you onto it
first") and run `/update` (the `update` skill). Then try what failed again. Only if it still happens do you go
on with this skill and build the report, on the new version. Never write the report up, or suggest emailing it,
from an engine that is behind. `python3 product/report_gate.py` answers the same question on its own (exit 0
newest, 2 behind, 3 couldn't tell), and step 5 runs it again before anything is sent.

**Every problem gets this.** One file, two halves:

- **Is this machine set up?** Versions, tools, CapCut, the setup check, the brand kit.
- **What was the engine doing?** The last renders and bakes (how far each got, how fast, whether it
  finished, froze, crawled, or ran at the same time as another), whether the renderer was drawing
  with the graphics chip or in software, the last transcription's timing, what is running right now
  (render-browser processes, ffmpeg, CapCut, the build engine), how much memory is free this minute,
  reports already sitting in `_handoff/`, and whether the last update finished.

**A render problem gets one more step.** When she is describing a render (graphics, captions, a
well-done finish) that hung, ran long, failed, or came out wrong, run it with `--render` instead:

```bash
bash scripts/collect-report.sh --render
```

That adds HyperFrames' own checks (`doctor` for the machine, `info` for the composition that ran) and
a timed test render: a 1-second test composition in a temp folder, once with a plain font and once
with a style-pack font. It takes a few minutes, so tell her first, in one line:

> "I'm going to run a short test render to see how fast your computer draws graphics. It takes a few
> minutes and doesn't touch anything of yours."

It is report-only either way: it installs nothing, changes nothing, needs no password, never touches
her footage, brand kit, keys or projects, and never sends anything anywhere. Only process names are
read, never what is open in them. (The `--render` test is a real render, so like any render it may
download the renderer's standard fonts the first time; nothing of hers leaves the computer.) Say one line about what it is doing ("checking what your machine has and what it
was doing, nothing's being changed") and let it run.

Read the output yourself. **Do not paste the whole thing at her.** It is written for whoever helps
her, not for her.

## 4. Read it, then try the fix

Match on what she said **and** what the report shows.

### The machine (setup)

| What the report shows | What it means | What you do |
|---|---|---|
| **Homebase: NOT personalized** | Setup never finished | Run the onboarding: tell her "one thing got skipped in setup," then go through `set-me-up` |
| **Computer: Mac (rosetta)** | Terminal has "Open using Rosetta" ticked | Walk her through unticking it, then the normal path works. This is one checkbox |
| **Computer: Mac (intel)** | True Intel Mac, Homebrew cannot install | Use the engine's own route (`product/INTEL-MAC-ROUTE.md`). Never hand her a `brew install` line |
| **python3: DECOY** (Windows) | Windows' Microsoft Store stub | Use `python`, never `python3`. It is not missing, it is the wrong name |
| **Long paths: OFF** (Windows) | CapCut drafts nest deeper than 260 chars | Turn long paths on, then retry the export |
| **A tool shows `missing`** | It is genuinely not installed | `./check-setup.sh` prints the exact install line for her machine. Run it, use that line |
| **Free disk very low** | Renders, frames and the transcription model need room | Say the number plainly and help her clear space before anything else |
| **Draft folder: not found yet** | CapCut has never been opened | Not a fault. Open CapCut once, then retry |
| **Engine version is behind** | A fix may already exist | Run `/update` first, then see if it still happens |
| **The update has not run its finishing step** | Normal right after an update | `/update` finishes it |

### What happened (everything else)

| She says, or the report shows | What it means | What you do |
|---|---|---|
| A render **never finished**, and its frames were still counting up | It was crawling, not frozen. The report gives its real speed and how long the whole render takes at that speed | Tell her the honest number. Then find out WHY it was slow from the rows below (software drawing, a second render, leftover processes, low memory). If none of them explains it, run `--render`: a healthy test render means the machine is fine and that composition was unusually heavy, so report it |
| A render **FROZE** (the renderer printed nothing for a long time before its last sign of life) | Stuck, not slow | Run `--render`. Its verdict names the cause: font loading, or the renderer not starting on this machine. Then report it with that verdict |
| **Drawing in SOFTWARE** | Chrome is not using the graphics chip, so the processor draws every frame, many times slower | Report it. The `doctor` output from `--render` says why the chip was not used |
| **Two ran at the same time** | Each render already uses every core, so two at once both crawl | Renders run one at a time. Let one finish (or stop the extra one), then run the next |
| **Render-browser processes running**, and no render is recorded as running | Left over from a render that was stopped, still using memory and processor | With her OK, close them (Mac: `pkill -f chrome-headless-shell`; Windows: `taskkill //F //IM chrome-headless-shell.exe`), or have her restart the computer. Then retry |
| **Memory: Low** | A render opens several browsers at once (about 256 MB each) | Close CapCut and other apps, then render again |
| A render **failed** and free disk is low | Frames need room while they are made | Clear space, or re-run the render with `--low-memory` (`product/reel_render.py`), which streams frames instead of storing them |
| **ENGINE DOWN**, and the build engine is not running | The CapCut build engine stops when the computer sleeps or restarts | Start it: Mac `start-editor.command`, Windows `start-editor.bat`. Leave that window open, then retry. Not a fault |
| "It says CapCut must be quit" | The guard that protects her CapCut edits, doing its job | Quit CapCut, retry. Not a fault |
| Her CapCut draft won't open, opens blank, or says media is missing | Usually CapCut updated its format underneath us | Follow `product/CAPCUT-SELF-HEAL-PLAYBOOK.md` exactly. Never rebuild over her draft |
| "There are no sound effects," or a reel came out silent | The sounds ship inside the engine; an empty search means it looked in the wrong folder | `python3 product/capcut_sfx.py --list`. Never tell her a bundled library is missing because a search came back empty |
| A style-pack font is missing or wrong in CapCut | The pack fonts resolve from her CapCut | `python3 product/capcut_font_doctor.py <Pack>` |
| On-screen text came out in English (or the wrong language) | Captions follow her voice; hooks and cards are written fresh | Read `language_code` in the transcript and rewrite only the on-screen copy in her language. No re-cut |
| Something went wrong in the **visual editor** (a button did nothing, "That didn't go through", an export failed, the page broke) | The editor writes down every error as it happens, including ones she never saw; the report's **Visual editor** section carries the latest, with the code's own trace (`python3 product/editor_errors.py` lists them) | Read that section first: it usually names the failing step. Fix it if the fix is hers to make (a reload, an export left running); a fix to the engine's code is the step-4 exception. Otherwise finish the report. Her page also has a **Report a problem** button: it makes the same evidence into one file in `_handoff/` and sends her back here, so read that file too. The step 5 send test still decides |
| Her CapCut edits are gone, or a draft was replaced | Serious: CapCut keeps no history | Stop. Do not rebuild anything. Report it right away, with the draft name and what she saw |
| Transcribing fails with the same error every time | Usually a half-downloaded Python, which the current engine repairs on its own | `/update`, then retry |
| The cut is wrong: a double take kept, a clipped word, dead air | Not a machine problem | Re-run it through the `rough-cut` skill (`stitch-cut.sh`, or `product/clean_cut.py` for a custom build). Never hand-trim |
| Something she (or Claude) changed in the engine is gone, or behaves differently, after an update | Updates bring her changes forward; the ones that collided with the update are waiting for her | Read the newest section of `_local/my-changes.md` (the report shows its counts). Anything under **Needs a hand**: bring it forward with the `update` skill. For the full list of what she has changed: `python3 product/keep_changes.py --scan` |

If the fix works, **stop here.** Tell her what it was in one sentence, in plain words, and get her
back to what she was doing. No report needed. Do not make her send anything.

**That includes a fix to the engine's own code.** If you fixed it by changing an engine file (a builder, a
script, a skill), the engine patched itself: her change is kept through every update (`product/keep_changes.py`),
so she has nothing to send. Tell her it is fixed and move on. The fix is already written down in
`_local/my-changes.md` and in the report file, if anyone ever asks for it.

## 5. Only if it is still broken: the send test

**The inbox is only for fixes that go out to every engine.** Every report is read by a person, and most
problems are one machine's problem, which this engine patches right here. So the default is: **no report.**
Decide it yourself; never ask her whether she thinks it should be sent.

A report goes in only when ALL of these hold:

1. **Her engine is the newest one.** `python3 product/report_gate.py` says NEWEST. BEHIND means `/update`
   first and try again (the fix is very likely already there); CAN'T TELL means try again in a few minutes.
   Neither one is ever sent.
2. **It is not her machine, her file or her setup.** Security or work-managed software, an unsupported
   computer (`set-me-up`'s list), one unusual clip, her internet, a full or slow disk, low memory, a CapCut
   she changed, a tool installed oddly: patch it here (step 4, including a change to the engine's own code
   when that is what her machine needs) and tell her it is fixed. Her change is kept through every update
   (`product/keep_changes.py`). Never a report.
3. **Every engine needs the fix.** The same thing would happen to anyone on a normal, supported setup doing
   a normal thing: a crash or traceback in engine code, a wrong result from a skill (a word cut in half, a
   lost edit, a draft that will not build), a setup step that fails on every supported Mac or Windows PC,
   a check of the engine's own that tells her to report. You can say in one sentence why. A wish ("could
   it also do X"), a style she would like, or a how-to question never passes: answer those here, from
   `which-lesson` and the course.

**All three pass:** finish the report (step 6), then stamp it:

```bash
python3 product/report_gate.py --send "<one sentence: why anyone's engine would hit this>"
```

It checks for a newer engine one more time and refuses unless this engine is the newest. Only when it prints
**SEND-READY** do you ask her to send it, in one line. No SEND-READY, no mention of sending.

**Any one fails:** do not mention a report or an email. Tell her plainly what is going on, in one or two
sentences, and give her the best way forward you have (a workaround, a setting on her machine, a different
clip, what to try tomorrow). If it is her machine, say so kindly: it is not her fault and it is not a
broken engine. The report file stays on her computer, unsent, in case it is ever needed. A one-off like
this is the one place where she is better served by you than by an inbox.

**One report per problem.** If `_handoff/` or `_local/` shows she already made a report for this same
problem, do not ask her to send another one. Tell her it is with the team.

## 6. Finish the report

Open `_local/problem-report.md` and fill in the **What happened** section at the bottom yourself,
from what she told you and what you just tried. Write it the way she said it, plus the facts:

```markdown
### What happened

She was [what she was doing] when [what happened instead].

The error, word for word:
```
[paste it exactly, no cleanup]
```

Already tried: [what you tried, and what it did]
Still happening: [yes/no, and what changes it]
```

The one file is enough: it already carries the key lines of any render record, stall report and test
render. Then stamp it with `python3 product/report_gate.py --send "..."` (step 5). Only on SEND-READY, hand
her the file and tell her exactly where it goes:

> "Okay, this one's past what I can fix from here, and it's one other people would hit too, so it's
> worth fixing for everyone. That's on the engine, not on you. I've put everything needed into one file.
> Send it in and we'll take it from there."

**Where to send it:** email it to **it@thestartupmom.com**. That is the one place, for every creator. Never
point her to a community or help channel: not every creator is a community member.

Offer to open the file for her so she can copy it. Do not make her go find it.

## What never goes in the report

The collector already keeps these out, and you should not add them by hand:

- Her footage, transcripts, scripts, captions or any file contents
- Her API keys, tokens or passwords
- Her brand kit contents (whether it is *filled in* is recorded; what it says is not)
- Her full home path (the collector shortens it to `~` so a paste in a public channel is safe)
- Anything about her other programs beyond their names (process names only, never what is open in them)

If she pastes something sensitive into the chat while describing the problem, leave it out of the
report and tell her plainly that you did.

## Notes for you (Claude)

- **`scripts/collect-report.sh` is the deterministic part. Run it, do not reimplement it.** Do not
  hand-gather versions, process lists or render timings with your own commands; the collector knows
  the Windows PATH repair, the Mac architecture split and the Python decoy, and your ad-hoc version
  will not. On Windows, any Python line in this skill runs as `python`, never `python3`.
- **The render record is the evidence.** Every graphics render and final bake writes one to
  `_local/render-log/` and keeps rewriting it while it runs, so a render that was cancelled after
  running all night still says how far it got, how fast, and whether it froze or crawled.
  `python3 product/render_log.py` prints the same summary on its own. It exists from this engine
  version on; for an older render the report falls back to the last render that ENDED, and a
  cancelled one left nothing behind. Say so plainly rather than guessing.
- **A missing stall report is normal.** One is only written when the renderer prints nothing for 10
  minutes, so a slow render that kept counting frames never writes one. Never treat its absence as a gap.
- **Never stop a render that is still counting frames just to check on it.** The record already says
  how far it is. A slow render stopped from outside is how a correct render gets reported as a hang.
- **It is genuinely safe to run at any time, including when she is mid-panic.** Nothing is installed,
  changed or sent; the only files written are the report and, with `--render`, the test render's own
  report in `_handoff/`. It cannot make the situation worse. So run it early
  rather than asking questions.
- **`--quiet` prints only the file path**, for when you want the file without dumping it in chat.
- **The send test in step 5 is the gate for every report, from every path.** A script message, the
  visual editor's Report a problem button and a stall report all bring her here first. Nothing she sees
  should tell her to email anything until it has passed both tests.
- **A report is the last resort, not the first move.** The tables in step 4 cover most of what comes
  up. If you find a fix that is not in them, say so at the end of your reply so it can be added.
- **Never show her a raw traceback.** Read it, translate it, and put the verbatim text in the report
  file where it belongs.
- **If she is upset, the fix is the apology.** Skip the paragraph about how sorry you are and solve it.
