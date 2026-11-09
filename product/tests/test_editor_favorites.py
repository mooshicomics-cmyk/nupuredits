#!/usr/bin/env python3
"""Guards: the visual editor's My favorites filter shows the effects she hearted in her Effects Library.

  hearts       a heart saved by the library's own server (favorites/effects.json) reaches the editor, by the name
               she saw it under in the library; an unreadable or missing file is an empty list, never an error
  looks        a heart that IS one of the page's looks marks that look's tile (a saved look built on it too); every
               other heart stays in the list, for Claude
  menus        Swap, Add a look and the Lookbook all carry her hearts, read fresh on every open
  page         the chip is one tap: only her hearted tiles and her other hearts, each one tap from Claude on a line;
               no hearts yet says so in one plain line and opens the library; All brings everything back
               (in a headless browser, when HyperFrames' Chrome is installed; skipped with a line otherwise)

Run: python3 product/tests/test_editor_favorites.py
"""
import importlib.util, json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
ROOT = os.path.dirname(PRODUCT)
sys.path.insert(0, PRODUCT)
sys.path.insert(0, HERE)
os.environ.setdefault("REE_EDITOR", "1")
os.environ.setdefault("REE_EDITOR_ERRORS_LOG", os.devnull)
import favorites, lookbook, visual_editor as ve  # noqa: E402

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    print(("  ok    " if cond else "  FAIL  ") + name + ("" if cond else f"  ({detail})"))
    if not cond:
        fails.append(name)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


library = open(os.path.join(PRODUCT, "effects-library.html"), encoding="utf-8").read()
m = re.search(r"var CATALOG=(.*?);/\* CATALOG:END \*/", library, re.S)
piece = json.loads(m.group(1))["items"][0] if m else ["", ""]

# ── hearts: written by the library's server, read by the editor (a throwaway engine folder, never hers) ──
tmp = tempfile.mkdtemp(prefix="ve-favs-")
real_root = favorites.ROOT
try:
    favorites.ROOT = tmp
    srv = load(os.path.join(ROOT, "scripts", "library-server.py"), "library_server")
    srv.FAVS = os.path.join(tmp, "favorites", "effects.json")
    check("hearts: no favorites file yet is an empty list", ve.hearts() == [])
    srv.write_favorites(["word-by-word", piece[0], "typewriter", "karaoke"])
    h = {x["name"]: x for x in ve.hearts()}
    check("hearts: every heart the library saved reaches the editor", set(h) == {"word-by-word", piece[0], "typewriter", "karaoke"}, sorted(h))
    check("hearts: a catalog piece shows by its library title", h.get(piece[0], {}).get("title") == piece[1], h.get(piece[0]))
    check("hearts: an engine effect reads as words", h.get("typewriter", {}).get("title") == "Typewriter", h.get("typewriter"))
    check("hearts: the library's word-by-word is the page's single-word look", h.get("word-by-word", {}).get("look") == "single-word")
    check("hearts: an effect the page can't draw has no look (it goes to Claude)", h.get(piece[0], {}).get("look") is None)
    open(srv.FAVS, "w", encoding="utf-8").write("{ not json")
    check("hearts: an unreadable favorites file is an empty list, never an error", ve.hearts() == [])
    check("hearts: an unreadable favorites file is left as it was", open(srv.FAVS, encoding="utf-8").read() == "{ not json")
finally:
    favorites.ROOT = real_root
    shutil.rmtree(tmp, ignore_errors=True)

look_ids = {l["id"] for l in lookbook.LOOKS}
check("looks: every library name the page maps is one of its looks", set(ve.HEART_LOOKS.values()) <= look_ids,
      sorted(set(ve.HEART_LOOKS.values()) - look_ids))
check("looks: every mapped library name is one of the library's own effects", all(f'"{n}"' in library for n in ve.HEART_LOOKS),
      [n for n in ve.HEART_LOOKS if f'"{n}"' not in library])

real_hearts = favorites.hearted_effects
try:
    favorites.hearted_effects = lambda: ["karaoke", "stat-countup"]
    menu = ve.with_hearts({"looks": [{"id": "karaoke", "base": "karaoke"}, {"id": "my-karaoke", "base": "karaoke"},
                                     {"id": "hook", "base": "hook"}, {"id": "counter", "base": "counter"}]})
    favs = [t["id"] for t in menu["looks"] if t.get("fav")]
    check("looks: a hearted look's tile is marked, and her saved look built on it", favs == ["karaoke", "my-karaoke", "counter"], favs)
    check("looks: the menu carries the whole list of hearts", [x["name"] for x in menu["hearts"]] == ["karaoke", "stat-countup"])
    favorites.hearted_effects = lambda: []
    menu = ve.with_hearts({"looks": [{"id": "karaoke"}]})
    check("looks: no hearts, nothing marked, an empty list", menu["hearts"] == [] and not menu["looks"][0].get("fav"))
