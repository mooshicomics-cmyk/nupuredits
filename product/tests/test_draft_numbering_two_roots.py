#!/usr/bin/env python3
"""test_draft_numbering_two_roots.py — on a Mac that keeps the engine out of Movies, versions count her CapCut drafts.

There, the engine builds in its staging folder and reads CapCut's own folder (capcut_store_redirect.lookup_roots).
draft_safety numbered new versions from the staging folder alone, so it could say "Her Reel 1.2" while the draft
landed as 1.3 (the installer moved it past the 1.2 she already had). Names now count across every root, and a name
she already has in CapCut is never built over. Off that route lookup_roots is [CAP], so nothing changes.

Run: python3 product/tests/test_draft_numbering_two_roots.py
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import capcut_store_redirect as R  # noqa: E402
import draft_safety as DS  # noqa: E402


class TwoRoots(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.stage, self.real = os.path.join(self.tmp, "stage"), os.path.join(self.tmp, "real")
        os.makedirs(os.path.join(self.stage, "Her Reel 1.1"))
        os.makedirs(os.path.join(self.real, "Her Reel 1.2"))
        self.saved = (R.lookup_roots, DS.CAP)
        R.lookup_roots = lambda root=None: [self.stage, self.real]
        DS.CAP = self.stage

    def tearDown(self):
        R.lookup_roots, DS.CAP = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_next_version_counts_her_capcut_drafts(self):
        self.assertEqual(DS.next_version("Her Reel"), "Her Reel 1.3")

    def test_a_name_she_has_in_capcut_is_never_built_over(self):
        with self.assertRaises(RuntimeError):
            DS.refuse_replace("Her Reel 1.2")

    def test_off_that_route_only_cap_counts(self):
        R.lookup_roots = lambda root=None: [root or DS.CAP]
        self.assertEqual(DS.next_version("Her Reel"), "Her Reel 1.2")


if __name__ == "__main__":
    unittest.main()
