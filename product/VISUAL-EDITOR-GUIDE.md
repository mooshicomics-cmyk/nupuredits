# The visual editor: what's on her page and how each thing works

The page is `product/visual-editor/editor.html`, served by `product/visual_editor_server.py` and opened with
`python3 product/visual_editor.py open <job>`. This is the map of it, for answering her "how do I…" and for knowing
what the page can do before saying it can't.

**She can't find the editor, or it didn't open?** She can type **"open my visual editor"** or **"show me the visual
editor"** in the chat any time, in any session. `python3 product/visual_editor.py open` (no reel named) opens her most
recent reel with a rough cut; it prints an `EDITOR LINK:` line: paste it into the chat word for word every time (her
browser often opens behind this window). It also writes "Open my visual editor.html" into her engine folder to
double-click. Whenever she can't see or reach the editor, open it and tell her those two phrases in one line, so she never
has to ask again. It is almost always an engine that came in through /update from before the editor: its update
rundown only covered the newest version (`scripts/post-update.py` now says the editor is there until she has met it),
and the chat she updated in started on her older instructions, so suggest a new chat too. No rough cut yet: the
editor opens after the cut. Still won't open: the original widget for this reel, plus `/report-a-problem`.

**Read this before you tell her the editor can't do something.** Never infer the page's abilities from its text, a
screenshot or a glance at the code: several tools are reached by clicking or dragging things that have no label
(a clip's edge on the timeline, the grip on the timeline's top edge). If this guide doesn't cover it, read the page's code for it (grep
`editor.html`) before answering, and never steer her off the editor to CapCut for a job the page does.

## The road through it

Four tabs, left to right, one job each: **Cut → Visuals → Sound → Finish**. Tapping a later tab takes the step that
opens it (sends her cut, locks in her cut or her looks) and goes there; only the few seconds her visuals take to move
to a new cut make a tab wait, and it says so. **Her choices are never refused**: a placement
near her face, an overlap, a long or quiet line, an odd size or file is done as she asked, with one plain line at most;
a refusal is only for what's truly impossible (a file that's gone, two edits colliding, an export already running),
and then it says the one thing to do next. The big button bottom right always names the next step.

1. **Cut.** She edits, presses **Send my cut** (a quick update, seconds; the button reads **Updating your cut…**
   until the page switches to the new cut by itself, and a slower computer just reads it longer), and when it sounds right, **Lock in my cut**. Lock in is refused while a note to Claude is waiting
   (the card hands her "update my edit").
2. **Visuals.** Empty until looks exist: the card says to type **"show me my looks"** (its button copies that line).
   Then she swaps, moves and refines line by line, and presses **Lock in my looks**. The toolbar is three menus, grouped
   by intent: **Looks ▾** (My looks, Build new, Browse), **Captions ▾**, and **Footage ▾** (Fill with my b-roll, Cover a
   face, Filter). Tap a menu to open its list; tap anywhere else to close it. A **dot on the Looks button** lights up
   when something's ready for her there (her Sandbox sketches landed, or Claude (re)built her looks), so she sees it
   without opening the menu; it clears the moment she opens Looks.
