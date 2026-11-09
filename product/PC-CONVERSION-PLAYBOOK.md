# Conversion Playbook (platforms the engine does not ship support for)

This is the reference an assistant uses to help a creator try to run the engine on a platform it does NOT
ship support for, e.g. Linux. **Windows is a supported platform and does not use this doc** — it installs
natively through the `set-me-up` skill. It is loaded by the `pc-conversion` skill. It is a preparedness
doc, not a promise. Read it fully before touching a creator's machine.

## THE GOLDEN RULE (read first, never break)
This path is **purely additive and experimental**. It must NEVER change how the engine works on a supported
platform.
- Do not edit the shipped pipeline code to "make it cross-platform" as a blanket change. Every port tweak is
  applied **live, on the creator's own copy, on their machine**, logged, and reversible. The Mac product ships
  and behaves exactly as before.
- Mac and Windows are the **Supported** tier. Everything else is the **Experimental** tier. There is no
  in-between where a creator on a supported platform silently gets experimental behavior.

## The three tiers (say the tier out loud, in plain words)
Borrowed from how Rust, Homebrew, and Steam Deck label platforms honestly:
- **Supported (Mac and Windows):** it works, we stand behind it.
- **Experimental (anything else):** opt-in only. On some machines it works, on some it works after a couple
  of steps, on some it is not there yet. We try it together on your machine and we are honest the whole way.
- **Not yet (Waitlist / refund):** for machines we already know cannot run it today, so nobody wastes money.

A sales page or checkout MAY say the engine runs on Mac and Windows, because it does: both install natively
and both are supported. What must never be claimed is a platform outside that list. For anything else,
**"experimental"** is still the only honest word a creator should see. Decide based on what it is today, not
what it might become.

## The safety pipeline (EVERY change to the creator's machine goes through this)
`preview -> consent -> backup -> change -> log -> offer undo`
- **Preview / dry-run first.** Tell them exactly what you will install or edit and where. "Nothing has changed
  yet." This is the single most trust-building step for a nervous non-technical creator.
- **Consent per action class,** not one blanket yes. Ask again before anything that needs admin, installs a
  tool, or edits an existing file.
- **Back up before you touch anything.** Copy any file to `<name>.bak` before editing it. Where reasonable,
  make a Windows System Restore point before the first install.
- **Log every change** to a manifest file in the creator's folder (`_pc-conversion/change-log.md`): what, where,
  timestamp, how to undo.
- **Idempotent:** re-running setup must be safe. Detect what is already done and skip it, never double-install.
- **Least privilege:** elevate only for the one step that needs it. Install into the tool's own folders, do not
  scatter files across their system.
- **Fail safe, not silent:** on any error, stop, restore from the backup you took, and report plainly. Never
  retry destructively.
- **Never write to the Mac product's files or config.** The PC work lives in the creator's copy only.

## STEP 0 - Preflight (read-only, before you promise anything)
Run these checks and give the creator the verdict BEFORE they invest time. Nothing is installed yet.
- **Windows edition + build** (`winver` / `systeminfo`). Windows 10 1809+ or Windows 11 is the floor.
- **CPU virtualization on?** (Task Manager > Performance > CPU > "Virtualization: Enabled"). Off in BIOS is a
  known cliff (only matters if you ever fall back to WSL2, but check anyway).
- **Admin rights available?** Installs need them.
- **RAM / free disk** (WhisperX large-v3 model is ~3 GB; leave headroom).
- **GPU:** is there an **NVIDIA** GPU? (`dxdiag` or Device Manager). NVIDIA = optional big speedup for
  transcription. AMD/Intel/none = CPU baseline (works, just slower). Assume CPU baseline for most creators.
- **CapCut installed, and which build?** You need the **standalone desktop CapCut** from capcut.com, NOT the
  Microsoft Store version (the Store version hides drafts under a `Packages\...\LocalCache` path and is a
  support trap). Confirm CapCut has been opened once (that creates the drafts folder).
Route the verdict to one of: **proceed** / **proceed with caveats** / **known cliff -> waitlist or refund**
(see the cliffs table). Catch a dead machine here, not 40 minutes in.

