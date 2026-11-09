# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow"]
# ///
"""
vo-build.py — the VOICEOVER REEL BUILDER. One command: VO + b-roll + a shot plan -> finished reel.

This is the "make my voiceover reel" engine. It takes the pieces the rest of the pipeline produced and
assembles the reel in ONE pass (Route A, baked MP4):
  • reframes each chosen b-roll window to 9:16 1080x1920 (scale + center-crop)
  • opens with a gentle hook-burst, then holds one shot per phrase (from the shot plan), each hold
    carrying a gentle Ken Burns move by default (alternating push-in/out; --motion still locks them)
  • lays the VO as the continuous spine + a quiet music bed under it
  • renders captions from the VO's real word timings: KARAOKE BUILD (words appear as spoken, current word
    highlighted) + one full-screen TAKEOVER for the payoff line
  • fonts + case come from the chosen STYLE PACK; accent is the buyer's color OR none (all white)

Ken Burns push-in/out on holds is DEFAULT ON (the format's motion look; --motion still to lock).
NO color grade, NO deflicker, NO hook card, NO fades — locked per the format spec (grade is offered per reel).

Inputs (in projects/<job>/):
  audio/vo.*              the voiceover  (spine)
  vo-grid.json            from vo-cutgrid.py  (words + phrases + timings)
  shot-plan.json          the beat->shot plan (authored after reading broll-candidates.jpg):
      { "burst_stab": 0.5,
        "burst":  [{"path": "...", "in": 34.0}, ...],
        "holds":  [{"path": "...", "in": 14.0, "out": 15.9}, ...],   # in timeline order
        "takeover_from_phrase": -1 }                                  # which phrase is the takeover (default last)

Usage:
  uv run product/vo-build.py --job my-reel --pack Editorial --accent 5B8DEF
  uv run product/vo-build.py --job my-reel --pack Butter --accent none --music path/to/bed.mp3
"""
import argparse, json, os, subprocess, tempfile, sys
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
from PIL import Image, ImageDraw, ImageFont, ImageFilter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H, FPS = 1080, 1920, 30
MAXW = 840   # overwritten from safe_zones once it is imported (see _resolve_frame)
# Caption band centre. Screen-centre is right when the picture is plain b-roll, but it collides with
# the subject's face and with any full-screen graphic shot (a screen demo, a card). "lower" drops the
# band into the clear strip above the platform UI. The safe-zone floor comes from safe_zones (y=1620,
# the creator's locked 300px call), so a 2-line caption centred at 1300 ends at ~1400, well inside.
# Layer 2 comes from safe_zones, never from numbers typed here. This module used to hardcode the band and
# the type sizes, which is the "one agent guesses, every buyer gets a differently wrong reel" failure the
# layout rules exist to stop. (product/reel_layout.py, product/safe_zones.py)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import safe_zones
import learned                                        # preferences the creator has TAUGHT (brand-kit.md Part C)
from video_encoder import pick_encoder
# The same libx264 defaults this format was tuned with on a Mac (preset medium, crf 23); on a Windows box
# with an NVIDIA card the shared encoder picks NVENC instead, which is where the render time actually hurts.
VENC = pick_encoder(vbr="12M", crf=23, preset="medium", hw_on_mac=False)
SAFE_TOP, SAFE_BOT = safe_zones.TOP, safe_zones.BOTTOM
SAFE_L, SAFE_R = safe_zones.LEFT, safe_zones.RIGHT
# A reel can carry a PERSISTENT element the build does not own — a category banner, a running overlay
# composited on afterwards. The caption and takeover layout has no way to see it, so it stacked straight
# through one. --reserve-top hands that height back: everything this build draws starts below it.
reserve_top = 0
CAP_CY = {"center": H // 2, "lower": 1300}
cap_cy = CAP_CY["center"]


def _resolve_frame(band, reserve):
    """Resolve the caption band + type floors from safe_zones for THIS build. Returns the band centre,
    clamped so a caption can never be authored outside the platform's readable box."""
    global MAXW
    MAXW = min(MAXW, SAFE_R - SAFE_L)
    top = SAFE_TOP + max(0, reserve)
    cy = CAP_CY[band]
    return max(top + 80, min(cy, SAFE_BOT - 80))
d0 = ImageDraw.Draw(Image.new("RGBA", (W, H)))


# ---------- fonts / pack ----------
def _system_font(file):
    """A "SYSTEM:<name>" reference as a real file on this machine, or None. Windows has no Helvetica, so
    Arial / Segoe UI are its stand-ins."""
    name = file.split(":", 1)[1]
    _win = os.environ.get("WINDIR", "C:/Windows")
    for p in (f"/System/Library/Fonts/{name.replace(' ','')}.ttc",
              "/System/Library/Fonts/HelveticaNeue.ttc", "/System/Library/Fonts/Helvetica.ttc",
              f"{_win}/Fonts/{name.replace(' ','')}.ttf", f"{_win}/Fonts/arial.ttf", f"{_win}/Fonts/segoeui.ttf"):
        if os.path.exists(p): return p
    return None


def pack_fonts(pack):
    """Resolve (body_font, display_font, takeover_upper) for a style pack: the caption font draws the
    karaoke build, the takeover font draws the takeover.

    Goes through stylepack.element, the resolver every other build uses, so a voiceover reel gets the same
    font the rest of the engine would: the creator's own packs from _local/style-packs.json, a pack face she
    added in CapCut, and the pack's own bundled stand-in when neither is on this machine (stylepack says so
    when it uses one). This used to read the shipped style-packs.json and assets/fonts/ and nothing else. The
    licensed faces are not bundled, so on a buyer's machine Playful found no caption font and stopped with
    "no usable font", a pack she built herself raised a KeyError, and Editorial's takeover quietly became
    its caption font. main() resolves this BEFORE the picture is built, so a pack problem costs a second,
    not a render."""
    import stylepack
    try:
        try:
            el = stylepack.load(pack)["elements"]
        except ValueError as e:
            # Her own pack file will not parse (a hand edit, a write cut off). The shipped packs still work, as
            # they did before this read her packs at all: say so, and resolve from the shipped file alone.
            print(f"[vo] ⚠ {os.path.relpath(stylepack.LOCAL_SPEC, REPO)} will not read ({e}), so only the "
                  f"shipped packs are available for this build.")
            stylepack.LOCAL_SPEC = os.path.join(REPO, "_local", "style-packs.unreadable")   # not there: skipped
            el = stylepack.load(pack)["elements"]
    except KeyError as e:
        sys.exit(f"[vo] ✗ {e.args[0] if e.args else e}")

    def resolve(kind):
        if kind not in el:
            return None
        ref = el[kind].get("file") or ""
        try:
            e = stylepack.element(pack, kind)
        except KeyError:                      # a "SYSTEM:" font the pack never mapped to a file
            e = {}
        found = e.get("file") if e.get("file") and os.path.exists(e["file"]) else None
        if ref.startswith("SYSTEM:") and (not found or e.get("fallback")):
            return _system_font(ref) or found  # this machine's own system face beats a bundled stand-in
        return found

    body = resolve("caption") or resolve("headline")
    disp = resolve("takeover") or body
    upper = el.get("takeover", {}).get("case") == "upper"
    return body, disp, upper


# HDR b-roll (iPhone shoots BT.2020 + HLG/PQ 10-bit) renders WASHED-OUT/flat when treated as SDR.
# Detect it from the stream's real color tags and convert BT.2020->BT.709 SDR before any scale/zoom.
# The detection and the filter live in product/hdr.py, shared with the b-roll hook baker so both convert
# the same footage the same way.
from hdr import HDR2SDR as _HDR2SDR, hdr_kind as _hdr_kind

def _is_hdr(src): return _hdr_kind(src) is not None


def _src_fps(src):
    """A clip's real frame rate: its measured average (a phone records a variable ~30), else its nominal
    rate; None when neither can be read."""
    try:
        out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                       "stream=avg_frame_rate,r_frame_rate", "-of", "default=nw=1", src], text=True)
    except Exception:
        return None
    rates = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    for key in ("avg_frame_rate", "r_frame_rate"):
        num, _, den = rates.get(key, "0/0").partition("/")
        try:
            if float(num) > 0 and float(den or 1) > 0:
                return float(num) / float(den or 1)
        except ValueError:
            pass
    return None

