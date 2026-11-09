#!/usr/bin/env python3
"""trial_reels.py — trial reels: versions of a finished reel to post as Instagram trial reels (shown to people who
don't follow her yet), so she learns which version pulls.

A trial must be a genuinely different edit. Instagram reads the same footage with a new text card as the same reel
posted again, so on a talking-head reel a hook swap is not enough (her rule, 2026-10-17). The `trial-reels` skill plans
each trial; this file makes them. How depends on how the reel was finished (`status` says which):
  * editor      her visual editor reel: a REAL RE-EDIT (product/trial_edits.py). Its own copy of her reel,
                projects/<job>-trial-<id>/, re-cut (a later line moved to the front, lines left out), her looks moved
                with her words, optionally another pack or captions and a new hook, exported through Finish (MP4 or
                CapCut). The copy is a full reel she can open in her editor.
  * capcut      a CapCut draft from the reel's own build script, finished by her in CapCut: a REAL RE-EDIT of HER
                finished draft (product/capcut_recut.py) into a new draft "<her draft> trial B". Her draft is only
                read: every layer (her grade, compound, graphics, sounds) is cut with her clips, a later clip moved
                to the front, clips left out, and the hook drawn in a style she set herself in CapCut (her draft's
                own hook, else a hook from another of her drafts, the pack's fonts first). Only when her draft
                isn't on this computer: the hook swap (product/trial_hook.py), with the plain repost warning.
  * well-done   a baked MP4: the hook swap only, for now (everything but the hook rendered once, each trial baked with
                its own hook). The same plain warning.

Files: projects/<job>/trials/trials.json (the plans). Editor trials live in their own reel folders; hook-swap MP4s in
projects/<job>/outputs/trials/ (a subfolder, so name-final never clears them). Trial ids are b, c, d... ("a" is the
reel she already has).

CLI
  python3 product/trial_reels.py status <job>             how this reel was finished, its hook now, how trials are made
  python3 product/trial_reels.py lines <job>              her cut, numbered (what "open" and "drop" name); on a
                                                          CapCut reel, her draft's clips with the words in each
  python3 product/trial_reels.py write <job> <plans.json> save the trials: [{"open": "50-51", "drop": ["42-46"],
                                                          "pack": "Editorial", "captions": "phrase", "hook": "a / b",
                                                          "shape": "eyebrow-headline", "angle": "..."}]
  python3 product/trial_reels.py list <job>               the saved trials and which are made
  python3 product/trial_reels.py make <job> [--only b,c]      editor reels: prepared to watch and tweak, nothing rendered
                                                          (--export also exports; other reels are made outright)
  python3 product/trial_reels.py export <job> [--only b,c] [--to mp4|capcut]   export prepared trials
  CapCut reels: --draft "<name>" (the draft to re-cut) and --hook-from "<name>" (whose hook style to copy) on
  status / lines / write override what the engine found; write saves them for make.
"""
import glob, json, os, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

NO_TYPED_HOOK = ("This reel's CapCut build doesn't type its hook as text, so there's nothing for a trial to swap. "
                 "Nothing was added to CapCut. In CapCut, duplicate your draft once per trial and type each trial hook "
                 "over yours.")
SHAPES = ("hook", "eyebrow-headline", "headline-subhead")     # the three hook shapes (WRITING-THE-HOOK.md)
MAX_TRIALS = 5
IDS = "bcdefg"


class Refuse(Exception):
    """A plain-words reason a trial can't be made right now (what to do is in the words)."""


def job_dir(job):
    jd = job if os.path.isabs(job) else os.path.join(ROOT, "projects", job)
    if not os.path.isdir(jd):
        raise Refuse(f"There's no reel called {os.path.basename(job)!r} in your projects folder.")
    return os.path.normpath(jd)


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    for attempt in range(40):                                # Windows refuses the swap while the page is reading the file
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 39:
                raise
            time.sleep(0.05)


def _halves(hook):
    return [p.strip() for p in re.split(r"\s+/\s+|\n", hook or "") if p.strip()]


# ─────────────────────────── how the reel was finished ───────────────────────────

def _build_script(jd):
    """The newest build script in the reel's folder that makes a CapCut draft (it calls finalize)."""
    best = None
    for p in glob.glob(os.path.join(jd, "build*.py")):
        try:
            src = open(p, encoding="utf-8").read()
        except OSError:
            continue
        if "finalize(" in src and ("import cleanyap" in src or "import superyap" in src):
            if best is None or os.path.getmtime(p) > os.path.getmtime(best):
                best = p
    return best


def _hook_layer(looks):
    for L in looks.get("layers", []):
        nm = (L.get("name") or "").lower()
        if re.match(r"^h\d+-hook", nm) or nm.split("-", 1)[-1].startswith("hook"):
            return L
    return None


