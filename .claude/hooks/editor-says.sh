#!/usr/bin/env bash
# editor-says.sh: when Claude waits on her in the chat, her open visual editor page says so (product/editor_says.py).
# She edits on the page, not in the chat, so a question sat there unseen. Wired in .claude/settings.json to:
#   PreToolUse    AskUserQuestion                     ask         the question box is about to show
#   Notification  permission_prompt|elicitation_dialog  permission  a "may I?" prompt (or a tool's question) waits
#   PostToolUse   AskUserQuestion                     answered    she answered: the "in the chat" card comes down
#   UserPromptSubmit                                  answered    she typed in the chat: same
# Only reels whose page is open get the card (asked its page server for anything in the last two minutes); with no
# page server running it does nothing. Claude's own `visual_editor.py tell` says it first when it can; this is the
# net under it (a card Claude already put up in the last two minutes is never doubled).
#
# Rules it keeps (like chime.sh): returns fast, prints nothing, never fails the session (exit 0 on every path).
#
# One exception to "prints nothing": when what she typed asks for her visual editor, it prints one line of context
# for Claude (UserPromptSubmit adds a hook's stdout to the chat). This hook is already registered in every engine
# since 2026-10-18 and its body is read fresh each time, so the line reaches a chat that started on instructions
# from before an update, the reason "open my visual editor" sometimes did nothing (2026-10-21).

if [ "${1:-}" = "answered" ] && [ ! -t 0 ]; then
  input=""
  IFS= read -r -t 1 -d '' input 2>/dev/null   # Claude pipes the event and closes it; never waits past a second
  case "$input" in *'"hook_event_name"'*'"UserPromptSubmit"'*)
    shopt -s nocasematch 2>/dev/null
    case "$input" in *"visual editor"*|*"open my editor"*|*"show me the editor"*)
      echo "Editor note: if she is asking to open, see or find her visual editor (not asking how to use something on it), run \`python3 product/visual_editor.py open\` (her latest reel; \`open <job>\` for one she names) and paste the EDITOR LINK: line it prints into your reply word for word, every time, since her browser can open behind this window. If it says there's no rough cut yet, tell her that instead." ;;
    esac
    shopt -u nocasematch 2>/dev/null ;;
  esac
fi

{
  root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)" || root="${CLAUDE_PROJECT_DIR:-.}"
  ev="${1:-ask}"
  # Fast paths in bash alone, so a buyer with no editor page open never waits on python (well under 100 ms,
  # Windows included). Python starts only when there is something to do.
  if [ "$ev" = "answered" ]; then
    # an "in the chat" card is up on some reel: editor_says.py keeps review/.claude-chat-card while one is
    set -- "$root"/projects/*/review/.claude-chat-card
    [ -e "$1" ] || exit 0
  else
    st="$root/_local/visual-editor-server.json"
    [ -f "$st" ] || exit 0                                  # a fresh install, or the editor never opened
    port="$(grep -oE '"port"[[:space:]]*:[[:space:]]*[0-9]+' "$st" 2>/dev/null | grep -oE '[0-9]+$' | head -1)"
    [ -n "$port" ] || exit 0
    command -v curl >/dev/null 2>&1 || exit 0
    # a server left behind (killed) refuses at once; a page open lists itself under "pages"
    ping="$(curl -s --max-time 0.4 "http://127.0.0.1:$port/ping" 2>/dev/null)" || exit 0
    case "$ping" in *'"pages": {}'*|'') exit 0 ;; *'"pages": {'*) ;; *) exit 0 ;; esac
  fi
  . "$root/scripts/_python3-shim.sh" >/dev/null 2>&1
  [ "${_P3_OK:-0}" = 1 ] || exit 0
  python3 "$root/product/editor_says.py" hook "$ev"
} </dev/null >/dev/null 2>&1
exit 0
