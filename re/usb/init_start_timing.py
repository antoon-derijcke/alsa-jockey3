#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""How long does a host wait after enumeration before initializing the device?

This is the vendor-side counterpart to the settling-delay bisect of
2026-08-14 (see init_timing_comparison.md). That bisect established, on
hardware, that the Jockey 3 needs roughly 150 ms after USB enumeration before
it will accept its initialization -- program it sooner and the audio engine
never starts, silently. The obvious next question is what the vendor drivers
actually do here, and the captured traces can answer it.

The anchors, chosen to be comparable with what JT-AUDIO-005 measures from the
kernel log:

  SET_ADDRESS        the host starting to enumerate the device. This is the
                     closest wire equivalent of Linux's "new high-speed USB
                     device number N" message, which the hub thread logs just
                     before addressing.
  SET_CONFIGURATION  the device becoming configured. On Linux the USB core
                     does this before any driver probe runs.
  GET_FIRMWARE       the first Ploytec-specific transfer -- the vendor
                     protocol proper starting. In our driver this is
                     ploytec_get_firmware(), the first EP0 transfer
                     jockey3_initialize() makes, and the point the settling
                     delay is inserted before.
  SET_STATUS         the end of the arming sequence.

Note GET_FIRMWARE appears more than once: macOS reads it at the tail of
enumeration, to identify the device, and again inside the initialization
proper. The one that matters is the one beginning the arming sequence, and it
sits *beside* SET_CONFIGURATION rather than reliably after it -- macOS issues
it 1.2 ms after, Windows 1.7 ms before. So the read nearest SET_CONFIGURATION
is used; see the comment in measure() for what a naive rule did instead.

    ./init_start_timing.py                 # summary table over every capture
    ./init_start_timing.py --csv out.csv   # one row per initialization
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
ROW_RE = re.compile(r"^\s*([\d.]+)\s*\|[^|]*\|[^|]*\|[^|]*\|\s*(.+?)\s*$")


def platform_of(name):
    low = name.lower()
    if "macos" in low:
        return "macOS"
    if "win" in low:
        return "Windows"
    if "linux" in low:
        return "Linux"
    return "?"


def transfers(path):
    """Every control transfer in an events file, as (abs_seconds, request)."""
    base = None
    out = []
    with open(path, encoding="ascii", errors="replace") as f:
        for line in f:
            m = EVENT_RE.match(line.strip())
            if m:
                base = float(m.group(3))
                continue
            if base is None:
                continue
            m = ROW_RE.match(line)
            if not m or "|" not in line:
                continue
            req = m.group(2)
            if req.startswith("Request") or set(req) <= set("-"):
                continue
            out.append((base + float(m.group(1)) / 1000.0, req))
    out.sort(key=lambda r: r[0])
    return out


def cycles(items):
    """Split into initialization cycles, one per SET_ADDRESS.

    A capture holds several power-on cycles; each begins when the host
    addresses the device again.
    """
    starts = [i for i, (_, r) in enumerate(items) if r.startswith("SET_ADDRESS")]
    for n, i in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(items)
        yield items[i:end]


def first(seq, prefix, after=None):
    for t, r in seq:
        if after is not None and t < after:
            continue
        if r.startswith(prefix):
            return t
    return None


def measure(path):
    items = transfers(path)
    name = os.path.basename(path).replace("_events.txt", "")
    rows = []
    for seq in cycles(items):
        t_addr = seq[0][0]
        t_cfg = first(seq, "SET_CONFIGURATION")
        if t_cfg is None:
            continue
        # The arming sequence's own firmware read, not enumeration's. It sits
        # beside SET_CONFIGURATION rather than reliably after it: macOS issues
        # it 1.2 ms after, Windows 1.7 ms BEFORE, and a naive "first after"
        # rule silently picks up an unrelated read 45 s later in the Windows
        # samplerate capture. So take the GET_FIRMWARE nearest to
        # SET_CONFIGURATION, and only if it is adjacent to it.
        near = [t for t, r in seq if r.startswith("GET_FIRMWARE")
                and abs(t - t_cfg) <= 0.250]
        t_first = min(near, key=lambda t: abs(t - t_cfg)) if near else None
        if t_first is None:
            t_first = first(seq, "SET_INTERFACE", after=t_cfg)
        t_status = first(seq, "SET_STATUS", after=t_cfg)
        rows.append({
            "capture": name,
            "platform": platform_of(name),
            "addr_to_config_ms": round((t_cfg - t_addr) * 1000, 1),
            "config_to_first_ms": (None if t_first is None
                                   else round((t_first - t_cfg) * 1000, 1)),
            "addr_to_first_ms": (None if t_first is None
                                 else round((t_first - t_addr) * 1000, 1)),
            "addr_to_status_ms": (None if t_status is None
                                  else round((t_status - t_addr) * 1000, 1)),
        })
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv")
    ap.add_argument("traces", nargs="*")
    args = ap.parse_args()

    paths = args.traces or sorted(glob.glob(os.path.join(TRACES, "*_events.txt")))
    rows = []
    for p in paths:
        rows.extend(measure(p))
    if not rows:
        sys.exit("no initialization cycles found")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"{len(rows)} cycles -> {args.csv}")
        return

    print(f"{'capture':<44} {'plat':<8} {'n':>3} "
          f"{'addr->config':>14} {'->first EP0':>13} {'->SET_STATUS':>14}")
    print("-" * 100)
    by = {}
    for r in rows:
        by.setdefault((r["capture"], r["platform"]), []).append(r)
    for (cap, plat), rs in by.items():
        def span(key):
            v = sorted(x[key] for x in rs if x[key] is not None)
            if not v:
                return "--"
            return f"{v[0]:.0f}" if v[0] == v[-1] else f"{v[0]:.0f}-{v[-1]:.0f}"
        print(f"{cap:<44} {plat:<8} {len(rs):>3} "
              f"{span('addr_to_config_ms'):>14} {span('addr_to_first_ms'):>13} "
              f"{span('addr_to_status_ms'):>14}")


if __name__ == "__main__":
    main()
