# The Intel-Mac route — setup without Homebrew

> Status: **SHIPPED to creators in v1.0.68 / v1.0.69 (2026-09-18), and live on the auto-update feed.**
> Tested as far as it can be without an Intel Mac: the stack was exercised on a genuine `x86_64`
> process under Rosetta 2 — Intel uv, Intel CPython 3.11, Intel wheels, a real transcription — and
> every branch was run. See **What was actually tested** at the end. Still unproven: real Intel
> *hardware*, which only a creator's machine can supply. It shipped before that proof existed, which
> was a deliberate call — see **What shipping early means** below.

## What broke

Homebrew's official installer now refuses to run on anything that is not Apple Silicon.
From the live `install.sh`:

```bash
UNAME_MACHINE="$(/usr/bin/uname -m)"
# On macOS, support Apple Silicon only
if [[ "${UNAME_MACHINE}" != "arm64" ]]
then
  abort "Homebrew on macOS is only supported on Apple Silicon processors!"
```

Since the entire Mac setup path in this engine is Homebrew (`check-setup.sh` hints `brew install`
for all six prerequisites, and `set-me-up` hands the creator the one-line installer), an Intel-Mac
creator hard-stops at the first real step.

**The symptom she reports is "it never asked for my password."** The installer aborts one step
*before* the password prompt, so nothing hangs, nothing errors in the engine, and the creator is left
staring at a prompt that will never come. First seen from a beta tester, 2026-09-17.

## Two machines, one message

`uname -m` returns something other than `arm64` in two very different cases:

| What she has | `uname -m` | `sysctl -n machdep.cpu.brand_string` | Fix |
|---|---|---|---|
| Apple Silicon, Terminal set to "Open using Rosetta" | `x86_64` | `Apple M...` | Untick Rosetta on Terminal (Get Info), reopen, install normally. Or `arch -arm64 /bin/bash -c "$(curl ...)"` |
| A genuine Intel Mac | `x86_64` | `Intel(R) Core(TM)...` | This document |

Non-technical version of the same question: Apple menu > About This Mac > Chip / Processor.

Check Rosetta first. It is one checkbox, and the creator then gets the normal, fully supported path.

## The route (true Intel Macs)

Every piece below was checked for a real `x86_64` macOS build.

| Need | Apple Silicon today | Intel route | Verified |
|---|---|---|---|
| ffmpeg + ffprobe | `brew install ffmpeg` | `https://evermeet.cx/ffmpeg/ffmpeg-<ver>.zip` and `ffprobe-<ver>.zip`, unzip into `~/.local/bin` (since v2.2.0: pinned to 9.0.2 and sha256-checked before unzip, because evermeet builds are unsigned; the Apple-chip martin-riedl build is checked by codesign, team KU3N25YGLU). When evermeet refuses (HTTP 429 "Too Many Connections" lasted over an hour for a creator on 2026-10-21) it is asked once more after 10 s, then the second source, `https://www.osxexperts.net/ffmpeg80intel.zip` / `ffprobe80intel.zip` (8.0, minos 11.0, also unsigned, so also sha256-pinned), and the switch is noted in `_local/fallbacks.log` | Downloaded 9.0.1; `file` reports `Mach-O 64-bit executable x86_64` |
| node >= 22 | `brew install node` | nodejs.org `osx-x64-pkg` (LTS v24.21.0) — a double-clickable installer, no terminal | `osx-x64-pkg` present in the dist index |
| uv | `brew install uv` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | `uv-x86_64-apple-darwin.tar.gz` ships on the current release (0.12.16) |
| python3 | `brew install python` | `uv python install 3.11 --default` | `cpython-3.11.16+20260901-x86_64-apple-darwin` ships in python-build-standalone |
| Pillow | `brew install pillow` | `python3 scripts/pip-install.py pillow` | `pillow-12.3.0-cp311-cp311-macosx_10_10_x86_64.whl` |
| transcription | whisperx venv (~3 GB) | **faster-whisper only, no torch** (see below) | built and run |

No sudo password is needed for any of it except the Node `.pkg`, which asks in a normal Mac
installer window, not in a terminal. That is a friendlier first step than Homebrew ever was.

## The transcription problem, and the fix

This is the part that does not have a drop-in substitute.

- PyTorch's **last macOS x86_64 wheel is 2.2.2**. Current torch is 2.14.0.
- WhisperX 3.8.6 requires `torch~=2.8.0`.

So the WhisperX venv cannot be built on an Intel Mac at any version pairing worth shipping.

What still works on Intel: **faster-whisper**, because it rides on CTranslate2, not torch.
`ctranslate2` 4.8.2 ships `cp311 macosx_11_0_x86_64`, `av` 18.1.0 ships Intel wheels, and
`onnxruntime` has three usable bands, measured from PyPI (cp311 wheels): `<=1.23.2` on macOS 13+,
`<=1.19.2` on macOS 11–12, `<=1.16.3` on macOS 10.15. From 1.24.0 there is no macOS x86_64 wheel at
all. All three sit above faster-whisper's `>=1.14` floor. `scripts/_mac-arch.sh` carries the bands
and picks the pin, so the resolver never walks the version list on the slowest machine we support. The engine already calls `faster_whisper` directly in
`verify-cut.py` with `word_timestamps=True`, so this is a path it already trusts.

