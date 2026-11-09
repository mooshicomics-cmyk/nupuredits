# Style plan widget: build internals

Read this ONLY when changing `product/build-style-plan.py`, or when the generator cannot run and the widget has
to be assembled by hand. Every normal review uses the generator, which already bakes all of this in. The
contract (what a review shows, when, and the on/off switch) is `product/style-plan-widget.md`.

## 🔴 EVERY BUTTON MUST FUNCTION — the locked functional rules

The style plan is an INTERACTIVE tool, not a picture. All three buttons must do something visible.

- **🔴 BIND EVERY HANDLER IN JS VIA `addEventListener` — NEVER inline `onclick="…"` HTML attributes.**
  The `show_widget` sandbox blocks / does not resolve inline event-handler attributes (CSP + wrapped
  script scope), so any button wired with `onclick="fn()"` is **dead on arrival while JS-attached buttons
  work** — that is the exact bug that shipped 2026-08-05 (note/trash worked, Send/Reset were dead). All
  buttons — send, reset, attach, note, trash, copy — attach their handlers in the script with
  `el.addEventListener("click", fn)`. There is **no** `onclick=` attribute anywhere in the markup.
- **🔴 WRAP THE SCRIPT IN AN IIFE AND SCOPE EVERY QUERY TO ITS OWN ROOT.** The root `<div>` carries
  `data-sp-root` (plus an `sp-<job>` id for a11y); the script resolves its root via `document.currentScript`
  / first un-hydrated `[data-sp-root]` (see the CANVAS-BLANK FAIL-SAFE below — **not** `getElementById`,
  which collides on duplicate ids) and queries only `root.querySelector(...)` (via `data-*` hooks, not
  global ids). This keeps two style plans
  in one session from colliding on global `const`s (a redeclare = SyntaxError that kills the second
  widget) or duplicate element ids. No top-level `const`/`function` leaks to global scope.
- **🔴 SEND ALWAYS SURFACES THE EDITS — never trust `sendPrompt`'s return.** `sendPrompt` can SILENTLY
  no-op: it returns without throwing but nothing lands in the chat. So a guarded call that reveals the
  copy box only ON failure still dead-ends when the call "succeeds" but does nothing (regression
  2026-08-11). Therefore `sendEdits()` ALWAYS reveals the copy box pre-filled with the compiled message
  AND copies it to the clipboard (see "Send order" below), whether or not `sendPrompt` reported
  success. Attempt `sendPrompt` (guarded by `typeof` + `try/catch`) as the fast path, but the visible,
  selectable copy-paste box is the guaranteed path that makes Send impossible to break.
- **🔴 SURVIVE THE REMOUNT — her marks live in storage, not memory (locked 2026-10-04).** The host reloads a
  widget after it sends (its own forms save their state in `sessionStorage` for exactly this reason) and again
  whenever the chat re-renders. A widget that kept its marks in memory came back blank the moment she pressed
  Send, taking the copy box with it. So every change saves `{marks, keep, sent}` to `sessionStorage` AND
  `localStorage` under `style-plan:<job>:<cut fingerprint>` (a re-cut gets a new key, so it starts clean), and
  hydration restores them, including the copy box with the message she already sent. Reset clears the key.
- **🔴 SHARE WITH THE HOST, the channel `read_widget_context` reads.** The widget calls
  `window.app.sendRequest({method:"ui/update-model-context", params:{content:[{type:"text", text}]}})` with her
  current marks (debounced) and with the exact message on Send. The app hands that to Claude with her next chat
  message. So if a send never lands, she types anything ("sent") and Claude calls `read_widget_context` with
  `tool_name` = the show_widget tool's full name (in the desktop app, `mcp__visualize__show_widget`) and gets
  her edits. Guard it (`window.app` is absent on hosts without the bridge); never let it throw.
- **Send order:** save → show the copy box → share → `sendPrompt` → copy to the clipboard with
  `navigator.clipboard.writeText` (the host relays it when the frame can't), `execCommand("copy")` only as the
  last resort. Then the note says honestly whether it is on her clipboard.
- **NEVER use `prompt()`, `alert()`, or `confirm()`** for the note / attach buttons. The `show_widget`
  sandbox **blocks** them, so the button silently does nothing. The attach + note buttons MUST open an
  **inline field** (`<textarea>` / `<input>`) rendered inside the row that the user types into, with
  `oninput` writing straight to state.
- **Trash** toggles the row's kept/trashed state and restyles it (strike-through + dim).
- Typing in a field updates the header counts live **without** a full re-render (a full re-render on every
  keystroke steals focus). Toggling a field open/closed re-renders, then focuses the new field.
- **Send my edits** compiles trashed line numbers + notes + references into a plain message and calls
  `sendPrompt(...)` (guarded, per above). If nothing changed, it sends an "approved, move on" message.
- **Reset** clears all state and its saved copy, hides the fallback, and re-renders.

If you change the skeleton, keep every button functional — re-test that clicking attach/note reveals a
typable field, that Send fires (or falls back to the copy box), and that Send carries the typed text.

## 🔴 CANVAS-BLANK FAIL-SAFE — the widget must never render empty (root fix, locked 2026-09-04)

**Symptom (recurring):** the style plan "doesn't load in the canvas" — it renders as an empty shell,
usually the *newest* one on screen. **Root cause:** every render's script located its root with
`document.getElementById("sp-<job>")`, and `getElementById` returns the **first** match. When the same
job's style plan renders twice in a session (a re-render after a fix, or the canvas re-materializing the
earlier widget), the second script hydrates the *first* widget's DOM and leaves the newer one's rows
empty. All content was JS-built into an empty `[data-rows]`, so a mis-scope — or any script throw —
left a blank box. Reproduced deterministically: two same-id renders → instance #2 had 0 rows.

Two locked layers of defense, both baked into `build-style-plan.py`:

- **🔴 SELF-SCOPING — bind to THIS render's own root, never a global id.** The script resolves its root
  from `document.currentScript` (its immediately-preceding `[data-sp-root]` sibling); if that is
  unavailable it claims the **first un-hydrated** `[data-sp-root]` and marks it `data-sp-hydrated`. This
  is immune to duplicate ids AND a null `currentScript`, so two renders each bind to their own instance.
  **Never** reintroduce `getElementById` as the scoping mechanism.
- **🔴 STATIC FALLBACK — every line is a visible static row in the markup, and hydration is wrapped in
  try/catch.** The numbered cut + durations are present with zero JS; hydration replaces them with the
  interactive rows. If the script never runs or throws, the canvas still shows the full read-only cut
  plus a "reply by line number" notice. The review degrades to readable, never to blank.

Verify after any change to the widget: render it **twice in one page with the same id** and confirm BOTH
instances populate their rows (not just the first).

## The skeleton lives in the generator

The one copy of the widget is `_TEMPLATE` in `product/build-style-plan.py`. A second hand-kept copy here drifted
behind it (no on/off box, no saved marks), so it was removed. To see the exact widget, run the generator on any
job: `python3 product/build-style-plan.py projects/<job> --out /tmp/style-plan.html`. If you ever hand-build
one, start from that output and keep every rule above; `scripts/lint-widgets.py` (check-ship gate 9) fails a
Send widget with inline handlers, no copy box, or marks that live only in memory.
