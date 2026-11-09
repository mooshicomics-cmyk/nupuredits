#!/usr/bin/env python3
"""Guards: one buyer's day on a new style for her reels (2026-10-25), six engine bugs, each fixed for everyone.

  second motion   a look that brings things in at separate moments has one Sound row per motion ("look:<layer>#2");
                  the page server refused every id with "#", so swapping or switching that sound never went through
  captions stay   a look marked "keeps_captions" (its design.json, or its lookbook entry), or "never hide my captions"
                  taught once (learned caption.never_hide), leaves her captions on under a card that shows the same
                  words; a caption style she picks for a line still replaces them; nothing set = the old rule
  gone drawing    a look whose drawing folder is gone isn't on her reel: never counted off its words (the page retimed
                  her looks on every load) and never moved by a retime
  plain remux     Apple's converter stopping on a long take's extra tracks is tried again on a copy with only the
                  picture and the first sound (ffmpeg's fallback is paler); the copy is always cleaned up; Mac only
  saved look      a look saved on a base keeps its tags and keeps_captions through find(), never its base's layer
  euro after      "300 €", "300€", "300 euros" are money: the count-up shows "300 €" with a non-breaking space

Run: python3 product/tests/test_buyer_reports_2026_10_26.py
"""
import http.client, json, os, shutil, subprocess, sys, tempfile, threading

os.environ.setdefault("REE_EDITOR", "1")
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import visual_editor as ve  # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  {str(detail)[:600]}"))
    if not cond:
        fails.append(name)


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(text)


# ── second motion: "#" in a Sound tab id ─────────────────────────────────────────────────────────────────────────
POPS = ('<div id="root" data-composition-id="pops"></div><script>\nwindow.__timelines=window.__timelines||{};\n'
        'const tl=gsap.timeline({paused:true});\n'
        '[0,1,2].forEach(i=>{ tl.fromTo("#p"+i,{autoAlpha:0,scale:0.15},{autoAlpha:1,scale:1,duration:0.5,'
        'ease:"back.out(1.8)"},1.0+i*0.6); });\nwindow.__timelines["pops"]=tl;\n</script>')


def second_motion(tmp):
    import visual_editor_server as srv
    import sound_plan as SP
    proj = os.path.join(tmp, "projects")
    jd = os.path.join(proj, "pops-reel")
    _write(os.path.join(jd, "hf-graphics", "_looks", "add-w0", "my-pops", "index.html"), POPS)
    _write(os.path.join(jd, "review", "looks.json"), json.dumps({"version": 1, "layers": [
        {"name": "add-w0", "dir": "hf-graphics/_looks/add-w0/my-pops", "offset": 0.0, "dur": 4.0, "look": "my-pops",
         "look_name": "Three pops", "captions": False}]}))
    cue_rx, layer_rx = getattr(srv, "SOUND_CUE_ID", None), getattr(srv, "SOUND_LAYER_ID", None)
    check("ids: a look's second motion is a Sound id the server takes", bool(cue_rx and cue_rx.match("look:add-w0#2")))
    check("ids: and the look it sits on, for a sound added on it", bool(layer_rx and layer_rx.match("add-w0#2")))
    check("ids: anything else is still refused", bool(cue_rx and layer_rx) and not cue_rx.match("look:add-w0/../x y")
          and not layer_rx.match("../add-w0#2"))

    saved = (srv.PROJECTS, srv.ve.ROOT, SP.job_dir, SP.LOCAL, SP.LEVELS, SP.PREVIEW_DIR)
    srv.PROJECTS, srv.ve.ROOT = proj, tmp
    SP.job_dir = lambda job: os.path.join(proj, job) if not os.path.isabs(str(job)) else job
    SP.LOCAL = os.path.join(tmp, "_local")
    SP.LEVELS = os.path.join(SP.LOCAL, "sound-levels.json")
    SP.PREVIEW_DIR = os.path.join(SP.LOCAL, "sound-preview")
    httpd = srv.http.server.ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def post(path, body):
        b = json.dumps(body)
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
        c.request("POST", path, body=b, headers={"Host": f"127.0.0.1:{port}", "Origin": f"http://127.0.0.1:{port}",
                                                 "Content-Type": "application/json", "Content-Length": str(len(b))})
        r = c.getresponse()
        d = r.read()
        c.close()
        try:
            return r.status, json.loads(d) if d else {}
        except ValueError:
            return r.status, {"raw": d[:300]}

    try:
        rows = {r["id"]: r for r in SP.read(jd)["cues"] if r.get("moment")}
        check("sound plan: the look's three pops are three rows, the 2nd and 3rd keyed with #",
              sorted(rows) == ["look:add-w0", "look:add-w0#2", "look:add-w0#3"], sorted(rows))
        st, j = post("/sound-swap?job=pops-reel", {"cue": "look:add-w0#2", "choice": "none"})
        row = next((r for r in (j.get("cues") or []) if r.get("id") == "look:add-w0#2"), {})
        check("swap: 'No sound here' on a look's second motion goes through", st == 200 and row.get("none") is True, (st, j.get("error"), row))
        other = next((r for r in (j.get("cues") or []) if r.get("id") == "look:add-w0#3"), {})
        check("swap: and lands on that motion only (the third is untouched)", not other.get("none"), other)
        st, j = post("/sound-nudge?job=pops-reel", {"cue": "look:add-w0#3", "delta": 0.1})
        check("nudge: a look's third motion reaches the sound plan, which answers in its own words (it has no sound yet)",
              st == 409 and "no sound here" in str(j.get("error")), (st, j))
        stored = json.load(open(SP.sound_json(jd), encoding="utf-8"))
        a = next((x for x in stored.get("added", []) if x.get("id") == "look:add-w0#2"), {})
        check("swap: saved on the motion it was made on (its anchor is the look's second motion)",
              a.get("none") is True and (a.get("anchor") or {}).get("layer") == "add-w0#2", stored)
    finally:
        httpd.shutdown()
        srv.PROJECTS, srv.ve.ROOT, SP.job_dir, SP.LOCAL, SP.LEVELS, SP.PREVIEW_DIR = saved


