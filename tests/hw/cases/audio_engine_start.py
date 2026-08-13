#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""L3: does the device's audio engine actually start after a power cycle?

THE FAILURE THIS EXISTS FOR
---------------------------
2026-08-13, production kernel: the device enumerated, the driver probed
cleanly, the rate was programmed and verified, ALSA opened a playback stream
and accepted every sample -- and nothing came out of the device. Three power
cycles in a row, after one that worked. Nothing in dmesg, no xrun, no error
return anywhere. Every counter said the run was fine.

The OpenVizsla trace showed what had happened. Playback was flawless: 100% of
packets carried non-zero audio at the correct cadence, with the MIDI idle byte
at offset 480 and the sync byte at 481 in every one. But the capture endpoint
returned nothing but zeros -- 82722 packets, not one non-zero byte, against
95.5% non-zero in the cycle that worked. The device was accepting the stream
and never starting its audio engine.

The control plane was byte-identical between the working and failing cycles:
same requests in the same order, same status bytes, same rate programmed and
read back, same inter-transfer gaps. So this is not something the driver can
see by checking return codes, and it will not show up in any existing case.

WHY SILENCE IS THE SIGNAL HERE, AND NOT IN JT-PCM-004
-----------------------------------------------------
JT-PCM-004 captures at each rate and deliberately does NOT fail on silence,
because with nothing patched into the inputs silence is the correct answer.
That is a different question from this one.

A running ADC is never bit-exact silent. It produces dither and noise floor
whether or not anything is connected, which is why the working cycles measured
95.5% and 99.4% of packets non-zero with nothing plugged in. Individual
all-zero packets are normal -- a few percent of them. A capture in which *no
sample anywhere* is non-zero is not a quiet input; it is a converter that is
not running.

So the threshold is deliberately nowhere near the observed values: anything
below `min_nonzero_fraction` (default 1%) fails, against ~0% when broken and
>95% when working. There is no sensitivity to tune and no risk of a quiet
studio failing the case.

IT TAKES A DEVICE POWER CYCLE, AND THAT IS THE FINDING
-----------------------------------------------------
Measured 2026-08-13: ten consecutive re-enumerations driven through the ppps
hub switch, and the device came back correctly every time. Not one silent
cycle.

The Jockey 3 is self-powered (bmAttributes 0xc0), so cutting VBUS at the hub
is a cable unplug and not a device power-off, and evidently the two are not
equivalent to the device. That fits the rest of what the traces showed: a USB
re-enumeration does send the rate back to 44100 Hz and the status byte back to
0x12, but the control surface LEDs keep their pattern across an unplug, so the
firmware is doing a partial re-initialization rather than a cold boot.

So the device has two distinct levels of reset, and only the deeper one
provokes this. The failure is a race against the device's own power-on boot:
its USB core answers early enough to enumerate and be programmed, while
whatever runs its audio engine is still coming up. Program it in that window
and the engine never starts -- which is why a debug kernel, which is slower to
reach probe, has never shown the fault.

The practical consequence is that this case cannot be automated through the
hub. `device_power` is the mode that reproduces it, and it switches the
device's own supply: a network relay if one is configured (see
lib/power/), otherwise an operator working the switch by hand. With a
relay it runs unattended, which is what makes a fault this intermittent
practical to chase -- three failures in four cycles, but only after a real
cold boot.

`port_power` is kept anyway: ten clean cycles is a useful regression baseline,
and if it ever starts failing that is a different and worse defect.

`module_reload` leaves the device alone and re-probes an already-running one.
It exists because of the one measurable difference between the working and
failing cycles in the 2026-08-13 trace: probe ran 43.9 ms after
SET_CONFIGURATION in the cycle that worked and 0.1 ms after it in the ones
that did not, because the working cycle probed from modprobe rather than from
enumeration.

