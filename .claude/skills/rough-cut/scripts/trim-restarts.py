#!/usr/bin/env python3
"""trim-restarts.py — remove QUICK RESTARTS the transcript can't see (acoustic MFCC fingerprint).

A creator starts a line, stops, and restarts it fast: "how much to— how much to charge." WhisperX keeps
only the clean words and deletes the abandoned take (often collapsing it into one over-long word: a 1.14s
"to", a 1.62s "warm"), so a transcript-only cut keeps clean text while the VIDEO plays BOTH takes.

The only reliable signal is acoustic, and it must be PHONETIC, not loudness: energy-envelope similarity
can't tell a real restart (~0.36) from ordinary speech (~0.28). So this compares MFCC fingerprints — which
encode what was actually SAID. At every short pause (a candidate restart boundary) it asks: does the speech
just BEFORE the pause repeat at the start of the take just AFTER it? (best-lag mean cosine over MFCC
frames). Same words score high (~0.8+); different words score low (~0.4). On a match it cuts the whole
abandoned take + the pause, keeping the completed take. snap-to-sound runs after, so boundaries land clean.

Runs LOCALLY (torchaudio MFCC) — zero LLM cost per reel. Must run with a Python that has torch/torchaudio
+ numpy (the WhisperX venv).

usage: trim-restarts.py <job_dir> [--print] [--debug] [--cuts PATH]
  --cuts PATH  read+write THIS cuts.json (the caller's scratch copy) instead of the persisted, shared
               transcript/cuts.json. stitch-cut.sh passes its per-invocation $WORK/cuts.json so two concurrent
               runs on one job can never stomp the same shared file (Bug #1). Default keeps the standalone /
               clean_cut behavior: read+write transcript/cuts.json and refresh the /tmp scratch copy.
"""
import json, os, sys, subprocess, wave, tempfile
try:                                       # os.replace that waits out Windows holding the plan open for a moment
    sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "product"))
    from swap import replace as swap_in
except ImportError:
    swap_in = os.replace
for stream in (sys.stdout, sys.stderr):   # ✓ and → need UTF-8; a cp1252 Windows console cannot print them
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
try:
    import numpy as np
    import torch, torchaudio
    _IMPORT_ERR = None
except Exception as _e:      # keep the pure helpers (low_confidence_segments) importable without the venv,
    np = torch = torchaudio = None   # so the regression test runs under plain python3 (main() still needs torch)
    _IMPORT_ERR = f"{type(_e).__name__}: {_e}"

# Exit code for "this computer's speech tools cannot run this pass" (torch, torchaudio or numpy will not load).
# It is the computer, not the reel, so stitch-cut.sh and clean_cut.py skip the pass, remember it, and finish the
# cut; any other failure is about this reel and is reported as one. 69 is the usual "service unavailable" code.
EXIT_TOOLS_UNAVAILABLE = 69
# Reading the clip's sound takes seconds even on a long phone clip. Past this, ffmpeg is stuck (a clip on a
# drive that went to sleep, say), and the pass gives up instead of holding the whole stitch.
FFMPEG_TIMEOUT = 300


def drop_cut_slivers(segs, min_len=0.12):
    """Remove only the slivers a restart cut left behind; keep every segment no cut touched.

    Segments carrying _retrim were produced by subtract(); those under min_len are debris from the cut.
    Anything else is the creator's own cut and is kept at ANY length. The old filter dropped every short
    segment, which silently undid a single-word edit on every splice, even when no restart was found."""
    return [s for s in segs if not s.get("_retrim") or s["end"] - s["start"] > min_len]


def low_confidence_segments(segs, word_probs, thr=0.5):
    """KEPT segments whose AVERAGE word probability (words.json 'score', 'prob' in older jobs) is below thr — a restart/repeat
    region where WhisperX forced-alignment timing collapses (probs seen as low as 0.0) and a cut boundary is
    exactly the kind that lands wrong. word_probs = [(start,end,prob)]. Returns [(start,end,avg_prob)].
    Advisory only (Bug #2): surfaces the mis-fire class for a re-listen before render; never alters the cut."""
    out = []
    for sg in segs:
        a, b = sg["start"], sg["end"]
        ps = [p for (s, e, p) in word_probs if a - 0.02 <= (s + e) / 2.0 < b + 0.02]
        ap = sum(ps) / len(ps) if ps else 1.0
        if ap < thr:
            out.append((a, b, round(ap, 3)))
    return out

