#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""L3: sample-rate change under full duplex.

Automates what JT-RATE-002 used to ask an operator to do by hand. The
device has one global rate: jockey3_pcm_open() applies
snd_pcm_hw_constraint_single(RATE, current_rate) to a second substream
while another is already open, so the ALSA core refuses a second stream at
a different rate before the driver's own -EBUSY check in
jockey3_pcm_hw_params() is ever reached. What is testable is that this
constraint is real and enforced in the right place -- see the catalog
entry's own notes for the 2026-08-10 rewrite that established this.

Four things are checked, corresponding to the old manual steps:

  1. With capture open, a second stream at the SAME rate is accepted.
  2. With capture open, a second stream at a DIFFERENT rate is refused --
     and refused fast, which is what separates "the open-time ALSA-core
     constraint fired" from "aplay failed for some unrelated reason". A
     constraint rejection never touches the device; a real device fault
     (stall, reset, disconnect) takes much longer. Exit code alone cannot
     tell those apart -- aplay exits non-zero for a missing device, a busy
     node, a bad format, or an ENODEV mid-open, all of which would make a
     bare `rc != 0` assertion a test that can never fail. Requiring both a
     non-zero exit AND a bounded elapsed time is why this case can fail.
  3. The kernel log, restricted to this run, never contains "Cannot change
     rate while other stream is active" -- that message is the driver's own
     sanity check, and reaching it means the open-time constraint above
     failed to do its job first.
  4. With nothing open, changing the rate and immediately opening capture
     at the new rate produces live (non-silent) audio -- not just an
     arecord that exited 0, which is exactly what the Milestone 13 capture
     stall looks like from the outside.