finally:
    favorites.hearted_effects = real_hearts

server = open(os.path.join(PRODUCT, "visual_editor_server.py"), encoding="utf-8").read()
for what in ("swap_menu", "add_menu", "lookbook_view"):
    check(f"menus: {what} carries her hearts", f"ve.with_hearts(ve.{what}(" in server)
dc = open(os.path.join(PRODUCT, "visual_editor.py"), encoding="utf-8").read()
check("menus: each drawn tile says which look it's built on", 'item["base"] = base' in dc)

editor = open(os.path.join(PRODUCT, "visual-editor", "editor.html"), encoding="utf-8").read()
check("page: Swap and Add a look pass her hearts, with Ask Claude", "groupTiles($(\"swGrid\"), d.looks, mk, { hearts: d.hearts, ask:" in editor)
check("page: the Lookbook passes her hearts", "}, { hearts: d.hearts });" in editor)
check("page: an Ask Claude goes to her task queue for that line", 'post("/look-request", { w: first, start: sp.a, end: sp.z' in editor)

# ── the page itself: groupTiles in a real (headless) browser ──
a, b = editor.find("const FAV_VIEW"), editor.find("// one of her hearted effects the page can't draw itself")
src = editor[a:b]
check("page: the filter's code is where this test reads it", a > 0 and b > a and "function groupTiles" in src)

FLOW = r"""
const { createRequire } = require("module");
const puppeteer = createRequire(process.env.PUP + "/")(process.env.PUP);
(async () => {
  const browser = await puppeteer.launch({ executablePath: process.env.CHROME, headless: "shell", args: ["--no-sandbox"] });
  const out = {};
  try {
    const page = await browser.newPage();
    const errs = []; page.on("pageerror", e => errs.push(String(e.message || e)));
    await page.setContent(`<div class="sheet"><div class="sw-grid" id="g"></div></div><div class="sheet"><div class="sw-grid" id="g2"></div></div>`);
    await page.evaluate(`(() => { const m = {}; Object.defineProperty(window, "localStorage", { configurable: true, value: {
      getItem: k => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); }, removeItem: k => { delete m[k]; } } }); })();`);
    await page.evaluate(process.env.SRC + `
      window.esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
      window.icon = id => "";
      window.posted = []; window.post = async (p, b) => { posted.push([p, b]); return { ok: true, j: {} }; };
      window.toastAt = () => {};
      window.asked = [];
      window.groupTiles = groupTiles;`);
    out.run = await page.evaluate(() => {
      try { localStorage.removeItem("ree-editor-favs"); } catch (e) {}
      const mk = t => { const el = document.createElement("button"); el.className = "sw-tile"; el.dataset.id = t.id; el.innerHTML = '<span class="sw-stage"></span>'; return el; };
      const g = document.getElementById("g"), orig = mk({ id: "_original" }); g.append(orig);
      const looks = [{ id: "karaoke", kind: "Captions", fav: true, base: "karaoke" }, { id: "phrase", kind: "Captions" }, { id: "hook", kind: "Hook" }];
      const hearts = [{ name: "karaoke", title: "Karaoke", look: "karaoke" }, { name: "x-slam", title: "Kinetic Slam", look: null }, { name: "typewriter", title: "Typewriter", look: null }];
      groupTiles(g, looks, mk, { hearts, ask: (x, row) => asked.push(x.name) });
      const bar = g.previousElementSibling, chip = bar.querySelector('[data-g="_fav"]');
      const vis = () => [...g.children].filter(e => !e.hidden && e.className !== "sw-kind").map(e => e.dataset.id || e.className);
      const r = { chip: !!chip && chip.textContent.includes("My favorites") && chip.textContent.includes("3"),
                  heart: !!g.querySelector('[data-id="karaoke"] .sw-heart') && !g.querySelector('[data-id="phrase"] .sw-heart'),
                  before: vis() };
      chip.click();
      r.fav = vis(); r.rows = [...g.querySelectorAll(".sw-fav-row")].map(e => e.querySelector(".t").textContent);
      r.on = chip.classList.contains("on");
      g.querySelector(".sw-fav-row").click(); r.asked = asked.slice();
      r.remembered = localStorage.getItem("ree-editor-favs") === "1";
      bar.querySelector('[data-g="All"]').click(); r.all = vis();
      chip.click();                                  // reopen in favorites, then the next sheet opens on it by itself
      const g2 = document.getElementById("g2");
      groupTiles(g2, looks, mk, { hearts });
      r.lookbook = [...g2.children].filter(e => !e.hidden && e.className !== "sw-kind").map(e => e.dataset.id || e.className);
      r.lookbookRows = [...g2.querySelectorAll(".sw-fav-row")].map(e => e.tagName);
      r.lookbookText = (g2.querySelector(".sw-favs p") || {}).textContent || "";
      const g3 = document.createElement("div"); g3.className = "sw-grid"; const s3 = document.createElement("div"); s3.className = "sheet"; s3.append(g3); document.body.append(s3);
      groupTiles(g3, looks, mk, { hearts: [] });
      r.emptyStartsAll = g3.querySelector(".sw-favs").hidden;
      g3.previousElementSibling.querySelector('[data-g="_fav"]').click();
      r.empty = g3.querySelector(".sw-favs").textContent;
      g3.querySelector(".sw-favs button").click();
      return r;
    });
    await new Promise(r => setTimeout(r, 50));
    out.posted = await page.evaluate(() => posted);
    out.errs = errs;
  } catch (e) { out.crash = String(e && e.stack || e); }
  await browser.close();
  console.log(JSON.stringify(out));
})();
"""

