#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""L3: unbind and rebind the driver from the device, repeatedly.

Derived from scripts-alsa-dev/bind_unbind_test.sh. The reason it exists:
devres was replaced with manual devm actions (jockey3_kfree_action), so the
plausible regression is a leak or a double free on the init-failure and
disconnect paths -- exactly the paths jockey3_probe() and jockey3_disconnect()
take on every cycle here.

Unlike JT-PROBE-001, the module stays loaded and the device stays on the bus
the whole time: only the driver<->interface binding is cycled, through
/sys/bus/usb/drivers/<module>/{bind,unbind} via jockey3-testctl. That is a
different path than modprobe/rmmod -- it exercises jockey3_probe() and
jockey3_disconnect() without also invoking module init/exit and the rest of
modprobe's own bookkeeping.

This case does not go looking for memory errors itself -- classifying dmesg is
the runner's job, per lib/case.py, and lib/rules.yaml already turns a "BUG:"
or "KASAN:" line into an INVESTIGATE verdict that aborts the run. What this
case controls is only the setup rules.yaml depends on: that the cycle count is
high enough and that KASAN, if compiled in, gets to see every cycle. On a
kernel without KASAN or similar a leak or double free is just as real and just
as invisible here -- see the pass criterion in catalog.yaml.
"""

import os
import sys
import time

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from lib.case import Case          # noqa: E402
from lib import alsa, env, priv    # noqa: E402


def wait_for_card(present, timeout):
    """Wait for the card to appear or disappear. Returns (index, when|None)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        idx, _ = alsa.find_card()
        if (idx is not None) == present:
            return idx, time.time()
        time.sleep(0.02)
    idx, _ = alsa.find_card()
    return idx, None


def _stale_helper(err):
    """True when the installed jockey3-testctl predates this case's verbs.

    priv.stale() compares file contents, but a case that has not been
    installed yet does not know to check that -- it only sees "unknown verb"
    come back from the helper. Surfaced as blocked rather than failed: a
    missing verb is a setup problem, not evidence against the driver.
    """
    return "unknown verb" in (err or "").lower()


def main():
    c = Case()
    c.require_card()
    ok, why = priv.available()
    if not ok:
        c.blocked(f"cannot unbind or bind the driver: {why}")
    if not env.module_loaded():
        c.blocked("module is not loaded")

    iterations = int(c.params.get("iterations_per_run", 50))
    settle = float(c.params.get("settle_seconds", 5))

    start_idx, _ = alsa.find_card()
    slots = {start_idx} if start_idx is not None else set()
    bind_ms, unbind_ms, unbind_call_ms, bind_call_ms = [], [], [], []

    for i in range(1, iterations + 1):
        t0 = time.time()
        rc, _out, err = priv.unbind()
        called = time.time()
        if rc != 0:
            if i == 1 and _stale_helper(err):
                c.blocked("jockey3-testctl has no unbind verb -- run "
                          "`sudo tests/hw/priv/install.sh` on this machine")
            c.fail(f"iteration {i}: unbind failed: {(err or '').strip()[:120]}")
            break
        unbind_call_ms.append(round((called - t0) * 1000, 1))
        # The sysfs unbind write is synchronous -- device_release_driver()
        # runs jockey3_disconnect() before echo returns -- so by the time the
        # helper call above completes the card is already gone. This wait is
        # therefore measuring the residual after the call, the same split
        # hotplug_cycle.py makes between switch_ms and teardown_ms: it can
        # legitimately read close to zero, and that is the driver's speed,
        # not a broken measurement.
        _idx, gone = wait_for_card(False, settle)
        if gone is None:
            c.fail(f"iteration {i}: card still present {settle}s after unbind")
            break
        unbind_ms.append(round((gone - called) * 1000, 1))

        t0 = time.time()
        rc, _out, err = priv.bind()
        called = time.time()
        if rc != 0:
            c.fail(f"iteration {i}: bind failed: {(err or '').strip()[:120]}")
            break
        bind_call_ms.append(round((called - t0) * 1000, 1))
        idx, seen = wait_for_card(True, settle)
        if seen is None:
            c.fail(f"iteration {i}: card did not reappear {settle}s after bind")
            break
        bind_ms.append(round((seen - called) * 1000, 1))
        slots.add(idx)

        subs = alsa.substreams(idx)
        for kind in ("playback", "capture", "rawmidi"):
            if not subs[kind]:
                c.fail(f"iteration {i}: no {kind} substream after rebind")

        c.progress(f"cycle {i}/{iterations}  down {unbind_ms[-1]:>6.0f} ms  "
                   f"up {bind_ms[-1]:>6.0f} ms  card hw:{idx}")

    # Leave it bound: every case after this one expects a working card.
    idx_now, _ = alsa.find_card()
    if idx_now is None:
        priv.bind()
        wait_for_card(True, settle)

    c.metric("slots_used", len(slots))
    if len(slots) > 1:
        c.fail(f"card index changed across bind/unbind: saw {sorted(slots)}")

    if bind_ms:
        c.metric("bind_ms", {"n": len(bind_ms), "min": min(bind_ms),
                             "max": max(bind_ms),
                             "mean": round(sum(bind_ms) / len(bind_ms), 1)})
    if unbind_ms:
        c.metric("unbind_ms", {"n": len(unbind_ms), "min": min(unbind_ms),
                               "max": max(unbind_ms),
                               "mean": round(sum(unbind_ms) / len(unbind_ms), 1)})
    # Tool cost of the helper call itself, kept separate so it cannot
    # masquerade as driver behavior -- see the note by unbind_call_ms above.
    if unbind_call_ms:
        c.metric("unbind_call_ms", {
            "n": len(unbind_call_ms), "min": min(unbind_call_ms),
            "max": max(unbind_call_ms),
            "mean": round(sum(unbind_call_ms) / len(unbind_call_ms), 1)})
    if bind_call_ms:
        c.metric("bind_call_ms", {
            "n": len(bind_call_ms), "min": min(bind_call_ms),
            "max": max(bind_call_ms),
            "mean": round(sum(bind_call_ms) / len(bind_call_ms), 1)})

    c.done()


if __name__ == "__main__":
    main()
