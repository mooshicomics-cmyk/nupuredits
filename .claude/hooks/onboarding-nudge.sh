#!/usr/bin/env bash
# onboarding-nudge.sh, run when a session starts: a short briefing about THIS install for Claude, read
# before her first message. Each piece below goes in only when it is true right now, and when none is, the
# hook prints nothing. It never ends a session: the exit status is 0 on every path.
#
#   machine note       _local/machine-notes.md exists: setup found that Claude's installs do not reach this
#                      computer, so Claude hands her lines to paste instead
#   missing tools      ffmpeg, ffprobe, node or uv are not on this machine
#   saved preferences  Part C of brand-kit.md holds at least one taught preference
#   stopped update     an update was interrupted partway (window closed, app quit, power cut)
#   unfinished update  an update landed but scripts/post-update.py has not run for this version
#   setup not done     brand-kit.md still has blank fields, the same count CLAUDE.md's "Fresh install?"
#                      section uses: any `{{` or an older copy's `<<`, never the example `{{this}}` a
#                      2.2.0-2.2.2 kit shows in its how-to line
#
# Before any of that it also repairs the global /studio link, silently, once she has said yes to it.
#
# set-me-up may not have run yet, so nothing here needs more than bash and the stock commands a new Mac and
# Git Bash both carry (Windows runs the engine in Git Bash, never WSL2 or PowerShell). Paths are relative to
# the engine folder, where Claude Code starts the hook.

