#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-python-headless", "numpy", "numpy<2; sys_platform == 'darwin' and platform_machine == 'x86_64'"]   # Intel Macs on macOS 11/12 only get OpenCV built for numpy 1
# ///
"""hook-burst.py — a ~3s rapid-fire b-roll OPENER for a reel: N cuts x ~0.1s, each the best IN-FRAME
moment of a clip (YuNet face detection: on-camera, facing, sharp). A punchy "you, real life" cold open
that front-loads energy before the reel settles into the talking head.

DELIVERY = OVERLAY, never a main-track replacement. The burst .mp4 is layered on a CapCut OVERLAY track at
time 0 (exactly like an animated-text .mov): it plays ON TOP for the opening ~2-3s, then ends and the
creator's untouched talking-head footage carries on. NEVER splice it into / replace the main footage track.

Portable engine tool — POINTS AT ANY creator's b-roll folder (auto-discovers every video in it); never
hardcodes a person, path, or clip list. Framing is rotation-safe COVER-crop to 1080x1920 (no squash). No audio.

COLOR (the "washed out" fix): a creator's b-roll is a MIX — HLG HDR (bt2020, transfer arib-std-b67, 10-bit)
plus full-range SDR (yuvj420p). One reframe washes whichever doesn't match. So it converts PER CLIP
(`colormatrix=bt2020:bt709` for HDR, nothing for SDR) and tags output bt709. This ffmpeg has no
zscale/libplacebo (no true tonemap) but HLG is SDR-compatible, so saturation is preserved (verified).

REMEMBERS what it learns: a per-clip face index (`.broll-face-index.json` in the b-roll folder, plus a
readable `BROLL-FACE-INDEX.md`) caches each clip's best on-camera moments + scores, keyed by file mtime.
So the slow face-scan happens ONCE per clip ever; later bursts reuse it and are near-instant. Frame grabs
run in parallel, so even the first (cold) scan is fast.

usage:
  uv run product/hook-burst.py <job_dir> [--broll DIR] [--target N] [--slice S] [--seconds S] [--reindex]

Run it with `uv run`: the header above brings OpenCV (the face detector) and numpy. Plain python3 has
neither unless someone installed them by hand, and setup does not.

b-roll resolution (first that exists) unless --broll: <job_dir>/broll -> <engine>/assets/broll -> <engine>/broll
"""
import os, sys, json, math, argparse, subprocess
import concurrent.futures as cf
# OpenCV 5 prints a "Targets are not supported" WARN line when the face detector loads; it is not a
# problem, so keep it off the creator's screen (errors still print). Must be set before the import.
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
import cv2, numpy as np

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VID_EXT = (".mov", ".mp4", ".m4v", ".avi", ".mkv", ".hevc")
FF, FFP = "ffmpeg", "ffprobe"
# COLOR (fixes the "washed out" clips): a creator's b-roll is a MIX — HLG HDR (bt2020, color_transfer
# arib-std-b67), 10-bit limited, and 8-bit FULL-range SDR (yuvj420p). A single reframe washes whichever
# doesn't match. So convert PER CLIP: read its real matrix + range and let swscale normalize each to
# bt709 SDR limited (ffmpeg 8.x swscale does bt2020->bt709; HLG is SDR-compatible so no true tonemap is
# needed — verified saturation preserved on both HDR and full-range SDR clips).
CLR_TAGS = ["-color_range","tv","-colorspace","bt709","-color_primaries","bt709","-color_trc","bt709"]

def color_reframe(p):
    info = subprocess.run([FFP,"-v","error","-select_streams","v:0","-show_entries",
                           "stream=color_space,color_range","-of","csv=p=0",p],
                          capture_output=True, text=True).stdout.strip().split(",")
    cs = info[0] if info and info[0] else "bt709"
    cr = info[1] if len(info) > 1 else ""
    # HDR/bt2020 clips get a matrix convert to bt709 (colormatrix as its own filter — combining it into
    # scale conflicts with force_original_aspect_ratio in this ffmpeg). SDR clips need none.
    pre = "colormatrix=bt2020:bt709," if cs.startswith("bt2020") else ""
    return pre + "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,format=yuv420p"
CACHE_MOMENTS = 6          # cache up to this many best moments per clip (serves future bursts of any size)
INDEX_JSON = ".broll-face-index.json"

def dur(p):
    r = subprocess.run([FFP,"-v","error","-show_entries","format=duration","-of","csv=p=0",p],
                       capture_output=True, text=True).stdout.strip()
    try: return float(r)
    except: return 0.0

PNG_SIG = b"\x89PNG\r\n\x1a\n"

def grab(p, t):
    r = subprocess.run([FF,"-v","error","-ss",f"{t:.3f}","-i",p,"-frames:v","1",
                        "-f","image2pipe","-vcodec","png","-"], capture_output=True)
    return cv2.imdecode(np.frombuffer(r.stdout, np.uint8), cv2.IMREAD_COLOR) if r.stdout else None

