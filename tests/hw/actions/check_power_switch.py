#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise the mains relay on its own, away from any test.

JT-AUDIO-005 depends on this relay to give the device a cold boot. When that
case fails it should be because the driver failed, and proving the relay works
belongs here rather than inside a run where a dead outlet and a dead audio
engine look alike.

    ./check_power_switch.py            report what is configured and its state
    ./check_power_switch.py --cycle    actually switch it, and time it

Reads are the default on purpose. This cuts mains power to hardware, so
nothing switches unless asked, and whatever state the device was found in is
restored before exit -- including after a failure part way through.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from lib import machineconf, power    # noqa: E402


def step(label, ok, detail=""):
    print(f"  {'ok ' if ok else 'FAIL'}  {label}"
          + (f"  ({detail})" if detail else ""))
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cycle", action="store_true",
                    help="switch the relay off and on (default: read only)")
    ap.add_argument("--off-seconds", type=float, default=5.0)
    args = ap.parse_args()

    conf = machineconf.path()
    print(f"config   {conf}"
          + ("" if os.path.exists(conf) else "  (not present)"))
    if not power.configured():
        print("\nNo power switch configured. Set power_switch.url in the file "
              "above,\nor export JOCKEY3_POWER_SWITCH. See machine.yaml.example.")
        return 2

    settings = power._settings()
    print(f"backend  {settings.get('type')}  {settings.get('url')}")
    print()

    failures = 0
    if not step("relay answers", power.available()):
        print("\nConfigured but not reachable. Nothing was switched.")
        return 1

    original = power.state()
    if not step("state is readable", original in ("ON", "OFF"),
                str(original)):
        return 1

    if not args.cycle:
        print("\nRead-only. Pass --cycle to exercise switching.")
        return 0

    print()
    try:
        # Off, then on, regardless of which state it started in -- the point
        # is to exercise both transitions and both confirmations.
        t0 = time.time()
        ok, detail = power.set_state(False)
        failures += not step("switch off", ok, f"{detail}, "
                             f"{(time.time() - t0) * 1000:.0f} ms")

        failures += not step("reads back OFF", power.state() == "OFF",
                             str(power.state()))

        print(f"  ..    holding off for {args.off_seconds:g}s "
              f"(a cold boot needs the supply to drain)")
        time.sleep(args.off_seconds)

        t0 = time.time()
        ok, detail = power.set_state(True)
        failures += not step("switch on", ok, f"{detail}, "
                             f"{(time.time() - t0) * 1000:.0f} ms")
        failures += not step("reads back ON", power.state() == "ON",
                             str(power.state()))

        print()
        t0 = time.time()
        ok, detail = power.cycle(off_seconds=args.off_seconds)
        failures += not step("cycle() end to end", ok,
                             f"{detail}, {time.time() - t0:.1f} s")
        failures += not step("device left powered", power.state() == "ON",
                             str(power.state()))
    finally:
        # Whatever happened above, put it back the way it was found.
        if power.state() != original:
            print(f"\nrestoring original state {original}")
            power.set_state(original == "ON")

    print()
    if failures:
        print(f"{failures} check(s) failed")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
