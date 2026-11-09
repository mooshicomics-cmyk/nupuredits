#!/usr/bin/env python3
"""transcript-cut.py — TRANSCRIPT-DRIVEN rough cut (the clean way). Instead of cutting on loudness dips
(which leaves retakes in and chops mid-phrase), this reads the WhisperX words as SENTENCES, drops every
duplicate take / false-start / filler-only fragment (keeps the LAST clean take), and keeps each surviving
sentence from its first word's onset to its last word's offset. Inter-sentence dead air collapses to a
clean J-cut; intra-sentence rhythm is preserved. No ellipsis/silence segments, no mid-word cuts.

usage: transcript-cut.py <job> [--clip <name>] [--print]
  <job> is a job name, projects/<job>, or a path to the job folder (relative or absolute)
writes: <job>/transcript/cuts.json  (+ a scratch copy under the temp dir for stitch-cut.sh)
"""
import json, re, sys, os, shutil, tempfile, unicodedata
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
from difflib import SequenceMatcher

# engine root = 4 levels up from this script (.../.claude/skills/rough-cut/scripts/transcript-cut.py).
# Derived from __file__ so it ships portable — never hardcode a home path.
ENG=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
FILLER_ONLY = {"so","and","but","um","uh","like","okay","ok","yeah","well","i","you","it","the","a"}
# Spanish: the same job ("este..." / "o sea" / "pues" / "bueno" are its "um" / "I mean" / "so" / "well"). Only a
# fragment of one or two words that are ALL filler is dropped, so "este reel" or "o sea que sí" stays.
FILLER_ONLY |= {"este","eh","em","mm","pues","bueno","entonces","o","sea","osea","y","pero","vale","yo","tú","el","la","un","una"}
# Korean: 음 / 어 / 아 are its "um" / "uh", 그 / 저 its "uh..." before a word, 그니까 / 근데 / 막 / 이제 / 약간 its
# "I mean" / "but" / "like" / "now" / "kind of". Same rule: only a fragment that is ALL filler goes, so "이제 시작해요" stays.
FILLER_ONLY |= {"음","어","아","에","으","흠","그","저","그니까","그러니까","근데","그래서","그리고","막","이제","약간",
                "네","응","예","자","그냥"}
# Haitian Creole: eee / ehm / enm are its "um", enben / ebyen / bon its "well", alò / donk its "so", anfen / antouka
# its "anyway", epi / e its "and", tankou its "like", wi / dakò / oke its "yeah" / "okay". Same rule: only a fragment
# that is ALL filler goes, so "alò nou kòmanse" stays. Pronouns are left out on purpose: "mwen la" is a real line.
FILLER_ONLY |= {"ee","eee","ehm","enm","hmm","enben","ebyen","bon","alò","alo","donk","anfen","antouka","epi","e",
                "tankou","wi","dakò","oke"}

WARMUP = {"here","we","go","okay","ok","alright","all","right","ready","lets","let's","let","s","and","action","three",
          "two","one","3","2","1","um","uh","so","start","starting","rolling","recording","test","testing"}
# Korean slate talk: "자 시작할게요", "하나 둘 셋", "오케이 레디 액션"
WARMUP |= {"자","시작","시작할게요","시작합니다","하나","둘","셋","준비","오케이","레디","액션","녹화","테스트","음","어"}
# Haitian Creole slate talk: "ann ale", "an nou ale", "en de twa", "youn de twa", "aksyon", "m ap kòmanse", "oke pare"
WARMUP |= {"ann","an","nou","ale","aksyon","en","youn","de","twa","pare","kòmanse","m","ap","map","anrejistre","tès",
           "oke","dakò","bon","alò","ee","eee"}