`scripts/transcribe-nofw.py` is a faster-whisper-only transcriber that emits
**the identical `words.json`** the whisperx path writes:

```json
{"clips":[{"clip":"...","path":"...","duration":25.003,
           "words":[{"word":"I","start":4.21,"end":4.71,"score":0.895}]}]}
```

Verified by running it against the pitch-reel demo clip and diffing the shape against
`projects/example-reel/transcript/words.json`. Same keys, same types, same rounding.

**Two honest trade-offs:**

1. **No wav2vec2 alignment pass**, so word edges come from Whisper's own cross-attention. In the
   whisperx output, consecutive words carry small gaps (`5.584 -> 5.624`); here they are contiguous
   (`4.71 -> 4.71`). Cut points land on word boundaries with no breath room either side. That look at
   real cuts happened on 2026-10-07 and it was worse than this line said; the words are now re-stamped
   from the audio (see "Clipped line starts" at the end).
2. The venv is **175 MB instead of ~3 GB**, which on an old Intel Mac is a real gift, not a loss.

The model ladder already in `word-timings.sh` covers Intel correctly (`small` on <= 4 cores, else
`medium`), and its own comment already says an Intel Mac "has the same weak, non-accelerated CPU as
a Windows laptop." Keep that rule as-is.

## What shipping early means

This went to creators without ever running on real Intel hardware. That was a judgement call, not an
oversight: the alternative was leaving every Intel creator at a dead end with no path at all. The
checklist that used to sit here is now history, and this is where each item landed.

| Was going to be done first | Where it actually stands |
|---|---|
| Confirm the creator is truly Intel, not Rosetta | **Done and automatic.** `mac_arch_class` runs before anything is offered; `check-setup.sh` and the `set-me-up` skill each branch three ways |
| Run the route end to end on an actual Intel Mac | **Still not done.** Rosetta 2 is a real `x86_64` process but not a real old chip. This is the one open risk |
| Only then touch `check-setup.sh` and the `set-me-up` skill | **Done.** Both branch on `mac_arch_class`; neither prints a `brew install` line to an Intel Mac any more. `ai-content-engine/.claude/skills/set-me-up/SKILL.md` was fixed the same way |
| Decide the honest ceiling | **Partly.** `check-setup.sh` says "supported but slow" at setup, and `mac_intel_supported` refuses below macOS 11 outright. It is still not said before purchase |

**The one thing still owed:** a real Intel Mac. Two beta members could supply it and neither has
reported back: one on a confirmed Intel machine (a 2019 13-inch MacBook Pro), and one whose chip was
never confirmed (see below).

## Do not assume every "older Mac" report is this bug

Two beta members reported chip trouble within a day of each other and they are **not** the same case.

- **Tester A**, 2026-09-18: setup never asked for her password. Confirmed Intel. This document.
- **Tester B**, 2026-09-15/16, in the beta feedback channel: errors and crashes she put down to an
  older chip, and waiting while Claude rebuilt pieces from scratch because of it. **Her chip was never confirmed.** She was asked for the hardware
  report twice and has not sent it. "Older Mac" from a non-technical creator can just as easily mean
  an M1, which is `arm64` and takes the normal Homebrew path untouched by any of this.

Her symptom is also matched by three **chip-agnostic** setup bugs fixed in v1.0.69 — the
`LOCALAPPDATA: unbound variable` abort, the Python workspace build failure on newer macOS, and the
launcher skipping setup's repairs. Any of those three produces "errors and crashes" on *any* Mac.
Do not close her case as an Intel case without the report.

---

# Getting the data back

There is no Intel Mac on this side. Every number about how this route actually behaves has to come
home from a creator's machine, so the route is built to produce those numbers as a side effect of
being used rather than as a favour we ask for.

Collection point is the tool that already exists: **`python3 product/make-handoff.py
hardware-diagnostic`**, which a creator reaches by saying *"run a hardware check."* It writes a
report to `_handoff/` for her to read, and she emails it in if she chooses. Voluntary, hardware and
timings only, never auto-sent. That posture is deliberate and is not to be replaced with a relay
(see `support-intake/README.md` — an auto-send relay existed once and was removed on purpose).

## What now feeds it

**1. `system_info()` gained the fields this route turns on** (done):

| Field | Why it is there |
|---|---|
| `mac_arch_class` | `arm64` / `rosetta` / `intel`. The thing that decides the whole route. |
| `macos_version` | Picks the onnxruntime pin: `<=1.23.2` on macOS 13+, `<=1.19.2` on 11–12, `<=1.16.3` on 10.15. |
| `cpu_physical_cores` | Alongside `cpu_logical_cores`. See the heuristic note below. |
| `ffprobe`, `uv` | Were checked nowhere before, and both are prerequisites. |
| `tool_origins` | Redacted paths. `~/.local/bin` = Intel route, `/opt/homebrew` = Apple Silicon, blank = not on PATH in that shell, which is the most common fresh-machine failure. |
| `install_route` | Read from `_local/install-route.json` when the installer recorded one, inferred from tool locations otherwise, and labelled as inferred either way. |