"""

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from lib.case import Case          # noqa: E402
from lib import alsa, kmsg         # noqa: E402

CHANNELS = 4                       # playback: Master L/R + Headphone L/R
CAPTURE_CHANNELS = 6               # fixed by the driver: min == max
FORMAT = "S24_3LE"
BYTES_PER_SAMPLE = 3

# A constraint rejection at open time never touches the device -- it is
# pure ALSA-core bookkeeping. Anything slower is evidence of a real device
# interaction (stall, reset, disconnect) rather than the constraint firing.
REFUSAL_FAST_S = 2.0

BUSY_MESSAGE = "Cannot change rate while other stream is active"
POWERCYCLE_MESSAGE = "hardware may need power-cycling"


def nonzero_fraction(path):
    """(fraction, frames) of non-silent frames in a raw capture. See JT-AUDIO-005."""
    frame = CAPTURE_CHANNELS * BYTES_PER_SAMPLE
    total = live = 0
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(frame * 8192)
                if not chunk:
                    break
                for off in range(0, len(chunk) - frame + 1, frame):
                    total += 1
                    if any(chunk[off:off + frame]):
                        live += 1
    except OSError:
        return None, 0
    return ((live / total) if total else None), total


def capture_outcome(rc, err, path, floor):
    """Classify one capture attempt. Returns (verdict, fraction, frames, detail).

    error/nodata/silent/live -- see rate_change.py's own capture_outcome for
    why these stay apart rather than collapsing to a bool: a stalled capture
    URB can leave a stream silent while playback continues perfectly, which
    is a transport fault, not the converter never having started.
    """
    if rc != 0:
        last = (err or "").strip().splitlines()
        return "error", None, 0, f"arecord exit {rc}: {last[-1][:100] if last else ''}"
    frac, frames = nonzero_fraction(path)
    if not frames:
        return "nodata", None, 0, "arecord returned 0 frames"
    if frac is None or frac < floor:
        return "silent", frac, frames, f"{frac:.4%} non-zero of {frames} frames"
    return "live", frac, frames, f"{frac:.2%} non-zero of {frames} frames"


def start_capture(device, rate, seconds, path):
    """Begin a bounded-duration recording; returns the Popen, not yet waited."""
    duration = max(1, int(round(seconds)))
    return subprocess.Popen(
        ["arecord", "-D", device, "-r", str(rate), "-c",
         str(CAPTURE_CHANNELS), "--format", FORMAT, "-t", "raw",
         "-d", str(duration), path],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)


def run_playback(device, rate, seconds):
    """Play a short tone and wait for it. Returns (rc, stderr, elapsed_s)."""
    gen = subprocess.Popen(
        ["sox", "-n", "-r", str(rate), "-c", str(CHANNELS), "-b", "24",
         "-e", "signed-integer", "-t", "raw", "-",
         "synth", str(seconds), "sine", "E3", "gain", "-6"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    t0 = time.monotonic()
    p = subprocess.Popen(
        ["aplay", "-D", device, "-r", str(rate), "-c", str(CHANNELS),
         "--format", FORMAT, "-t", "raw"],
        stdin=gen.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True)
    gen.stdout.close()
    try:
        _out, err = p.communicate(timeout=seconds + 30)
    except subprocess.TimeoutExpired:
        p.kill()
        gen.kill()
        return 124, "timed out", time.monotonic() - t0
    elapsed = time.monotonic() - t0
    gen.wait(timeout=5)
    return p.returncode, err, elapsed


def main():
    c = Case()
    c.require_card()
    c.require_tools("aplay", "arecord", "sox")

    device = c.device or alsa.device_name(c.card)

    rate_a = int(c.params.get("rate_a", 44100))
    rate_b = int(c.params.get("rate_b", 96000))
    if rate_a == rate_b:
        c.blocked(f"rate_a and rate_b are both {rate_a} -- nothing to duplex-test")

    settle_s = float(c.params.get("settle_seconds", 1))
    same_rate_s = float(c.params.get("same_rate_seconds", 2))
    diff_rate_s = float(c.params.get("diff_rate_seconds", 2))
    after_capture_s = float(c.params.get("after_capture_seconds", 4))
    min_nonzero_fraction = float(c.params.get("min_nonzero_fraction", 0.01))
    # Long enough to still be running through settle + both playback attempts,
    # with margin -- the capture itself is what "under full duplex" means here.
    capture_s = float(c.params.get("capture_seconds",
                       settle_s + same_rate_s + diff_rate_s + 6))

    failures = 0

    def note_fail(text):
        nonlocal failures
        failures += 1
        c.fail(text)

    mark = kmsg.Marker(c.id)
    mark.write()

    cap_path = os.path.join(c.workdir, "duplex.raw")
    c.progress(f"starting capture at {rate_a} Hz, held open for the duplex checks "
               f"({capture_s:.0f}s)")
    cap = start_capture(device, rate_a, capture_s, cap_path)
    time.sleep(settle_s)

    c.progress(f"opening playback at the SAME rate ({rate_a} Hz) -- must be accepted")
    rc, err, elapsed = run_playback(device, rate_a, same_rate_s)
    if rc != 0:
        last = (err or "").strip().splitlines()
        note_fail(f"same-rate playback ({rate_a} Hz) was refused: exit {rc} in "
                  f"{elapsed:.2f}s: {last[-1][:120] if last else ''}")
    else:
        c.progress(f"same-rate playback accepted in {elapsed:.2f}s")
    c.metric("same_rate_open_s", round(elapsed, 3))

    c.progress(f"opening playback at a DIFFERENT rate ({rate_b} Hz) -- must be refused")
    rc2, err2, elapsed2 = run_playback(device, rate_b, diff_rate_s)
    c.metric("diff_rate_refusal_s", round(elapsed2, 3))
    if rc2 == 0:
        note_fail(f"different-rate playback ({rate_b} Hz) was ACCEPTED while "
                  f"capture was open at {rate_a} Hz -- the open-time rate "
                  f"constraint did not fire")
    elif elapsed2 > REFUSAL_FAST_S:
        note_fail(f"different-rate playback was refused but took {elapsed2:.2f}s "
                  f"(> {REFUSAL_FAST_S}s) -- too slow to be the open-time "
                  f"ALSA-core constraint; looks like a device-level failure "
                  f"instead of a parameter rejection")
    else:
        c.progress(f"different-rate playback refused in {elapsed2:.2f}s "
                   f"(exit {rc2})")
        last2 = (err2 or "").strip().splitlines()
        if not last2 or "rate" not in last2[-1].lower():
            c.note(f"refusal message did not mention 'rate': "
                   f"{last2[-1][:120] if last2 else '(no stderr)'!r}")

    cap_rc = cap.wait(timeout=capture_s + 30)
    cap_err = cap.stderr.read() if cap.stderr else ""
    verdict, frac, frames, detail = capture_outcome(
        cap_rc, cap_err, cap_path, min_nonzero_fraction)
    if verdict != "live":
        note_fail(f"capture during full duplex did not stay live: "
                  f"{verdict} -- {detail}")
    else:
        c.progress(f"capture stayed live throughout: {detail}")

    if not mark.written:
        c.note("kmsg marker could not be written -- the absence checks below "
               "cover the whole ring buffer, not just this run, so a hit is "
               "recorded as a note rather than a failure")
        window_text = "\n".join(kmsg.read_log())
        if BUSY_MESSAGE in window_text:
            c.note(f'"{BUSY_MESSAGE}" appears somewhere in the ring buffer '
                   f"(unattributed -- no run marker)")
        if POWERCYCLE_MESSAGE in window_text:
            c.note(f'"{POWERCYCLE_MESSAGE}" appears somewhere in the ring '
                   f"buffer (unattributed -- no run marker)")
    else:
        window_text = "\n".join(kmsg.slice_since(kmsg.read_log(), mark))
        if BUSY_MESSAGE in window_text:
            note_fail(f'driver logged "{BUSY_MESSAGE}" -- the open-time rate '
                      f"constraint failed to do its job before the driver's "
                      f"own sanity check had to catch it")
        if POWERCYCLE_MESSAGE in window_text:
            note_fail(f'driver logged "{POWERCYCLE_MESSAGE}" -- capture '
                      f"stall recovery escalated past what this case accepts "
                      f"as a pass")

    c.progress(f"nothing open -- changing rate to {rate_b} Hz, then opening "
               f"capture there")
    rc3, err3, elapsed3 = run_playback(device, rate_b, 2)
    if rc3 != 0:
        last3 = (err3 or "").strip().splitlines()
        note_fail(f"priming playback at {rate_b} Hz failed with nothing else "
                  f"open: exit {rc3}: {last3[-1][:120] if last3 else ''}")

    after_path = os.path.join(c.workdir, "after.raw")
    cap2 = start_capture(device, rate_b, after_capture_s, after_path)
    cap2_rc = cap2.wait(timeout=after_capture_s + 30)
    cap2_err = cap2.stderr.read() if cap2.stderr else ""
    verdict2, frac2, frames2, detail2 = capture_outcome(
        cap2_rc, cap2_err, after_path, min_nonzero_fraction)
    if verdict2 != "live":
        note_fail(f"capture after rate change to {rate_b} Hz did not "
                  f"recover: {verdict2} -- {detail2}")
    else:
        c.progress(f"capture after rate change recovered: {detail2}")

    c.metric("failures", failures)
    c.done()


if __name__ == "__main__":
    main()