def _cue_reader():
    """Does a run of words name an effect ("takeover", "karaoke", "count-up", "pantalla completa"...), in any
    language the cues are heard in? From their one home in product/spoken_cues.py. A cutter that cannot load them
    keeps working, just without the exemption."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("spoken_cues", os.path.join(ENG, "product", "spoken_cues.py"))
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        return mod.names_an_effect
    except Exception:
        return lambda text: False
CUE_READER = None

def names_an_effect(sent):
    """True when the words name an effect. Pausing before the effect word ("this is a... takeover") leaves
    that word as its own one-word sentence, and it is a direction for the build, never a fragment to drop."""
    global CUE_READER
    if CUE_READER is None: CUE_READER = _cue_reader()
    return CUE_READER(" ".join(w for (w,_,_) in sent))

def load_words(job):
    d=json.load(open(f"{job}/transcript/words.json", encoding="utf-8"))
    if isinstance(d,dict) and "clips" in d and len(d["clips"])>1:
        sys.exit(f"transcript-cut: this job has {len(d['clips'])} clips, but this cutter reads only the first. "
                 "Cut each clip as its own job, or combine the takes into one file first (multi-clip cutting is not supported here).")
    cw=d["clips"][0]["words"] if isinstance(d,dict) and "clips" in d else d
    def g(x): return x.get("word",x.get("w","")), x.get("start",x.get("s")), x.get("end",x.get("e"))
    return [(w,s,e) for (w,s,e) in (g(x) for x in cw) if s is not None and (e is not None)]

# A spoken amount ("$27,000", "40%", "3.5k") is several spoken words under ONE stamp: the aligner cannot time
# digits, so the stamp runs long, holds quiet inside it ("twenty-seven ... thousand") and can end a whole word
# early ("dollars", "percent" said after it; measured on a real cut: stamp end 24.67 s, "dollars" 25.10-25.60 s).
# So a pause beside an amount is never a place to cut (up to AMOUNT_GAP), a line that ends on one keeps the
# sound after its stamp up to the next word, and the long-word guard never shortens one.
# Only a real amount: a currency sign, a percent, a k/m/b, or thousands written with commas ("27,000" is said as
# "twenty-seven thousand"). A bare number ("3, 2, 1", "2024", "2nd") is said inside its own stamp and cut as any word.
AMOUNT=re.compile(r"^\W*(?:[$€£¥]\d[\d,.]*[kKmMbB]?|\d[\d,.]*\s*(?:%|[kKmMbB])|\d{1,3}(?:,\d{3})+(?:\.\d+)?)\W*$")
AMOUNT_GAP=1.0          # the longest pause beside an amount that can still hold its own words ("dollars")
AMOUNT_TAIL=1.5         # how far past its stamp a line-ending amount's words can run, up to her next word
AMOUNT_LEAD=0.5         # how far before an amount's start stamp its first spoken word can begin
def amount(w): return bool(AMOUNT.match(w or ""))
def amount_pause(a, b, gap):
    """True when the pause between words a and b sits beside an amount, so it holds the amount's own words."""
    return gap <= AMOUNT_GAP and (amount(a[0]) or amount(b[0]))

def sentences(W, gap=0.6):
    out=[]; cur=[]
    for i,(w,s,e) in enumerate(W):
        if not w.strip(): continue
        cur.append((w,s,e))
        nxt_gap=(W[i+1][1]-e) if i+1<len(W) else 99
        # sentences split as always (so a retake of a line with an amount is still found and dropped); two KEPT
        # sentences that meet beside an amount are joined in build(), where the drop decisions are already made
        if w.rstrip().endswith((".","?","!")) or nxt_gap>gap:
            out.append(cur); cur=[]
    if cur: out.append(cur)
    return out

def toks(sent):
    # Letters, combining marks and digits of EVERY alphabet are word material. The old [a-z0-9] kept only
    # ASCII, so a Russian, Greek, Hindi, Arabic, Hebrew or Chinese line came out with no tokens at all and
    # drop_set threw every line away. On ASCII text this keeps exactly what [a-z0-9] kept.
    # NFC, so a filler written with a combining accent ("alò" as o + U+0300) is the same token as the list's.
    text=unicodedata.normalize("NFC", " ".join(w for (w,_,_) in sent).lower())
    return "".join(c for c in text if c==" " or unicodedata.category(c)[0] in "LMN").split()
def destem(t): return [w[:-1] if len(w)>3 and w.endswith("s") else w for t2 in [t] for w in t2]
def contained(short, long):
    """True if `short`'s tokens appear as a near-contiguous run inside `long` (fragment of it)."""
    if not short or len(short)>=len(long): return False
    m=SequenceMatcher(None, short, long).find_longest_match(0,len(short),0,len(long))
    return m.size >= max(3, int(0.85*len(short)))

