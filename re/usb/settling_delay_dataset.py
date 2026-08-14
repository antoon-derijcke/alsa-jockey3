#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Extract the cold-boot settling-delay bisect into a tidy CSV.

The 2026-08-14 bisect established how long the Jockey 3 needs after USB
enumeration before it will accept initialization -- see
init_timing_comparison.md. This turns the JT-AUDIO-005 run records into one row
per power-cycle, so the raw measurements survive independently of the result
directories (which are git-ignored and get pruned) and can be loaded straight
into pandas.

    ./settling_delay_dataset.py                 # regenerate the CSV
    ./settling_delay_dataset.py --runs          # one row per run instead

THE BUILD-ID TO DELAY MAPPING IS DATA, NOT DERIVABLE
----------------------------------------------------
Every bisect step was built with `build_module.sh --uncommitted`, deliberately:
per Frank's rule, interim development iterations do not get committed, because
a history of eight throwaway steps is worse than useless and anyone pulling the
middle of it gets something that does not work. The consequence is that the
delay a build carried is *not* recoverable from git -- the manifests record
`git_describe: <sha>-dirty` and nothing about the sleep value.

So DELAY_MS below is the primary record of which build had which delay. It was
kept as the bisect ran. If it is lost, the dataset becomes uninterpretable, and
the only recovery is to rebuild each value and match GNU build-ids -- which does
work, since the toolchain is reproducible (the 250 ms build was built twice, in
separate sessions, and came out as the same build-id 97a55434 both times).
"""

import argparse
import csv
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
RESULTS = os.path.join(REPO, "tests", "hw", "results")

# build-id prefix -> msleep() value in jockey3_initialize(), in ms.
DELAY_MS = {
    "f6a71204": 0,      # pre-instrumentation baseline, commit acd8477
    "ecfdd2b4": 0,      # control run, re-confirming the fault with markers
    "c3f050c8": 15,
    "5341ff26": 30,
    "5d49d27b": 60,
    "44486fb2": 125,
    "97a55434": 250,    # the shipped value
    "e6ee079e": 500,
    "6efaa705": 1000,
    "25355bfe": 2000,   # first confirmation that a delay fixes it at all
}

# Per-cycle metrics are emitted as "<name>_<cycle>". Anything matching one of
# these becomes a column; the cycle number becomes a row.
PER_CYCLE = ("power_on_to_enumerate_ms", "enumerate_to_first_ep0_ms",
             "power_on_to_first_ep0_ms", "pcm_settle_ms", "nonzero_fraction")

CASE = "JT-AUDIO-005"


def runs():
    """Every JT-AUDIO-005 result, newest last."""
    for path in sorted(glob.glob(os.path.join(RESULTS, "*", "*", "run.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, ValueError):
            continue
        for res in doc.get("results", []):
            if res.get("id") != CASE:
                continue
            yield doc, res, path


def split_metrics(metrics):
    """Separate per-cycle metrics from run-level ones.

    Returns (per_cycle, run_level) where per_cycle is {cycle: {name: value}}.
    """
    cycles, run_level = {}, {}
    for key, value in metrics.items():
        m = re.match(r"^(.*)_(\d+)$", key)
        if m and m.group(1) in PER_CYCLE:
            cycles.setdefault(int(m.group(2)), {})[m.group(1)] = value
        else:
            run_level[key] = value
    return cycles, run_level


def rows_per_cycle():
    out = []
    for doc, res, path in runs():
        env = doc.get("env", {})
        drv = env.get("driver", {}) or {}
        build = (drv.get("build") or {})
        bid = (drv.get("build_id") or "")[:8]
        cycles, run_level = split_metrics(res.get("metrics", {}))
        # A run that predates the kernel-clock markers has no per-cycle timing;
        # keep it anyway, because its verdict is still a data point.
        n = run_level.get("cycles") or 0
        silent = run_level.get("silent_cycles") or 0
        first_silent = run_level.get("first_silent_cycle")
        for cyc in sorted(cycles) or range(1, (n or 0) + 1):
            row = {
                "run_id": doc.get("run_id"),
                "started": doc.get("started"),
                "build_id": bid,
                "delay_ms": DELAY_MS.get(bid),
                "kernel": (env.get("kernel") or {}).get("release"),
                "machine": (env.get("machine") or {}).get("hostname"),
                "driver_dirty": build.get("kernel_driver_dirty"),
                "cycle": cyc,
                # Per-cycle silence is only recorded from the run that added
                # nonzero_fraction_<i>; before that the run tells us how many
                # cycles were silent and which was first, so a run that was
                # wholly silent or wholly live is still unambiguous.
                "silent": (None if silent not in (0, n)
                           else bool(silent)),
            }
            row.update({k: cycles.get(cyc, {}).get(k) for k in PER_CYCLE})
            out.append(row)
        if not cycles and not n:
            continue
    return out


def rows_per_run():
    out = []
    for doc, res, _ in runs():
        env = doc.get("env", {})
        drv = env.get("driver", {}) or {}
        bid = (drv.get("build_id") or "")[:8]
        _, run_level = split_metrics(res.get("metrics", {}))
        out.append({
            "run_id": doc.get("run_id"),
            "started": doc.get("started"),
            "build_id": bid,
            "delay_ms": DELAY_MS.get(bid),
            "status": res.get("status"),
            "cycles": run_level.get("cycles"),
            "silent_cycles": run_level.get("silent_cycles"),
            "nonzero_fraction_min": run_level.get("nonzero_fraction_min"),
            "nonzero_fraction_max": run_level.get("nonzero_fraction_max"),
        })
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", action="store_true",
                    help="one row per run instead of one per cycle")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    rows = rows_per_run() if args.runs else rows_per_cycle()
    if not rows:
        sys.exit(f"no {CASE} results under {RESULTS}")
    dest = args.output or os.path.join(
        HERE, "settling_delay_runs.csv" if args.runs
        else "settling_delay_cycles.csv")
    with open(dest, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} rows -> {os.path.relpath(dest, REPO)}")


if __name__ == "__main__":
    main()
