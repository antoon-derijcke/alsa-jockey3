#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""When does streaming resume after a rate change, and who resumes it first?

Milestone 13 -- the capture endpoint sometimes failing to restart after a rate
change -- has always been treated as a separate problem from the cold-boot
fault fixed in milestone 15. The cold-boot result raises the obvious question:
if the device needs ~150 ms after enumeration before it will accept
initialization, does it also need settling time after being *reconfigured*?

This measures, per rate-change sequence in the vendor captures:

  stop_before_ms    last bulk packet before the sequence began. How long the
                    host had already been quiet when it started reprogramming.
  resume_out_ms     first bulk OUT on EP 0x05 after SET_STATUS -- the HOST
                    deciding to stream again. This is a host policy choice and
                    is directly comparable to what our driver does.
  resume_in_ms      first bulk IN on EP 0x86 after SET_STATUS -- the DEVICE
                    producing capture data again. This is the device telling
                    us when it is actually ready, and is the number milestone
                    13 cares about.

Anchors come from the *_events.txt files (absolute times), bulk traffic from
the corresponding *_parsed.txt. NAKs are already discarded by
parse_openvizsla.py, so an IN transaction here means real data moved.

    ./rate_change_stream_timing.py
    ./rate_change_stream_timing.py --csv out.csv
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


def events(path):
    """Yield (kind, absolute_start, [(abs_time, request), ...])."""
    kind = base = None
    rows = []
    with open(path, encoding="ascii", errors="replace") as f:
        for line in f:
            m = EVENT_RE.match(line.strip())
            if m:
                if base is not None:
                    yield kind, base, rows
                kind, base, rows = m.group(2), float(m.group(3)), []
                continue
            if base is None:
                continue
            m = ROW_RE.match(line)
            if not m or "|" not in line:
                continue
            req = m.group(2)
            if req.startswith("Request") or set(req) <= set("-"):
                continue
            rows.append((base + float(m.group(1)) / 1000.0, req))
    if base is not None:
        yield kind, base, rows


def bulk(path):
    """Bulk traffic as two sorted lists of timestamps: (out_ep5, in_ep6)."""
    out5, in6 = [], []
    with open(path, encoding="ascii", errors="replace") as f:
        for line in f:
            parts = line.split("|")
            if len(parts) < 4:
                continue
            ts, direction, target = (p.strip() for p in parts[:3])
            if "." not in target:
                continue
            try:
                t = float(ts)
                ep = int(target.split(".")[1])
            except ValueError:
                continue
            try:
                nbytes = int(parts[3].strip())
            except ValueError:
                nbytes = 0
            if ep == 5 and direction == "OUT" and nbytes:
                out5.append(t)
            elif ep == 6 and direction == "IN" and nbytes:
                in6.append(t)
    out5.sort()
    in6.sort()
    return out5, in6


def after(times, t):
    for x in times:
        if x > t:
            return x
    return None


def before(times, t):
    prev = None
    for x in times:
        if x >= t:
            break
        prev = x
    return prev


def measure(events_path, parsed_path):
    out5, in6 = bulk(parsed_path)
    name = os.path.basename(events_path).replace("_events.txt", "")
    rows = []
    for kind, base, rows_in in events(events_path):
        if "rate" not in kind:
            continue
        if not rows_in:
            continue
        t_start = rows_in[0][0]
        t_status = None
        for t, req in rows_in:
            if req.startswith("SET_STATUS"):
                t_status = t
        if t_status is None:
            continue
        last_out = before(out5, t_start)
        last_in = before(in6, t_start)
        last_any = max([x for x in (last_out, last_in) if x is not None],
                       default=None)
        r_out = after(out5, t_status)
        r_in = after(in6, t_status)
        rows.append({
            "capture": name,
            "kind": kind,
            "sequence_ms": round((t_status - t_start) * 1000, 1),
            "stop_before_ms": (None if last_any is None
                               else round((t_start - last_any) * 1000, 1)),
            "resume_out_ms": (None if r_out is None
                              else round((r_out - t_status) * 1000, 1)),
            "resume_in_ms": (None if r_in is None
                             else round((r_in - t_status) * 1000, 1)),
        })
    return rows


def span(rs, key):
    v = sorted(r[key] for r in rs if r[key] is not None)
    if not v:
        return "--"
    return f"{v[0]:.0f}" if v[0] == v[-1] else f"{v[0]:.0f}-{v[-1]:.0f}"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv")
    args = ap.parse_args()

    rows = []
    for ev in sorted(glob.glob(os.path.join(TRACES, "*_events.txt"))):
        parsed = ev.replace("_events.txt", "_parsed.txt")
        if not os.path.exists(parsed):
            continue
        rows.extend(measure(ev, parsed))
    if not rows:
        sys.exit("no rate-change sequences with a matching parsed trace")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"{len(rows)} sequences -> {args.csv}")
        return

    print(f"{'capture':<44} {'n':>3} {'sequence':>10} {'quiet before':>13} "
          f"{'EP05 resume':>12} {'EP86 resume':>12}")
    print("-" * 100)
    by = {}
    for r in rows:
        by.setdefault(r["capture"], []).append(r)
    for cap, rs in by.items():
        print(f"{cap:<44} {len(rs):>3} {span(rs,'sequence_ms'):>10} "
              f"{span(rs,'stop_before_ms'):>13} {span(rs,'resume_out_ms'):>12} "
              f"{span(rs,'resume_in_ms'):>12}")
    print("\nall times in ms; resume_* are measured from SET_STATUS")


if __name__ == "__main__":
    main()
