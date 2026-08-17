#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Profile the structure of every rate-programming burst in the corpus.

`classify_rate_transitions.py` answers "which transitions exist" and keys off
the EVENT blocks `extract_events.py` produces. That unit is wrong for two
reasons once the question becomes "what does the sequence look like":

  * An EVENT can contain more than one rate change. Every vendor event holds
    exactly one, so this never showed, but the Linux driver's do -- event 5 of
    capture_2026-08-17_linux_ratechange holds three rate changes and a full
    re-enumeration. The classifier keeps only the last GET_RATE(ep=none) and
    the last SET_RATE it sees in a block, so those events were silently
    reduced to a single, mis-paired transition.
  * The interesting structure (burst length, endpoint order, the quiet windows
    either side of the burst) is a property of the burst, not of the event.

So this script re-derives from the transfer list directly. A *burst* is a
maximal run of SET_RATE transfers with no unrelated transfer between them; its
old rate is the nearest preceding GET_RATE(ep=none), which is what the device
itself reports rather than what the capture's context implies.

    ./rate_burst_profile.py                       # per-burst table, all traces
    ./rate_burst_profile.py --summary             # aggregate by direction/class
    ./rate_burst_profile.py --csv out.csv
    ./rate_burst_profile.py capture_..._events.txt
"""

import argparse
import csv
import glob
import os
import re
import sys

from classify_rate_transitions import divider_class

HERE = os.path.dirname(os.path.abspath(__file__))
TRACES = os.path.join(HERE, "openvizsla")

EVENT_RE = re.compile(r"^EVENT\s+(\d+)\s+\[([^\]]+)\]\s+at\s+([\d.]+)\s*s")
RATE_RE = re.compile(r"->\s*(\d+)\s*Hz")
SET_RATE_RE = re.compile(r"^SET_RATE ep=(\S+)")
GET_RATE_RE = re.compile(r"^GET_RATE ep=(\S+)")


def transfers(path):
    """Yield one dict per control transfer, tagged with its enclosing event."""
    event_num = event_kind = None
    event_at = 0.0
    for line in open(path, encoding="ascii", errors="replace"):
        m = EVENT_RE.match(line.strip())
        if m:
            event_num = int(m.group(1))
            event_kind = m.group(2)
            event_at = float(m.group(3))
            continue
        if event_num is None or "|" not in line:
            continue
        cols = [c.strip() for c in line.split("|")]
        if len(cols) < 5 or not cols[0]:
            continue
        try:
            t_ms = float(cols[0])
            gap_ms = float(cols[1]) if cols[1] else None
            stream = int(cols[3])
        except ValueError:
            continue            # the header row, and the dashed rule
        yield {
            "event": event_num,
            "kind": event_kind,
            "event_at": event_at,
            # t(ms) restarts at zero in every EVENT block, so anything that
            # measures across a block boundary has to use abs_ms.
            "abs_ms": event_at * 1000 + t_ms,
            "t_ms": t_ms,
            "gap_ms": gap_ms,
            "stream": stream,
            "req": cols[4],
        }


def bursts(path):
    """Yield a profile dict for every SET_RATE burst in one trace."""
    xfers = list(transfers(path))
    old_rate = None             # last GET_RATE(ep=none) seen, device-reported
    i = 0
    while i < len(xfers):
        x = xfers[i]
        m = GET_RATE_RE.match(x["req"])
        if m and m.group(1) == "none":
            r = RATE_RE.search(x["req"])
            if r:
                old_rate = int(r.group(1))
            i += 1
            continue
        if not SET_RATE_RE.match(x["req"]):
            i += 1
            continue

        # Both vendors precede the burst with a GET_STATUS + GET_RATE(none)
        # probe pair and a ~50 ms quiet window, but they place the window on
        # opposite sides of that pair: macOS waits after GET_RATE(none)
        # (so it lands in lead_gap_ms), Windows waits before GET_STATUS.
        # Measure the gap entering the whole probe-and-program block so the
        # two shapes are comparable.
        pre_block_gap = xfers[i]["gap_ms"]
        for k in (i - 1, i - 2):
            if k >= 0 and (xfers[k]["req"].startswith("GET_STATUS")
                           or GET_RATE_RE.match(xfers[k]["req"])):
                pre_block_gap = max(pre_block_gap or 0, xfers[k]["gap_ms"] or 0)
            else:
                break

        start = i
        eps, rates = [], []
        while i < len(xfers) and SET_RATE_RE.match(xfers[i]["req"]):
            eps.append(SET_RATE_RE.match(xfers[i]["req"]).group(1))
            r = RATE_RE.search(xfers[i]["req"])
            rates.append(int(r.group(1)) if r else None)
            i += 1
        end = i - 1

        new_rate = rates[-1]
        # The lone leading write and the burst proper are separated by a quiet
        # window on every vendor sequence; measure it rather than assume it.
        split = max(range(1, len(eps)), key=lambda k: xfers[start + k]["gap_ms"] or 0) \
            if len(eps) > 1 else None
        split_gap = xfers[start + split]["gap_ms"] if split else None

        # verify read, then the closing status poll(s)
        verify = None
        if i < len(xfers):
            m = GET_RATE_RE.match(xfers[i]["req"])
            if m and m.group(1) != "none":
                r = RATE_RE.search(xfers[i]["req"])
                verify = int(r.group(1)) if r else None
                i += 1
        settle_gap = terminator = None
        if i < len(xfers) and xfers[i]["req"].startswith("GET_STATUS"):
            settle_gap = xfers[i]["gap_ms"]
            i += 1
            terminator = "GET_STATUS"
            if i < len(xfers) and xfers[i]["req"].startswith("SET_STATUS"):
                terminator = "SET_STATUS"
                i += 1
            elif i < len(xfers) and xfers[i]["req"].startswith("GET_STATUS"):
                terminator = "GET_STATUS x2"
                i += 1

        cls, direction = divider_class(old_rate, new_rate) \
            if old_rate is not None else (None, None)
        yield {
            "capture": os.path.basename(path).replace("_events.txt", ""),
            "event": xfers[start]["event"],
            "kind": xfers[start]["kind"],
            "at_s": round(xfers[start]["event_at"] + xfers[start]["t_ms"] / 1000, 3),
            "old_hz": old_rate,
            "new_hz": new_rate,
            "pair": f"{old_rate}->{new_rate}",
            "direction": direction,
            "divider_class": cls,
            "writes": len(eps),
            "ep_order": ",".join(e.replace("0x", "") for e in eps),
            "pre_block_gap_ms": pre_block_gap,
            "lead_gap_ms": xfers[start]["gap_ms"],
            "split_after": split,
            "split_gap_ms": split_gap,
            "burst_ms": round(xfers[end]["t_ms"] - xfers[start]["t_ms"], 3),
            "verify_hz": verify,
            "settle_gap_ms": settle_gap,
            "terminator": terminator,
            # Anchor for the optional per-endpoint resume measurement; the
            # EVENT stream column cannot be used for this (see resume_times).
            "_anchor_ms": xfers[end]["abs_ms"],
            "resume_out_ms": None,
            "resume_in_ms": None,
        }
        old_rate = new_rate      # a burst leaves the device at the new rate


def resume_times(rows, parsed_path, window_s=6.0):
    """Fill resume_out_ms / resume_in_ms from the bulk stream, in place.

    The `stream` column of the events file counts EP 0x05 and 0x86 together,
    which is useless here: the whole of milestone 13 is playback continuing
    while capture stays dead, and a combined counter reports a healthy resume
    for exactly that case. Worse, it counts re-enumeration traffic too -- on a
    failing change the packets it sees are the dying playback stream, timed to
    a GET_DESCRIPTOR of the reset that the stall provoked.

    So resume has to come from the parsed trace, where `Target` is `addr.ep`
    and the two directions are separable. `resume_out_ms` is the first bulk
    OUT on EP 0x05 after the burst -- a host decision. `resume_in_ms` is the
    first bulk IN on EP 0x86 -- the device saying it is producing capture data
    again, which is the number milestone 13 cares about. `None` for the latter
    means capture never came back inside `window_s`.
    """
    pending = sorted(rows, key=lambda r: r["_anchor_ms"])
    if not pending:
        return
    lo = pending[0]["_anchor_ms"] / 1000
    hi = pending[-1]["_anchor_ms"] / 1000 + window_s
    with open(parsed_path, encoding="ascii", errors="replace") as fh:
        fh.readline(), fh.readline()          # header and rule
        head = 0
        for line in fh:
            cols = line.split("|", 4)
            if len(cols) < 4:
                continue
            try:
                t = float(cols[0])
            except ValueError:
                continue
            if t < lo:
                continue
            if t > hi:
                break
            direction = cols[1].strip()
            ep = cols[2].strip().rpartition(".")[2]
            if ep not in ("5", "6"):
                continue
            field = "resume_out_ms" if direction == "OUT" else "resume_in_ms"
            if (direction == "OUT") != (ep == "5"):
                continue                      # 0x05 is OUT, 0x86 is IN
            t_ms = t * 1000
            while head < len(pending) and \
                    pending[head]["resume_out_ms"] is not None and \
                    pending[head]["resume_in_ms"] is not None:
                head += 1
            for r in pending[head:]:
                if r["_anchor_ms"] > t_ms:
                    break
                if t_ms - r["_anchor_ms"] > window_s * 1000:
                    continue
                if r[field] is None:
                    r[field] = round(t_ms - r["_anchor_ms"], 3)


def fmt(v, width, prec=1):
    if v is None:
        return "-".rjust(width)
    if isinstance(v, float):
        return f"{v:.{prec}f}".rjust(width)
    return str(v).rjust(width)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="*_events.txt (default: all)")
    ap.add_argument("--summary", action="store_true",
                    help="aggregate by platform, direction and divider class")
    ap.add_argument("--csv", metavar="PATH", help="write every burst as CSV")
    ap.add_argument("--resume", action="store_true",
                    help="also measure per-endpoint stream resume; reads the "
                         "sibling *_parsed.txt, which is large and slow")
    args = ap.parse_args()

    paths = args.files or sorted(glob.glob(os.path.join(TRACES, "*_events.txt")))
    rows = []
    for p in paths:
        if not os.path.exists(p):
            p = os.path.join(TRACES, p)
        got = list(bursts(p))
        if args.resume:
            parsed = p.replace("_events.txt", "_parsed.txt")
            if os.path.exists(parsed):
                resume_times(got, parsed)
            else:
                print(f"no parsed trace for {os.path.basename(p)}, "
                      f"skipping resume", file=sys.stderr)
        for r in got:
            r.pop("_anchor_ms", None)
            if not args.resume:
                r.pop("resume_out_ms", None)
                r.pop("resume_in_ms", None)
        rows.extend(got)

    if args.csv:
        with open(args.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"{len(rows)} bursts -> {args.csv}", file=sys.stderr)

    if args.summary:
        groups = {}
        for r in rows:
            if r["divider_class"] is None:
                continue
            key = (r["capture"], r["direction"], r["divider_class"])
            groups.setdefault(key, []).append(r)
        print(f"{'capture':38} {'dir':5} {'class':8} {'n':>3} "
              f"{'writes':>7} {'pre ms':>9} {'split ms':>9} "
              f"{'settle ms':>10}" + (f" {'EP05 res':>12} {'EP86 res':>12}"
                                          if args.resume else ""))
        for key in sorted(groups):
            g = groups[key]

            def rng(field, prec=1):
                vals = [r[field] for r in g if r[field] is not None]
                if not vals:
                    return "-"
                lo, hi = min(vals), max(vals)
                if isinstance(lo, int):
                    return str(lo) if lo == hi else f"{lo}-{hi}"
                return f"{lo:.{prec}f}" if abs(hi - lo) < 0.05 \
                    else f"{lo:.{prec}f}-{hi:.{prec}f}"

            print(f"{key[0]:38} {key[1]:5} {key[2]:8} {len(g):>3} "
                  f"{rng('writes'):>7} {rng('pre_block_gap_ms'):>9} "
                  f"{rng('split_gap_ms'):>9} {rng('settle_gap_ms'):>10}"
                  + (f" {rng('resume_out_ms'):>12} {rng('resume_in_ms'):>12}"
                     if args.resume else ""))
        return

    if not args.csv:
        print(f"{'capture':32} {'ev':>4} {'pair':>14} {'dir':5} {'class':8} "
              f"{'w':>2} {'ep order':18} {'pre':>7} {'split':>7} "
              f"{'settle':>7} {'term':11}"
              + (f" {'EP05':>8} {'EP86':>8}" if args.resume else ""))
        for r in rows:
            print(f"{r['capture'][:32]:32} {r['event']:>4} {r['pair']:>14} "
                  f"{r['direction'] or '-':5} {r['divider_class'] or '-':8} "
                  f"{r['writes']:>2} {r['ep_order']:18} "
                  f"{fmt(r['pre_block_gap_ms'], 7)} {fmt(r['split_gap_ms'], 7)} "
                  f"{fmt(r['settle_gap_ms'], 7)} {(r['terminator'] or '-'):11}"
                  + (f" {fmt(r['resume_out_ms'], 8)} {fmt(r['resume_in_ms'], 8)}"
                     if args.resume else ""))


if __name__ == "__main__":
    main()