def drop_set(S, T):
    """Indices to DROP. A sentence drops if a nearby sentence is a near-duplicate (retake, keep LAST),
    contains it as a fragment (keep the COMPLETE take), restarts it (keep the finished take), or it's a
    filler-only / orphan fragment."""
    drop=set(); LOOK=6; WIN=26.0
    for i in range(len(S)):
        ti=T[i]
        if not ti: drop.add(i); continue
        # filler-only (<=2 tok all filler) OR an orphan 1-token fragment not ending a sentence -> drop
        if len(ti)<=2 and all(t in FILLER_ONLY for t in ti): drop.add(i); continue
        # a filming warm-up before the first real line ("here we go", "okay go", "three two one", "and action"): the
        # camera rolling, not the reel. Only while nothing real has been said yet, and only when it's all warm-up.
        if not any(j < i and j not in drop for j in range(len(S))) and 1 <= len(ti) <= 5 and all(t in WARMUP for t in ti):
            drop.add(i); continue
        if len(ti)==1 and not S[i][-1][0].rstrip().endswith((".","?","!")) and not names_an_effect(S[i]): drop.add(i); continue
    for i in range(len(S)):
        if i in drop or not T[i]: continue
        istart=S[i][0][1]
        for j in range(i+1, len(S)):
            if S[j][0][1]-istart>WIN or j>i+LOOK: break
            if j in drop or not T[j]: continue
            ti,tj=T[i],T[j]
            r=SequenceMatcher(None,ti,tj).ratio()
            if (len(ti)>=4 and r>=0.72) or r>=0.90: drop.add(i); break     # retake -> drop earlier
            # fragment containment: drop whichever is the fragment of the other
            if contained(ti,tj): drop.add(i); break
            if contained(tj,ti): drop.add(j); continue
            di,dj=destem(ti),destem(tj); n=min(len(di),len(dj),4)          # restart (contraction-safe)
            if n>=3 and di[:n]==dj[:n] and len(ti)<0.92*len(tj): drop.add(i); break
    return drop

def quiet_clip(job):
    """The clip's transcript entry when it has no talking in it (product/quiet_clips.py), else None."""
    sys.path.insert(0, os.path.join(ENG, "product"))
    try:
        import quiet_clips
        c0=json.load(open(f"{job}/transcript/words.json", encoding="utf-8"))["clips"][0]
        return c0 if quiet_clips.is_silent(c0) else None
    except Exception:
        return None

# A voiceover read with feeling ("emotional" in the job's voiceover.json, product/visual_editor.py vo-pace) keeps her
# pauses: a breath or a held beat up to EMO_GAP stays, between her sentences and inside them. Punchy (the default, and
# every other reel) cuts as below.
EMO_GAP=1.0
def vo_pace(job):
    try: return json.load(open(f"{job}/voiceover.json", encoding="utf-8")).get("pace")
    except Exception: return None

def build(job, clip, do_print):
    W=load_words(job)
    emo=vo_pace(job)=="emotional"
    q=quiet_clip(job)
    if q is not None:
        # No talking (her kids, a vlog moment): no lines to choose between, so the clip is kept whole. What the
        # transcriber heard in its background sound is never a reason to cut it.
        import quiet_clips
        segs=[{"clip":clip,"start":0.0,"end":round(max(0.1, quiet_clips.duration(q)-0.03),3),"transcript":"","keep_edges":True}]
        return write_cut(job, segs, 0, 0, do_print, quiet=True)
    S=sentences(W); T=[toks(s) for s in S]
    drop=drop_set(S,T)
    keep=[]
    for i,s in enumerate(S):
        if i in drop: continue
        # two kept sentences that meet in a pause beside an amount ("...$27,000. A month later") are one stretch
        # of her voice: the amount's spoken words ("dollars") sit in that pause, so it is never cut. On an emotional
        # voiceover, so are two that meet in a pause she held on purpose.
        g=s[0][1]-keep[-1][-1][2] if keep else 99
        if keep and i-1 not in drop and (amount_pause(keep[-1][-1], s[0], g) or (emo and g<=EMO_GAP)):
            keep[-1]=keep[-1]+s
        else:
            keep.append(s)
    # Keep each surviving SENTENCE WHOLE (first word onset -> last word offset). Sentences are already
    # split at gaps > 0.6s, so inter-sentence dead air is already gone; natural WITHIN-sentence pauses
    # (commas, breaths) STAY, so a line is never shredded into choppy jump-cuts. (An earlier 0.35s
    # internal split did exactly that — "how to pitch, what to say, how much to charge" became 3 hard
    # cuts. Never again.) Only guard: a WhisperX mis-stamp that stretches the FINAL word to an absurd
    # duration (a 6s line once ballooned to 20s) — clamp that phantom tail.
    # Split each kept sentence at internal pauses/gaps > GAP. This removes long dead air AND untranscribed
    # DYSFLUENCIES: a stutter/false-start WhisperX dropped from the transcript still sits as audio ENERGY
    # in the word-gap, so cutting the gap removes the "intra-line insert" you hear but never see in the
    # text. Author clean word-boundary splits and let snap-to-sound.py dial each boundary just outside the
    # words — that only lands clean because the proxy-name refine bug is now fixed (before, every micro-cut
    # shipped a clipped onset, which is what read as "shredded / not delivered well").
    GAP=EMO_GAP if emo else 0.30
    MAXWORD=1.3
    segs=[]
    at={(w,s,e):i for i,(w,s,e) in enumerate(W)}
    def head(fw):                                  # an amount's first spoken word can sit before its stamp
        if not amount(fw[0]): return fw[1]
        i=at.get(fw); prev_end=W[i-1][2] if i else 0.0
        return min(fw[1], max(prev_end+0.08, fw[1]-AMOUNT_LEAD, 0.0))   # never later than its own stamp
    def tail(lw, last=False):                      # ...and its last ones after it, up to the next word
        if amount(lw[0]):
            i=at.get(lw); nxt=W[i+1][1] if i is not None and i+1<len(W) else None
            return min(lw[2]+AMOUNT_TAIL, nxt-0.06) if nxt is not None else lw[2]+0.6   # the clip's last word: a short tail
        if last and (lw[2]-lw[1]) > MAXWORD: return lw[1]+0.5   # mis-stamp guard on the final word
        return lw[2]
    def emit(a, end, text):
        if end-a > 0.12: segs.append({"clip":clip,"start":round(a,3),"end":round(end,3),"transcript":text})
    for s in keep:
        run=[s[0]]
        for prev,cw in zip(s, s[1:]):
            g=cw[1]-prev[2]
            if g > GAP and not amount_pause(prev, cw, g):
                emit(head(run[0]), tail(prev), " ".join(w for (w,_,_) in run).strip())
                run=[cw]
            else:
                run.append(cw)
        emit(head(run[0]), tail(run[-1], last=True), " ".join(w for (w,_,_) in run).strip())
    return write_cut(job, segs, len(S), len(drop), do_print)

