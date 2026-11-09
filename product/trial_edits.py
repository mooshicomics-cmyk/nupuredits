#!/usr/bin/env python3
"""trial_edits.py — a trial reel that is a real re-edit: its own copy of her visual editor reel with a different cut.

Instagram reads the same footage with a new text card as the same reel posted again, so a trial of a talking-head reel
has to be a genuinely different edit. Each trial is its own reel folder, `projects/<job>-trial-<id>/`, copied from hers
and then changed on the axes its spec names:

  open      a later line of hers moved to the very front (a cold open): the first seconds she says are different
  drop      lines left out (a tighter cut, a different length)
  pack      another style pack (her looks redrawn in it, same words, same moments)
  captions  another caption style
  hook      new hook words (and shape), drawn in the reel's pack where her hook sits

Her looks follow her words through the new cut (the editor's own retime: a look on a moved line moves with it, a look on
a dropped line goes with it), so nothing is hand-placed. The copy is finished through the editor's own Finish
(`finish.run`): every check, the same sounds, an MP4 or a CapCut draft named after the trial. It is also a full reel she
can open in her editor ("open <job>-trial-b") to change anything before she posts it. Her reel is only ever read.

Traps this avoids (each one silently wrecks a copy):
  * the stitch reads its scratch plan before transcript/cuts.json, so the new plan is handed to `restitch` directly;
  * looks are retimed only AFTER the stitch has written outputs/<copy>.transcript.json (without it every added look
    would read as cut and be removed);
  * a line can be moved, never duplicated (the editor gives each word one place in the cut).

Used by `product/trial_reels.py make` for an editor reel. Stdlib + the engine's own modules.
"""
import contextlib, json, os, re, shutil, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MARK = "trial-of.json"                                       # review/trial-of.json: this folder is a trial copy, safe to remake

# never copied: renders, exports and the copy's own trials (Finish makes them again for the copy)
SKIP_TOP = {"outputs", "trials", "unused-takes", "raw", "hdr-originals", "layers", "renders"}
SKIP_ANY = {".reel_render", ".hyperframes", "__pycache__"}
# per-reel state that must not carry over: an export, a running job, requests and notes already handled on her reel
DROP_REVIEW = ("finish.json", "finish.stop", "finish-allow.json", "claude-working.json", "claude-watching.json",
               "trial-request.json", "kit-request.json", ".applying", ".write.lock", "looks-retimed.json",
               "last-problem.json", "base-cut.json", "phase.json")


class Refuse(Exception):
    """A plain-words reason this trial can't be made (what to do is in the words)."""


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


@contextlib.contextmanager
def _quiet(logfile):
    """The stitch's long working log goes to a file in the trial's folder, not the chat (said only if it fails)."""
    os.makedirs(os.path.dirname(logfile), exist_ok=True)
    sys.stdout.flush(); sys.stderr.flush()
    saved = os.dup(1), os.dup(2)
    with open(logfile, "w", encoding="utf-8") as f:
        os.dup2(f.fileno(), 1); os.dup2(f.fileno(), 2)
        try:
            yield
        finally:
            sys.stdout.flush(); sys.stderr.flush()
            os.dup2(saved[0], 1); os.dup2(saved[1], 2)
            os.close(saved[0]); os.close(saved[1])


def her_packs(jd):
    """The packs a trial may wear: this reel's own, the ones she has chosen on her own reels, the ones she saved a
    lookbook in, and the packs she made. A trial is a fast pass inside her brand, never a look she doesn't use."""
    import visual_editor as ve
    out = set()
    try:
        out.add(ve._swap_pack(jd, _read(os.path.join(jd, "review", "looks.json"), {}))[0])
    except Exception:
        pass
    try:
        import choices
        out |= {h.get("pack") for h in choices.history(limit=30) if h.get("pack")}
    except Exception:
        pass
    lb = os.path.join(ROOT, "_local", "lookbooks")
    if os.path.isdir(lb):
        out |= {f[:-5] for f in os.listdir(lb) if f.endswith(".json")}
    mine = (_read(os.path.join(ROOT, "_local", "style-packs.json"), {}) or {}).get("packs")
    if isinstance(mine, dict):
        out |= set(mine)
    elif isinstance(mine, list):
        out |= {p.get("name") for p in mine if isinstance(p, dict) and p.get("name")}
    return {p for p in out if p}


