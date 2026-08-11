#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""L5: sustained MIDI OUT traffic, watching for the device to wedge.

WHAT THIS IS HUNTING
--------------------
On 2026-08-11 the device stopped completing URBs on every endpoint and stopped
answering EP0, while still enumerated. It happened minutes after the two MIDI
cases ran, and nothing noticed for about fourteen minutes -- the first sign was
ALSA's own "rawmidi drain error", because MIDI OUT rides in byte 480 of every
playback packet and can only drain while the playback URBs are flowing.

The root cause is still unknown. MIDI traffic at the driver's rate limit is the
first suspect purely because of when it appeared, so this case reproduces that
load for as long as it is given.

WHY IT IS WORTH RUNNING EVEN WHEN IT PASSES
-------------------------------------------
The driver now carries a URB liveness watchdog, and a wedge that used to be
invisible for a quarter of an hour is reported within 1.5 s with a measured
onset age. That is the datum the recovery work is waiting on: either this case
produces a timestamped onset, or a long clean run says the wedge is not
reachable through MIDI load and the search moves elsewhere.

Either outcome is progress. A pass here is not "nothing happened", it is
evidence.

HOW THE VERDICT IS REACHED
--------------------------
Partly by the runner. lib/rules.yaml classifies the watchdog's heartbeat
('... URB stream still stalled ...') as driver_fail, so a stall that outlives a
minute turns the run red on the runner's judgement. The stall ONSET is only
counted -- see the note in rules.yaml for why it cannot be a failure -- and
appears as the urb_stall_onset_ms metric.

That is not sufficient on its own, which is why this file counts stalls too.
The heartbeat needs the watchdog to still be ticking a minute after the stall
started, and it is not always: the tick stops without requeueing once the device
is marked disconnected, and it stops when the case ends. A wedge in the last
minute of the soak, or one the device does not survive, produces an onset and no
heartbeat -- and the onset alone cannot fail anything. So the counts are read
back from the kernel log here and an onset with no matching recovery is a
failure, which is the same rule rules.yaml states in prose.

The rest is the coarser thing the classifier cannot see at all: that the card is
still there, and that MIDI OUT still accepts writes, sampled throughout rather
than only at the end.

PACING
------
The driver limits MIDI OUT to roughly 3125 bytes/sec, because the device
overruns its own buffers and truncates messages if fed faster. This case aims
just under that. Driving deliberately over the limit would back the rawmidi
buffer up and produce a drain error -- which lib/rules.yaml classifies as a
failure, correctly, since on a healthy device it means the URB ring has died.
Provoking that on purpose would make the case fail on its own doing and destroy
the one signature worth watching for.
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from lib.case import Case          # noqa: E402
from lib import alsa, kmsg         # noqa: E402

ONSET_RE = re.compile(r"URB stream stalled: no completion for \d+ ms")
# The two ways an outage ends. A stall almost always ends in a restart rather
# than recovering on its own, because every recovery path in the driver goes
# through a URB stop/start -- so counting only recoveries would read every
# handled stall as an unresolved one.
CLOSED_RE = re.compile(r"URB stream (?:recovered after|restarted after stalling for) \d+ ms")


def stall_counts():
    """(onsets, closed) currently in the kernel log.

    Counted over the whole log and differenced around the soak rather than
    sliced from a marker: the runner owns the marker for this case, and writing
    a second one would leave two candidates for the slice it takes afterwards.
    """
    try:
        lines = kmsg.read_log()
    except Exception:       # noqa: BLE001 - diagnostics must not fail the soak
        return None, None
    if not lines:
        return None, None
    return (sum(1 for ln in lines if ONSET_RE.search(ln)),
            sum(1 for ln in lines if CLOSED_RE.search(ln)))

# The driver's MIDI OUT ceiling, from the leaky-bucket limiter in
# jockey3_get_next_midi_out_byte(). Bytes per second.
CEILING_BPS = 3125

# Note On / Note Off for the deck Load LEDs -- three bytes each, the same
# messages JT-MIDI-002 uses. Chosen because they are known to be accepted and
# have a visible effect, so a soak that is running is obvious from across the
# room.
ON = "90 0B 7F"
OFF = "90 0B 00"


def find_port(c):
    port = alsa.rawmidi_device(c.card)
    if port:
        return port
    rc, out, _err = c.run(["amidi", "-l"], timeout=20)
    if rc != 0:
        return None
    for line in (out or "").splitlines():
        if "Jockey" in line and line.strip().startswith("IO"):
            return line.split()[1]
    return None