def write_cut(job, segs, n_sent, n_drop, do_print, quiet=False):
    name=os.path.basename(job.rstrip("/\\"))
    os.makedirs(f"{job}/transcript",exist_ok=True)
    _p=f"{job}/transcript/cuts.json"; _t=_p+".tmp"
    json.dump({"segments":segs}, open(_t,"w", encoding="utf-8"), indent=2); os.replace(_t,_p)   # atomic write
    # A fresh machine-authored cut resets the "her trim wins" marker (Bug #3): this cut is NOT a your-turn
    # pull-back, so trim-restarts is appropriate again on the next splice.
    _marker=f"{job}/transcript/.your-turn-cut"
    if os.path.exists(_marker):
        try: os.remove(_marker)
        except OSError: pass
    _scratch_dir=os.path.join(tempfile.gettempdir(), "reels-editing-engine", name)
    os.makedirs(_scratch_dir,exist_ok=True)
    shutil.copy(f"{job}/transcript/cuts.json", os.path.join(_scratch_dir, "cuts.json"))
    tot=sum(x["end"]-x["start"] for x in segs)
    if quiet:
        print(f"{name}: no talking in this clip, so it's kept whole | {tot:.1f}s ({int(tot//60)}:{int(tot%60):02d})")
    else:
        print(f"{name}: {len(segs)} piece{'s' if len(segs) != 1 else ''} kept from {n_sent} sentence{'s' if n_sent != 1 else ''} | dropped {n_drop} | {tot:.1f}s ({int(tot//60)}:{int(tot%60):02d})")
    if do_print:
        for i,x in enumerate(segs,1):
            print(f"{i:2d}|{x['end']-x['start']:4.1f}s| {x['transcript']}")
    return segs

def resolve_clip(job, name):
    """Which media file the cut points at. Priority: --clip flag > a 1080 review proxy if one exists
    > the exact clip that was transcribed (words.json). Portable — never assumes a proxy exists."""
    if "--clip" in sys.argv:
        return sys.argv[sys.argv.index("--clip")+1]
    proxy=f"{name}-1080.MOV"
    if os.path.exists(f"{job}/raw/{proxy}"):
        return proxy
    try:
        d=json.load(open(f"{job}/transcript/words.json", encoding="utf-8"))
        return os.path.basename(d["clips"][0]["clip"])
    except Exception:
        return f"{name}.MOV"

def job_dir(arg):
    """The job folder, from any form the neighbouring steps accept (trim-restarts.py reads the same ones):
    a bare job name, projects/<job>, or a relative or absolute path to the folder, a Windows C:\\... one
    included. Only a bare name is looked up under this engine's projects/."""
    job=arg.rstrip("/\\")
    if job.startswith(("projects/","projects\\")): job=job[len("projects/"):]
    if job.startswith("/") or os.path.isabs(job): return job
    if os.path.isdir(os.path.join(job,"transcript")): return os.path.abspath(job)
    return f"{ENG}/projects/{job}"

if __name__=="__main__":
    if len(sys.argv)<2 or sys.argv[1].startswith("--"):
        sys.exit("usage: transcript-cut.py <job> [--clip <name>] [--print]   (<job> = its name, projects/<job>, or its folder)")
    job=job_dir(sys.argv[1])
    name=os.path.basename(job.rstrip("/\\"))
    build(job, resolve_clip(job, name), "--print" in sys.argv)
