#!/usr/bin/env python3
"""user_style.py — where her saved default style pack is kept, and the one reader and writer for it.

A buyer's engine keeps it in `product/creative-vault/user-style.json` ("default_pack"), which ships with null
and which every update protects.

IN THE COPY THE ENGINE SHIPS FROM (the seller's own engine: `make-ship.sh` sits at its root, and make-ship
never puts itself in a bundle, so a buyer's copy never has it) that file is a SHIPPED one, so saving a default
there dirtied the tree and make-ship refused to build on it. So there the default goes to
`_local/default-pack.json` instead (git-ignored, never staged), the same split pack_write.py makes for her own
packs. Readers take that one first and fall back to user-style.json.

Every function takes the shipped user-style.json path its caller already uses, and finds the engine root from
it, so a caller pointed at a scratch user-style.json (the tests) is never treated as the source copy and never
reads or writes a real _local.

    python3 product/user_style.py            # prints her default pack (empty when none is saved)
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHIPPED = os.path.join(HERE, "creative-vault", "user-style.json")


def _root(shipped):
    """product/creative-vault/user-style.json -> the engine folder that owns it."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(shipped))))


def source_copy(shipped=SHIPPED):
    """True in the copy the engine ships from: make-ship.sh is there, and it never ships."""
    return os.path.isfile(os.path.join(_root(shipped), "make-ship.sh"))


def local_path(shipped=SHIPPED):
    return os.path.join(_root(shipped), "_local", "default-pack.json")


def where(shipped=SHIPPED):
    """The file a new default is saved to: _local/default-pack.json in the source copy, else user-style.json."""
    return local_path(shipped) if source_copy(shipped) else shipped


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def default_pack(shipped=SHIPPED):
    """Her saved default style pack, or None when she has not chosen one."""
    if source_copy(shipped):
        name = _read(local_path(shipped)).get("default_pack")
        if name:
            return name
    return _read(shipped).get("default_pack") or None


def set_default_pack(name, shipped=SHIPPED):
    """Save `name` as her default (the caller has already checked the pack exists). Keeps a switch history;
    the same pack twice adds nothing. In the source copy user-style.json is never written."""
    path = where(shipped)
    d = _read(path)
    if path != shipped and "default_pack" not in d:
        d = {"default_pack": _read(shipped).get("default_pack") or None, "history": []}
    if d.get("default_pack") != name:
        d.setdefault("history", []).append(d.get("default_pack"))
        d["default_pack"] = name
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    return name


if __name__ == "__main__":
    print(default_pack(sys.argv[1] if len(sys.argv) > 1 else SHIPPED) or "")
