#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""L3/L5: sustained MIDI OUT traffic, watching for the device to wedge.

Two modes, one underlying burst loop, selected by whether params.rates is
set -- there is no argv mode switch, since one of the two catalog cases that
runs this file supplies no rate list and the other always does:

  rates unset      L5 endurance: one rate, run for duration_seconds
                   (JT-MIDI-007).
  rates set        L3 per-rate throughput: prime each rate in turn and hold
                   the achieved byte rate to a tolerance band around the
                   driver's ceiling for a much shorter window (JT-MIDI-004).

One file because both modes are the same burst loop, differing only in how
long it runs and whether the device is switched to a specific rate first.
Splitting them would duplicate the loop, the stall accounting and the
pacing logic for no benefit.

WHAT THE ENDURANCE MODE IS HUNTING
-----------------------------------
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
CEILING_BPS was lowered from 3125 to 2500 on 2026-08-19, after a rate sweep
across both Remix units (see re/playback_stall_wedge.md) found sustained
MIDI OUT above ~2500-2810 B/s made the device's control surface periodically
stop responding to LED updates, well under the raw 31250 bps MIDI line rate
that 3125 B/s approximated. The driver's own limiter moved with it (see
jockey3_get_next_midi_out_byte() in jockey3.c) -- this constant exists to
mirror that value, not to set it independently, so update both together.
The historical notes below still describe measurements taken against the old
3125 constant; they were correct for their time and are not rewritten here.

The driver limits MIDI OUT to roughly 3125 bytes/sec, because the device
overruns its own buffers and truncates messages if fed faster. The endurance
mode aims just under that (load_fraction), by design: it wants a realistic,
sustained LED-blink load, not to find the ceiling. Driving deliberately over
the limit would back the rawmidi buffer up and produce a drain error -- which
lib/rules.yaml classifies as a failure, correctly, since on a healthy device
it means the URB ring has died. Provoking that on purpose would make the case
fail on its own doing and destroy the one signature worth watching for. This
is also why JT-MIDI-003 ("flood past the ceiling") was retired rather than
added here: it cannot be done without risking exactly that false failure.

Paced with a direct os.write() per burst on one open fd, not an amidi
subprocess per burst -- run_burst_window() used to spawn amidi(1), which is
exactly the ~59%-of-target process-spawn overhead described under PER-RATE
MODE below, except it had only ever been fixed there. Confirmed 2026-08-19
(arm64-prod, load_fraction 0.9): 1604 B/s achieved against a 2812 B/s target
under the old amidi-per-burst design.

PER-RATE MODE
--------------
jockey3_get_next_midi_out_byte() paces via
midi_out_acc += 3125; emit when midi_out_acc >= midi_rate_divisor, where
midi_rate_divisor = rate / PLOYTEC_PLAYBACK_FRAMES is recomputed on every rate
change. PLOYTEC_PLAYBACK_FRAMES is 10, which divides all four supported rates
exactly, so there is no integer-truncation bias in the divisor itself; working
through the algebra, the achieved byte rate this produces is ~3125 B/s at
every sample rate -- the divisor scaling exists to cancel the rate-dependent
URB completion frequency, not to make the target rate-dependent.

Unlike the endurance mode, this mode does not throttle its own writes at
all -- it writes as fast as write() will go, via measure_throughput(); the
kernel's own backpressure on the finite rawmidi buffer paces that to
whatever the driver actually drains, so bytes_sent/elapsed is a direct
measurement of the driver's real output rate rather than of this script's
own overhead. An earlier version paced small amidi(1) invocations against a
target interval, which measured the cost of spawning a process every
~130 ms far more than it measured the driver -- confirmed against hardware
on 2026-08-16, where every rate read back at the same ~59% of target
regardless of sample rate, the signature of a constant per-call overhead
rather than a real per-rate effect.

Each rate is primed with a few seconds of silent PCM playback first --
enough to drive jockey3_pcm_hw_params() through the rate change and let the
new midi_rate_divisor take effect -- before the timed measurement window
starts, so the reprogram itself is not counted against the achieved rate.