WHAT A FAILURE HERE MEANS
-------------------------
Not that the driver returned an error -- it will not have. It means the device
was left in a state where it accepts USB traffic and produces no audio, and
the driver did not notice. Report `silent_cycles` and `first_silent_cycle`;
the run that produced them is worth an OpenVizsla trace.
"""

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from lib.case import Case          # noqa: E402
from lib import alsa, power, priv    # noqa: E402

CHANNELS = 6                       # fixed by the driver: min == max
FORMAT = "S24_3LE"
BYTES_PER_SAMPLE = 3


def nonzero_fraction(path):
    """Fraction of frames in a raw S24_3LE capture carrying any non-zero byte.

    Frame-granular rather than sample-granular on purpose: the question is
    whether the converter is running at all, and a frame is the smallest unit
    that answers it. Reading the whole file matters -- a device that starts
    late would look dead from a prefix alone.
    """
    frame = CHANNELS * BYTES_PER_SAMPLE
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
    if not total:
        return None, 0
    return live / total, total


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


def wait_for_substreams(idx, timeout):
    """Poll until playback and capture substreams exist. See JT-HOTPLUG-005."""
    t0 = time.time()
    deadline = t0 + timeout
    while True:
        subs = alsa.substreams(idx)
        missing = [w for w in ("playback", "capture") if not subs[w]]
        if not missing or time.time() >= deadline:
            return round((time.time() - t0) * 1000, 1), missing
        time.sleep(0.02)


def reenumerate(c, trigger, off_seconds, settle, operator_timeout):
    """Put the device through the chosen re-entry path.

    Returns (card_index, elapsed_ms) or (None, None) having already recorded
    the failure.
    """
    t0 = time.time()

    if trigger == "device_power":
        # The only mode known to reproduce the fault, because it is the only
        # one that gives the device a cold boot.
        if power.available():
            ok, detail = power.set_state(False)
            if not ok:
                c.fail(f"could not switch the device off: {detail}")
                return None, None
            _idx, gone = wait_for_card(False, settle)
            if gone is None:
                c.fail(f"card still present {settle}s after mains power was "
                       f"cut -- is the relay feeding the right outlet?")
                return None, None
            time.sleep(off_seconds)
            ok, detail = power.set_state(True)
            if not ok:
                c.fail(f"could not switch the device back on: {detail}")
                return None, None
        else:
            c.instruct("Switch the device OFF, wait for the LEDs to go dark, "
                       "then switch it ON again.")
            # Waiting on a person, not on the bus: the machine settle is far
            # too short for someone to reach the switch.
            _idx, gone = wait_for_card(False, operator_timeout)
            if gone is None:
                c.fail(f"card still present {operator_timeout}s after the "
                       f"power-off instruction -- was the device switched "
                       f"off?")
                return None, None
    elif trigger == "port_power":
        rc, _out, err = priv.usb_power("off")
        if rc != 0:
            c.fail(f"usb-power off failed: {(err or '').strip()[:120]}")
            return None, None
        _idx, gone = wait_for_card(False, settle)
        if gone is None:
            c.fail(f"card still present {settle}s after the port went down")
            return None, None
        time.sleep(off_seconds)
        rc, _out, err = priv.usb_power("on")
        if rc != 0:
            c.fail(f"usb-power on failed: {(err or '').strip()[:120]}")
            return None, None
    else:
        rc, err = priv.unload_module()
        if rc != 0:
            c.fail(f"module unload failed: {str(err).strip()[:120]}")
            return None, None
        time.sleep(off_seconds)
        rc, err = priv.load_module()
        if rc != 0:
            c.fail(f"module load failed: {str(err).strip()[:120]}")
            return None, None

    back = (operator_timeout if trigger == "device_power"
            and not power.available() else settle)
    idx, seen = wait_for_card(True, back)
    if seen is None:
        c.fail(f"card did not come back within {back}s")
        return None, None
    return idx, round((seen - t0) * 1000, 1)


def main():
    c = Case()
    c.require_card()
    c.require_tools("arecord")

    ok, why = priv.available()
    if not ok:
        c.blocked(f"privileged helper unavailable: {why}")

    trigger = c.params.get("trigger", "device_power")
    if trigger not in ("device_power", "port_power", "module_reload"):
        c.blocked(f"unknown trigger {trigger!r}")
    if trigger == "port_power" and not priv.usb_switch_available():
        c.blocked("no Jockey 3 behind a ppps-capable hub port")
    if trigger == "device_power":
        # A relay makes this unattended; without one it needs somebody at the
        # switch, and saying which is in play belongs in the record.
        if power.available():
            c.metric("power_control", "relay")
        elif c.attended:
            c.metric("power_control", "operator")
        else:
            c.blocked("device_power needs either a configured mains relay "
                      "(see lib/power/) or an operator at the switch")

    iterations = int(c.params.get("iterations_per_run", 10))
    # Long enough for the device's own supply to drain: the point is a cold
    # boot, and reconnecting mains too early gives a warm one, which is the
    # case that already works.
    off_seconds = float(c.params.get("off_seconds", 5))
    settle = float(c.params.get("settle_seconds", 8))
    seconds = int(c.params.get("seconds", 2))
    rate = int(c.params.get("rate", 44100))
    floor = float(c.params.get("min_nonzero_fraction", 0.01))
    operator_timeout = float(c.params.get("operator_timeout_seconds", 120))

    c.metric("trigger", trigger)
    c.metric("rate", rate)

    fractions, enumerate_ms = [], []
    silent_cycles = 0
    first_silent = None
    cycles = 0

    for i in range(1, iterations + 1):
        idx, took = reenumerate(c, trigger, off_seconds, settle,
                                operator_timeout)
        if idx is None:
            break
        enumerate_ms.append(took)

        settle_ms, missing = wait_for_substreams(idx, settle)
        if missing:
            c.fail(f"cycle {i}: no {', '.join(missing)} substream after "
                   f"re-enumeration")
            break

        device = alsa.device_name(idx)
        raw = os.path.join(c.workdir, f"engine_{i}.raw")
        try:
            p = subprocess.run(
                ["arecord", "-D", device, "-d", str(seconds), "-f", FORMAT,
                 "-c", str(CHANNELS), "-r", str(rate), "-t", "raw", raw],
                capture_output=True, text=True, timeout=seconds + 30)
            rc, err = p.returncode, p.stderr
        except subprocess.TimeoutExpired:
            rc, err = 124, "arecord did not finish"
        if rc != 0:
            c.fail(f"cycle {i}: arecord exited {rc}: "
                   f"{(err or '').strip()[:120]}")
            break

        frac, frames = nonzero_fraction(raw)
        cycles = i
        if frac is None:
            c.fail(f"cycle {i}: captured nothing to measure")
            break
        fractions.append(round(frac, 4))

        if frac < floor:
            silent_cycles += 1
            if first_silent is None:
                first_silent = i
            c.fail(f"cycle {i}: capture is bit-exact silent over {frames} "
                   f"frames ({frac:.4%} non-zero, floor {floor:.0%}) -- the "
                   f"device accepted the stream without starting its audio "
                   f"engine. Nothing in dmesg will say so.")
        else:
            # Keep the evidence only for the cycles that failed.
            try:
                os.unlink(raw)
            except OSError:
                pass

        c.metric(f"pcm_settle_ms_{i}", settle_ms)

    c.metric("cycles", cycles)
    c.metric("silent_cycles", silent_cycles)
    c.metric("first_silent_cycle", first_silent)
    if fractions:
        c.metric("nonzero_fraction_min", min(fractions))
        c.metric("nonzero_fraction_max", max(fractions))
    if enumerate_ms:
        c.metric("enumerate_ms_max", max(enumerate_ms))

    if silent_cycles:
        c.note(f"{silent_cycles} of {cycles} cycles produced a device that "
               f"accepted playback and generated no audio. The raw captures "
               f"for those cycles are kept in the work directory. This run is "
               f"worth an OpenVizsla trace -- see "
               f"re/usb/init_timing_comparison.md.")
    c.done()


if __name__ == "__main__":
    main()