3. **Sound.** Every moment that moves has a sound. **Next: Finish**.
4. **Finish.** Pick where your reel goes, then **Export** (the dock button): **CapCut** (an editable draft), the **Edits app** (your cut in Instagram's Edits app, each look its own movable layer), **DaVinci Resolve** (your whole reel as an editable Resolve timeline), or an **MP4 file** (your finished reel plus a phone copy). They land from the same looks. The Edits app is **medium only** (it keeps your style by carrying your looks in as rendered layers); it has no raw option, because the packs' fonts are CapCut's, so a raw Edits build would lose your look. Same for Resolve. Resolve writes a `<job> resolve` folder in the reel's outputs. When DaVinci Resolve is installed, the export drops the build script straight into its menu, so the **one click** is: open Resolve, **Workspace > Scripts > Build <job> overlay** (or `native`). No file to find. If Resolve isn't installed the folder still holds everything for a **hand import**: the FCPXML (`<job> overlay.fcpxml`, or `<job> native.fcpxml` + the `.srt` for real retypeable captions). The Finish tab shows whichever way applies. Your cut, looks, sounds, music and captions come in on their own tracks, your voice alone on its own; captions default to your exact look.

Going back is always allowed. A cut edit after locking shows "You updated your cut" with **Confirm my edits**; the
looks she added follow her words by themselves, and looks Claude built for the old cut wait for "update my edit".

## Cut tab

| She wants to | How |
|---|---|
| Cut words | Tap a word (or drag across several with a mouse; on touch, one word at a time or the line number for the whole line), then **Cut** in the little menu. **Delete** / **Backspace** cuts what's selected. |
| Watch the reel without the script pulling her down | While it plays, the script follows the word being said only while she is reading along. Once she scrolls away herself (up to the player on a wide reel, whose player sits above the script), it stays where she put it; pressing play again, or tapping a word, makes it follow again. |
| Bring words back | Tap a struck word, **Bring back**. Lines the engine cut entirely sit folded in "N lines the engine cut": open the fold to bring words back. |
| **Trim dead space at the start or end of a clip** | On the timeline, like CapCut. **Drag the clip's edge** (a grip at each end of every block): the clip follows her cursor and the clips after it slide along. Or put the playhead where the dead space ends and press **Cut before playhead** (**Q**) / **Cut after playhead** (**W**); hovering either button shades exactly what it will cut. Zoom in (**+**, the slider, or pinch) for precision. Then **Send my cut**. |
| Remove a long pause (anywhere: the middle of a line, or the quiet before her first word / after her last in a clip) | **Split works wherever she puts the playhead** (**B**, or ⌘B): between words, inside a word, or in a clip's opening or closing quiet. The clip becomes two and nothing heard changes. Split at both ends of the pause, click the piece in the middle and press **Delete**: exactly that stretch goes. Or split once and drag the new edges, or press **Q** / **W** on a side. Never tell her Split only works between words: that limit is gone. Also: a note (**Awkward pause**) or her ask in the chat still works (see "Her notes" below). |
| Delete a whole clip | Click it on the timeline (it outlines; the playhead doesn't move), then **Delete** (the key or the button). Its words are cut; Undo brings them back. The last clip in a cut can't be deleted. |
| Speed up a clip, or zoom in / out across it | Select the clip on the timeline (or put the playhead in it), then **Speed** (Normal · 1.25× · 1.5× · 2×, or a ramp: **Fast, easing to normal** · **Normal, speeding up**) or **Zoom** (No zoom · Zoom in · Zoom out) in the tool row. A ramp is ONE fluid clip easing between speeds (never two pieces: a jump in speed reads as a jerk); `"ramp": {"from", "to", "ease"}` in cuts.json, "speed" holding its average, its sound at that average speed (best on a clip with no talking). The preview plays it at once: the clip runs faster (its length, the playhead and her looks' timing follow) and the zoom moves smoothly across the clip, held on her face (set for each frame the video shows, as the export does, so a push-in never shakes in the preview). The block shows a **2×** / **Z+** / **Z−** badge. It goes in with her next **Send**, like a trim; every Send after keeps it, Undo takes it back. A clip carries ONE move: set on either half of a split clip, it replaces the clip's move (never a second, opposite one), and the change chip says "speed or zoom change", never "edge trimmed". The MP4 export renders both; CapCut gets them baked into the footage clip (sped and zoomed, still split line by line). Zoom in = 1.0 to 1.15, zoom out = 1.15 to 1.0. |
| Split a line in two | Tap a word that isn't the first in its line, **Split line here**. This regroups the script lines (and the looks on them); it doesn't cut any sound. A look on the line follows with everything she chose: her refine (size, animation, words she typed), her highlights, her picture's entrance and where she moved it. A look that can't be redrawn on the new words stays as it was drawn; the split always goes through. |
| Combine two lines | Hover between them, **Combine** (shows once looks exist, on Cut and Visuals). |
| Put two lines under one look, or give half a line its own (Visuals) | On **Visuals**, tap a word: **Split line here**; hover between two lines: **Combine**. Only her script lines regroup: her cut, its length and its sound never change, and nothing unlocks (her cut and her looks stay locked in). A look on the line follows its words (a split keeps the half with its first word; a join covers both, and if both lines had one she picks which stays). Undo puts it back. |
| Start over | "Start over from your rough cut" in the toast that says her edits were picked up (two taps, one undo). |
| A Send that didn't go through | The page says so at once, wherever she is ("Your last change didn't go through", with the reason), and the note at the top of her script keeps saying it. **Go back to my last cut** (in that message and that note) drops her unsent changes in one tap; Undo brings them back. After a refresh, unsent changes the engine refused are said the same way, so the button never sits on **Send my cut** without a reason. A Send that never reached her cut (no receipt in `review/applied/`, nothing refused) is said too ("Your last Send didn't reach your cut"). A Send her cut couldn't take (it came back without that change) is said with the words named ("your cut didn't take one change you sent"), and the page shows the cut as it is, so **Lock in my cut** comes back instead of the same Send again. |
| Claude changed her cut from the chat | Her page loads the new cut by itself. Only the changes she had NOT sent ride on top of it; what she already sent is never replayed over Claude's change. A Send pressed from the older page in the moment before it reloads is turned back ("Your cut was just updated") and the page reloads; she presses Send again. A Send with nothing in it never unlocks a cut she locked in. |
| Jump to a line | Click a word, or the blank space of its row (Cut and Visuals): the player and timeline go to the line's start. |
| Leave Claude a note | Tap a word, **Add a note**. Quick picks: Sounds clipped · Awkward pause · Wrong take · Mumbled. |
| Cut part of a clip with no talking | A clip she filmed with no one talking (her kids, a vlog moment) shows as **No talking · Ns** lines, five seconds to a line, each second a small block (`product/quiet_clips.py`: the transcript marks it silent and sets aside what the transcriber "heard" in its background sound, so it never becomes a caption, and the rough cut keeps it whole). Tap blocks or the line number, **Cut N seconds**; everything else works as with words (Bring back, the timeline tools, Visuals, Cover a face). In chat: `python3 product/quiet_clips.py check <job>`. A stretch with no talking INSIDE a talking clip (b-roll she kept, a held look) shows the same way, and every Send and every `restitch` keeps it exactly as it is (`keep_edges` + `no_trim`), so no edge pass drops it. |

**Trimming on the timeline, exactly.** Every tool is one undo step and lives on the Cut tab (the tool row above the
timeline: **Split · Cut before playhead · Cut after playhead · Delete · Speed · Zoom**, then timeline zoom **− slider +**).
Narrower windows drop the key hints, then the Cut before / after words (icons and tooltips stay).
- **Edges are smooth, like CapCut:** an edge stays exactly where she drops it, even partway into a word. A word the edge
  covers completely (less than 50 ms of it left) is cut; a struck word it uncovers comes back. The tip says what
  changed ("+0.12 s", "+1 word back", "2 words cut"). Hold **Shift** while dragging to move 10× slower.
- **Limits:** an edge goes out at most 4 s and stops at the nearest word that already plays (so nothing doubles); it
  can't pass the last 50 ms of the clip's own last (or first) word. Only the dragged clip changes.
- **The scale holds while she edits** (pixels per second of her cut): trimming moves only what comes after the clip,
  never the whole timeline. Zoomed in, the timeline scrolls (trackpad, wheel, or scrub near its ends) and her words
  show along the waveform. All the way in is about 400 px a second.
- **The playhead stays put:** clicking a clip only selects it, and an edge drag leaves the playhead where it was.
  The ruler and waveform move it; **,** and **.** step it one frame. The view follows the playhead only while it plays.
- **Taller timeline:** drag the grip on the timeline's top edge up (bigger clips and waveform; double-click resets;
  remembered on her browser). Not on phones.
- **Splits are real, and hers:** a split in the quiet between two words is an end edge on one word and a start edge
  on the next; anywhere else (inside a word, or in a clip's opening or closing quiet) it is a split by time. A side of
  a time split may hold no words at all (a quiet stretch); Delete, Q / W or dragging its edge cuts exactly that
  stretch by time (sent as `holes`), and a word wholly inside it is struck in her script too. The engine cuts the
  piece in the same places (`visual_editor.apply_edits`, steps 1 and 4). Her edges are kept exactly (the clean-edge pass never moves them). Edges she
  sent are part of her new cut; edges dragged but never sent belong to the old cut, and if the cut is remade under
  them the page says they need dragging again.

**Where the page tells her.** The Cut tab's intro line says to trim on the timeline like CapCut, the first-visit tour
mentions it, and Shortcuts lists B, Q, W and , / . (not shown on touch screens).

**The breath warning.** Cutting a word said in one breath with its neighbor gives "may sound a touch clipped" with
Undo. That's a heads-up, not a fault.

## The timeline (the dock, every tab)

Play button, time, and the timeline: one block per **clip** of her cut (a line in several clips reads 02a, 02b), a
filmstrip, her waveform, and the playhead. Click or drag the ruler or waveform to move the playhead. On **Cut**,
clicking a block selects it and its edges drag (see "Trimming on the timeline"); on Visuals and Sound, a block takes
her to that line. Visuals
and Sound add lanes for looks and sounds: click a look to jump to it, a sound dot to play it. On Sound, **drag a sound
dot** left or right to retime it (mouse or touch): a faint ghost stays where it was and a readout says how far it went
and where it lands ("+0.35s · 0:07.4"); it lands on a frame (1/30 s; hold Alt/Option to place it freely), never before
0:00 or past the end of her cut, and the playhead follows it. A tap that doesn't move (under 4 px) still plays it.
Focus a dot (Tab) and **← →** move it one frame, **Shift ← →** 0.1 s (a run of presses is one move). Where it lands is
the sound's nudge (`/sound-nudge`, the same one the ⋯ menu sets), so **⋯ › Back to its moment** puts it back. A look's
own sound has no drag (it moves with its look). Her **b-roll** has its own
**B-ROLL** lane above the main track (the main track stays her cut and its sound; a cutaway never changes it): one block
per cutaway showing its clip, a muted or speaker icon on it; cutaways that overlap get a row each, the later one above
(it plays on top). Drag a block to move it, drag an edge to trim it (both land on her words; never longer than the
clip, "End of your clip" says so); tap it for its panel. Dimmed on Cut.

## Visuals tab

| She wants to | How |
|---|---|
| Change a line's look | **Swap** on the line's look chip (tiles play on hover, their own video clips included; "Your original" is first; "Remove this look" at the end). **♥ My favorites** in the filter row narrows it to the effects she hearted in her Effects Library (see "See only the effects she hearted"). |
| Move, size or turn a look | **⋯ › Move**, ✥ on the player, or click the graphic on the player. The playhead never moves for a look that's on screen (only one that isn't showing is brought to its moment), the player's ✥ picks the line's own look over her whole-reel captions, and Done / Cancel leave the playhead where it is. The box and its handles track the look's real ink while she sizes and turns it (the pivot is measured in the look page's own root box). Drag to move, corner to size, dot to turn (Shift = 15° steps), scroll or pinch to size; snaps to the center lines (Alt turns snapping off); arrows 6 px, Shift 24 px. The two icon buttons at the left of the Move bar center it in one tap: **Center left to right** (a line down through a box) and **Center top to bottom** (a line across through a box). Each puts the look's visible middle on the frame's center line, shown live with the pink guide; like a drag, Done saves it and Cancel puts it back. On a narrow panel the two icons sit on their own row above Reset · Cancel · Done. The Move bar sits UNDER the phone, in the play controls' place while Move is open (they come back after), so nothing covers the look she's moving, low captions included; its "Your call" note shows in the notices above the phone (on a real phone, under the bar). In a short window the bar stays on the part of the panel she can see, above the timeline, and scrolling the panel to its end shows the whole phone above it. Done or Enter saves. Captions move for the whole reel and don't size or turn here (their left-to-right button is greyed out: captions stay centered side to side). |
| Change its words or animation | **⋯ › Refine**: Words, Animation, a note to Claude, "Save as a new look…" to keep it in her pack, "Apply to this line". A look with a heading of its own over her words (a checklist) shows it in Words as "heading / her list": she changes the heading before the /, the list after it (in chat: `place ... --text "heading / item, item, item"`; each item still ticks when she says it). A graphic made just for this reel is note-only there ("Send to Claude"). |
| Take a look off / bring it back | **⋯ › Remove** (or "Back to your original"); a removed look shows **Bring back**. Undo after a swap, a removal or a Sandbox lock-in puts back exactly what the line had a moment before: a line that was empty is empty again (never an older look she had already taken off it). |
| Add a look | Select words, **Add a look**; or **+ Add a look** on a line with none. One tap on a tile puts it on, even one marked "May overlap your …" (the overlap is said once, after). A **hook** (Hook, Eyebrow + headline, Headline + subhead) says its own thing, never her spoken line: its tile shows a sample, and picking it opens a box for the hook's words (a / splits the small line from the big words), **Use this hook**, or **Ask Claude to write it** (a look idea in her task queue; in chat it's a `place ... --text` on that line). A quiet line (no words, "No talking") offers just the hooks, with her own words; captions need words, so there are none to add there. In chat, `place` puts a look on a reel with no talking at all too (it times the "No talking" seconds from her cut's pieces). |
| Leave a reel with no looks | A reel can go out clean (a b-roll clip, nothing on it). Once Claude has done the looks step for her cut (`visual_editor.py looks <job>` marks it in `review/looks-made.json`), or she took her looks off herself, Visuals opens as normal with **0 looks** (the Looks, Captions and Footage menus all there), Sound and Finish open after **Lock in my looks**, and the page never asks Claude for looks again (`looks.json` carries `"clean": true`). |
| Add her own picture or clip | **Media** on the line: her Favorites, her Inbox, or Add new (images and GIFs up to 40 MB, clips up to 200 MB; up to 8 picks, one after another or all at once; two or more b-roll clips always go one after another, each filling the screen for its share of the line). **Add new** and drag-and-drop take every file she gives them, not just the first, and name any that didn't save. When several go on at once and one fails, the rest still land and the page names the one to add again. Typing an idea in the Tell Claude box instead sends each pick to Claude as a Sandbox idea; to put a GIF straight on the reel, leave that box empty and tap **Add it**. A new idea never replaces one that already has sketches, a build Claude is on, or her picture: the page says why and points to **Lock it in**, **Cancel this idea** or **Remix**. |
| B-roll on several lines at once (any reel) | **Footage ▾ › Fill with my b-roll** (Visuals toolbar, once her cut is locked in): her inbox folder, then **Which lines get b-roll?** (her lines, numbered as on her page, ticked one by one; her face stays on every other line), and a note if she likes. It goes to Claude like a voiceover's fill ("fill my b-roll"), who puts the best moment of a fitting clip on each line she ticked: two ticked lines in a row play as one stretch, nothing lands on a line she didn't tick (`broll-fill` refuses one), and a clip she placed herself is never covered. A voiceover has no line picker: every line gets a clip (see "A voiceover reel"). |
| Cut away to b-roll | **Media**, then a clip tagged **B-roll** (favorites' `broll/` drawer, loose in her inbox, or `inbox/b-roll/`; her talking-footage folders aren't offered). It fills the frame over the line while her voice keeps going, muted, playing the clip's best moment (`broll-select.py`'s scorer), ending on a word. Its card is "B-roll: <name>". **⋯ › Refine** (or tap its block on the B-ROLL lane) opens its panel: **Which moment plays** (slide to slip the clip; it stays on the same words), **Engine's pick**, **When it's on screen** (start / end a word earlier or later), **Its sound** (Muted · On, under my voice, set 10 LU under her voice), **Comes in** (Cut · Fade), **Apply**. In chat: `visual_editor.py cutaway <job> <add-key> slip= start= end= sound=on|off`. Exports to MP4 as footage under every look; in CapCut as its own layer (its sound in the clip when on). |
| Highlight a word in the captions | Tap it, **Highlight** (or **H**). |
| Captions on part of the reel | Select words, **Captions here**; **Captions ▾** in the toolbar for the style. |
| Change the color feel | **Footage ▾ › Filter**: None, Cinematic, Warm, Cool, Film, Black & white. |
| Hide her kids' faces | **Footage ▾ › Cover a face** (there as soon as her cut is locked, looks or not). The first open finds every face in her clips (`face_cover.py find`, under a minute per minute of footage, with a progress bar on the page) into `review/faces.json`. Opt-in: nothing is covered until she taps a face. **1 Which faces should be covered?** every face from every video in her reel as round tiles (grouped "Video 1 · <file>", "Video 2 · <file>" when there's more than one; the same child in two videos is two tiles, one tap each); tap to cover, tap again to show. A newly covered face starts as 🙈. **2 Cover with:** Blur, Pixelate, ten emoji, or **Your own** (any picture, as a sticker); a size slider; **Use on every face**. **3 Check these moments:** the stretches where a covered face was turned away or out of view (the cover held its spot, riding with whoever stayed in view), each with **Watch** and **Looks right?**, over a strip she can scrub, one row per covered face with its face and cover beside it. Cover slipped: pause, drag it back on the player; the fix carries through that moment. Saved as she goes (`review/face-cover.json`, plus each emoji or sticker as the PNG the page drew). At Finish it's built into her footage first, under her filter and every look, on both routes (`face_cover.py bake`); nothing moves out of a cover's way. B-roll cutaways are other footage and aren't covered. In chat: `uv run product/face_cover.py status <job>`. |
| Switch the whole pack | **Looks ▾ › My looks**, a pack tab, "Use <Pack> for this reel" (same as typing "switch my reel to <Pack>"). |
| Make a pack her default | **Looks ▾ › My looks**, a pack tab, **Make <Pack> my default** (under the tabs). Every NEW reel opens in it, on the editor and every build route; the reel she is on keeps its own pack unless she also presses "Use <Pack> for this reel". Her default's tab is tagged "your default". In chat: "make <Pack> my default". |
| Put a look on a whole line | Tap one word on Visuals: **Add a look** / **Captions here** cover that word's whole line as her lines stand now (split or combined), never the old break; drag across words to pick exactly those words. |
| A look that doesn't exist yet | **Looks ▾ › Build new** (her idea shows in two lines there, links counted, tap to read it all, so the sketches stay in view): describe it on any lines, send, then type **"sandbox"** in Claude. Three sketches come back; Remix or Lock it in (for every reel, or just this one). Going **Back** from waiting sketches never offers to start fresh: it points to Remix, or **Cancel this idea** (right there) when she wants something new. Trying a sketch never bumps her own look off the line, and cancelling an idea removes only that idea's sketch. **Lock it in** suggests a name that says what the look IS ("Card pop orbit": the sketch's design.json `name`, else a few words from its `about`), never the first words of her idea; the look's id follows the name, and a name she types wins. A sketch that carries its own words (its design.json `note`, like the handles on her cards, or no words at all) locks in on a stretch with no talking, so it works on a b-roll reel (`place_look` uses the note; in chat no `--text` needed). Or **Looks ▾ › My looks › Build a new look**, then "build my look" in Claude. |
| See every effect the engine can make | **Looks ▾ › Browse** (the Effects library). Opens the full Effects Library in her own browser, on its Effects tab, served from her computer (`scripts/open-library.sh effects`). She can heart effects there, or name one to Claude. Her hearts show up in the editor under **My favorites** (next row). |
| See only the effects she hearted | **♥ My favorites**, the chip at the end of the filter row in **Swap**, **Add a look** and the **Lookbook** (her heart count on it). One tap shows only her hearts, read fresh from `favorites/effects.json` (what the library saves) each time the sheet opens. A heart that IS one of the page's looks is its tile, marked ♥, ready to tap (a look she saved on top of it too); the library names that map are `visual_editor.HEART_LOOKS`: karaoke, word-by-word (Single word), bottom-pop (Phrase), full-screen-takeover (Takeover), stat-countup (Count-up card). Every other heart (catalog pieces, text animations, grades) is listed by its library name: on a line (Swap, Add a look), tapping one sends Claude "put <effect> on this line" as a look idea (her task queue; in chat it's a `look-requests` entry, built with **build my look**); in the Lookbook there's no line, so the list says to name one to Claude. **All** brings everything back. Her pick is remembered in that browser, so the next sheet opens on her favorites. No hearts yet: one line saying so, and **Open my Effects Library** to heart some. |
| Something reads too close to her face or the edge | The warning under the card has **Move it for me** and **It's okay**. Nothing is blocked. |