def caption_looks(pack):
    """The caption styles in that pack's lookbook (shipped and hers)."""
    import lookbook
    return [l["id"] for l in lookbook.looks(pack) if l.get("layer") == "captions"]


def check_brand(jd, spec):
    """Refuse a trial look that steps outside her brand (another pack she doesn't use, a caption style not in her lookbook)."""
    import visual_editor as ve
    packs = her_packs(jd)
    if spec.get("pack") and spec["pack"] not in packs:
        raise Refuse(f"{spec['pack']} isn't one of your looks, so a trial won't wear it. Your packs: "
                     f"{', '.join(sorted(packs))}.")
    pack = spec.get("pack") or ve._swap_pack(jd, _read(os.path.join(jd, "review", "looks.json"), {}))[0]
    if spec.get("captions") and spec["captions"] not in caption_looks(pack):
        raise Refuse(f"{spec['captions']} isn't a caption style in your {pack} lookbook. Yours: "
                     f"{', '.join(caption_looks(pack))}.")


def segments(jd):
    """Her cut as she approved it, in play order: [{"n", "text", "dur", "seg"}]. n is what a trial spec names."""
    segs = (_read(os.path.join(jd, "transcript", "cuts.json"), {}) or {}).get("segments") or []
    return [{"n": i + 1, "text": (s.get("transcript") or "").strip(), "dur": round(float(s["end"]) - float(s["start"]), 2),
             "seg": s} for i, s in enumerate(segs)]


def span(x):
    """A line, or a run of lines, as a list of line numbers: 7, "4-7", [4, 7]. A sentence usually spans several lines."""
    if x is None or x == "" or x == []:
        return []
    if isinstance(x, (list, tuple)):
        if len(x) == 2 and all(isinstance(v, int) for v in x) and x[1] >= x[0]:
            return list(range(int(x[0]), int(x[1]) + 1))
        return sorted({int(v) for v in x})
    m = re.match(r"^\s*(\d+)\s*(?:-\s*(\d+))?\s*$", str(x))
    if not m:
        raise Refuse(f"I couldn't read {x!r} as a line or a run of lines (like 4-7).")
    a, b = int(m.group(1)), int(m.group(2) or m.group(1))
    return list(range(a, b + 1)) if b >= a else []


def plan_segments(segs, open_n=None, drop=()):
    """The trial's cut: the opening line(s) first (moved, never repeated), the dropped lines out, the rest in her order."""
    opening = span(open_n)
    out_n = set()
    for d in (drop if isinstance(drop, (list, tuple)) else [drop]):
        out_n |= set(span(d))
    by_n = {s["n"]: s["seg"] for s in segs}
    missing = [n for n in opening + sorted(out_n) if n not in by_n]
    if missing:
        raise Refuse(f"There's no line {missing[0]} in this reel (it has {len(segs)}).")
    if set(opening) & out_n:
        raise Refuse("A line can't open the reel and be left out.")
    rest = [s["seg"] for s in segs if s["n"] not in out_n and s["n"] not in opening]
    out = [by_n[n] for n in opening] + rest
    if len(out) < 2:
        raise Refuse("That leaves less than two lines. Keep more of the reel.")
    return [dict(s) for s in out]