# ── captions stay ────────────────────────────────────────────────────────────────────────────────────────────────
LINE = "my plan is the whole floor of the house"


def _comp(name, dur, body=""):
    return ('<!doctype html><html><head></head><body>'
            f'<div id="root" data-composition-id="{name}" data-start="0" data-duration="{dur}" data-width="1080" '
            f'data-height="1920">{body}</div></body></html>')


def captions_stay(tmp):
    import learned, lookbook
    jd = os.path.join(tmp, "projects", "plan-reel")
    words = LINE.split()
    tw = [{"text": w, "start": 10.0 + 0.3 * i, "end": 10.25 + 0.3 * i, "type": "word"} for i, w in enumerate(words)]
    _write(os.path.join(jd, "outputs", "plan-reel.transcript.json"), json.dumps({"words": tw}))
    _write(os.path.join(jd, "hf-captions", "index.html"), _comp("hf-captions", 60))
    card = os.path.join(jd, "hf-graphics", "c01-card")
    _write(os.path.join(card, "index.html"), _comp("c01-card", 3, f"<div class='card'>{LINE}</div>"))
    _write(os.path.join(card, "look.json"), json.dumps({"pack": "Test Pack", "look": "my-floor-card"}))
    _write(os.path.join(jd, "hf-graphics", "windows.json"), json.dumps({"c01-card": [10.0, 3.0]}))
    design = os.path.join(tmp, "designs", "my-floor-card")
    _write(os.path.join(design, "design.json"), json.dumps({"name": "Floor card"}))

    def skips():
        shutil.rmtree(os.path.join(jd, "review"), ignore_errors=True)
        for p in (os.path.join(jd, "hf-graphics", "_looks"),):
            shutil.rmtree(p, ignore_errors=True)
        os.makedirs(os.path.join(jd, "review"), exist_ok=True)
        by = {l["name"]: l for l in ve.looks_manifest(jd)["layers"]}
        return [list(x) for x in (by.get("hf-captions") or {}).get("skips", [])]

    real = (lookbook.design_dir, lookbook.find, learned.STORE)
    lookbook.design_dir = lambda pack, look: design
    book = {"keeps_captions": False}
    lookbook.find = lambda look, pack=None: dict({"id": look, "layer": "design", "design": True}, **(
        {"keeps_captions": True} if book["keeps_captions"] else {}))
    learned.STORE = os.path.join(tmp, "_local", "learned.json")
    try:
        check("default: a card that shows her words still takes the captions' place (nothing changed for anyone else)",
              [10.0, 13.0] in skips(), skips())
        _write(os.path.join(design, "design.json"), json.dumps({"name": "Floor card", "keeps_captions": True}))
        check("design.json keeps_captions: her captions stay on under it", skips() == [], skips())
        _write(os.path.join(design, "design.json"), json.dumps({"name": "Floor card"}))
        book["keeps_captions"] = True
        check("lookbook keeps_captions: her captions stay on under it", skips() == [], skips())
        book["keeps_captions"] = False
        _write(learned.STORE, json.dumps({"preferences": [
            {"id": "t1", "field": "caption.never_hide", "value": True, "scope": {}, "note": "", "from_job": "", "date": "2026-10-26"}]}))
        check("learned: caption.never_hide is a preference a buyer can teach", "caption.never_hide" in learned.FIELDS)
        check("learned caption.never_hide: her captions stay on under a card with her words, on every reel", skips() == [], skips())
        # a caption style she picks for a line still replaces them (the words never show twice)
        k = os.path.join(jd, "hf-graphics", "k01-karaoke")
        _write(os.path.join(k, "index.html"), _comp("k01-karaoke", 2.5))
        _write(os.path.join(jd, "hf-graphics", "windows.json"), json.dumps({"c01-card": [10.0, 3.0], "k01-karaoke": [30.5, 2.5]}))
        s = skips()
        check("learned caption.never_hide: a karaoke line still swaps her captions for its own", s == [[30.5, 33.0]], s)
    finally:
        lookbook.design_dir, lookbook.find, learned.STORE = real