_PQ_WARNED = set()

# ---------- reframe / assemble ----------
def reframe(src, tin, dur, dst, kb=None):
    """Reframe a b-roll window to 9:16 (scale + center-crop). kb adds a gentle Ken Burns
    move over the shot: "in" = slow push-in (1.0 -> 1.06), "out" = slow push-out
    (1.06 -> 1.0), None = static hold (byte-identical to the old behavior). Pre-scales 2x
    before the zoom so the move stays sharp and jitter-free. HDR sources are tone-mapped to
    SDR first (else they render washed-out)."""
    kind = _hdr_kind(src)
    pre = f"{_HDR2SDR}," if kind else ""
    if kind == "pq" and src not in _PQ_WARNED:   # say it once per clip: this toolchain has no true PQ tonemap
        _PQ_WARNED.add(src)
        print(f"[vo] ⚠ {os.path.basename(src)} is PQ / Dolby Vision HDR — converted APPROXIMATELY (this ffmpeg has "
              f"no zscale). HLG clips (the iPhone default) convert correctly; for exact color on this one, "
              f"export it as SDR from the phone.")
    # Fit by aspect: a source at least as wide as 9:16 scales to full height (as before, so those
    # renders are unchanged); a narrower one (a phone screen recording) scales to full width instead,
    # where a height-first scale would leave it too narrow to crop and ffmpeg would refuse it.
    base = (f"{pre}scale=w='if(gte(a\\,{W}/{H})\\,-2\\,{W})':h='if(gte(a\\,{W}/{H})\\,{H}\\,-2)',"
            f"crop={W}:{H}:(iw-{W})/2:(ih-{H})/2")
    if kb:
        frames = max(1, round(dur * FPS)); maxz = 1.06; inc = (maxz - 1.0) / frames
        z = (f"max({maxz}-{inc:.6f}*on,1.0)" if kb == "out" else f"min(1.0+{inc:.6f}*on,{maxz})")
        # zoompan (d=1) turns each INPUT frame into one output frame, so fed a 60 fps clip a 2 s hold played
        # 1 s of it at double speed, and fed 24 fps it played 2.5 s. A clip that is not already ~30 fps is
        # brought to 30 first. One that is (29.97, or a phone's variable ~30) is left exactly as before.
        rate = _src_fps(src)
        resample = f"fps={FPS}," if rate and abs(rate - FPS) > 0.5 else ""
        vf = (f"{base},{resample}scale={W*2}:{H*2},"
              f"zoompan=z='{z}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
              f"setsar=1,format=yuv420p")
    else:
        vf = f"{base},fps={FPS},setsar=1,format=yuv420p"
    subprocess.run(["ffmpeg","-v","error","-ss",f"{tin:.3f}","-i",src,"-t",f"{dur:.3f}",
                    "-vf",vf,"-an","-r",str(FPS),"-y",dst], check=True)