def copy_reel(src, dst, tid):
    """Her reel → its trial folder. Her footage is linked (never written); everything else is a real copy, so nothing
    done to the trial can reach her reel. A folder that is already this trial's copy is replaced; anything else is never
    touched."""
    if os.path.exists(dst):
        mark = _read(os.path.join(dst, "review", MARK), {})
        if mark.get("of") != os.path.basename(src):
            raise Refuse(f"There's already a folder called {os.path.basename(dst)} that isn't a trial of this reel, so "
                         "nothing was changed. Rename that folder or pick another trial.")
        def _writable(fn, path, _exc):                       # Windows: a read-only file blocks the delete; clear it, retry
            os.chmod(path, 0o666)
            fn(path)
        try:
            shutil.rmtree(dst, **({"onexc": _writable} if sys.version_info >= (3, 12) else {"onerror": _writable}))
        except OSError:
            raise Refuse(f"{os.path.basename(dst)} is open somewhere (its editor page, a video player, CapCut), so it "
                         "can't be remade right now. Close it and ask again. Nothing of yours changed.")

    def ignore(d, names):
        rel = os.path.relpath(d, src)
        skip = {n for n in names if n in SKIP_ANY}
        if rel == ".":
            skip |= {n for n in names if n in SKIP_TOP}
        if rel == "hf-graphics":
            skip.add("finish")
        if rel == "review":
            skip |= {n for n in names if n == "preview.mp4" or n == "strip"}
        return skip

    shutil.copytree(src, dst, ignore=ignore)
    raw = os.path.join(src, "raw")
    if os.path.isdir(raw):
        os.makedirs(os.path.join(dst, "raw"))
        for f in os.listdir(raw):
            a, b = os.path.join(raw, f), os.path.join(dst, "raw", f)
            if os.path.isfile(a):
                try:
                    os.link(a, b)                            # same disk: instant and no second copy of her footage
                except OSError:
                    shutil.copy2(a, b)
    os.makedirs(os.path.join(dst, "outputs"), exist_ok=True)
    rv = os.path.join(dst, "review")
    for f in DROP_REVIEW:
        p = os.path.join(rv, f)
        if os.path.exists(p):
            os.remove(p)
    _write(os.path.join(rv, "look-requests.json"), {"requests": []})   # her ideas were for her reel, already handled
    notes = os.path.join(dst, "transcript", "script-notes.json")
    if os.path.exists(notes):
        _write(notes, {"notes": []})
    acc = os.path.join(dst, "transcript", "accents.json")
    if os.path.exists(acc):
        d = _read(acc, {})
        if isinstance(d, dict) and "job" in d:
            d["job"] = os.path.basename(dst)
            _write(acc, d)
    _write(os.path.join(rv, MARK), {"of": os.path.basename(src), "id": tid, "at": time.strftime("%Y-%m-%d %H:%M:%S")})


def _win_key(wmap, name):
    """A layer's entry in hf-graphics/windows.json: keyed by its folder ("h01-hook/hf-reel-type-<pack>") or its name."""
    if not isinstance(wmap, dict):
        return None
    for k, v in wmap.items():
        if (k == name or k.split("/")[0] == name) and isinstance(v, list) and len(v) == 2:
            return k
    return None


def _shift_built(ve, jd, names, was, now, hook_name):
    """Looks the build made (fixed cut seconds, not keyed to words) move by how far their own words moved, in this copy's
    lists only. A look whose words were cut or split is taken off this trial. Returns (moved, off)."""
    frame = 1 / 30
    looks = _read(os.path.join(jd, "review", "looks.json"), {"layers": []})
    by = {l["name"]: l for l in looks.get("layers", [])}
    wpath = os.path.join(jd, "hf-graphics", "windows.json")
    win = _read(wpath, None)
    wmap = (win.get("windows", win) if isinstance(win, dict) else None)
    adds = ve._adds(jd)
    moved, off = [], []
    for name in names:
        if name == hook_name:
            continue                                         # the hook opens the trial wherever its first line is: redrawn below
        L = by.get(name) or {}
        o, d = float(L.get("offset") or 0), float(L.get("dur") or 0)
        ws = [w for w, a in was.items() if o - frame <= a <= o + d + frame]
        deltas = {round(now[w][0] - was[w], 2) for w in ws if w in now}
        if ws and all(w in now for w in ws) and len(deltas) == 1:
            dlt = deltas.pop()
            wkey = _win_key(wmap, name)
            if wkey:
                wmap[wkey] = [round(wmap[wkey][0] + dlt, 3), round(wmap[wkey][1] + dlt, 3)]
                moved.append(name)
                continue
            if name in adds:                                 # her refined look: same drawing, moved with its words
                e = adds[name]
                e["offset"] = round(float(e.get("offset") or 0) + dlt, 3)
                if e.get("span"):
                    e["span"] = [round(float(e["span"][0]) + dlt, 3), round(float(e["span"][1]) + dlt, 3)]
                moved.append(name)
                continue
        try:
            ve.swap(os.path.basename(jd), name, None if name.startswith(("add-", "cap-")) else "_off")
        except Exception:
            pass
        off.append(name)
    if isinstance(win, dict) and wmap is not None:
        if "windows" in win:
            win["windows"] = wmap
        _write(wpath, win)
    sw = _read(os.path.join(jd, "review", "swaps.json"), {})
    if isinstance(sw, dict) and moved:
        sw["adds"] = adds
        _write(os.path.join(jd, "review", "swaps.json"), sw)
    return moved, off


