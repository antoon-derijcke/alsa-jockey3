#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""L3: cut power to the device's hub port, restore it, and see what comes back.

The driver is left loaded throughout. This is not a module load/unload cycle
-- that is JT-PROBE-001 -- it is the device disappearing from the bus and
re-enumerating underneath a driver that stayed put, which is a different path
through probe() and disconnect().

WHAT IT IS ACTUALLY LOOKING FOR
-------------------------------
The card index. ALSA allocates slots from a bitmap under a mutex, and the
failure mode of a leak is not a crash or a warning -- it is an index that
climbs by one per cycle until the machine runs out of card slots, hours later,
in some other test. Watching it get REUSED is the whole point; everything else
here is a precondition for that observation being meaningful.

WHAT THE TIMINGS DO AND DO NOT MEASURE
--------------------------------------
`switch_ms` is how long the uhubctl call itself took, and it is nobody's
driver metric -- uhubctl re-reads port status after acting and waits before
doing so, which puts seconds of fixed cost in the path. It is recorded only so
that cost stays visible instead of hiding inside the numbers that matter.

`teardown_ms` and `enumerate_ms` are measured from when that call RETURNS, so
they are the part the kernel is responsible for. The first version of this
case started the clock before the call and produced 3839, 3839, 3854, 3851 ms
-- ten readings within 15 ms of each other, which is the signature of a sleep
rather than of work, and which would have made a real regression in
enumeration invisible underneath it.

Even so these are upper bounds: the port may already be dark before uhubctl
returns, in which case the teardown has partly or wholly happened and reads as
near zero. The authoritative timings are the dmesg timestamps between "USB
disconnect" and "Initialization complete." -- but reading the kernel log is
the runner's job, not a case's, so what is here is a proxy and is labeled as
one.

