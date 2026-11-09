#!/usr/bin/env python3
"""Canonical generator for the style-plan review widget (the rough-cut review surface).

Emits the HARDENED, self-scoping, fail-safe widget so it can never be hand-assembled wrong or render
blank in the canvas again. Two layers of defense are baked in and cannot be forgotten:

  1. SELF-SCOPING (root fix). Every render's script binds to ITS OWN root via `document.currentScript`
     (falling back to the first un-hydrated root), NEVER `getElementById`. Two renders of the same job
     share the same base id; `getElementById` returns the FIRST, which left the newer widget blank
     ("not loading in the canvas"). Self-scoping is immune to duplicate ids and a null currentScript.
  2. STATIC FALLBACK (degradation). Every line is emitted as a visible static row in the markup and the
     hydration body is wrapped in try/catch. If the script never runs or throws, the canvas still shows
     the full numbered cut + a "reply by line number" notice. The review is never a blank box.

Usage:
    python product/build-style-plan.py <job-dir> [--job NAME] [--out FILE]

<job-dir> holds transcript/cuts.json ({"segments":[{start,end,transcript,...}]}). Optional section tags:
transcript/style-plan-sections.json = {"1":"Hook","18":"Confession",...} (1-based line -> tag). Prints
the widget HTML to stdout, or to --out. Feed the result to show_widget on the FIRST review only; re-cuts
use the lean markdown table (see style-plan-widget.md cost policy).
"""
import json, sys, os, re, html, argparse, hashlib

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from fallbacks import note
except Exception:   # the helper missing must not cost her the review
    def note(step, message): pass


class WidgetFailed(Exception):
    """The widget could not be built from a cuts.json that DID read. The review goes on as the lean table."""

