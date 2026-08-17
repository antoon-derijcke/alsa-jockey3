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
NOT assert that it was hit. It provokes repeatedly, reopening aplay at a
jittered interval for as long as the card is still present -- see
race_rate_change_against_cut() for why a single jittered delay before one
cut was not enough. How often a rate change actually raced a removal is read
from the driver's own log, not measured here: jockey3_set_rate() only reaches
"Failed to initialize device to change rate: -19" when the device was still
believed live at the start of the EP0 transfer and went away mid-transfer,
which is exactly this window, and lib/rules.yaml counts it as the benign
'rate_change_raced_removal' metric. The verdict on what
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
import threading
import time

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from lib.case import Case          # noqa: E402
from lib import alsa, priv         # noqa: E402

CHANNELS = 4
FORMAT = "S24_3LE"


def wait_for_card(present, timeout):
    """Wait for the card to appear or disappear. Returns (index, when|None).

    Presence alone is not enough when waiting for the card to come back:
    /proc/asound/cardN and its substreams appear early in probe, before
    snd_card_register() publishes the /dev/snd character devices, and those
    devices can also be stale leftovers from the previous incarnation that
    udev has not reaped yet. alsa.control_is_live() asks the same question
    aplay does when it opens "hw:<idx>,0" -- see its docstring, and
    audio_engine_start.py's wait_for_substreams() where this was first hit.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        idx, _ = alsa.find_card()
        if idx is not None and present:
            if alsa.control_is_live(idx):
                return idx, time.time()
        elif idx is None and not present:
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


def cut_power_async():
    """Fire usb-power off in the background. Returns (thread, result-box)."""
    box = {}

    def run():
        box["rc"], box["out"], box["err"] = priv.usb_power("off")

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t, box


def race_rate_change_against_cut(idx, rates, seed, seconds, race_lo, race_hi):
    """Reopen at a rotating rate until the device actually disappears.

    priv.usb_power("off") is not fast: the privileged helper re-resolves the
    hub port from the device's own USB ids and only then cuts it, two serial
    round trips to uhubctl that measured 2-4 seconds on this rig -- far
    longer than the sub-second window a rate change is actually vulnerable
    in. A single short jittered sleep before ONE blocking off() call almost
    never lands inside that window, which is why races_observed read 0 in
    every run since this case was added: the jitter was aimed at the wrong
    clock. Firing off() in the background and reopening aplay at short
    jittered intervals for as long as the card is still present spreads many
    attempts across the helper's whole round trip instead of gambling on a
    single one, and each reopen re-enters the vulnerable window at its own
    hw_params() rather than needing the first guess to land.

    Whether any one attempt actually raced the cut is NOT decided here.
    Watching aplay's own liveness at the moment the card disappears was the
    first approach tried, and it undercounted badly: aplay exits as soon as
    its write fails, which can well be before the poll below runs, so a race
    that did land often reads as "not running" anyway. The driver's own log
    is unambiguous about this instead -- see the benign
    'rate_change_raced_removal' entry in lib/rules.yaml -- so the runner
    counts it from there, not from anything guessed in this process.

    Returns (attempts, last_rate, off_result_box).
    """
    device = alsa.device_name(idx)
    off_thread, off_box = cut_power_async()
    gen = p = None
    attempt = 0
    rate = None
    deadline = time.time() + 30
    while time.time() < deadline:
        now_idx, _ = alsa.find_card()
        if now_idx is None:
            break
        if p is not None:
            reap(gen, p)
        attempt += 1
        rate = rates[(seed + attempt) % len(rates)]
        gen, p = start_playback(device, rate, seconds)
        time.sleep(random.uniform(race_lo, race_hi))
    if p is not None:
        reap(gen, p)
    off_thread.join(timeout=30)
    return attempt, rate, off_box


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
    # The reopen interval used while racing the cut -- see
    # race_rate_change_against_cut() for why this is no longer a single delay
    # before one cut, but a repeated one spread across the whole round trip.
    race_lo = float(c.params.get("race_ms_min", 20)) / 1000.0
    race_hi = float(c.params.get("race_ms_max", 120)) / 1000.0

    start_idx, _ = alsa.find_card()
    enumerate_ms, attempts_total = [], 0
    powered_off = False
    cycles = 0

    try:
        for i in range(1, iterations + 1):
            idx, _ = alsa.find_card()
            if idx is None:
                c.fail(f"iteration {i}: no card to start from")
                break

            attempts, rate, off_box = race_rate_change_against_cut(
                idx, rates, i, seconds, race_lo, race_hi)
            attempts_total += attempts
            if off_box.get("rc") != 0:
                c.fail(f"iteration {i}: usb-power off failed: "
                       f"{(off_box.get('err') or '').strip()[:120]}")
                break
            powered_off = True

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

            c.progress(f"cycle {i}/{iterations}  {attempts} reopen(s), "
                       f"last {rate} Hz  up {ms:>5.0f} ms  card hw:{idx}"
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
    # How many times a rate change actually raced a removal is not something
    # this process can see reliably -- aplay exits as soon as its write
    # fails, often before this script gets to look. It is read from the
    # driver's own log instead: run.json's "rate_change_raced_removal" metric,
    # attached to the benign entry of the same name in lib/rules.yaml.
    c.metric("reopen_attempts", attempts_total)
    if enumerate_ms:
        c.metric("enumerate_ms", {"n": len(enumerate_ms),
                                  "min": min(enumerate_ms),
                                  "max": max(enumerate_ms),
                                  "mean": round(sum(enumerate_ms)
                                                / len(enumerate_ms), 1)})
    c.done()


if __name__ == "__main__":
    main()