HOOK_MIN_S = 1.5   # the shortest stretch a hook reads in; under this it would only flash


HOOK_BAND = (250, 450)   # where a trial hook draws, top of the frame (y px on 1080x1920): a line or two of the hook job


def _band(jd, l):
    """(y0, y1) where a look draws on the frame, its motion included, or None when unknown (then it counts as
    everywhere). A caption style sits low; one of her designs says so in its design.json "band"; her Move shifts it."""
    import lookbook
    rec = _read(os.path.join(jd, l.get("dir") or "", "look.json"), {}) or {}
    look = rec.get("look") or l.get("look")
    band = None
    if look in lookbook.CAPTION_LOOKS and look != "takeover":
        band = (980, 1700)
    elif rec.get("pack") and look:
        b = (_read(os.path.join(lookbook.design_dir(rec["pack"], look), "design.json"), {}) or {}).get("band")
        if isinstance(b, list) and len(b) == 2:
            band = (float(b[0]), float(b[1]))
    if band is None:
        return None
    dy = float((l.get("nudge") or [0, 0])[1] or 0)
    return (band[0] + dy, band[1] + dy)


def _meets(band, other):
    return band is None or (band[0] < other[1] and other[0] < band[1])


def hook_window(busy, start, dur, total):
    """(start, dur) of the hook: the first stretch from `start` at least HOOK_MIN_S long with none of `busy`
    ([(t0, t1)] of the other looks) on screen, ending as the next one comes in. dur < HOOK_MIN_S = no room."""
    t = start
    for a0, b0 in sorted(busy):
        if b0 <= t:
            continue
        if a0 - t >= HOOK_MIN_S:
            break
        t = max(t, b0)
    nxt = min((a0 for a0, b0 in busy if a0 >= t), default=total)
    return round(t, 3), round(min(dur, nxt - t, total - t), 3)