def sample_frames(p, a, b, step, downscale=640):
    """Extract frames every `step`s across [a,b] in ONE ffmpeg decode pass (far faster than N seeks).
    Downscaled for detection speed. Returns [(t, img), ...]. Splits the concatenated PNG stream."""
    fps = 1.0 / step
    r = subprocess.run([FF,"-v","error","-ss",f"{a:.2f}","-to",f"{b:.2f}","-i",p,
                        "-vf",f"fps={fps},scale={downscale}:-2","-f","image2pipe","-vcodec","png","-"],
                       capture_output=True)
    if not r.stdout: return []
    chunks = r.stdout.split(PNG_SIG)
    out = []
    for i, ch in enumerate(chunks[1:]):
        img = cv2.imdecode(np.frombuffer(PNG_SIG+ch, np.uint8), cv2.IMREAD_COLOR)
        if img is not None: out.append((round(a + i/fps + 0.5/fps, 2), img))
    return out

def score(det, img, conf_min, minfrac):
    h, w = img.shape[:2]; det.setInputSize((w, h))
    _, faces = det.detect(img)
    if faces is None or len(faces) == 0: return None
    f = max(faces, key=lambda r: r[2]*r[3]); x,y,fw,fh = f[:4]; conf = float(f[-1])
    if conf < conf_min or fh/h < minfrac: return None
    reye, leye, nose = (f[4],f[5]),(f[6],f[7]),(f[8],f[9])
    facing = max(0.0, 1.0 - abs(reye[1]-leye[1])/max(1.0,fw)*4 - abs(nose[0]-(reye[0]+leye[0])/2)/max(1.0,fw)*3)
    patch = img[max(0,int(y)):int(y+fh), max(0,int(x)):int(x+fw)]
    sharp = cv2.Laplacian(cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var() if patch.size else 0
    return float(conf + min((fh/h)/0.25,1.0)*1.5 + min(sharp/400.0,1.0) + facing*1.2)

def scan(det, path, a, b, k, step, mingap, conf_min, minfrac):
    scored = []
    for t, img in sample_frames(path, a, b, step):         # ONE decode pass per clip
        s = score(det, img, conf_min, minfrac)
        if s is not None: scored.append((round(s,2), t))
    scored.sort(reverse=True)
    picks = []
    for s, t in scored:
        if all(abs(t-pt) >= mingap for _, pt in picks): picks.append((s, t))
        if len(picks) >= k: break
    return picks

def find_broll(job_dir, cli):
    if cli: return os.path.abspath(os.path.expanduser(cli))
    for c in (os.path.join(job_dir,"broll"), os.path.join(ENGINE,"assets","broll"), os.path.join(ENGINE,"broll")):
        if os.path.isdir(c): return c
    return None

def write_md(broll, index):
    rows = []
    for rel, e in sorted(index.items()):
        ms = e.get("moments", [])
        if not ms: continue
        cat = rel.split(os.sep)[0] if os.sep in rel else "-"
        best = ms[0]
        rows.append((rel, cat, best[1], best[0], len(ms)))
    rows.sort(key=lambda r: -r[3])
    with open(os.path.join(broll, "BROLL-FACE-INDEX.md"), "w", encoding="utf-8") as f:
        f.write("# B-roll face index\n\n_Auto-built by hook-burst.py. Each clip's best on-camera moments "
                "(the frames where you're facing the camera, sharp, well-framed), cached so picking is "
                "instant next time. Higher score = stronger moment._\n\n")
        f.write("| clip | category | best moment | score | good moments |\n|---|---|---|---|---|\n")
        for rel, cat, t, s, n in rows:
            f.write(f"| {rel} | {cat} | {t:.1f}s | {s:.1f} | {n} |\n")
        weak = [rel for rel, e in index.items() if not e.get("moments")]
        if weak:
            f.write("\n**No clean on-camera moment found** (skipped in bursts): " + ", ".join(sorted(weak)) + "\n")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job_dir")
    ap.add_argument("--broll", default=None)
    ap.add_argument("--target", type=int, default=30)
    ap.add_argument("--slice", type=float, default=0.10)
    ap.add_argument("--seconds", type=float, default=None)
    ap.add_argument("--step", type=float, default=1.5)
    ap.add_argument("--mingap", type=float, default=2.5)
    ap.add_argument("--conf", type=float, default=0.60)
    ap.add_argument("--minfrac", type=float, default=0.05)
    ap.add_argument("--reindex", action="store_true", help="ignore the cache and re-scan every clip")
    ap.add_argument("--model", default=os.path.join(ENGINE,"assets","models","face_detection_yunet_2023mar.onnx"))
    a = ap.parse_args()

    job_dir = os.path.abspath(os.path.expanduser(a.job_dir))
    broll = find_broll(job_dir, a.broll)
    if not broll or not os.path.isdir(broll):
        sys.exit("no b-roll folder. Point me at yours:  uv run product/hook-burst.py <job> --broll /path/to/your/broll")
    if not os.path.exists(a.model): sys.exit(f"YuNet model missing: {a.model}")
    target = max(1, int(round(a.seconds/a.slice))) if a.seconds else a.target
    OUT = os.path.join(job_dir, "assets"); os.makedirs(OUT, exist_ok=True)

    clips = []
    for root,_,files in os.walk(broll):
        for fn in sorted(files):
            if fn.lower().endswith(VID_EXT) and not fn.startswith("."): clips.append(os.path.join(root, fn))
    if not clips: sys.exit(f"no video files in {broll}")

    index = {}
    ip = os.path.join(broll, INDEX_JSON)
    if not a.reindex and os.path.exists(ip):
        try: index = json.load(open(ip, encoding="utf-8"))
        except: index = {}
    det = cv2.FaceDetectorYN.create(a.model, "", (320,320), a.conf, 0.3, 5000)
    k = 1 if len(clips) >= target else math.ceil(target/len(clips))
    cache_k = max(k, CACHE_MOMENTS)

    print(f"b-roll: {broll}  ({len(clips)} clips)  ->  target {target} cuts x {a.slice}s")
    per_clip = []; scanned = 0; reused = 0
    for p in clips:
        rel = os.path.relpath(p, broll); st = round(os.path.getmtime(p), 1); e = index.get(rel)
        if e and not a.reindex and abs(e.get("mtime",0)-st) < 1 and "moments" in e:
            ms_all = [(s,t) for s,t in e["moments"]]; reused += 1
        else:
            d = dur(p)
            a0 = min(0.5, d*0.1); b0 = min(max(0.6, d-0.5), a0+90.0)   # scan up to first ~90s of a clip
            ms_all = scan(det, p, a0, b0, cache_k, a.step, a.mingap, a.conf, a.minfrac) if d>=0.6 else []
            index[rel] = {"mtime": st, "dur": round(d,2), "moments": [[s,t] for s,t in ms_all]}
            scanned += 1
            print(f"  scan {rel:46} {len(ms_all)} moment(s)")
        if ms_all: per_clip.append((p, ms_all[:k]))
    json.dump(index, open(ip,"w", encoding="utf-8"), indent=1); write_md(broll, index)
    print(f"index: {scanned} scanned, {reused} reused from cache -> {ip}")
    if not per_clip: sys.exit("no in-frame moments in any clip (is the creator on camera in the b-roll?)")

    per_clip.sort(key=lambda cm: -max(s for s,_ in cm[1]))
    pools = [[(p,t) for _,t in ms] for p,ms in per_clip]; order = []
    while any(pools):
        for pool in pools:
            if pool: order.append(pool.pop(0))
    order = order[:target]
    print(f"{len(order)} cuts -> {len(order)*a.slice:.1f}s")

    slices = []
    for i,(p,t) in enumerate(order):
        outp = os.path.join(OUT, f"_s{i:03d}.mp4")
        subprocess.run([FF,"-y","-v","error","-ss",f"{max(0,t-a.slice/2):.3f}","-i",p,
                        "-t",f"{a.slice:.3f}","-vf",color_reframe(p)+",fps=30","-an",
                        "-c:v","libx264","-preset","veryfast","-pix_fmt","yuv420p",*CLR_TAGS,outp]); slices.append(outp)
    lst = os.path.join(OUT,"_concat.txt"); open(lst,"w", encoding="utf-8").write("".join(f"file '{os.path.basename(s)}'\n" for s in slices))
    burst = os.path.join(OUT,"hook-burst.mp4")
    subprocess.run([FF,"-y","-v","error","-f","concat","-safe","0","-i",lst,"-c","copy",burst], cwd=OUT)

    tiles = []
    for p,t in order:
        img = grab(p,t)
        if img is None: continue
        h,w = img.shape[:2]; s = max(1080/w,1920/h); img = cv2.resize(img,(int(w*s),int(h*s)))
        rw,rh = img.shape[1],img.shape[0]; x0=(rw-1080)//2; y0=(rh-1920)//2; img = img[max(0,y0):y0+1920, max(0,x0):x0+1080]
        tiles.append(cv2.copyMakeBorder(cv2.resize(img,(108,192)),2,2,2,2,cv2.BORDER_CONSTANT))
    if tiles:
        while len(tiles)%6: tiles.append(np.zeros_like(tiles[0]))
        cv2.imwrite(os.path.join(OUT,"hook-burst-picks.jpg"),
                    np.vstack([np.hstack(tiles[i:i+6]) for i in range(0,len(tiles),6)]))
    for s in slices: os.remove(s)
    os.remove(lst)
    json.dump([{"clip": os.path.relpath(p,broll), "t": t} for p,t in order], open(os.path.join(OUT,"hook-burst.json"),"w", encoding="utf-8"), indent=2)
    print(f"BURST: {burst} ({dur(burst):.2f}s, {len(order)} cuts) | picks sheet: {OUT}/hook-burst-picks.jpg")

if __name__ == "__main__": main()