# SessionStart reads extra context from a JSON object on stdout. Every message below is written as JSON
# string content already (\n for a line break, \" for a quote), so it goes in as it is.
emit() { printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$1"; }

# --- Keep the global /studio command working from ANY folder, once she has said yes to it (opt-in). ---
# Links this engine's Studio skill into the user's global Claude skills dir. Silent, idempotent, and
# HARDENED against the dangling-link bug that used to break /studio everywhere:
#   1. If a VALID global /studio already resolves (its SKILL.md is reachable), leave it ALONE. Never
#      repoint a working link, so a session opened in another copy of the engine can never hijack it.
#   2. Only heal a MISSING or DANGLING link, and NEVER from a throwaway location: system temp
#      (/tmp, /var/folders, $TMPDIR), any mktemp "tmp.XXXX" dir, or the make-ship "dist/" staging tree
#      that later gets rm -rf'd. Pointing the global link at a temp/staging copy is exactly what dangled
#      and broke /studio in every other folder. In a throwaway session we do nothing (a missing link for
#      that one temp session is fine; the next session in the real engine heals it).
# Writes NOTHING to stdout (this hook's stdout must stay valid JSON) and can never fail the session.
# Never clobbers a real folder the user placed at ~/.claude/skills/studio.
#
# Windows (Git Bash) needs its own kind of link. There `ln -s` quietly makes a COPY (MSYS's default), and a
# copy never follows an engine update, so /studio went stale after the first update and stayed that way.
# On Windows the link is a directory junction instead: a real link that needs no admin rights and no
# Developer Mode. A stale copy an earlier version of this hook left behind is recognised by its SKILL.md and
# swapped for a junction; it is moved aside to ~/.claude/, never deleted, and put back if the junction
# cannot be made.
_win_studio_link() {   # _win_studio_link <src> <link> <stale copy: 0|1>
  local aside=""
  if [ "$3" -eq 1 ]; then
    aside="$HOME/.claude/studio-old-copy-$(date +%Y%m%d%H%M%S)"
    mv "$2" "$aside" || return 1
  elif [ -L "$2" ]; then
    rm -f "$2" 2>/dev/null || rmdir "$2" 2>/dev/null
  fi
  if MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' cmd /c mklink /J "$(cygpath -w "$2")" "$(cygpath -w "$1")"; then
    return 0
  fi
  if [ -n "$aside" ] && [ ! -e "$2" ]; then mv "$aside" "$2"; fi
  return 1
}
{
  SRC="$PWD/.claude/skills/studio"
  LINK="$HOME/.claude/skills/studio"
  CONSENT="$PWD/_local/studio-global.ok"
  # Opt-in only (v2.2.0): linking /studio into ~/.claude/skills makes it load in EVERY Claude project on
  # her computer, so it needs her yes first (set-me-up step 6, or running ./install-studio.sh herself).
  # A link she already has that points at this engine counts as that yes, so existing installs keep healing.
  if [ ! -f "$CONSENT" ] && [ -e "$LINK/SKILL.md" ] && [ "$LINK/SKILL.md" -ef "$SRC/SKILL.md" ]; then
    mkdir -p "$PWD/_local" && : > "$CONSENT"
  fi
  win=0; case "$(uname -s 2>/dev/null)" in MINGW*|MSYS*|CYGWIN*) win=1 ;; esac
  # A stale Windows copy: a real folder (not a link, not this engine's own folder) holding THIS skill.
  stale=0
  if [ "$win" -eq 1 ] && [ -d "$SRC" ] && [ -d "$LINK" ] && [ ! -L "$LINK" ] \
     && [ ! "$LINK/SKILL.md" -ef "$SRC/SKILL.md" ] \
     && grep -q '^name: studio' "$LINK/SKILL.md" && grep -q 'The craft layer' "$LINK/SKILL.md"; then
    stale=1
  fi
  # Act only when this folder has Studio AND the global /studio is missing or broken (SKILL.md
  # unreachable through the link), or is that stale copy. A valid link makes this test false, so it is
  # left untouched.
  if [ -f "$CONSENT" ] && [ -d "$SRC" ] && { [ ! -e "$LINK/SKILL.md" ] || [ "$stale" -eq 1 ]; }; then
    here="$(cd "$PWD" 2>/dev/null && pwd -P)"     # canonical path (resolves /tmp -> /private/tmp, etc.)
    tmpd="${TMPDIR:-/no-such-tmpdir}"; tmpd="${tmpd%/}"
    throwaway=0
    case "$here/" in
      /tmp/*|/private/tmp/*|/var/folders/*|/private/var/folders/*) throwaway=1 ;;
      */dist/*|*/.ship-state/*|*"/tmp."*) throwaway=1 ;;
      "$tmpd"/*) throwaway=1 ;;
    esac
    # Heal only from a real (non-throwaway) engine copy, and only over a missing path, an existing
    # symlink, or the stale Windows copy above — never over a real folder the user placed there.
    if [ "$throwaway" -eq 0 ] && { [ ! -e "$LINK" ] || [ -L "$LINK" ] || [ "$stale" -eq 1 ]; }; then
      if [ "$win" -eq 1 ]; then
        mkdir -p "$HOME/.claude/skills" && _win_studio_link "$SRC" "$LINK" "$stale"
      else
        mkdir -p "$HOME/.claude/skills" && ln -sfn "$SRC" "$LINK"
      fi
    fi
  fi
} >/dev/null 2>&1 || true

# A machine note is written by `set-me-up` when it finds that Claude's installs do not reach this
# computer (the app is containerized, so what it installs lands in a private copy nothing else can see).
# That fact has to outlive setup, or every later session rediscovers it the slow, miserable way. The file
# lives in _local/, which `apply-update.py` protects, so an update never wipes it. Presence is the whole
# signal — the file's own text is for Claude to read, this just points at it.
note=''
if [ -f _local/machine-notes.md ]; then
  note='📌 THIS MACHINE HAS A NOTE — read _local/machine-notes.md before running any install or setup command.\nShort version: commands you run may not reach her real computer, so hand her lines to paste instead. It is a working setup, not a broken one. The file says exactly what applies.'
fi

# Tools check, independent of the brand kit: a personalized engine copied to a second machine (a new PC, an
# older Mac) has a filled-in brand kit and no ffmpeg, and used to get no nudge at all. Presence only, after
# the path shim so a tool winget just installed still counts. No " or \ in the text (it lands in JSON).
tools=''
[ -f scripts/_path-shim.sh ] && . scripts/_path-shim.sh >/dev/null 2>&1 || true
for t in ffmpeg ffprobe node uv; do command -v "$t" >/dev/null 2>&1 || tools="$tools $t"; done
if [ -n "$tools" ]; then
  tnote='🔧 Core tools missing on this machine:'"$tools"'. Before any edit, run ./check-setup.sh and install what it flags, naming each by its job. A fresh-machine state, not a fault.'
  if [ -n "$note" ]; then note="$note"'\n\n'"$tnote"; else note="$tnote"; fi
fi

# Part C of the brand kit is the "learn my pattern" memory, and brand-kit.md promises her IN WRITING that
# Claude "reads it before building your next reel". Nothing ever did: a search for it across the engine
# finds no code path at all, so the whole feature rested on a future session happening to open the file. A
# PC tester was told her CapCut pass had been learned and saved — true of the file, false of every later
# build. Presence is the signal; the file itself is what Claude reads. One awk line does the counting.
#
# Count ONLY the bullets a preference is actually written as ("- ..."), and stop at the "> _For Claude:_"
# note that closes the section. Counting every non-blank line meant the SHIPPED template scored 7 — its
# own "(empty for now)" placeholder plus that note — so a buyer who had taught it nothing was told, from
# session one, that she had saved preferences. A reminder that fires when nothing was learned trains the
# reader to ignore it, which costs exactly the signal this hook exists to send.
learned=''
if [ -f brand-kit.md ]; then
  learned="$(awk '/^### Learned preferences/{f=1;next} f&&/^>/{exit} f&&/^- /{c++} END{printf "%d", c+0}' brand-kit.md 2>/dev/null)"
fi
if [ -n "$learned" ] && [ "$learned" -gt 0 ] 2>/dev/null; then
  pnote='🧠 SHE HAS SAVED REEL PREFERENCES. The builders apply them automatically (product/learned.py) and print what they used, so you do NOT have to hand-apply anything. Read Part C of brand-kit.md before planning a reel so your CREATIVE choices match what she has already told you, and load the `learn` skill before saving a new one.'
  if [ -n "$note" ]; then note="$note"'\n\n'"$pnote"; else note="$pnote"; fi
fi

# An update stopped from outside before it finished (the window closed, the app quit, the power went) leaves the
# engine part old, part new. Its record in _update-backups/ still names the version she is on as where it started,
# because product.json takes the new version last. Every file it changed is saved, so nothing of hers is lost, but
# nothing should be built on a half-updated engine: running the update again puts it back first, then installs.
stopped=''
if [ -d _update-backups ] && [ -f product.json ]; then
  ver="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' product.json 2>/dev/null | head -1)"
  for rec in _update-backups/*/applied.json; do
    [ -n "$ver" ] && [ -f "$rec" ] || continue
    case "$rec" in *.rolledback/*) continue ;; esac
    from="$(sed -n 's/.*"from"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$rec" 2>/dev/null | head -1)"
    to="$(sed -n 's/.*"to"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$rec" 2>/dev/null | head -1)"
    if [ "$from" = "$ver" ] && [ -n "$to" ] && [ "$to" != "$ver" ]; then stopped="$to"; fi
  done
fi
if [ -n "$stopped" ]; then
  snote='⏸️ An update to v'"$stopped"' was stopped before it finished (the window closed, the app quit, or the power went), so some engine files are new and some are old. Nothing of hers is lost: every file it changed is saved. Before building anything, tell her in one calm line and finish it: run the update again (it puts the stopped one back first, then installs), or undo it with python3 scripts/apply-update.py --rollback (on Windows: python scripts/apply-update.py --rollback). This is a normal recovery, not a fault.'
  if [ -n "$note" ]; then note="$note"'\n\n'"$snote"; else note="$snote"; fi
fi

# An update installed by an updater from v1.0.64 or earlier never ran the finishing step (scripts/post-update.py):
# script permissions dropped, engine settings erased, instructions stale. That updater cannot be changed on a
# buyer's machine, but this hook ships IN the update, so the very next session finishes the job: scripts are
# made runnable right here (bash only, instant), and Claude is told to run the Python step first. Nothing to
# do on a fresh install (no _update-backups/) or once post-update.py has recorded this version, and not while
# an update is stopped halfway (above): that one is finished by running the update again, not by this step.
if [ -z "$stopped" ] && [ -d _update-backups ] && [ -f product.json ] && [ -f scripts/post-update.py ]; then
  ver="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' product.json 2>/dev/null | head -1)"
  if [ -n "$ver" ] && [ ! -f "_local/post-update-$ver.ok" ]; then
    find . \( -path ./node_modules -o -path ./projects -o -path ./_update-backups -o -path ./.claude/worktrees \
              -o -path ./dist -o -path ./releases -o -path ./inbox -o -path ./renders \) -prune -o \
           -type f \( -name '*.sh' -o -name '*.command' \) -print 2>/dev/null \
      | while IFS= read -r f; do [ -x "$f" ] || chmod +x "$f" 2>/dev/null; done
    unote='🔄 The engine was updated to v'"$ver"' but its finishing step has not run yet. Before anything else, run python3 scripts/post-update.py (on Windows: python scripts/post-update.py). It restores engine settings, refreshes the engine instructions while keeping her profile, tidies the changelog and fetches the render browser. Tell her in one warm line that you are finishing her update. This is normal, not a fault.'
    if [ -n "$note" ]; then note="$note"'\n\n'"$unote"; else note="$unote"; fi
  fi
fi

if [ -f brand-kit.md ] && grep -e '{{' -e '<<' brand-kit.md 2>/dev/null | grep -v -F '{{this}}' | grep -q .; then
  # Written as JSON string content already (see emit): \n for each line break, \" around the quote.
  msg='💡 The brand kit is not filled in yet (brand-kit.md still has blank fields to fill).\n\nThis does NOT block anything. Reels build fine without it as long as she has picked a style pack, which is what sets her fonts and colors. Never refuse an edit over this.\n\nRecommend it ONCE, warmly, early: filling it in is what makes reels sound like her instead of generic. She says \"build my homebase\" and it walks her through. If she says she would rather skip it, drop it and do not raise it again.\n\nIf tools are also missing, run ./check-setup.sh and install what it flags, and bootstrap the render browser once with npx hyperframes@0.9.6 browser ensure (doctor only reports; it downloads nothing).'
  [ -n "$note" ] && msg="$note"'\n\n'"$msg"
  emit "$msg"
elif [ -n "$note" ]; then
  # Setup is done, but this machine still needs the note every session.
  emit "$note"
fi

exit 0