def _hook(ve, jd, text, shape, dur_default=7.0, size=1.0):
    """The trial's hook: drawn in the reel's pack where her hook sits (on, even if she had it off), or added over the
    opening when her reel has none. It never shares the screen with a look on the opening line: when the moved line
    brings its own look (a takeover, a card), that look opens the trial and the hook comes in as it ends. Returns the
    layer it's on."""
    import lookbook
    job = os.path.basename(jd)
    try:                                                     # the trial's looks where they are NOW (moved with her words)
        looks = ve.looks_manifest(jd) or _read(os.path.join(jd, "review", "looks.json"), {"layers": []})
    except Exception:
        looks = _read(os.path.join(jd, "review", "looks.json"), {"layers": []})
    hook = next((l for l in looks.get("layers", []) if re.match(r"^h\d+-hook", l.get("name", ""))), None)
    pack = ve._swap_pack(jd, looks)[0]
    zones = _read(os.path.join(jd, "subject-zones.json"), None)
    look = shape or "eyebrow-headline"
    dur = float((hook or {}).get("dur") or dur_default)
    opening = [l for l in looks.get("layers", []) if not l.get("off") and not l.get("captions") and l is not hook
               and float(l.get("offset") or 0) < 0.5 and float(l.get("dur") or 0) < 30 and _meets(_band(jd, l), HOOK_BAND)]
    start = round(max((float(l["offset"]) + float(l["dur"]) for l in opening), default=0.0), 3)
    times = ve.word_cut_times(jd)
    total = max((b for a, b in times.values()), default=0.0)
    # never on top of another look (a card that comes in later, 2026-10-18 "make sure it's not colliding with that
    # card"): the hook takes the first stretch from `start` with no other look on screen, ending as the next one enters
    busy = sorted((float(l["offset"]), float(l["offset"]) + float(l["dur"])) for l in looks.get("layers", [])
                  if not l.get("off") and not l.get("captions") and l is not hook and l.get("dur") is not None
                  and _meets(_band(jd, l), HOOK_BAND))     # a look elsewhere on screen (beside her, low) can share it
    start, dur = hook_window(busy, start, dur, total)
    if dur < HOOK_MIN_S:
        raise Refuse("This trial has a look on screen almost the whole way through, so there's no clear stretch for a "
                     "hook that wouldn't sit on top of one. Make it without a hook, or take a look off in its editor.")
    if hook:
        key = hook["name"]
        if start > 0 or dur < float(hook.get("dur") or 0) - 1e-3:   # this copy's own list: the hook waits for the opening
                                                             # look and ends as the next look comes in
            wpath = os.path.join(jd, "hf-graphics", "windows.json")
            win = _read(wpath, None)
            wmap = win.get("windows", win) if isinstance(win, dict) else None
            wkey = _win_key(wmap, key)
            if wkey:
                wmap[wkey] = [start, round(start + dur, 3)]
                if "windows" in win:
                    win["windows"] = wmap
                _write(wpath, win)
                ve.looks_manifest(jd)
            else:
                key = None                                   # a hook with fixed timing we can't move: added instead, below
    if not hook or key is None:
        end = min(start + dur, total)   # (dur already ends before the next look comes in)
        first = min((w for w, (a, b) in times.items() if b > start + 0.02), key=lambda w: times[w][0], default=None)
        if first is None:
            raise Refuse("This trial's cut has no words to put a hook over.")
        if hook:
            ve.swap(job, hook["name"], "_off")
        key = ve._free_add_key(jd, first, look)              # keyed to the word it starts on, like any look she adds
        ve.place_look(job, key, start, end, look)
        e_ = ve._adds(jd).get(key) or {}
        over = float(e_.get("offset", start)) + float(e_.get("dur") or 0) - end   # a look holds a beat past its last
        if over > 0.02 and end - over - start >= HOOK_MIN_S:                     # word: pulled in, so the hook is gone
            ve.place_look(job, key, start, end - over, look)                      # before the next look comes in
        dur = float((ve._adds(jd).get(key) or {}).get("dur") or (end - start))
    rel = f"hf-graphics/_looks/{key}/{look}"
    try:
        lookbook.draw(look, os.path.join(jd, rel), text, dur, pack, zones, comp_id=f"{key}-{look}", size=size)
    except lookbook.Refuse as e:
        raise Refuse(str(e))
    ve.swap(job, key, look)
    return key


def prepare_one(src_jd, t, log=print):
    """One trial, made ready to watch and to tweak, with nothing rendered: its own copy of her reel, re-cut, her looks
    moved with her words, the new pack / captions / hook drawn. Seconds, not minutes. She can open it in her editor
    ("open <job>-trial-b") and change anything before it's exported. Returns {"job", "changed", "left_off"}."""
    import visual_editor as ve
    src = os.path.basename(src_jd)
    tid = t["id"]
    dst_name = f"{src}-trial-{tid}"
    dst = os.path.join(os.path.dirname(src_jd), dst_name)
    segs = segments(src_jd)
    plan = plan_segments(segs, t.get("open"), t.get("drop") or ())
    changed = []
    if t.get("open"):
        changed.append(f"opens on line {t['open']}")
    if t.get("drop"):
        n_out = len(set().union(*[set(span(d)) for d in t["drop"]]))
        changed.append(f"{n_out} line{'s' if n_out != 1 else ''} out")

    log(f"  Copying your reel for trial {tid.upper()}")
    copy_reel(src_jd, dst, tid)
    plan = [dict(s, keep_edges=True) for s in plan]          # her approved edges, exactly: only the order changes
    _write(os.path.join(dst, "review", "trial-plan.json"), {"segments": plan})
    log(f"  Making trial {tid.upper()}'s cut")
    scratch = os.path.join(tempfile.gettempdir(), "reels-editing-engine", dst_name)
    os.makedirs(scratch, exist_ok=True)
    try:
        with _quiet(os.path.join(dst, "review", "trial-stitch.log")), ve._making(dst, "lean"):
            # the stitch reads its scratch plan first, so it IS the trial's plan; no second cleaning pass (her cut was
            # set by ear on her page, exactly as Finish treats it)
            ve._atomic_json(os.path.join(scratch, "cuts.json"), {"segments": plan})
            ve._stitch(dst, lean=True, log=lambda *a: None, env={"TRIM_RESTARTS": "0", "SNAP": "0", "VERIFY_CUT": "0"})
        ve.build_script(dst_name)
    except ve.Refuse as e:
        raise Refuse(f"{e} (the stitch's own words: projects/{dst_name}/review/trial-stitch.log)")
    if not os.path.isfile(os.path.join(dst, "outputs", f"{dst_name}.transcript.json")):
        raise Refuse(f"Trial {tid.upper()}'s cut didn't finish, so its looks weren't moved. Nothing of yours changed.")
    was = {int(k): float(v) for k, v in ((_read(os.path.join(dst, "review", "looks-cut.json"), {}) or {}).get("times") or {}).items()}
    log(f"  Moving your looks onto trial {tid.upper()}'s cut")
    with _quiet(os.path.join(dst, "review", "trial-looks.log")):
        ve.retime_adds(dst_name)
        left, off = ve.looks_to_redo(dst), []
        if left:
            hook = next((n for n in left if re.match(r"^h\d+-hook", n)), None)
            _moved, off = _shift_built(ve, dst, left, was, ve.word_cut_times(dst), hook)
        ve.looks_current(dst_name)
        if t.get("pack"):
            ve.set_pack(dst_name, t["pack"])
        if t.get("captions"):
            ve.set_captions(dst_name, t["captions"])
        if t.get("hook"):
            _hook(ve, dst, t["hook"], t.get("shape"), size=float(t.get("hook_size") or 1.0))   # her size: "10% bigger" = 1.1
    if t.get("pack"):
        changed.append(f"{t['pack']} pack")
    if t.get("captions"):
        changed.append(f"{t['captions'].replace('-', ' ')} captions")
    if t.get("hook"):
        changed.append("a new hook")
    if off:
        log(f"  Left off trial {tid.upper()} (its words aren't in this cut): {', '.join(off)}")
    _write(os.path.join(dst, "review", MARK), dict(_read(os.path.join(dst, "review", MARK), {}), prepared=time.strftime("%Y-%m-%d %H:%M:%S"),
                                                     changed=changed))
    return {"job": dst_name, "changed": changed, "left_off": off}