def main():
    c = Case()
    c.require_card()
    c.require_tools("amidi")

    duration = float(c.params.get("duration_seconds", 1800))
    # Fraction of the driver's ceiling to aim at. Below 1.0 on purpose; see the
    # pacing note in the module docstring.
    load = float(c.params.get("load_fraction", 0.9))
    check_every = float(c.params.get("check_interval_seconds", 30))
    report_every = float(c.params.get("progress_interval_seconds", 60))

    port = find_port(c)
    if not port:
        c.blocked("no Jockey 3 rawmidi port found")

    # One amidi invocation per burst, so the cost of starting the process has
    # to be paid out of the budget rather than ignored. A burst of several
    # messages amortizes it; one message per invocation could not keep up.
    burst = [ON, OFF] * int(c.params.get("messages_per_burst", 8))
    burst_bytes = sum(len(m.split()) for m in burst)
    interval = burst_bytes / (CEILING_BPS * load)

    c.progress(f"soaking {port} for {duration:.0f}s at "
               f"~{CEILING_BPS * load:.0f} B/s "
               f"({burst_bytes} bytes every {interval * 1000:.0f} ms)")

    onsets_before, closed_before = stall_counts()
    if onsets_before is None:
        c.note("kernel log unreadable; stall detection is left entirely to the "
               "runner's classifier, which cannot see a stall that outlives "
               "this case")

    started = time.time()
    deadline = started + duration
    next_check = started + check_every
    next_report = started + report_every

    bytes_sent = 0
    bursts = 0
    write_failures = 0
    card_lost = 0

    while time.time() < deadline:
        t0 = time.time()
        rc, _out, err = c.run(["amidi", "-p", port, "-S", " ".join(burst)],
                              timeout=30)
        if rc != 0:
            write_failures += 1
            # Do not fail on the first one. A single refused write during a
            # half-hour soak is worth knowing about, but the thing being hunted
            # is a device that stops responding and stays that way -- which
            # shows up as write_failures climbing, and is judged at the end.
            if write_failures <= 3:
                c.note(f"MIDI OUT write failed after "
                       f"{time.time() - started:.0f}s: "
                       f"{(err or '').strip()[:100]}")
        else:
            bytes_sent += burst_bytes
        bursts += 1

        now = time.time()
        if now >= next_check:
            next_check = now + check_every
            idx, _ = alsa.find_card()
            if idx is None:
                card_lost += 1
                c.fail(f"card disappeared after {now - started:.0f}s of MIDI "
                       f"traffic")
                break

        if now >= next_report:
            next_report = now + report_every
            c.progress(f"   {now - started:>6.0f}s  {bytes_sent:>9d} bytes  "
                       f"{bursts:>7d} bursts"
                       + (f"  {write_failures} WRITE FAILURES"
                          if write_failures else ""))

        # Pace against the interval, not against a fixed sleep: amidi's own
        # runtime is a large and variable part of the budget, and sleeping a
        # flat interval on top of it would sit well under the rate this is
        # meant to sustain.
        slack = interval - (time.time() - t0)
        if slack > 0:
            time.sleep(slack)

    elapsed = time.time() - started
    c.metric("elapsed_seconds", round(elapsed, 1))
    c.metric("bytes_sent", bytes_sent)
    c.metric("bursts", bursts)
    c.metric("write_failures", write_failures)
    if elapsed > 0:
        c.metric("achieved_bps", round(bytes_sent / elapsed, 1))

    if write_failures:
        c.fail(f"{write_failures} of {bursts} MIDI OUT writes failed during "
               f"the soak")

    onsets_after, closed_after = stall_counts()
    if onsets_before is not None and onsets_after is not None:
        onsets = onsets_after - onsets_before
        closed = closed_after - closed_before
        c.metric("urb_stalls_seen", onsets)
        c.metric("urb_stalls_closed", closed)
        # An onset with a matching close is a stream that came back, whether on
        # its own or via a restart. That is worth recording but is not what
        # this case is hunting. An onset left over at the end is a stall that
        # never ended -- the wedge, and the one thing here that must not pass
        # quietly.
        if onsets > closed:
            c.fail(f"{onsets - closed} URB stall(s) never ended during "
                   f"{elapsed:.0f}s of MIDI traffic -- see the onset timestamps "
                   f"in dmesg for when it started")
        elif onsets:
            c.note(f"{onsets} URB stall(s) during the soak, all resolved")

    if not card_lost:
        idx, _ = alsa.find_card()
        if idx is None:
            c.fail("card was gone by the end of the soak")
        else:
            subs = alsa.substreams(idx)
            for what in ("playback", "capture", "rawmidi"):
                if not subs[what]:
                    c.fail(f"no {what} substream left after the soak")

    c.done()


if __name__ == "__main__":
    main()
