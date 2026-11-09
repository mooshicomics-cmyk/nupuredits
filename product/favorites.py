#!/usr/bin/env python3
"""favorites.py — read the creator's favorites project in CapCut and make it the engine's taste.

The favorites project (spec: product/FAVORITES-PROJECT.md) is a CapCut project that is not a reel. It is a
shelf: she drops in the things she likes and the engine reads it. Adjectives do not survive the trip to a
builder ("high class", "punchy"); examples do. A creator who cannot describe her taste can always point at it.

BUILT: the SOUND half. Every sound on the shelf is copied into `_local/sounds/` and becomes part of the
engine's sound library, outranking the bundled set (capcut_sfx.palette() scans it last, so hers win). Her
"don'ts" (vary these, never the same one twice in a row, no whooshes on serious reels) are saved with them.
ALSO BUILT: `learn-style` — read a finished CapCut project she LOVES (not her shelf) and fold its taste in:
the text animations she used become the default in/out on hooks and other text in CapCut builds
(cleanyap / superyap `add_text`, when the reel's own plan names none), how busy its sound is becomes her
`sfx.density`, and its fonts + colors are reported so she can save them as a pack. Her sounds shelf is never
touched by it. Type sizes are reported, not applied (CapCut's stored size is not the builder's size unit).

`_local/` is protected by the updater and never ships, so her shelf survives every update.

  python3 product/favorites.py list                         # CapCut projects that hold sounds, newest first
  python3 product/favorites.py learn "my sound palette"     # read that project's sounds (re-run as it grows)
  python3 product/favorites.py learn "my sound palette" --rule "never the same sound twice in a row"
  python3 product/favorites.py rule "no whooshes on serious reels"   # add a don't later
  python3 product/favorites.py show                         # what the engine is using now (read this before choosing sounds)
  python3 product/favorites.py forget-rule 2                # drop one rule by its number in `show`
  python3 product/favorites.py forget                       # drop the whole shelf, sounds + rules (her CapCut project
                                                            # is untouched; a learned style stays until forget-style)
  python3 product/favorites.py learn-style "my best reel"   # fold in the style of a reel she loves
  python3 product/favorites.py forget-style                 # stop using it

Reading only. It never writes to CapCut, so CapCut can stay open.
Precedence, lowest to highest: bundled sounds -> her favorites -> what she asks for on THIS reel. The mood
rules still win over all of it: a somber reel gets no sound even when her shelf is full.
"""
import argparse, datetime, json, os, re, shutil, sys

for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import draft_safety as ds

LOCAL = os.path.join(ROOT, "_local")
SOUNDS = os.path.join(LOCAL, "sounds")          # capcut_sfx.palette() scans this; hers outrank the bundled set
STATE = os.path.join(LOCAL, "favorites.json")

# Audio in a draft that is NOT a sound she picked: the footage's own audio, a voiceover she recorded,
# text-to-speech. Everything else (CapCut library sounds, music, files she imported) is on the shelf.
NOT_A_PICK = {"video_original_sound", "record", "text_to_audio", "tts"}
LONGEST_SFX_S = 15.0    # longer than this is a music track, not a sound effect: listed, not added
AUDIO_EXT = (".mp3", ".wav", ".m4a", ".aac")