Not on the page: changing when a look starts or how long it holds (timing comes from the words it sits on; a
different stretch = select those words and Add a look, or a note), and reordering lines. Those go to Claude.

## A voiceover reel (her voice first, then her clips)

A voiceover she chose to edit here (`voiceover-reel` → "Edit it in my visual editor"; `visual_editor.py vo-start`
made the reel, `voiceover.json` marks it) runs the same four tabs. Her recording is laid on a black 9:16 picture, so:

| She wants to | How |
|---|---|
| Trim her voiceover | The **Cut** tab, exactly as on any reel: words, the timeline's edges, Split, Q / W. Her phone shows a blank screen that says "Your voiceover. Your clips go on in Visuals." That is the design, never a fault. How tight the pauses between her lines start out is the pace she picked (punchy or emotional, `vo-pace`), asked before the cut. |
| Fill her voiceover with her clips | **Visuals › Footage ▾ › Fill with my b-roll** (voiceover reels only, once her cut is locked in): she picks a folder in her inbox (every inbox folder with clips in it is listed) and can type what she wants ("the kitchen clips first"). It goes to Claude (the watcher takes it; otherwise the page copies **fill my b-roll**). Claude watches every clip, matches them to her lines and lays one on every line, one after another, each running on to the next, so the picture never goes black (`visual_editor.py broll-fill`). A second fill replaces only what the last fill laid. |
| Put a clip on one line herself | **Media** on the line, like any reel. Her fill folder's clips are listed first (on any reel she filled). A fill never lands on a clip she put on herself. |
| Change a clip | Each one is an ordinary b-roll cutaway: its block on the **B-ROLL** lane (drag to move, edges to trim), **⋯ › Refine** (Which moment plays, its sound, Cut or Fade), Swap, Remove. Its card shows a still of the clip itself. A clip longer than 30 s is kept as the stretch around its moment (6 s of room either side), so **Which moment plays** slides within that; for a different part of a long clip, put it on again with Media. |
| Where one clip ends and the next begins | Claude cuts on her words, not her line breaks (`vo-beats`): at a sentence end, a pause or a comma, never right after a word that leads on; shots hold longer on an emotional pace than a punchy one, and a voiceover opens on a few quick cuts. A shot can run across two lines. To change one, drag its block's edge on the B-ROLL lane. |
| See where there's no clip yet | The phone says "No clip here yet" at that moment. On **Finish**, any stretch with no clip is said once ("…shows a black screen. Okay with that?") with **Yes, it's fine** and **Show me** (Visuals, at that moment, her script scrolled to the line); Export renders either way. |

