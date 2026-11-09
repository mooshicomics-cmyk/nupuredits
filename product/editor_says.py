#!/usr/bin/env python3
"""editor_says.py — Claude's message for her open visual editor page: the page pops it as a card she closes.

She edits on her page, not in the chat, so a question, an approval or "your sketches are in" sat unseen in the chat.
Now whatever Claude has for her lands on the page too: a Chef Claude card at the top of her preview (on every tab),
the tab's title says so while she is in another tab, and (when she allowed it) a browser notification plus the
engine's soft chime. It stays until she closes it.

    python3 product/visual_editor.py tell <job> "<one plain line>" [--chat]   Claude's own words (the CLI lives there)
    python3 product/editor_says.py hook ask|permission|answered                the chat's hooks (.claude/hooks/editor-says.sh)

Where it fires by itself (the engine already knows something is ready for her): her sandbox sketches landing
(visual_editor.sandbox_takes), a note fixed (resolve), a new look on her line or in her lookbook (place-look,
look-request done), her looks made for her cut (`looks`), and an export done or stopped (finish.run). The hooks add
"Claude has a question for you" when the chat's question box or a permission prompt waits on her while her page is
open, and take it down once she answers in the chat.

The file is projects/<job>/review/claude-says.json: {"messages": [{id, at, text, chat, kind, go, group, n, seen}]}.
`chat` = the answer goes in her Claude chat. `go` = where the card's button takes her (sandbox, notes, cut, visuals,
sound, finish). Messages close for good when she closes them (POST /says-seen), so a reload never pops one twice.
Stdlib only, and it never raises into a caller that was only telling her something.
"""
import json, os, random, re, sys, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_STATE = os.environ.get("VE_SERVER_STATE") or os.path.join(ROOT, "_local", "visual-editor-server.json")
NAME = "claude-says.json"
KEEP = 8                  # messages kept per reel (the newest)
SHOW_S = 6 * 3600         # a message older than this never pops (she was away; the chat has it)
MERGE_S = 180             # the same kind of news within 3 minutes is one card ("Fixed 3 of your notes")
SOFT_S = 120              # a hook's "question in the chat" is skipped when Claude said so itself this recently
OPEN_S = 120              # a reel's page counts as open when it asked its server for anything this recently
TEXT_MAX = 220
GO = ("sandbox", "notes", "cut", "visuals", "sound", "finish")


def path(jd):
    return os.path.join(jd, "review", NAME)


def _load(jd):
    try:
        with open(path(jd), encoding="utf-8") as f:
            ms = (json.load(f) or {}).get("messages") or []
        return [m for m in ms if isinstance(m, dict) and m.get("id")]
    except Exception:
        return []


MARK = ".claude-chat-card"   # review/<this> exists while an "in the chat" card is up: the answered hook's bash fast path


def _save(jd, ms):
    p = path(jd)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=NAME + ".", suffix=".tmp", dir=os.path.dirname(p))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"messages": ms[-KEEP:]}, f, indent=1, ensure_ascii=False)
    for attempt in range(40):                                # Windows: the page's read can hold it for a moment
        try:
            os.replace(tmp, p)
            break
        except PermissionError:
            if attempt == 39:
                raise
            time.sleep(0.1)
    mark = os.path.join(os.path.dirname(p), MARK)
    try:
        if any(m.get("chat") and not m.get("seen") for m in ms[-KEEP:]):
            with open(mark, "w", encoding="utf-8") as f:
                f.write("1")
        elif os.path.exists(mark):
            os.remove(mark)
    except OSError:
        pass


def clean(text):
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    return t if len(t) <= TEXT_MAX else t[:TEXT_MAX - 1].rstrip() + "…"


