#!/usr/bin/env python3
"""Regression guard for script_fonts — Cyrillic (and Greek, and Korean) on screen in a pack face that has none.

The bug this locks down: a Bulgarian reel set in a Latin-only pack face (Poppins, Prosecco, Soup Du Jour)
rendered its Cyrillic letters in whatever system font the browser borrowed, usually a serif, and the text
was sized by measuring placeholder boxes, so a Playful takeover ran 200px off the frame. Nothing errored.

What must hold: an English page comes back byte for byte; a Cyrillic page gains a unicode-range companion
for each face that lacks the letters and none for a face that has them; the companion suits the face; and
text is measured on the face that will actually draw it. Greek works the same way, with its own serif
(Noto Serif Display) and handwritten (Mynerve) companions, and no letter of a Greek hook or caption is left
for the browser to borrow in any shipped pack face. Only fonts that ship are used, so this passes on
a buyer machine too.

Run: python3 product/tests/test_script_fonts.py
"""
import os, sys, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import script_fonts as SF
import hooksplit

FONTS = SF.FONTS
fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def page(text, faces):
    rules = "".join(f"@font-face{{font-family:'{fam}';src:url('fonts/{f}');}}" for fam, f in faces)
    return f"<html><head><style>{rules}\nbody{{}}</style></head><body><div>{text}</div></body></html>"


def comp_dir(faces):
    d = tempfile.mkdtemp(prefix="script-fonts-")
    os.makedirs(os.path.join(d, "fonts"))
    for _, f in faces:
        shutil.copy(os.path.join(FONTS, f), os.path.join(d, "fonts", f))
    return d