achieved_bps is asserted against CEILING_BPS +/-tolerance (default 5%) at
every rate. First clean measurement from this direct-write design
(x86_64-prod, 2026-08-16): 3122 / 3120 / 3121 / 3120 B/s at 44.1 / 48 / 88.2 /
96 kHz -- flat across rates to within 0.1% and within 0.2% of the driver's own
3125 constant, confirming the exact-division algebra above rather than the
2906-3188 B/s spread an earlier manual measurement (the old interactive
miditest.py) had suggested. That manual figure was never a counter-measurement
to weigh against this one: miditest.py finds the ceiling by ear/eye, nudging
its send rate up and down in 10% steps while watching /proc's rawmidi buffer
occupancy for the first sign of backup -- a methodology built for "close
enough to play with", not to resolve the ceiling tighter than roughly that
10% step plus human reaction time. 5% tolerance leaves ~25x margin over the
0.2% deviation actually observed, room for run-to-run and machine-to-machine
jitter without losing the ability to catch a real regression. write_failures
and unended playback stalls are asserted on regardless of any baseline; those
have unambiguous expected values (zero).
"""

import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from lib.case import Case          # noqa: E402
from lib import alsa, kmsg         # noqa: E402

ONSET_RE = re.compile(r"(Playback|Capture) URB stream stalled: no completion for \d+ ms")
# The two ways an outage ends. A stall almost always ends in a restart rather
# than recovering on its own, because every recovery path in the driver goes
# through a URB stop/start -- so counting only recoveries would read every
# handled stall as an unresolved one.
CLOSED_RE = re.compile(
    r"(Playback|Capture) URB stream (?:recovered after|restarted after stalling for) \d+ ms")


def stall_counts():
    """Per-direction (onsets, closed) currently in the kernel log.

    Counted over the whole log and differenced around the soak rather than
    sliced from a marker: the runner owns the marker for this case, and writing
    a second one would leave two candidates for the slice it takes afterwards.
    """
    try:
        lines = kmsg.read_log()
    except Exception:       # noqa: BLE001 - diagnostics must not fail the soak
        return None
    if not lines:
        return None
    counts = {"Playback": [0, 0], "Capture": [0, 0]}
    for ln in lines:
        m = ONSET_RE.search(ln)
        if m:
            counts[m.group(1)][0] += 1
            continue
        m = CLOSED_RE.search(ln)
        if m:
            counts[m.group(1)][1] += 1
    return counts

# The driver's MIDI OUT ceiling, from the leaky-bucket limiter in
# jockey3_get_next_midi_out_byte(). Bytes per second. See PACING above for
# why this is 2500, not the device's raw MIDI line rate.
CEILING_BPS = 2500

PLAYBACK_CHANNELS = 4               # fixed by the driver: Master + Headphone
PCM_FORMAT = "S24_3LE"              # the only format the device accepts

# Note On / Note Off for the 4 Hot Cue LEDs on both decks.
# Gives a visible effect, so a soak that is running is obvious from across the
# room.
# A single led would result in a blink frequency hardly visible to the human
# eye. Choosing a set of LEDs will result is a lower update frequency due to
# the number of bytes to be sent.

ON = "90 0B 7F 90 0C 7F 90 0D 7F 90 0E 7F 91 0B 7F 91 0C 7F 91 0D 7F 91 0E 7F"
OFF = "90 0B 00 90 0C 00 90 0D 00 90 0E 00 91 0B 00 91 0C 00 91 0D 00 91 0E 00"


def prime_rate(c, device, rate, seconds=2.0):
    """Force a rate change and let it settle before any MIDI is timed.

    Silence rather than a tone: nothing here cares what the device outputs,
    only that jockey3_pcm_hw_params() has run and midi_rate_divisor reflects
    the new rate by the time aplay exits.
    """
    frame_bytes = PLAYBACK_CHANNELS * 3   # S24_3LE
    zero = subprocess.Popen(["dd", "if=/dev/zero", "bs=4096",
                             f"count={int(rate * frame_bytes * seconds) // 4096 + 1}"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    p = subprocess.Popen(
        ["aplay", "-D", device, "-r", str(rate), "-c", str(PLAYBACK_CHANNELS),
         "--format", PCM_FORMAT, "-t", "raw"],
        stdin=zero.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True)
    zero.stdout.close()
    try:
        _out, err = p.communicate(timeout=seconds + 30)
    except subprocess.TimeoutExpired:
        p.kill()
        zero.kill()
        return False
    zero.wait(timeout=5)
    if p.returncode != 0:
        c.note(f"priming aplay at {rate} Hz exited {p.returncode}: "
               f"{(err or '').strip()[:120]}")
        return False
    return True


def measure_throughput(c, node_path, duration, check_every, report_every, label=""):
    """Write continuously to the rawmidi device node for duration seconds.

    No subprocess per chunk: one open(), then a loop of os.write() calls on
    a blocking fd. A full kernel rawmidi buffer makes write() block until the
    driver has drained room for more, so the rate this loop achieves is the
    driver's, not a process-spawn budget -- see the module docstring for why
    that distinction matters here.

    Returns (bytes_sent, elapsed, write_failures, card_lost).
    """
    prefix = f"{label}: " if label else ""
    pattern = bytes(int(b, 16) for b in (ON + " " + OFF).split())
    # A few KB per write(): large enough that the write() syscall itself is
    # not the bottleneck, small enough that one call does not block through
    # more than a fraction of a second at the driver's real drain rate.
    reps = max(1, 2048 // len(pattern) + 1)
    chunk = pattern * reps

    try:
        fd = os.open(node_path, os.O_WRONLY)
    except OSError as e:
        c.fail(f"{prefix}could not open {node_path}: {e}")
        return 0, 0.0, 1, False

    c.status(f"{prefix}measuring achieved MIDI OUT throughput on "
            f"{node_path} for {duration:.0f}s")

    started = time.time()
    deadline = started + duration
    next_check = started + check_every
    next_report = started + report_every
    bytes_sent = 0
    write_failures = 0
    card_lost = False

    try:
        while time.time() < deadline:
            try:
                bytes_sent += os.write(fd, chunk)
            except OSError as e:
                write_failures += 1
                if write_failures <= 3:
                    c.note(f"{prefix}write failed after "
                           f"{time.time() - started:.0f}s: {e}")
                time.sleep(0.1)

            now = time.time()
            if now >= next_check:
                next_check = now + check_every
                idx, _ = alsa.find_card()
                if idx is None:
                    card_lost = True
                    c.fail(f"{prefix}card disappeared after "
                           f"{now - started:.0f}s of MIDI traffic")
                    break

            if now >= next_report:
                next_report = now + report_every
                so_far = now - started
                rate_so_far = bytes_sent / so_far if so_far > 0 else 0
                c.status(f"   {prefix}{so_far:>6.0f}s  {bytes_sent:>9d} bytes  "
                        f"{rate_so_far:>6.0f} B/s"
                        + (f"  {write_failures} WRITE FAILURES"
                           if write_failures else ""))
    finally:
        os.close(fd)

    elapsed = time.time() - started
    return bytes_sent, elapsed, write_failures, card_lost


def run_burst_window(c, node_path, duration, load, burst_pattern, burst_bytes,
                     check_every, report_every, label=""):
    """Send bursts for duration seconds. Returns (bytes_sent, bursts,
    write_failures, elapsed, card_lost).

    Direct os.write() on one open fd, like measure_throughput() -- not an
    amidi subprocess per burst. That used to be exactly the ~59%-of-target
    process-spawn overhead the module docstring describes fixing for the
    per-rate mode (measure_throughput()), except it was never applied here:
    this endurance mode kept spawning amidi once per burst, so a
    load_fraction of 0.9 achieved barely more than half that in practice.
    Confirmed 2026-08-19 (arm64-prod, load_fraction 0.9): 1604 B/s achieved
    against a 2812 B/s target, 57.0% -- the same signature.
    """
    interval = burst_bytes / (CEILING_BPS * load)
    prefix = f"{label}: " if label else ""

    try:
        fd = os.open(node_path, os.O_WRONLY)
    except OSError as e:
        c.fail(f"{prefix}could not open {node_path}: {e}")
        return 0, 0, 1, 0.0, False

    c.progress(f"{prefix}soaking {node_path} for {duration:.0f}s at "
               f"~{CEILING_BPS * load:.0f} B/s "
               f"({burst_bytes} bytes every {interval * 1000:.0f} ms)")

    started = time.time()
    deadline = started + duration
    next_check = started + check_every
    next_report = started + report_every

    bytes_sent = 0
    bursts = 0
    write_failures = 0
    card_lost = False

    try:
        while time.time() < deadline:
            t0 = time.time()
            try:
                os.write(fd, burst_pattern)
                bytes_sent += burst_bytes
            except OSError as e:
                write_failures += 1
                # Do not fail on the first one. A single refused write during
                # a long soak is worth knowing about, but the thing being
                # hunted is a device that stops responding and stays that
                # way -- which shows up as write_failures climbing, and is
                # judged at the end.
                if write_failures <= 3:
                    c.note(f"{prefix}MIDI OUT write failed after "
                           f"{time.time() - started:.0f}s: {e}")
            bursts += 1

            now = time.time()
            if now >= next_check:
                next_check = now + check_every
                idx, _ = alsa.find_card()
                if idx is None:
                    card_lost = True
                    c.fail(f"{prefix}card disappeared after {now - started:.0f}s "
                           f"of MIDI traffic")
                    break

            if now >= next_report:
                next_report = now + report_every
                c.progress(f"   {prefix}{now - started:>6.0f}s  "
                           f"{bytes_sent:>9d} bytes  {bursts:>7d} bursts"
                           + (f"  {write_failures} WRITE FAILURES"
                              if write_failures else ""))

            # Pace against the interval, not a flat sleep: the write() itself
            # takes some of the budget too, small as it is compared to the
            # amidi spawn it replaced.
            slack = interval - (time.time() - t0)
            if slack > 0:
                time.sleep(slack)
    finally:
        os.close(fd)

    elapsed = time.time() - started
    return bytes_sent, bursts, write_failures, elapsed, card_lost


def report_stalls(c, before, after, elapsed, label="", metric_suffix=""):
    """Record urb_stalls_* metrics and fail on an unended playback stall.

    Shared between both modes -- see the module docstring for why only
    playback is asserted on. label is for human-readable messages
    ("44100 Hz"); metric_suffix is appended to metric names as-is ("_44100"),
    since a metric name cannot contain a space.
    """
    prefix = f"{label}: " if label else ""
    if before is None or after is None:
        return
    stalls = {d: after[d][0] - before[d][0] for d in before}
    unended = {d: (after[d][0] - before[d][0]) - (after[d][1] - before[d][1])
               for d in before}
    suffix = metric_suffix
    for d in ("Playback", "Capture"):
        c.metric(f"urb_stalls_{d.lower()}{suffix}", stalls[d])

    if unended["Playback"] > 0:
        c.fail(f"{prefix}{unended['Playback']} playback URB stall(s) never "
               f"ended during {elapsed:.0f}s of MIDI traffic -- see the onset "
               f"timestamps in dmesg for when it started")
    elif stalls["Playback"]:
        c.note(f"{prefix}{stalls['Playback']} playback URB stall(s), all resolved")
    if unended["Capture"] > 0:
        c.note(f"{prefix}{unended['Capture']} capture URB stall(s) still open "
               f"at the end; expected if a rate change deferred one, since "
               f"nothing here opens capture to collect it")


def final_liveness_check(c):
    idx, _ = alsa.find_card()
    if idx is None:
        c.fail("card was gone by the end of the run")
        return
    subs = alsa.substreams(idx)
    for what in ("playback", "capture", "rawmidi"):
        if not subs[what]:
            c.fail(f"no {what} substream left after the run")


def main():
    c = Case()
    c.require_card()

    # Fraction of the driver's ceiling to aim at. Below 1.0 on purpose; see the
    # pacing note in the module docstring.
    load = float(c.params.get("load_fraction", 0.9))
    check_every = float(c.params.get("check_interval_seconds", 30))
    report_every = float(c.params.get("progress_interval_seconds", 60))

    node = alsa.rawmidi_node(c.card)
    if not node:
        c.blocked("no rawmidi device node found for direct write")

    # A burst of several ON/OFF pairs amortizes fixed per-write overhead
    # (negligible for os.write(), but the burst grouping is also what gives
    # the LED blink pattern its visible rhythm -- see the module comment
    # above ON/OFF).
    burst = [ON, OFF] * int(c.params.get("messages_per_burst", 8))
    burst_bytes = sum(len(m.split()) for m in burst)
    burst_pattern = bytes(int(b, 16) for m in burst for b in m.split())

    rates = c.params.get("rates")

    if rates:
        c.require_tools("aplay")
        device = c.device or alsa.device_name(c.card)
        duration = float(c.params.get("duration_seconds", 30))
        tolerance = float(c.params.get("tolerance", 0.05))
        lo, hi = CEILING_BPS * (1 - tolerance), CEILING_BPS * (1 + tolerance)
        card_lost = False

        for rate in rates:
            if not prime_rate(c, device, rate):
                c.fail(f"{rate} Hz: could not switch the device to this rate")
                continue

            before = stall_counts()
            bytes_sent, elapsed, write_failures, card_lost = \
                measure_throughput(c, node, duration, check_every,
                                   report_every, label=f"{rate} Hz")
            after = stall_counts()

            if elapsed > 0:
                achieved = bytes_sent / elapsed
                c.metric(f"achieved_bps_{rate}", round(achieved, 1))
                # Printed unconditionally, not just on failure. measure_
                # throughput()'s own progress is c.status() -- transient,
                # redrawn in place -- and its periodic update only fires
                # every report_every seconds (default 60), longer than this
                # case's own 30s-per-rate default; without a final line here
                # the transient "measuring..." status never gets replaced by
                # anything, and the achieved rate never reaches the console
                # at all, pass or fail. This line is what it gets rewritten
                # to once the rate's measurement is done.
                c.progress(f"   {rate} Hz: achieved {achieved:.0f} B/s "
                          f"(target {CEILING_BPS} B/s +/-{tolerance * 100:.0f}%)")
                if not (lo <= achieved <= hi):
                    c.fail(f"{rate} Hz: achieved {achieved:.0f} B/s, expected "
                           f"{CEILING_BPS} B/s +/-{tolerance * 100:.0f}%")

            c.metric(f"write_failures_{rate}", write_failures)
            if write_failures:
                c.fail(f"{rate} Hz: {write_failures} MIDI OUT write(s) failed")

            report_stalls(c, before, after, elapsed, label=f"{rate} Hz",
                         metric_suffix=f"_{rate}")

            if card_lost:
                break

        c.metric("rates_tested", len(rates))
        if not card_lost:
            final_liveness_check(c)
    else:
        duration = float(c.params.get("duration_seconds", 1800))

        before = stall_counts()
        if before is None:
            c.note("kernel log unreadable; stall detection is left entirely to "
                   "the runner's classifier, which cannot see a stall that "
                   "outlives this case")

        bytes_sent, bursts, write_failures, elapsed, card_lost = \
            run_burst_window(c, node, duration, load, burst_pattern, burst_bytes,
                             check_every, report_every)
        after = stall_counts()

        c.metric("elapsed_seconds", round(elapsed, 1))
        c.metric("bytes_sent", bytes_sent)
        c.metric("bursts", bursts)
        c.metric("write_failures", write_failures)
        if elapsed > 0:
            c.metric("achieved_bps", round(bytes_sent / elapsed, 1))

        if write_failures:
            c.fail(f"{write_failures} of {bursts} MIDI OUT writes failed "
                   f"during the soak")

        report_stalls(c, before, after, elapsed)

        if not card_lost:
            final_liveness_check(c)

    c.done()


if __name__ == "__main__":
    main()
