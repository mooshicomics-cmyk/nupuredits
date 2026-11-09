#!/usr/bin/env python3
"""update_signature.py — proves an engine update really came from the engine's publisher.

Every update is signed with the publisher's private key (which never leaves the publisher's computer) and
checked here against the public key pinned below. Three things carry a signature:

  * the online feed (latest.json): which version is newest, which file to fetch, and that file's sha256.
    scripts/apply-update.py checks it BEFORE downloading anything, so the sha256 check on the download is
    then a real authenticity check, not just a corruption check.
  * update.json inside every update package (update.json.sig beside it). update.json lists the sha256 of
    every file the update writes, and the updater checks each one, so a valid manifest signature covers
    the whole package. This is what lets a single update file, emailed or saved by hand, prove itself.
  * the update .zip as a whole, in a detached <zip>.sig beside it.

The signature scheme is Ed25519 (RFC 8032). Verification is written out here in plain Python, standard
library only, so it runs on every interpreter the engine supports (3.8+, Intel Macs on 3.11 included) with
nothing to install. It is the reference algorithm from RFC 8032 section 6, which is slow by crypto standards
(a few hundredths of a second per check) and fine for a handful of checks per update.

Each signed message starts with a fixed label naming what it is, so a signature made for one kind of thing
can never be replayed as another.

Command line (used by .claude/hooks/update-check.sh):
  python3 scripts/update_signature.py feed-summary < latest.json
      exit 0 and print the feed's summary (cleaned: no control characters, capped) when the feed's signature
      is valid; exit 1 and print nothing when it is missing or invalid.
"""
import base64
import hashlib
import json
import sys
import unicodedata

# The publisher's Ed25519 public key(s), hex. An update is genuine when ANY of these signed it, which leaves
# room to add a new key in one release and retire the old one in a later release.
PUBLIC_KEYS = (
    "dc4912c729b79cdbe209caa212015766abb8bd8a678b49a71e94e146bfb0674f",   # primary, generated 2026-10-05
)

SIG_ALG = "ed25519"
FEED_LABEL = b"reels-engine-update-feed/v1\n"
MANIFEST_LABEL = b"reels-engine-update-manifest/v1\n"
ZIP_LABEL = b"reels-engine-update-zip/v1\n"
MANIFEST_SIG_NAME = "update.json.sig"
SUMMARY_CAP = 280

# ── Ed25519 (RFC 8032, section 6 reference implementation) ─────────────────────────────────────────────
_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493


def _inv(x):
    return pow(x, _P - 2, _P)


_D = -121665 * _inv(121666) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _add(a, b):
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    A = (y1 - x1) * (y2 - x2) % _P
    B = (y1 + x1) * (y2 + x2) % _P
    C = 2 * t1 * t2 * _D % _P
    D = 2 * z1 * z2 % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _mul(s, pt):
    q = (0, 1, 1, 0)          # the neutral element
    while s > 0:
        if s & 1:
            q = _add(q, pt)
        pt = _add(pt, pt)
        s >>= 1
    return q


def _equal(a, b):
    x1, y1, z1, _ = a
    x2, y2, z2, _ = b
    return (x1 * z2 - x2 * z1) % _P == 0 and (y1 * z2 - y2 * z1) % _P == 0


def _recover_x(y, sign):
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


_GY = 4 * _inv(5) % _P
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _compress(pt):
    zinv = _inv(pt[2])
    x, y = pt[0] * zinv % _P, pt[1] * zinv % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(s):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def _h(m):
    return int.from_bytes(hashlib.sha512(m).digest(), "little")


def _secret_expand(seed):
    if len(seed) != 32:
        raise ValueError("an Ed25519 private key seed is 32 bytes")
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_from_seed(seed):
    a, _ = _secret_expand(seed)
    return _compress(_mul(a, _G))


def sign(seed, msg):
    """Ed25519 signature (64 bytes) of msg with a 32-byte private seed. Publisher side and tests only: an
    engine never holds a private key."""
    a, prefix = _secret_expand(seed)
    A = _compress(_mul(a, _G))
    r = _h(prefix + msg) % _L
    R = _compress(_mul(r, _G))
    k = _h(R + A + msg) % _L
    s = (r + k * a) % _L
    return R + int.to_bytes(s, 32, "little")