Captions and other looks go on the same way as any reel ("show me my looks"), following the voiceover's caption rules.
A cut from one clip to the next gets no sound effect of its own on a voiceover (the clips are the picture, not a
graphic that moves); her music bed and any sound she adds work as on every reel.

## Sound tab

Music bed: play, **Swap / Add music**, **− / +** (3 dB a tap, remembered for her next reels), on/off. A switch for
all sound effects. Under each line, each sound: play, **Swap** (search; "No sound here" at the end), mute, **⋯** for
"A little earlier" / "A little later" (0.05 s a tap) / "Back to its moment" / **Note for Claude** (the note names that
sound and its moment, `[Sound: <name> at 0:03]`), delete. To move a sound further, drag its dot on the timeline's sound
lane, or focus it and use the arrow keys (see "The timeline"); any distance inside her cut, shown on its row as
"+0.42s". Every line also has a **Note for Claude** chip, as on Visuals
(`[Sound]`). **Every motion gets its own sound:** a look that brings things in at separate moments (four cards popping in one after another, a list's lines) has one row per motion, each at its own time, saying "Part of your <look> · 2 of 4" (`sound_plan.entrances`: things 0.3 s apart or more; a closer burst is one; positions timed by a loop are read pass by pass). A hook, takeover, captions, type-on or count-up stays one row, and two looks bringing something in on the same frame (a sketch's in-front and behind halves) share one sound. **Add a sound** on a line with none, or at the playhead; her favorites folder is one tap away. **Sound library** (toolbar) opens the full
Effects Library in her own browser on its Sounds tab, every sound playable (`scripts/open-library.sh sounds`). Sounds and music play in the preview on Sound and
Finish only. Pressing play (or landing after a skip) inside a sound that is still going, a song under a stretch or a
typing burst, plays it from that spot, as the export has it there; a sound that already ended, or has only its last
quarter second left, stays silent. A sound whose file loads late joins where the playhead is. **A level set in the
chat:** a sound she added that carries its own `gain_db` in `review/sound.json` ("added") shows as set and plays at
exactly that level in the preview and every export (CapCut, MP4); swapping it levels the new sound the engine's way.
**Changed from the chat:** when Claude changes her sounds (`review/sound.json`, or the plan under it), an open Sound
tab picks it up within a few seconds ("Your sounds are updated."), never while a sheet, a Swap menu or a dragged
sound is open (it waits until it closes). **A look's own sound** (a design or Sandbox sketch can carry one, an `<audio>` in its page, like an echo)
gets its own row ("Part of your …") with play, mute and **⋯ › Note for Claude** only (it's the look: swap the look to change it). It plays with
the look on Visuals, in the Sandbox and lookbook tiles on hover, on Sound and Finish through her sound plan, and every
export lays it in at its moment, leveled against her voice (`sound_plan.look_sounds`). The Sound FX switch leaves it.

**A muted clip** (her clip's own sound off for the whole reel, e.g. a clip she'll put music under in CapCut): there is
no button for it on the page yet. She asks in the chat or leaves a **Note for Claude** ("mute my clip"), and Claude runs
`python3 product/sound_plan.py voice <job> off` (`on` brings it back). Her page preview then plays with no voice, the
CapCut export puts her cut on the main track at volume 0, and the MP4 export carries no voice; her sound effects and
music bed still play.

## Finish tab

**CapCut**, the **Edits app**, **DaVinci Resolve** or an **MP4 file** (remembered), then **Export** in the dock. If a check flags something: one question,
"Okay with that?" (Yes, they're fine · Move them for me · Which ones?); Export renders whatever she answers. A failed
export offers Show me · It's on purpose · Tell Claude. Also here: **Your snaps** (Save this frame, or **S**; star one as
her cover), **Make a carousel**, and **Make a story**. When it's done, the Finish panel and the "your reel is ready"
sheet show where it landed: an **Edits app** export names your project after your reel and gives **Open the Edits
app** to bring it forward and find your project there (not a folder); CapCut gives **Open CapCut**; the others
**Show in folder**. Then **Turn it into:** carousel · story, their one home after an export (the snaps card's
"Turn this reel into a post" row hides then); the "your reel is ready" sheet groups them the same way.

**Trial reels (Beta)**, their own section on Finish, only after an export and never on a trial's own page. Before any
trials: an invite card, **Make trial reels**, which saves `review/trial-request.json` for the watcher (the `trial-reels`
skill: plan 3 real re-edits, one pick-many in the chat, then `trial_reels.py make`), or copies "make trial reels". With
trials (`trials/trials.json`, `visual_editor.trials_view`): tiles **A** (her reel) then **B, C, D**, each with its
opening shot, its first words, what changed, and its state (being planned · ready to watch in the editor · waiting
its turn · exporting, about N min · ready). Buttons: **Watch** (a made MP4), **Open in editor** (switches the page to
`<job>-trial-<id>`), **Show in folder** / **Open CapCut**, **This one won** (`trials/won.json`, a watcher
`trial-won` item: keep its angle with `teach_style.py keep`). **Export all trials** runs `visual_editor.trials_export`
from the page, one at a time, in her Finish route, with this computer's own minutes a trial (`_local/trial-export-times.json`,
12 until it has some). While trials export, her reel's own Export waits. On a trial's own page a banner says "Trial B of
<reel> · Back to your reel", and its Finish exports just that trial.