**2. `scripts/transcribe-nofw.py` writes `.transcribe-diagnostics.json`** (done) — same filename,
same location and same shape as the whisperx path, so the diagnostic picks it up with no changes of
its own. It carries `engine: "faster-whisper"`, a key the whisperx path never writes, which is how
the two are told apart later. The field that matters is `realtime_ratio`: wall-seconds per second of
footage. On an M1 Pro with the tiny model it is 0.03. Whatever comes back from a 1.4 GHz i5 is the
first real Intel number this engine has ever had.

**3. Still to write: `_local/install-route.json`**, by the installer, one object:

```json
{"when": "<iso8601>", "arch_class": "intel", "macos_major": 15,
 "steps": [{"tool": "ffmpeg", "source": "evermeet.cx", "seconds": 34.2,
            "exit": 0, "version": "9.0.1", "landed": "~/.local/bin/ffmpeg"}]}
```

One entry per tool, whether it succeeded or not. A failed step is more valuable than a clean one.
Until this exists the diagnostic infers the route from where the tools ended up, which answers
*where* but never *how long* or *what went wrong on the way*.

## The heuristic this machine already broke

`word-timings.sh` decides "weak machine" with `os.cpu_count() <= 4`, and `os.cpu_count()` counts
hyperthreads. A quad-core i5-8257U reports **8**, passes the test as if it were strong, and gets
handed `medium` on a chip that cannot carry it. That is the multi-hour transcribe the file's own
comments were written to prevent, arriving through the front door.

`transcribe-nofw.py` now counts physical cores and treats any true Intel Mac as weak regardless.
**`word-timings.sh` still has the original test** and should get the same fix.

## What to ask the first Intel creator

Twice, and no more than twice:

1. **Right after setup finishes** — "run a hardware check." Catches chip, macOS, cores, and where
   every tool landed. Confirms the route worked before any footage is involved.
2. **After her first reel** — same command. Now it also carries the real transcribe and render
   wall-times, which is the number nothing on this side can produce.

---

# What was actually tested

Rosetta 2 turns an Apple Silicon Mac into a real `x86_64` test bed. Not a simulation of Intel — the
processes below genuinely report `x86_64`, resolve Intel wheels and execute Intel binaries. What it
cannot reproduce is Intel *hardware speed*, so every timing here is a floor, never a forecast.

**Machine detection — all three classes, none of them faked where it mattered**

| Case | How it was produced | `mac_arch_class` |
|---|---|---|
| Apple Silicon | this Mac, natively | `arm64` |
| Rosetta | `arch -x86_64`, real translation | `rosetta` |
| True Intel | `x86_64` process + no `hw.optional.arm64` | `intel` |

The Python side (`make-handoff.py`) was checked the same three ways in real `x86_64` processes, not
against stubs — an early stub run reported `arm64` for the Intel case, because `platform.machine()`
does not go through a fake `uname`. The code was right; the harness was not. Worth remembering:
**a stub can only lie to a subprocess.**

**The install route, run for real**

- `intel-mac-install.sh ffmpeg` executed end to end: fetched from evermeet.cx, verified `x86_64`
  with `file`, cleared quarantine, landed in `~/.local/bin`, **25 seconds**.
- Both binaries then did real work — a synthesised tone and a cut from the pitch-reel clip both
  transcoded, and `ffprobe` read them back.
- Refusals fire correctly on all three wrong machines: Apple Silicon ("use Homebrew"), Rosetta
  ("untick one checkbox"), and a simulated macOS 10.15 Intel Mac ("below the floor, stop").
- `_local/install-route.json` records every step with real timings, and **no account name reaches
  it** — `$HOME` becomes `~` before anything is written. Verified by grep.

**The transcription stack, on genuine x86_64**

Built with the Intel `uv` (`uv 0.12.16 … x86_64-apple-darwin`) and a uv-managed
`cpython-3.11.16-macos-x86_64`:

```
ctranslate2 4.8.2   onnxruntime 1.23.2   av 18.1.0   faster-whisper 1.2.1   torch: absent
```

`onnxruntime` landed exactly on the pin `_mac-arch.sh` computes. A real 25-second clip transcribed
to 48 correct words, average word confidence 0.952, and the model ladder chose `small` on its own
because a true Intel Mac is classed weak regardless of core count.

`realtime_ratio` **0.40** — ten seconds of work per twenty-five seconds of footage, under emulation
on an M1 Pro. A 1.4 GHz i5 will be slower than that and nobody here can say how much slower. It is a
floor. The number that matters comes home from the first real machine.

**Found by testing, fixed**

