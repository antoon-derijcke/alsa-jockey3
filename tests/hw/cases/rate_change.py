#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""L3: switch sample rates in a loop.

The most important case in the catalog, and the one with the least obvious
criterion.

Capture stall after a rate change is EXPECTED on a healthy build. The driver
logs it deliberately, on every occurrence, so that stall frequency can be
tracked. A test that failed on the presence of a warning would fail every run
on a perfectly good driver.

So what is checked is whether each rate change ends with a working stream:

    stalled and recovered  -> pass, and counted
    stalled and stuck      -> fail

BOTH DIRECTIONS, AND WHY THAT MATTERS
-------------------------------------
This case used to play only. That made it a playback rate-change test wearing
a general name, and it hid the thing it was built to find. With no capture
stream open, jockey3_pcm_hw_params() takes its *deferred* branch on a capture
stall -- it logs and moves on rather than resetting -- so a run could report 19
capture stalls in 20 changes and still pass, having never once checked whether
capture produced audio afterwards.

So each change now plays and records simultaneously, and the recording is
checked the way JT-AUDIO-005 checks it: a running converter is never bit-exact
silent, so an all-zero capture is an engine that did not restart. Opening the
capture stream also puts the driver on its reset path, which is the path that
matters and was previously untested here.

Stall counts and reset-completion delays come from the kernel log and are
classified by the runner, not here. This case's job is to provoke the
transitions and confirm audio still flows after each one.

The rate list is deliberately not sorted: the failure is worst on a downward
switch, so a sorted sweep would systematically test the easy direction.
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


def nonzero_fraction(path):
    """Fraction of frames carrying any non-zero byte. See JT-AUDIO-005."""
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
        return None
    return (live / total) if total else None


def start_capture(device, rate, seconds, path):
    """Begin recording, to run concurrently with playback."""
    return subprocess.Popen(
        ["arecord", "-D", device, "-r", str(rate), "-c",
         str(CAPTURE_CHANNELS), "--format", FORMAT, "-t", "raw",
         "-d", str(seconds), path],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)


def play_briefly(device, rate, seconds):
    gen = subprocess.Popen(
        ["sox", "-n", "-r", str(rate), "-c", str(CHANNELS), "-b", "24",
         "-e", "signed-integer", "-t", "raw", "-",
         "synth", str(seconds), "sine", "E3", "gain", "-6"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
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
        return 124, "timed out"
    gen.wait(timeout=5)
    return p.returncode, err


def interleave(rates):
    """Order the sweep so every step is a real change, including downward.

    Alternating from the ends -- highest, lowest, second highest, ... -- makes
    every transition a large one in an alternating direction, which is the
    shape that provokes the fault.
    """
    rs = sorted(rates, reverse=True)
    out, lo, hi = [], 0, len(rs) - 1
    while lo <= hi:
        out.append(rs[lo])
        if lo != hi:
            out.append(rs[hi])
        lo, hi = lo + 1, hi - 1
    return out


def main():
    c = Case()
    c.require_card()
    c.require_tools("aplay", "sox")

    rates = interleave(c.params.get("rates", [44100, 48000, 88200, 96000]))
    seconds = float(c.params.get("seconds_per_rate", 1))
    loops = int(c.params.get("iterations_per_run", 10))
    device = c.device or alsa.device_name(c.card)

    with_capture = bool(c.params.get("capture", True))
    floor = float(c.params.get("min_nonzero_fraction", 0.01))

    changes = 0
    failures = 0
    capture_silent = 0
    first_silent_change = None
    capture_fracs = []
    silent_here = []
    xruns_before = alsa.xruns(c.card, "pcm0p")
    t0 = time.time()

    # One line per loop, per tests/README.md "Live feedback while a case runs".
    # A transient line names the rate being exercised and is replaced by the
    # loop's verdict. Reported before c.fail(), never after: the runner takes
    # the last line of stderr as the failure reason.
    total = loops * len(rates)
    for loop in range(1, loops + 1):
        bad = []
        for rate in rates:
            changes += 1
            c.status(f"    loop {loop}/{loops}  ....  {rate} Hz "
                     f"({changes}/{total} changes)")
            # A marker per change, so a stall in the kernel log can be
            # attributed to the change that caused it rather than to the run
            # as a whole -- "when did it start" was previously unanswerable.
            kmsg.Marker(f"{c.id}#change{changes}@{rate}").write()

            raw = os.path.join(c.workdir, f"rate_{changes}_{rate}.raw")
            rec = start_capture(device, rate, seconds, raw) if with_capture \
                else None
            rc, err = play_briefly(device, rate, seconds)
            if rec is not None:
                try:
                    rec.communicate(timeout=seconds + 30)
                except subprocess.TimeoutExpired:
                    rec.kill()
                frac = nonzero_fraction(raw)
                capture_fracs.append((changes, rate,
                                      None if frac is None else round(frac, 4)))
                if frac is None or frac < floor:
                    capture_silent += 1
                    if first_silent_change is None:
                        first_silent_change = changes
                    silent_here.append(rate)
                else:
                    try:
                        os.unlink(raw)
                    except OSError:
                        pass
            if rc != 0:
                failures += 1
                bad.append((rate, rc, err))
        rates_ok = len(rates) - len(bad)
        detail = f"{rates_ok}/{len(rates)} rates played"
        if with_capture:
            detail += (f", capture silent at {', '.join(str(r) for r in silent_here)} Hz"
                       if silent_here else ", capture live throughout")
        c.progress(f"    loop {loop}/{loops}  "
                   f"{'FAIL' if bad or silent_here else 'pass':4}  " + detail
                   + (f", playback failed at {', '.join(str(r) for r, _, _ in bad)} Hz"
                      if bad else ""))
        for rate in silent_here:
            c.fail(f"loop {loop}, {rate} Hz: capture is bit-exact silent after "
                   f"the rate change -- the device accepted the stream without "
                   f"restarting its audio engine")
        silent_here.clear()
        for rate, rc, err in bad:
            # This is the real failure mode: the stream did not come back
            # after the change. One is enough to fail the case, but keep
            # going -- whether it is one rate or every rate is a
            # different bug, and the counts say which.
            c.fail(f"loop {loop}, {rate} Hz: playback failed after rate "
                   f"change (exit {rc}) "
                   f"{(err or '').strip().splitlines()[-1][:100] if err else ''}")

    c.metric("rate_changes", changes)
    c.metric("failures", failures)
    if with_capture:
        c.metric("capture_silent_changes", capture_silent)
        c.metric("first_silent_change", first_silent_change)
        live = [f for _, _, f in capture_fracs if f is not None]
        if live:
            c.metric("capture_nonzero_min", min(live))
            c.metric("capture_nonzero_max", max(live))
        for n, rate, frac in capture_fracs:
            c.metric(f"capture_nonzero_{n}_{rate}", frac)
    c.metric("xruns", max(0, alsa.xruns(c.card, "pcm0p") - xruns_before))
    c.metric("elapsed_s", round(time.time() - t0, 1))
    if changes:
        c.metric("failure_rate_pct", round(100.0 * failures / changes, 2))

    c.note("stall and reset-delay counts come from the kernel log; a stall "
           "that recovered is expected and is not a failure")
    c.done()


if __name__ == "__main__":
    main()