## Everywhere

- **Undo / Redo** (top bar, ⌘Z / ⇧⌘Z) cover cuts, trims, timeline splits and clip deletes, a clip's Speed and Zoom, highlights, line split and combine, swaps and removals, deleting
  a sound. Sound swaps, mutes, nudges, music, Move, Refine, Filter and pack switches aren't on the undo list (swaps
  show their own Undo toast).
- **Keys:** Space play/pause · ← → 5 s · Shift ← → 15 s · , . one frame · Delete cut (whatever she picked last: the clip she
  clicked on the timeline, or the words she tapped in her script; a clip click drops a script selection, and a word
  tap drops a clip selection) · B split · Q / W cut before / after the playhead · S save this frame · G safe zones · V hide or show the tools on the phone (the "sits behind your head" note steps off too) · H highlight · Esc clear the selection ·
  ⌘Z / ⇧⌘Z. None work while a sheet is open or she's typing. B, Q, W and clip Delete are Cut tab only.
- **Notes:** "Anything else about …?" at the bottom of a tab, with "Make this my default for every reel".
- **Report a problem** (top bar) makes one file for her to email; nothing is sent.
- **Show me around** replays the tour. Each tab's tour shows once: finishing or skipping it is remembered by the engine
  (`_local/editor-tour.json`), so a new browser or page address never brings it back, and a tour returns only when its
  words change in an update. **Light/dark** toggle (not on phones).