- **`~/.local/bin` was invisible to the engine for everything except `uv`.** The whole Intel route
  installs there, and `scripts/_path-shim.sh` — the thing that repairs PATH before every tool call —
  listed that directory for `uv` alone. So a perfect install would still have reported ffmpeg,
  ffprobe and python3 as missing, which is the most demoralising failure shape there is: you did it
  all right and the checker says you did not. Now listed for every tool. Homebrew still takes
  precedence where it exists, so nothing changes on an Apple Silicon Mac.
- **`uv pip install --python <interpreter> pillow` does not work.** uv refuses to install into a
  bare managed interpreter ("Consider creating a virtual environment"), and Pillow has to land in
  the interpreter itself because `check-setup.sh` tests `import PIL` through whichever `python3`
  runs. The engine already had the answer — `scripts/pip-install.py` installs into the interpreter
  that runs it and handles uv's refusal. Also: `uv python install 3.11` needs **`--default`**, or
  only `python3.11` is created and plain `python3` stays missing on a Mac with no Homebrew Python.
  Both caught on real runs. The obvious commands look right and fail.

- CTranslate2 links Intel MKL, which prints `Intel MKL WARNING: Support of … SSE4.2 … deprecated` on
  Intel. Harmless, and the first thing a creator would see during her first transcription, containing
  the words WARNING and deprecated, on the machine she has just been told is the unusual one. Now
  filtered the same way the torchcodec noise is.
- The weak-machine test counted hyperthreads. A quad-core i5-8257U reports 8 and would have been
  handed `medium`. Now counts physical cores and treats any true Intel Mac as weak.

**Full integration**

`word-timings.sh` with `REELS_ENGINE_FORCE_NOFW=1`: built its own separate venv, announced
"faster-whisper" rather than "WhisperX", wrote `words.json` and `.transcribe-diagnostics.json`,
persisted the canonical transcript, and reused it on a second run instead of re-transcribing. The
existing rough-cut regression tests still pass.

**Not tested, and cannot be from here**

Real Intel hardware. Node's `.pkg` actually installing (it hands off to Apple's installer UI and
wants a password). Gatekeeper's behaviour on a machine that has never run an unsigned binary. Whole
reel renders on a slow chip. Every one of those needs a creator's Mac.

---

# The hole audit (after v1.0.68)

Getting setup working was only half of it. Everything downstream still assumed the WhisperX venv
exists at its one hardcoded path, and on an Intel Mac that path is never created. Each of these was
found by grepping for that assumption rather than by anything failing, which is the point: they
would all have failed **silently, on the creator's first reel**, after a setup that reported success.

| Where | What would have happened | Status |
|---|---|---|
| `verify-cut.py` | The cut listen-back found no interpreter and every cut in the job went unchecked. It only ever needed `faster_whisper`, which IS present — it was just looking in one place. | **fixed** — resolves either venv, env overrides first |
| `stitch-cut.sh` | The de-stutter pass was skipped in total silence: the "skipped" message lived inside the same `if` block as the work, so a failed guard printed nothing at all. | **fixed** — detects the case and says so, in three plain lines |
| `clean_cut.py` | Reported `SKIPPED (WhisperX venv missing)`, which reads as a broken install rather than a permanent, explainable limit. | **fixed** — names the real reason on Intel |
| `smoke-test.sh` | Reported speech transcription as not-ready on every Intel Mac. A false alarm in the one place a creator goes to ask whether her machine is fine. | **fixed** |
| `word-timings.sh` adoption | A working faster-whisper venv that lost its sentinel was deleted and rebuilt instead of adopted, because adoption only asked `import whisperx`. | **fixed** |
| `word-timings.sh` forced path | `REELS_ENGINE_FORCE_NOFW=1` outside the engine folder would exec `/scripts/transcribe-nofw.py` and fail with a file-not-found that explains nothing. | **fixed** — refuses with the real cause |

## Genuine limits on an Intel Mac, not bugs

These cannot be fixed, because the software underneath has no Intel build. They are listed so nobody
spends an afternoon rediscovering them.

- **The quick-restart de-stutter pass does not run.** `trim-restarts.py` needs torchaudio. `stitch-cut.sh`
  now says this out loud instead of skipping in silence; the creator trims a restarted sentence by
  hand. Everything else in the cut is unaffected.
- **`vo-cutgrid.py` falls back.** Voiceover reels lose the precise WhisperX word timing and use the
  caller's fallback path. It already degrades by design, and it could be pointed at faster-whisper
  later — worth doing, not urgent, and Module 5 is still draft.
- **MusicGen cannot generate a music track offline.** `gen-music.py` imports torch. Sourced music is
  unaffected; only the generated-track fallback is gone.
- **`CLAUDE.md` and the rough-cut `SKILL.md`** both tell Claude to run trim-restarts via the whisperx
  venv path. On an Intel Mac that instruction cannot be followed. Low harm (the wrapper scripts all
  guard correctly now) but it should be reworded next time either file is touched.