def _clip_dur(path):
    try:
        return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                              "-of", "csv=p=0", path]).strip())
    except Exception:
        return 0.0


def build_picture(plan, tmp, motion="kenburns"):
    segs = []; i = 0
    # PRE-FLIGHT: a shot-plan path that does not exist used to surface as a raw ffmpeg CalledProcessError
    # traceback mid-build. Say which clip is missing, up front.
    shots = list(plan.get("burst", [])) + list(plan["holds"])
    missing = [s["path"] for s in shots if not os.path.exists(s["path"])]
    if missing:
        sys.exit("⛔ shot-plan.json points at clip(s) that do not exist:\n"
                 + "".join(f"   • {m}\n" for m in missing) + "   Fix the paths and re-run.")
    # burst = the rapid hook-burst opener; keep it static (motion there reads as chaos).
    for b in plan.get("burst", []):
        d = f"{tmp}/s{i:03d}.mp4"; reframe(b["path"], b["in"], plan.get("burst_stab", 0.5), d); segs.append(d); i += 1
    # holds = one shot per phrase. DEFAULT: a gentle Ken Burns move, alternating push-in/out
    # for variety; a shot can pin its own via plan "kb": "in"|"out"|"still". motion="still" locks all.
    hi = 0
    for h in plan["holds"]:
        d = f"{tmp}/s{i:03d}.mp4"
        kb = None
        if motion == "kenburns":
            kb = h.get("kb") or ("out" if hi % 2 else "in")
            if kb == "still": kb = None
        want = float(h["out"]) - float(h["in"])
        reframe(h["path"], h["in"], want, d, kb=kb)
        # A hold whose `out` runs past the clip's real end came back SHORT and silent (asked 9s, got 5s
        # measured), so every later shot landed EARLIER than the plan and the VO-timed captions no longer sat
        # on the shots she chose. Hold the last frame for the missing time so the timeline stays on plan.
        got = _clip_dur(d)
        if got and got + 0.08 < want:
            padded = f"{tmp}/s{i:03d}p.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-i", d, "-vf",
                            f"tpad=stop_mode=clone:stop_duration={want - got:.3f}",
                            *VENC, "-r", str(FPS), "-y", padded], check=True)
            print(f"[vo] ⚠ hold {os.path.basename(h['path'])} asks {float(h['in']):.1f}→{float(h['out']):.1f}s but the clip "
                  f"is only {_clip_dur(h['path']):.1f}s long: held its last frame for the missing {want - got:.1f}s so "
                  f"every later shot stays on its planned beat. Fix that `out` in shot-plan.json.")
            d = padded
        segs.append(d); i += 1; hi += 1
    lst = f"{tmp}/list.txt"; open(lst, "w", encoding="utf-8").write("".join(f"file '{s}'\n" for s in segs))
    pic = f"{tmp}/picture.mp4"
    subprocess.run(["ffmpeg","-v","error","-f","concat","-safe","0","-i",lst,
                    *VENC,"-r",str(FPS),"-y",pic], check=True)
    dur = float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",pic]).strip())
    return pic, dur


