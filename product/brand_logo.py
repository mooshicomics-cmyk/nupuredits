#!/usr/bin/env python3
"""brand_logo.py — resolve a REAL third-party brand's official mark + real color, live, at build
time. For a card/graphic that names or depicts an actual outside brand (an app, a platform, a
tool) — the "borrowed palette" exception in CLAUDE.md's Rules: that one element gets the brand's
own real color, sampled from the actual asset, never guessed from memory or forced into the
buyer's style pack.

NOTHING IS BUNDLED OR REDISTRIBUTED. Every mark is fetched live from a public source at the moment
a build actually needs it — the same pattern as a CDN dependency, not a stock-asset library shipped
inside the product. This sidesteps the redistribution question entirely: nothing of a third party's
ships in the buyer's copy of the engine, a specific brand's mark is pulled fresh only when a build
specifically asks for it.

Cascade (each tier tried in order; first hit wins):
  1. simple-icons — an open-source (CC0-licensed icon set) MIT-licensed project's monochrome
     official brand glyphs, served from a pinned jsDelivr CDN build for determinism. Covers
     thousands of consumer/tech brands. Also the SOURCE of the official brand hex color — simple-
     icons ships each icon's real brand color as data, which is exactly what "sampled from the
     actual asset, never guessed" needs.
  2. favicon fallback — any domain's own favicon via a public favicon service, for a brand simple-
     icons doesn't cover. Lower quality (a small raster icon, no color data), but universal: works
     for literally any domain name.
  3. miss — plain failure, said out loud. Never fabricate a placeholder logo or a guessed color.

Usage:
  python3 product/brand_logo.py instagram --out /tmp/instagram.svg
      → downloads the mark, prints its official hex color
  python3 product/brand_logo.py somenichetool --out /tmp/x.png
      → simple-icons miss, falls back to a favicon
"""
import argparse, json, os, re, sys, urllib.request, urllib.error
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

SIMPLE_ICONS_VERSION = "13.16.0"   # pinned, like every other CDN dependency this engine uses —
                                    # deliberate version bumps only, never float to latest
SIMPLE_ICONS_CDN = f"https://cdn.jsdelivr.net/npm/simple-icons@{SIMPLE_ICONS_VERSION}/icons"
SIMPLE_ICONS_DATA = f"https://cdn.jsdelivr.net/npm/simple-icons@{SIMPLE_ICONS_VERSION}/_data/simple-icons.json"
FAVICON_SERVICE = "https://icons.duckduckgo.com/ip3/{domain}.ico"
TIMEOUT = 10

# A handful of common brand-name -> simple-icons slug mismatches (the library's own slug rules
# strip spaces/punctuation, which occasionally doesn't match how people actually say a brand name).
_SLUG_ALIASES = {
    "nextjs": "nextdotjs", "next.js": "nextdotjs", "next": "nextdotjs",
    "x": "x", "twitter": "x",
    "chatgpt": "openai", "capcut": "capcut",
}


def _slugify(name):
    n = name.strip().lower()
    n = _SLUG_ALIASES.get(n, n)
    return re.sub(r"[^a-z0-9]", "", n)


def _sniff_image_ext(data):
    """Real format from magic bytes, not a filename or a Content-Type header (the favicon
    service's header isn't always trustworthy). Returns None for an unrecognized format —
    the caller keeps the originally-requested extension rather than guessing further."""
    if data[:4] == b"\x00\x00\x01\x00":
        return ".ico"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:2] == b"\xff\xd8":
        return ".jpg"
    if data[:4] in (b"GIF8",):
        return ".gif"
    return None


def _fetch(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": "ai-edit-engine/brand_logo.py"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def resolve(name, out_path):
    """Returns a dict: {ok, tier, path, hex_color, source} or {ok: False, tried: [...]}.
    hex_color is only ever populated from real data (simple-icons' own metadata) — a favicon-tier
    hit or a miss NEVER fabricates a color."""
    slug = _slugify(name)
    tried = []

    # Tier 1: simple-icons — monochrome SVG + the brand's real official hex color
    try:
        svg = _fetch(f"{SIMPLE_ICONS_CDN}/{slug}.svg")
        hexcolor = None
        try:
            data = json.loads(_fetch(SIMPLE_ICONS_DATA))
            for icon in data.get("icons", []):
                if _slugify(icon.get("title", "")) == slug or icon.get("slug") == slug:
                    hexcolor = "#" + icon.get("hex", "").upper()
                    break
        except Exception:
            pass   # SVG resolved even if the color-data fetch failed — still a real, usable mark
        with open(out_path, "wb") as f:
            f.write(svg)
        return {"ok": True, "tier": "simple-icons", "path": out_path, "hex_color": hexcolor,
                "source": f"{SIMPLE_ICONS_CDN}/{slug}.svg"}
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        tried.append(f"simple-icons ({slug}): {e}")

    # Tier 2: favicon — universal fallback, any domain, no color data
    domain = re.sub(r"^www\.", "", name.strip().lower())
    if "." not in domain:
        domain = f"{domain}.com"   # best-effort guess only when no domain was given at all
    try:
        img = _fetch(FAVICON_SERVICE.format(domain=domain))
        if len(img) < 200:   # a near-empty response is the service's own "no favicon" placeholder
            raise ValueError("favicon service returned an empty/placeholder image")
        # The service can return .ico OR .png depending on the domain — writing raw bytes to
        # whatever extension the caller asked for (e.g. --out logo.svg) silently mislabels the
        # file, which breaks anything downstream that trusts the extension over the content.
        # Sniff the real format and correct the path instead of lying about it.
        real_ext = _sniff_image_ext(img)
        fixed_path = out_path
        if real_ext and not out_path.lower().endswith(real_ext):
            fixed_path = os.path.splitext(out_path)[0] + real_ext
        with open(fixed_path, "wb") as f:
            f.write(img)
        result = {"ok": True, "tier": "favicon", "path": fixed_path, "hex_color": None,
                  "source": FAVICON_SERVICE.format(domain=domain),
                  "note": "no official color data at this tier — sample the actual downloaded "
                          "image if a color is needed, never guess one"}
        if fixed_path != out_path:
            result["note"] += f" (also: requested {out_path}, but the real format is " \
                               f"{real_ext or 'unknown'} — wrote {fixed_path} instead of " \
                               f"mislabeling the file)"
        return result
    except Exception as e:
        tried.append(f"favicon ({domain}): {e}")

    return {"ok": False, "tried": tried}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("brand", help="brand name or domain, e.g. instagram / notion.so")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    r = resolve(a.brand, a.out)
    if r["ok"]:
        print(f"[brand_logo] ✓ {a.brand} → {r['tier']} → {r['path']}")
        if r.get("hex_color"):
            print(f"[brand_logo]   official color: {r['hex_color']}")
        else:
            print(f"[brand_logo]   no official color data at this tier — do not guess one; "
                  f"sample the downloaded asset directly if a color is needed")
        if r.get("note") and "requested" in r["note"]:
            print(f"[brand_logo]   note: {r['note']}")
    else:
        print(f"[brand_logo] ✗ could not resolve '{a.brand}':")
        for t in r["tried"]:
            print(f"    {t}")
        sys.exit(1)
