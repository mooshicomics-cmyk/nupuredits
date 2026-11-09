---
name: style-pack
description: Builds the creator's OWN style pack — walks them through picking their 3 fonts (main / caption / accent) and their accent color, then writes it into style-packs.json as a new named pack the engine can use forever. Fonts can be any they have (system/Font Book, CapCut, or bundled). Use when the creator says "build my style pack", "make a pack from my design", "here is my DESIGN.md", "build my own pack", "make my own look", "make my own style pack", "custom style pack", "I want to use my own fonts", "create a style pack", "save this as my pack", "make this my pack", or hands over a frame pack zip from hyperframes.dev/design, or says "I styled my Canva pack" / "read my Canva style pack" / "use my Canva pack" / asks where the Canva style pack is. The LAYOUT stays locked; only fonts, sizes, case, and accent color are theirs.
---

# Build your own style pack

The 3 style packs (Editorial / Playful / Butter) are a starting point. This skill lets the creator
make **their own** pack, so every reel is unmistakably theirs. The **layout never changes** (that's the
locked part that keeps reels clean); what they choose is **their 3 fonts, sizes, case, and accent color.**

**Trigger command (teach this):** the creator says **"build my own style pack"** (or "make my own look").

**Two other ways in, both real:**
- **"save this as my pack"** / "make this my pack" — they just finished a reel and love how it looks. Read
  the pack + any per-reel overrides the job actually used (and, if they hand-set type in CapCut, read the
  draft's text layers), confirm the fonts and colors back to them in plain language, ask what to call it,
  and write it as a new named pack (saved the same way as below, step 3). Never guess a value you did not
  read; ask instead.
- **They designed it on https://www.hyperframes.dev/design and downloaded a frame pack.** That is the PRO
  route and it has its own walkthrough: hand off to **`/studio recipe`**, which builds from the zip's
  `FRAME.md` via `product/frame_to_pack.py`. Do not rebuild that flow here.

**Own font? Say yes.** Any font works, bought or free. They install it on their Mac, add it in CapCut that
same one time, then tell you its name. If you cannot find it, say so and wait. Never substitute silently.

**They styled the Canva Style Pack.** That is the Canva route, the friendliest one, with its own
walkthrough: see **"The Canva route"** below. Follow it exactly; it is how the pack ships.

## Voice
Big sister across the table. Warm, plain, one question at a time, lead with hope. First, read
them the guardrails in `product/creative-vault/font-picking-guardrails.md` in your own words — it's the "how
to pick 3 fonts" guide already written in her voice.

## The 3 fonts (each has a job — from font-picking-guardrails.md)
1. **Main font** — the loud one. Headlines + full-screen takeovers. Must stay readable when big.
2. **Caption font** — the quiet workhorse. Read-along captions. Clean, easy in half a second. Not the cute one.
3. **Accent font** — the little bit of them. Thought bubbles, side comments, highlighted keywords. Used small.

Guardrails to hold: only ONE font is loud (the main); pair a character font with a clean one; half-second read
test on the caption; pick fonts that feel like them; then lock them in and reuse forever.

## Any font they have works
They can use their **own system fonts** (anything installed on their Mac / in Font Book), **CapCut fonts**
(added in CapCut once — the engine resolves it via `capcut_userfonts` / userFontData), or the **bundled OFL**
fonts. Ask what they want by NAME; you resolve the file. If a font isn't found, tell them to add it in CapCut
or install it once, then continue.

## How to build it (what YOU do — grounded in the real files)
1. Ask their 3 font names (main / caption / accent) and their **accent color** (a hex, or "point at a color
   you love" → convert to hex). Accent defaults to white if they don't want one. In the same question box, ask
   the **case** as one pick-one: headlines and takeovers in ALL CAPS, or the way she types them. (Captions keep
   the clone's case unless she names one.)
2. **Clone an existing pack's element block** from `creative-vault/style-packs.json` (sizes + y-positions +
   tracking + line_height per role are the LOCKED layout — keep them). Swap the `font` + `file` for each role to
   their fonts, set each role's `case` from her answer (ALL CAPS = `upper`, as typed = `as-written`), and set the
   pack's `accent_color`. Set `"in_launch_kit": false`. **Case is hers, never the clone's:** Butter's headline and
   takeover are `upper`, so a pack cloned from Butter without this step comes out in all caps she never chose.
   - Roles map: headline + takeover = their **main**; caption = their **caption**; thought_bubble +
     accent_caption = their **accent**.
   - Resolve each `file` with `capcut_userfonts.resolve_font_file(name)`; store what it finds. System fonts
     use their absolute path; add to `system_fonts` if needed.
3. Add it as a new named pack (`"in_launch_kit": false`) under `packs`, named after them (e.g. "My Pack").
   **Save it through the engine, never by editing `style-packs.json` by hand:** `style-packs.json` ships
   with the engine, so an update replaces it, and a pack written straight into it was deleted by the next
   update. Put the finished block in a JSON file (e.g. `_local/my-pack.json`: `_local/` is hers and never
   ships) and run
   ```bash
   python3 product/pack_write.py --name "My Pack" --block _local/my-pack.json \
       [--system-font "Font Name=/absolute/path/to/the/font"]     # once per SYSTEM: font a role uses
   ```
   (`--block -` reads it from stdin; on Windows use `python`.) It writes the pack into `style-packs.json`
   and keeps a protected copy in `creative-vault/user-packs.json`, which every update puts back. Changing a
   pack she already has ("make my accent bigger") is the same command with `--force`, so the protected copy
   stays current too.
4. Offer a quick test render of one caption so they SEE it before locking in. Adjust on their word.

## The Canva route ("I styled my Canva pack")

The Style Pack is a Canva template of her reel's pieces (fonts, colors, hook, captions, side comments,
takeover, name tag, end card) drawn at the engine's real sizes. She copies it, styles it, and the engine
reads it back. Where the template lives and the markers it uses are in
`product/creative-vault/canva-style-pack.json`.

**She has not got the template yet** ("where's the Canva style pack?"): give her `template_url` from that
file. Page 2 of the template shows her File, then Make a copy; she works only in her copy (it suggests
the name "My Style Pack").

### 1. Make sure Canva is connected
You can only read her design through the Canva connector (tools such as `read-design` and
`search-designs`). Check before anything else:
- If you have a `session_connectors_status` tool, call it. Canva listed as **connected**: go on. Listed
  but **off** for this session: offer to turn it on with `set_session_connector_enabled` (she approves),
  and tell her its tools arrive with her next message. **needs_auth**: she signs in; walk her through
  step 3 of the list below, starting at "Sign in to Canva".
- No Canva tools and no such status tool, or Canva is not listed at all: walk her through adding it, one
  step at a time, waiting for her to say done after each:
  1. Open the Claude app's **Settings**, then **Connectors**.
  2. Find **Canva** in the list (use the search or Browse connectors) and click **Connect**.
  3. Sign in to Canva with the account that holds her Style Pack, and click **Allow**.
  4. Back in this chat, click the **+** in the message box, open **Connectors**, and make sure Canva is
     switched on.
  5. Send any message ("done") so the Canva tools load, then carry on.
  Running Claude Code in a terminal instead of the app: connectors from her claude.ai account show up
  there too once she is signed in with it; `/mcp` lists them.
- This is Claude's own connector, added by her. Never reach for the Claude app's setup skill for it (it
  is blocked in this folder), and never ask for her Canva password: the sign-in happens in Canva's own
  window.
- She cannot connect at all: she can still build a pack the plain way (ask her font names and colors,
  the steps above this section). Say so kindly; do not stall.

### 2. Find her copy
- She pasted a link: a `canva.link/...` link goes through `resolve-shortlink` first; a
  `canva.com/design/<ID>/...` link gives you the design ID directly.
- No link: `search-designs` for "Style Pack" (owned by her), newest first. One clear match: confirm its
  title with her. Several: show her the titles and let her pick.
- If what you found is the master template (title exactly `template_title`, and she cannot edit it),
  she styled nothing yet: send her back to Make a copy.

### 3. Read it, and read ONLY what is hers
Call `read-design` for the whole design with fields `design_content`, `page_metadata` and
`thumbnails` (thumbnails for the styling pages). Save the `design_content` JSON to
`_local/canva-pack/design.json` and run:
```bash
python3 product/canva_to_pack.py --design _local/canva-pack/design.json --name "<her pack name>"   # Windows: python
```
The script reads only what sits inside a purple dashed outline. **Never take a style from the template's
own parts**, even though they are colored and bold:
- the purple dashed outlines and their purple **STYLE ME** / **BUILD HERE** tags;
- the gray panel at the bottom of each page, the gray labels, the "yours to style / instructions" key;
- page titles, the cover and instruction pages, and the gray stand-in person and footage.
If you ever describe her pack from the thumbnails, the same rule holds: purple outline and tag are not
her accent color; the gray panel is not her background.

### 4. Settle what the script flags, with her
- **"no name typed" / "uses a font that is not on the your fonts page"**: Canva never tells us a font's
  name, only what she typed on the fonts page. Ask her the name; have her type it on that page too.
- **"case unclear"**: Canva keeps the letters she typed, not its uppercase switch. Look at that page's
  thumbnail: showing in capitals means `--case <role>=upper`, otherwise `lower`. Roles: headline,
  caption, thought_bubble, accent_caption, takeover.
- **"not installed yet"**: the font lives in Canva but not on her computer. Walk her through installing
  it (fonts.google.com, double click on Mac / right click, Install for all users on Windows, then pick it
  once in CapCut), exactly as page 3 of the template says, and re-run.
- Pages she added (**her own page: ...**) are kept with her pack under `canva.custom_pages`, by their
  page title. Tell her which ones you found.

### 5. Save it and show her
Read the pack back in plain words (her three fonts, her colors, anything the script flagged), ask what to
call it, then run the same command with `--write` (and `--case ...` answers). It saves through
`pack_write.py`, so an update never deletes it. The name tag, end card and takeover background she styled
are stored with the pack under `canva`. Offer the quick test render of one caption so she sees it before
using it on a real reel, and offer to make it her default pack (on a yes:
`python3 -c "import sys; sys.path.insert(0, 'product'); import cleanyap; cleanyap.set_default_pack('<Her pack>')"`;
every build route and the visual editor open new reels in it).

## The DESIGN.md route ("make a pack from my design")

She has her own design system written down: a DESIGN.md in this engine's format or the common web shape, in
`favorites/designs/<name>/` (make that folder for her if it isn't there, and move a DESIGN.md she dropped in the
inbox into it). Run `python3 product/design_md.py favorites/designs/<name>` (the dry run: what it read, the pack it will make, anything to
fix or ask), answer what it asks in ONE message, then `--write`. Never hand-roll the steps. The spec,
`product/DESIGN-MD-SPEC.md`, says what each field does: fonts go by name
(installed on her computer = CapCut has it; Windows: "Install for all users"), the front matter becomes the pack
(pack_recipe for seed colors, pack_write --set for a full palette and each optional field), a web-shape DESIGN.md
goes through the spec's map with ONE line naming what was dropped, and every `## Look:` section goes through
`build-a-look`. A field outside the spec is one question to her, never a silent drop; a legibility or size floor
it misses is refused in plain words with the nearest passing value.

## Changing a shipped pack ("keep Butter but make the blue pink")
Never edit Editorial, Playful or Butter in place: every update resets the shipped packs. Make it a pack of
theirs, built from the one they like, in one command:
```bash
python3 product/pack_write.py --name "Butter Blush" --from Butter --set palette.dark=#C2527A --set palette.muted=#CB6B8F
```
`--from` copies the pack's fonts, settings and full palette; each `--set` changes one value (`accent_color=`,
`palette.<role>=`, `ground=`). It warns when text in the new colour will not read on the background (a pale
pink on Butter's pale lemon will not); pick a deeper shade for text. Then set it as their default. If a shipped
pack was already edited in place, the next update saves those edits for them as "My Butter".

## Finish
Confirm: "That's your pack. Say its name anytime and every reel uses it." Remind them they can set it as
their default (E3) and refine it later ("make my accent bigger", "swap my main font") — it's theirs to coach.

## Rules
- Never change the LAYOUT (sizes/positions are the pattern). Only fonts + accent color + case are theirs.
- One font is loud (the main). Enforce the guardrails kindly.
- Resolve every font to a real file (bundled / CapCut / system); if missing, help them add it, don't fake it.
- Save it for them with `product/pack_write.py` (it writes `style-packs.json` and keeps the protected copy
  an update restores from); they just talk. See no hand mock reel layouts (use real sizes).
