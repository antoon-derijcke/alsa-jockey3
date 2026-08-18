#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""L2: run the in-kernel codec KUnit suite.

Thin wrapper around tests/codec/run_kunit.sh, which already knows the cross
compilers, the QEMU binaries and the two per-architecture config quirks. The
value added here is recording the pass count as a metric, so a suite that
silently starts running fewer tests is visible.

The MIDI Running Status suite (ploytec_midi_kunit.c, see midi_kunit.py) is
built into the very same .kunitconfig and module, so a plain kunit.py run
would fold its results into these counts too. KUNIT_FILTER scopes the run to
just the codec suite, keeping this case's counts about the codec alone.

This same script backs JT-CODEC-003 (full architecture matrix, optimized
codec) and JT-CODEC-004 (portable reference codec, um only) -- a leading
"--ref" argument selects the latter by forwarding run_kunit.sh's own --ref
flag, which builds with CONFIG_SND_USB_JOCKEY3_REFERENCE_CODEC=y instead of
whichever optimized variant the architecture would otherwise pick.

Architectures run one at a time, each its own run_kunit.sh invocation, so
that kunit.py's own "Configuring / Building / Starting KUnit Kernel" lines
can be turned into a per-architecture status line -- see tests/README.md
"Live feedback while a case runs". A single batched run_kunit.sh call across
every target would say nothing for as long as JT-CODEC-003 across five
architectures takes.
"""

import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from lib.case import Case          # noqa: E402

RESULT_RE = re.compile(r"Ran (\d+) tests: passed: (\d+)(?:, failed: (\d+))?")

PHASES = (
    ("Configuring KUnit Kernel", "configuring"),
    ("Building KUnit Kernel", "building"),
    ("Starting KUnit Kernel", "testing"),
)


def run_one_arch(c, script, arch, i, n, env, deadline, use_ref):
    """Stream one run_kunit.sh <arch> invocation, reporting phase changes.

    Returns (rc, log_text, result_match_or_None, skipped_bool).
    """
    label = f"    arch {i}/{n}  ....  {arch:<6}"
    c.status(f"{label} starting")

    argv = ["bash", script]
    if use_ref:
        argv.append("--ref")
    argv.append(arch)

    try:
        proc = subprocess.Popen(
            argv, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except OSError as e:
        c.progress(f"{label} ERROR  {e}")
        return 125, "", None, False

    lines = []
    phase = "starting"
    result = None
    skipped = False
    try:
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            lines.append(line)
            text = line.rstrip("\n")
            for marker, name in PHASES:
                if marker in text:
                    phase = name
                    c.status(f"{label} {phase}")
                    break
            if "SKIPPED -- missing tools" in text:
                skipped = True
            m = RESULT_RE.search(text)
            if m:
                result = m
            if time.monotonic() > deadline:
                proc.kill()
                break
    finally:
        proc.wait()

    log_text = "".join(lines)

    if skipped:
        c.progress(f"{label} skip  missing tools")
    elif result:
        passed, total = int(result.group(2)), int(result.group(1))
        verdict = "pass" if passed == total and proc.returncode == 0 else "FAIL"
        c.progress(f"{label} {verdict}  {passed}/{total} tests")
    elif proc.returncode == 0:
        c.progress(f"{label} FAIL  no results parsed")
    else:
        c.progress(f"{label} FAIL  exited {proc.returncode}")

    return proc.returncode, log_text, result, skipped


def main():
    c = Case()
    script = os.path.join(c.repo, "tests", "codec", "run_kunit.sh")
    if not os.path.exists(script):
        c.blocked(f"{script} not found")

    kernel_src = os.environ.get("KERNEL_SRC") or os.path.expanduser("~/sound")
    if not os.path.isdir(os.path.join(kernel_src, "tools", "testing", "kunit")):
        # Skip rather than blocked -- see build_gate.py. Note the codec is not
        # untested on a machine that skips this: with
        # CONFIG_SND_USB_JOCKEY3_CODEC_KUNIT_TEST the suite runs at every
        # module load, and JT-PROBE-001 records the result as
        # kunit_cases_passed_on_target.
        c.skip(f"no kernel tree with kunit.py at {kernel_src}: this is not a "
               f"build host. Run the 'build' profile on one, or set KERNEL_SRC.")

    argv = sys.argv[1:]
    use_ref = "--ref" in argv
    targets = [a for a in argv if a != "--ref"] or ["um"]
    env = dict(os.environ, KUNIT_FILTER="ploytec-codec*")
    deadline = time.monotonic() + 3600

    total = passed = failed = 0
    any_rc_nonzero = False
    log_path = os.path.join(c.workdir, "kunit.log")
    with open(log_path, "w", encoding="utf-8") as log:
        for i, arch in enumerate(targets, start=1):
            rc, log_text, result, skipped = run_one_arch(
                c, script, arch, i, len(targets), env, deadline, use_ref)
            log.write(log_text)
            if rc != 0 and not skipped:
                any_rc_nonzero = True
            if result:
                total += int(result.group(1))
                passed += int(result.group(2))
                failed += int(result.group(3) or 0)

    c.metric("tests_run", total)
    c.metric("tests_passed", passed)
    c.metric("arches_run", len(targets))
    if failed:
        c.metric("tests_failed", failed)

    if any_rc_nonzero:
        c.fail(f"run_kunit.sh failed on one or more of: {' '.join(targets)}")
    elif total == 0:
        # Exit 0 with no parsed results means the output format changed, which
        # would otherwise be reported as a silent pass -- the worst outcome a
        # test suite can have.
        c.fail("no KUnit results parsed from output")
    elif passed != total:
        c.fail(f"{total - passed} of {total} tests failed")

    c.done()


if __name__ == "__main__":
    main()