- **Offline:** the banner tells her to type "open my editor". While an export runs, edits wait.
- **"🧑‍🍳 Chef Claude is cooking"** marks the big steps only: locking in her cut (the bar across the top while her
  full-quality cut is made), Claude making her first looks (the card above the preview and the note under the hero),
  and an export. Just the headline and one line that turns every few seconds ("Sautéing your reel"...), what's cooking
  being one of the turns; when it lands, "Chef's kiss, we're ready to eat. Bon appétit!" for a moment. A quick update
  after Send is said plainly ("Updating your cut · just a few seconds"). While an export renders her captions, one small grey line under the bar says not to worry: captions take the longest because they run under every second of her reel.
  An export's percentage covers every step it runs, each weighted by its real work (her full-quality cut, each look,
  the 1080 copy, the CapCut draft's extra footage and caption copy, or the burn and phone copy), and moves inside each
  one; it never goes back and shows 100% only when the export is done (`finish.py` `_Bar`, `review/finish.json` `progress`).
- **Two surfaces, split by source (2026-11-07).** Every update from Claude lands in the **chat**; the **bell**
  (top bar) holds a different class only: major REE updates and news from the engine's maker. They never overlap, so nothing repeats.
- **Claude's messages land in the chat panel.** A question, an approval, her sketches landing, a note fixed, a new look,
  her looks made, an export done: each is one synthesized line in the chat (never a "See my notes" button, never a log of
  edits behind a click). A new one still **peeks** as a card at the top of the notices above her preview for about 9 s,
  then it's in the chat ("N more in your chat" when others wait); one that needs her in the chat stays until she reads it.
  Its button goes where the news is (**Open my Sandbox**, **Go to Visuals / Sound / Finish**) and closes it. In another
  tab the title reads "(1) A note from Claude" / "(1) Claude needs you", the engine's soft chime plays (her chime switch
  applies), and a browser notification shows when she allowed it (**Tell me in other tabs too**, offered once). It comes
  from `review/claude-says.json` (`product/editor_says.py`, in `/status`; a background tab checks `/says` every 15 s
  without counting as her using the page). The chat's question box and permission prompts pop "Claude has a question for
  you" (`.claude/hooks/editor-says.sh`) and take it down when she answers in the chat. Claude's own line:
  `python3 product/visual_editor.py tell <job> "<one plain line>" [--chat] [--go sandbox|cut|visuals|sound|finish]`.