def verify(public, msg, signature):
    """True only when `signature` (64 bytes) is a valid Ed25519 signature of `msg` under `public` (32 bytes)."""
    if len(public) != 32 or len(signature) != 64:
        return False
    A = _decompress(public)
    if A is None:
        return False
    R = _decompress(signature[:32])
    if R is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _L:
        return False
    k = _h(signature[:32] + public + msg) % _L
    return _equal(_mul(s, _G), _add(R, _mul(k, A)))


# ── what gets signed ───────────────────────────────────────────────────────────────────────────────────
def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def feed_message(feed):
    """The exact bytes a feed signature covers: every field of latest.json except the signature itself."""
    body = {k: v for k, v in feed.items() if k not in ("signature", "sig_alg")}
    return FEED_LABEL + _canonical(body)


def manifest_message(manifest_bytes):
    """The exact bytes a package signature covers: update.json as it sits in the package, byte for byte."""
    return MANIFEST_LABEL + manifest_bytes


def zip_message(engine, version, digest):
    return ZIP_LABEL + _canonical({"engine": str(engine), "sha256": str(digest).lower(), "version": str(version)})


def _keys(keys):
    out = []
    for k in (PUBLIC_KEYS if keys is None else keys):
        try:
            raw = bytes.fromhex(k)
        except (ValueError, TypeError):
            continue
        if len(raw) == 32:
            out.append(raw)
    return out


def _check(msg, sig_b64, keys):
    """'' when sig_b64 is a valid signature of msg by a pinned key, else the reason it is not."""
    trusted = _keys(keys)
    if not trusted:
        return "this engine has no update signing key to check against"
    if not sig_b64 or not isinstance(sig_b64, str):
        return "it carries no signature"
    try:
        raw = base64.b64decode(sig_b64.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError):
        return "its signature is not readable"
    if any(verify(k, msg, raw) for k in trusted):
        return ""
    return "its signature does not match the publisher's key"


def check_feed(feed, keys=None):
    """'' when latest.json is signed by the publisher, else the reason it is not."""
    if not isinstance(feed, dict):
        return "it is not an update feed"
    if feed.get("sig_alg") != SIG_ALG:
        return "it carries no signature" if "signature" not in feed else "its signature type is not recognised"
    return _check(feed_message(feed), feed.get("signature"), keys)


def check_manifest(manifest_bytes, sig_text, keys=None):
    """'' when update.json (exact bytes) is signed by the publisher, else the reason it is not."""
    try:
        sig = json.loads(sig_text)
    except (ValueError, TypeError):
        return "its signature file is not readable"
    if not isinstance(sig, dict) or sig.get("sig_alg") != SIG_ALG:
        return "its signature type is not recognised"
    return _check(manifest_message(manifest_bytes), sig.get("signature"), keys)


def check_zip(zip_path, sig_text, keys=None):
    """'' when the detached <zip>.sig proves zip_path is the publisher's file, else the reason it is not."""
    try:
        sig = json.loads(sig_text)
    except (ValueError, TypeError):
        return "its signature file is not readable"
    if not isinstance(sig, dict) or sig.get("sig_alg") != SIG_ALG:
        return "its signature type is not recognised"
    h = hashlib.sha256()
    try:
        with open(zip_path, "rb") as fh:
            for block in iter(lambda: fh.read(65536), b""):
                h.update(block)
    except OSError as e:
        return f"the file could not be read ({e})"
    if h.hexdigest() != str(sig.get("sha256", "")).lower():
        return "the file is not the one its signature was made for"
    return _check(zip_message(sig.get("engine", ""), sig.get("version", ""), h.hexdigest()),
                  sig.get("signature"), keys)


def clean_summary(text, cap=SUMMARY_CAP):
    """A summary safe to show as quoted text: control and formatting characters gone, whitespace collapsed,
    at most `cap` characters."""
    if not isinstance(text, str):
        return ""
    kept = "".join(" " if unicodedata.category(ch).startswith(("C", "Z")) else ch for ch in text)
    kept = " ".join(kept.split())
    if len(kept) > cap:
        kept = kept[:cap - 3].rstrip() + "..."
    return kept


def main(argv):
    if len(argv) >= 2 and argv[1] == "feed-summary":
        try:
            feed = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return 1
        if check_feed(feed):
            return 1
        out = clean_summary(feed.get("summary", ""))
        sys.stdout.buffer.write(out.encode("utf-8"))
        return 0
    print("usage: update_signature.py feed-summary < latest.json", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
