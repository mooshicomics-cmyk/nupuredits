#!/usr/bin/env python3
"""probe.py — the ONE way to ask a video its size.

`ffprobe -show_entries stream=width,height` reports the STORED frame, not the DISPLAYED one. A phone filmed
vertically is usually stored 1920x1080 with a rotation=90 display matrix, so the raw probe says "landscape"
while every player (and ffmpeg itself, during any re-encode) shows it portrait. Vertical phone video is the
main input to this engine, so every intake, planning, and reframe decision goes through here.

    from probe import probe, display_dims
    w, h = display_dims(path)              # what the viewer sees (rotation applied)
    p = probe(path)                        # {"width","height","stored_width","stored_height","rotation","duration","fps"}
"""
import json, subprocess


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,avg_frame_rate:stream_side_data=rotation:stream_tags=rotate:format=duration",
                        "-of", "json", str(path)], capture_output=True, text=True)
    try:
        d = json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        d = {}
    st = (d.get("streams") or [{}])[0]
    sw = int(st.get("width") or 0); sh = int(st.get("height") or 0)
    rot = 0
    for sd in st.get("side_data_list") or []:
        if sd.get("rotation") not in (None, ""):
            try: rot = int(round(float(sd["rotation"]))); break
            except (TypeError, ValueError): pass
    if not rot:
        try: rot = int(round(float((st.get("tags") or {}).get("rotate", 0) or 0)))
        except (TypeError, ValueError): rot = 0
    w, h = (sh, sw) if abs(rot) % 180 == 90 else (sw, sh)
    try: dur = float((d.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError): dur = 0.0
    fps = 0.0
    try:
        n, den = str(st.get("avg_frame_rate", "0/1")).split("/")
        fps = float(n) / float(den) if float(den) else 0.0
    except (ValueError, ZeroDivisionError): pass
    return {"width": w, "height": h, "stored_width": sw, "stored_height": sh, "rotation": rot, "duration": dur, "fps": fps}


def display_dims(path):
    p = probe(path)
    return p["width"], p["height"]


if __name__ == "__main__":
    import sys
    for a in sys.argv[1:]:
        print(a, probe(a))