def _tokens(text):
    """Lowercased words with edge punctuation stripped; pure-punctuation tokens ("?", "—") dropped.
    Letters in any alphabet survive, and so does an apostrophe inside a word (n'as, don't)."""
    out = []
    for raw in str(text).split():
        t = "".join(ch for ch in raw.lower() if ch.isalnum() or ch == "'").strip("'")
        if t:
            out.append(t)
    return out


def words_agree(take1, take2, thr=0.6):
    """Do the two takes OPEN with the same words? take1/take2 are the transcript text of each take.

    A restart repeats its opening ("how much to / how much to charge", "I'm a mom who / I'm a mom
    working"). Two different lines that merely sound alike open on different words ("tu n'as pas
    besoin / tu as besoin d'un", "maybe I can earn / maybe I could do"). Compares take-1's first few
    words against take-2's opening, allowing one inserted word. Language-free: plain token matching."""
    from difflib import SequenceMatcher
    a = _tokens(take1)[:4]
    b = _tokens(take2)[:len(a) + 1]
    if not a or not b:
        return True                      # nothing to compare: leave the decision to the sound
    hit = sum(m.size for m in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())
    return hit / len(a) >= thr


def take2_heard(words, d1, lead=0.15, lag=0.20):
    """Did the transcript hear a NEW phrase start right where take-2 resumes? words = [(w, start, end)].

    True when a word begins within [d1-lead, d1+lag]. When WhisperX collapsed a restart it keeps the
    phrase once, so nothing starts at the resume point (the repeat is folded into an over-long word or
    left as a gap). Only when it did hear a fresh start is the text trustworthy enough to overrule the
    sound."""
    return any(d1 - lead <= s <= d1 + lag for (w, s, e) in words if _tokens(w))


LONG_WORD = 1.0     # the same "unusually long span" word-timings.sh warns about: a merged repeat


def folded_repeat(words, p0, d1, long_word=LONG_WORD):
    """Did WhisperX fold a repeat into one over-long word between take-1's start and the resume point?
    ("The number— the number that": 'number' stamped 1.28s.) Then the transcript is missing take-2's
    opening, so its words cannot be compared and the sound must decide."""
    return any(e - s > long_word for (w, s, e) in words if e > p0 and s < d1)


SIL      = 250.0    # rms below this = quiet
DIP_MIN  = 0.16     # a restart pause can be short
DIP_MAX  = 0.95     # longer = a sentence break (already handled upstream), not a restart
BACK     = 1.60     # how far back the abandoned take may reach
SIM      = 0.68     # prefix-DTW similarity above this = the take's OPENING repeats = a restart
MINLEN   = 0.45     # ignore too-short bursts (can't judge)
PREFIX   = 0.65     # match only take-1's OPENING (~0.65s): a restart repeats the opening even when the two
                    # takes diverge after ("I'm a mom WHO" vs "I'm a mom WORKING"); matching the whole
                    # burst would penalize that divergence and miss the restart.
HOP      = 0.010    # MFCC frame hop (s)

def media_dir(job):
    """Where the job's footage is: raw/ (intake copies it there), or the job folder itself on a job made before
    intake did that. The same rule stitch-cut.sh uses for MEDIA_DIR."""
    raw=os.path.join(job,"raw")
    return raw if os.path.isdir(raw) else job


