#!/usr/bin/env python3
"""An Apple-chip Mac is never called Intel, even from a shell whose PATH has no /usr/sbin (a buyer, 2026-10-22).

A buyer on an M1 sent a problem report that said "Computer: Mac (arm64)" and, a few lines down in the setup part,
"transcription speed: an Intel Mac". check-setup.sh read the chip for that one line from sysctl alone, before
uname, and sysctl lives in /usr/sbin: from a shell started with PATH=/usr/bin:/bin it is not found, the reading is
empty, and empty meant Intel. The same empty reading blanked the report's "Chip:" line. Now that line uses the one
answer the rest of the check gives (mac_arch_class), and scripts/_mac-arch.sh finds sysctl in /usr/sbin itself.

Run: python3 product/tests/test_chip_on_short_path.py
"""
import os, platform, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
APPLE_CHIP = (sys.platform == "darwin" and os.path.exists("/usr/sbin/sysctl")
              and subprocess.run(["/usr/sbin/sysctl", "-n", "hw.optional.arm64"], capture_output=True,
                                 text=True).stdout.strip() == "1")
SHORT_PATH = "/usr/bin:/bin"


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def sh(script, path, cwd=ROOT):
    env = dict(os.environ, PATH=path)
    r = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, encoding="utf-8", env=env,
                       cwd=cwd, timeout=300)
    return r.returncode, r.stdout, r.stderr


def speed_block():
    """check-setup.sh's "transcription speed" lines, as they are in the file."""
    cs = read("check-setup.sh")
    start = cs.index("# How fast transcription will be.")
    end = cs.index("\nfi\n", start) + 4
    return cs[start:end]


class TheSpeedLineFollowsTheChipClass(unittest.TestCase):
    """Runs anywhere: the block, given each class, with no sysctl in reach at all."""
    def run_block(self, cls):
        script = ('ok(){ echo "OK $1: $2"; }; note(){ echo "NOTE $1: $2"; }; '
                  f'command(){{ return 1; }}; OS=mac; MACCLASS={cls}\n' + speed_block())
        rc, out, err = sh(script, SHORT_PATH)
        self.assertEqual(rc, 0, err)
        return out

    def test_an_apple_chip_is_the_fast_path(self):
        out = self.run_block("arm64")
        self.assertIn("OK transcription speed: Apple Silicon", out)
        self.assertNotIn("Intel Mac", out)

    def test_rosetta_is_never_called_an_intel_mac(self):
        out = self.run_block("rosetta")
        self.assertIn("Rosetta", out)
        self.assertNotIn("an Intel Mac", out)

    def test_a_real_intel_mac_still_hears_it(self):
        self.assertIn("NOTE transcription speed: an Intel Mac", self.run_block("intel"))

    def test_the_block_never_reads_the_chip_itself(self):
        block = speed_block()
        code = [ln for ln in block.splitlines() if not ln.lstrip().startswith("#")]
        self.assertFalse([ln for ln in code if "sysctl" in ln or "uname" in ln], "the chip comes from MACCLASS only")
        self.assertIn('"$MACCLASS" = arm64', block)


class TheArchHelperFindsSysctl(unittest.TestCase):
    def test_every_reading_goes_through_mac_sysctl(self):
        src = read("scripts/_mac-arch.sh")
        body = src[src.index("mac_sysctl() {"):]
        body = body[body.index("\n}\n") + 3:]
        code = [ln for ln in body.splitlines() if not ln.lstrip().startswith("#")]
        self.assertFalse([ln for ln in code if "sysctl -n" in ln and "mac_sysctl -n" not in ln], "a bare sysctl")

    def test_a_stand_in_on_path_still_answers_first(self):
        """The route tests fake the machine with a sysctl on PATH; it must keep winning over /usr/sbin."""
        with tempfile.TemporaryDirectory() as tmp:
            for name, body in (("uname", 'case "$1" in -m) echo x86_64;; *) echo Darwin;; esac'),
                               ("sysctl", "exit 1")):
                p = os.path.join(tmp, name)
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(f"#!/bin/sh\n{body}\n")
                os.chmod(p, 0o755)
            rc, out, err = sh(". scripts/_mac-arch.sh; mac_arch_class", f"{tmp}:{SHORT_PATH}")
            self.assertEqual(out.strip(), "intel", err)

    @unittest.skipUnless(APPLE_CHIP, "needs an Apple-chip Mac")
    def test_rosetta_found_with_sysctl_off_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "uname")                           # this shell runs translated: x86_64
            with open(p, "w", encoding="utf-8") as fh:
                fh.write('#!/bin/sh\ncase "$1" in -m) echo x86_64;; *) echo Darwin;; esac\n')
            os.chmod(p, 0o755)
            rc, out, err = sh(". scripts/_mac-arch.sh; mac_arch_class", f"{tmp}:{SHORT_PATH}")
            self.assertEqual(out.strip(), "rosetta", err)

    @unittest.skipUnless(APPLE_CHIP, "needs an Apple-chip Mac")
    def test_the_chip_line_is_filled_with_sysctl_off_path(self):
        rc, out, err = sh(". scripts/_mac-arch.sh; mac_arch_class; mac_cpu_brand", SHORT_PATH)
        lines = out.strip().splitlines()
        self.assertEqual(lines[0], "arm64" if platform.machine() == "arm64" else "rosetta")
        self.assertTrue(len(lines) > 1 and lines[1].strip(), f"the chip is named: {out!r} {err}")


@unittest.skipUnless(APPLE_CHIP and platform.machine() == "arm64", "needs an Apple-chip Mac, run natively")
class TheWholeCheckOnAShortPath(unittest.TestCase):
    def test_check_setup_never_says_intel(self):
        rc, out, err = sh("bash check-setup.sh", SHORT_PATH)
        said = out + err
        self.assertIn("transcription speed: Apple Silicon", said)
        self.assertNotIn("an Intel Mac", said)


if __name__ == "__main__":
    unittest.main()
