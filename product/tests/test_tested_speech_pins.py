#!/usr/bin/env python3
"""test_tested_speech_pins.py — the speech tools install the set measured working, on every machine that can take it.

Before this, only whisperx and torch were pinned on a Mac or an NVIDIA PC; CTranslate2, pyannote, onnxruntime,
PyAV and torchcodec came in at whatever was newest the day she set up (CTranslate2 4.8.3 the day after its
release). word-timings.sh tested_pins() now adds the set measured with whisperx 3.8.6 + torch 2.8, and only where
it installs: onnxruntime 1.27 / PyAV 18 have wheels for Python 3.11 only and, on an Apple-chip Mac, macOS 14+.
The processor-only Windows set and the Smart App Control set keep their own measured pins; an Intel Mac never
installs whisperx. The retry after a failed install (fallback_note) drops the set.

Run: python3 product/tests/test_tested_speech_pins.py
"""
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
WT = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "word-timings.sh")
BASE = "ctranslate2==4.8.1 pyannote.audio==4.0.7 torchcodec==0.7.0"
WIDE = BASE + " onnxruntime==1.27.0 av==18.0.0"


def functions():
    """The pin helpers as written in word-timings.sh, run on their own (the script itself does real work)."""
    src = open(WT, encoding="utf-8").read()
    keep = []
    for name in ("CT2_WIN_CPU_PIN=", "CT2_WIN_CPU_TRY=", "ct2_pin()", "TORCH_PIN=", "whisperx_pin()", "TESTED_SET=", "TESTED_SET_311=",
                 "tested_pins()"):
        i = src.index(name)
        if name.endswith("()"):
            j = src.index("\n}\n", i) + 3
        else:
            j = src.index("\n", i) + 1
        keep.append(src[i:j])
    return "\n".join(keep)


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class TestedPins(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def stub(self, name, body):
        p = os.path.join(self.bin, name)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/bash\n" + body + "\n")
        os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)

    def pins(self, kernel, machine="x86_64", macos="15.1", py311=True, windows=0, cuda=0, sac=""):
        self.stub("uname", f'case "$1" in -s) echo {kernel};; -m) echo {machine};; *) echo {kernel};; esac')
        self.stub("sw_vers", f'echo {macos}')
        self.stub("fakepy", f'exit {0 if py311 else 1}')
        script = (functions() + f'\nWINDOWS_SHELL={windows}; GPU_CUDA={cuda}; SAC_PINS="{sac}"\n'
                  f'tested_pins "{self.bin}/fakepy"\n')
        env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ.get("PATH", ""))
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return " ".join(r.stdout.split())

    def test_apple_chip_mac_on_macos_14_plus_gets_the_whole_set(self):
        self.assertEqual(self.pins("Darwin", "arm64", "15.1"), WIDE)

    def test_apple_chip_mac_on_macos_13_leaves_onnxruntime_and_av_to_resolve(self):
        self.assertEqual(self.pins("Darwin", "arm64", "13.6"), BASE)

    def test_intel_mac_gets_nothing(self):
        self.assertEqual(self.pins("Darwin", "x86_64", "13.6"), "")

    def test_nvidia_pc_gets_the_set_without_its_ctranslate2(self):
        # 4.8.x crashes loading on a PC (a buyer's NVIDIA laptop, 2026-10-22): ct2_pin brings 4.7.2 instead.
        self.assertEqual(self.pins("MINGW64_NT-10.0", windows=1, cuda=1), WIDE.replace("ctranslate2==4.8.1 ", ""))

    def test_venv_not_on_311_leaves_onnxruntime_and_av_to_resolve(self):
        self.assertEqual(self.pins("MINGW64_NT-10.0", windows=1, cuda=1, py311=False),
                         BASE.replace("ctranslate2==4.8.1 ", ""))
        self.assertEqual(self.pins("Darwin", "arm64", "15.1", py311=False), BASE)

    def test_processor_only_pc_keeps_its_own_measured_pins(self):
        self.assertEqual(self.pins("MINGW64_NT-10.0", windows=1, cuda=0), "")

    def test_smart_app_control_keeps_its_own_measured_pins(self):
        self.assertEqual(self.pins("MINGW64_NT-10.0", windows=1, cuda=1, sac="ctranslate2==4.5.0"), "")

    def ct2(self, windows=1, cuda=0, sac="", nofw=0, measured=0):
        script = (functions() + f'\nWINDOWS_SHELL={windows}; GPU_CUDA={cuda}; SAC_PINS="{sac}"; NOFW={nofw}; '
                  f'CT2_WIN_CPU_MEASURED={measured}\nct2_pin\n')
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_no_pc_ever_gets_ctranslate2_4_8(self):
        self.assertEqual(self.ct2(cuda=1), "ctranslate2==4.7.2", "NVIDIA PC: WhisperX venv")
        self.assertEqual(self.ct2(cuda=1, measured=1), "ctranslate2==4.7.2", "4.4.0 is not built for cuDNN 9")
        self.assertEqual(self.ct2(cuda=1, nofw=1), "ctranslate2==4.4.0 setuptools<81", "NVIDIA PC: faster-whisper venv")
        self.assertEqual(self.ct2(cuda=0), "ctranslate2==4.7.2")
        self.assertEqual(self.ct2(cuda=0, measured=1), "ctranslate2==4.4.0 setuptools<81")
        self.assertEqual(self.ct2(cuda=0, nofw=1), "ctranslate2==4.4.0 setuptools<81")
        self.assertEqual(self.ct2(cuda=1, sac="ctranslate2==4.5.0"), "", "Smart App Control keeps its own")
        self.assertEqual(self.ct2(windows=0, cuda=1), "", "a Mac or Linux keeps the tested set")

    def test_nvidia_install_carries_the_pin(self):
        src = open(WT, encoding="utf-8").read()
        body = src[src.index("install_listener() {"):]
        body = body[:body.index("\n}\n")]
        cuda = body[body.index('if [ "$GPU_CUDA" -eq 1 ] && [ "$NOFW" != 1 ]; then\n'):body.index("elif [ \"$NOFW\" = 1 ]")]
        lines = [l for l in cuda.splitlines() if "uv pip install" in l and "whisperx" in l]
        self.assertEqual(len(lines), 2, lines)
        self.assertTrue(all("$(ct2_pin)" in l for l in lines), lines)

    def test_only_first_attempts_carry_the_set(self):
        src = open(WT, encoding="utf-8").read()
        first = re.findall(r"uv pip install [^\n]*\$\(whisperx_pin\)[^\n]*", src)
        self.assertEqual(len(first), 3)
        self.assertTrue(all("tested_pins" in line for line in first), first)
        retries = re.findall(r"uv pip install --python \"\$PYBIN\" whisperx [^\n]*", src)
        self.assertTrue(retries and not any("tested_pins" in line for line in retries), retries)


if __name__ == "__main__":
    unittest.main()
