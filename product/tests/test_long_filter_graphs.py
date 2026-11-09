#!/usr/bin/env python3
"""A long ffmpeg filter graph goes to ffmpeg in a file on every render that grows one, not only the stitch.

Buyer reports (launch week, 2026-10-19): Windows refuses a command line over 32,767 characters (WinError 206).
The stitch already handed its graph over in a file (-/filter_complex), but four renders still put theirs inline,
and each grows by a chain per clip, sound or layer: the well-done bake (build-reel-mp4.py), the editor's sound
mix on export (finish.py), the editor's preview copy (visual_editor.py) and the layer composite (reel_render.py).
A long reel on a PC stopped there; buyers' Claudes patched each by hand.

  1. video_encoder.graph_args keeps a short graph inline, exactly as before, and writes a long one to a file
  2. ffmpeg here really runs a long graph read from that file
  3. reel_render composite, with the inline limit lowered so its small graph counts as long, renders through
     the file and leaves no graph file behind
  4. none of the four renders passes its graph inline any more; each goes through graph_args and cleans up

Run:  python3 product/tests/test_long_filter_graphs.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types

PRODUCT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PRODUCT)
import video_encoder  # noqa: E402

fails = []


def check(label, cond, detail=""):
    print(("  PASS " if cond else "  FAIL ") + label + ("" if cond or not detail else f"  {detail}"))
    if not cond:
        fails.append(label)


FFMPEG = shutil.which("ffmpeg")
tmp = tempfile.mkdtemp()
try:
    print("1. graph_args")
    short = "[0:a]volume=1[a]"
    gpath = os.path.join(tmp, "g.txt")
    check("a short graph stays inline, as it always ran", video_encoder.graph_args(short, gpath) == ["-filter_complex", short]
          and not os.path.exists(gpath))
    long_graph = "[0:a]" + ",".join(["volume=1.0"] * 1200) + "[a]"
    args = video_encoder.graph_args(long_graph, gpath)
    check("a long graph is written to the file and read from there",
          args[0] in ("-/filter_complex", "-filter_complex_script") and args[1] == gpath
          and open(gpath, encoding="utf-8").read() == long_graph, str(args[:1]))
    check("the inline limit leaves Windows' 32,767 characters room for the inputs",
          video_encoder.GRAPH_INLINE_MAX <= 16000)

    if FFMPEG:
        print("2. ffmpeg runs a long graph from the file")
        out = os.path.join(tmp, "long.m4a")
        r = subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=0.3", *args,
                            "-map", "[a]", "-c:a", "aac", out], capture_output=True, text=True)
        check("it renders", r.returncode == 0 and os.path.exists(out), r.stderr[-300:])
        video_encoder.remove_graph(gpath)
        check("remove_graph takes the file away (and is quiet when there is none)",
              not os.path.exists(gpath) and video_encoder.remove_graph(gpath) is None)

        print("3. reel_render composite through the file")
        base = os.path.join(tmp, "base.mp4")
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=96x160:rate=30:duration=1",
                        "-f", "lavfi", "-i", "sine=duration=1", "-c:v", "libx264", "-preset", "ultrafast",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", base], check=True)
        layers = []
        for i, c in enumerate(("red", "blue")):
            lp = os.path.join(tmp, f"layer{i}.mov")
            subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={c}@0.4:s=96x160:r=30:d=1",
                            "-vf", "format=argb", "-c:v", "qtrle", lp], check=True)
            layers.append(lp)
        import reel_render
        used = []
        real_fca = video_encoder.filter_complex_args
        old_max = video_encoder.GRAPH_INLINE_MAX

        def spy(graph, path):
            used.append(path)
            return real_fca(graph, path)

        video_encoder.filter_complex_args, video_encoder.GRAPH_INLINE_MAX = spy, 10
        try:
            out = os.path.join(tmp, "composited.mp4")
            rc = reel_render.cmd_composite(types.SimpleNamespace(base=base, layers=layers, audio=None, output=out,
                                                                 crf=30, grade=None))
        finally:
            video_encoder.filter_complex_args, video_encoder.GRAPH_INLINE_MAX = real_fca, old_max
        check("the composite renders", rc == 0 and os.path.exists(out), f"rc {rc}")
        check("its graph went over in a file", len(used) == 1, str(used))
        check("and that file is gone afterwards", used and not os.path.exists(used[0]), str(used))
    else:
        print("  (no ffmpeg here: 2-3 skipped)")

    print("4. the four renders")

    def src(name):
        with open(os.path.join(PRODUCT, name), encoding="utf-8") as fh:
            return fh.read()

    bake, fin, ve, rr = src("build-reel-mp4.py"), src("finish.py"), src("visual_editor.py"), src("reel_render.py")
    check("the well-done bake hands its graph through graph_args and cleans up",
          '*graph_args(";".join(fc), GRAPH_FILE)' in bake and "remove_graph(GRAPH_FILE)" in bake
          and '"-filter_complex", ";".join(fc)' not in bake)
    check("the export's sound mix does too", 'graph_args(";".join(fc), gfile)' in fin and "remove_graph(gfile)" in fin
          and '"-filter_complex", ";".join(fc)' not in fin)
    check("the editor's preview copy does too", "*graph_args(graph, gfile)" in ve and "remove_graph(gfile)" in ve
          and '"-filter_complex", graph,' not in ve)
    check("the layer composite does too", "*graph_args(fc, gfile)" in rr and "remove_graph(gfile)" in rr
          and '"-filter_complex", fc' not in rr)
    inline = [n for n, s in (("build-reel-mp4.py", bake), ("finish.py", fin), ("visual_editor.py", ve), ("reel_render.py", rr))
              if re.search(r'"-filter_complex",\s*[a-z";]', s)]
    check("no inline -filter_complex left in any of them", not inline, str(inline))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "long filter graphs: every growing render hands its graph over in a file"))
sys.exit(1 if fails else 0)