- **Baked graphics and captions render slowly, and a correct render looks like a broken one.** The
  renderer draws one frame at a time in a headless Chromium, so wall-clock time scales with clip length
  and core count. Measured on a creator's 2017 i5-7360U (2 cores, 8 GB, macOS 13.7.8): a **53-second
  composition rendered ~1,585 frames in roughly 6 minutes**, steady the whole way, no stall. That is
  normal for the hardware. Nothing in the engine caps it (`reel_render.py` is uncapped on purpose, see
  the watchdog note in the changelog for v1.0.86), so the danger is a creator or a session deciding it is
  stuck and killing it. That is exactly what produced the September 2026 "Intel caption hang": the job
  needed ~360s and was aborted at 200.6s from outside the engine, which read as an infinite hang and
  sent three people looking for a font bug that was not there.

  The sales copy already says an Intel Mac takes longer, so the creator is not missing the expectation.
  What she needs is to SEE it working. Both render calls run without capture, so the renderer's own
  progress streams straight to her screen, and since v1.0.86 a renderer that goes quiet for ten minutes
  prints one line and writes a note without cancelling anything. Point her at that: a render that is
  still printing is a render that is fine. Do not add a time estimate anywhere else; the number above is
  one machine, and a different Intel Mac with a different clip will not match it.

  If she would rather not wait at all, `product/build-captions.py` builds the same captions as editable
  CapCut text and never starts the renderer.

## Update before setup: the bootstrap (v1.0.74)

The route above shipped in v1.0.68, but the FIRST creator it was built for could not receive it. Her copy
predated it, `update me` is `scripts/apply-update.py` (Python), and her fresh Mac had no Python:
`/usr/bin/python3` is Apple's placeholder, which opens the "install the developer tools?" dialog and exits
1. So the updater's own "does python3 run" probe popped a dialog and the update never happened. The fix
for Intel Macs could not reach an Intel Mac.

`scripts/ensure-python.sh` closes that loop and the `update` skill runs it first:

1. `scripts/_python3-shim.sh` now recognises the placeholder by path plus `xcode-select -p` and never
   executes it (`_P3_OK=0`), then searches the real on-disk homes (uv's `~/.local/bin/python3` first).
2. If nothing runs, `ensure-python.sh` installs uv (its own installer, `~/.local/bin`, no sudo) and
   `uv python install 3.11 --default`, exactly what `intel-mac-install.sh python` does, so a later
   `set me up` finds it already there. It prints the interpreter path on stdout and nothing else.
3. `check-setup.sh` and `intel-mac-install.sh` no longer touch the placeholder either, so the dialog only
   ever appears when a creator chooses to install Apple's tools herself. The step log quotes its values with
   `json_str` (`_mac-arch.sh`). The two download lookups, the ffmpeg/ffprobe zip URL from evermeet.cx and
   the Node LTS from nodejs.org's `index.json`, are now read with `tr`, `sed` and `grep`. They used to go
   through `python3 -c`, and because ffmpeg is the route's first step and `node` can be asked for on its
   own, both ran before any real Python existed: on a fresh Intel Mac the dialog opened and both installs
   failed at their first line.

Guarded by `product/tests/test_python_bootstrap.py` (run by `check-ship.sh`), which stands up a fake
fresh Mac: a placeholder that records every execution, `xcode-select` failing, uv stood in by a stub. Its
section 5 also runs `intel-mac-install.sh ffmpeg` and `node` end to end on a simulated fresh Intel Mac,
with curl stood in by a stub that serves both indexes offline, and fails on any bare `python3` call in the
route.

## The dependency drifted out from under the route (v1.0.78)

> **Superseded in v2.2.0:** `oss2` (unused Aliyun upload code) was removed from VectCutAPI, which removed
> `cryptography` and its `<49` Intel pin with it. The section below is kept as history and as the general
> lesson about pins drifting.

The route above installs cleanly, then the internet moves. `cryptography` **49.0.0 dropped its macOS
`universal2` wheel and now publishes `macosx_11_0_arm64` only** — 49.0.0, 50.0.0 and 50.0.1 all checked
on PyPI, so this is the new normal, not one bad release.

Nothing in this engine asks for `cryptography`. It arrives four levels down:

```
requirements.txt -> oss2 -> aliyun-python-sdk-core -> cryptography  (>=3.0.0, otherwise unpinned)
```

Unpinned means pip takes the newest, finds no wheel it can use on an Intel Mac, falls back to the
sdist, and tries to **compile** it — which needs a Rust toolchain and Apple's Command Line Tools.
Neither is on the machine this whole route exists to serve. The creator-visible symptom is that
`setup-editor-engine.sh` runs for a while and then dies in the middle of "Installing the engine's
tools", with a compiler error nobody can act on. Reported live by an Intel-Mac creator.

The fix is one marker-gated line in `product/engine/VectCutAPI/requirements.txt`:

```
cryptography<49; sys_platform == "darwin" and platform_machine == "x86_64"
```

- 48.0.x still ships `macosx_10_9_universal2`, which installs on Intel with no compiler at all.
- `aliyun-python-sdk-core` only asks for `>=3.0.0`, so 48.x satisfies the chain.
- The marker keeps Apple Silicon and Windows on current `cryptography`. It also catches an Apple
  Silicon Mac running a Rosetta'd terminal, whose Python reports `x86_64` and hits the same wall.
- It belongs in `requirements.txt`, not in the setup script. Every route that installs the engine's
  tools reads that file, so the pin applies itself and there is no second code path to keep in step.

Guarded by `product/tests/test_intel_wheels.py` (run by `check-ship.sh`), which fails both ways a
later tidy-up could break it: the pin going missing, and the pin losing its marker and quietly
downgrading every machine.

**Re-test line** — when this prints an Intel-compatible wheel, the pin can go:

```bash
curl -s https://pypi.org/pypi/cryptography/json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['info']['version'], [f['filename'] for f in d['urls'] if 'macos' in f['filename']])"
```

Today that prints only `macosx_11_0_arm64` filenames. A `universal2` or `x86_64` filename in that
list means Intel is served again.

**The general lesson, which is not about `cryptography`.** This route's pins are measured against
PyPI at a moment in time, and transitive dependencies keep moving after a version ships. An Intel
install breaking months later is the expected failure mode here, not a surprise — when a creator on
Intel reports setup dying mid-install, check for a *newly* wheel-less dependency before assuming the
route itself regressed.


## Apple-chip Macs below Homebrew's floor use this route too (v2.0.12, 2026-09-30)

A launch-day creator on an Apple-chip Mac with macOS 13.x got stuck at Homebrew's "Installing Command Line
Tools for Xcode-14.3 / Finding available software". Homebrew's installer now says `MACOS_OLDEST_SUPPORTED="15.0"`,
and formulae.brew.sh lists arm64 bottles for ffmpeg, node and uv on sequoia/tahoe and newer only, so
below 15 every `brew install` compiles from source. `mac_install_route` (scripts/_mac-arch.sh) now returns
`direct` for an arm64 Mac below `MAC_BREW_OLDEST` (15), and this script serves it with Apple-chip builds:

| Tool | Apple chip source | Vetted |
|---|---|---|
| ffmpeg / ffprobe | `ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/<tool>.zip`; when it fails (HTTP 521, server down, all through 2026-10-21) or its binary is not signed by Team KU3N25YGLU, it is asked once more after 10 s, then the second source `https://www.osxexperts.net/ffmpeg9arm.zip` / `ffprobe9arm.zip`, sha256-pinned (it is only ad-hoc signed), switch noted in `_local/fallbacks.log` (since v2.3.8) | martin-riedl 9.0.2: arm64, minos 12.0, system libs only, Developer ID signed, every encoder/filter the engine calls. osxexperts 9.0 (vetted 2026-10-21): arm64, minos 12.0, system libs only, ad-hoc signed, every encoder/filter the engine calls; the file name only says "9", so a later 9.x there fails the pin closed until it is moved |
| uv | astral.sh installer (aarch64 build) | unchanged |
| Python 3.11 + Pillow | uv-managed CPython, Pillow wheel | unchanged |
| Node | nodejs.org universal .pkg, **Node 22 below macOS 13.5** (`mac_node_line`) | Node 24 needs 13.5 per its BUILDING.md; this also fixed Intel Macs on 11 to 13.4 |

Only the install route changes. The chip is still arm64, so WhisperX, restart trimming and music generation
all run. One more fix rode along: PyAV's arm64 wheels need macOS 14 from av 16 on, so on macOS 13 the
resolver picked av 18.1 as a SOURCE build. `word-timings.sh` now passes `--only-binary av` on every Mac;
macOS 13 resolves av 15.1.0 (minos 13.0) and 14+ is unchanged.

Proven 2026-09-30 on a real Apple-chip Mac with `sw_vers` shimmed to 13.4 and a throwaway HOME: the full
`intel-mac-install.sh all` ran in 15 s against the live downloads (Node v22.23.3, notarized), the ffmpeg
encoded H.264/AAC and ran loudnorm, and `uv pip install --target … --python-platform aarch64-apple-darwin`
with `MACOSX_DEPLOYMENT_TARGET=13.0` installed all 104 whisperx packages with nothing to compile.
`MAC_DIRECT_ROUTE=1` forces the route on a current Mac for exactly this kind of check. Guard:
`product/tests/test_mac_route.py` (check-ship gate 23).


## A supported Mac whose Command Line Tools download fails takes this route too (2026-10-02)

A creator (Maria) on an Apple-chip Mac on macOS 15+, so route `brew`, ran the Homebrew installer from "set me up"
and got Apple's popup partway through: **"Can't install the software because it is not currently available
from the Software Update server."** Homebrew fetches Apple's Command Line Tools from that server and cannot
continue without them (it clones itself with git, and git is one of those tools), so the engine had no next
step. The same failure can show in the Homebrew Terminal as `xcode-select: error: invalid developer directory`.

The fix is this route, which needs none of Apple's developer tools. The installer used to refuse a `brew`
Mac outright; it now names the fallback in its refusal, and forced with `MAC_DIRECT_ROUTE=1` it runs:

```bash
MAC_DIRECT_ROUTE=1 bash scripts/intel-mac-install.sh all
```

On a Mac with no Homebrew that run also writes a pin, `~/.local/share/reels-editing-engine/mac-route`, which
`mac_install_route` honors for as long as no Homebrew is installed. Without it every later check said
`brew` again: `check-setup.sh` printed the Homebrew line she had just watched fail. The pin lives beside
her tools, not in the engine folder, so a fresh engine download keeps it; a Homebrew that later works
takes the Mac back to `brew` by itself; and a Mac that has Homebrew (a developer's test run) is never
pinned. `check-setup.sh` gives a pinned Mac its own message (Apple's server, not her macOS, so no update
advice), and the Homebrew line on a `brew` Mac now carries the fallback underneath it.

**Proven 2026-10-02 on a real Apple-chip Mac (macOS 26.6.2) with the tools hidden** (`DEVELOPER_DIR` pointed
at a folder that does not exist, a throwaway HOME, a UTF-8 locale like a real Terminal, and tripwires on
git, python3, make, cc/clang, xcrun, install_name_tool, otool, lipo and strip): `MAC_DIRECT_ROUTE=1 ...
all` finished with exit 0 against the live downloads (ffmpeg 9.0.2 arm64, uv 0.12.22, CPython 3.11.17,
Pillow 12.3.0, Node v24.21.0 .pkg) and pinned the Mac; `check-setup.sh` passed every core tool from
`~/.local/bin` (Node unpacked from that .pkg); a fresh `npx hyperframes@<pin>` install (0.8.43 at the time), postinstalls
included, exited 0, and so did its `browser ensure`; the transcriber's `whisperx`
resolves to 107 arm64 wheels with `--only-binary :all:` for macOS 15. Final rerun: zero tripwire hits. The
only other things that would reach for git or a compiler are two optional HyperFrames extras the engine
never uses (the ltx-2-mlx local video model and whisper.cpp).

That run turned up four more things, all fixed with it:

0. **hyperframes runs `git ls-remote https://github.com/heygen-com/hyperframes.git`** in the background
   of any command (its "are your agent skills current?" check, `checkSkills` in dist/cli.js; once a day
   when it can save its cache, every run when it cannot). On a Mac without the tools that is Apple's git
   placeholder, so the dialog would pop during setup's `browser ensure` and again mid-render. No env
   switch covers it (`HYPERFRAMES_NO_UPDATE_CHECK` gates only the version check), but it fails soft: when
   git errors it fetches the manifest over HTTPS. So `intel-mac-install.sh` (step `git`, part of `all`)
   puts a stand-in in `~/.local/bin/git` when /usr/bin/git is a placeholder: it prints "not installed"
   and exits 1, and once real developer tools exist it `exec`s Apple's git. A real git already in
   `~/.local/bin` is never overwritten. This covers Intel and below-15 Macs on this route too.

1. **uv calls Apple's `install_name_tool` placeholder** after downloading a Python (`otool -L` shows it
   links libxcselect, like git and python3). On a Mac without the tools that opens the "install the
   developer tools?" dialog again. `mac_clt_shield` puts a quiet stand-in in front of PATH for every
   `uv python install` / first-run `uv venv` (this installer, `ensure-python.sh`, `word-timings.sh`); uv
   only warns ("Failed to patch the install name ... native extensions"), and the engine builds none.
2. **`xcode-select -p` is not proof the tools exist.** It prints any configured path with exit 0
   (`DEVELOPER_DIR=/nonexistent xcode-select -p` answers `/nonexistent`), which is exactly what a failed
   install can leave behind. `mac_clt_has` / `mac_clt_stub` check the tool is really in that folder;
   `_python3-shim.sh`, `check-setup.sh` and the problem report (`collect-report.sh`, which ran
   `git --version`) all use it now, so none of them can pop the dialog.
3. **`say "downloading Node $ver…"` crashed the Node step in any UTF-8 terminal.** Bash 3.2 reads the
   first byte of "…" into the variable name, and under `set -u` that is "ver?: unbound variable", one step
   from the end of every Terminal-run install. It slipped past the 9/30 proof because that ran without a
   locale. Braced to `${ver}…`; test_mac_route.py now fails on any unbraced `$name` before a non-ASCII glyph.

Guard: `product/tests/test_mac_route.py` sections 7 to 9 (8b is the git stand-in). Creator reply: your-brand-hq/support/REPLY-LIBRARY.md B8.

## A loaded Intel Mac: the check's page budget, unpunctuated transcripts, takeover layers (2026-10-07)

Three things one Intel Mac (8 GB, macOS 12, so below the floor, but each one would hit a 13+ Intel Mac too)
turned up in a single report:

1. **The pre-render check ran out of time loading its own page.** HyperFrames gives the check's browser
   page max(10 s, `--timeout`) to load, and the engine passes 10 s on anything that is not Apple Silicon, so
   the budget was exactly its floor. A busy 8 GB machine missed it and a clean composition was refused as if
   the composition were wrong. `npx_run.hf_check_env()` now gives the check (never the render, whose own
   default is 60 s) 45 s on any non-Apple-Silicon machine and 60 s at 8 GB or less; it is a ceiling, not a
   wait. A navigation timeout is reported as the check not starting in time (exit 4), never as a finding.
   Override: `REELS_ENGINE_HF_NAV_TIMEOUT_MS`. Guard: `product/tests/test_check_nav_budget.py`.
2. **faster-whisper can return words with no sentence punctuation.** Every sentence split looked only for
   `.`, `!` or `?`, so the whole reel was one sentence: spoken cues collapsed to one, and a takeover ("to the
   end of its sentence") would have run to the end of the reel. On a transcript with no sentence punctuation
   anywhere, a sentence now ends at a pause measured against the speaker's own rhythm
   (`beat-lines.py` `pause_threshold`, used by `spoken_cues.py` and `build-reel-type.py`). A punctuated
   transcript is split exactly as before. Guard: `product/tests/test_unpunctuated_transcript.py`.
3. **A separated takeover layer was refused twice over.** Its render was judged on 16 evenly spaced frames
   that all missed a two-second takeover ("the render contains NOTHING"), and the face check could only refuse
   a layer that covers her by design. The render gate now also looks inside every clip window the composition
   holds, and `separate_layers.sh` renders a takeover-or-breakaway-only layer with `--no-subject`
   (`REEL_RENDER_EXTRA` passes anything else, such as `--low-memory`). Guards:
   `product/tests/test_render_brief_layers.py`, `product/tests/test_separate_layers_render.py`.

## Clipped line starts: the pauses are put back from the audio (2026-10-07)

An Intel creator (i5-1038NG7, 16 GB, macOS 26, engine 2.2.2) reported the rough cut clipping the start of her words
on many lines, with measurements: 304 of 350 word pairs touching, 39 of 43 cut starts left unadjusted.

Reproduced on this side without Intel hardware, by running this route's own listener (`transcribe-nofw.py`,
faster-whisper `small`, cpu int8) over the 24 clips her own cuts use (85 minutes of the creator's takes) and
comparing every word with the aligned WhisperX transcript of the same clip:

- **The start stamps are early, not late.** A word said after a pause was stamped a median 363 ms before it really
  began (89 in 100 more than 100 ms early). The pause is folded into the next word. End stamps are close (median
  47 ms early). 87 in 100 word pairs touch, against 1 in 100 aligned.
- **What that did to her cuts.** Each kept line was rebuilt from those stamps the way `transcript-cut.py` writes
  one and run through the unchanged `snap-to-sound.py`, then judged by the neutral room-tone judge in
  `dev-tools/cut-timing/before-after.py`. 48 in 100 cut starts opened on stray sound (dead air, a breath, the tail of
  a dropped retake), against 5 in 100 aligned: snap-to-sound looks for an onset around the stamp, and the real onset
  was a third of a second past it. 59 in 100 cut ends clipped their word, because the next word's stamp (which
  touches this one's end) fenced the search off. Most kept lines also "abutted" and were never cut at all, so the
  pauses between them stayed in.

**Fix:** `scripts/restamp_words.py`, called by `transcribe-nofw.py` on every clip before words.json is written.
For each word pair it finds held quiet between the earlier end stamp and the later end stamp and moves the boundary
onto it (earlier word ends where the quiet begins, later word starts where it ends). Quiet is 16 dB under the
pair's speaking level OR 8 dB over the background around it, which is what finds a pause in a noisy room. Same
judge, same 507 cuts: stray-sound starts 48 → 15 in 100, clipped ends 59 → 29, clipped starts unchanged (6 to 7
in 100), 92 more joints cut. Words in running speech are untouched. Costs about 20 s per 85 minutes of footage.
Best effort: if the audio cannot be read the words are written as heard, as before. The count lands in
`.transcribe-diagnostics.json` as `restamped_pairs`. Test: `product/tests/test_nofw_restamp.py` (check-ship gate 23).

**Still true on this route:** no restart trimming (`trim-restarts.py` needs WhisperX), and starts are still looser
than aligned (a median 53 ms early after a pause, against about 0). A creator with an Apple-chip Mac to borrow gets the
aligned route automatically.

**Transcripts made before the fix are repaired on reuse.** `word-timings.sh` hands a heard job's saved words.json
straight back, so an old Intel transcript would have kept its folded pauses for good. On the Intel route only,
`repair_older_intel_transcript` runs `restamp_words.py repair` on it first: clips with no `restamped` key that look
unaligned (more than half their pairs touching) are re-stamped from the footage via ffmpeg, the old file goes to
`transcript/history/`, and every clip is marked so it is never looked at twice. Aligned transcripts, other routes
and moved footage are untouched.