def tell(jd, text, chat=False, kind="note", go=None, group=None, merged=None, soft=False):
    """Leave her page a message. group: news of the same group within MERGE_S replaces the last unseen card (merged,
    with {n}, is its text from the second one on). soft: skipped when an unseen chat message is that fresh (the hooks).
    Returns the message, or None when nothing was written."""
    text = clean(text)
    if not text:
        raise ValueError("an empty message")
    now = time.time()
    ms = [m for m in _load(jd) if now - float(m.get("at") or 0) < 24 * 3600]
    if soft and any(m.get("chat") and not m.get("seen") and now - float(m.get("at") or 0) < SOFT_S for m in ms):
        return None
    n = 1
    if group:
        prev = next((m for m in reversed(ms) if m.get("group") == group and not m.get("seen")
                     and now - float(m.get("at") or 0) < MERGE_S), None)
        if prev:
            prev["seen"] = "merged"
            n = int(prev.get("n") or 1) + 1
            if merged:
                text = clean(merged.format(n=n))
    m = {"id": f"m{int(now * 1000)}{random.randint(100, 999)}", "at": round(now, 3), "text": text, "chat": bool(chat),
         "kind": str(kind or "note"), "go": go if go in GO else None, "group": group, "n": n, "seen": False}
    ms.append(m)
    _save(jd, ms)
    return m


def told(jd, *a, **kw):
    """tell() for the engine's own events: a message is a courtesy, so it never breaks the work that sent it."""
    try:
        return tell(jd, *a, **kw)
    except Exception:
        return None


def pending(jd):
    """The messages her page should show: not closed, not too old. Oldest first."""
    now = time.time()
    return [{k: m.get(k) for k in ("id", "at", "text", "chat", "kind", "go", "n")}
            for m in _load(jd) if not m.get("seen") and now - float(m.get("at") or 0) < SHOW_S]


def seen(jd, ids=None, only_chat=False):
    """She closed them (ids), or every one (None). only_chat: just the "it's in the chat" ones (she answered there)."""
    ms, hit = _load(jd), 0
    want = None if ids is None else {str(i) for i in ids}
    for m in ms:
        if not m.get("seen") and (want is None or m["id"] in want) and (not only_chat or m.get("chat")):
            m["seen"] = True
            hit += 1
    if hit or os.path.exists(os.path.join(jd, "review", MARK)):   # the marker always matches what is up
        _save(jd, ms)
    return hit


def open_pages(within=OPEN_S):
    """The reels whose editor page is open right now (asked its server for anything within `within` seconds, a tab
    in the background included): their folders. [] when no page server runs."""
    try:
        import urllib.request
        with open(SERVER_STATE, encoding="utf-8") as f:
            port = int(json.load(f)["port"])
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/ping", timeout=1.5) as r:
            pages = (json.load(r) or {}).get("pages") or {}
    except Exception:
        return []
    out = []
    for job, idle in pages.items():
        jd = os.path.join(ROOT, "projects", job)
        if "/" not in job and "\\" not in job and not job.startswith(".") and os.path.isdir(jd) and float(idle) <= within:
            out.append(jd)
    return out


def chime():
    """The engine's soft chime (.claude/hooks/chime.sh: her off switch and its debounce apply), in the background."""
    try:
        import shutil, subprocess
        bash, hook = shutil.which("bash"), os.path.join(ROOT, ".claude", "hooks", "chime.sh")
        if bash and os.path.isfile(hook):
            subprocess.Popen([bash, hook], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    except Exception:
        pass
    return False


HOOK_SAYS = {"ask": "Claude has a question for you.", "permission": "Claude needs your OK to keep going."}


def hook(event):
    """The chat's hooks: a question box or a permission prompt waits on her (ask / permission) while her page is open,
    or she answered in the chat (answered: the "it's in the chat" cards come down, on every reel)."""
    if event in HOOK_SAYS:
        for jd in open_pages():
            told(jd, HOOK_SAYS[event], chat=True, kind="chat", group="chat", soft=True)
    elif event == "answered":
        import glob
        for p in glob.glob(os.path.join(ROOT, "projects", "*", "review", MARK)):
            try:
                if time.time() - os.path.getmtime(p) < 24 * 3600:
                    seen(os.path.dirname(os.path.dirname(p)), only_chat=True)
                else:
                    os.remove(p)                             # a day-old marker: nothing of it would pop anyway
            except Exception:
                pass


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "hook":
        try:
            hook(sys.argv[2])
        except Exception:
            pass                                            # a hook never fails the chat
        sys.exit(0)
    print(__doc__)
    sys.exit(2)