- **The notification bell holds announcements only** (top bar, next to Report a problem): a red count of new ones, and a
  dropdown that tags each **REE** (an engine update is ready) or **News** (a note from the engine's maker) with an X to dismiss it, plus
  **Mark all as read** and a footer line ("Engine updates and news. Your edit updates are in the chat."); an
  empty bell says "No new updates." The REE "Update ready — v…" banner comes from `_local/update-available.json`; a
  piece of news is `python3 product/visual_editor.py announce <job> "<text>" --kind news|ree [--title "…"] [--go finish]`
  (`product/editor_announce.py`, `review/announce.json`, in `/status`; dismiss posts `/announce-seen`). Claude never
  routes a per-edit update here.
- **An export always finishes.** A render check that flags a look is a warning: the look renders as placed (nothing
  alarming on her page). A look that still can't be made goes out without that one look, and the Finish card says so in
  one small grey line ("Heads up: gif library (0:55) didn't come through this time... Ask Claude to take a look"). An
  export that stopped partway keeps the bar across the top on every tab ("Your export stopped partway · open Finish to
  pick it back up") until she opens Finish.
- **The task queue** ("With Claude", above her preview) is everything she has sent Claude: notes on her cut, notes on a
  look or a section, Sandbox ideas and their remixes, new-look ideas, looks to redo on a new cut. One row each, a short
  label and a step bar: **Sent · Claude has it · (Working) · Done** (Working is for Sandbox and look ideas), plus one bar
  for the round (done of total). The row Claude is on wears a tiny chef hat. Done rows fade, then go (**Clear done** takes
  them now); the header folds it. It comes from `visual_editor.task_queue` (in `/status`): claimed by `wait` / `todo` =
  has it, `sandbox-working` = working, `resolve` / `sandbox-takes` / `look-request … done` = done. While Claude's watcher
  is running nothing on the page tells her to type anything; only with no watcher does the card say "Type “update my
  edit” in Claude" (a button inside the queue; never a second card for the same items).
- **The workspace is three framed panels on the cream ground** — the script panel (left: her cut / visuals / sound / finish
  by tab), the preview (middle), and the chat with the engine (right) — with the timeline below. **She resizes them by
  dragging the divider between the script and the preview, or between the preview and the chat** (double-click a divider to
  reset it to its default; the widths are remembered in her browser). The dividers behave like normal splitters: dragging
  one right shrinks the panel on its right. The chat panel stays the same height as the preview. There is no "Regular /
  Bigger" phone button any more — the preview size follows its panel. **On a 9:16 reel the phone fills its panel's full
  height (width follows), the chat column stays narrow, and the transcript fills the rest. On a 16:9 (YouTube) reel the
  layout is different: the transcript owns the LEFT, and the preview sits over the chat on the RIGHT. It has two resize
  bars — a vertical one between the transcript and the preview/chat column, and a HORIZONTAL one under the video that
  trades height between the preview and the chat. Every bar is clamped so it can't be dragged out of sight. The Finish
  tab hides the chat so the export routes lay out across in one row and the preview grows.** A **Reset the layout** button
  (the circular-arrow icon in the top bar) puts every panel, bar and the timeline height back to default in one tap.
- **Reel shape follows her footage; the editor matches it on its own.** A reel's shape comes from what she films or
  uploads: vertical phone clips are a **9:16 Reel** (the three-panel vertical editor, the phone, the Instagram safe
  zones); uploaded wide footage is a **16:9 YouTube** reel (the horizontal editor: the wide player on top, the cut and
  the chat beneath it, the **YouTube safe guides**). Nothing to switch and nothing is reframed, the editor reads the
  footage's shape and lays itself out to match. A read-only badge by the Preview title ("9:16 · Reel" / "16:9 ·
  YouTube") just says which. The **safe-zones button (G)** shows the Instagram bands on a 9:16 reel and the YouTube
  guides (title-safe, action-safe, the player-controls strip, the end-screen zone) on a 16:9 one.
- **The chat panel is where she talks to the engine, and where Claude talks back.** She types in it ("make the hook
  bigger", "add a sound on line 1") and Claude does it on the reel and replies in the same thread — Claude's messages
  and updates all land here now (not a card over the phone; the bell is for REE/news announcements only). The moment she sends,
  a **receipt row** appears in the chat (three dots + "Claude is on it…", or "Sent — Claude will pick this up." when the watcher
  is off) and clears itself the instant Claude's first reply lands, so she always knows her message got through. The spark button in the top bar
  hides or shows the chat (hidden, the cut and preview take the whole width). The server writes her message to
  `review/chat.json`; the watcher hands it to Claude in `todo()` as a `[chat:…]` item; Claude answers with
  `visual_editor.py tell <job> "…" --chat`. When no watcher is running the header reads "Not connected" and, once she
  has sent something, a line tells her to type **open my editor** in Claude Code — her message is saved and picked up
  the moment it connects. Any system dictation (Wispr Flow, macOS Dictation) types into the box; the mic button is a
  reminder of that, not its own recorder (so nothing of hers leaves her computer).
- **The phone keeps its shape and place.** It holds its 9:16 (or 16:9) shape and stays centered in the preview panel, and
  its play controls pin to the bottom of that panel so a short window never pushes them off (the phone scrolls under them
  if it truly must). A look being moved is held still at its moment, so its box can't slip off it. Notices (Claude's message,
  the card, the task queue) still show in a band above the phone and collapse to nothing when there's none.
- **The eye** (first button under the preview, left of play, or **V**): hides the tools that float on the phone (a look's
  Swap / Move / Refine bar, Snap, the Preview pill) for a clean view of her reel; the eye crosses out while they're
  hidden, and it's remembered in her browser. Nothing is lost: clicking a look on the phone still opens Move, the
  line's ⋯ still has every tool, S still snaps. "Can I hide the buttons on the preview?" → this.
- **Safe zones** (the phone-with-bands button next to it, or **G**): shades where Instagram's own header ("Reels"), the
  like / comment / share buttons and the name and caption sit over her reel, from the engine's own bands
  (`safe_zones.py`: top 270, bottom 300, the right-hand buttons from x 900), with dashed edges. A guide, never a wall:
  it doesn't block clicks (Move grabs looks right through it) and nothing in her reel changes. Remembered in her
  browser; hidden for a landscape reel.
  Move still shows its own striped bands while she drags.
- **Snap and Preview** (top corners of the preview) fold to just their icons when the phone is narrow, so they never
  run into each other.
- **A note on a look** (Refine's note box, Finish's "Tell Claude") pins to that look's own word, so it shows under the
  line its card is on, wherever the playhead was.
- **Lock in always works**, even while Claude works through her notes: it locks in, says how many notes are still open
  in one line, and Claude's fixes land on her cut with her lock kept. **Export** works from any step (it locks in what
  wasn't) and says in one line what isn't in it yet (an open note; looks made for an earlier cut go out where they sat).
  **Lock in my looks** locks her cut too if it wasn't. A failed sound mix still delivers her reel (her voice), said once.
  A Sandbox sketch she locks in is kept as she picked it (a detail it trips goes on Claude's list); a line split where a
  line already starts, a cutaway too long for its clip, an image exit too soon, a sound past the reel's end or a level
  past the range are done as close as possible, never refused.
- **Her note cards:** an open one is warm cream with her red edge and says where it stands ("Waiting for Claude", "Sent to
  Claude", or "🧑‍🍳 Claude's on it"); a done one is soft green with ✓, her words muted and "Fixed: …" under them.

## What the page tells her to type in Claude

"open my editor" (or "open my visual editor", "show me the visual editor") · "the original widget" · "show me my looks" · "update my edit" · "sandbox" · "build my look" ·
"make a carousel" / "make a story" · "make trial reels" · "make my cover" · "/report-a-problem". What each one does on your side is in
the `rough-cut` skill. When the watcher (`visual_editor.py wait`) is running, the page says "It's with Claude" instead.
If the page can't load her script it tries again for a few seconds before showing "Something on this page didn't load right", which has a **Reload** button and records why in her editor log. When a change has to wait ("still being made", an export running), the page always says so and logs it as told, never as an error.
"make my preview again" (her page says "Your preview copy is shorter than your cut"): `python3 product/visual_editor.py preview <job> --force`, then she reloads her page (open/prepare already remake a copy shorter than her cut, and name a clip in raw/ that is itself too short).

## Her notes: how you handle them

`python3 product/visual_editor.py notes <job>` lists each with its line, word and footage time; fix them in a scratch
copy of `transcript/cuts.json`, `restitch`, then `resolve` (the `rough-cut` skill has the steps). **Awkward pause** =
split the clip around the gap. A note asking for a clip to be faster, or to zoom in or out ("speed up this clip, start
zoomed in and zoom out"): `python3 product/visual_editor.py clip-fx <job> <clip number> --speed 2 --zoom out` (the clip
number her timeline shows; `--zoom in|out|none`; `--speed 1` = normal). Same road as her page's Speed and Zoom. For a
"faster at first, then slower" or a custom ramp, write the one segment with `"speed": {"from": 2.6, "to": 1.4, "ease":
"out"}` (eases: linear, in, out, inOut) and `"zoom": {"from": 1.3, "to": 1.0, "ease": "out"}` in a fixed plan and
`restitch` it. Never split a clip into pieces to fake a ramp.
A note (or a chat ask) for a look's animation: `python3 product/visual_editor.py look-effect <job> <look key> <effect>`
(`default` = the pack's own). It draws it and keeps it, as her Refine and Keep do, and refuses an animation that look
can't show, naming the ones it can. Never call `refine()` on its own from the chat: it only fills the Refine sandbox,
so nothing reaches her preview.
**A change you make FOR her keeps her lock-in:** `clip-fx` and `restitch` re-stamp `review/phase.json` with the new cut
when she had locked it, and her looks follow their words (`retime_adds`) without asking her to confirm. Only HER Send of
cut edits reopens the Cut step. When she asks in the chat instead ("cut the dead space at 8 to 10 seconds"), the
times she sees are times in her CUT: map them to footage time through `cuts.json` first, then the same split and
`restitch`; her page picks it up by itself.

<!-- editor-guide-stamp: 746c5ef0fc36 -->
