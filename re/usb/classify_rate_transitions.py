#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Classify every rate change in the vendor OpenVizsla corpus by direction
and by divide-ratio class, instead of by clock family.

Milestone 13 (re/rate_change_stall.md) established on 2026-08-16 that this
driver's capture stalls track the hardware's divide-ratio transition -- the
74HC74 flip-flop moving from /256 to /512 -- and not the 74HC00 oscillator
mux switching between the 22.5792 MHz and 24.576 MHz crystals. "Clock family"
(44k1 vs 48k) was a correlate of that in every sweep run so far, not the
mechanism. This script re-derives, from the raw parsed events rather than
from prose written about them, which rate transition each vendor capture
actually contains and which divide-ratio class it belongs to, so a
capture-vs-driver comparison can be built on the same criterion the hardware
finding uses.

/512 rates: 44100, 48000 (crystal, DSP-clock respectively)
/256 rates: 88200, 96000

A transition's "old" rate is read directly from the GET_RATE(ep=none) query
every vendor sequence performs before programming the new one -- not assumed
from the capture's context -- so a capture that starts mid-session (as
capture_macos_rate_change.txt does; see its own commentary) is still
classified correctly.

    ./classify_rate_transitions.py                    # every *_events.txt
    ./classify_rate_transitions.py capture_macos_rate_change_events.txt
    ./classify_rate_transitions.py --csv out.csv
"""

import argparse
import csv
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TRACES = os.path.join(HERE, "openvizsla")

EVENT_RE = re.compile(r"^EVENT\s+(\d+)\s+\[([^\]]+)\]\s+at\s+([\d.]+)\s*s")
OLD_RATE_RE = re.compile(r"GET_RATE ep=none.*->\s*(\d+)\s*Hz")
NEW_RATE_RE = re.compile(r"SET_RATE.*->\s*(\d+)\s*Hz")

DIV512 = {44100, 48000}    # rates using the /512 divide ratio
XTAL = {44100, 88200}      # rates sourced from the 22.5792 MHz crystal


def divider_class(old, new):
    """('within' | 'cross' | 'lateral' | None, 'up' | 'down' | None).

    'within'  -- same oscillator, divide ratio changes (e.g. 96000<->48000)
    'cross'   -- different oscillator, divide ratio changes (e.g. 96000<->44100)
    'lateral' -- different oscillator, divide ratio unchanged (e.g. 44100<->48000)
    None      -- old == new (not a real change, e.g. a cold-init GET/SET pair)
    """
    if old == new:
        return None, None
    direction = "down" if new < old else "up"
    old_div = 512 if old in DIV512 else 256
    new_div = 512 if new in DIV512 else 256
    if old_div == new_div:
        cls = "lateral"
    else:
        same_osc = (old in XTAL) == (new in XTAL)
        cls = "within" if same_osc else "cross"
    return cls, direction


def events(path):
    """Yield (event_num, kind, old_rate, new_rate) for every EVENT block
    that contains both a GET_RATE(ep=none) and at least one SET_RATE."""
    num = kind = old = new = None

    def flush():
        if num is not None and old is not None and new is not None:
            yield_row = (num, kind, int(old), int(new))
            return yield_row
        return None

    for line in open(path, encoding="ascii", errors="replace"):
        m = EVENT_RE.match(line.strip())
        if m:
            row = flush()
            if row:
                yield row
            num, kind, old, new = m.group(1), m.group(2), None, None
            continue
        if num is None:
            continue
        m = OLD_RATE_RE.search(line)
        if m:
            old = m.group(1)
            continue
        m = NEW_RATE_RE.search(line)
        if m:
            new = m.group(1)
    row = flush()
    if row:
        yield row


def classify_file(path):
    name = os.path.basename(path).replace("_events.txt", "")
    rows = []
    for num, kind, old, new in events(path):
        cls, direction = divider_class(old, new)
        if cls is None:
            continue
        rows.append({
            "capture": name,
            "event": num,
            "kind": kind,
            "old_hz": old,
            "new_hz": new,
            "pair": f"{old}->{new}",
            "direction": direction,
            "divider_class": cls,
        })
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*",
                     help="*_events.txt files (default: all in openvizsla/)")
    ap.add_argument("--csv", help="write full rows to this CSV path")
    ap.add_argument("--summary", action="store_true",
                     help="print only the per-(direction, divider_class) counts")
    args = ap.parse_args()

    files = args.files or sorted(glob.glob(os.path.join(TRACES, "*_events.txt")))
    rows = []
    for f in files:
        path = f if os.path.isabs(f) or os.path.exists(f) else os.path.join(TRACES, f)
        rows.extend(classify_file(path))

    if not rows:
        print("no rate transitions found", file=sys.stderr)
        return 1

    if not args.summary:
        width = max(len(r["capture"]) for r in rows)
        for r in rows:
            print(f"{r['capture']:<{width}}  event {r['event']:>2}  "
                  f"{r['pair']:>13}  {r['direction']:<4}  {r['divider_class']}")
        print()

    counts = {}
    for r in rows:
        key = (r["direction"], r["divider_class"])
        counts.setdefault(key, []).append(r["pair"])
    print("direction  divider_class  n   pairs seen")
    for (direction, cls), pairs in sorted(counts.items()):
        uniq = sorted(set(pairs))
        print(f"{direction:<9}  {cls:<13}  {len(pairs):<3} {', '.join(uniq)}")

    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\nwrote {len(rows)} rows to {args.csv}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
