#!/usr/bin/env python3
"""Every video segment must reach CapCut tagged SDR.

A segment tagged HDR (hdr_settings mode 1 or 4) makes CapCut apply HDR treatment to bt709 footage,
and the clip renders washed out. That shipped to a buyer once. This test exists so it cannot come
back quietly: it checks the guardrail AND the two places a segment is born, because the bug the
first time was that the correction lived downstream of the default.
"""
import json, os, re, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
ROOT = os.path.dirname(PRODUCT)
sys.path.insert(0, PRODUCT)

import capcut_color as cc


class GuardrailSweep(unittest.TestCase):
    def draft(self):
        return {"tracks": [
            {"type": "video", "segments": [
                {"id": "a", "hdr_settings": {"mode": 1, "intensity": 1.0, "nits": 1000}},
                {"id": "b", "hdr_settings": {"mode": 4, "intensity": 1.0, "nits": 1000}},
                {"id": "c", "hdr_settings": {"mode": 0, "intensity": 1.0, "nits": 203}},
                {"id": "d"},
            ]},
            {"type": "text", "segments": [{"id": "t1"}]},
            {"type": "audio", "segments": [{"id": "m1", "hdr_settings": None}]},
        ]}

    def test_corrects_every_hdr_mode_and_a_missing_key(self):
        d = self.draft()
        self.assertEqual(cc.enforce_sdr(d), 3)
        for seg in d["tracks"][0]["segments"]:
            self.assertEqual(seg["hdr_settings"]["mode"], 0, seg["id"])
            self.assertEqual(seg["hdr_settings"]["nits"], 203, seg["id"])

    def test_leaves_non_video_tracks_alone(self):
        d = self.draft()
        cc.enforce_sdr(d)
        self.assertNotIn("hdr_settings", d["tracks"][1]["segments"][0])
        self.assertIsNone(d["tracks"][2]["segments"][0]["hdr_settings"])

    def test_idempotent(self):
        d = self.draft()
        cc.enforce_sdr(d)
        self.assertEqual(cc.enforce_sdr(d), 0)

    def test_segments_do_not_share_one_dict(self):
        d = self.draft()
        cc.enforce_sdr(d)
        vid = d["tracks"][0]["segments"]
        vid[0]["hdr_settings"]["nits"] = 999
        self.assertEqual(vid[1]["hdr_settings"]["nits"], 203)

    def test_survives_a_malformed_draft(self):
        for junk in ({}, {"tracks": None}, {"tracks": [{"type": "video", "segments": None}]}):
            self.assertEqual(cc.enforce_sdr(junk), 0)


class EveryDraftWriterSweeps(unittest.TestCase):
    """ISS-13: the overlay, GIF, slip and compound writers copied the footage segment's hdr_settings and never
    called the sweep, so a clip went washed out after an edit. Every draft writer calls
    capcut_ripple.enforce_maintrack_ripple() (ship gate 12), so the sweep lives there."""

    def draft(self):
        return {"tracks": [
            {"type": "video", "segments": [
                {"id": "f1", "hdr_settings": {"mode": 0, "intensity": 1.0, "nits": 203}},
                {"id": "f2", "hdr_settings": {"mode": 0, "intensity": 1.0, "nits": 203}},
            ]},
            {"type": "video", "segments": [
                {"id": "ov", "hdr_settings": {"mode": 1, "intensity": 1.0, "nits": 1000}},
            ]},
            {"type": "audio", "segments": [{"id": "a1"}]},
        ], "materials": {}, "config": {}}

    def test_ripple_corrects_a_mode_1_segment(self):
        from capcut_ripple import enforce_maintrack_ripple
        d = enforce_maintrack_ripple(self.draft())
        ov = d["tracks"][1]["segments"][0]
        self.assertEqual(ov["hdr_settings"]["mode"], 0)
        self.assertEqual(ov["hdr_settings"]["nits"], 203)
        self.assertNotIn("hdr_settings", d["tracks"][2]["segments"][0])

    def test_ripple_survives_odd_shapes(self):
        from capcut_ripple import enforce_maintrack_ripple
        d = self.draft()
        d["tracks"][1]["segments"].append("not a segment")
        d["tracks"][1]["segments"].append({"id": "nohdr"})
        enforce_maintrack_ripple(d)
        self.assertEqual(d["tracks"][1]["segments"][2]["hdr_settings"]["mode"], 0)

    def test_compound_inner_draft_is_sdr(self):
        import tempfile
        import capcut_compound
        seg = {"id": "s1", "material_id": "v1", "extra_material_refs": [],
               "target_timerange": {"start": 0, "duration": 1_000_000},
               "source_timerange": {"start": 0, "duration": 1_000_000},
               "hdr_settings": {"mode": 4, "intensity": 1.0, "nits": 1000}}
        draft = {"canvas_config": {"width": 1080, "height": 1920},
                 "materials": {"videos": [{"id": "v1", "path": "clip.mp4"}]},
                 "tracks": [{"type": "video", "segments": [seg]}]}
        with tempfile.TemporaryDirectory() as tmp:
            comp_id = capcut_compound.make_compound(draft, seg, tmp, 2_000_000, 0, 1)
            entry = next(x for x in draft["materials"]["drafts"] if x["id"] == comp_id)
            inner_seg = entry["draft"]["tracks"][0]["segments"][0]
            self.assertEqual(inner_seg["hdr_settings"]["mode"], 0)
            sub = os.path.join(tmp, "subdraft", entry["draft"]["id"], "draft_content.json")
            with open(sub, encoding="utf-8") as fh:
                on_disk = json.load(fh)
            self.assertEqual(on_disk["tracks"][0]["segments"][0]["hdr_settings"]["mode"], 0)


class BornSDR(unittest.TestCase):
    """The default at each write site. If one of these fails, a path that skips the guardrail ships
    washed-out footage again, which is exactly how this reached a buyer the first time."""

    WRITE_SITES = (
        "product/engine/VectCutAPI/pyJianYingDraft/video_segment.py",
        "workflows/capcut-live.py",
        "workflows/capcut-export/templates/tpl_vseg.json",         # build-overlay.py clones this
        "workflows/capcut-export/templates/tpl_gif_segment.json",  # gif_dropins.py clones this
    )

    def test_no_write_site_is_born_hdr(self):
        for rel in self.WRITE_SITES:
            path = os.path.join(ROOT, rel)
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
            for m in re.finditer(r'"hdr_settings"\s*:\s*\{[^}]*\}', src):
                blob = m.group(0)
                mode = re.search(r'"mode"\s*:\s*(\d+)', blob)
                self.assertIsNotNone(mode, f"{rel}: hdr_settings with no mode: {blob}")
                self.assertEqual(
                    mode.group(1), "0",
                    f"{rel} writes hdr_settings mode {mode.group(1)}. Segments must be born SDR. "
                    f"See product/capcut_color.py.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