## The route: native Windows, NOT WSL2 (this is the important call)
Research verdict, weighted by the one step that cannot break (handing CapCut a draft it can open):
- **Use native Windows** for everything: Python + `uv`, ffmpeg, WhisperX, and the `.sh` scripts under
  **Git Bash** (from Git for Windows). CapCut is a native Windows app that reads its draft by absolute Windows
  path, so producing the draft on the Windows filesystem makes the handoff zero-copy and zero-translation.
- **Avoid WSL2 as the primary environment.** WSL2 is the nicer place to run WhisperX, but a WSL2 (Linux)
  process must write the draft + media to `/mnt/c/...` for the Windows CapCut app to see it, which is slow
  (the 9P filesystem boundary) and forces Linux paths that CapCut cannot resolve. That fights the single most
  fragile, creator-facing step. Only consider WSL2 if the `.sh` layer proves impractical under Git Bash, and
  even then stage the final draft + media onto a real Windows path and rewrite media paths to `C:\...`.

## Install recipes (native Windows, hide the machinery, run them FOR the creator)
Each is one command. After any install that changes PATH, **open a fresh terminal** before verifying.
- **ffmpeg:** `winget install -e --id Gyan.FFmpeg` then (new shell) `ffmpeg -version`.
- **uv:** `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"` (or
  `winget install --id=astral-sh.uv -e`). `uv run`, `uv sync`, lockfiles all behave like macOS.
- **Python:** let `uv` install and pin **Python 3.12**. Do NOT use 3.13 (CTranslate2, which WhisperX depends
  on, has no 3.13 wheels). 3.11 also fine.
- **Git Bash:** install **Git for Windows** (`winget install -e --id Git.Git`); it provides the bash the
  `.sh` scripts need. Save scripts LF-only (a CRLF `.sh` fails with `bad interpreter: /bin/bash^M`). If an
  ffmpeg path arg gets mangled by Git Bash path translation, prefix with `MSYS_NO_PATHCONV=1`.

## WhisperX (the fragile part - ship a pinned set, do NOT free-resolve)
The instability is the PyTorch <-> CTranslate2 <-> cuDNN version triangle, not Windows itself. Remove the
freedom to resolve and reliability mostly returns.
- **Python 3.11 or 3.12 only** (3.13 blocked, above).
- **CPU baseline** (no NVIDIA): install the CPU PyTorch wheel, then WhisperX. large-v3 runs, just slow. Fine
  for short reels.
- **NVIDIA GPU:** install the **CUDA** torch wheel explicitly FIRST (e.g. the `cu121`/`cu124` index), THEN
  WhisperX, or a plain `pip install whisperx` silently pulls CPU torch and you get no GPU.
- **The classic failure** is `Could not load library cudnn_ops...dll`: a CTranslate2/cuDNN mismatch. Pin a
  known-good trio rather than mixing latest:
  - CUDA 12 + cuDNN 9 -> CTranslate2 >= 4.5, torch 2.5+.
  - CUDA 12 + cuDNN 8 -> pin `ctranslate2==4.4.0`, torch < 2.4.
  - CUDA 11 + cuDNN 8 -> pin `ctranslate2==3.24.0`.
- **Never CTranslate2 4.8.x on Windows**, GPU or not: it segfaults (exit 139) loading any Whisper model, on the
  card and on the processor. The engine pins 4.7.2 (the last release before it) on an NVIDIA PC's WhisperX venv
  and 4.4.0 on every faster-whisper venv (`ct2_pin` in `word-timings.sh`).
- **Best practice:** ship a `uv.lock` with the exact tested torch + ctranslate2 + whisperx versions so the
  creator gets the combination that was proven, not a fresh resolve. Treat that lockfile as the deliverable.

## THE CRUX: the CapCut draft handoff (this is what actually makes or breaks a port)
The pipeline's final act is a CapCut draft the creator opens. On Windows:
- **Windows draft folder:** `%LocalAppData%\CapCut\User Data\Projects\com.lveditor.draft`
  (i.e. `C:\Users\<user>\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft`). The
  `com.lveditor.draft` name is the same as Mac. Quick open for the creator: `Win+R`, paste
  `%LocalAppData%\CapCut\User Data`, Enter.
- **#1 breakage - absolute media paths.** CapCut does NOT embed media; the draft JSON references each clip by
  **absolute path**. A Mac path (`/Users/...`) does not exist on Windows, so a Mac-built draft opens as
  **"media offline."** Every media path in the draft must be the Windows location (`C:\Users\...`). Either
  build the draft on the Windows machine so paths are written native, or run a **relink pass** over the JSON
  before the creator opens CapCut. This is mandatory, not optional.
