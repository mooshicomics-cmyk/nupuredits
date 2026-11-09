#!/usr/bin/env python3
"""Buyer problem reports from 2026-10-22, each guarded where it went wrong.

1. THE ROUGH CUT STOPPED AT TRANSCRIPTION ON AN NVIDIA PC. A Windows laptop with an NVIDIA card got the tested set's
   CTranslate2 4.8.1 (the processor-only pin never covered a GPU PC). WhisperX crashed loading on the card (exit
   139), the fallback ran faster-whisper on the processor in the SAME venv, which crashed the same way, and nothing
   came after it. Now: no Windows venv gets 4.8 (ct2_pin, test_tested_speech_pins.py), an existing one is swapped in
   place with its "WhisperX crashed" mark cleared, a faster-whisper crash in WhisperX's venv moves the reel to the
   light faster-whisper venv, and that venv is the light one even beside an NVIDIA card.

The functions run on their own, as written in word-timings.sh, with stand-ins for the tools they call.

Run: python3 product/tests/test_buyer_reports_2026_10_22.py
"""
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
WT = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "word-timings.sh")


def pieces(*names):
    """Each `name() {...}` function or `NAME=` line, exactly as written in word-timings.sh."""
    with open(WT, encoding="utf-8") as fh:
        src = fh.read()
    out = []
    for name in names:
        if name.endswith("()"):
            i = src.index("\n" + name + " {") + 1
            out.append(src[i:src.index("\n}\n", i) + 3])
        else:
            i = src.index("\n" + name) + 1
            out.append(src[i:src.index("\n", i) + 1])
    return "\n".join(out)


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class NvidiaPcTranscriber(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.venv = os.path.join(self.tmp, "whisperx-venv")
        os.makedirs(self.venv)
        self.log = os.path.join(self.tmp, "calls.log")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_sh(self, body):
        script = f'VENV="{self.venv}"; LOG="{self.log}"\ncall() {{ echo "$*" >> "$LOG"; }}\n' + body
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=30)
        calls = []
        if os.path.exists(self.log):
            with open(self.log, encoding="utf-8") as fh:
                calls = fh.read().split("\n")[:-1]
        return r.returncode, calls, r.stderr

    def listen(self, whisperx_rc, fw_rcs, pivot_ok=True, fw_only_mark=False):
        """listen() with WhisperX exiting whisperx_rc and each faster-whisper run exiting the next of fw_rcs."""
        if fw_only_mark:
            open(os.path.join(self.venv, ".whisperx-crashed"), "w", encoding="utf-8").close()
        stubs = f'''
NOFW=0
FW_RCS=({" ".join(str(c) for c in fw_rcs)})
listen_whisperx() {{ call whisperx; return {whisperx_rc}; }}
listen_faster_whisper() {{ local rc="${{FW_RCS[0]}}"; FW_RCS=("${{FW_RCS[@]:1}}"); call "faster-whisper on $([ "$NOFW" = 1 ] && echo own || echo shared) venv"; return "$rc"; }}
pivot_to_faster_whisper() {{ call "pivot: $1"; NOFW=1; return {0 if pivot_ok else 1}; }}
can_hear_without_whisperx() {{ return 0; }}
retry_on_measured_set() {{ return 1; }}
note_newer_set_heard() {{ :; }}
note_fallback() {{ :; }}
'''
        return self.run_sh(pieces('FW_ONLY_MARK=', 'listen_faster_whisper_here()', 'listen()') + stubs + "listen\n")

    def test_her_report_both_crash_then_the_light_venv_hears_it(self):
        rc, calls, err = self.listen(139, [139, 0])
        self.assertEqual(rc, 0, err)
        self.assertEqual(calls, ["whisperx", "faster-whisper on shared venv",
                                 "pivot: faster-whisper crashed in the same speech tools too (exit 139)",
                                 "faster-whisper on own venv"])

    def test_a_later_reel_on_the_crashed_mark_gets_the_same_way_out(self):
        rc, calls, err = self.listen(0, [139, 0], fw_only_mark=True)
        self.assertEqual(rc, 0, err)
        self.assertEqual(calls[0], "faster-whisper on shared venv", "WhisperX is skipped behind the mark")
        self.assertEqual(calls[-1], "faster-whisper on own venv")

    def test_a_shared_venv_that_works_is_never_left(self):
        rc, calls, _ = self.listen(139, [0])
        self.assertEqual((rc, calls), (0, ["whisperx", "faster-whisper on shared venv"]))

    def test_a_python_error_is_not_a_crash_and_is_said(self):
        rc, calls, _ = self.listen(139, [1])
        self.assertEqual(rc, 1)
        self.assertFalse(any(c.startswith("pivot") for c in calls), calls)

    def test_a_light_venv_that_will_not_build_stops_with_the_crash(self):
        rc, calls, _ = self.listen(139, [139], pivot_ok=False)
        self.assertEqual(rc, 139)
        self.assertNotIn("faster-whisper on own venv", calls)

    def pin(self, ct2, cuda=1, nofw=0, sac="", windows=1, install_ok=True):
        open(os.path.join(self.venv, ".whisperx-crashed"), "w", encoding="utf-8").close()
        stubs = f'''
WINDOWS_SHELL={windows}; GPU_CUDA={cuda}; NOFW={nofw}; SAC_PINS="{sac}"; CT2_WIN_CPU_MEASURED=0; PYBIN=py
venv_ct2() {{ echo "{ct2}"; }}
ensure_uv() {{ :; }}
uv() {{ call "uv $*"; return {0 if install_ok else 1}; }}
put_measured_win_cpu_set() {{ call measured-set; }}
'''
        body = pieces('FW_ONLY_MARK=', 'CT2_WIN_CPU_PIN=', 'CT2_WIN_CPU_TRY=', 'pin_ct2_in_place()') + stubs
        rc, calls, err = self.run_sh(body + "pin_ct2_in_place\n")
        self.assertEqual(rc, 0, err)
        return calls, os.path.exists(os.path.join(self.venv, ".whisperx-crashed"))

    def test_her_venv_is_swapped_to_4_7_2_and_whisperx_gets_its_turn_again(self):
        calls, mark = self.pin("4.8.1")
        self.assertEqual(calls, ['uv pip install --python py ctranslate2==4.7.2'])
        self.assertFalse(mark, "the crash was 4.8's: the mark goes")

    def test_a_swap_that_fails_keeps_the_mark(self):
        calls, mark = self.pin("4.8.1", install_ok=False)
        self.assertTrue(mark)

    def test_an_nvidia_venv_already_off_4_8_is_left_alone(self):
        self.assertEqual(self.pin("4.7.2"), ([], True))
        self.assertEqual(self.pin("4.5.0"), ([], True))

    def test_the_light_venv_goes_to_the_measured_4_4_0(self):
        calls, _ = self.pin("4.8.1", nofw=1)
        self.assertEqual(calls, ['uv pip install --python py ctranslate2==4.4.0 setuptools<81'])

    def test_smart_app_control_and_a_mac_are_never_touched(self):
        self.assertEqual(self.pin("4.8.1", sac="ctranslate2==4.5.0")[0], [])
        self.assertEqual(self.pin("4.8.1", windows=0)[0], [])

    def test_the_light_venv_beside_an_nvidia_card_installs_no_cuda_torch(self):
        stubs = '''
GPU_CUDA=1; NOFW=1; WINDOWS_SHELL=1; SAC_PINS=""; VENV_MODE=cpu
venv_py() { echo py; }
uname() { echo MINGW64_NT-10.0; }
pick_cuda_channel() { call pick_cuda_channel; }
mac_intel_onnx_pin() { :; }
mac_intel_extra_pins() { :; }
uv() { call "uv $*"; }
'''
        body = pieces('CT2_WIN_CPU_PIN=', 'CT2_WIN_CPU_TRY=', 'ct2_pin()', 'install_listener()') + stubs
        rc, calls, err = self.run_sh(body + "install_listener\n")
        self.assertEqual(rc, 0, err)
        self.assertEqual(calls, ["uv pip install --python py faster-whisper ctranslate2==4.4.0 setuptools<81"])


if __name__ == "__main__":
    unittest.main()
