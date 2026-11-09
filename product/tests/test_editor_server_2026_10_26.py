#!/usr/bin/env python3
"""Guards: four visual-editor problem reports from 2026-10-21..23, each fixed in the engine.

  look effect kept   an animation set from the chat is drawn AND kept on her line (`look-effect`), never left in the
                     Refine sandbox where her preview never sees it; one the look can't show is refused by name
  restitch path      `restitch <job> transcript/fixed-plan.json` finds a plan given relative to the reel's folder, and
                     a plan found nowhere (or unreadable) is a plain refusal, never a FileNotFoundError traceback
  open never silent  the page server starts before the preview copy; the copy's ffmpeg says how far it is as it goes
                     and is stopped (said plainly) only when nothing has moved for a while; output is line-buffered
  hidden words       words a look's page hides (a display:none timing note) are not words on screen, so her captions
                     don't step aside under it; a hidden note the page's script copies onto the screen still counts

Run: python3 -m pytest product/tests/test_editor_server_2026_10_26.py -q   (or python3 <this file>)
"""
import inspect, json, os, shutil, sys, tempfile

os.environ.setdefault("REE_EDITOR", "1")
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import visual_editor as ve  # noqa: E402


def _reel(words=()):
    """A throwaway reel folder with a kept-words transcript."""
    jd = tempfile.mkdtemp(prefix="ve-1026-")
    os.makedirs(os.path.join(jd, "outputs"))
    os.makedirs(os.path.join(jd, "review"))
    tw = [{"text": w, "start": 0.3 * i, "end": 0.3 * i + 0.25, "type": "word"} for i, w in enumerate(words)]
    json.dump({"words": tw}, open(os.path.join(jd, "outputs", os.path.basename(jd) + ".transcript.json"), "w", encoding="utf-8"))
    return jd


def _refuses(fn, *a, **k):
    try:
        fn(*a, **k)
    except ve.Refuse as e:
        return str(e)
    return None


# ── hidden words (2026-10-21) ────────────────────────────────────────────────────────────────────────────
LINE = "the launch was so fun"


def _says(page):
    jd = _reel(LINE.split())
    try:
        d = os.path.join(jd, "hf-graphics", "_looks", "add-w0", "mine", "hf-reel-type-butter")
        os.makedirs(d)
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(page)
        return ve._says_her_words(jd, {"dir": os.path.relpath(d, jd), "offset": 0.0, "dur": 2.0})
    finally:
        shutil.rmtree(jd, ignore_errors=True)


def _page(style="", body="", script=""):
    return (f"<!doctype html><html><head><title>launch fun</title><style>{style}</style></head><body>"
            f"<div id=\"root\">{body}</div><script>{script}</script></body></html>")


def test_hidden_timing_note_is_not_on_screen():
    timing = ('const kw=document.getElementById("note").textContent.toLowerCase().split(" ");'
              'const at=w=>Math.max(0,kw.indexOf(w))*0.3; tl.fromTo("#big",{autoAlpha:0},{autoAlpha:1},at("fun"));')
    by_rule = _page("#note{display:none;}", f'<span id="note">{LINE}</span><div id="big">Best week ever</div>', timing)
    inline = _page("", f'<span id="note" style="display: none">{LINE}</span><div id="big">Best week ever</div>', timing)
    unread = _page("", f'<span hidden>{LINE}</span><div id="big">Best week ever</div>')
    assert not _says(by_rule), "a display:none note read only for timing is not her words on screen (stylesheet rule)"
    assert not _says(inline), "a display:none note read only for timing is not her words on screen (inline style)"
    assert not _says(unread), "a hidden element nothing reads is not on screen"