# ── gone drawing ─────────────────────────────────────────────────────────────────────────────────────────────────
def gone_drawing(tmp):
    jd = os.path.join(tmp, "projects", "gone-reel")
    os.makedirs(os.path.join(jd, "review"), exist_ok=True)
    json.dump({"layers": []}, open(os.path.join(jd, "review", "looks.json"), "w", encoding="utf-8"))
    json.dump({"cut_id": "c2", "order": [], "words": []}, open(os.path.join(jd, "review", "script.json"), "w", encoding="utf-8"))
    here = "hf-graphics/_looks/add-w5/hook/hf-reel-type-test"
    os.makedirs(os.path.join(jd, here), exist_ok=True)
    adds = {"add-w5": {"look": "hook", "dir": here, "offset": 2.0, "dur": 2.0, "span": [2.0, 4.0], "words": [5, 6]},
            "add-w9": {"look": "hook", "dir": "hf-graphics/_looks/add-w9/hook/hf-reel-type-test", "offset": 6.0,
                       "dur": 2.0, "span": [6.0, 8.0], "words": [9, 10]}}
    times = {5: (3.0, 3.3), 6: (3.4, 3.7), 9: (7.0, 7.3), 10: (7.4, 7.7)}   # her cut moved every word 1 s later
    calls = []
    real = (ve.job_dir, ve.word_cut_times, ve._adds, ve.redraw_captions, ve.looks_manifest, ve.place_look)
    ve.job_dir = lambda job: jd
    ve.word_cut_times = lambda _jd: times
    ve._adds = lambda _jd: {k: dict(v) for k, v in adds.items()}
    ve.redraw_captions = lambda job: {}
    ve.looks_manifest = lambda _jd: None
    ve.place_look = lambda job, key, s0, e0, look, **k: calls.append(key)
    try:
        d = ve.drifted_adds(jd)
        check("drift: a look whose drawing is gone is never counted off its words (only the one on her reel is)",
              d == ["add-w5"], d)
        ve.retime_adds("x")
        check("retime: a look whose drawing is gone is never moved (the one on her reel follows its words)",
              calls == ["add-w5"], calls)
    finally:
        ve.job_dir, ve.word_cut_times, ve._adds, ve.redraw_captions, ve.looks_manifest, ve.place_look = real


# ── plain remux before ffmpeg ────────────────────────────────────────────────────────────────────────────────────
FAKE_AVCONVERT = r'''#!/usr/bin/env python3
"""Stands in for Apple's avconvert: stops on a file with more than two streams (a long take's extra tracks)."""
import json, subprocess, sys
a = sys.argv
src, dst = a[a.index("--source") + 1], a[a.index("--output") + 1]
open(LOG, "a", encoding="utf-8").write(src + "\n")
n = len(json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=index", "-of", "json", src],
                                  capture_output=True, text=True).stdout or "{}").get("streams", []))
if n > 2 or FAIL_ALL:
    sys.stderr.write("The operation could not be completed\n"); sys.exit(1)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-c", "copy", dst], check=True)
'''