def fmt(s):
    m = int(s // 60); sc = round(s % 60)
    return f"{m}:{sc:02d}"

def played(s):
    """Seconds a segment is on screen: (end - start) / speed, so a clip sped to 2x counts half."""
    return (float(s["end"]) - float(s["start"])) / float(s.get("speed", 1.0) or 1.0)

def load_sections(job_dir):
    """The optional section tags ({"1": "Hook", ...}). A damaged file only costs her the tags, never the review."""
    sec_path = os.path.join(job_dir, "transcript", "style-plan-sections.json")
    if not os.path.exists(sec_path):
        return {}
    try:
        with open(sec_path, encoding="utf-8") as fh:
            return {int(k): str(v) for k, v in json.load(fh).items()}
    except Exception as e:
        print(f"style-plan-sections.json would not read ({type(e).__name__}); the style plan goes without section "
              f"tags this time", file=sys.stderr)
        note("style-plan", f"style-plan-sections.json would not read ({type(e).__name__}: {str(e)[:120]}); "
                           f"built the style plan without section tags")
        return {}


def build(job_dir, job=None):
    job = job or os.path.basename(os.path.normpath(job_dir))
    cuts = json.load(open(os.path.join(job_dir, "transcript", "cuts.json"), encoding="utf-8"))
    # cuts.json read: from here on nothing can cost her the review. Anything that breaks becomes WidgetFailed
    # and the caller hands over the lean table instead.
    try:
        return _widget(cuts, job, load_sections(job_dir))
    except Exception as e:
        raise WidgetFailed(f"{type(e).__name__}: {str(e)[:200]}") from e


def _widget(cuts, job, sections):
    segs = cuts["segments"]

    segs_js, static_rows, last = [], [], None
    for i, s in enumerate(segs, 1):
        tag = sections.get(i)
        secf = json.dumps(tag) if (tag and tag != last) else '""'
        if tag and tag != last:
            static_rows.append(f'<div style="font-size:11px; letter-spacing:.04em; color:var(--text-muted); margin:8px 0 2px 2px;">{html.escape(tag)}</div>')
            last = tag
        t = json.dumps(s["transcript"]); dur = fmt(played(s))
        # e is start + on-screen length: the widget reads (e - s) as how long the line plays
        segs_js.append(f'    {{n:{i}, sec:{secf}, t:{t}, s:{s["start"]:.3f}, e:{s["start"] + played(s):.3f}}},')
        static_rows.append(
            f'<div data-static-row style="display:flex; gap:12px; padding:10px 12px; border:0.5px solid var(--border); '
            f'border-radius:var(--radius); background:var(--surface-2); font-size:14px; line-height:1.5;">'
            f'<span style="color:var(--text-muted); font-variant-numeric:tabular-nums;">{i}</span>'
            f'<span style="flex:1 1 auto; color:var(--text-primary);">{html.escape(s["transcript"])}</span>'
            f'<span style="color:var(--text-secondary); font-variant-numeric:tabular-nums;">{dur}</span></div>')

    total = fmt(sum(played(s) for s in segs))
    # Her marks are saved in the widget's own storage under this key (see "SURVIVE THE REMOUNT" in
    # style-plan-widget-build.md). It is the cut's fingerprint, so a re-cut starts clean.
    cut_id = hashlib.sha1(json.dumps([[round(s["start"], 3), round(s["end"], 3), s["transcript"]] for s in segs],
                                     ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
    fill = {"CUTID": cut_id, "SEGS": "\n".join(segs_js), "STATIC": "\n    ".join(static_rows),
            "KEPT0": str(len(segs)), "METER0": total, "JOB": job}
    # ONE pass over the template: text that comes in (her words, the job name) is never searched again, so a
    # "JOB" or "__SEGS__" in what she said stays exactly as she said it.
    return re.sub(r"__(CUTID|SEGS|STATIC|KEPT0|METER0|JOB)__", lambda m: fill[m.group(1)], _TEMPLATE)


def lean_table(job_dir):
    """The lean markdown table (style-plan-widget.md, "Lean re-cut table"), same line numbers as the widget.
    None when even this cannot be made from cuts.json."""
    try:
        segs = json.load(open(os.path.join(job_dir, "transcript", "cuts.json"), encoding="utf-8"))["segments"]
        sections, last = load_sections(job_dir), None
        rows = ["| # | line | dur |", "|---|------|-----|"]
        for i, s in enumerate(segs, 1):
            tag = sections.get(i)
            if tag and tag != last:
                rows.append(f"| | *{tag}* | |")
                last = tag
            line = " ".join(str(s.get("transcript", "")).split()).replace("|", "/")
            rows.append(f"| {i} | {line} | {played(s):.1f}s |")
        total = fmt(sum(played(s) for s in segs))
        return "\n".join(rows) + f"\n\n**total: {total} · reply with cuts/notes by line number**\n"
    except Exception:
        return None

_TEMPLATE = r'''<h2 class="sr-only">Interactive style plan: each kept line is removable, with inline note and reference fields and a live length meter.</h2>
<div data-sp-root id="sp-__JOB__" style="padding: 0.5rem 0 1.25rem;">
  <div style="display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:14px;">
    <div style="display:flex; gap:16px; font-size:13px; color:var(--text-secondary);">
      <span><span data-kept style="color:var(--text-primary); font-weight:500;">__KEPT0__</span> kept</span>
      <span><span data-trashed style="color:var(--text-primary); font-weight:500;">0</span> trashed</span>
      <span><span data-notes style="color:var(--text-primary); font-weight:500;">0</span> notes</span>
    </div>
    <div style="display:flex; align-items:center; gap:10px;">
      <div style="width:150px; height:6px; border-radius:999px; background:var(--surface-1); overflow:hidden;">
        <div data-meter-fill style="height:100%; width:0%; background:var(--text-secondary); transition:width .2s, background .2s;"></div>
      </div>
      <span data-meter-label style="font-size:13px; font-weight:500; min-width:74px; text-align:right;">__METER0__</span>
    </div>
  </div>
  <div data-rows style="display:flex; flex-direction:column; gap:6px;">
    __STATIC__
  </div>
  <div style="display:flex; gap:10px; margin-top:16px; flex-wrap:wrap;">
    <button type="button" data-send>Send my edits <i class="ti ti-arrow-up-right" aria-hidden="true"></i></button>
    <button type="button" data-reset><i class="ti ti-refresh" aria-hidden="true"></i> Reset</button>
  </div>
  <label style="display:flex; align-items:center; gap:8px; margin-top:12px; font-size:13px; color:var(--text-secondary); cursor:pointer;">
    <input type="checkbox" data-keep-widget checked> Show me this visual style plan on every new reel
  </label>
  <div data-fallback style="display:none; margin-top:14px; padding:12px; border:0.5px solid var(--border-strong); border-radius:var(--radius); background:var(--surface-1);">
    <div data-fallback-note style="font-size:13px; color:var(--text-secondary); margin-bottom:8px;">If this didn't show up in the chat, copy it and paste it to me.</div>
    <textarea data-fallback-text readonly rows="5" style="width:100%; font-size:13px; resize:vertical;"></textarea>
    <button type="button" data-copy style="margin-top:8px;">Copy to clipboard <i class="ti ti-copy" aria-hidden="true"></i></button>
  </div>
</div>
<script>(function(){
  // FAIL-SAFE SCOPING: bind to THIS render's own root, never a shared global id. Two renders of the same
  // job share id="sp-__JOB__"; getElementById returns the FIRST, so the newer widget stays blank ("not
  // loading in the canvas"). currentScript resolves our own sibling; else claim the first un-hydrated
  // root. Immune to duplicate ids AND a null currentScript.
  var me = document.currentScript;
  function pickRoot(){
    if (me && me.previousElementSibling && me.previousElementSibling.matches &&
        me.previousElementSibling.matches("[data-sp-root]")) return me.previousElementSibling;
    var all = document.querySelectorAll("[data-sp-root]");
    for (var i=0;i<all.length;i++){ if(!all[i].hasAttribute("data-sp-hydrated")) return all[i]; }
    return all.length ? all[all.length-1] : null;
  }
  var root = pickRoot();
  if (!root) return;
  root.setAttribute("data-sp-hydrated","1");
  try {
  const q = s => root.querySelector(s);
  const SEGS = [
__SEGS__
  ];
  const state = {};
  SEGS.forEach(g => state[g.n] = {trashed:false, note:"", ref:"", noteOpen:false, refOpen:false});
  // SURVIVE THE REMOUNT: the host reloads a widget after it sends (and when the chat re-renders), which
  // wipes everything that lives only in memory. Her marks and the last message she sent live in this
  // frame's storage, keyed to this cut, and come back on every load.
  const KEY = "style-plan:__JOB__:__CUTID__";
  function stores(){ const out = []; try { out.push(window.sessionStorage); } catch(e){} try { out.push(window.localStorage); } catch(e){} return out.filter(Boolean); }
  let sentMsg = "";
  function save(){
    const kw = q("[data-keep-widget]");
    const marks = {};
    SEGS.forEach(g => { const st = state[g.n]; marks[g.n] = {trashed:st.trashed, note:st.note, ref:st.ref, noteOpen:st.noteOpen, refOpen:st.refOpen}; });
    const v = JSON.stringify({marks:marks, keep:kw ? kw.checked : true, sent:sentMsg});
    stores().forEach(st => { try { st.setItem(KEY, v); } catch(e){} });
  }
  function load(){
    for (const st of stores()){ try { const v = st.getItem(KEY); if (v) return JSON.parse(v); } catch(e){} }
    return null;
  }
  function forget(){ stores().forEach(st => { try { st.removeItem(KEY); } catch(e){} }); }
  // SHARE WITH THE HOST: the app hands a widget's shared content to Claude with her next message
  // (read_widget_context). So her marks reach Claude even when a send never lands in the chat.
  let shareTimer = null;
  function share(text){
    try {
      if (window.app && typeof window.app.sendRequest === "function"){
        const p = window.app.sendRequest({method:"ui/update-model-context", params:{content:[{type:"text", text:text}]}});
        if (p && typeof p.catch === "function") p.catch(() => {});
      }
    } catch(e){}
  }
  function changed(){
    save();
    clearTimeout(shareTimer);
    shareTimer = setTimeout(() => share("Style plan marks for the __JOB__ rough cut, as they stand now (not sent yet):\n" + compile()), 600);
  }
  const fmt = sec => { const m=Math.floor(sec/60), s=Math.round(sec%60); return m+":"+String(s).padStart(2,"0"); };
  const hasMeta = st => (st.note && st.note.trim()) || (st.ref && st.ref.trim());
  function refreshCounts(){
    let kept=0, trashed=0, notes=0, dur=0;
    SEGS.forEach(g => { const st=state[g.n]; if(st.trashed) trashed++; else { kept++; dur+=(g.e-g.s); } if(hasMeta(st)) notes++; });
    q("[data-kept]").textContent = kept;
    q("[data-trashed]").textContent = trashed;
    q("[data-notes]").textContent = notes;
    q("[data-meter-label]").textContent = fmt(dur);
    const fill = q("[data-meter-fill]");
    fill.style.width = Math.min(100, dur/120*100) + "%";
    const good = dur>=45 && dur<=90;
    fill.style.background = good ? "var(--text-success)" : (dur>90 ? "var(--text-warning)" : "var(--text-secondary)");
    q("[data-meter-label]").style.color = good ? "var(--text-success)" : "var(--text-primary)";
  }
  function makeField(g, kind){
    const st = state[g.n];
    const wrap = document.createElement("div"); wrap.style.cssText = "margin-top:8px; display:flex; flex-direction:column; gap:4px;";
    const lbl = document.createElement("label"); lbl.textContent = kind === "note" ? "Note" : "Reference or link";
    lbl.style.cssText = "font-size:11px; color:var(--text-muted); letter-spacing:.03em;";
    const inp = document.createElement(kind === "note" ? "textarea" : "input");
    if(kind === "note"){ inp.rows = 2; inp.style.cssText = "width:100%; resize:vertical; font-size:13px; padding:6px 8px;"; }
    else { inp.type = "text"; inp.placeholder = "paste a link, timestamp, or file path"; inp.style.cssText = "width:100%; font-size:13px;"; }
    inp.value = kind === "note" ? st.note : st.ref;
    inp.oninput = e => { if(kind === "note") st.note = e.target.value; else st.ref = e.target.value; refreshCounts(); changed(); };
    wrap.appendChild(lbl); wrap.appendChild(inp); return { wrap, inp };
  }
  function render(){
    const rows = q("[data-rows]"); rows.innerHTML = ""; let lastSec = null; let focusTarget = null;
    SEGS.forEach(g => {
      const st = state[g.n];
      if(g.sec && g.sec !== lastSec){
        const h = document.createElement("div"); h.textContent = g.sec;
        h.style.cssText = "font-size:11px; letter-spacing:.04em; color:var(--text-muted); margin:8px 0 2px 2px;";
        rows.appendChild(h); lastSec = g.sec;
      }
      const row = document.createElement("div");
      row.style.cssText = "display:flex; align-items:flex-start; gap:12px; padding:10px 12px; border:0.5px solid var(--border); border-radius:var(--radius); background:var(--surface-2);" + (st.trashed ? "opacity:.5;" : "");
      const left = document.createElement("div"); left.style.cssText = "display:flex; gap:4px; flex:0 0 auto; padding-top:1px;";
      const attachBtn = document.createElement("button"); attachBtn.type = "button";
      attachBtn.innerHTML = '<i class="ti ti-paperclip" aria-hidden="true"></i>';
      attachBtn.setAttribute("aria-label","Add a reference to line "+g.n);
      attachBtn.style.cssText = "padding:4px 7px; font-size:14px; line-height:1;" + (((st.ref && st.ref.trim()) || st.refOpen) ? "border-color:var(--border-accent); color:var(--text-accent);" : "");
      attachBtn.addEventListener("click", () => { st.refOpen = !st.refOpen; if(st.refOpen) st._focus = "ref"; render(); save(); });
      const noteBtn = document.createElement("button"); noteBtn.type = "button";
      noteBtn.innerHTML = '<i class="ti ti-message" aria-hidden="true"></i>';
      noteBtn.setAttribute("aria-label","Add a note to line "+g.n);
      noteBtn.style.cssText = "padding:4px 7px; font-size:14px; line-height:1;" + (((st.note && st.note.trim()) || st.noteOpen) ? "border-color:var(--border-accent); color:var(--text-accent);" : "");
      noteBtn.addEventListener("click", () => { st.noteOpen = !st.noteOpen; if(st.noteOpen) st._focus = "note"; render(); save(); });
      left.appendChild(attachBtn); left.appendChild(noteBtn);
      const mid = document.createElement("div"); mid.style.cssText = "flex:1 1 auto; min-width:0;";
      const line = document.createElement("div");
      line.style.cssText = "font-size:14px; line-height:1.5;" + (st.trashed ? "text-decoration:line-through; color:var(--text-muted);" : "color:var(--text-primary);");
      const num = document.createElement("span"); num.textContent = g.n;
      num.style.cssText = "color:var(--text-muted); font-variant-numeric:tabular-nums; margin-right:8px;";
      line.appendChild(num); line.appendChild(document.createTextNode(g.t));
      mid.appendChild(line);
      if(st.refOpen){ const f = makeField(g, "ref"); mid.appendChild(f.wrap); if(st._focus === "ref") focusTarget = f.inp; }
      if(st.noteOpen){ const f = makeField(g, "note"); mid.appendChild(f.wrap); if(st._focus === "note") focusTarget = f.inp; }
      st._focus = null;
      const right = document.createElement("div"); right.style.cssText = "display:flex; align-items:center; gap:8px; flex:0 0 auto;";
      const dur = document.createElement("span"); dur.textContent = fmt(g.e-g.s);
      dur.style.cssText = "font-size:12px; color:var(--text-secondary); font-variant-numeric:tabular-nums; min-width:30px; text-align:right;";
      const trash = document.createElement("button"); trash.type = "button";
      trash.innerHTML = '<i class="ti ti-trash" aria-hidden="true"></i>';
      trash.setAttribute("aria-label", (st.trashed?"Restore":"Cut")+" line "+g.n);
      trash.style.cssText = "padding:4px 7px; font-size:14px; line-height:1;" + (st.trashed ? "border-color:var(--border-danger); color:var(--text-danger);" : "");
      trash.addEventListener("click", () => { st.trashed = !st.trashed; render(); refreshCounts(); changed(); });
      right.appendChild(dur); right.appendChild(trash);
      row.appendChild(left); row.appendChild(mid); row.appendChild(right); rows.appendChild(row);
    });
    if(focusTarget) focusTarget.focus();
  }
  function compile(){
    const trashed = SEGS.filter(g => state[g.n].trashed).map(g => g.n);
    const notes = SEGS.filter(g => state[g.n].note && state[g.n].note.trim()).map(g => 'line '+g.n+' ("'+g.t.slice(0,40)+'..."): '+state[g.n].note.trim());
    const refs  = SEGS.filter(g => state[g.n].ref && state[g.n].ref.trim()).map(g => 'line '+g.n+': '+state[g.n].ref.trim());
    const kw = q("[data-keep-widget]");
    const pref = (kw && !kw.checked) ? "\n\nStyle plan: show me the simple table from now on, not the visual one." : "";
    if(trashed.length===0 && notes.length===0 && refs.length===0){
      return "The __JOB__ rough cut looks good, no changes. Move on to the creative plan." + pref;
    }
    let msg = "Here are my edits to the __JOB__ rough cut:\n";
    if(trashed.length) msg += "\nCut these lines: "+trashed.join(", ")+".";
    if(notes.length) msg += "\nNotes:\n- "+notes.join("\n- ");
    if(refs.length) msg += "\nReferences:\n- "+refs.join("\n- ");
    msg += "\n\nRe-cut with these changes, then show me the updated cut.";
    return msg + pref;
  }
  function deliver(msg){
    try { if (typeof sendPrompt === "function"){ sendPrompt(msg); return true; } } catch(e){}
    return false;
  }
  function showCopyBox(msg, text){
    const fb = q("[data-fallback]"), ta = q("[data-fallback-text]"), note = q("[data-fallback-note]");
    ta.value = msg; fb.style.display = "block";
    if(note) note.textContent = text;
  }
  function copyText(text){
    const ta = q("[data-fallback-text]");
    const byCommand = () => { try { ta.focus(); ta.select(); return document.execCommand("copy"); } catch(e){ return false; } };
    try {
      if (navigator.clipboard && typeof navigator.clipboard.writeText === "function")
        return navigator.clipboard.writeText(text).then(() => true, () => byCommand());
    } catch(e){}
    return Promise.resolve(byCommand());
  }
  // Send never trusts the chat to receive it. In this order: save the message (the host reloads the
  // widget after a send), show it in the copy box, share it with the host, copy it, THEN send.
  function sendEdits(){
    const msg = compile();
    sentMsg = msg; save(); clearTimeout(shareTimer);
    showCopyBox(msg, "Sent to the chat. If it didn't show up there, copy this and paste it to me:");
    share("She pressed Send my edits on the __JOB__ style plan. This is what she sent:\n" + msg);
    const sent = deliver(msg);
    copyText(msg).then(ok => {
      const note = q("[data-fallback-note]");
      if(!note) return;
      note.textContent = (sent ? "Sent to the chat. If it didn't show up there, " : "This couldn't be sent from here. ")
        + (ok ? "it's on your clipboard too: paste it to me." : "copy this and paste it to me:");
    });
  }
  function resetSheet(){
    SEGS.forEach(g => { state[g.n]={trashed:false, note:"", ref:"", noteOpen:false, refOpen:false}; });
    sentMsg = ""; forget(); clearTimeout(shareTimer);
    q("[data-fallback]").style.display = "none"; q("[data-fallback-text]").value = "";
    render(); refreshCounts();
    share("She reset the __JOB__ style plan: no marks.");
  }
  q("[data-send]").addEventListener("click", sendEdits);
  q("[data-reset]").addEventListener("click", resetSheet);
  q("[data-copy]").addEventListener("click", () => {
    const btn = q("[data-copy]");
    copyText(q("[data-fallback-text]").value).then(ok => { if(!ok) { const ta = q("[data-fallback-text]"); ta.focus(); ta.select(); } });
    if(btn) btn.blur();
  });
  const kwBox = q("[data-keep-widget]");
  if(kwBox) kwBox.addEventListener("change", changed);
  // Bring her marks back after a reload, plus the copy box if she had already sent them.
  const saved = load();
  if(saved){
    if(saved.marks) SEGS.forEach(g => { const m = saved.marks[g.n]; if(m) Object.assign(state[g.n], m); });
    if(kwBox && saved.keep === false) kwBox.checked = false;
    if(saved.sent){ sentMsg = saved.sent; showCopyBox(saved.sent, "You sent these edits. If they didn't show up in the chat, copy this and paste it to me:"); }
  }
  render(); refreshCounts();
  } catch(err){
    // Hydration failed: keep the static rows (they already show every line + duration) so the canvas is
    // never blank, and add a short notice so the review still works by line number.
    root.setAttribute("data-sp-degraded","1");
    var n=document.createElement("div");
    n.style.cssText="margin-top:10px; font-size:12px; color:var(--text-secondary);";
    n.textContent="(Showing the read-only cut. Reply with any cuts or notes by line number.)";
    root.appendChild(n);
  }
})();</script>'''

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("job_dir", nargs="?")
    ap.add_argument("--job", default=None, help="job name for id + message (default: folder name)")
    ap.add_argument("--out", default=None, help="write to file (default: stdout)")
    ap.add_argument("--which", action="store_true",
                    help="print widget-first / widget / table: which first review to give her, then exit")
    a = ap.parse_args()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import learned
        pref, rec = learned.value("review.style_plan", "widget")
    except Exception:
        pref, rec = "widget", True   # a missing or damaged preference file never costs her the review
    if a.which:
        # widget-first = she has never chosen: show the widget plus the one-time switch-off line, then save
        # `widget` so the line never repeats (see style-plan-widget.md, "Her on/off switch").
        print("widget-first" if rec is None else pref); sys.exit(0)
    if not a.job_dir:
        ap.error("job_dir is required")
    import review_route; review_route.refuse_if_editor(a.job or a.job_dir, "the original widget")
    if pref == "table":
        print("SHE SWITCHED THE VISUAL STYLE PLAN OFF (review.style_plan = table): give her the lean markdown "
              "table on this first review, not this widget, and end it with: \"Want the visual style plan "
              "back? Just say so.\"", file=sys.stderr)
    try:
        out = build(a.job_dir, a.job)
    except WidgetFailed as e:
        # Never a dead end: the review is the lean table this time. Nothing goes to show_widget.
        note("style-plan", f"the widget would not build ({e}); gave her the lean markdown table instead")
        table = lean_table(a.job_dir)
        print("STYLE PLAN TABLE INSTEAD OF THE WIDGET: the widget would not build this time "
              f"({str(e)[:160]}). Do not call show_widget. Give her the lean markdown table "
              + ("printed on stdout" if table else "from transcript/cuts.json (style-plan-widget.md, \"Lean re-cut table\")")
              + ", say in one calm line that the visual plan could not be drawn this time, and end with the "
              "link below.", file=sys.stderr)
        if table:
            sys.stdout.write(table)
        out = None
    if out is not None and a.out:
        open(a.out, "w", encoding="utf-8").write(out); print(f"wrote {len(out)} chars -> {a.out}", file=sys.stderr)
    elif out is not None:
        sys.stdout.write(out)
    # Also emit the VERIFIED preview link for the final message AFTER the widget (text written before a tool
    # call is folded away in the app) — computed + existence-checked, so the "Couldn't load this preview"
    # (doubled-path) bug can't slip in by hand. Best-effort.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import style_plan_link
        job = a.job or os.path.basename(os.path.normpath(a.job_dir))
        after = "show_widget" if out is not None else "the table"
        print(f"\nPUT THIS LINK LAST, in your final message AFTER {after} (run every other command first;"
              " text before a tool call is folded away):\n  " + style_plan_link.emit(job), file=sys.stderr)
    except SystemExit:
        print("(no preview mp4 yet — build the cut, then: python product/style_plan_link.py <job>)", file=sys.stderr)
    except Exception as e:
        print(f"(the preview link could not be made here ({type(e).__name__}); run: python product/style_plan_link.py <job>)",
              file=sys.stderr)
