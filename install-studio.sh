#!/usr/bin/env bash
# install-studio.sh — make the /studio command available in Claude Code from ANY folder.
#
# By default a skill only shows up when you open Claude Code inside this engine folder.
# This installs Studio into your global Claude skills folder (~/.claude/skills) so you can
# type /studio anywhere, the same way built-in commands work.
#
# Run it once, from inside your Reels Editing Engine folder:
#     ./install-studio.sh
#
# It creates a link (not a copy), so whenever your engine updates, /studio updates too.
# Safe to run again anytime — it just re-points the link.

set -euo pipefail

# Where this script lives = the engine root. Studio ships beside it.
# pwd -P resolves symlinks so the global link records the real, stable location.
ENGINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SRC="$ENGINE_DIR/.claude/skills/studio"
DEST_DIR="$HOME/.claude/skills"
DEST="$DEST_DIR/studio"

if [ ! -d "$SRC" ]; then
  echo "✗ Could not find the Studio skill at:"
  echo "    $SRC"
  echo "  Run this script from inside your Reels Editing Engine folder."
  exit 1
fi

# Refuse to link the global /studio at a throwaway copy (system temp, a mktemp dir, or the make-ship
# dist/ staging tree). Doing so would leave /studio dangling the moment that copy is removed.
case "$ENGINE_DIR/" in
  /tmp/*|/private/tmp/*|/var/folders/*|/private/var/folders/*|*/dist/*|*"/tmp."*)
    echo "✗ This looks like a temporary or staging copy of the engine:"
    echo "    $ENGINE_DIR"
    echo "  Installing /studio globally from here would break the moment this copy is removed."
    echo "  Move the engine to a permanent folder (e.g. ~/ai-edit-engine), then run this again."
    exit 1 ;;
esac

mkdir -p "$DEST_DIR"

# Windows (Git Bash): `ln -s` quietly makes a COPY there (MSYS's default), and a copy never follows an engine
# update. So on Windows the link is a directory junction, which is a real link and needs no admin rights or
# Developer Mode. A copy an earlier install left behind is the one real folder it is safe to replace: it holds
# this very skill, so it is moved aside (never deleted) and the junction takes its place.
WIN=0
case "$(uname -s 2>/dev/null)" in MINGW*|MSYS*|CYGWIN*) WIN=1 ;; esac
ASIDE=""
if [ "$WIN" -eq 1 ] && [ -d "$DEST" ] && [ ! -L "$DEST" ] && [ ! "$DEST/SKILL.md" -ef "$SRC/SKILL.md" ] \
   && grep -q '^name: studio' "$DEST/SKILL.md" 2>/dev/null && grep -q 'The craft layer' "$DEST/SKILL.md" 2>/dev/null; then
  ASIDE="$HOME/.claude/studio-old-copy-$(date +%Y%m%d%H%M%S)"
  mv "$DEST" "$ASIDE"
fi

# If a REAL folder (not a link) is already there, don't destroy it — the buyer put it there on purpose.
if [ -e "$DEST" ] && [ ! -L "$DEST" ]; then
  echo "✗ A real folder already exists at $DEST"
  echo "  Nothing changed. Remove or rename that folder, then run this again."
  exit 1
fi

if [ "$WIN" -eq 1 ]; then
  # Replace any old link, then make the junction. cmd needs Windows paths and its own switches left alone.
  if [ -L "$DEST" ]; then rm -f "$DEST" 2>/dev/null || rmdir "$DEST" 2>/dev/null || true; fi
  if ! MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' cmd /c mklink /J "$(cygpath -w "$DEST")" "$(cygpath -w "$SRC")" >/dev/null \
     || [ ! -e "$DEST/SKILL.md" ]; then
    if [ -n "$ASIDE" ] && [ ! -e "$DEST" ]; then mv "$ASIDE" "$DEST"; fi
    echo "✗ Windows would not create the link at $DEST"
    echo "  Nothing changed. This usually means the engine folder is on a network or removable drive."
    echo "  Keep the engine on your main drive (C:), then run this again."
    exit 1
  fi
  if [ -n "$ASIDE" ]; then
    echo "↻ Replaced an old copy of Studio that would never have updated. That copy is kept at:"
    echo "    $ASIDE"
  fi
else
  # -s symlink, -f replace any old link, -n don't dereference an existing link-to-dir.
  ln -sfn "$SRC" "$DEST"
fi

mkdir -p "$ENGINE_DIR/_local" && : > "$ENGINE_DIR/_local/studio-global.ok"   # her yes, so the session hook keeps it healed
echo "✅ Studio installed."
echo "   /studio will now work from any folder."
echo "   Restart Claude Code (quit and reopen), then type  /studio  to see the command menu."