try:
    import test_visual_editor_page as tvp
    tools = tvp.find_tools()
except Exception:
    tools = None
if not tools:
    print("  (page checks skipped: no headless browser here yet; `npx hyperframes@0.9.6 browser ensure` installs one)")
else:
    node, pup, chrome = tools
    work = tempfile.mkdtemp(prefix="ve-favs-page-")
    try:
        script = os.path.join(work, "flow.js")
        open(script, "w", encoding="utf-8").write(FLOW)
        r = subprocess.run([node, script], capture_output=True, text=True, encoding="utf-8", timeout=120, cwd=work,
                           env=dict(os.environ, PUP=pup, CHROME=chrome, SRC=src))
        try:
            res = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            res = {"crash": (r.stdout[-800:] + r.stderr[-800:]) or "no output"}
        run = res.get("run") or {}
        check("page: the browser run finished with no script error", not res.get("crash") and not res.get("errs"), res.get("crash") or res.get("errs"))
        check("page: the My favorites chip shows, with her count", run.get("chip"), run)
        check("page: a hearted look's tile carries a heart, others don't", run.get("heart"))
        check("page: before the tap, every tile shows and the favorites list doesn't", run.get("before") == ["_original", "karaoke", "phrase", "hook"], run.get("before"))
        check("page: one tap shows only her hearted tile and her other hearts", run.get("fav") == ["karaoke", "sw-favs"] and run.get("on"), run.get("fav"))
        check("page: her other hearts are listed by name", run.get("rows") == ["Kinetic Slam", "Typewriter"], run.get("rows"))
        check("page: tapping one hands it to Claude for this line", run.get("asked") == ["x-slam"], run.get("asked"))
        check("page: All brings every tile back and puts the list away", isinstance(run.get("all"), list) and "phrase" in run["all"] and "sw-favs" not in run["all"], run.get("all"))
        check("page: her favorites pick is remembered for the next sheet", run.get("remembered") and run.get("lookbook") == ["karaoke", "sw-favs"], run.get("lookbook"))
        check("page: with no line (the Lookbook), her hearts are a list to name to Claude, not buttons",
              run.get("lookbookRows") == ["DIV", "DIV"] and "tell Claude" in run.get("lookbookText", ""), (run.get("lookbookRows"), run.get("lookbookText")))
        check("page: no hearts yet never opens on an empty filter", run.get("emptyStartsAll"))
        check("page: no hearts yet says so in one plain line, pointing to the library's hearts",
              "No favorites yet" in run.get("empty", "") and "Effects Library" in run.get("empty", ""), run.get("empty"))
        check("page: its button opens the Effects Library", ["/open-library", {"tab": "effects"}] in (res.get("posted") or []), res.get("posted"))
    finally:
        shutil.rmtree(work, ignore_errors=True)

print(f"\ntest_editor_favorites: {total - len(fails)}/{total} passed")
sys.exit(1 if fails else 0)
