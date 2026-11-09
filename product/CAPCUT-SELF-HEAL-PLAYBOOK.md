# CapCut Self-Heal Playbook

> When a CapCut update breaks an editable draft, this is how the system repairs itself. It ships baked into the product, and it is the exact procedure Claude follows when a creator says **"my draft won't open, fix it."**
>
> **The one law:** never hardcode CapCut's format. Always derive the CURRENT format from a FRESH draft made in the CURRENT CapCut, then bring the broken draft up to match. CapCut auto-updates on its own schedule; this is how we stay ahead of it without shipping a new version every time.

---

## What the creator sees (the whole experience)

She says, in plain words: **"Claude, my draft won't open, fix it."** That is all she has to do. Everything below is your job, not hers. Keep her calm: breakage is normal, it is not her fault, and it is almost always a quick fix. If the deep path fails, it becomes an "engine update from the creator" and she reaches out. She is never stuck alone.

**Prevention to mention once:** turning off CapCut auto-update makes surprises rare. Keeping her project folder (the reel's source) means the reel can always be rebuilt from scratch if a repair is ever messy.

---

## The three things that actually break (diagnose first)

Editable drafts live in `~/Movies/CapCut/User Data/Projects/com.lveditor.draft/` (Windows: `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft\`). A draft is a folder with `draft_info.json` (the timeline + content; `draft_content.json` on Windows), `draft_meta_info.json` (name + metadata), and it is registered in `root_meta_info.json` (`all_draft_store`) at the projects root. Media is copied into the draft's own `assets/` folder.

1. **Format drift (most common).** A CapCut update changes the draft JSON schema or bumps the version fields, so a draft written for the old version will not open or opens with missing/blank tracks. The engine writes a hardcoded platform block (`app_version` is `6.5.0` in `product/engine/VectCutAPI/draft_profiles.py` `CAPCUT_PLATFORM`; a new draft from the live commands takes the installed CapCut's own version), so when real CapCut moves to 9.x+, that stamp and possibly some keys need to be brought current.
2. **Media path broken.** The draft opens but clips, images, or overlays show as missing. Usually the media moved, or the draft's asset paths point somewhere that no longer exists.
3. **Driving the open app drifts.** If a step drives the running CapCut app (`workflows/capcut-live.py` with CapCut open), CapCut's internal automation IDs (the AX hooks) can change on an update, so clicks land wrong or not at all. **Check permission first:** when the app Claude runs in has no macOS Accessibility permission, CapCut reads as completely empty and every live command fails as if the ids had changed; the command now says so outright. The ids themselves were last read off CapCut 9.5.0 and were all unchanged, and the export dialog's own buttons have ids there (`ExportOkBtn`, `automationbackupCheckBox`, `automationcancel`) that export presses directly. Each live command waits for the screen or file it needs rather than for a fixed time, so when one runs out of patience it names what never appeared: that name is what to look for in `ids --map`.

---

## Repair procedures

### A) Format drift — the core self-heal
1. **Learn the current format from a fresh draft.** Have CapCut (current version) create a brand-new empty draft, or make one through the engine, then read its `draft_info.json`, `draft_meta_info.json`, and the new `root_meta_info.json` entry. This fresh draft IS the source of truth for the current schema: the version fields, the key names, the folder layout, the registry entry shape.
2. **Diff against what the engine emits.** Compare the fresh draft's version/platform block and top-level keys to what `draft_profiles.py` (`CAPCUT_PLATFORM`) and the build write. Note what changed: the `app_version`, any `new_version` / `draft_new_version` numbers, added or renamed keys.
3. **Bring the format current.** Update the engine's platform/version fields (and any changed key names) to match the fresh draft. Do this in the config/profile, never as a one-off hardcode buried in a script.
4. **Rebuild or remap.** Rebuild the reel draft through the engine now that it emits the current format (best, if the source project folder is available), OR remap the broken draft's JSON onto the new schema and re-write it.
5. **Re-register.** Make sure the draft's `root_meta_info.json` `all_draft_store` entry matches the fresh draft's entry shape (draft_name, draft_fold_path, draft_root_path, cover, timestamps, duration).
6. **Verify.** Quit CapCut fully, then reopen it and confirm the draft opens and every track is present. (CapCut rewrites its registry on quit, so it must be closed while you write and reopened to see the result.)

### B) Media path broken
1. Open the draft's `draft_info.json` and find the media references.
2. Point them at the real files in the draft's own `assets/` folder (media is always copied there, so the files exist locally).
3. Quit and reopen CapCut, confirm the media shows.

### C) Live-lane automation drift
1. Run `uv run workflows/capcut-live.py ids --map` against the running CapCut, once on the home screen, once with a draft open, and once with the export dialog open (open it by hand). It reads only (nothing is clicked) and says which ids CapCut still answers to (and at what level of its accessibility tree), and which are gone, with the labels that look like them. It also says when a reading was cut short by its element budget (raise `walk_budget`).
2. Try a new value without editing code in `_local/capcut-live-map.json` (for example a renamed id such as `{"export_ok": "<new label>"}`, a longer wait limit such as `{"load": 120}`, or a larger element budget such as `{"walk_budget": 10000}`), retry the action, then move what worked into the live map at the top of the live section in `workflows/capcut-live.py`. (This only affects steps that drive the live app, not the written draft.)


### D) Mac: the project never reaches CapCut ("Operation not permitted" in Movies)
Some Macs refuse the engine's own Python any write in `~/Movies` (and `~/Music`, `~/Pictures`) while Apple's own tools write there fine. That is almost always a security app's protected-folders or ransomware shield. The engine handles it by itself; nothing here needs her to change a setting.
1. **What the engine does.** Each run makes and removes one hidden folder directly in `~/Movies` (never inside CapCut's folder). Refused: it remembers this Mac (`mac.drafts-blocked` in `_local/pivots.json`, one line in `_local/fallbacks.log`), builds the project in `projects/_capcut-staging/`, and leaves **Add to CapCut.command** there. She quits CapCut and double-clicks it in Finder: it adds the project with Apple's own `/bin/mv`, never replaces a project she already has (a taken name goes in as the next version), and backs up CapCut's list first. A change to a draft she already has works the same way: the engine reads hers from CapCut's folder, changes a copy in the staging folder, and the double-click brings it in as a new version. Hers is never changed.
2. **A build that ended on "This Mac would not let the engine save the project into CapCut's folder"** means VectCut's save was refused even though the quick check passed. It is remembered too: run the build again and it takes the staging route.
3. **Check the answer:** `python3 product/capcut_store_redirect.py` says `redirected: yes/no`. If she later allows the engine in her security app, `python3 product/capcut_store_redirect.py --recheck` forgets what this Mac learned and checks again. A project added to CapCut this way shows up after she opens CapCut.

---

## Boundaries — what self-heal covers vs. what escalates

**Self-heal handles:** format drift (A), media-path breaks (B), text/render mismatches that come from format drift, live-lane AX-id drift (C), and a Mac that keeps the engine out of Movies (D). These are all "CapCut changed something" problems, and they are fixable on the creator's machine by re-deriving the current format.

**Escalate to an engine update from the creator:** a break INSIDE the engine itself — the VectCut server won't start, a `pyJianYingDraft` error, or the build logic itself is wrong. That is not the creator's to fix. Tell her plainly: "This one is on my end, I'll push a fix," and route it to the creator. Never leave her feeling like she broke it.

---

## The always-true habits (bake these into the flow)

- **CapCut must be fully quit while a draft is written, and reopened to see it.** Most "it didn't show up" reports are this.
- **Never hardcode a CapCut version to \"fix\" drift.** Derive it from a fresh draft every time, so the repair keeps working through future updates.
- **Keep the source project folder.** If a repair is ever ugly, rebuilding the reel from source is the clean reset.
- **MP4 finishers rarely land here at all.** The finished-MP4 path does not use CapCut drafts, so format drift can't touch it. If a creator keeps hitting draft breakage, the MP4 finish is a calm fallback.