# ---------- captions (karaoke build + takeover) ----------
TAKEOVER_MAX_WORDS = 7   # past this the one-word-per-line stack shrinks every word below reading size


def caption_lines(grid, takeover_idx, takeover_text=None):
    """Group the VO words into caption lines. Each phrase -> line(s); long phrases chunk to <=6 words.
    Returns list of {words:[(w,start)], end, mode}."""
    phrases = grid["phrases"]; n = len(phrases)
    takeover_idx = n - 1 if takeover_idx in (None, -1) else takeover_idx
    lines = []
    for pi, p in enumerate(phrases):
        ws = [(w["w"], w["a"]) for w in p["words"]]
        is_take = (pi == takeover_idx)
        if is_take and takeover_text:
            # The plan named the payoff fragment. Keep the WORD TIMINGS of the matching tail of the phrase so
            # the takeover still lands on the beat she says it, and drop the run-up words from the card.
            want = [w for w in takeover_text.split()]
            tail = ws[-len(want):] if len(want) <= len(ws) else ws
            ws = [(want[i], tail[i][1]) for i in range(len(want))] if len(want) == len(tail) else \
                 [(w, tail[0][1]) for w in want]
        line_end_default = phrases[pi+1]["words"][0]["a"] if pi+1 < n else (p["b"] + 1.2)
        if is_take or len(ws) <= 6:
            lines.append({"words": ws, "end": line_end_default, "mode": "takeover" if is_take else "build"})
        else:
            for k in range(0, len(ws), 6):
                chunk = ws[k:k+6]
                nxt = ws[k+6][1] if k+6 < len(ws) else line_end_default
                lines.append({"words": chunk, "end": nxt, "mode": "build"})
    return lines