_NUDGE = re.compile(r'<style id="ve-nudge">\s*#root\{\s*(?:transform:\s*)?translate:?\s*\(?\s*(-?[\d.]+)px[\s,]+(-?[\d.]+)px\s*\)?;?\s*\}\s*</style>')


def _same_picture(a, b):
    """Two drawings of a look are the same picture: every file byte for byte, except that the position nudge in
    index.html may be written in either of the two forms the editor has used (`translate:x y` / `transform:translate(x,y)`)."""
    import filecmp
    skip = {".reel_render", ".hyperframes", "renders", "node_modules"}

    def files(d):
        out = {}
        for root, dirs, fs in os.walk(d):
            dirs[:] = [x for x in dirs if x not in skip]
            for f in fs:
                if f != ".DS_Store":
                    out[os.path.relpath(os.path.join(root, f), d)] = os.path.join(root, f)
        return out
    fa, fb = files(a), files(b)
    if set(fa) != set(fb):
        return False
    for rel in fa:
        if rel == "index.html":
            ta = open(fa[rel], encoding="utf-8", errors="replace").read()
            tb = open(fb[rel], encoding="utf-8", errors="replace").read()
            norm = lambda t: _NUDGE.sub(lambda m: f"<nudge {float(m.group(1)):g} {float(m.group(2)):g}>", t)
            if norm(ta) != norm(tb):
                return False
        elif not filecmp.cmp(fa[rel], fb[rel], shallow=False):
            return False
    return True


