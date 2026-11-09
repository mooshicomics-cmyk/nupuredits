#!/usr/bin/env python3
"""Regression guard for the empty-registry crash class.

`cleanyap.py` / `superyap.py` finalize() register a new draft into CapCut's root_meta_info.json by
cloning an existing entry's shape. On a BRAND-NEW CapCut install `all_draft_store` is `[]`, so the old
`all_draft_store[0]` clone raised IndexError and crashed the buyer's first-ever build. The shared
`capcut_media.register_draft()` now falls back to a real-schema template when the store is empty.

Run: python3 product/tests/test_finalize_registry.py
"""
import json, os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import capcut_media
import capcut_front

# register_draft() also pins each draft to the top of CapCut's list (capcut_front.remember + ensure), and
# those write the REAL pin list and the REAL CapCut project list. Point both at a throwaway folder, so this
# test never touches the machine it runs on: it used to leave its fake draft names in the seller's pin list.
_REAL = [capcut_front.STATE, capcut_front.META]
_REAL_BEFORE = {p: (os.path.getmtime(p) if os.path.exists(p) else None) for p in _REAL}
_pins = tempfile.mkdtemp(prefix="capcut-front-test-")
capcut_front.CAP = _pins
capcut_front.META = os.path.join(_pins, "root_meta_info.json")
capcut_front.STATE_DIR = _pins
capcut_front.STATE = os.path.join(_pins, "capcut-front.json")
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def _fresh_root(store):
    """A temp CapCut projects dir whose root_meta_info.json has the given all_draft_store."""
    cap = tempfile.mkdtemp(prefix="capcut-test-")
    json.dump({"all_draft_store": store}, open(f"{cap}/root_meta_info.json", "w", encoding="utf-8"))
    return cap


def _read(cap):
    return json.load(open(f"{cap}/root_meta_info.json", encoding="utf-8"))["all_draft_store"]


# 1) FROM EMPTY: the crash repro — must NOT raise, and must produce a well-formed, real-schema entry.
cap = _fresh_root([])
capcut_media.register_draft(cap, "my-first-reel", "/x/my-first-reel",
                            "/x/my-first-reel/draft_info.json", "uuid-1", 15_500_000, 1_000_000_000)
store = _read(cap)
assert len(store) == 1, "empty-start registration should create exactly one entry"
e = store[0]
for k in capcut_media._EMPTY_REGISTRY_ENTRY:
    assert k in e, f"entry is missing real-schema key {k!r}"
assert e["draft_name"] == "my-first-reel"
assert e["draft_cover"] == "/x/my-first-reel/draft_cover.jpg"
assert e["tm_duration"] == 15_500_000
assert e["tm_draft_create"] == 1_000_000_000 * 1_000_000, "now must be threaded, not recomputed"
assert isinstance(e["draft_is_invisible"], bool), "field types preserved from real schema"
assert isinstance(e["tm_draft_cloud_modified"], int)

# 2) TWO NAMES coexist without clobbering each other.
capcut_media.register_draft(cap, "second-reel", "/x/second-reel",
                            "/x/second-reel/draft_info.json", "uuid-2", 30_000_000, 1_000_000_001)
names = [x["draft_name"] for x in _read(cap)]
assert "my-first-reel" in names and "second-reel" in names, "second draft must not replace the first"
assert names[0] == "second-reel", "newest draft inserts at the top (grid sort order)"

# 3) RE-REGISTER same name -> replace in place, never duplicate.
capcut_media.register_draft(cap, "second-reel", "/x/second-reel",
                            "/x/second-reel/draft_info.json", "uuid-2b", 31_000_000, 1_000_000_002)
store = _read(cap)
assert [x["draft_name"] for x in store].count("second-reel") == 1, "re-register must not duplicate"
assert store[0]["draft_id"] == "uuid-2b", "re-register replaces with the new values"

# 4) NON-EMPTY start still clones the existing entry's shape (unchanged behavior).
cap2 = _fresh_root([{"draft_name": "old", "custom_field": "keep-me", "draft_cover": "old.jpg"}])
capcut_media.register_draft(cap2, "new-one", "/y/new-one",
                            "/y/new-one/draft_info.json", "uuid-3", 10_000_000, 1_000_000_003)
top = _read(cap2)[0]
assert top["custom_field"] == "keep-me", "non-empty start should clone the existing shape verbatim"
assert top["draft_name"] == "new-one"

# 5) The test left the machine alone: the real pin list and the real CapCut project list are untouched.
for p, before in _REAL_BEFORE.items():
    after = os.path.getmtime(p) if os.path.exists(p) else None
    assert after == before, f"the test wrote to a real file it must never touch: {p}"

print("✓ finalize registry: from-empty all_draft_store never raises, entry is well-formed and "
      "real-schema-shaped, repeat registers don't duplicate or clobber other drafts")