def clean_word(w): return w.strip(",.!?").lower()


def word_layout(text, size, mode, body_font, disp_font, upper):
    if mode == "takeover":
        # The takeover stacks ONE WORD PER LINE, so its height is driven by the word COUNT, not the text
        # width — and it had no height fit at all. A long payoff line (15 words at 150px = 2295px on a
        # 1920 canvas) ran off the top AND bottom of the frame with the middle words the only ones visible.
        # Shrink until the whole stack fits the platform safe band, and centre it in that band, not on the
        # raw canvas — the band is where the viewer can actually read it.
        f = disp_font
        ws = (text.upper() if upper else text).split()
        band_top, band_bot = SAFE_TOP + reserve_top, SAFE_BOT
        band = band_bot - band_top
        s = size
        while True:
            lh = int(s*1.02); hero_h = int(s*1.4*1.02)
            total = lh*(len(ws)-1) + hero_h
            widest = max(d0.textbbox((0,0), w, font=ImageFont.truetype(f, int(s*1.4) if i == len(ws)-1 else s))[2]
                         for i, w in enumerate(ws))
            if (total <= band and widest <= MAXW) or s <= safe_zones.MIN_PX["takeover"]: break
            s -= 4
        base = ImageFont.truetype(f, s); hero = ImageFont.truetype(f, int(s*1.4))
        y0 = band_top + (band - total)//2; out = []
        for i, w in enumerate(ws):
            fo = hero if i == len(ws)-1 else base
            lw = d0.textbbox((0,0), w, font=fo)[2]; out.append((w, W//2-lw//2, y0+i*lh, fo, i == len(ws)-1))
        return out
    s = size
    floor = safe_zones.MIN_PX["karaoke"]
    while s >= floor:
        font = ImageFont.truetype(body_font, s)
        lines, cur = [], ""
        for w in text.split():
            t = (cur+" "+w).strip()
            if d0.textbbox((0,0), t, font=font)[2] <= MAXW or not cur: cur = t
            else: lines.append(cur); cur = w
        if cur: lines.append(cur)
        if len(lines) >= 2 and len(lines[-1].split()) == 1:      # no orphan
            prev = lines[-2].split()
            if len(prev) >= 2: lines[-1] = prev[-1]+" "+lines[-1]; lines[-2] = " ".join(prev[:-1])
        if all(d0.textbbox((0,0), ln, font=font)[2] <= MAXW for ln in lines): break
        s -= 3
    lh = int(s*1.32); y0 = cap_cy - lh*len(lines)//2; out = []
    for li, line in enumerate(lines):
        lw = d0.textbbox((0,0), line, font=font)[2]; cx = W//2 - lw//2; y = y0 + li*lh
        for w in line.split():
            out.append((w, cx, y, font, False)); cx += d0.textbbox((0,0), w+" ", font=font)[2]
    return out


# Caption backing. Her own drafts carry NO stroke and shadow either off or around 17% alpha; engine builds
# had been using ~85% at a 22-24px blur, which reads as a coloured glow behind every word over anything
# flat. "none" is the default because that is the house style. "faint" mirrors the 17% her own drafts use
# and is there for footage bright enough that white-on-white stops reading. An OUTLINE is not an option:
# it was tried as the fix for the glow and rejected too.
CAPTION_SHADOW = "none"
_FAINT = {"alpha": 44, "offset": (3, 4)}      # 44/255 ~= the 0.17 alpha her drafts use


def render_state(words, k, accent, path):
    """Draw one caption frame. Plain text by default: nothing behind the letters."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if CAPTION_SHADOW == "faint":
        dx, dy = _FAINT["offset"]
        for (w, x, y, font, hero) in words[:k]:
            d.text((x + dx, y + dy), w, font=font, fill=(0, 0, 0, _FAINT["alpha"]))
    for j, (w, x, y, font, hero) in enumerate(words[:k]):
        col = (accent if accent else (255, 255, 255, 255)) if (j == k - 1 or hero) else (255, 255, 255, 255)
        d.text((x, y), w, font=font, fill=col)
    img.save(path)


def build_captions(grid, pic, dur, pack, accent, takeover_idx, tmp, takeover_text=None, fonts=None):
    body_font, disp_font, upper = fonts or pack_fonts(pack)
    if not body_font: sys.exit(f"no usable font for pack {pack}")
    lines = caption_lines(grid, takeover_idx, takeover_text)
    take = next((l for l in lines if l["mode"] == "takeover"), None)
    if take and len(take["words"]) > TAKEOVER_MAX_WORDS:
        print(f"[vo] ⚠ TAKEOVER IS {len(take['words'])} WORDS: \"{' '.join(w for w,_ in take['words'])}\"\n"
              f"      It stacks one word per line, so fitting that many inside the safe band shrinks every word\n"
              f"      below reading size. A takeover is the payoff FRAGMENT, not the sentence. Set\n"
              f'      "takeover_text": "<the few words worth screenshotting>" in shot-plan.json.')
    states = []; si = 0
    # floors from safe_zones.MIN_PX (the in-feed minimums), never a magic px typed here
    B_SIZE = max(76, safe_zones.MIN_PX["karaoke"])
    T_SIZE = max(150, safe_zones.MIN_PX["takeover"])
    for ln in lines:
        text = " ".join(clean_word(w) for w,_ in ln["words"])
        size = T_SIZE if ln["mode"] == "takeover" else B_SIZE
        words = word_layout(text, size, ln["mode"], body_font, disp_font, upper)
        starts = [t for _,t in ln["words"]]; nwd = len(words)
        # if layout split a build line into fewer visual tokens than words (wrap), map by index safely
        m = min(nwd, len(starts))
        for k in range(1, m+1):
            a = starts[k-1]; b = starts[k] if k < m else ln["end"]
            p = f"{tmp}/c{si:04d}.png"; render_state(words, k, accent, p); states.append((p, round(a,3), round(b,3))); si += 1
    # ONE transparent caption track, then ONE overlay.
    # The old path opened a separate ffmpeg INPUT per caption state and chained an overlay filter for each.
    # On a short VO that worked; past roughly 30s of speech the karaoke build produces 300+ states and ffmpeg
    # dies with "pthread_create() failed: Resource temporarily unavailable" — it cannot spawn a decoder thread
    # per input. Building the states into a single alpha filmstrip with the concat demuxer is O(1) inputs, so
    # it scales to any VO length, and lossless qtrle means no generation loss from an intermediate re-encode.
    blank = f"{tmp}/c_blank.png"
    Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(blank)
    strip, t = [], 0.0
    for p, a, b in states:
        if a - t > 0.001: strip.append((blank, a - t))         # hole between states = transparent
        strip.append((p, max(0.001, b - a))); t = b
    if dur - t > 0.001: strip.append((blank, dur - t))
    lst = f"{tmp}/caps.txt"
    with open(lst, "w", encoding="utf-8") as fh:
        for p, d in strip: fh.write(f"file '{p}'\nduration {d:.4f}\n")
        fh.write(f"file '{strip[-1][0]}'\n")
    track = f"{tmp}/captrack.mov"
    subprocess.run(["ffmpeg","-v","error","-f","concat","-safe","0","-i",lst,
                    "-c:v","qtrle","-pix_fmt","argb","-r",str(FPS),"-y",track], check=True)
    capd = f"{tmp}/captioned.mp4"
    subprocess.run(["ffmpeg","-v","error","-i",pic,"-i",track,
                    "-filter_complex","[0:v][1:v]overlay=0:0:shortest=0[v]","-map","[v]",
                    *VENC,"-r",str(FPS),"-y", capd], check=True)
    return capd, len(states)


# ---------- audio mux ----------
def resolve_music(music, jd):
    """The music bed as a real file, or None when none was asked for.

    A --music that does not resolve used to fall through to the voice-only mux without a word, so a reel
    shipped with no bed and nobody could tell why. Now a relative path is tried from where the build ran,
    then from the job folder and its audio/, and a path that still resolves to nothing stops the build."""
    if not music:
        return None
    for cand in (music, os.path.join(jd, music), os.path.join(jd, "audio", music),
                 os.path.join(jd, "audio", os.path.basename(music))):
        if os.path.isfile(cand):
            return os.path.abspath(cand)
    sys.exit(f"[vo] ✗ music track not found: {music}\n"
             f"     Looked where the build ran, in {jd}, and in {jd}/audio/. Nothing was built. Check the name "
             f"(ls {jd}/audio/) and run the same command again.")


def mux(capd, vo, music, dur, out):
    if music and os.path.exists(music):
        # BED LEVEL via the shared module — a hardcoded multiplier (this was 0.15) is the same silent bug
        # the SFX had: it means nothing without knowing the bed's own level. sfx music must auto level
        import sys as _sys, os as _os
        _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
        import audio_levels
        _bg = audio_levels.bed_gain_for(music, vo)                 # the north star: 15 LU under her voice
        audio_levels.report([{"file": music, "gain_db": _bg, "how": "auto"}], prefix="[vo]")
        # duration=longest, not first: the picture can run up to a second past the last word, and ending the
        # mix with the voice cut the bed dead there (and its fade-out with it). -t still ends the reel.
        fc = (f"[1:a]volume=1.0[vo];[2:a]volume={_bg:.1f}dB,afade=t=out:st={max(0,dur-1.5):.2f}:d=1.4[bed];"
              f"[vo][bed]amix=inputs=2:normalize=0:duration=longest[a]")
        subprocess.run(["ffmpeg","-v","error","-i",capd,"-i",vo,"-stream_loop","-1","-i",music,
                        "-filter_complex",fc,"-map","0:v","-map","[a]","-map_chapters","-1","-t",f"{dur:.2f}",
                        "-c:v","copy","-c:a","aac","-b:a","192k","-y",out], check=True)
    else:
        subprocess.run(["ffmpeg","-v","error","-i",capd,"-i",vo,"-map","0:v","-map","1:a","-t",f"{dur:.2f}",
                        "-c:v","copy","-c:a","aac","-b:a","192k","-y",out], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--pack", default="Editorial")
    ap.add_argument("--accent", default="none")   # hex (5B8DEF) or "none"
    ap.add_argument("--pace", default="emotional", choices=["punchy","emotional"])  # register -> pacing
    ap.add_argument("--motion", default="kenburns", choices=["kenburns","still"])   # holds MOVE (default, gentle Ken Burns) vs locked still
    ap.add_argument("--music", default=None)
    ap.add_argument("--caption-shadow", default="none", choices=["none", "faint"],
                    help="backing behind caption text: none (house style) or faint (a 17%% drop, for footage bright enough that white stops reading)")
    ap.add_argument("--reserve-top", type=int, default=0,
                    help="px of the top safe zone already occupied by a persistent overlay this build does "
                         "not draw (a banner composited on afterwards); captions + takeover start below it")
    ap.add_argument("--caption-band", default="center", choices=["center","lower"],
                    help="center = screen centre (plain b-roll); lower = clear strip above the platform UI "
                         "(use when shots carry their own full-screen graphics)")
    args = ap.parse_args()
    learned.context_for_build("voiceover", pack=getattr(args, "pack", None))   # so scoped preferences can match

    jd = f"{REPO}/projects/{args.job}"
    music = resolve_music(args.music, jd)   # before the slow steps: a bad path fails in a second, not after the render
    # prefer the spliced clean VO (after rough-cut) when present, else the raw recording
    grid = json.load(open(f"{jd}/vo-grid.clean.json" if os.path.exists(f"{jd}/vo-grid.clean.json")
                          else f"{jd}/vo-grid.json", encoding="utf-8"))
    global cap_cy, reserve_top, CAPTION_SHADOW
    CAPTION_SHADOW = args.caption_shadow
    reserve_top = args.reserve_top
    cap_cy = _resolve_frame(args.caption_band, reserve_top)
    plan = json.load(open(f"{jd}/shot-plan.json", encoding="utf-8"))
    vo = f"{jd}/audio/vo.clean.wav" if os.path.exists(f"{jd}/audio/vo.clean.wav") else \
         next((f"{jd}/audio/vo.{e}" for e in ("m4a","wav","mp3","aac","mov","mp4","caf")
               if os.path.exists(f"{jd}/audio/vo.{e}")), None)
    if not vo: sys.exit(f"no VO audio in {jd}/audio/")
    fonts = pack_fonts(args.pack)     # before the slow steps: a pack with no usable font fails now, not after the render
    if not fonts[0]: sys.exit(f"no usable font for pack {args.pack}")
    acc = None if args.accent.strip().lower() in ("none","off","") else \
          tuple(int(args.accent.lstrip('#')[i:i+2],16) for i in (0,2,4)) + (255,)

    # register -> pacing: punchy = sharper burst; emotional = gentler. (Inter-line VO gaps are handled
    # upstream at the splice; here pace sets the burst feel when the plan doesn't override burst_stab.)
    plan.setdefault("burst_stab", 0.35 if args.pace == "punchy" else 0.55)

    tmp = tempfile.mkdtemp()
    print(f"[1/3] reframe + assemble b-roll ({args.pace} pace, motion={args.motion}) ...")
    pic, dur = build_picture(plan, tmp, motion=args.motion)
    # GUARD: never silently truncate the voiceover. If the assembled b-roll picture is shorter than the VO,
    # freeze the last shot to cover the remaining speech (and SAY SO) — the old `min(dur, ...)` mux would have
    # cut the tail of her VO off with no warning. This turns silent content loss into a visible, safe outcome.
    try:
        vo_dur = float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", vo]).strip())
    except Exception:
        vo_dur = float(grid.get("duration", dur))
    if dur < vo_dur - 0.25:
        ext = f"{tmp}/picture_ext.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-i", pic,
                        "-vf", f"tpad=stop_mode=clone:stop_duration={vo_dur - dur:.2f}",
                        *VENC, "-r", str(FPS), "-y", ext], check=True)
        print(f"[vo] ⚠ b-roll picture ({dur:.1f}s) is shorter than the voiceover ({vo_dur:.1f}s) — froze the "
              f"last shot to cover the tail (+{vo_dur - dur:.1f}s) so NO speech is dropped. Add more b-roll "
              f"holds to shot-plan.json to fill that time with real footage instead.")
        pic, dur = ext, vo_dur
    print(f"[2/3] captions ({args.pack} pack, accent={'none' if not acc else args.accent}) ...")
    capd, nstates = build_captions(grid, pic, dur, args.pack, acc, plan.get("takeover_from_phrase", -1), tmp,
                                   plan.get("takeover_text"), fonts=fonts)
    print(f"[3/3] lay VO + music, finish ...")
    os.makedirs(f"{jd}/outputs", exist_ok=True)
    out = f"{jd}/outputs/{args.job}.vo.mp4"
    mux(capd, vo, music, min(dur, grid['duration']+1.0), out)
    print(f"\n✅ voiceover reel -> projects/{args.job}/outputs/{args.job}.vo.mp4  "
          f"({dur:.1f}s, {args.pack} pack, {nstates} caption states)")
    if music:
        print(f"[vo] music bed: {os.path.basename(music)}")
    else:
        print("[vo] no music bed on this one: voice only, as asked. To add one, generate options with "
              f"`python3 product/gen-music.py {args.job}` or drop a track in projects/{args.job}/audio/, "
              "then rebuild with --music <track>.")
    for _ln in learned.report():                      # what came from her saved preferences
        print(_ln)


if __name__ == "__main__":
    main()
