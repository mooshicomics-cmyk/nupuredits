#!/usr/bin/env python3
"""test_win_cpu_newer_speech.py — a processor-only Windows PC tries CTranslate2 4.7.2 + whisperx 3.8.6, and can
never end up worse off than the measured 4.4.0 + whisperx 3.4.5.

CTranslate2 4.8.x segfaults loading any Whisper model on a buyer's 13th-gen Intel laptop; 4.8.0 turned on
PACKED_GEMM for Intel MKL, and 4.7.2 is the last release before it. 4.7.2 lets whisperx 3.8.6 (the tested set)
in, but nobody has run it on that laptop, so word-timings.sh:
  * installs 4.7.2 + whisperx 3.8.6 + torch 2.8 on a new (or rebuilt) processor-only venv;
  * when that install fails, or the first WhisperX load crashes (139 and friends) or errors, puts 4.4.0 +
    whisperx 3.4.5 in the same venv, hears the reel again, logs the switch and marks "<venv>.ct2-4.4", so every
    later build goes straight to the measured set;
  * keeps the faster-whisper pivot working when the measured set crashes too;
  * leaves a working venv already on 4.4.0 exactly as it is;
  * changes nothing for Smart App Control, an NVIDIA PC or a Mac.

Everything runs on a throwaway copy of the engine with stand-ins for uname, uv, nvidia-smi and the venv's Python
(which "crashes" with exit 139 on the CTranslate2 versions it is told to), so nothing is downloaded.

Run:  python3 product/tests/test_win_cpu_newer_speech.py
"""
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
WT_DIR = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts")
WT = os.path.join(WT_DIR, "word-timings.sh")
JOB = "tx-job"   # the stand-in job word-timings.sh is pointed at
SYS_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
POSIX = os.name != "nt" and shutil.which("bash") is not None

TRY = "ctranslate2==4.7.2"
MEASURED = "ctranslate2==4.4.0 setuptools<81"


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def lines(path):
    return read(path).splitlines() if os.path.exists(path) else []