def _pack_of(jd):
    cp = _read(os.path.join(jd, "caption-plan.json"), {})
    pk = cp.get("pack") or cp.get("style_pack")
    if not pk:                                               # the pack its overlay was last built in
        comps = sorted(glob.glob(os.path.join(jd, "hf-reel-type-*", "index.html")), key=os.path.getmtime)
        if comps:
            low = os.path.basename(os.path.dirname(comps[-1]))[len("hf-reel-type-"):]
            try:
                import stylepack
                pk = next((n for n in stylepack.names() if n.lower() == low), None)
            except Exception:
                pk = None
    if not pk:
        import user_style
        pk = user_style.default_pack(os.path.join(HERE, "creative-vault", "user-style.json"))
    return pk


def status(job):
    """{"how", "hook", "shape", "start", "dur", "why", ...}. how = editor / capcut / well-done / None."""
    jd = job_dir(job)
    name = os.path.basename(jd)
    import review_route
    out = {"job": name, "how": None, "hook": "", "shape": None, "start": 0.0, "dur": 8.0, "why": ""}
    looks_p = os.path.join(jd, "review", "looks.json")
    if review_route.get(jd) == "editor" and os.path.isfile(looks_p):
        looks = _read(looks_p, {"layers": []})
        L = _hook_layer(looks)
        swaps = (_read(os.path.join(jd, "review", "swaps.json"), {}).get("swaps") or {})
        if L:
            meta = _read(os.path.join(jd, os.path.dirname(L.get("dir") or ""), "look.json"), {})
            off = bool(L.get("off")) or (swaps.get(L["name"]) or {}).get("look") == "_off" or L.get("look") == "_off"
            out.update(hook="" if off else meta.get("text", ""), shape=meta.get("look") if meta.get("look") in SHAPES else None,
                       start=float(L.get("offset") or 0.0), dur=float(L.get("dur") or 8.0), layer=L["name"], hook_off=off)
        fin = _read(os.path.join(jd, "review", "finish.json"), {})
        out["how"] = "editor"
        out["exported"] = (fin.get("state") == "done")
        out["why"] = ("her visual editor reel: the trial hook replaces hers over the looks Finish already rendered"
                      if out["exported"] else "her visual editor reel, not exported yet: Export it from Finish first")
        her = _editor_capcut_draft(jd, fin) if out["exported"] else None
        if her:                                              # exported to CapCut and reworked there: that draft is the reel
            rs = _recut_source(jd, None, draft=her)
            if rs:
                out.update(how="capcut", **rs, why="her editor reel, finished in CapCut: re-cut from her CapCut draft, "
                                                    "every layer she has cut with her clips")
                return out
        script = None if out["exported"] else _build_script(jd)
        if not (script and _recut_source(jd, script)):
            return out
        # opened in the editor but never exported from it, and finished as a CapCut draft: that draft is the reel
        out = {"job": name, "how": None, "hook": "", "shape": None, "start": 0.0, "dur": 8.0, "why": "",
               "editor_unexported": True}
    script = _build_script(jd)
    if script:
        out.update(how="capcut", script=os.path.relpath(script, ROOT).replace(os.sep, "/"),
                   why="a CapCut draft from its build script: built again into a new draft with only the hook's words changed")
        try:
            src = open(script, encoding="utf-8").read()
            consts = dict(re.findall(r'^(HOOK|HEADLINE|SUBHEAD|KICKER|EYEBROW)\s*=\s*"([^"]+)"', src, re.M))
            parts = [consts[k] for k in ("EYEBROW", "HOOK", "HEADLINE", "SUBHEAD", "KICKER") if k in consts]
            out["hook"] = " / ".join(parts)
            out["lines"] = len(parts) or None
            out["places_hook"] = bool(re.search(r'(add_text|\btext)\([^\n]*["\'](hook|eyebrow|headline|subhead|kicker)', src))
            if not out["places_hook"]:
                out["why"] = ("a CapCut draft whose build doesn't type the hook (it's a rendered layer, or she types it in "
                              "CapCut): she types each trial hook into a copy of her draft")
        except OSError:
            pass
        rc = _recut_source(jd, script)
        if rc:
            out.update(rc)
            out["why"] = (f"a CapCut draft she finished ({rc['draft']!r}): each trial is a real re-edit of that draft "
                          "(a new opening, clips left out, a new hook in a style she set in CapCut), into a new draft")
            if not rc["edited"]:
                out["why"] += "; that draft looks unopened since the engine built it, so it's the reel as built"
            if rc.get("her_hook"):
                out["hook"], out["lines"] = " / ".join(rc["her_hook"]), len(rc["her_hook"])
        return out
    cp = _read(os.path.join(jd, "caption-plan.json"), None)
    final = os.path.join(jd, "outputs", f"{name}.final.mp4")
    if cp is not None and os.path.isfile(final) and os.path.isfile(os.path.join(jd, "outputs", f"{name}.mp4")):
        hook = cp.get("hook") or ([cp["hook_long"]] if cp.get("hook_long") else [])
        hook = hook if isinstance(hook, list) else [hook]
        shape = "hook" if len(hook) < 2 else ("headline-subhead" if cp.get("hook_emphasis") == "first" else "eyebrow-headline")
        out.update(how="well-done", hook=" / ".join(hook), shape=shape, start=0.0,
                   dur=float(cp.get("hook_end", 8.0)), pack=_pack_of(jd),
                   why="a baked MP4: everything but the hook renders once, then each trial is baked with its own hook")
        return out
    out["why"] = "this reel isn't finished yet: finish it first (a CapCut draft or an MP4), then make trial reels"
    return out


