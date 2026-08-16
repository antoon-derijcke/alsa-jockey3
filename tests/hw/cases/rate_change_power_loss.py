#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""L3: attempt a sample-rate change while the device is being taken away.

WHY THIS CASE EXISTS
--------------------
On 2026-08-11 a wedged device produced a cascade nobody had predicted. The
driver tried to change rate on a device that had stopped answering EP0;
usb_set_interface() disables an interface's endpoints as its FIRST action, then
sends SET_INTERFACE, and when that request fails it returns without ever
calling usb_enable_interface(). Interface 0 was left with EP 0x05 and EP 0x83
permanently disabled, so every later usb_submit_urb() returned -ENOENT (-2)
until a USB reset re-enumerated the device. Interface 1 was never reached, which
is why the capture endpoint kept submitting cleanly -- that asymmetry is what
identified the mechanism.

The fix is in ploytec_initialize_device(): the firmware read at the head of the
handshake is now checked, and an unresponsive control endpoint aborts the
sequence BEFORE usb_set_interface() is called.

WHAT THIS CASE CAN AND CANNOT REPRODUCE
---------------------------------------
It cannot reproduce the original wedge. That needs a device that is still
enumerated but has stopped answering, and nothing here can put the hardware into
that state on demand -- which is exactly why the watchdog (JT-MIDI-007) exists.

What it CAN do is exercise the same code path against a device that is going
away, which is the only mechanical way to make an EP0 transfer fail on command.
Between VBUS dropping and the kernel marking the device NOTATTACHED there is a
window in which a control transfer is submitted and does not complete, and a
rate change started inside that window walks the identical sequence.

The window is short and its width is not under our control, so this case does
NOT assert that it was hit. It provokes repeatedly with a jittered delay and
records how often a rate change actually raced a removal. The verdict on what
the driver said is the runner's, from lib/rules.yaml -- 'Failed to submit
(?:playback|capture|MIDI IN) URB' and 'Endpoints are disabled after ...' are
both driver_fail, so a single -2 anywhere in this case's log turns it red
without this file needing to know about it.

WHAT IS ASSERTED HERE
---------------------
That the device survives the treatment: it re-enumerates every time, comes back
with all three substream types, and still accepts a rate change afterwards. A
driver that left the endpoints disabled would fail that last check even if the
log had somehow been quiet.
"""

import os
import random
import subprocess
import sys
import time

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from lib.case import Case          # noqa: E402
from lib import alsa, priv         # noqa: E402

CHANNELS = 4
FORMAT = "S24_3LE"


def wait_for_card(present, timeout):
    """Wait for the card to appear or disappear. Returns (index, when|None)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        idx, _ = alsa.find_card()
        if (idx is not None) == present:
            return idx, time.time()
        time.sleep(0.05)
    idx, _ = alsa.find_card()
    return idx, None