def load():
    try:
        with open(STATE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save(state):
    os.makedirs(LOCAL, exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, STATE)


def slug(title):
    """'Camera shutter sound. "Kasha"(92309)' -> 'camera-shutter-sound-kasha'."""
    t = re.sub(r"\(\d+\)", "", str(title))
    t = os.path.splitext(t)[0] if t.lower().endswith(AUDIO_EXT) else t
    t = re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")
    return (t[:60].rstrip("-") or "sound")


def drafts():
    """(name, folder) for every CapCut project on this machine, newest first."""
    out = []
    for n in ds._drafts():
        p = os.path.join(ds.CAP, n)
        try:
            js = ds.draft_json(p)
            out.append((os.path.getmtime(js), n, p))
        except Exception:
            continue
    return [(n, p) for _t, n, p in sorted(out, reverse=True)]


def find(name):
    """The project she named. Exact name first, then ignoring case/spacing, then a unique partial match."""
    all_ = drafts()
    key = lambda s: re.sub(r"\s+", " ", s.strip().lower())
    for test in (lambda n: n == name, lambda n: key(n) == key(name), lambda n: key(name) in key(n)):
        hits = [(n, p) for n, p in all_ if test(n)]
        if len(hits) == 1:
            return hits[0], None
        if len(hits) > 1:
            return None, [n for n, _p in hits]
    return None, []


def resolve(path, draft_dir):
    """A material path as a real file: expands CapCut's per-draft placeholder."""
    p = re.sub(r"##_draftpath_placeholder_[0-9A-Fa-f-]+_##", draft_dir.replace("\\", "/"), str(path or ""))
    return p if p and os.path.isfile(p) else None, p


def sounds_in(draft_dir):
    """Every sound she picked in this project, in timeline order, de-duplicated by file."""
    with open(ds.draft_json(draft_dir), encoding="utf-8") as fh:
        d = json.load(fh)
    first_at = {}
    for tr in d.get("tracks", []) or []:
        if tr.get("type") != "audio":
            continue
        for seg in tr.get("segments", []) or []:
            mid = seg.get("material_id")
            at = (seg.get("target_timerange") or {}).get("start", 0)
            if mid and (mid not in first_at or at < first_at[mid]):
                first_at[mid] = at
    picks, seen = [], set()
    for m in d.get("materials", {}).get("audios", []) or []:
        if m.get("type") in NOT_A_PICK:
            continue
        real, raw = resolve(m.get("path"), draft_dir)
        ident = real or raw
        if not ident or ident in seen:
            continue
        seen.add(ident)
        picks.append({"title": m.get("name") or os.path.basename(raw), "src": real, "raw": raw,
                      "seconds": round((m.get("duration") or 0) / 1_000_000, 2),
                      "order": first_at.get(m.get("id"), float("inf"))})
    picks.sort(key=lambda s: s["order"])
    return picks


def learn(name, rules):
    hit, many = find(name)
    if not hit:
        if many:
            return f"More than one CapCut project matches \"{name}\": {', '.join(many)}. Which one is it?", 2
        return (f"I couldn't find a CapCut project called \"{name}\". Run `python3 product/favorites.py list` "
                f"to see the projects that have sounds in them."), 2
    dname, ddir = hit
    picks = sounds_in(ddir)
    state = load()
    old_files = {s["file"] for s in state.get("sounds", [])}
    os.makedirs(SOUNDS, exist_ok=True)
    # A sound still on her shelf that CapCut does not have on this computer right now (its cache was
    # cleared, or it has not downloaded again yet) keeps the copy saved last time. Keeping a copy is the
    # whole reason sounds are copied; a re-read used to delete it exactly when it was needed.
    saved_copy = {}
    for s in state.get("sounds", []):
        if s.get("file") and os.path.isfile(os.path.join(ROOT, s["file"])):
            saved_copy.setdefault(s.get("title"), []).append(s)
    keep_old = {}
    for i, p in enumerate(picks):
        if p["seconds"] <= LONGEST_SFX_S and not p["src"] and saved_copy.get(p["title"]):
            keep_old[i] = saved_copy[p["title"]].pop(0)
    kept, music, missing = [], [], []
    used = {s.get("name") for s in keep_old.values() if s.get("name")}   # a new copy never lands on a kept one
    for i, p in enumerate(picks):
        if p["seconds"] > LONGEST_SFX_S:
            music.append(p["title"]); continue
        if i in keep_old:
            kept.append(keep_old[i]); continue
        if not p["src"]:
            missing.append(p["title"]); continue
        base, n = slug(p["title"]), 2
        stem = base
        while stem in used:
            stem = f"{base}-{n}"; n += 1
        used.add(stem)
        ext = os.path.splitext(p["src"])[1].lower() or ".mp3"
        rel = f"_local/sounds/{stem}{ext}"
        shutil.copy2(p["src"], os.path.join(ROOT, rel))
        kept.append({"name": stem, "title": p["title"], "file": rel, "seconds": p["seconds"]})
    # the shelf is what is in the project NOW: a sound she took off it leaves the library too
    for f in old_files - {s["file"] for s in kept}:
        try: os.remove(os.path.join(ROOT, f))
        except OSError: pass
    all_rules = state.get("rules", [])
    for r in rules:
        if r.strip() and r.strip() not in all_rules:
            all_rules.append(r.strip())
    # Update the saved state rather than replace it: it also holds the style `learn-style` folded in, and a
    # fresh dict here used to erase that every time she re-read her shelf.
    state.update({"draft": dname, "learned_at": datetime.datetime.now().isoformat(timespec="seconds"),
                  "sounds": kept, "rules": all_rules})
    save(state)

    lines = []
    if kept:
        lines.append(f"I found {len(kept)} sound{'s' if len(kept) != 1 else ''} in \"{dname}\". "
                     f"They're your go-to set now, and every reel reaches for them first:")
        lines += [f"  {i}. {s['title']}  ({s['seconds']:.1f}s)" for i, s in enumerate(kept, 1)]
        if keep_old:
            lines.append(f"CapCut doesn't have {', '.join(keep_old[i]['title'] for i in sorted(keep_old))} on "
                         f"this computer right now, so I kept the cop{'y' if len(keep_old) == 1 else 'ies'} I saved last time.")
    elif missing:
        # The project HAS sounds; CapCut just has not got them here right now. Never say it has none.
        one = len(missing) == 1
        lines.append(f"\"{dname}\" has {len(missing)} sound{'' if one else 's'} in it, but CapCut doesn't have "
                     f"{'it' if one else 'them'} saved on this computer right now: {', '.join(missing)}. Open "
                     f"\"{dname}\" in CapCut once so it downloads {'it' if one else 'them'} again, then ask me "
                     f"to re-read it.")
    else:
        lines.append(f"\"{dname}\" doesn't have any sound effects in it yet. Drop your favorites into it in "
                     f"CapCut, then ask me again.")
    if all_rules:
        lines.append("Your rules:")
        lines += [f"  - {r}" for r in all_rules]
    if music:
        lines.append(f"Left out, because they're music tracks rather than sound effects: {', '.join(music)}.")
    if missing and kept:
        lines.append(f"CapCut doesn't have these saved on this computer right now: {', '.join(missing)}. Open "
                     f"\"{dname}\" in CapCut once so it downloads them again, then ask me to re-read it.")
    return "\n".join(lines), 0


# ───────────────────────────── learn-style: a reel she loves ─────────────────────────────
# Same read-only rule as the shelf. What is folded in, and how:
#   text animations -> default in/out for text the build does not animate itself (hook role vs other text)
#   sound density   -> learned.py `sfx.density` (so every sound pass reads it)
#   fonts / colors  -> REPORTED with the offer to save them as a pack (a pack is its own decision)
# An animation is only used when the editor engine can place it (matched by CapCut resource id or name).

def _catalog():
    """(resource_id -> api name, lowercase title -> api name), keyed by kind 'in' / 'out', for every text
    animation the editor engine can place. Read straight from the engine's own table (plain text), because
    importing the package pulls in the editor's heavy dependencies. Empty when the engine is not installed,
    and then nothing is applied."""
    by_id, by_name = {}, {}
    src = os.path.join(HERE, "engine", "VectCutAPI", "pyJianYingDraft", "metadata", "capcut_text_animation_meta.py")
    try:
        with open(src, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return by_id, by_name
    kind = None
    for line in text.splitlines():
        m = re.match(r"\s*class\s+CapCut_Text_(intro|outro)\b", line)
        if m:
            kind = "in" if m.group(1) == "intro" else "out"; continue
        if re.match(r"\s*class\s+", line):
            kind = None; continue
        m = re.match(r'\s*([A-Za-z0-9_]+)\s*=\s*Animation_meta\(\s*"([^"]+)"\s*,[^,]+,[^,]+,\s*"(\d+)"', line)
        if m and kind:
            attr, title, rid = m.groups()
            by_id[(kind, rid)] = attr
            by_name[(kind, title.lower())] = attr
    return by_id, by_name


def _rgb_hex(rgb):
    try:
        return "#" + "".join(f"{max(0, min(255, round(float(c) * 255))):02X}" for c in rgb[:3])
    except Exception:
        return None


def style_in(draft_dir):
    """What a project's own choices say about her taste: text roles, animations, fonts, colors, sound."""
    with open(ds.draft_json(draft_dir), encoding="utf-8") as fh:
        d = json.load(fh)
    mats = d.get("materials", {}) or {}
    texts = {t.get("id"): t for t in mats.get("texts", []) or []}
    anims = {a.get("id"): a.get("animations", []) or [] for a in mats.get("material_animations", []) or []}
    dur = max(1, int(d.get("duration") or 0)) / 1_000_000

    rows = []           # one per text segment on the timeline
    full = {}           # (name, resource_id) -> the animation's full CapCut record, for the swap
    for tr in d.get("tracks", []) or []:
        if tr.get("type") != "text":
            continue
        for seg in tr.get("segments", []) or []:
            t = texts.get(seg.get("material_id"))
            if not t:
                continue
            try:
                content = json.loads(t.get("content") or "{}")
            except ValueError:
                content = {}
            st = (content.get("styles") or [{}])[0]
            font = ((st.get("font") or {}).get("path")) or t.get("font_path") or ""
            color = _rgb_hex((((st.get("fill") or {}).get("content") or {}).get("solid") or {}).get("color") or [])
            size = st.get("size") or t.get("font_size") or 0
            a_in = a_out = None
            for ref in seg.get("extra_material_refs", []) or []:
                for a in anims.get(ref, []):
                    if a.get("type") == "in" and a.get("name"):
                        a_in = (a.get("name"), str(a.get("resource_id") or ""))
                        full[a_in] = a
                    elif a.get("type") == "out" and a.get("name"):
                        a_out = (a.get("name"), str(a.get("resource_id") or ""))
                        full[a_out] = a
            rows.append({"start": (seg.get("target_timerange") or {}).get("start", 0) / 1_000_000,
                         "font": os.path.splitext(os.path.basename(font))[0] if font else "",
                         "color": color, "size": round(float(size or 0), 1),
                         "in": a_in, "out": a_out, "text": (content.get("text") or "")[:40]})

    # the hook = the biggest text on screen in the first 3 seconds; everything else is "other text"
    early = [r for r in rows if r["start"] <= 3.0]
    hook_ix = max(range(len(rows)), key=lambda i: (rows[i] in early, rows[i]["size"])) if rows else None
    for i, r in enumerate(rows):
        r["role"] = "hook" if i == hook_ix else "text"

    sounds = 0
    for tr in d.get("tracks", []) or []:
        if tr.get("type") == "audio":
            sounds += len(tr.get("segments", []) or [])
    # the footage's own audio / her voice is not a sound pick
    sounds -= sum(1 for m in mats.get("audios", []) or [] if m.get("type") in NOT_A_PICK)
    sounds = max(0, sounds)
    per10 = sounds / dur * 10
    density = "lighter" if per10 <= 1.0 else "heavier" if per10 > 3.0 else "normal"
    trans = [x.get("name") for x in mats.get("transitions", []) or [] if x.get("name")]
    fx = [x.get("name") for x in mats.get("video_effects", []) or [] if x.get("name")]
    return {"rows": rows, "full": full, "sounds": sounds, "seconds": round(dur, 1), "per10": round(per10, 1),
            "density": density, "transitions": trans, "effects": fx}


def _top(values):
    c = {}
    for v in values:
        if v:
            c[v] = c.get(v, 0) + 1
    return sorted(c, key=lambda k: -c[k])


def learn_style(name):
    hit, many = find(name)
    if not hit:
        if many:
            return f"More than one CapCut project matches \"{name}\": {', '.join(many)}. Which one is it?", 2
        return f"I couldn't find a CapCut project called \"{name}\". Check the exact name in CapCut and ask again.", 2
    dname, ddir = hit
    info = style_in(ddir)
    by_id, by_name = _catalog()

    def placeable(kind, pair):
        if not pair:
            return None
        nm, rid = pair
        return by_id.get((kind, rid)) or by_name.get((kind, nm.lower()))

    anim, unplaceable = {}, []
    for role in ("hook", "text"):
        rs = [r for r in info["rows"] if r["role"] == role]
        for kind in ("in", "out"):
            picks = _top(r[kind] for r in rs if r[kind])
            for pair in picks:
                attr = placeable(kind, pair)
                if attr:
                    anim[f"{role}.{kind}"] = {"name": pair[0], "api": attr}
                    break
                # Newer CapCut animations the editor engine has no name for. CapCut keeps the animation's
                # files on this computer, so the build places a stand-in and finalize swaps hers in.
                rec = info["full"].get(pair)
                stand_in = by_name.get((kind, PLACEHOLDER[kind].lower()))
                if rec and stand_in and os.path.exists(str(rec.get("path") or "")):
                    keep = {k: v for k, v in rec.items() if k not in ("request_id", "start")}
                    anim[f"{role}.{kind}"] = {"name": pair[0], "api": stand_in, "swap": keep}
                    break
                if pair[0] not in unplaceable:
                    unplaceable.append(pair[0])

    fonts = {role: _top(r["font"] for r in info["rows"] if r["role"] == role)[:1] for role in ("hook", "text")}
    colors = _top(r["color"] for r in info["rows"])[:3]
    sizes = {role: [r["size"] for r in info["rows"] if r["role"] == role] for role in ("hook", "text")}

    density_saved = False
    if info["sounds"]:
        try:
            import learned
            learned.add("sfx.density", info["density"], note=f"from the CapCut project \"{dname}\"")
            density_saved = True
        except Exception:
            pass

    state = load()
    state["style"] = {"draft": dname, "learned_at": datetime.datetime.now().isoformat(timespec="seconds"),
                      "animations": anim, "fonts": fonts, "colors": colors, "density": info["density"],
                      "transitions": info["transitions"][:5], "effects": info["effects"][:5]}
    save(state)

    lines = [f"I studied \"{dname}\" ({len(info['rows'])} text layers, {info['sounds']} sounds over "
             f"{info['seconds']:.0f}s). Here is what I'm folding in:"]
    if anim:
        for key, label in (("hook.in", "hooks come in with"), ("hook.out", "hooks leave with"),
                           ("text.in", "other text comes in with"), ("text.out", "other text leaves with")):
            if key in anim:
                lines.append(f"  - {label} \"{anim[key]['name']}\" (on your CapCut builds)")
    else:
        lines.append("  - no text animations I can place yet")
    if density_saved:
        lines.append(f"  - sound: {info['per10']} sounds per 10 seconds, so I'll keep your reels {info['density']}")
    if unplaceable:
        lines.append(f"These are in that project, but CapCut hasn't kept their files on this computer, so I left "
                     f"them out (open the project in CapCut once and ask me again): "
                     f"{', '.join(unplaceable)}.")
    if any(fonts.values()) or colors:
        f_bits = [f"{role} font {fonts[role][0]}" for role in ("hook", "text") if fonts[role]]
        lines.append(f"Your type: {', '.join(f_bits)}"
                     f"{'; colors ' + ', '.join(colors) if colors else ''}. Say \"save this as my pack\" "
                     f"to make that your look on every reel.")
    if info["transitions"] or info["effects"]:
        lines.append(f"Also noted (used only when you ask): {', '.join((info['transitions'] + info['effects'])[:5])}.")
    lines.append("Your own sounds shelf wasn't touched. Say \"forget that style\" any time to stop using it.")
    return "\n".join(lines), 0


PLACEHOLDER = {"in": "Fade In", "out": "Fade Out"}   # stand-in the build places, swapped at finalize


def style_needs_swap(role, kind):
    a = (load().get("style") or {}).get("animations", {}).get(f"{role}.{kind}")
    return bool(isinstance(a, dict) and a.get("swap"))


def apply_style_swaps(d, roles_by_text):
    """Swap her real CapCut animation in for the stand-in, on the text the BUILD animated from her style.
    `roles_by_text` = {normalized text: role} recorded by the builder's add_text. A stand-in the reel asked
    for on purpose is never on that list, so it is never touched. Returns how many were swapped."""
    anims = (load().get("style") or {}).get("animations", {}) or {}
    if not roles_by_text or not any(isinstance(a, dict) and a.get("swap") for a in anims.values()):
        return 0
    norm = lambda t: re.sub(r"\s+", " ", str(t or "")).strip()
    mats = d.get("materials", {}) or {}
    texts = {m.get("id"): m for m in mats.get("texts", []) or []}
    groups = {m.get("id"): m for m in mats.get("material_animations", []) or []}
    n = 0
    for tr in d.get("tracks", []) or []:
        if tr.get("type") != "text":
            continue
        for seg in tr.get("segments", []) or []:
            m = texts.get(seg.get("material_id"))
            if not m:
                continue
            try:
                txt = json.loads(m.get("content") or "{}").get("text")
            except ValueError:
                txt = None
            role = roles_by_text.get(norm(txt))
            if not role:
                continue
            for ref in seg.get("extra_material_refs", []) or []:
                g = groups.get(ref)
                if not g:
                    continue
                for i, a in enumerate(g.get("animations", []) or []):
                    kind = a.get("type")
                    want = anims.get(f"{role}.{kind}")
                    if not (isinstance(want, dict) and want.get("swap")) or a.get("name") != PLACEHOLDER.get(kind):
                        continue
                    new = dict(want["swap"])
                    new["start"] = a.get("start", 0) if kind == "in" else a.get("start", 0)
                    g["animations"][i] = new
                    n += 1
    return n


def style_animation(role, kind):
    """The API name of the text animation she taught for `role` ('hook' | 'text') and `kind` ('in' | 'out'),
    or None. The CapCut builders call this only when the reel's own plan names no animation."""
    a = (load().get("style") or {}).get("animations", {}).get(f"{role}.{kind}")
    return a.get("api") if isinstance(a, dict) else None


def hearted_effects():
    """The effects she hearted in the Effects Library (favorites/effects.json, written by scripts/library-server.py).
    Her favorites folder: no update touches it."""
    try:
        data = json.load(open(os.path.join(ROOT, "favorites", "effects.json"), encoding="utf-8"))
        return [n for n in data.get("effects", []) if isinstance(n, str)]
    except Exception:
        return []


def _hearted_lines():
    h = hearted_effects()
    if not h:
        return []
    return [f"Effects she hearted in the library ({len(h)}): " + ", ".join(h),
            "Offer these first where one fits a line, on a medium or well-done reel; she still approves the plan."]


def show():
    st = load()
    if not st.get("sounds") and not st.get("rules") and not st.get("style"):
        return "\n".join(["No favorites project read yet. The engine is using its own sound library. To teach it yours: "
                          "make a CapCut project with your favorite sounds in it, then say \"study my CapCut draft called "
                          "<its name>\"."] + _hearted_lines())
    if st.get("draft") or st.get("sounds"):
        out = [f"Favorite sounds, from \"{st.get('draft')}\" (read {st.get('learned_at', '?')}):"]
    else:       # only rules or a folded-in style so far: there is no shelf to name
        out = ["No favorites project read yet, so the engine is using its own sound library."]
    for s in st.get("sounds", []):
        ok = os.path.isfile(os.path.join(ROOT, s["file"]))
        out.append(f"  {s['name']}  ({s['seconds']:.1f}s){'' if ok else '  [file missing: re-read the project]'}")
    out.append("Rules:" if st.get("rules") else "Rules: none yet.")
    out += [f"  {i}. {r}" for i, r in enumerate(st.get("rules", []), 1)]
    out.append("Use these names in the plan's sfx. The mood rules still apply: a somber reel stays silent.")
    sty = st.get("style") or {}
    if sty:
        out.append(f"Style folded in from \"{sty.get('draft')}\" (read {sty.get('learned_at', '?')}):")
        for k, a in (sty.get("animations") or {}).items():
            out.append(f"  {k}: {a.get('name')}")
        out.append(f"  sound density: {sty.get('density')}")
    return "\n".join(out + _hearted_lines())


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    a = sub.add_parser("learn"); a.add_argument("draft"); a.add_argument("--rule", action="append", default=[])
    r = sub.add_parser("rule"); r.add_argument("text")
    sub.add_parser("show")
    f = sub.add_parser("forget-rule"); f.add_argument("n", type=int)
    sub.add_parser("forget")
    ls = sub.add_parser("learn-style"); ls.add_argument("draft")
    sub.add_parser("forget-style")
    args = ap.parse_args()

    if args.cmd == "list":
        rows = []
        for n, p in drafts():
            try:
                c = len(sounds_in(p))
            except Exception:
                continue
            if c:
                rows.append(f"  {n}  ({c} sound{'s' if c != 1 else ''})")
            if len(rows) >= 20:
                break
        print("CapCut projects with sounds in them, newest first:\n" + "\n".join(rows) if rows
              else "None of your CapCut projects have sounds in them yet.")
        return 0
    if args.cmd == "learn":
        msg, code = learn(args.draft, args.rule); print(msg); return code
    if args.cmd == "show":
        print(show()); return 0
    if args.cmd == "learn-style":
        msg, code = learn_style(args.draft); print(msg); return code
    if args.cmd == "forget-style":
        st = load(); st.pop("style", None); save(st)
        print("Done. New builds stop using that style. Your CapCut project is untouched, and any sound "
              "density it set stays in /learn list until you forget it there."); return 0
    st = load()
    if args.cmd == "rule":
        st.setdefault("rules", [])
        if args.text.strip() not in st["rules"]:
            st["rules"].append(args.text.strip())
        save(st); print(show()); return 0
    if args.cmd == "forget-rule":
        rules = st.get("rules", [])
        if not 1 <= args.n <= len(rules):
            print(f"There is no rule {args.n}. {show()}"); return 2
        gone = rules.pop(args.n - 1); save(st)
        print(f"Dropped: {gone}\n{show()}"); return 0
    if args.cmd == "forget":
        # the SHELF goes (its sounds and its rules); a style she folded in with learn-style is a separate
        # thing she asked for separately, and only `forget-style` drops it
        shutil.rmtree(SOUNDS, ignore_errors=True)
        style = st.get("style")
        if style:
            save({"style": style})
        else:
            try: os.remove(STATE)
            except OSError: pass
        print("Done. The engine is back to its own sound library. Your CapCut project is untouched."
              + (f" The style you folded in from \"{style.get('draft')}\" is still in use; say \"forget that "
                 f"style\" to stop it." if style else "")); return 0


if __name__ == "__main__":
    sys.exit(main())