WHAT A PORT POWER-OFF IS NOT
----------------------------
It is not a cable pull. Power drops at once, the device is gone instantly, and
resubmits fail synchronously with -ENODEV. A real unplug degrades over several
USB frames and the in-flight URBs accumulate -71 (EPROTO) first, which is what
drives the driver's consecutive-error give-up path. Measured 2026-08-10, idle
and under active playback alike: that path is never reached this way. It is
not a gap in this case -- slot reuse is what is being tested -- but it does
mean this case cannot stand in for JT-HOTPLUG-001.
"""

import os
import sys
import time

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from lib.case import Case          # noqa: E402
from lib import alsa, priv         # noqa: E402


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


def power_on(c, settle):
    """Restore power and wait for the card.

    Returns (index, switch_ms, enumerate_ms). The two timings are kept apart
    deliberately -- see the note on measurement in the module docstring.
    """
    t0 = time.time()
    rc, _out, err = priv.usb_power("on")
    switched = time.time()
    if rc != 0:
        c.fail(f"usb-power on failed: {(err or '').strip()[:120]}")
        return None, None, None
    idx, seen = wait_for_card(True, settle)
    switch_ms = round((switched - t0) * 1000, 1)
    if seen is None:
        return None, switch_ms, None
    return idx, switch_ms, round((seen - switched) * 1000, 1)


def main():
    c = Case()
    c.require_card()

    ok, why = priv.available()
    if not ok:
        c.blocked(f"cannot switch port power: {why}")
    if not priv.usb_switch_available():
        # The runner normally catches this and demotes the case to manual
        # before it ever starts. Reaching it here means the hub went away
        # between the capability probe and now, which is worth saying plainly
        # rather than failing with a confusing usb-power error.
        c.blocked("no Jockey 3 behind a ppps-capable hub port")

    iterations = int(c.params.get("iterations_per_run", 10))
    off_seconds = float(c.params.get("off_seconds", 2))
    settle = float(c.params.get("settle_seconds", 8))

    start_idx, _ = alsa.find_card()
    slots, enumerate_ms, teardown_ms, switch_ms = set(), [], [], []
    if start_idx is not None:
        slots.add(start_idx)
    c.metric("card_index_first", start_idx)

    powered_off = False
    cycles = 0
    try:
        for i in range(1, iterations + 1):
            t0 = time.time()
            rc, _out, err = priv.usb_power("off")
            switched = time.time()
            if rc != 0:
                c.fail(f"iteration {i}: usb-power off failed: "
                       f"{(err or '').strip()[:120]}")
                break
            powered_off = True
            switch_ms.append(round((switched - t0) * 1000, 1))

            _idx, gone = wait_for_card(False, settle)
            if gone is None:
                c.fail(f"iteration {i}: card still present {settle}s after "
                       f"the port was powered down")
                break
            teardown_ms.append(round((gone - switched) * 1000, 1))

            # Held dark deliberately. Powering straight back on can complete
            # before the host controller has finished tearing the old device
            # down, which tests the hub's timing rather than the driver's.
            time.sleep(off_seconds)

            idx, on_switch_ms, ms = power_on(c, settle)
            powered_off = False
            if on_switch_ms is not None:
                switch_ms.append(on_switch_ms)
            if idx is None:
                c.fail(f"iteration {i}: card did not reappear within "
                       f"{settle}s of power being restored")
                break
            enumerate_ms.append(ms)
            slots.add(idx)
            cycles += 1

            subs = alsa.substreams(idx)
            missing = [w for w in ("playback", "capture", "rawmidi")
                       if not subs[w]]
            for what in missing:
                c.fail(f"iteration {i}: no {what} after re-enumeration")

            # The card index is the whole point, so it is what the progress
            # line leads with: a reader watching this scroll past sees the
            # leak the moment it starts, without waiting for the verdict.
            c.progress(
                f"cycle {i}/{iterations}  down {teardown_ms[-1]:>5.0f} ms  "
                f"up {ms:>5.0f} ms  card hw:{idx}"
                f"   (hub {switch_ms[-2]:.0f}+{switch_ms[-1]:.0f} ms)"
                + ("  MISSING " + ", ".join(missing) if missing else ""))
    finally:
        # Never leave the rig dark. A case that fails halfway and walks away
        # with the port powered down takes every case after it with it, and
        # the next person to look finds a controller that appears to be dead.
        if powered_off:
            idx, _ms = power_on(c, settle)
            if idx is None:
                c.note("PORT LEFT POWERED DOWN -- run "
                       "`sudo jockey3-testctl usb-power on` by hand")

    c.metric("cycles", cycles)
    c.metric("slots_used", len(slots))
    end_idx, _ = alsa.find_card()
    c.metric("card_index_last", end_idx)

    # The point of the case. One slot means it was released and reused every
    # time; more means it was not, and the count is how many leaked.
    if len(slots) > 1:
        c.fail(f"card index was not reused: saw {sorted(slots)} across "
               f"{cycles} cycle(s) -- slot leak")

    if enumerate_ms:
        c.metric("enumerate_ms", {"n": len(enumerate_ms),
                                  "min": min(enumerate_ms),
                                  "max": max(enumerate_ms),
                                  "mean": round(sum(enumerate_ms)
                                                / len(enumerate_ms), 1)})
    if teardown_ms:
        c.metric("teardown_ms", {"n": len(teardown_ms),
                                 "min": min(teardown_ms),
                                 "max": max(teardown_ms),
                                 "mean": round(sum(teardown_ms)
                                               / len(teardown_ms), 1)})
    # Tool cost, kept out of the two metrics above so it cannot masquerade as
    # driver behavior. Worth recording rather than discarding: it is most of
    # the wall clock of this case, so it is what to attack if the cycle count
    # ever needs to go up.
    if switch_ms:
        c.metric("switch_ms", {"n": len(switch_ms), "min": min(switch_ms),
                               "max": max(switch_ms),
                               "mean": round(sum(switch_ms)
                                             / len(switch_ms), 1)})
    c.done()


if __name__ == "__main__":
    main()
