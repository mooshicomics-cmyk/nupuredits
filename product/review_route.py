#!/usr/bin/env python3
"""review_route.py — which road one reel is on: the visual editor or the original widget. Once a reel is on the
editor, it stays there: the widget builder and the old CapCut builders refuse it, so a build can never drift back
to the other version. Only her own words switch a reel ("the original widget" for this reel).

    python3 product/review_route.py <job>              prints editor / widget / unset
    python3 product/review_route.py <job> editor        lock this reel to the visual editor (visual_editor.py open does it)
    python3 product/review_route.py <job> widget        she asked for the original widget for THIS reel, by name

Stored in projects/<job>/review/route.json (it travels with the reel). No heavy imports: every builder reads it.
"""
import json, os, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUTES = ("editor", "widget")


def _jd(job):
    return job if os.path.isabs(job) and os.path.isdir(job) else os.path.join(ROOT, "projects", os.path.basename(os.path.normpath(job)))


def get(job):
    """editor / widget / unset (a reel that never chose, e.g. one made before the editor existed)."""
    try:
        r = json.load(open(os.path.join(_jd(job), "review", "route.json"), encoding="utf-8")).get("route")
        return r if r in ROUTES else "unset"
    except Exception:
        return "unset"


def set_route(job, route):
    if route not in ROUTES:
        raise ValueError(f"route is editor or widget, not {route!r}")
    d = os.path.join(_jd(job), "review"); os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "route.json"); tmp = p + ".tmp"
    json.dump({"route": route, "at": time.strftime("%Y-%m-%d %H:%M:%S")}, open(tmp, "w", encoding="utf-8"))
    os.replace(tmp, p)


def refuse_if_editor(job, what):
    """The guard every widget-route tool calls. Exits with the way back to her page. With the editor off in this
    engine (product/early_access.py) there is no page to go back to, so every reel takes the widget road."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import early_access
        if not early_access.editor_on():
            return
    except Exception:
        return
    if job and get(job) == "editor" and os.environ.get("REE_EDITOR_FINISH") != "1":   # the Finish tab's export is the editor road
        name = os.path.basename(os.path.normpath(job))
        sys.exit(f"This reel is on the visual editor, so {what} doesn't run for it. Stay on the editor: her page has "
                 f"the cut, the looks, the sound and the export. Open it: python3 product/visual_editor.py open {name}\n"
                 f"Only if she asked for the original widget for this reel, by name: "
                 f"python3 product/review_route.py {name} widget, then run this again.")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); sys.exit(0)
    if len(a) > 1:
        set_route(a[0], a[1]); print(a[1])
    else:
        print(get(a[0]))