def seed_renders(src_jd, dst_jd):
    """Every look the trial shares with her reel, picture for picture, reuses the render her reel's Finish already made.
    The trial's drawing becomes an exact copy of hers, so the renderer (which knows a look by its content) recognizes it.
    Only looks that really changed render again. Copies, never links: a later re-render in the trial must never write
    into her reel's files. Returns how many were reused."""
    import finish, reel_render
    used = 0
    out_dir = os.path.join(dst_jd, "hf-graphics", "finish")
    os.makedirs(out_dir, exist_ok=True)
    for name, comp, _start in finish.plan(dst_jd):
        rel = os.path.relpath(comp, dst_jd)
        src_comp = os.path.join(src_jd, rel)
        if not os.path.isdir(src_comp):
            continue
        st = reel_render._load(src_comp) or {}
        # every clean render she has of this look (one per export setting it was checked under), newest file first
        hits = {k: v for k, v in st.items() if v.get("ok") and os.path.isfile(v.get("out") or "")
                and os.path.basename(v["out"]).split(".")[0] == name}
        if not hits or not _same_picture(src_comp, comp):
            continue                                         # never rendered for her, or the trial's drawing differs
        if reel_render.comp_hash(src_comp, "probe") != reel_render.comp_hash(comp, "probe"):
            shutil.rmtree(comp)                              # take her drawing exactly (same picture, her bytes)
            shutil.copytree(src_comp, comp, ignore=shutil.ignore_patterns(".reel_render", ".hyperframes", "renders"))
        dst_st = reel_render._load(comp) or {}
        for key, prev in hits.items():
            new = os.path.join(out_dir, os.path.basename(prev["out"]))
            if not os.path.isfile(new):
                shutil.copy2(prev["out"], new)
            dst_st[key] = dict(prev, out=new)
        reel_render._save(comp, dst_st)
        used += 1
    return used


def _phone_size_base(ve, dst_jd, log=print):
    """The trial's cut at 1080 x 1920, the size Instagram plays and her looks are drawn at. Burning her looks onto a
    1728 x 3072 phone recording took most of a trial's time for no visible gain. Stamped so Finish uses it as is."""
    import subprocess
    name = os.path.basename(dst_jd)
    base = os.path.join(dst_jd, "outputs", f"{name}.mp4")
    if not os.path.isfile(base) or ve.base_is_stale(name):
        with _quiet(os.path.join(dst_jd, "review", "trial-cut.log")):
            ve.finish_cut(name, log=lambda *a: None, exact=True)
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", base], capture_output=True, text=True)
    try:
        w, h = (int(x) for x in probe.stdout.strip().split(",")[:2])
    except ValueError:
        return
    if w <= 1080:
        return
    import video_encoder
    tmp = base + ".1080.mp4"
    venc = video_encoder.pick_encoder(vbr="12M", crf=16, preset="veryfast")   # hardware where the machine has it
    cmd = lambda enc: ["ffmpeg", "-v", "error", "-y", "-i", base, "-vf", "scale=1080:-2:flags=lanczos", *enc,
                       "-c:a", "copy", "-movflags", "+faststart", tmp]
    r = subprocess.run(cmd(venc))
    if r.returncode != 0 and video_encoder.is_hardware(venc):   # a hardware encoder that won't start: software, every build has it
        r = subprocess.run(cmd(video_encoder.software_encoder(crf=16, preset="veryfast")))
    if r.returncode == 0 and os.path.isfile(tmp):
        ve._replace(tmp, base)                               # retried: Windows refuses a swap while the page streams it
        ve._stamp_base(dst_jd)                               # Finish sees a fresh cut and burns onto it as is
    elif os.path.exists(tmp):
        os.remove(tmp)                                       # the full-size cut stays; the export still works, just slower


def export_one(src_jd, dst_name, route="mp4", log=print):
    """Export a prepared trial (after any tweaks she made in its editor): her reel's renders reused wherever the trial
    shares a look, the cut at 1080 x 1920, then the editor's own Finish. Returns {"file"|"draft"}."""
    import visual_editor as ve, finish
    dst = os.path.join(os.path.dirname(src_jd), dst_name)
    if not os.path.isfile(os.path.join(dst, "review", MARK)):
        raise Refuse(f"{dst_name} isn't a trial of this reel.")
    reused = seed_renders(src_jd, dst)
    if reused:
        log(f"  Reusing {reused} of your reel's looks as they are")
    log(f"  Making {dst_name}'s cut at 1080 x 1920")
    _phone_size_base(ve, dst, log)
    log(f"  Finishing {dst_name} ({'CapCut' if route == 'capcut' else 'MP4'})")
    try:
        with _quiet(os.path.join(dst, "review", "trial-export.log")):
            res = finish.run(dst_name, route, log=lambda *a: None)
    except finish.Refuse as e:
        raise Refuse(f"{dst_name} didn't export: {e} It's saved as its own reel; open it with \"open {dst_name}\" to fix it there.")
    out = (res or {}).get("result") or {}
    return {k: out[k] for k in ("file", "draft") if out.get(k)}
