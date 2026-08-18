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
  2. With capture open, a second stream at a DIFFERENT rate is constrained
     to the rate already running, not refused outright: aplay/arecord call
     snd_pcm_hw_params_set_rate_near(), which is satisfied by the nearest
     legal rate -- and the driver's constraint set has exactly one, the
     rate already in use -- so the request is silently coerced rather than
     rejected, and aplay exits 0 having actually run at the existing rate.
     This was confirmed against real hardware, and corrects an earlier
     version of this case that asserted a fast non-zero exit instead; see
     diff_rate_playback()'s docstring below. What is checked is the
     negotiated rate the kernel actually applied, read back from /proc
     while the stream runs, not aplay's exit code or its stderr text (the
     "rate is not accurate" warning is not printed for every mismatch, so
     matching on it can hide a real failure).
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


# How long to poll /proc for a negotiated rate before giving up and treating
# the attempt as a bare refusal. hw_params is applied at open, long before
# any audio is written, so this only needs to outlast process start-up.
HW_PARAMS_POLL_DEADLINE_S = 3.0
HW_PARAMS_POLL_INTERVAL_S = 0.025


def diff_rate_playback(device, rate, seconds, card, pcm):
    """Play at 'rate' while another stream holds the device at a different
    one, and read back what ALSA actually negotiated.

    aplay always calls snd_pcm_hw_params_set_rate_near(), which is
    satisfied by the NEAREST rate the driver's constraint set allows --
    and jockey3_pcm_open() constrains RATE to exactly one value,
    chip->current_rate, while a second stream is open. So a divergent
    request is not refused, it is silently coerced: aplay exits 0, having
    actually run at the existing rate. Confirmed against real hardware
    2026-08-18 (run x86_64-prod/20260818T141039Z-smoke): a request for
    96000 Hz while capture held the device at 44100 Hz was accepted and
    ran the full requested duration -- at 44100 Hz.

    Exit code and stderr text are therefore not reliable evidence either
    way: aplay's "rate is not accurate" warning is not gated on the exit
    code and is not even printed when requested and obtained rates happen
    to fall within alsa-lib's own tolerance band, so parsing it can hide a
    real failure behind a well-chosen (rate_a, rate_b) pair. What the
    kernel actually did is not in doubt, though --
    /proc/asound/cardN/<pcm>/sub0/hw_params reports the negotiated rate
    while the stream is open, so that is what is asked instead.

    Returns (rc, stderr, elapsed_s, obtained_rate_or_None). obtained_rate
    is None only if the process never reached a state hw_params could be
    read from before it exited -- which means it really was refused before
    ever touching the device, the outcome step 2 originally assumed.
    """
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

    obtained = None
    deadline = time.monotonic() + HW_PARAMS_POLL_DEADLINE_S
    while time.monotonic() < deadline:
        rate_seen = alsa.hw_params(card, pcm, "sub0").get("rate")
        if rate_seen:
            obtained = rate_seen
            break
        if p.poll() is not None:
            break
        time.sleep(HW_PARAMS_POLL_INTERVAL_S)

    try:
        _out, err = p.communicate(timeout=seconds + 30)
    except subprocess.TimeoutExpired:
        p.kill()
        gen.kill()
        return 124, "timed out", time.monotonic() - t0, obtained
    elapsed = time.monotonic() - t0
    gen.wait(timeout=5)
    return p.returncode, err, elapsed, obtained


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
    # Long enough to still be running through settle + both playback
    # attempts, with margin. The diff-rate attempt is coerced to rate_a (see
    # diff_rate_playback()), so its *wall-clock* length is diff_rate_s worth
    # of rate_b samples played out at rate_a -- longer than diff_rate_s
    # whenever rate_b > rate_a -- not just the nominal duration.
    diff_rate_wall_s = diff_rate_s * max(1.0, rate_b / rate_a)
    capture_s = float(c.params.get("capture_seconds",
                       settle_s + same_rate_s + diff_rate_wall_s + 6))

    subs = alsa.substreams(c.card)
    pcm_p = (subs["playback"] or ["pcm0p"])[0]

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

    c.progress(f"opening playback at a DIFFERENT rate ({rate_b} Hz) -- must "
               f"stay constrained to {rate_a} Hz")
    rc2, err2, elapsed2, obtained2 = diff_rate_playback(
        device, rate_b, diff_rate_s, c.card, pcm_p)
    c.metric("diff_rate_attempt_s", round(elapsed2, 3))
    if obtained2 is not None:
        c.metric("diff_rate_obtained_hz", obtained2)
        if obtained2 == rate_a:
            c.progress(f"different-rate playback was coerced to the "
                       f"existing rate ({rate_a} Hz) rather than refused, "
                       f"exit {rc2} in {elapsed2:.2f}s -- alsa-lib's "
                       f"near-rate matching satisfying the single-value "
                       f"constraint by rounding to it")
        elif obtained2 == rate_b:
            note_fail(f"different-rate playback actually ran at the "
                      f"requested {rate_b} Hz while capture was open at "
                      f"{rate_a} Hz -- the open-time rate constraint did "
                      f"not fire")
        else:
            note_fail(f"different-rate playback negotiated {obtained2} Hz, "
                      f"neither {rate_a} nor {rate_b} Hz -- unexpected")
    elif rc2 == 0:
        note_fail(f"different-rate playback ({rate_b} Hz) exited 0 but no "
                  f"negotiated rate could be read from /proc -- cannot "
                  f"confirm the constraint held")
    elif elapsed2 > REFUSAL_FAST_S:
        note_fail(f"different-rate playback was refused but took {elapsed2:.2f}s "
                  f"(> {REFUSAL_FAST_S}s) -- too slow to be the open-time "
                  f"ALSA-core constraint; looks like a device-level failure "
                  f"instead of a parameter rejection")
    else:
        c.progress(f"different-rate playback refused outright in "
                   f"{elapsed2:.2f}s (exit {rc2}), before any rate could "
                   f"be read back")

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