def main():
    args=sys.argv[1:]
    job=args[0].rstrip("/")
    # accept what the neighbouring steps accept: a bare job name, `projects/<job>`, a relative or an absolute path
    eng=os.path.abspath(os.path.join(os.path.dirname(__file__),"..","..","..",".."))
    if job.startswith("projects/"): job=job[len("projects/"):]
    if not job.startswith("/"):
        job=os.path.abspath(job) if os.path.isdir(job) and os.path.isdir(os.path.join(job,"transcript")) else f"{eng}/projects/{job}"
    do_print="--print" in args; debug="--debug" in args
    # Bug #1: operate on the caller's SCRATCH cuts.json when given, never the persisted shared file.
    if "--cuts" in args:
        _ci = args.index("--cuts")
        if _ci + 1 >= len(args):
            sys.exit("trim-restarts: --cuts requires a path argument")
        scratch = args[_ci + 1]
    else:
        scratch = None
    cp=scratch or f"{job}/transcript/cuts.json"
    segs=json.load(open(cp, encoding="utf-8"))["segments"]
    d=json.load(open(f"{job}/transcript/words.json", encoding="utf-8"))
    if len(d["clips"])>1:
        sys.exit(f"trim-restarts: this job has {len(d['clips'])} clips, but this pass reads only the first. Cut each clip as its own job.")
    cw=d["clips"][0]["words"]
    def g(x): return (x.get("word",x.get("w","")), x.get("start",x.get("s")), x.get("end",x.get("e")),
                      x.get("score", x.get("prob", 1.0)))
    _rows=[(w,s,e,p) for (w,s,e,p) in (g(x) for x in cw) if s is not None and e is not None]
    WD=[(w,s,e) for (w,s,e,p) in _rows]
    WP=[(s,e,float(p) if p is not None else 1.0) for (w,s,e,p) in _rows]   # per-word confidence (Bug #2 guard)

    if _IMPORT_ERR is not None:
        # Said in so many words and with its own exit code, instead of an AttributeError on None further down
        # that reads like a bug in this reel. Checked only now, so what is true of the job itself (several
        # clips, above) is still what she hears first.
        print(f"trim-restarts: this computer's speech tools can't run this pass ({_IMPORT_ERR})", file=sys.stderr)
        sys.exit(EXIT_TOOLS_UNAVAILABLE)

    clip=segs[0]["clip"]; media=os.path.join(media_dir(job), clip)   # a clip given as a full path stays that path
    wav=os.path.join(tempfile.gettempdir(), f"_trim_restarts_{os.getpid()}.wav")
    # -nostdin: run from a script, ffmpeg otherwise waits on the terminal for keystrokes it never gets.
    try:
        subprocess.run(["ffmpeg","-nostdin","-y","-i",media,"-map","0:a:0?","-ac","1","-ar","16000","-c:a","pcm_s16le",wav],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=FFMPEG_TIMEOUT)
    except subprocess.TimeoutExpired:
        sys.exit(f"trim-restarts: ffmpeg was still reading the sound of {media} after {FFMPEG_TIMEOUT} s, "
                 f"so this pass stopped there")
    _w=wave.open(wav,"rb"); sr=_w.getframerate(); _n=_w.getnframes()
    samp=(np.frombuffer(_w.readframes(_n), dtype=np.int16).astype(np.float32)/32768.0)
    sig=torch.from_numpy(samp).unsqueeze(0)        # [1, N] @ 16k
    # RMS energy per 10ms frame (for pause detection)
    fl=int(HOP*sr); nf=len(samp)//fl
    en=np.sqrt(np.maximum(0,(samp[:nf*fl]**2).reshape(nf,fl).mean(1)))*32768.0
    def rms(t0,t1):
        i0,i1=int(t0/HOP),max(int(t0/HOP)+1,int(t1/HOP)); s=en[i0:i1]; return float(s.mean()) if len(s) else 0.0
    def onset_after(t_lo, t_hi):
        """Acoustic onset of the take that RESUMES after a pause: first frame in [t_lo, t_hi] where energy
        rises above a relative speech level and holds ~30 ms. Uses the RMS envelope already computed here —
        snap-to-sound' onset idea, independent of any (unreliable) word timestamp (Bug #2). Seconds, or None."""
        i0=max(0,int(t_lo/HOP)); i_end=min(len(en), int(t_hi/HOP)+1)
        i_meas=min(len(en), int((t_hi+0.25)/HOP)+1)          # gauge the speech level a bit past the window
        gauge=en[i0:i_meas]
        if len(gauge) < 4 or i_end-i0 < 3: return None
        srt=sorted(gauge); thr=max(SIL, float(srt[int(0.8*len(srt))])*0.35)
        for k in range(i_end-i0-2):
            if en[i0+k]>=thr and en[i0+k+1]>=thr and en[i0+k+2]>=thr:
                return (i0+k)*HOP
        return None
    # MFCC fingerprint: 13 coeffs @10ms, drop c0 (energy), z-normalize each coeff over the clip
    mf = torchaudio.transforms.MFCC(sample_rate=sr, n_mfcc=13,
            melkwargs=dict(n_fft=400, hop_length=fl, n_mels=40, center=True))(sig)[0].numpy()  # [13, T]
    M = mf[1:].T                                   # [T,12]
    M = (M - M.mean(0)) / (M.std(0)+1e-6)
    T = M.shape[0]
    def frames(t0,t1): return M[max(0,int(t0/HOP)):min(T,int(t1/HOP))]
    def sim_seq(A,B):
        # SUBSEQUENCE DTW similarity: does phrase A recur anywhere inside B, allowing for the two takes
        # being spoken at different speeds? DTW time-warps the alignment, so a fast first take still matches
        # a slower second take (fixed-offset cosine could not — that scored a real restart only 0.49).
        if len(A)<3 or len(B)<3: return 0.0
        An=A/(np.linalg.norm(A,axis=1,keepdims=True)+1e-6)
        Bn=B/(np.linalg.norm(B,axis=1,keepdims=True)+1e-6)
        C=1.0-(An@Bn.T)                            # [na,nb] cosine distance
        na,nb=C.shape
        D=np.full((na,nb),np.inf); D[0,0]=C[0,0]   # PREFIX DTW: A[0] must align to B[0] — a restart resumes
                                                   # right after the pause, so take-1 repeats at take-2's START
        for i in range(1,na):
            row=C[i]; prev=D[i-1]; cur=D[i]
            for j in range(nb):
                b=prev[j]                                       # vertical
                if j>0:
                    if prev[j-1]<b: b=prev[j-1]                 # diagonal
                    if cur[j-1]<b:  b=cur[j-1]                  # horizontal
                cur[j]=row[j]+b
        cost=float(D[na-1].min())/na               # best normalized alignment cost
        return 1.0-cost

    # candidate pauses: quiet runs DIP_MIN..DIP_MAX flanked by speech
    dips=[]; st=None
    for i in range(T):
        q = en[i] < SIL if i<len(en) else True
        if q:
            if st is None: st=i
        else:
            if st is not None:
                if DIP_MIN <= (i-st)*HOP <= DIP_MAX: dips.append((st*HOP, i*HOP))
                st=None
    def word_txt(a,b): return " ".join(w for (w,s,e) in WD if s>=a-0.02 and s<b).strip()

    trims=[]; dbg=[]; spared=[]
    for (d0,d1) in dips:
        # abandoned burst = speech before d0, back to the previous pause (cap BACK)
        p0=max(0.0, d0-BACK); prev=[e for (s,e) in dips if e<=d0-0.02 and e>=p0]
        p0 = max(prev) if prev else max(0.0,d0-BACK)
        i=int(p0/HOP)                                    # advance p0 to where SPEECH actually starts, so the
        while i<int(d0/HOP) and (i>=len(en) or en[i]<SIL): i+=1   # prefix is the phrase, not leading silence
        p0=i*HOP
        L=d0-p0
        if L<MINLEN: continue
        if len(word_txt(p0,d0).split()) < 2: continue        # need a real 2+ word phrase, not a breath/filler
        A=frames(p0, min(d0, p0+PREFIX))                      # take-1's OPENING
        sim=sim_seq(A, frames(d1, d1+PREFIX+0.55))            # ...must recur at take-2's START
        if debug and L>0.3: dbg.append((round(p0,2),round(d0,2),round(sim,2),word_txt(p0,d0)))
        if sim>=SIM and take2_heard(WD, d1) and not folded_repeat(WD, p0, d1):
            # The sound says "restart", but the transcript heard a fresh phrase begin at the resume point.
            # If the two takes open on different words, they are two lines that sound alike ("you don't
            # need X. / You need Y."), not a restart, and cutting would delete a real line.
            take2=" ".join(w for (w,s,e) in WD if d1-0.15<=s<d1+PREFIX+0.55)
            if not words_agree(word_txt(p0,d0), take2):
                spared.append((round(p0,2), round(d0,2), round(sim,2), word_txt(p0,d0), take2))
                continue
        if sim>=SIM:
            # Bug #2: resume the kept take at the MEASURED acoustic onset of take-2, not a forced-alignment
            # timestamp. Clamped INSIDE the pause [d0, d1+0.12], so it can only nudge within the silence —
            # worst case it equals d1 (no regression by construction).
            on=onset_after(d0, d1+0.12)
            ce=on if (on is not None and d0 <= on <= d1+0.12) else d1
            trims.append((round(p0,3), round(ce,3), round(sim,2)))
    # merge overlapping
    trims.sort(); merged=[]
    for a,b,s in trims:
        if merged and a<=merged[-1][1]+0.02: merged[-1]=(merged[-1][0], max(merged[-1][1],b), max(merged[-1][2],s))
        else: merged.append((a,b,s))

    def subtract(seg,cs,ce):
        a,b=seg["start"],seg["end"]
        if seg.get("no_trim"): return [seg]        # authored opt-out: a ground-truthed false positive stays whole
        if ce<=a or cs>=b: return [seg]
        out=[]
        if cs>a+0.10: out.append({**seg,"end":round(cs,3),"_retrim":True})
        if ce<b-0.10: out.append({**seg,"start":round(ce,3),"_retrim":True})
        return out
    cur=segs
    for cs,ce,s in merged:
        nxt=[]
        for sg in cur: nxt+=subtract(sg,cs,ce)
        cur=nxt
    # Drop only the SLIVERS a cut left behind (tagged _retrim by subtract). A segment no cut touched is
    # kept at ANY length. Before this, every segment of 0.12s or less was discarded on every splice, even
    # with zero restarts found — which silently deleted a hand-authored word-level edit: cutting a single
    # stumbled word out of continuous speech leaves exactly that kind of short segment, and the next
    # splice quietly merged the edit away while printing "0 restart(s) cut".
    new=drop_cut_slivers(cur)
    # A trimmed segment still carries its PRE-fix `transcript` (the abandoned take's duplicated text),
    # so re-derive the label from the words actually kept in the new [start,end] range — the same
    # first-word-onset..last-word-offset join transcript-cut used to build it. Only touch segments a cut
    # actually moved (the "_retrim" tag); untouched segments keep their text verbatim, so the normal
    # no-restart case is unchanged. Without this, cuts.json's stale label makes verify-cut.py compare
    # the pre-fix text against the correctly-fixed render and raise a FALSE stumble/mismatch.
    for sg in new:
        if sg.pop("_retrim", False):
            sg["transcript"]=word_txt(sg["start"], sg["end"])

    if debug:
        print("candidate bursts (sim | text):")
        for p0,d0,sim,tx in sorted(dbg,key=lambda x:-x[2])[:16]: print(f"  {sim:.2f}  [{p0}-{d0}]  «{tx}»")
    if do_print:
        print(f"{len(merged)} restart(s) cut:")
        for cs,ce,s in merged: print(f"  cut {cs:.2f}->{ce:.2f} ({ce-cs:.2f}s, sim={s})  «{word_txt(cs,ce)}»")
    for p0,d0,s,t1,t2 in spared:
        print(f"  kept {p0:.2f}->{d0:.2f}: sounds like the next line (sim={s}) but the words differ, "
              f"so it is its own line  «{t1}» / «{t2}»")
    # LOW-CONFIDENCE GUARD (Bug #2) — loud, advisory: flag any kept segment whose transcript timing is
    # unreliable (avg word prob < 0.5), i.e. exactly a restart/repeat region where a boundary can land wrong.
    for a,b,ap in low_confidence_segments(new, WP):
        print(f"  ⚠ low-confidence cut {a:.2f}->{b:.2f} (avg word prob {ap:.2f} < 0.5) — WhisperX timing here "
              f"is unreliable (repeat/restart region); RE-LISTEN before render  «{word_txt(a,b)}»", file=sys.stderr)
    if do_print:
        # --print is a PREVIEW. It used to rewrite cuts.json anyway, so "just looking" changed the cut.
        # The pipeline never passes --print (stitch-cut.sh calls this without it), so a real run still writes.
        print("(preview only: --print writes nothing)")
        return
    _t=cp+".tmp"; json.dump({"segments":new}, open(_t,"w", encoding="utf-8"), indent=2); swap_in(_t,cp)   # atomic write
    if scratch is None:
        # default (standalone / clean_cut) mode: also refresh the /tmp scratch copy splice consumes.
        # In --cuts mode the caller's scratch IS cp, so there is nothing to mirror (and no shared file to race).
        name=os.path.basename(job.rstrip("/"))
        _scratch_dir=os.path.join(tempfile.gettempdir(), "reels-editing-engine", name)
        os.makedirs(_scratch_dir,exist_ok=True)
        _mirror=os.path.join(_scratch_dir, "cuts.json")
        if os.path.abspath(_mirror) != os.path.abspath(cp):
            __import__("shutil").copy(cp,_mirror)
    try: os.remove(wav)
    except OSError: pass

if __name__=="__main__": main()