def write_exec(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


# The venv's Python. What is "installed" lives in files beside it, written by the uv stand-in. A WhisperX run
# (the script on stdin, with a words file to write) exits 139 when the installed CTranslate2 is one of $CRASH_CT2; faster-whisper's script
# always works.
VENV_PY = r"""#!/bin/bash
v="$(cd "$(dirname "$0")/.." && pwd)"
printf '%s\n' "$*" >> "$VENV_LOG"
ct2="$(cat "$v/.fake-ct2" 2>/dev/null)"
case "$1" in
  -)
    cat >/dev/null
    [ -n "${2:-}" ] || exit 0   # the torch drift probe: no words file, nothing drifted
    for c in ${CRASH_CT2:-}; do
      if [ "$c" = "$ct2" ]; then echo "whisperx-run ct2=$ct2 crashed" >> "$VENV_LOG"; exit 139; fi
    done
    echo "whisperx-run ct2=$ct2 ok" >> "$VENV_LOG"
    printf '{"clips": []}\n' > "$2"; exit 0 ;;
  -c)
    case "$2" in
      *torch.cuda*) exit 1 ;;
      *ctranslate2*) [ -n "$ct2" ] && echo "$ct2"; exit 0 ;;
      *"import whisperx"*) [ -e "$v/.fake-whisperx" ]; exit $? ;;
      *"import faster_whisper"*) [ -e "$v/.fake-fw" ]; exit $? ;;
    esac
    exit 0 ;;
  -m) exit 0 ;;
  *transcribe-nofw.py)
    echo "faster-whisper-run ct2=$ct2" >> "$VENV_LOG"
    printf '{"clips": []}\n' > "$2"; exit 0 ;;
esac
exit 0
"""

# uv: `uv venv DIR` makes a venv holding the stand-in; `uv pip install` records what went in, and fails without
# installing anything when it names a CTranslate2 listed in $FAIL_CT2.
UV = r"""#!/bin/bash
printf 'uv %s\n' "$*" >> "$CALL_LOG"
if [ "$1" = venv ]; then mkdir -p "$2/bin"; cp "$VENVPY_SRC" "$2/bin/python"; exit 0; fi
[ "$1" = pip ] && [ "$2" = install ] || exit 0
shift 2
py=""; ct2=""; wx=0; fw=0
while [ $# -gt 0 ]; do
  case "$1" in
    --python) py="$2"; shift ;;
    ctranslate2==*) ct2="${1#ctranslate2==}" ;;
    whisperx|whisperx==*) wx=1 ;;
    faster-whisper) fw=1 ;;
  esac
  shift
done
for f in ${FAIL_CT2:-}; do [ "$f" = "$ct2" ] && { echo "error: no solution (stand-in)" >&2; exit 1; }; done
v="$(cd "$(dirname "$py")/.." && pwd)"
[ -n "$ct2" ] && echo "$ct2" > "$v/.fake-ct2"
[ "$wx" = 1 ] && { : > "$v/.fake-whisperx"; : > "$v/.fake-fw"; [ -n "$ct2" ] || echo 4.8.3 > "$v/.fake-ct2"; }
[ "$fw" = 1 ] && : > "$v/.fake-fw"
exit 0
"""

WINDOWS_UNAME = "#!/bin/sh\ncase \"$1\" in -m) echo x86_64 ;; *) echo MINGW64_NT-10.0-26200 ;; esac\n"


@unittest.skipUnless(POSIX, "needs bash and a POSIX shell for the stand-ins")
class ProcessorOnlyPc(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        t = self.tmp
        self.eng = os.path.join(t, "engine")
        for rel in ("scripts/_python3-shim.sh", "scripts/_mac-arch.sh", "scripts/_win-sac.sh",
                    "scripts/transcribe-nofw.py"):
            os.makedirs(os.path.dirname(os.path.join(self.eng, rel)), exist_ok=True)
            shutil.copy(os.path.join(ROOT, rel), os.path.join(self.eng, rel))
        with open(os.path.join(self.eng, "scripts", "_path-shim.sh"), "w", encoding="utf-8") as fh:
            fh.write("# stand-in: no PATH repair\n")
        shutil.copytree(WT_DIR, os.path.join(self.eng, ".claude", "skills", "rough-cut", "scripts"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        self.wt = os.path.join(self.eng, ".claude", "skills", "rough-cut", "scripts", "word-timings.sh")
        self.home = os.path.join(t, "home")
        self.fake = os.path.join(t, "bin")
        self.venvpy = os.path.join(t, "venvpy")
        write_exec(self.venvpy, VENV_PY)
        write_exec(os.path.join(self.fake, "uv"), UV)
        write_exec(os.path.join(self.fake, "nvidia-smi"), "#!/bin/sh\nexit 1\n")
        write_exec(os.path.join(self.fake, "uname"), WINDOWS_UNAME)
        # python3 for the shims' scratch-folder question: the interpreter running this test
        write_exec(os.path.join(self.fake, "python3"), f"#!/bin/sh\nexec '{sys.executable}' \"$@\"\n")
        self.venv = os.path.join(self.home, ".cache", "reels-editing-engine", "whisperx-venv")
        self.mark = self.venv + ".ct2-4.4"
        self.heard = self.venv + ".ct2-4.7-heard"
        self.call_log = os.path.join(t, "calls.log")
        self.venv_log = os.path.join(t, "venv.log")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_wt(self, extra=None):
        job = os.path.join(self.eng, "projects", JOB)
        shutil.rmtree(job, ignore_errors=True)
        os.makedirs(os.path.join(job, "raw"))
        open(os.path.join(job, "raw", "IMG_0001.MOV"), "w", encoding="utf-8").close()
        for p in (self.call_log, self.venv_log):
            if os.path.exists(p):
                os.remove(p)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("REELS_ENGINE", "UV_"))}
        env.update(HOME=self.home, TMPDIR=os.path.join(self.tmp, "scratch"), PATH=self.fake + ":" + SYS_PATH,
                   CALL_LOG=self.call_log, VENV_LOG=self.venv_log, VENVPY_SRC=self.venvpy)
        env.update(extra or {})
        os.makedirs(env["TMPDIR"], exist_ok=True)
        r = subprocess.run(["bash", self.wt, os.path.join("projects", JOB), "--force"], cwd=self.eng, env=env,
                           capture_output=True, text=True, encoding="utf-8", timeout=120)
        return r, lines(self.call_log), lines(self.venv_log)

    def installs(self, calls):
        return [c for c in calls if c.startswith("uv pip install")]

    def fallbacks_log(self):
        return lines(os.path.join(self.eng, "_local", "fallbacks.log"))

    def ct2(self):
        return read(os.path.join(self.venv, ".fake-ct2")).strip()

    def words_saved(self):
        return os.path.exists(os.path.join(self.eng, "projects", JOB, "transcript", "words.json"))

    def existing_venv(self, ct2, heard=False):
        """A finished processor venv an earlier version (or an earlier run) built."""
        os.makedirs(os.path.join(self.venv, "bin"))
        shutil.copy(self.venvpy, os.path.join(self.venv, "bin", "python"))
        for name, body in ((".fake-ct2", ct2 + "\n"), (".fake-whisperx", ""), (".fake-fw", ""),
                           (".speech-tools-ready", "cpu\n"), (".deps-ok", "cpu\n")):
            with open(os.path.join(self.venv, name), "w", encoding="utf-8") as fh:
                fh.write(body)
        if heard:
            open(self.heard, "w", encoding="utf-8").close()

    # ── a new venv ──

    def test_new_venv_tries_the_newer_set_and_keeps_it_when_it_works(self):
        r, calls, venv_calls = self.run_wt()
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        first = [c for c in self.installs(calls) if "whisperx==" in c][0]
        for pin in ("whisperx==3.8.6", "torch==2.8.0", "torchaudio==2.8.0", TRY):
            self.assertIn(pin, first)
        self.assertNotIn("ctranslate2==4.8.1", first, "the tested set's CTranslate2 is the line that crashes here")
        self.assertNotIn("setuptools<81", first)
        self.assertEqual(self.ct2(), "4.7.2")
        self.assertIn("whisperx-run ct2=4.7.2 ok", venv_calls)
        self.assertTrue(self.words_saved())
        self.assertFalse(os.path.exists(self.mark))
        self.assertTrue(os.path.exists(self.heard), "the first reel heard on 4.7.2 makes it this PC's set")
        self.assertEqual(self.fallbacks_log(), [])

    def test_a_crash_on_the_first_load_moves_to_the_measured_set_in_the_same_run_and_remembers(self):
        r, calls, venv_calls = self.run_wt({"CRASH_CT2": "4.7.2"})
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertEqual([c for c in venv_calls if c.startswith("whisperx-run")],
                         ["whisperx-run ct2=4.7.2 crashed", "whisperx-run ct2=4.4.0 ok"])
        back = [c for c in self.installs(calls) if "whisperx==3.4.5" in c]
        self.assertTrue(back, calls)
        self.assertIn("torch==2.8.0 torchaudio==2.8.0", back[0])
        self.assertIn(MEASURED, back[0])
        self.assertEqual(self.ct2(), "4.4.0")
        self.assertTrue(self.words_saved())
        self.assertTrue(os.path.exists(self.mark))
        self.assertFalse(os.path.exists(self.heard))
        self.assertFalse(os.path.exists(os.path.join(self.venv, ".whisperx-crashed")), "WhisperX still hears here")
        self.assertTrue(any("exit 139" in ln and "4.4.0" in ln for ln in self.fallbacks_log()), self.fallbacks_log())
        said = r.stderr.split("Moving the speech tools")[1].split("hearing the same footage again")[0]
        self.assertNotIn("⚠", said, "a calm switch")

        # The next reel: the venv on 4.4.0 is kept as it is, nothing installed, no crash first.
        r2, calls2, venv_calls2 = self.run_wt({"CRASH_CT2": "4.7.2"})
        self.assertEqual(r2.returncode, 0, r2.stderr[-1500:])
        self.assertEqual(self.installs(calls2), [])
        self.assertEqual([c for c in venv_calls2 if c.startswith("whisperx-run")], ["whisperx-run ct2=4.4.0 ok"])

        # A rebuilt venv goes straight to the measured set: 4.7.2 is never tried on this PC again.
        shutil.rmtree(self.venv)
        r3, calls3, _ = self.run_wt({"CRASH_CT2": "4.7.2"})
        self.assertEqual(r3.returncode, 0, r3.stderr[-1500:])
        self.assertFalse([c for c in calls3 if TRY in c], calls3)
        wx = [c for c in self.installs(calls3) if "whisperx==" in c]
        self.assertIn("whisperx==3.4.5", wx[0])
        self.assertIn(MEASURED, wx[0])
        self.assertEqual(self.ct2(), "4.4.0")

    def test_a_python_error_on_the_first_load_moves_too(self):
        # exit 1 from the WhisperX run (a Python error on load) instead of a native crash
        write_exec(self.venvpy, VENV_PY.replace("exit 139", "exit 1"))
        r, calls, venv_calls = self.run_wt({"CRASH_CT2": "4.7.2"})
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertEqual(self.ct2(), "4.4.0")
        self.assertTrue(os.path.exists(self.mark))
        self.assertIn("whisperx-run ct2=4.4.0 ok", venv_calls)

    def test_when_the_measured_set_crashes_too_faster_whisper_still_hears_it(self):
        r, calls, venv_calls = self.run_wt({"CRASH_CT2": "4.7.2 4.4.0"})
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertEqual([c for c in venv_calls if c.startswith("whisperx-run")],
                         ["whisperx-run ct2=4.7.2 crashed", "whisperx-run ct2=4.4.0 crashed"])
        self.assertIn("faster-whisper-run ct2=4.4.0", venv_calls)
        self.assertTrue(os.path.exists(os.path.join(self.venv, ".whisperx-crashed")))
        self.assertTrue(os.path.exists(self.mark))
        self.assertTrue(self.words_saved())
        log = self.fallbacks_log()
        self.assertEqual(len(log), 2, log)
        self.assertIn("heard with faster-whisper", log[1])
        # and the next reel goes straight to faster-whisper
        r2, _, venv_calls2 = self.run_wt({"CRASH_CT2": "4.7.2 4.4.0"})
        self.assertEqual(r2.returncode, 0, r2.stderr[-1500:])
        self.assertFalse([c for c in venv_calls2 if c.startswith("whisperx-run")])
        self.assertIn("faster-whisper-run ct2=4.4.0", venv_calls2)

    def test_an_install_that_will_not_take_moves_to_the_measured_set_in_the_same_run(self):
        r, calls, venv_calls = self.run_wt({"FAIL_CT2": "4.7.2"})
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        wx = [c for c in self.installs(calls) if "whisperx" in c]
        self.assertTrue(TRY in wx[0] and "whisperx==3.8.6" in wx[0], wx)
        self.assertTrue(any("whisperx==3.4.5" in c and MEASURED in c for c in wx), wx)
        self.assertEqual(self.ct2(), "4.4.0")
        self.assertEqual(read(os.path.join(self.venv, ".speech-tools-ready")), "cpu\n")
        self.assertTrue(os.path.exists(self.mark))
        self.assertIn("whisperx-run ct2=4.4.0 ok", venv_calls)
        self.assertFalse(os.path.exists(self.venv + ".use-faster-whisper"), "WhisperX installed after all")
        self.assertTrue(any("would not install" in ln and "4.4.0" in ln for ln in self.fallbacks_log()))

    # ── an existing venv ──

    def test_a_working_venv_on_the_measured_set_is_left_alone(self):
        self.existing_venv("4.4.0")
        r, calls, venv_calls = self.run_wt({"CRASH_CT2": "4.7.2"})
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertEqual(self.installs(calls), [], "no surprise rebuild or swap")
        self.assertEqual([c for c in calls if c.startswith("uv venv")], [])
        self.assertEqual(self.ct2(), "4.4.0")
        self.assertEqual([c for c in venv_calls if c.startswith("whisperx-run")], ["whisperx-run ct2=4.4.0 ok"])
        self.assertFalse(os.path.exists(self.mark))
        self.assertFalse(os.path.exists(self.heard))

    def test_a_venv_on_the_crashing_line_is_swapped_to_4_7_2_and_still_has_the_way_back(self):
        self.existing_venv("4.8.3")
        r, calls, venv_calls = self.run_wt({"CRASH_CT2": "4.8.3 4.7.2"})
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertTrue(self.installs(calls)[0].endswith(TRY), calls)
        self.assertEqual([c for c in venv_calls if c.startswith("whisperx-run")],
                         ["whisperx-run ct2=4.7.2 crashed", "whisperx-run ct2=4.4.0 ok"])
        self.assertEqual(self.ct2(), "4.4.0")
        self.assertTrue(os.path.exists(self.mark))

    def test_once_4_7_2_has_heard_a_reel_a_later_error_is_not_blamed_on_it(self):
        self.existing_venv("4.7.2", heard=True)
        r, calls, venv_calls = self.run_wt({"CRASH_CT2": "4.7.2"})
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertEqual(self.installs(calls), [])
        self.assertEqual(self.ct2(), "4.7.2")
        self.assertFalse(os.path.exists(self.mark))
        self.assertIn("faster-whisper-run ct2=4.7.2", venv_calls, "the usual faster-whisper route takes it")

    # ── other machines: unchanged ──

    def test_smart_app_control_keeps_its_own_set(self):
        write_exec(os.path.join(self.fake, "reg"),
                   "#!/bin/sh\necho\necho '    VerifiedAndReputablePolicyState    REG_DWORD    0x1'\n")
        lad = os.path.join(self.tmp, "lad")
        write_exec(os.path.join(lad, "Programs", "Python", "Python311", "python.exe"), "#!/bin/sh\nexit 0\n")
        r, calls, _ = self.run_wt({"LOCALAPPDATA": lad, "CRASH_CT2": "4.5.0"})
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        wx = [c for c in self.installs(calls) if "whisperx==" in c]
        self.assertIn("whisperx==3.7.9", wx[0])
        self.assertIn("ctranslate2==4.5.0", wx[0])
        self.assertFalse([c for c in calls if TRY in c or "ctranslate2==4.4.0" in c], calls)
        self.assertFalse(os.path.exists(self.mark), "a Smart App Control crash takes the faster-whisper route")

    def test_an_nvidia_pc_keeps_the_tested_set(self):
        write_exec(os.path.join(self.fake, "nvidia-smi"), "#!/bin/sh\necho 'CUDA Version: 12.8'\n")
        r, calls, _ = self.run_wt()
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        wx = [c for c in self.installs(calls) if "whisperx==" in c]
        self.assertIn("whisperx==3.8.6", wx[0])
        # v2.3.12: an NVIDIA PC never gets CTranslate2 4.8 (it crashes there), so it installs 4.7.2.
        self.assertIn("ctranslate2==4.7.2", wx[0])
        self.assertNotIn("ctranslate2==4.8.1", wx[0])
        # The NVIDIA set already carries 4.7.2 (TRY), so check there is no SEPARATE processor-only try install.
        self.assertEqual(len(wx), 1, calls)
        self.assertFalse([c for c in calls if "ctranslate2==4.4.0" in c], calls)

    def test_a_mac_is_unchanged(self):
        os.remove(os.path.join(self.fake, "uname"))   # this machine's own kernel: never Windows
        r, calls, _ = self.run_wt({"CRASH_CT2": "4.8.1"})
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertFalse([c for c in calls if TRY in c or "ctranslate2==4.4.0" in c], calls)
        self.assertFalse(os.path.exists(self.mark))


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class PinHelpers(unittest.TestCase):
    """ct2_pin / whisperx_pin / tested_pins as written, run on their own."""

    def ask(self, setup, expr):
        src = read(WT)
        keep = []
        for name in ("CT2_WIN_CPU_PIN=", "CT2_WIN_CPU_TRY=", "ct2_pin()", "TORCH_PIN=", "whisperx_pin()",
                     "TESTED_SET=", "TESTED_SET_311=", "tested_pins()"):
            i = src.index(name)
            j = src.index("\n}\n", i) + 3 if name.endswith("()") else src.index("\n", i) + 1
            keep.append(src[i:j])
        r = subprocess.run(["bash", "-c", "\n".join(keep) + "\n" + setup + "\n" + expr],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    WIN_CPU = "WINDOWS_SHELL=1; GPU_CUDA=0; SAC_PINS=''"

    def test_a_processor_only_pc_tries_the_newer_set(self):
        self.assertEqual(self.ask(self.WIN_CPU, "ct2_pin"), TRY)
        self.assertEqual(self.ask(self.WIN_CPU, "whisperx_pin"), "whisperx==3.8.6")
        self.assertEqual(self.ask(self.WIN_CPU, "tested_pins true"), "")

    def test_the_measured_set_when_chosen_and_for_the_faster_whisper_venv(self):
        for extra in ("CT2_WIN_CPU_MEASURED=1", "NOFW=1"):
            self.assertEqual(self.ask(self.WIN_CPU + "; " + extra, "ct2_pin"), MEASURED)
        self.assertEqual(self.ask(self.WIN_CPU + "; CT2_WIN_CPU_MEASURED=1", "whisperx_pin"), "whisperx==3.4.5")

    def test_gpu_and_smart_app_control_get_no_processor_pin(self):
        self.assertEqual(self.ask("WINDOWS_SHELL=1; GPU_CUDA=1", "ct2_pin"), "ctranslate2==4.7.2")  # v2.3.12 NVIDIA pin
        self.assertEqual(self.ask("WINDOWS_SHELL=1; GPU_CUDA=0; SAC_PINS=x", "ct2_pin"), "")
        self.assertEqual(self.ask("WINDOWS_SHELL=0; GPU_CUDA=0", "ct2_pin"), "")


if __name__ == "__main__":
    unittest.main()
