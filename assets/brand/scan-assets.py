#!/usr/bin/env python3
"""scan-assets.py — auto-catalog the creator's brand assets so she never has to label them.
Finds every clip/photo under assets/brand/, extracts a thumbnail (video=mid-frame, image=itself),
and tiles a contact sheet per category. Claude then LOOKS at the sheets and writes tags into catalog.md.
Run: python3 assets/brand/scan-assets.py   (re-run whenever she adds media)"""
import os, subprocess, glob
BASE=os.path.dirname(os.path.abspath(__file__)); TH=os.path.join(BASE,"_catalog"); os.makedirs(TH,exist_ok=True)
VID={'.mp4','.mov','.m4v','.webm'}; IMG={'.png','.jpg','.jpeg','.heic','.webp'}
def dur(p):
    try: return float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",p],capture_output=True,text=True).stdout.strip() or 0)
    except: return 0
found=[]
for cat in ["broll","screenshots","products","photos"]:
    d=os.path.join(BASE,cat)
    if not os.path.isdir(d): continue
    files=[f for f in sorted(glob.glob(d+"/*")) if os.path.splitext(f)[1].lower() in VID|IMG]
    for f in files:
        ext=os.path.splitext(f)[1].lower(); name=os.path.splitext(os.path.basename(f))[0]
        thumb=f"{TH}/{cat}__{name}.jpg"
        if ext in VID:
            subprocess.run(["ffmpeg","-y","-ss",str(dur(f)/2),"-i",f,"-frames:v","1","-vf","scale=320:-1",thumb],capture_output=True)
        else:
            subprocess.run(["ffmpeg","-y","-i",f,"-vf","scale=320:-1",thumb],capture_output=True)
        found.append((cat,os.path.basename(f)))
print(f"cataloged {len(found)} assets -> {TH}/")
for c,n in found: print(f"  [{c}] {n}")