def test_hidden_note_copied_onto_the_page_still_counts():
    count_up = _page("#note{display:none;}", f'<span id="note">{LINE}</span><span id="pre"></span>',
                     'const t=document.getElementById("note").textContent, m=t.match(/x/);'
                     'document.getElementById("pre").textContent=m?t.slice(0,1):t;')
    each_word = _page(".w{visibility:hidden}", f'<div id="words"><span id="src" hidden>{LINE}</span></div>',
                      'const all=document.getElementById("src").textContent.trim().split(/\\s+/);'
                      'const words=all.slice(0);\nwords.forEach((w, i) => { const d=document.createElement("div"); '
                      'd.className="w"; d.textContent = w; });')
    destructured = _page("#notes{display:none}", f'<span id="notes">{LINE}</span><div class="card"><span class="h"></span></div>',
                         'const items=document.getElementById("notes").textContent.split(/\\s+/).map(s=>s.split(":"));\n'
                         'document.querySelectorAll(".card").forEach((c,i)=>{\nconst [h,n]=items[i]||["",""];\n'
                         'c.querySelector(".h").textContent=h;\n});')
    helper = _page("", f'<span id="src" hidden>{LINE}</span><span id="l1"></span>',
                   'const [a] = document.getElementById("src").textContent.split(" / ").map(s => s.split(/\\s+/));\n'
                   'function put(host, list) { list.forEach((w, i) => { const s = document.createElement("span");\n'
                   's.textContent = w; host.appendChild(s); }); }\nput(document.getElementById("l1"), a);')
    letters = _page("", f'<div id="so"><span id="src" hidden>{LINE}</span></div>',
                    'const txt=document.getElementById("src").textContent.trim();\n'
                    '[...txt].forEach((ch,i)=>{const s=document.createElement("span");s.textContent=ch;});')
    shown = _page(".w{visibility:hidden}", f'<div class="w">{LINE}</div>', 'gsap.to(".w",{autoAlpha:1});')
    for name, page in (("count-up", count_up), ("word by word", each_word), ("card names", destructured),
                       ("helper function", helper), ("letter by letter", letters), ("visibility:hidden revealed", shown)):
        assert _says(page), f"{name}: her words the page draws still take the captions' place"


def test_shown_text_drops_code_and_title():
    t = ve._shown_text(_page("p{color:red}", "<p>Hello there</p>", 'el.textContent="launch";'))
    assert "Hello there" in t and "launch" not in t and "color" not in t


# ── restitch path (2026-10-21) ───────────────────────────────────────────────────────────────────────────
def test_restitch_plan_relative_to_the_reel(monkeypatch):
    jd, elsewhere = _reel(), tempfile.mkdtemp(prefix="ve-1026-cwd-")
    try:
        os.makedirs(os.path.join(jd, "transcript"))
        segs = [{"clip": "a.mov", "start": 1.0, "end": 2.0}]
        json.dump({"segments": segs}, open(os.path.join(jd, "transcript", "fixed-plan.json"), "w", encoding="utf-8"))
        got = {}
        monkeypatch.setattr(ve, "_phase_now", lambda jd_: None)
        monkeypatch.setattr(ve, "pin_wordless", lambda jd_, s: got.setdefault("segs", s))
        monkeypatch.setattr(ve, "_stitch", lambda *a, **k: None)
        monkeypatch.setattr(ve, "build_script", lambda job: None)
        monkeypatch.setattr(ve, "_keep_lock", lambda *a, **k: None)
        monkeypatch.setattr(ve.tempfile, "gettempdir", lambda: jd)       # the scratch plan lands in the throwaway reel
        monkeypatch.chdir(elsewhere)                                    # not the reel's folder: the path is relative to it
        ve.restitch(jd, plan="transcript/fixed-plan.json", log=lambda *a: None)
        assert got.get("segs") == segs, "a plan path relative to the reel's folder is found there"
        msg = _refuses(ve.restitch, jd, plan="transcript/no-such-plan.json", log=lambda *a: None)
        assert msg and "no plan file" in msg.lower(), f"a missing plan is a plain refusal, not a traceback: {msg}"
        open(os.path.join(jd, "transcript", "bad.json"), "w", encoding="utf-8").write("{not json")
        msg = _refuses(ve.restitch, jd, plan=os.path.join(jd, "transcript", "bad.json"), log=lambda *a: None)
        assert msg and "segments" in msg, f"an unreadable plan is a plain refusal: {msg}"
    finally:
        shutil.rmtree(jd, ignore_errors=True)
        shutil.rmtree(elsewhere, ignore_errors=True)


# ── look effect kept (2026-10-23) ────────────────────────────────────────────────────────────────
def _looks_reel():
    jd = _reel("ter liberdade".split())
    json.dump({"pack": "Butter", "layers": [{"name": "add-w5", "look": "phrase", "offset": 0.0, "dur": 2.0,
                                             "dir": "hf-graphics/_looks/add-w5/phrase/hf-reel-type-butter"}]},
              open(os.path.join(jd, "review", "looks.json"), "w", encoding="utf-8"))
    return jd


def test_refine_refuses_an_effect_the_look_cannot_show():
    import lookbook
    offered = {x["id"] for x in lookbook.effects_for("phrase", "Butter")}
    assert "kinetic-center-build" not in offered and "stagger-from-center" not in offered
    jd = _looks_reel()
    try:
        for fx in ("kinetic-center-build", "stagger-from-center"):
            msg = _refuses(ve.refine, jd, "add-w5", "phrase", effect=fx)
            assert msg and fx in msg and "It takes:" in msg, f"{fx}: refused by name, with what the look can take: {msg}"
            assert not os.path.isdir(os.path.join(jd, "hf-graphics", "_looks", "add-w5", "_refine")), "nothing drawn"
    finally:
        shutil.rmtree(jd, ignore_errors=True)