- **`com.lemon.lvoverseas` is Mac-only.** That container path (fonts, caches, sometimes the draft root) does
  not exist on Windows; the Windows data root is simply `%LocalAppData%\CapCut`. Remap any such path.
- **Fonts:** confirm the draft references fonts by **name / font-id** (so CapCut resolves them from the
  creator's own CapCut, per the ship model), NOT by a Mac absolute font path. A baked Mac font path is dead on
  Windows.
- **Possible encryption (version-dependent).** Some newer CapCut builds obfuscate/encrypt `draft_content.json`
  so it is not plain JSON. If the creator's version does this, direct-JSON rewrite tools need a fallback. **Test
  against the creator's exact CapCut version; do not assume plaintext.**

### The drafts folder is already per-platform (do not hand-patch anything)
The engine finds CapCut's drafts folder on each platform by itself: `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft`
on Windows, `~/Movies/CapCut/User Data/Projects/com.lveditor.draft` on a Mac (`product/draft_safety.py` and
`workflows/capcut-live.py` both branch on the platform), and it names the draft's timeline file the way
each platform's CapCut expects. So never patch a draft path into her copy: the Windows branch is already
there. If a draft still opens "media offline", run a relink pass over its media paths instead. CapCut has no
Linux app, so on Linux there is no drafts folder to find at all; the finished-video route (HyperFrames +
ffmpeg) is the one to try there.

### The Claude app from the Microsoft Store (MSIX): new drafts are hidden from CapCut
The Store version of the Claude desktop app is an MSIX package. Windows gives it, and everything it starts
(Git Bash, Python, the editing engine), a private copy of AppData: a NEW file or folder written under
`%LOCALAPPDATA%` lands in `%LOCALAPPDATA%\Packages\Claude_<id>\LocalCache\Local\...` instead. Claude reads
its private copy merged over the real folder, so everything looks fine from inside, but CapCut runs outside
the package and never sees a draft built there. Changing an EXISTING file is not redirected (reading CapCut's
list and fonts keeps working), which is why this hides so well.
- **The engine handles it.** `product/capcut_store_redirect.py` probes once per run (a uniquely named folder in
  `%LOCALAPPDATA%`, then a look under `Packages\*\LocalCache\Local`). When redirected, every draft writer's
  root becomes `projects/_capcut-staging/com.lveditor.draft` (one shared root: `draft_safety.CAP`). Everything
  that reaches CapCut goes through **Add to CapCut.bat**, which runs `install_to_capcut.py` outside the
  package, so the copy reaches CapCut's real folder. It refuses while CapCut is open or when started from
  inside the Claude app, never replaces a project she changed in CapCut (a fingerprint lives in each installed
  project), rewrites the staging paths in every JSON file (forward-slash and JSON-escaped backslash forms), backs
  up `root_meta_info.json` first, and runs one copy at a time (`.add-to-capcut.lock`).
- **The engine runs that step for her.** `capcut_media.register_draft` queues each staged draft
  (`capcut_store_redirect.after_build`); when the build process ends, so every write it makes is done, and
  `draft_safety.capcut_running()` says CapCut is closed, `auto_add` leaves a one-time request
  (`.auto-request.json`: token + time, honored for 120 s) in the staging folder and runs
  `explorer.exe "<staging>\Add to CapCut.bat"`. Explorer passes the file to the shell process that is already
  running, outside the package, which starts the .bat exactly like her double-click. Explorer cannot pass
  arguments, so the fresh request is what makes it an automatic run: the script writes `.auto-result.json` in the
  staging folder (never AppData, so it is never redirected): `running`, then `done` with what went in, or
  `refused` / `error` with the reason, and exits 75, which the .bat reads to close without "press a key".
  The engine waits 25 s for it to start and up to 15 min for the copy. A clean `done` naming the draft: one
  line, "It's in CapCut, at the top of your list", no folder, no instructions (the editor's Finish tab shows
  "In CapCut"). Anything else (CapCut open or unknown, Explorer never started it, the script found itself inside
  the package, CapCut opened in between, a copy that never finished, a build that crashed): the exact
  double-click instructions and the folder, as before, plus a `fallbacks.log` line. `REE_AUTO_ADD=0` turns the
  automatic step off. **Unverified on a real Store-app PC (2026-10-19):** proven only with a stand-in for
  Explorer on a Mac. If Explorer turns out to start the .bat inside the package, the script's own probe refuses
  ("inside-package") and she gets the double-click, so the worst case is today's flow.
- **One answer for every Python on the PC.** Whether a process is inside the package depends on how it was
  started: on one creator's PC the engine's venv Python said "redirected" and the `python` on PATH (outside the
  package) said "no". A redirect any process sees is remembered for the PC (`windows.store-redirect` in
  `_local/pivots.json`, inside the engine folder, which no package redirects), so every later process builds in
  the staging folder too; the editing engine (VectCut) runs the same check when it starts. The Store app
  uninstalled: forgotten. `python product/capcut_store_redirect.py --recheck` forgets it and probes again.
- **A clip that did not go into the draft is a failed build, with the reason.** VectCut copies every clip into
  the draft at save time, from its own folder (`product/engine/VectCutAPI`). Its copy used to answer False on a
  failure and the save still said success, so finalize later refused "file missing ... assets\video\...". Now:
  the build's own process makes every clip path absolute (`vectcut_engine.local_media_path`: a relative path or
  a Git Bash `/c/...` path) and fails a call whose clip is not there; VectCut's save answers success False with
  "media could not be copied into the draft" and each clip's path and reason; finalize
  (`vectcut_engine.refuse_failed_media`) says that in plain words and removes the unfinished draft-id folder.