def plain_remux(tmp):
    import importlib.util
    spec = importlib.util.spec_from_file_location("hdr_under_test", os.path.join(os.path.dirname(HERE), "hdr.py"))
    hdr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hdr)
    src_hdr = open(os.path.join(os.path.dirname(HERE), "hdr.py"), encoding="utf-8").read()
    check("Mac only: Apple's converter is looked for on a Mac alone, so a PC never runs the retry",
          'shutil.which("avconvert") if sys.platform == "darwin" else None' in src_hdr)
    if os.name == "nt" or not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("  (plain remux: the converter run is skipped here: needs ffmpeg, ffprobe and a Unix shell)")
        return
    clip = os.path.join(tmp, "long-take.MOV")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=108x192:rate=30:duration=1",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-f", "lavfi", "-i", "sine=frequency=880:duration=1",
                    "-map", "0:v", "-map", "1:a", "-map", "2:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", clip], check=True)
    log = os.path.join(tmp, "avconvert.log")
    temps = os.path.join(tmp, "tmp")
    os.makedirs(temps)
    real = (hdr.apple_converter, tempfile.tempdir)
    tempfile.tempdir = temps
    try:
        for fail_all in (False, True):
            fake = os.path.join(tmp, f"avconvert-{int(fail_all)}")
            _write(fake, FAKE_AVCONVERT.replace("LOG", repr(log)).replace("FAIL_ALL", repr(fail_all)))
            os.chmod(fake, 0o755)
            hdr.apple_converter = lambda fake=fake: fake
            open(log, "w", encoding="utf-8").close()
            dst = os.path.join(tmp, f"out-{int(fail_all)}.mp4")
            how = hdr.to_sdr(clip, dst)
            tried = open(log, encoding="utf-8").read().split()
            if not fail_all:
                check("remux: Apple's converter stopping on the long take is tried again on a plain copy, and wins",
                      how == "apple" and len(tried) == 2 and tried[0] == clip and os.path.exists(dst), (how, tried))
            else:
                check("remux: when the plain copy fails too, ffmpeg still makes the copy", how == "ffmpeg" and os.path.exists(dst), how)
            check(f"remux: the temp copy is cleaned up ({'both fail' if fail_all else 'Apple wins'})", os.listdir(temps) == [], os.listdir(temps))
    finally:
        hdr.apple_converter, tempfile.tempdir = real


# ── saved look and the euro ──────────────────────────────────────────────────────────────────────────────────────
def saved_look(tmp):
    import lookbook
    pack = "Test Pack"
    real = lookbook.ROOT
    lookbook.ROOT = tmp
    try:
        _write(os.path.join(tmp, "_local", "lookbooks", f"{pack}.json"), json.dumps({"looks": [
            {"id": "my-plan-card", "name": "Plan card", "base": "breakaway", "plan": {}, "tags": "[mini]",
             "keeps_captions": True, "layer": "captions", "kind": "Captions"}]}))
        l = lookbook.find("my-plan-card", pack)
        check("saved look: keeps its tags", l.get("tags") == "[mini]", l)
        check("saved look: keeps keeps_captions (the engine reads it)", l.get("keeps_captions") is True, l)
        check("saved look: never takes a layer or kind of its own (its base's stay)",
              l.get("layer") == "breakaway" and l.get("kind") == "Full screen", l)
    finally:
        lookbook.ROOT = real


def euro_after():
    import lookbook
    nb = " €"
    for said in ("ça m'a coûté 300 €", "300€ de plus", "300 euros", "300 Euros par mois"):
        check(f"euro after: {said!r} is 300 with the euro after it", lookbook.number_in(said) == ("", 300, nb), lookbook.number_in(said))
    check("euro after: 1,250 € keeps its thousands", lookbook.number_in("1,250 €") == ("", 1250, nb), lookbook.number_in("1,250 €"))
    check("euro after: €300 (in front) is unchanged", lookbook.number_in("€300") == ("€", 300, ""))
    check("euro after: $1,250 and 40% are unchanged", lookbook.number_in("$1,250") == ("$", 1250, "")
          and lookbook.number_in("40%") == ("", 40, "%"))
    check("euro after: 'European' is not a euro", lookbook.number_in("300 European moms") == ("", 300, ""),
          lookbook.number_in("300 European moms"))
    p = lookbook.plan_for(lookbook.find("counter"), "it cost 300 €", 3.0, [])
    el = p["elements"][0]
    check("count-up: counts to 300 and shows the euro after it, French style", el["to"] == 300 and el["prefix"] == ""
          and el["suffix"] == nb, el)
    v = lookbook._fill_values("300 euros par mois", {"slots": ["number", "label"]})
    check("design count-up: the number reads '300 €' and the label keeps the rest", v["number"] == "300" + nb
          and v["label"] == "par mois", v)


def main():
    tmp = tempfile.mkdtemp(prefix="buyer-1026-")
    try:
        for name, fn in (("second motion", second_motion), ("captions stay", captions_stay), ("gone drawing", gone_drawing),
                         ("plain remux", plain_remux), ("saved look", saved_look)):
            print(name)
            try:
                fn(tmp)
            except Exception as e:                           # one part breaking never hides the others' results
                check(f"{name}: ran to the end", False, repr(e))
        print("euro after")
        euro_after()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print(f"test_buyer_reports_2026_10_26: {len(fails)} of {total} checks FAILED")
        return 1
    print(f"test_buyer_reports_2026_10_26: all {total} checks passed")
    return 0


def test_buyer_reports_2026_10_26():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