def test_look_effect_draws_and_keeps(monkeypatch):
    jd = _looks_reel()
    try:
        calls = []
        monkeypatch.setattr(ve, "refine", lambda job, layer, look, **k: calls.append(("refine", layer, look, k.get("effect")))
                            or {"effect": k.get("effect"), "effects": [{"id": "per-word-crossfade", "name": "Word by word"}]})
        monkeypatch.setattr(ve, "refine_apply", lambda job, layer, scope, name=None: calls.append(("keep", layer, scope))
                            or {"look": "phrase"})
        r = ve.look_effect(jd, "add-w5", "per-word-crossfade")
        assert calls == [("refine", "add-w5", "phrase", "per-word-crossfade"), ("keep", "add-w5", "moment")], calls
        assert r["effect"] == "per-word-crossfade"
        calls.clear()
        ve.look_effect(jd, "add-w5", "default")
        assert calls[0][3] is None, "default = the pack's own animation"
        msg = _refuses(ve.look_effect, jd, "add-w99", "rise")
        assert msg and "add-w5" in msg, f"an unknown look key names the reel's looks: {msg}"
    finally:
        shutil.rmtree(jd, ignore_errors=True)
    src = inspect.getsource(ve.main)
    assert '"look-effect"' in src and "look_effect(a.job" in src, "the chat has a command for it"


# ── open never silent (2026-10-21) ───────────────────────────────────────────────────────────────────────
def test_open_starts_the_page_server_before_the_preview_copy():
    src = inspect.getsource(ve.open_editor)
    assert src.index("ensure_server()") < src.index("prepare(job)"), "the page server starts first"
    top = open(ve.__file__, encoding="utf-8").read().split("ROOT = ", 1)[0]
    assert "line_buffering=True" in top, "progress lines reach Claude's pipe as they're printed"
    mp = inspect.getsource(ve.make_preview)
    assert "-progress" in mp and "-nostdin" in mp and "_watched_ffmpeg" in mp


def test_preview_encode_reports_progress_and_finishes():
    code = ("import sys,time\nfor i in range(1,9):\n    print(f'out_time_us={i*1000000}', flush=True)\n"
            "    time.sleep(0.15)\nprint('progress=end', flush=True)\n")
    said = []
    r = ve._watched_ffmpeg([sys.executable, "-c", code], 8.0, said.append, stall_s=5, tick_s=0.3)
    assert r.returncode == 0 and not r.stalled and r.done == 8.0, r
    assert any("preview copy:" in s and "of 0:08" in s for s in said), said


def test_preview_encode_that_stops_moving_is_stopped_and_said():
    code = "import time\nprint('out_time_us=2000000', flush=True)\ntime.sleep(60)\n"
    r = ve._watched_ffmpeg([sys.executable, "-c", code], 30.0, lambda *a: None, stall_s=1, tick_s=10)
    assert r.stalled and r.returncode != 0 and r.done == 2.0, r


def test_a_slow_encode_that_keeps_moving_is_never_stopped():
    code = ("import time\nfor i in range(1,13):\n    print(f'out_time_us={i*100000}', flush=True)\n    time.sleep(0.25)\n")
    r = ve._watched_ffmpeg([sys.executable, "-c", code], 2.0, lambda *a: None, stall_s=1, tick_s=10)
    assert not r.stalled and r.returncode == 0, r


class _Patch:
    """pytest's monkeypatch, as far as these tests use it, for a plain `python3 <this file>` run (no pytest needed)."""

    def __init__(self):
        self.undo = []

    def setattr(self, obj, name, value):
        self.undo.append(lambda old=getattr(obj, name): setattr(obj, name, old))
        setattr(obj, name, value)

    def chdir(self, path):
        self.undo.append(lambda old=os.getcwd(): os.chdir(old))
        os.chdir(path)

    def close(self):
        for f in reversed(self.undo):
            f()


def main():
    fails, tests = [], [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        mp = _Patch()
        try:
            fn(mp) if "monkeypatch" in inspect.signature(fn).parameters else fn()
        except Exception as e:                               # noqa: BLE001 (each failure is reported, then the rest run)
            fails.append(f"{name}: {type(e).__name__}: {e}")
        finally:
            mp.close()
    for f in fails:
        print("  FAIL ", f)
    print(f"test_editor_server_2026_10_26: {len(tests) - len(fails)} of {len(tests)} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