def start_playback(device, rate, seconds):
    """Start aplay at @rate without waiting for it. Returns the Popen pair.

    Opening at a rate the hardware is not already at is what makes the driver
    run the rate change; the audio itself is irrelevant here.
    """
    gen = subprocess.Popen(
        ["sox", "-n", "-r", str(rate), "-c", str(CHANNELS), "-b", "24",
         "-e", "signed-integer", "-t", "raw", "-",
         "synth", str(seconds), "sine", "A3", "gain", "-12"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    p = subprocess.Popen(
        ["aplay", "-D", device, "-r", str(rate), "-c", str(CHANNELS),
         "--format", FORMAT, "-t", "raw"],
        stdin=gen.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True)
    gen.stdout.close()
    return gen, p


def reap(gen, p):
    """Stop the playback pair and report whether aplay was still running."""
    running = p.poll() is None
    for proc in (p, gen):
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
    return running


def power_on(c, settle):
    """Restore power and wait for the card. Returns (index, enumerate_ms)."""
    rc, _out, err = priv.usb_power("on")
    switched = time.time()
    if rc != 0:
        c.fail(f"usb-power on failed: {(err or '').strip()[:120]}")
        return None, None
    idx, seen = wait_for_card(True, settle)
    if seen is None:
        return None, None
    return idx, round((seen - switched) * 1000, 1)


def rate_change_still_works(c, idx, rate, seconds):
    """Open at @rate and confirm it plays. The endpoints must be alive for this."""
    device = alsa.device_name(idx)
    gen, p = start_playback(device, rate, seconds)
    try:
        _out, err = p.communicate(timeout=seconds + 30)
    except subprocess.TimeoutExpired:
        reap(gen, p)
        return False, "aplay hung"
    gen.wait(timeout=5)
    if p.returncode != 0:
        return False, (err or "").strip()[:160]
    return True, ""


def main():
    c = Case()
    c.require_card()
    c.require_tools("aplay", "sox")

    ok, why = priv.available()
    if not ok:
        c.blocked(f"cannot switch port power: {why}")
    if not priv.usb_power_available():
        c.blocked("no Jockey 3 behind a ppps-capable hub port")

    iterations = int(c.params.get("iterations_per_run", 6))
    rates = list(c.params.get("rates", [44100, 48000, 96000]))
    off_seconds = float(c.params.get("off_seconds", 2))
    settle = float(c.params.get("settle_seconds", 8))
    seconds = float(c.params.get("seconds", 2))
    # The delay between launching aplay and cutting power. aplay has to get far
    # enough to reach hw_params -- which is where the rate change happens -- but
    # not so far that it has finished. Jittered because the window this is
    # aiming at is narrow and its position is not something we can measure.
    race_lo = float(c.params.get("race_ms_min", 20)) / 1000.0
    race_hi = float(c.params.get("race_ms_max", 120)) / 1000.0

    start_idx, _ = alsa.find_card()
    enumerate_ms, races = [], 0
    powered_off = False
    cycles = 0

    try:
        for i in range(1, iterations + 1):
            idx, _ = alsa.find_card()
            if idx is None:
                c.fail(f"iteration {i}: no card to start from")
                break

            # Rotate so consecutive iterations always request a different rate
            # from the one before, otherwise the driver short-circuits on
            # "Rate already set" and no rate change happens at all.
            rate = rates[i % len(rates)]
            gen, p = start_playback(alsa.device_name(idx), rate, seconds)

            time.sleep(random.uniform(race_lo, race_hi))
            rc, _out, err = priv.usb_power("off")
            if rc != 0:
                reap(gen, p)
                c.fail(f"iteration {i}: usb-power off failed: "
                       f"{(err or '').strip()[:120]}")
                break
            powered_off = True

            # aplay still running when the power went means the open -- and so
            # the rate change -- had not finished, which is the race we want.
            raced = reap(gen, p)
            if raced:
                races += 1

            _idx, gone = wait_for_card(False, settle)
            if gone is None:
                c.fail(f"iteration {i}: card still present {settle}s after "
                       f"the port was powered down")
                break

            time.sleep(off_seconds)

            idx, ms = power_on(c, settle)
            powered_off = False
            if idx is None:
                c.fail(f"iteration {i}: card did not reappear within {settle}s")
                break
            enumerate_ms.append(ms)
            cycles += 1

            subs = alsa.substreams(idx)
            missing = [w for w in ("playback", "capture", "rawmidi")
                       if not subs[w]]
            for what in missing:
                c.fail(f"iteration {i}: no {what} after re-enumeration")

            # The real assertion. If a failed rate change left interface 0's
            # endpoints disabled, this is where it shows: aplay opens, the URBs
            # cannot be submitted, and nothing plays.
            good, why_not = rate_change_still_works(
                c, idx, rates[(i + 1) % len(rates)], seconds)
            if not good:
                c.fail(f"iteration {i}: rate change no longer works after the "
                       f"race: {why_not}")

            c.progress(f"cycle {i}/{iterations}  requested {rate} Hz  "
                       f"up {ms:>5.0f} ms  card hw:{idx}"
                       + ("  RACED" if raced else "")
                       + ("  MISSING " + ", ".join(missing) if missing else ""))
    finally:
        # Never leave the rig dark; see hotplug_cycle.py for what that costs.
        if powered_off:
            idx, _ms = power_on(c, settle)
            if idx is None:
                c.note("PORT LEFT POWERED DOWN -- run "
                       "`sudo jockey3-testctl usb-power on` by hand")

    c.metric("cycles", cycles)
    c.metric("card_index_first", start_idx)
    c.metric("card_index_last", alsa.find_card()[0])
    # Not a pass criterion: the window is not ours to control, and a run that
    # raced nothing has simply not provoked anything. Recorded so a series of
    # zeroes is visible rather than being mistaken for a series of clean passes.
    c.metric("races_observed", races)
    if enumerate_ms:
        c.metric("enumerate_ms", {"n": len(enumerate_ms),
                                  "min": min(enumerate_ms),
                                  "max": max(enumerate_ms),
                                  "mean": round(sum(enumerate_ms)
                                                / len(enumerate_ms), 1)})
    if not races:
        c.note("no rate change was still in flight when power was cut; "
               "widen race_ms_min/race_ms_max if this persists")
    c.done()


if __name__ == "__main__":
    main()