def main():
    faces = [("Cap", "Poppins-SemiBold.ttf"), ("Head", "PlayfairDisplay-VF.ttf"), ("Aside", "PinyonScript-Regular.ttf")]
    d = comp_dir(faces)
    try:
        en = page("Hello there, $300", faces)
        out, notes = SF.add_companions(en, d)
        check("an English page comes back byte for byte", out == en and notes == [])

        bg = page("Като макраме, когато плетеш много-много", faces)
        out, notes = SF.add_companions(bg, d)
        check("a Bulgarian page gains the companion block", SF.MARK in out)
        check("Poppins SemiBold gets Inter Bold for its Cyrillic",
              "font-family:'Cap';src:url('fonts/cyr-Inter-Bold.otf');unicode-range:" in out, out[:600])
        check("a script face gets the handwritten companion", "font-family:'Aside';src:url('fonts/cyr-Caveat-VF.ttf')" in out)
        check("a face that has Cyrillic (Playfair) is left alone", "font-family:'Head';src:url('fonts/cyr-" not in out)
        check("companions come after the pack faces, so they win for Cyrillic",
              out.index("unicode-range") > out.index("PinyonScript-Regular.ttf"))
        check("the companion file is copied next to the page",
              os.path.exists(os.path.join(d, "fonts", "cyr-Inter-Bold.otf")))
        check("it says in plain words which font draws the Cyrillic", any("Poppins" in n for n in notes), str(notes))
        again, notes2 = SF.add_companions(out, d)
        check("running it twice changes nothing", again == out and notes2 == [])
    finally:
        shutil.rmtree(d, ignore_errors=True)

    # accented Latin, shipped faces only: Inter Medium has é and « » but no Ÿ (French) or ć ł Ż (Polish)
    faces = [("Cap", "Inter-Medium.ttf"), ("Aside", "Caveat-VF.ttf")]
    d = comp_dir(faces)
    try:
        fr = page("« L'HAŸ-LES-ROSES », ça a tout changé", faces)
        out, notes = SF.add_companions(fr, d)
        check("a French page gains the companion block", SF.MARK in out)
        check("Inter Medium hands over exactly Ÿ, nothing else",
              "font-family:'Cap';src:url('fonts/comp-Inter-Regular.otf');unicode-range:U+0178;" in out, out[:700])
        check("a face with every letter on the page (Caveat) is left alone", "font-family:'Aside';src:url('fonts/c" not in out)
        check("the note names the letter and the face that draws it",
              any("Ÿ" in n and "Inter-Regular" in n for n in notes), str(notes))
        check("Latin-only companions are not labelled Cyrillic", "cyr-" not in out)
        out, _ = SF.add_companions(page("Żółć", faces), d)
        check("Polish letters Inter Medium lacks go to Inter Regular, one by one (ó it has stays put)",
              "font-family:'Cap';src:url('fonts/comp-Inter-Regular.otf');unicode-range:U+0107,U+0142,U+017B;" in out,
              out[:700])
        out, _ = SF.add_companions(page("Като ż", faces), d)
        check("Cyrillic plus a missing Latin letter share one rule: the alphabet range, then the letter",
              f"font-family:'Cap';src:url('fonts/cyr-Inter-Regular.otf');unicode-range:{SF.RANGE},U+017C;" in out,
              out[:700])
        check("a face that has its own Cyrillic (Caveat) is not handed any", "font-family:'Aside';src:url('fonts/c" not in out)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    im = os.path.join(FONTS, "Inter-Medium.ttf")
    runs = [(os.path.basename(p), t) for p, t in SF.split(im, "« Ÿ é »")]
    check("only the missing letter is measured on the companion; « é » stay on the face",
          runs == [("Inter-Medium.ttf", "« "), ("Inter-Regular.otf", "Ÿ"), ("Inter-Medium.ttf", " é »")], str(runs))
    check("accented text a face fully covers stays one run", SF.split(im, "café") == [(im, "café")])
    # a pack face that is not bundled (it resolves from the creator's own CapCut): checked where it exists
    bloop = os.path.join(FONTS, "Bloop.ttf")
    if os.path.exists(bloop):
        check("Bloop keeps é and hands over only « »",
              [(os.path.basename(p), t) for p, t in SF.split(bloop, "« été »")] ==
              [("Caveat-VF.ttf", "«"), ("Bloop.ttf", " été "), ("Caveat-VF.ttf", "»")], str(SF.split(bloop, "« été »")))
    else:
        print("  (Bloop is a pack font that is not bundled here, so its « » check was skipped)")

    # the companion picked for each Latin-only face that ships
    for face, want in (("Poppins-SemiBold.ttf", "Inter-Bold.otf"), ("Inter-Medium.ttf", "Inter-Regular.otf"),
                       ("Poppins-Black.ttf", "Inter-Black.otf"), ("PinyonScript-Regular.ttf", "Caveat-VF.ttf"),
                       ("SpaceGrotesk-VF.ttf", "Inter-Regular.otf")):
        got = SF.companion_for(os.path.join(FONTS, face), "ж")
        check(f"{face} -> {want}", got and os.path.basename(got) == want, str(got))

    # every companion ships and really has the letters it is there to draw
    for comp in ("Caveat-VF.ttf", "PlayfairDisplay-VF.ttf", "PlayfairDisplay-SemiBold.ttf",
                 "Inter-Regular.otf", "Inter-Bold.otf", "Inter-Black.otf"):
        p = os.path.join(FONTS, comp)
        check(f"companion {comp} ships and covers Cyrillic",
              os.path.exists(p) and SF.companion_for(p, "БъЛгарскиЖЩЮЯ") is None)

    # Greek: its own companions where the Cyrillic ones have none (Playfair, Caveat)
    faces = [("Cap", "Poppins-SemiBold.ttf"), ("Head", "PlayfairDisplay-VF.ttf"), ("Aside", "PinyonScript-Regular.ttf"),
             ("Big", "Inter-SemiBold.ttf")]
    d = comp_dir(faces)
    try:
        el = page("Σαν μακραμέ, όταν πλέκεις πολύ; Ἀρχή", faces)
        out, notes = SF.add_companions(el, d)
        check("a Greek page gains the companion block", SF.MARK in out)
        check("Playfair (Cyrillic but no Greek) gets Noto Serif Display for its Greek",
              f"font-family:'Head';src:url('fonts/grk-NotoSerifDisplay-VF.ttf');unicode-range:{SF.GREEK};" in out, out[:900])
        check("Poppins SemiBold gets Inter Bold for its Greek",
              f"font-family:'Cap';src:url('fonts/grk-Inter-Bold.otf');unicode-range:{SF.GREEK};" in out)
        check("a script face gets the handwritten Greek companion",
              f"font-family:'Aside';src:url('fonts/grk-Mynerve-Regular.ttf');unicode-range:{SF.GREEK};" in out)
        check("a polytonic letter Mynerve lacks goes on to Inter, in a rule written after (so it wins)",
              "font-family:'Aside';src:url('fonts/comp-Inter-Regular.otf');unicode-range:U+1F08;" in out
              and out.index("comp-Inter-Regular.otf") > out.index("grk-Mynerve-Regular.ttf"), out[:900])
        check("a face that has Greek (Inter SemiBold) is left alone",
              out.count("font-family:'Big';") == 1, out[:900])
        check("Greek companions are not labelled Cyrillic", "cyr-" not in out)
        check("it says in plain words which font draws the Greek",
              any(n.startswith("Greek letters in Playfair Display") and "NotoSerifDisplay" in n for n in notes), str(notes))
        again, notes2 = SF.add_companions(out, d)
        check("running it twice on a Greek page changes nothing", again == out and notes2 == [])
        out, _ = SF.add_companions(page("Като Σαν", faces), d)
        check("Cyrillic and Greek in one script face: Caveat draws one, Mynerve the other",
              f"font-family:'Aside';src:url('fonts/cyr-Caveat-VF.ttf');unicode-range:{SF.RANGE};" in out
              and f"font-family:'Aside';src:url('fonts/grk-Mynerve-Regular.ttf');unicode-range:{SF.GREEK};" in out, out[:900])
        check("Cyrillic and Greek in a sans face share one Inter rule, both ranges",
              f"font-family:'Cap';src:url('fonts/cyr-Inter-Bold.otf');unicode-range:{SF.RANGE},{SF.GREEK};" in out, out[:900])
    finally:
        shutil.rmtree(d, ignore_errors=True)
    pin = os.path.join(FONTS, "PinyonScript-Regular.ttf")
    runs = [(os.path.basename(p), t) for p, t in SF.split(pin, "Σαν ok")]
    check("Greek is measured on Mynerve, the rest on the face",
          runs == [("Mynerve-Regular.ttf", "Σαν"), ("PinyonScript-Regular.ttf", " ok")], str(runs))
    for face, want in (("PlayfairDisplay-VF.ttf", "NotoSerifDisplay-VF.ttf"), ("InstrumentSerif-Regular.ttf", "NotoSerifDisplay-VF.ttf"),
                       ("PinyonScript-Regular.ttf", "Mynerve-Regular.ttf"), ("Caveat-VF.ttf", "Mynerve-Regular.ttf"),
                       ("Poppins-SemiBold.ttf", "Inter-Bold.otf"), ("Shrikhand-Regular.ttf", "Inter-Black.otf")):
        got = SF.companion_for(os.path.join(FONTS, face), "λ")
        check(f"Greek: {face} -> {want}", got and os.path.basename(got) == want, str(got))
    modern = "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩαβγδεζηθικλμνξοπρσςτυφχψωάέήίόύώΆΈΉΊΌΎΏϊϋΐΰ"
    for comp in ("Mynerve-Regular.ttf", "NotoSerifDisplay-VF.ttf", "Inter-Regular.otf", "Inter-Bold.otf", "Inter-Black.otf"):
        p = os.path.join(FONTS, comp)
        check(f"companion {comp} ships and covers modern Greek", os.path.exists(p) and SF.companion_for(p, modern) is None)
    for comp in ("OFL-Mynerve.txt", "OFL-NotoSerifDisplay.txt"):
        check(f"{comp} ships beside its font", os.path.exists(os.path.join(FONTS, comp)))
    for comp in ("Inter-Regular.otf", "Inter-Bold.otf", "Inter-Black.otf"):
        check(f"{comp} covers polytonic Greek (where Mynerve stops)", SF.companion_for(os.path.join(FONTS, comp), "ἀἄὐῶῆ") is None)

    ugly = os.path.join(FONTS, "UglyDaveAlternates.otf")    # a pack font that is not bundled: checked where it exists
    if os.path.exists(ugly):
        check("· goes with the Greek it punctuates (Ugly Dave has no ·)",
              [os.path.basename(p) for p, _t in SF.split(ugly, "Σαν · ok")] ==
              ["Mynerve-Regular.ttf", "UglyDaveAlternates.otf", "Mynerve-Regular.ttf", "UglyDaveAlternates.otf"],
              str(SF.split(ugly, "Σαν · ok")))
        d = comp_dir([("Aside", "UglyDaveAlternates.otf")])
        try:
            en = page("one · two", [("Aside", "UglyDaveAlternates.otf")])
            check("· on a page with no Greek is left alone (build pages carry it in their own markup)",
                  SF.add_companions(en, d) == (en, []))
        finally:
            shutil.rmtree(d, ignore_errors=True)
    else:
        print("  (Ugly Dave is a pack font that is not bundled here, so its · check was skipped)")

    # the promise: a Greek hook and captions in every shipped pack face (and the stand-ins used when a pack
    # font is missing) are drawn entirely by faces that have every letter, so the browser borrows nothing
    import json
    spec = json.load(open(os.path.join(os.path.dirname(HERE), "creative-vault", "style-packs.json"), encoding="utf-8"))
    files = set()

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                (files.add(v) if k in ("file", "fallback_file") and isinstance(v, str) and v else walk(v))
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(spec.get("packs", {}))
    files |= {"PlayfairDisplay-VF.ttf", "Poppins-SemiBold.ttf", "PinyonScript-Regular.ttf", "InstrumentSerif-Regular.ttf"}
    hook = "ΤΙ ΚΆΝΕΙΣ; Σαν μακραμέ, όταν πλέκεις πολύ-πολύ · «Ἀρχή» 300€ ϊϋΐΰ"
    seen = 0
    for f in sorted(files):
        p = os.path.join(FONTS, f)
        if not os.path.exists(p) or not SF.face_info(p):
            continue                    # a pack font that resolves from her CapCut, not bundled here
        seen += 1
        bad = [(os.path.basename(q), c) for q, t in SF.split(p, hook) for c in t if ord(c) not in SF.face_info(q)[2]]
        check(f"every letter of a Greek hook in {f} is drawn by a face that has it", not bad, str(bad[:6]))
    check("the Greek promise was checked on the shipped pack faces", seen >= 4, str(seen))

    # the editable CapCut route: CapCut draws the text itself, so letters a font lacks get style spans of
    # their own in the same companion the rendered routes use (CapCut counts ranges in UTF-16 units)
    import json, copy, io, contextlib

    def material(text, font):
        st = {"fill": {"content": {"solid": {"color": [1, 1, 1]}, "render_type": "solid"}}, "range": [0, len(text)],
              "size": 14, "shadows": [{"alpha": 0.3}], "font": {"path": font, "id": "x"}}
        return {"content": json.dumps({"styles": [st], "text": text}, ensure_ascii=False)}

    same = lambda p: p                                   # tests hand companions over in place, no CapCut folder
    pop = os.path.join(FONTS, "Poppins-SemiBold.ttf")
    en = material("hello there,\n$300 ’ok’", pop)
    before = copy.deepcopy(en)
    check("CapCut: English text comes back byte for byte",
          SF.capcut_companions(en, pop, resolve=same) is None and en == before)
    m = material("Τι κάνεις; ok", pop)
    note = SF.capcut_companions(m, pop, resolve=same)
    st = json.loads(m["content"])["styles"]
    got = [(s["range"], os.path.basename(s["font"]["path"])) for s in st]
    check("CapCut: Greek words are one companion span (spaces join them), the rest stays the pack face",
          got == [([0, 9], "Inter-Bold.otf"), ([9, 13], "Poppins-SemiBold.ttf")] and note is None, str(got))
    check("CapCut: each span keeps the size, color and effects; only range and font differ",
          all(s["size"] == 14 and s["fill"]["content"]["solid"]["color"] == [1, 1, 1] and s["shadows"] == [{"alpha": 0.3}]
              for s in st) and st[0]["font"]["id"] == "" and st[1]["font"]["id"] == "x", str(st))
    m = material("Σαν πλέκεις", pin)
    SF.capcut_companions(m, pin, resolve=same)
    got = [(s["range"], os.path.basename(s["font"]["path"])) for s in json.loads(m["content"])["styles"]]
    check("CapCut: an all-Greek line is one span in the companion", got == [([0, 11], "Mynerve-Regular.ttf")], str(got))
    m = material("😂 Σαν", pin)
    SF.capcut_companions(m, pin, resolve=same)
    got = [(s["range"], os.path.basename(s["font"]["path"])) for s in json.loads(m["content"])["styles"]]
    check("CapCut: ranges count UTF-16 units, as CapCut does (an emoji is 2)",
          got == [([0, 3], "PinyonScript-Regular.ttf"), ([3, 6], "Mynerve-Regular.ttf")], str(got))
    import capcut_text
    d = {"materials": {"texts": [copy.deepcopy(m)]}}
    capcut_text.sanitize_draft_text(d)
    check("CapCut: the wrap guard keeps those UTF-16 spans (not mistaken for corrupt ones)",
          json.loads(d["materials"]["texts"][0]["content"])["styles"] == json.loads(m["content"])["styles"])
    m = material("Σαν πλέκεις", pin)
    note = SF.capcut_companions(m, pin, resolve=lambda p: None)
    check("CapCut: a companion CapCut cannot load leaves the pack face, named in one plain line",
          bool(note) and note.startswith("Greek letters in Pinyon Script") and "CapCut" in note
          and {os.path.basename(s["font"]["path"]) for s in json.loads(m["content"])["styles"]} == {"PinyonScript-Regular.ttf"},
          str(note))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        for _ in range(3):
            SF.say_capcut(note)
        SF.say_capcut(None)
    check("the CapCut builders say it once per run, not once per text", buf.getvalue().count("Greek letters") == 1,
          buf.getvalue())
    check("CapCut: a font with Greek of its own is left alone",
          SF.capcut_companions(material("Σαν", os.path.join(FONTS, "Inter-SemiBold.ttf")),
                               os.path.join(FONTS, "Inter-SemiBold.ttf"), resolve=same) is None)
    for f in sorted(files):                              # the promise, on the CapCut route too
        p = os.path.join(FONTS, f)
        if not os.path.exists(p) or not SF.face_info(p):
            continue
        m = material(hook, p)
        SF.capcut_companions(m, p, resolve=same)
        c = json.loads(m["content"])
        u = [0]
        for ch in c["text"]:
            u.append(u[-1] + len(ch.encode("utf-16-le")) // 2)
        bad = [(os.path.basename(s["font"]["path"]), ch) for s in c["styles"]
               for i, ch in enumerate(c["text"]) if s["range"][0] <= u[i] < s["range"][1]
               and not ch.isspace() and ord(ch) not in SF.face_info(s["font"]["path"])[2]]
        check(f"CapCut: every letter of a Greek hook in {f} has a span in a face that has it", not bad, str(bad[:6]))
    import design_md
    check("a font is checked for Greek letters when her reels are in Greek", "λ" in design_md.LETTERS.get("el", ""))

    # measuring: English untouched, Cyrillic measured on the face that draws it
    pop = os.path.join(FONTS, "Poppins-SemiBold.ttf")
    check("English text is one run on its own face", SF.split(pop, "hello") == [(pop, "hello")])
    runs = SF.split(pop, "да ok")
    check("mixed text splits by alphabet", [os.path.basename(p) for p, _ in runs] ==
          ["Inter-Bold.otf", "Poppins-SemiBold.ttf"] and runs[0][1] == "да" and runs[1][1] == " ok", str(runs))
    try:
        import PIL  # noqa: F401
        inter = os.path.join(FONTS, "Inter-Bold.otf")
        w = hooksplit._measure("РАЗЛИЧНИ", pop, 100)
        check("a Cyrillic word is measured on its companion",
              abs(w - hooksplit._measure("РАЗЛИЧНИ", inter, 100)) < 0.5, f"{w}")
        from PIL import ImageFont
        check("an English word is measured exactly as before",
              hooksplit._measure("different", pop, 100) == ImageFont.truetype(pop, 100).getlength("different"))
        # A word ALL in Greek is one run, drawn wholly by the companion. pil_width used to skip any single run,
        # so a phrase caption measured "όσο" on the pack face's empty boxes: Editorial's words ran together,
        # another pack's drifted apart (a Greek test reel, 10/19).
        f = ImageFont.truetype(pop, 100)
        w = SF.pil_width(f, "όσο")
        check("a word all in Greek is measured in its companion, not the face's empty boxes",
              w is not None and abs(w - ImageFont.truetype(inter, 100).getlength("όσο")) < 0.5, f"{w}")
        check("an English word still measures as before (pil_width says nothing to change)",
              SF.pil_width(f, "different") is None)
    except ImportError:
        print("  (Pillow not installed here, so the measuring checks were skipped)")

    # Greek in capitals drops its accents and keeps dialytika (Butter's caps hook read ΔΈΚΑ, 10/19).
    import stylepack
    for low, up in (("δέκα λεπτά αρκούν", "ΔΕΚΑ ΛΕΠΤΑ ΑΡΚΟΥΝ"), ("άι", "ΑΪ"), ("αϊτός", "ΑΪΤΟΣ"),
                    ("ωραία", "ΩΡΑΙΑ"), ("ἀρχή", "ΑΡΧΗ"), ("Hello école", "HELLO ÉCOLE")):
        check(f"capitals: {low} -> {up}", stylepack.apply_case(low, "upper") == up, stylepack.apply_case(low, "upper"))

    # Korean: a whole alphabet no Latin companion has, so it has its own three (sans at the face's weight,
    # serif, handwritten), and a syllable Gaegu lacks goes on to Noto Sans KR, never to a system font
    faces = [("Cap", "Poppins-SemiBold.ttf"), ("Head", "PlayfairDisplay-VF.ttf"), ("Aside", "PinyonScript-Regular.ttf"),
             ("Big", "Shrikhand-Regular.ttf")]
    d = comp_dir(faces)
    try:
        en = page("one two three", faces)
        check("an English page is still untouched with the Korean companions in", SF.add_companions(en, d) == (en, []))
        out, notes = SF.add_companions(page("엄마는 오늘도 바빠요 「똠」", faces), d)
        check("Poppins SemiBold gets Noto Sans KR Bold for its Korean",
              f"font-family:'Cap';src:url('fonts/kor-NotoSansKR-Bold.ttf');unicode-range:{SF.KOREAN};" in out, out[:900])
        check("a display face gets Noto Sans KR Black",
              f"font-family:'Big';src:url('fonts/kor-NotoSansKR-Black.ttf');unicode-range:{SF.KOREAN};" in out, out[:900])
        check("Playfair gets Nanum Myeongjo",
              f"font-family:'Head';src:url('fonts/kor-NanumMyeongjo-Regular.ttf');unicode-range:{SF.KOREAN};" in out, out[:900])
        check("a script face gets Gaegu",
              f"font-family:'Aside';src:url('fonts/kor-Gaegu-Regular.ttf');unicode-range:{SF.KOREAN};" in out, out[:900])
        check("a syllable Gaegu lacks (똠) goes on to Noto Sans KR, in a rule written after (so it wins)",
              "font-family:'Aside';src:url('fonts/comp-NotoSansKR-Regular.ttf');unicode-range:" in out
              and "U+B620" in out and out.index("comp-NotoSansKR-Regular.ttf") > out.index("kor-Gaegu-Regular.ttf"), out[:1200])
        check("it says in plain words which font draws the Korean",
              any(n.startswith("Korean letters in Poppins") and "NotoSansKR-Bold" in n for n in notes), str(notes))
        again, notes2 = SF.add_companions(out, d)
        check("running it twice on a Korean page changes nothing", again == out and notes2 == [])
    finally:
        shutil.rmtree(d, ignore_errors=True)
    for comp in ("NotoSansKR-Regular.ttf", "NotoSansKR-Bold.ttf", "NotoSansKR-Black.ttf",
                 "NanumMyeongjo-Regular.ttf", "NanumMyeongjo-Bold.ttf"):
        p = os.path.join(FONTS, comp)
        check(f"companion {comp} ships and covers every Hangul syllable",
              os.path.exists(p) and {c for c in range(0xAC00, 0xD7A4)} <= SF.face_info(p)[2])
    gaegu = os.path.join(FONTS, "Gaegu-Regular.ttf")
    check("Gaegu ships and covers everyday Korean", os.path.exists(gaegu) and SF.companion_for(gaegu, "엄마는 오늘도 바빠요") is None)
    for comp in ("OFL-NotoSansKR.txt", "OFL-NanumMyeongjo.txt", "OFL-Gaegu.txt"):
        check(f"{comp} ships beside its font", os.path.exists(os.path.join(FONTS, comp)))
    hook = "엄마의 300만원, 「진짜」 이야기 · 똠방각하 Café"
    seen = 0
    for f in sorted(files):
        p = os.path.join(FONTS, f)
        if not os.path.exists(p) or not SF.face_info(p):
            continue
        seen += 1
        bad = [(os.path.basename(q), c) for q, t in SF.split(p, hook) for c in t
               if not c.isspace() and ord(c) not in SF.face_info(q)[2]]
        check(f"every letter of a Korean hook in {f} is drawn by a face that has it", not bad, str(bad[:6]))
    check("the Korean promise was checked on the shipped pack faces", seen >= 4, str(seen))
    pop = os.path.join(FONTS, "Poppins-SemiBold.ttf")
    runs = [(os.path.basename(p), a, b) for p, a, b in SF.capcut_runs(pop, "엄마 오늘도 ok")]
    check("CapCut route: a Korean line is one span in Noto Sans KR, the English its own",
          runs == [("NotoSansKR-Bold.ttf", 0, 6), ("Poppins-SemiBold.ttf", 6, 9)], str(runs))

    # Haitian Creole: Latin with è ò à (capitals too, for a caps hook). Every letter of a typical Kreyòl hook, in
    # every shipped pack face, is drawn by a face that has it, on the rendered route and the CapCut route.
    hook = "Kòman pou w kòmanse? Pa fè erè sa a! Lè w pa konnen, ou pèdi lajan. KÒMAN À PÈ « Ann ale! » 300 dola"
    seen = 0
    for f in sorted(files):
        p = os.path.join(FONTS, f)
        if not os.path.exists(p) or not SF.face_info(p):
            continue
        seen += 1
        bad = [(os.path.basename(q), c) for q, t in SF.split(p, hook) for c in t
               if not c.isspace() and ord(c) not in SF.face_info(q)[2]]
        check(f"every letter of a Haitian Creole hook in {f} is drawn by a face that has it", not bad, str(bad[:6]))
        m = material(hook, p)
        SF.capcut_companions(m, p, resolve=same)
        c = json.loads(m["content"])
        u = [0]
        for ch in c["text"]:
            u.append(u[-1] + len(ch.encode("utf-16-le")) // 2)
        bad = [(os.path.basename(s["font"]["path"]), ch) for s in c["styles"]
               for i, ch in enumerate(c["text"]) if s["range"][0] <= u[i] < s["range"][1]
               and not ch.isspace() and ord(ch) not in SF.face_info(s["font"]["path"])[2]]
        check(f"CapCut: every letter of a Haitian Creole hook in {f} has a span in a face that has it", not bad, str(bad[:6]))
    check("the Haitian Creole promise was checked on the shipped pack faces", seen >= 4, str(seen))
    check("a font is checked for è ò à when her reels are in Haitian Creole",
          set("èòà") <= set(design_md.LETTERS.get("ht", "")))
    check("capitals: kòman pèdi -> KÒMAN PÈDI", stylepack.apply_case("kòman pèdi", "upper") == "KÒMAN PÈDI")

    if fails:
        print(f"\nFAIL: {len(fails)} check(s) failed")
        sys.exit(1)
    print("\n✓ script_fonts: Cyrillic, Greek, Korean, accented letters (Haitian Creole too) and « » get a matching "
          "companion, English is untouched")


if __name__ == "__main__":
    main()
