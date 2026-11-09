#!/usr/bin/env python3
"""The visual editor's NOTIFICATION BELL — a surface SEPARATE from the chat (2026-11-07).

The bell houses announcements only: **major REE updates** (an engine update is ready) and **news from the engine's maker**
(creator/system broadcasts to the buyer). It never carries Claude's per-edit updates — those are synthesized,
one line each, and live in the chat (editor_says.py / the chat panel). Keeping the two surfaces apart is what
stops the bell from echoing the chat.

Store: projects/<job>/review/announce.json -> {"items": [{id, at, kind, title, text, go, seen}]}
  kind  = "ree" | "news"
  go    = optional button target the page understands (finish, visuals, sound, cut, sandbox)
The REE "update ready" banner is injected by pending() from _local/update-available.json ({version, note}), so
the update checker only has to drop that file; it's deduped by version and respects the per-id seen set.

CLI:
    python3 product/editor_announce.py add   <job> --kind news|ree --title "..." "text" [--go finish]
    python3 product/editor_announce.py list  <job>
    python3 product/editor_announce.py seen   <job> [id ...]        (no ids = all)
"""
import argparse
import json
import os
import random
import sys
import tempfile
import time

for _s in (sys.stdout, sys.stderr):                          # a ✓ printed on a cp1252 PC console raises without this
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "announce.json"
KEEP = 50
GO = ("sandbox", "cut", "visuals", "sound", "finish", "notes")
KINDS = ("ree", "news")


def path(jd):
    return os.path.join(jd, "review", NAME)


def _load(jd):
    try:
        with open(path(jd), encoding="utf-8") as f:
            items = (json.load(f) or {}).get("items") or []
        return [m for m in items if isinstance(m, dict) and m.get("id")]
    except Exception:
        return []


def _save(jd, items):
    p = path(jd)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    kept = items[-KEEP:]
    # Never truncate a DISMISSED update banner out of the file: without its seen-record, pending() would re-surface
    # the same "Update ready" banner once 50+ announcements pile up. Carry those few records past the cap.
    kept_ids = {m.get("id") for m in kept}
    extra = [m for m in items[:-KEEP] if m.get("seen") and str(m.get("id", "")).startswith("ree-update-")
             and m.get("id") not in kept_ids]
    fd, tmp = tempfile.mkstemp(prefix=NAME + ".", suffix=".tmp", dir=os.path.dirname(p))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"items": extra + kept}, f, indent=1, ensure_ascii=False)
    for attempt in range(40):                                # Windows: the page's read can hold it for a moment
        try:
            os.replace(tmp, p)
            break
        except PermissionError:
            if attempt == 39:
                raise
            time.sleep(0.1)


def add(jd, kind, title, text, go=None):
    kind = kind if kind in KINDS else "news"
    items = _load(jd)
    now = time.time()
    m = {"id": f"a{int(now * 1000)}{random.randint(100, 999)}", "at": round(now, 3),
         "kind": kind, "title": (title or "").strip(), "text": (text or "").strip(),
         "go": go if go in GO else None, "seen": False}
    items.append(m)
    _save(jd, items)
    return m


def _update_banner(jd):
    """The REE 'update ready' item, from _local/update-available.json, deduped by version against the seen set.
    Fully guarded: this runs inside /status (the editor's hot polling endpoint), so a malformed file must never
    raise — a bad field just means no banner, never a 500 that freezes her page."""
    try:
        with open(os.path.join(ROOT, "_local", "update-available.json"), encoding="utf-8") as f:
            u = json.load(f) or {}
        ver = str(u.get("version") or "").strip()
        if not ver:
            return None
        try:
            at = float(u.get("at") or 0)
        except (TypeError, ValueError):
            at = 0.0
        return {"id": f"ree-update-{ver}", "at": at, "kind": "ree",
                "title": f"Update ready — v{ver}",
                "text": (str(u.get("note") or "").strip()
                         or "A new version of your engine is ready. Type “update me” to install."),
                "go": None}
    except Exception:
        return None


def pending(jd):
    """What the bell shows: unseen stored items, plus the REE update banner if one is waiting and unseen."""
    items = _load(jd)
    seen_ids = {m["id"] for m in items if m.get("seen")}
    out = [{k: m.get(k) for k in ("id", "at", "kind", "title", "text", "go")}
           for m in items if not m.get("seen")]
    banner = _update_banner(jd)
    if banner and banner["id"] not in seen_ids:
        out.append(banner)
    out.sort(key=lambda m: m.get("at") or 0)
    return out


def seen(jd, ids=None):
    """She dismissed one or more (ids), or all (None). The update banner is remembered by its own id."""
    items = _load(jd)
    want = set(str(i) for i in ids) if ids else None
    banner = _update_banner(jd)
    # a dismissed banner is recorded as a real (seen) item so it stays gone
    if banner and (want is None or banner["id"] in (want or set())) \
            and not any(m["id"] == banner["id"] for m in items):
        items.append({**banner, "seen": True})
    n = 0
    for m in items:
        if not m.get("seen") and (want is None or m["id"] in want):
            m["seen"] = True
            n += 1
    _save(jd, items)
    return n


def _main(argv=None):
    ap = argparse.ArgumentParser(description="The editor's notification bell (REE + news announcements).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pa = sub.add_parser("add")
    pa.add_argument("job")
    pa.add_argument("text")
    pa.add_argument("--kind", default="news", choices=KINDS)
    pa.add_argument("--title", default="")
    pa.add_argument("--go", default=None, choices=GO)
    pl = sub.add_parser("list")
    pl.add_argument("job")
    ps = sub.add_parser("seen")
    ps.add_argument("job")
    ps.add_argument("ids", nargs="*")
    a = ap.parse_args(argv)

    jd = a.job if os.path.isdir(a.job) else os.path.join(ROOT, "projects", a.job)
    if not os.path.isdir(jd):
        print(f"no such job: {a.job}", file=sys.stderr)
        return 2
    if a.cmd == "add":
        m = add(jd, a.kind, a.title, a.text, a.go)
        print(f"✓ bell: [{m['kind']}] {m['title'] or m['text']}")
    elif a.cmd == "list":
        for m in pending(jd):
            print(f"[{m['kind']}] {m.get('title') or ''} — {m.get('text') or ''}")
    elif a.cmd == "seen":
        print(f"marked {seen(jd, a.ids or None)} seen")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
