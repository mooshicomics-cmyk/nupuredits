#!/usr/bin/env bash
# PreToolUse guard (Bash + Write/Edit/MultiEdit) — LOCKED fail-safe: never delete or hand-overwrite a
# CapCut draft. A rebuild must never replace/delete a draft: the creator's in-app edits (fonts, effects,
# layout) live ONLY inside the draft and CapCut has NO version history/autosave, so loss is unrecoverable.
# ALLOWED: moving a draft into .recycle_bin (reversible, via draft_safety.recycle). BLOCKED: deleting under
# the drafts folder, or Writing/Editing a file inside it.
# Parser-independent (scans the raw JSON payload) so it can NEVER fail open if a JSON parser is unavailable.
payload="$(cat)"
DRAFTS='com\.lveditor\.draft'

# (A) Write/Edit/MultiEdit whose file_path is INSIDE the CapCut drafts folder -> block.
#     The engine writes draft JSON via its own python scripts, never via the Write/Edit tools, so this only
#     catches an accidental hand-overwrite of a real draft.
if printf '%s' "$payload" | grep -Eq "\"file_path\"[[:space:]]*:[[:space:]]*\"[^\"]*${DRAFTS}"; then
  {
    echo "BLOCKED by protect-capcut-drafts: refusing to Write/Edit a file inside the CapCut drafts folder."
    echo "Never hand-edit a draft's JSON. Build the change to a NEW version, or layer on top. See product/draft_safety.py."
  } >&2
  exit 2
fi

# (B) A Bash command that DELETES inside the CapCut drafts folder -> block.
#     Only gated to the Bash tool so editing engine source that merely mentions these words is never blocked.
if printf '%s' "$payload" | grep -Eq '"tool_name"[[:space:]]*:[[:space:]]*"Bash"'; then
  if printf '%s' "$payload" | grep -Fq 'com.lveditor.draft'; then
    if printf '%s' "$payload" | grep -Eiq '(^|[^a-zA-Z0-9_.])rm[[:space:]-]|rmtree|removedirs|(^|[^a-zA-Z0-9_.])rmdir|os\.remove|(^|[^a-zA-Z0-9_.])unlink|-delete'; then
      {
        echo "BLOCKED by protect-capcut-drafts: this command would delete inside the CapCut drafts folder."
        echo "A rebuild must NEVER replace/delete a draft — in-app edits are unrecoverable (CapCut has no history)."
        echo "Instead: build to a NEW version (draft_safety.next_version -> <base> 1.1/1.2/1.3), LAYER on top,"
        echo "or (only after the creator says yes) MOVE it with draft_safety.recycle() (reversible)."
      } >&2
      exit 2
    fi
  fi
fi
exit 0