# ─────────────────────────── the saved trials ───────────────────────────

def _trials_path(jd):
    return os.path.join(jd, "trials", "trials.json")


def trials(job):
    return (_read(_trials_path(job_dir(job)), {}) or {}).get("trials", [])


def write(job, hooks, draft=None, hook_from=None):
    """Save the trial hooks (replacing any not made yet; made ones keep their id). Returns the saved list.
    CapCut reels: `draft` / `hook_from` name the draft to re-cut and whose hook style to copy (saved for make)."""
    jd = job_dir(job)
    if not isinstance(hooks, list) or not hooks:
        raise Refuse("Give at least one trial hook.")
    meta = _read(_trials_path(jd), {}) or {}
    for k, v in (("draft", draft), ("hook_from", hook_from)):
        if v:
            if v not in set(_drafts_now()):
                raise Refuse(f"There's no CapCut draft called {v!r} on this computer.")
            meta[k] = v
    if draft or hook_from:
        _write(_trials_path(jd), meta)
    st = status(job)
    st_how = st["how"]
    have = [t for t in trials(job) if t.get("made")]
    used = {t["id"] for t in have}
    out = list(have)
    for h in hooks:
        if not isinstance(h, dict) or not ((h.get("hook") or "").strip() or h.get("open") is not None or h.get("drop")):
            continue
        h = dict(h, hook=(h.get("hook") or "").strip())
        if len(out) >= MAX_TRIALS:
            break
        shape = h.get("shape") if h.get("shape") in SHAPES else None
        if shape is None and h["hook"]:
            shape = "hook" if len(_halves(h["hook"])) < 2 else "eyebrow-headline"
        if h.get("hook") and shape != "hook" and len(_halves(h["hook"])) != 2:
            raise Refuse(f"A {shape.replace('-', ' + ')} hook has two lines, written \"first line / second line\": {h['hook']!r}")
        tid = next(c for c in IDS if c not in used)
        used.add(tid)
        spec = {"id": tid, "hook": h["hook"].strip(), "shape": shape, "angle": (h.get("angle") or "").strip(),
                "made": None, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
        if h.get("open") not in (None, "", []):              # a re-edit (editor reels): the line(s) that open it ("4-7")
            spec["open"] = h["open"]
        if h.get("drop"):
            spec["drop"] = h["drop"] if isinstance(h["drop"], list) else [h["drop"]]
        for k in ("pack", "captions"):
            if h.get(k):
                spec[k] = str(h[k])
        if h.get("hook_size"):                               # her hook bigger or smaller ("10% bigger" = 1.1)
            spec["hook_size"] = round(max(0.7, min(1.6, float(h["hook_size"]))), 3)
        if st_how == "editor":
            if spec.get("open") is None and not spec.get("drop"):
                raise Refuse("A trial of this reel needs a different edit, not just a new hook: give it a line to open "
                             "on, or lines to leave out (Instagram treats the same footage with a new card as a repost).")
            import trial_edits
            try:
                trial_edits.plan_segments(trial_edits.segments(jd), spec.get("open"), spec.get("drop"))   # a bad plan,
                trial_edits.check_brand(jd, spec)                                                       # a look she doesn't use
            except trial_edits.Refuse as e:
                raise Refuse(str(e))
        elif st_how == "capcut" and st.get("recut"):
            if spec.get("open") is None and not spec.get("drop"):
                raise Refuse("A trial of this reel needs a different edit, not just a new hook: give it a clip to open "
                             "on, or clips to leave out (Instagram treats the same footage with a new card as a repost).")
            _recut_order(st["clips"], spec.get("open"), spec.get("drop"))
        out.append(spec)
    meta["trials"] = out
    _write(_trials_path(jd), meta)
    return out


def _mark(jd, tid, **kv):
    d = _read(_trials_path(jd), {"trials": []})
    for t in d.get("trials", []):
        if t["id"] == tid:
            t.update(kv)
    _write(_trials_path(jd), d)


# ─────────────────────────── making them ───────────────────────────

def _run(cmd, cwd=None, env=None, what="a step"):
    p = subprocess.run(cmd, cwd=cwd or ROOT, env=dict(os.environ, **(env or {})), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (p.stdout or "") + (p.stderr or "")
    for line in out.splitlines():                           # the renderer's own plain lines (the time estimate) pass on
        if line.strip().startswith(("This render", "Putting your reel", "[trial] hook:")):
            print("  " + line.strip())
    if p.returncode != 0:
        tail = "\n".join(l for l in out.strip().splitlines()[-6:])
        raise Refuse(f"{what} didn't finish:\n{tail}")
    return out


def _render(comp, mov, what):
    _run([sys.executable, os.path.join(HERE, "reel_render.py"), "render", comp, "-o", mov], what=what)
    return mov


def _out_mp4(jd, tid):
    d = os.path.join(jd, "outputs", "trials")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{os.path.basename(jd)}.trial-{tid}.mp4")


def _capcut_python():
    venv = os.path.join(HERE, "engine", "VectCutAPI", "venv-capcut")
    for p in (os.path.join(venv, "bin", "python"), os.path.join(venv, "Scripts", "python.exe")):
        if os.path.isfile(p):
            return p
    return sys.executable


def _make_capcut(jd, st, t, to):
    if to == "mp4":
        raise Refuse("This reel was finished as a CapCut draft, so its trials are CapCut drafts too: export each one "
                     "from CapCut like the reel itself.")
    try:
        import finish
        if not finish._vectcut_up() and not finish._start_vectcut():
            raise Refuse("The CapCut build engine didn't start. Open product/engine/VectCutAPI/"
                         + ("start-editor.bat" if os.name == "nt" else "start-editor.command")
                         + ", leave that window open, then ask again.")
    except ImportError:
        pass
    if st.get("places_hook") is False:
        raise Refuse(NO_TYPED_HOOK)
    want = len(_halves(t["hook"]))
    if st.get("lines") and want != st["lines"]:
        print(f"  This reel's hook has {st['lines']} line{'s' if st['lines'] != 1 else ''} and trial {t['id'].upper()} "
              f"has {want}; the build places what fits and says the rest.")
    env = {"REE_TRIAL_HOOK": json.dumps(_halves(t["hook"]), ensure_ascii=False),
           "REE_TRIAL_NAME": "{name} trial " + t["id"].upper()}
    try:
        out = _run([_capcut_python(), os.path.join(ROOT, st["script"])], cwd=jd, env=env,
                   what=f"Trial {t['id'].upper()}'s CapCut draft")
    except Refuse as e:
        if "placed no hook text" in str(e):
            raise Refuse(NO_TYPED_HOOK)
        raise
    if "[trial] hook:" not in out:
        raise Refuse(NO_TYPED_HOOK)
    m = re.search(r"built \+ registered:\s*(.+?)\s*\|", out)          # cleanyap / superyap say the name they used
    return {"draft": m.group(1) if m else f"trial {t['id'].upper()}"}


# ─────────────────────────── a reel she finished in CapCut: re-cut her own draft ───────────────────────────

_TRIAL_NAME = re.compile(r"\btrial [A-Z](?: \d+\.\d+)?$")


def _drafts_now():
    import draft_safety
    try:
        return draft_safety._drafts()
    except Exception:
        return []


def _load_draft(name):
    import draft_safety
    try:
        with open(draft_safety.draft_json(draft_safety._draft_dir(name)), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _her_draft(jd, script):
    """The draft she finished this reel in: the newest version of the reel's CapCut draft (its build scripts name
    it) that she edited in CapCut, else its newest version. (name, edited) or (None, False)."""
    import draft_safety
    names = _drafts_now()
    have, bases = set(names), {draft_safety.base_of(n) for n in names}
    lits = set()
    for p in sorted(set(glob.glob(os.path.join(jd, "*.py")) + [script])):
        try:
            src = open(p, encoding="utf-8").read()
        except OSError:
            continue
        lits |= set(re.findall(r'"([^"\\\n{}]{1,120})"', src)) | set(re.findall(r"'([^'\\\n{}]{1,120})'", src))
    lineage = {draft_safety.base_of(x) for x in lits if x in have} | (lits & bases)
    versions = {n for b in lineage for n in draft_safety.list_versions(b) if not _TRIAL_NAME.search(n)}
    if not versions:
        return None, False
    edited = {n: bool(draft_safety.edited_in_capcut(n)) for n in versions}
    best = max(versions, key=lambda n: (edited[n], draft_safety._ver_key(n)))
    return best, edited[best]


def _stem(font):
    return re.sub(r"[\s_\-]+", "", os.path.splitext(os.path.basename(str(font)))[0]).lower()


def _pack_fonts(pack):
    """The pack's font names and files, normalized ("Helvetica Medium.ttf" -> "helveticamedium")."""
    try:
        import stylepack
        p = stylepack.load(pack)
    except Exception:
        return set()
    out = set()
    for e in (p.get("elements") or {}).values():
        if isinstance(e, dict):
            out |= {_stem(e[k]) for k in ("file", "font") if isinstance(e.get(k), str) and e[k]}
    out |= {_stem(v) for v in (p.get("fonts") or {}).values() if isinstance(v, str) and v}
    return out - {""}


def _hook_fonts(d):
    """The font of each line of a draft's hook block, top line first."""
    import capcut_recut
    pool, out = capcut_recut._pool(d), []
    for _t, s in capcut_recut.hook_segments(d):
        try:
            st = (json.loads(pool[s["material_id"]][1]["content"]).get("styles") or [{}])[0]
            out.append(_stem((st.get("font") or {}).get("path", "")))
        except Exception:
            out.append("")
    return out


def _hook_style_source(src, pack, want=1):
    """A hook she styled herself in CapCut, to copy for a trial's hook: her finished draft's own hook block first,
    then one in another of her drafts (one she edited in CapCut, or made herself), the pack's fonts first, then the
    newest. Only a block with at least `want` lines. None when she has none."""
    import capcut_recut, draft_safety
    d = _load_draft(src)
    if d is not None and len(capcut_recut.hook_segments(d)) >= want:
        return src
    fonts = _pack_fonts(pack) if pack else set()
    best = None
    for n in _drafts_now():
        if n == src or _TRIAL_NAME.search(n):
            continue
        edited, why = draft_safety.edited_in_capcut(n, why=True)
        if not (edited or why == "no-snapshot"):            # built by the engine and never touched: not her styling
            continue
        d = _load_draft(n)
        if d is None:
            continue
        hf = _hook_fonts(d)
        if len(hf) < want:
            continue
        try:
            mt = os.path.getmtime(draft_safety.draft_json(draft_safety._draft_dir(n)))
        except OSError:
            mt = 0.0
        key = (sum(f in fonts for f in hf), bool(edited), mt)
        if best is None or key > best[0]:
            best = (key, n)
    return best[1] if best else None


def _script_pack(jd, script):
    try:
        if not script:
            raise OSError("no build script")
        m = re.search(r'\bpack\s*=\s*["\']([^"\']+)["\']', open(script, encoding="utf-8").read())
        if m:
            return m.group(1)
    except OSError:
        pass
    try:
        return _pack_of(jd)
    except Exception:
        return None


def _editor_capcut_draft(jd, fin):
    """An editor reel exported to CapCut and then worked on there: her newest version of that draft she has edited
    in CapCut (or the one she named with --draft). None when she never touched it in CapCut (the editor reel is the
    reel). You: trials from her CapCut version, "there are tons of layers in CapCut"."""
    import draft_safety
    names = set(_drafts_now())
    saved = (_read(_trials_path(jd), {}) or {}).get("draft")
    if saved in names:
        return saved
    res = (fin or {}).get("result") or {}
    if res.get("route") != "capcut" or not res.get("draft"):
        return None
    for n in reversed(draft_safety.list_versions(draft_safety.base_of(res["draft"]))):
        if n in names and draft_safety.edited_in_capcut(n):
            return n
    return None


def _recut_source(jd, script, draft=None):
    """What a CapCut reel's trials are re-cut from, or None when her draft isn't on this computer."""
    import capcut_recut
    saved = _read(_trials_path(jd), {}) or {}
    names = set(_drafts_now())
    if draft in names:
        draft, edited = draft, None
    elif saved.get("draft") in names:
        draft, edited = saved["draft"], None
    else:
        draft, edited = _her_draft(jd, script)
    d = _load_draft(draft) if draft else None
    if d is None:
        return None
    if edited is None:
        import draft_safety
        edited = bool(draft_safety.edited_in_capcut(draft))
    try:
        clips = len(capcut_recut.clip_edges(d))
    except capcut_recut.Refuse:
        return None
    pack = _script_pack(jd, script)
    hook_from = saved.get("hook_from") if saved.get("hook_from") in names else _hook_style_source(draft, pack)
    return {"recut": True, "draft": draft, "edited": edited, "clips": clips, "pack": pack, "hook_from": hook_from,
            "her_hook": capcut_recut.hook_texts(d)}


def recut_lines(jd, st):
    """Her finished draft's clips, numbered, with the words in each: [{"n", "dur", "text"}]. The clips map 1:1 to her
    approved cut (transcript/cuts.json) when the counts match; else the words are read off the kept-words transcript
    by time."""
    import capcut_recut
    edges = capcut_recut.clip_edges(_load_draft(st["draft"]))
    segs = (_read(os.path.join(jd, "transcript", "cuts.json"), {}) or {}).get("segments") or []
    if len(segs) == len(edges):
        texts = [(s.get("transcript") or "").strip() for s in segs]
    else:
        words = (_read(os.path.join(jd, "outputs", os.path.basename(jd) + ".transcript.json"), {}) or {}).get("words") or []
        words = [w for w in words if w.get("type", "word") == "word" and "start" in w]
        texts = [" ".join(w["text"] for w in words if a <= (w["start"] + w.get("end", w["start"])) / 2 * 1e6 < b).strip()
                 for a, b in edges]
    return [{"n": i + 1, "dur": round((b - a) / 1e6, 2), "text": texts[i]} for i, (a, b) in enumerate(edges)]


def _recut_order(n, open_n=None, drop=()):
    """The trial's clip numbers in play order (the opening first, dropped clips out, the rest in her order)."""
    import trial_edits
    try:
        return [x["n"] for x in trial_edits.plan_segments([{"n": i, "seg": {"n": i}} for i in range(1, n + 1)],
                                                          open_n, drop or ())]
    except trial_edits.Refuse as e:
        raise Refuse(str(e).replace("line", "clip"))


def _runs(order):
    """[18, 19, 20, 1, 2, 3] -> "18-20,1-3": neighboring clips stay one piece, so nothing is cut where she didn't cut."""
    out, i = [], 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and order[j + 1] == order[j] + 1:
            j += 1
        out.append(str(order[i]) if i == j else f"{order[i]}-{order[j]}")
        i = j + 1
    return ",".join(out)


def _make_recut(jd, st, t, to):
    if to == "mp4":
        raise Refuse("This reel was finished as a CapCut draft, so its trials are CapCut drafts too: export each one "
                     "from CapCut like the reel itself.")
    import capcut_recut, draft_safety
    tid = t["id"].upper()
    if t.get("open") is None and not t.get("drop"):
        raise Refuse(f"Trial {tid} has no different edit (only a new hook), so it would read as a repost. "
                     "Give it a clip to open on or clips to leave out.")
    src = st["draft"]
    spec = _runs(_recut_order(st["clips"], t.get("open"), t.get("drop")))
    lines = _halves(t.get("hook")) or None
    hook_from, dur = None, None
    if lines:
        saved = (_read(_trials_path(jd), {}) or {}).get("hook_from")
        own = len(st.get("her_hook") or [])
        if own >= len(lines):
            hook_from = src                                  # her own hook block, new words, her timing
        elif saved and saved in set(_drafts_now()):
            hook_from = saved
        else:
            hook_from = _hook_style_source(src, st.get("pack"), len(lines))
        if not hook_from:
            raise Refuse(f"Trial {tid}'s hook has {len(lines)} line(s) and I couldn't find a hook you styled in CapCut "
                         "with that many (text at the top of the frame in a draft's first second) to copy. Name a draft "
                         "with one (--hook-from \"<draft>\"), or give the trial a one-line hook. Nothing was made.")
        if hook_from != src:
            dur = float(st.get("dur") or 8.0)
    name = f"{draft_safety.base_of(src)} trial {tid}"           # named like the reel, without its version
    if name in set(_drafts_now()):
        name = draft_safety.next_version(name)               # a trial draft she may have opened is never replaced
    try:
        d = _load_draft(src)
        low = (_read(os.path.join(jd, "subject-zones.json"), {}).get("zones") or {}).get("below")
        try:
            import learned
            when = learned.get("hook.when_covered", "shorter")
        except Exception:
            when = "shorter"
        res = capcut_recut.make(src, name, capcut_recut.pieces_from_lines(d, spec), lines, hook_from, dur,
                                low_zone=low if (low or {}).get("usable") else None, when_covered=when)
    except capcut_recut.Refuse as e:
        raise Refuse(str(e))
    except draft_safety.CapCutOpen as e:
        raise Refuse(str(e))
    print(f"  re-cut from {src!r}: clips {spec}, {res['seconds']}s"
          + (f"; hook styled like {hook_from!r}, on at {res['hook_at']}s for {res['hook_dur']}s"
             + (" under your chin" if res.get("hook_spot") == "below" else "") + " (clear of your graphics)"
             if res.get("hook") and not res.get("note") else "")
          + (f"; {', '.join(res['bed'])} laid fresh under the whole trial (one continuous play)" if res.get("bed") else ""))
    if res.get("note"):
        print(f"  Trial {tid}: {res['note']}. Let me know if you'd like it moved.")
    return {"draft": res["draft"], "clips": spec, "seconds": res["seconds"],
            **({"hook_from": hook_from, "hook_at": res["hook_at"], "hook_dur": res["hook_dur"]} if res.get("hook") else {}),
            **({"bed": res["bed"]} if res.get("bed") else {})}


def _front_overlay(jd, name, pack):
    """Everything in the reel but its hook, rendered once (reel_render caches it by content, so every trial and
    every later run reuses it). The reel's own composition is put back to normal afterwards, whatever happens."""
    od = os.path.join(jd, f"hf-reel-type-{pack.lower()}")
    mov = os.path.join(jd, "layers", "front.mov")
    plan = os.path.join(jd, "caption-plan.json")
    if os.path.isfile(mov) and os.path.getmtime(mov) > os.path.getmtime(plan):
        return mov                                           # made for an earlier trial, and the reel hasn't changed
    os.makedirs(os.path.dirname(mov), exist_ok=True)
    env = {"JOB": name, "STYLE_PACK": pack}
    try:
        _run([sys.executable, os.path.join(HERE, "build-reel-type.py")], env=dict(env, LAYER="front"),
             what="Building your reel without its hook")
        _render(od, mov, "Rendering your reel without its hook (once, for every trial)")
    finally:
        try:
            _run([sys.executable, os.path.join(HERE, "build-reel-type.py")], env=dict(env, LAYER="all"),
                 what="Putting your reel's own composition back")
        except Refuse:
            print(f"  Your reel's own composition needs one rebuild before anything else uses it: "
                  f"JOB={name} STYLE_PACK={pack} LAYER=all python3 product/build-reel-type.py")
    return mov


def _link_or_copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst):
        os.remove(dst)
    try:
        os.link(src, dst)                                    # same disk: instant, no second copy of her footage
    except OSError:
        shutil.copy2(src, dst)


def _hook_plan(cp, t, pack):
    """The reel's caption plan with only its hook changed: the same keys the builder reads for the hook."""
    cp = json.loads(json.dumps(cp))
    halves = _halves(t["hook"])
    cp["hook"] = halves
    cp["hook_long"] = " ".join(halves)
    for k in ("hook_halves",):
        cp.pop(k, None)
    if len(halves) == 2:
        cp["hook_halves"] = halves
        cp["hook_emphasis"] = "first" if t["shape"] == "headline-subhead" else "second"
    if isinstance(cp.get("hook_by_pack"), dict):
        cp["hook_by_pack"].pop(pack, None)
    return cp


def _draw_hook_welldone(jd, t, pack):
    """Draw a trial hook with the reel's OWN builder (LAYER=hook) from a copy of its plan with only the hook changed,
    so it sits exactly where her hook did, around everything else on screen (a label above it, her measured zones).
    Her reel's folder is only read. Returns the trial hook's composition dir."""
    name = os.path.basename(jd)
    tj = os.path.join(jd, "trials", t["id"], name)              # named like the reel: the builder reads <name>.* files
    if os.path.isdir(tj):
        shutil.rmtree(tj)
    os.makedirs(os.path.join(tj, "outputs"))
    for f in ("subject-zones.json", "owns-screen.json", "head-framing.json", "face-frame.json", "face-anchors.json"):
        if os.path.isfile(os.path.join(jd, f)):
            shutil.copy2(os.path.join(jd, f), os.path.join(tj, f))
    if os.path.isdir(os.path.join(jd, "transcript")):
        shutil.copytree(os.path.join(jd, "transcript"), os.path.join(tj, "transcript"),
                        ignore=shutil.ignore_patterns("*.wav", "*.mp3", "*.mp4", "*.m4a"))
    for f in (f"{name}.transcript.json", f"{name}.mp4"):
        if os.path.isfile(os.path.join(jd, "outputs", f)):
            _link_or_copy(os.path.join(jd, "outputs", f), os.path.join(tj, "outputs", f))
    _write(os.path.join(tj, "caption-plan.json"), _hook_plan(_read(os.path.join(jd, "caption-plan.json"), {}), t, pack))
    _run([sys.executable, os.path.join(HERE, "build-reel-type.py")],
         env={"JOB": name, "JOB_DIR": tj, "STYLE_PACK": pack, "LAYER": "hook"}, what=f"Trial {t['id'].upper()}'s hook")
    return os.path.join(tj, f"hf-reel-type-{pack.lower()}")


def _make_welldone(jd, st, t, to):
    pack = st.get("pack")
    if not pack:
        raise Refuse("I couldn't tell which style pack this reel is in. Name it and I'll make the trials.")
    name = os.path.basename(jd)
    rest = _front_overlay(jd, name, pack)
    comp = _draw_hook_welldone(jd, t, pack)
    hook_mov = _render(comp, os.path.join(jd, "trials", t["id"], "hook.mov"), f"Trial {t['id'].upper()}'s hook")
    if to == "capcut":
        uv = shutil.which("uv") or "uv"
        out = _run([uv, "run", os.path.join(HERE, "capcut_handoff.py"), name, "--no-overlay", "--pack", pack,
                    "--punch", "--name", f"{name} trial {t['id'].upper()}", "--layer", f"front={rest}@0",
                    "--layer", f"trial-hook={hook_mov}@0"], what=f"Trial {t['id'].upper()}'s CapCut draft")
        draft = next((l.split("CapCut project ready:", 1)[1].strip() for l in out.splitlines() if "CapCut project ready:" in l), None)
        return {"draft": draft or f"{name} trial {t['id'].upper()}"}
    final = _out_mp4(jd, t["id"])
    baked = os.path.join(jd, "trials", t["id"], "baked.mp4")
    _run([sys.executable, os.path.join(HERE, "build-reel-mp4.py")],          # her zooms and sounds, as the reel had them
         env={"JOB": name, "STYLE_PACK": pack, "OVERLAY": rest, "OUT": baked}, what=f"Trial {t['id'].upper()}")
    _run([sys.executable, os.path.join(HERE, "burn_layers.py"), "--base", baked, "--layer",
          f"{hook_mov}@0", "-o", final], what=f"Trial {t['id'].upper()}'s hook")   # the builder times it on the reel's clock
    return {"file": os.path.relpath(final, ROOT).replace(os.sep, "/")}


def export(job, only=None, to=None):
    """Export trials that are prepared (after any tweaks she made in their editors), one at a time."""
    jd = job_dir(job)
    import trial_edits
    todo = [t for t in trials(job) if t.get("job") and (not only or t["id"] in only)]
    if not todo:
        raise Refuse("There are no prepared trial reels to export yet. Make them first.")
    out = []
    for t in todo:
        print(f"Trial {t['id'].upper()} ({t['job']})")
        try:
            res = trial_edits.export_one(jd, t["job"], route=to or "mp4", log=print)
        except trial_edits.Refuse as e:
            raise Refuse(str(e))
        _mark(jd, t["id"], made=time.strftime("%Y-%m-%d %H:%M:%S"), to=to or "mp4", **res)
        out.append(dict(t, **res))
        print(f"  ready: {res.get('file') or 'CapCut draft ' + repr(res.get('draft'))}")
    return out


def make(job, only=None, to=None, export=False):
    jd = job_dir(job)
    st = status(job)
    if not st["how"]:
        raise Refuse(st["why"].capitalize() + ".")
    todo = [t for t in trials(job) if not only or t["id"] in only]
    if not todo:
        raise Refuse("There are no trial hooks saved for this reel yet.")
    to = to or ("capcut" if st["how"] == "capcut" else "mp4")
    made = []
    unit = "clip" if st.get("recut") else "line"
    for t in todo:
        print(f"Trial {t['id'].upper()}: " + "; ".join(x for x in (
            f"opens on {unit} {t['open']}" if t.get("open") else "", f"{unit}s {', '.join(map(str, t['drop']))} out" if t.get("drop") else "",
            t.get("pack") or "", t.get("captions") or "", t["hook"]) if x))
        if st["how"] == "editor":                            # a real re-edit: its own copy of her reel, prepared, not rendered
            import trial_edits
            if t.get("open") is None and not t.get("drop"):
                raise Refuse(f"Trial {t['id'].upper()} has no different edit (only a new hook), so it would read as a repost. "
                             "Give it a line to open on or lines to leave out.")
            if not st.get("exported"):
                raise Refuse("Export this reel from the Finish tab first, then make the trials.")
            try:
                res = trial_edits.prepare_one(jd, t, log=print)
                if export:
                    res.update(trial_edits.export_one(jd, res["job"], route=to, log=print))
            except trial_edits.Refuse as e:
                raise Refuse(str(e))
        else:
            fn = _make_recut if st.get("recut") else {"capcut": _make_capcut, "well-done": _make_welldone}[st["how"]]
            res = fn(jd, st, t, to)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        _mark(jd, t["id"], **({"made": stamp, "to": to} if (res.get("file") or res.get("draft")) else {"prepared": stamp}), **res)
        made.append(dict(t, **res))
        if res.get("file") or res.get("draft"):
            print(f"  ready: {res.get('file') or 'CapCut draft ' + repr(res.get('draft'))}")
        else:
            print(f"  ready to watch and tweak: open {res['job']} (nothing rendered yet)")
    return made


# ─────────────────────────── CLI ───────────────────────────

def _opt(argv, flag):
    if flag in argv:
        i = argv.index(flag)
        return argv[i + 1] if i + 1 < len(argv) else None
    return None


def main(argv):
    if len(argv) < 3 or argv[1] in ("-h", "--help"):
        print(__doc__.split("CLI", 1)[1].rstrip())
        return 0 if len(argv) > 1 and argv[1] in ("-h", "--help") else 2
    cmd, job = argv[1], argv[2]
    try:
        if cmd in ("status", "lines") and (_opt(argv, "--draft") or _opt(argv, "--hook-from")):
            jd = job_dir(job)
            meta = _read(_trials_path(jd), {}) or {}
            for k, flag in (("draft", "--draft"), ("hook_from", "--hook-from")):
                v = _opt(argv, flag)
                if v:
                    if v not in set(_drafts_now()):
                        raise Refuse(f"There's no CapCut draft called {v!r} on this computer.")
                    meta[k] = v
            _write(_trials_path(jd), meta)
        if cmd == "status":
            print(json.dumps(status(job), indent=2, ensure_ascii=False))
        elif cmd == "write":
            src = argv[3] if len(argv) > 3 else None
            hooks = json.load(open(src, encoding="utf-8")) if src and src != "-" else json.load(sys.stdin)
            for t in write(job, hooks, draft=_opt(argv, "--draft"), hook_from=_opt(argv, "--hook-from")):
                print(f"{t['id'].upper()}  [{t['shape']}]  {t['hook']}" + (f"   ({t['angle']})" if t.get("angle") else ""))
        elif cmd == "lines":
            st = status(job)
            if st.get("recut"):
                print(f"Clips of your CapCut draft {st['draft']!r} (what \"open\" and \"drop\" name):")
                xs = recut_lines(job_dir(job), st)
            else:
                import trial_edits
                xs = trial_edits.segments(job_dir(job))
            for x in xs:
                print(f"{x['n']:>2}  ({x['dur']:.1f}s)  {x['text']}")
        elif cmd == "list":
            ts = trials(job)
            if not ts:
                print("No trial hooks saved for this reel yet.")
            for t in ts:
                where = t.get("file") or (f"CapCut draft {t['draft']!r}" if t.get("draft") else "not made yet")
                if t.get("job"):
                    where += f"  (its own reel: {t['job']})"
                print(f"{t['id'].upper()}  {t['hook']}  ->  {where}")
        elif cmd == "make":
            only = set((_opt(argv, "--only") or "").lower().replace(" ", "").split(",")) - {""}
            to = _opt(argv, "--to")
            if to not in (None, "mp4", "capcut"):
                raise Refuse("--to is mp4 or capcut.")
            make(job, only or None, to, export="--export" in argv)
        elif cmd == "export":
            only = set((_opt(argv, "--only") or "").lower().replace(" ", "").split(",")) - {""}
            to = _opt(argv, "--to")
            if to not in (None, "mp4", "capcut"):
                raise Refuse("--to is mp4 or capcut.")
            export(job, only or None, to)
        else:
            print(f"unknown command: {cmd}")
            return 2
    except Refuse as e:
        print(str(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