- **Do not hand-build drafts into AppData from inside the app** and do not tell her CapCut "should" show it.
  `python product/capcut_store_redirect.py` answers `redirected: yes/no` in one line.
- **Limit:** layering onto a draft she has already edited in CapCut cannot reach her edited copy while
  redirected (the engine sees only the staged one); the installer keeps hers and says so.
- **An open CapCut does not block a staging build.** `draft_safety.require_capcut_quit` lets a write into the
  staging folder through (`draft_safety.capcut_never_reads`, one plain line), because CapCut never reads that
  folder; **Add to CapCut** is the step that keeps requiring CapCut closed. CapCut's own drafts folder is never
  relaxed. Every caller of the guard takes its root from `drafts_root()` / `draft_safety.CAP`
  (`product/tests/test_windows_capcut_gates.py` checks each one).
- **A stuck CapCut.exe** (no window, and even an administrator's `taskkill` says Access denied): Add to CapCut
  measures it with PowerShell `Get-Process`, two looks 5 seconds apart. When every CapCut process has no window
  and used no processor time, it cannot save, so the copy goes ahead with a plain line and a `fallbacks.log`
  entry; nothing is remembered. Any window, any work, or anything unreadable keeps refusing. When the SAME
  CapCut processes (same id, same start time) are still there at the next build refusal, the refusal says the
  computer did not fully restart: Start > Power > Restart (Shut down with Fast Startup is not a restart), or
  hold the power button.

### Non-English Windows: never decode console output as UTF-8
`tasklist` (and `reg`, `where`, other console tools) print in the console's OEM codepage: cp850 on Spanish,
cp1252/cp850 on French and German. With `PYTHONUTF8=1`, `subprocess.run(..., text=True)` decodes that as UTF-8
and raises `UnicodeDecodeError` on the first accented byte (0xa2 in "Sesión"). The CapCut-is-open guard then
answered "could not tell" and refused every handoff. Read such output as bytes and match ASCII
(`b"CapCut.exe" in r.stdout`), or decode with `errors="replace"`. `test_quit_guard.py` scans for regressions.

### Smart App Control (Windows 11)
When Smart App Control is ON it blocks native files that are neither signed nor widely known. uv's own
downloaded Python has an unsigned `python311.dll` (Code Integrity events 3077/3033), so `uv venv` ends on
"Missing expected target directory for Python minor version link" and uv's repair loop only repeats it. The
newest native wheels of ctranslate2, pandas, scikit-learn, aiohttp, matplotlib and SQLAlchemy were blocked too
("An Application Control policy has blocked this file"). `scripts/_win-sac.sh` reads the state
(`VerifiedAndReputablePolicyState`: 1 on, 2 evaluation, 0 off); when it is on, `word-timings.sh` builds the
speech tools from the signed python.org 3.11 (installed with winget, user scope, if missing), with
`UV_PYTHON_PREFERENCE=only-system UV_PYTHON_DOWNLOADS=never` and the pins in `WIN_SAC_PINS`. Never tell her to
turn Smart App Control off: once off, Windows will not let her turn it back on.

## Known cliffs (STOP and offer waitlist/refund, do not flail)
- Virtualization off in BIOS and the creator cannot/will not enable it (only blocks a WSL2 fallback, but note it).
- Windows Home edge cases or a corporate-locked / no-admin machine.
- An **ARM** Windows PC (Surface Pro X and similar): the tool stack is not proven there.
- **Microsoft Store CapCut** keeps its own project list inside its package (`Packages\...\LocalCache`), where the
  engine never writes. `product/capcut_installs.py` tells the four setups apart (`both`, `store-only`, `desktop`,
  `none`). With both, the engine says after each build that her projects are in the desktop CapCut;
  `--open` opens the right one when she asks, once the last write is done; store-only means installing the free desktop CapCut from capcut.com. Not a cliff any more.
- The creator's CapCut version writes **encrypted** drafts and the relink cannot read them: cliff until tested.
When a cliff is hit, stop, be warm, and route to the graceful exit (refund or "first in line" waitlist).

## What to capture (this is why we do this: the compatibility flywheel)
Every attempt, success OR failure, produces a **handoff report**. The report is what lets the creator build a
real PC release later, so treat data quality as the point. Auto-fill everything a machine can see; ask the
human only for the verdict and one comment. Fields (keep outcomes as a CLOSED vocabulary so they can be
counted):
1. **Config fingerprint (auto):** Windows edition + build, CPU, GPU (NVIDIA?), RAM, virtualization on/off,
   admin available, CapCut version + install type (standalone/Store), free disk, and this engine's version.
2. **Outcome (pick one):** Worked / Worked-after-steps / Failed-at-setup / Failed-at-render / Bad-output.
3. **Break point (pick one + verbatim error):** which step or command, and the exact error text.
4. **The tweak that fixed it (if any):** "worked after I did X." This is the seed of the next automated fix.
5. **Timestamp + engine version + CapCut version** (so fixed issues age out of the matrix).
6. **One free-text comment box, last, optional.**

## Handoff report template (write to `_pc-conversion/PC-REPORT-<date>.md`)
```
# PC Conversion Report
Engine version: <x> | Date: <ISO> | CapCut version: <x> (standalone/Store)

## Config
Windows: <edition + build> | CPU: <> | GPU: <NVIDIA? model> | RAM: <> GB
Virtualization: <on/off> | Admin: <yes/no> | Free disk: <> GB

## Outcome
[ ] Worked   [ ] Worked after steps   [ ] Failed at setup   [ ] Failed at render   [ ] Bad output

## Where it broke (if it did)
Step/command: <>
Verbatim error: <>

## What fixed it (the tweak)
<>

## Anything else (optional)
<>
```
Then ask the creator to **email this file to the creator's support address** (the address on their purchase
receipt or the creator's website). Frame it warmly: they are a "PC Pioneer," their report is exactly what
builds the real PC version, and redundant reports still help (they quantify impact). If it succeeded, say so
with extra thanks; success cases are the most valuable rows of all.

## Confidence + what MUST be tested before promising anything
- HIGH: the install one-liners, the Windows draft path, the WhisperX dependency pitfalls, native-Windows route.
- MEDIUM (version-dependent, TEST on a real Windows machine with the creator's CapCut version first): whether the
  draft JSON is plaintext or encrypted, and exactly how the engine writes media/font paths into the draft.
Do not tell a creator "this will work." Tell them "let's try it together and see, and either way what we learn
helps." That honesty is the product.

## Set UTF-8 permanently (required, one command)

```
setx PYTHONUTF8 1
setx PYTHONIOENCODING utf-8
```
Reopen the terminal afterwards.

Windows runs Python under a legacy codepage (cp1252), not UTF-8. That causes two failures that look like
unrelated bugs: printing a status symbol raises `UnicodeEncodeError` mid-step, and `open()` without an
explicit `encoding=` raises `UnicodeDecodeError` on any file containing a curly quote, an accent or an
emoji (a caption, a hook, the brand kit, a draft JSON). Roughly 129 engine files can trip one of these.
The shell scripts export it themselves, but anything Claude runs directly does not inherit that, so it has
to be set on the machine. It stays invisible until the creator's first piece of non-plain text.
