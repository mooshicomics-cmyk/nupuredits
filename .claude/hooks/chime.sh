#!/usr/bin/env bash
# chime.sh: one soft sound when Claude is waiting on her, so a question or a permission prompt never sits
# unnoticed while she is across the room. Wired in .claude/settings.json to:
#   Notification   permission_prompt   a "may I?" prompt has waited about 6 seconds
#                  idle_prompt         Claude finished and she has not typed for about a minute
#                  elicitation_dialog  a connected tool is asking her for something
#   PreToolUse     AskUserQuestion     the question box (the engine's pick-one prompts) is about to show
#
# Rules it keeps: returns at once (the player runs in the background), prints nothing (hook output must stay
# clean), never fails the session (exit 0 on every path), and makes no sound when a player is missing.
#
# Her off switch: "turn the chime off" -> python3 product/chime.py --off, stored in _local/chime.json
# ({"off": true}). _local/ is kept by every update and never ships.
# Debounce: no second chime within DEBOUNCE seconds (a question box followed by its own notification, or a
# permission prompt right after a question, is one ding, not two). The last chime time is _local/.chime-last.
#
# --force (what `product/chime.py --test` runs) plays it even when it is off and skips the debounce.
#
# Mac: afplay (built in). Windows under Git Bash (uname MINGW/MSYS/CYGWIN): powershell.exe, built into every
# Windows 10/11, plays the stock notify sound from C:\Windows\Media. Linux: paplay or canberra-gtk-play when
# one is there, else nothing.

DEBOUNCE=10   # seconds; permission_prompt fires ~6s after its prompt shows, so 3 would let a question ding twice

{
  root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)" || root="${CLAUDE_PROJECT_DIR:-.}"
  state="$root/_local/chime.json"
  stamp="$root/_local/.chime-last"
  force=0
  [ "${1:-}" = "--force" ] && force=1

  if [ "$force" = 0 ]; then
    # Off when she said so: {"off": true} in any spacing.
    if [ -f "$state" ] && tr -d ' \t\r\n' < "$state" 2>/dev/null | grep -q '"off":true'; then
      exit 0
    fi
    now="$(date +%s 2>/dev/null)"
    last="$(cat "$stamp" 2>/dev/null)"
    case "$last" in ''|*[!0-9]*) last=0 ;; esac
    case "$now" in ''|*[!0-9]*) now=0 ;; esac
    if [ "$now" -gt 0 ] && [ $((now - last)) -lt "$DEBOUNCE" ] && [ $((now - last)) -ge 0 ]; then
      exit 0
    fi
    mkdir -p "$root/_local" 2>/dev/null && printf '%s\n' "$now" > "$stamp" 2>/dev/null
  fi

  case "$(uname -s 2>/dev/null)" in
    Darwin)
      snd=/System/Library/Sounds/Glass.aiff
      if command -v afplay >/dev/null 2>&1 && [ -f "$snd" ]; then
        nohup afplay -v 0.6 "$snd" >/dev/null 2>&1 &
      fi
      ;;
    MINGW*|MSYS*|CYGWIN*)
      if command -v powershell.exe >/dev/null 2>&1; then
        # PlaySync keeps PowerShell alive until the sound ends (Play() would exit and cut it off). A missing
        # file falls back to the system Asterisk sound, held long enough to be heard.
        nohup powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -Command \
          "try { (New-Object System.Media.SoundPlayer 'C:\\Windows\\Media\\Windows Notify System Generic.wav').PlaySync() } catch { [System.Media.SystemSounds]::Asterisk.Play(); Start-Sleep -Milliseconds 900 }" \
          </dev/null >/dev/null 2>&1 &
      fi
      ;;
    Linux)
      if command -v paplay >/dev/null 2>&1 && [ -f /usr/share/sounds/freedesktop/stereo/message.oga ]; then
        nohup paplay /usr/share/sounds/freedesktop/stereo/message.oga >/dev/null 2>&1 &
      elif command -v canberra-gtk-play >/dev/null 2>&1; then
        nohup canberra-gtk-play -i message >/dev/null 2>&1 &
      fi
      ;;
  esac
} </dev/null >/dev/null 2>&1
exit 0
