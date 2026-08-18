#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""L3 semi-automated: firmware padding bytes are stripped from MIDI IN.

THE HUMAN IS THE ACTUATOR; THE MACHINE IS THE JUDGE -- same division as
JT-MIDI-001 (cases/midi_controls.py), and worth restating because this case
almost reused that script wholesale and deliberately did not.

WHY THIS IS A SEPARATE CASE, NOT A FLAG ON JT-MIDI-001
-------------------------------------------------------
JT-MIDI-001 asks "do my actions produce events", and its exit condition is
event counts: 5 button events, 20 continuous ones, whichever arrives first.
This case asks a different question -- "does anything UNEXPECTED also
arrive" -- and an event count has no bearing on it: padding can appear (or
fail to appear) regardless of how many real messages were seen, so requiring
a minimum count would tie an unrelated pass/fail to this case's own. Its
exit condition is purely the clock: watch for the full window, however much
or little traffic that produces, and there is no length of good traffic that
excuses not finding one bad byte.

Originally scoped to reuse JT-MIDI-001's own monitoring pass so this could
just be "active during" it. That does not work: mido's default Linux backend
subscribes through the ALSA sequencer, and the sequencer's raw-to-event MIDI
parser has to interpret every byte to build snd_seq_event_t values -- 0xF9
and 0xFD are UNDEFINED System Real-Time status bytes with no MIDI 1.0
meaning, and there is no guarantee they survive that translation, or survive
it unchanged, on the way to a mido message. This case reads the character
device node directly instead -- see rawmidi_node() below -- which is also
literally what the catalog's pass criterion says: bytes reaching "the
rawmidi stream", not bytes reaching a sequencer client's parsed view of it.
python-mido is consequently not a dependency of this case at all.

jockey3_midi_in_callback() strips every byte >= 0xF0, not just the System
Real-Time range (0xF8-0xFF) the case's title mentions -- see its comment:
the device sends no MIDI System or Real-Time messages at all, so any byte
in 0xF0-0xFF arriving from the firmware is padding, never a legitimate
message a human could distinguish from padding. That is the actual
threshold this case checks against.

A rawmidi input node is exclusive, so a raw open() here would EBUSY against
a concurrent JT-MIDI-001 run for the same reason it would against PipeWire --
one more reason this could not simply run alongside it.

TWO FIRMWARE REVISIONS, TWO PADDING VALUES
-------------------------------------------
Different units have been observed emitting different padding bytes (0xF9,
0xFB, 0xFD, 0xFF). One unit proves the strip loop works for whichever byte
it emits, not that the loop's threshold is right in general. A site with a
second unit gets more from running this case again on it, cable swapped,
than from doubling any other case's iteration count -- see the catalog
notes -- but that is not required for a useful run.
"""

import os
import select
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from lib.case import Case          # noqa: E402
from lib import alsa               # noqa: E402

# jockey3_midi_in_callback()'s own strip threshold: `buf[i] < 0xF0` survives,
# anything else is dropped. Any byte at or above this reaching the rawmidi
# node is the strip loop having failed, not a legitimate message -- the
# device sends no MIDI System or Real-Time messages of its own.
PADDING_FLOOR = 0xF0

POLL_TIMEOUT_S = 0.5


def main():
    c = Case()
    c.require_card()
    if not c.attended:
        # Mirrors JT-MIDI-001: the runner normally withholds `human` under
        # --unattended and demotes this to the checklist before it starts.
        c.blocked("nobody is at the keyboard; this case needs an operator "
                  "generating traffic")

    node = alsa.rawmidi_node(c.card)
    if not node:
        c.blocked("no rawmidi device node found")

    seconds = float(c.params.get("watch_seconds", 60))

    try:
        fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK)
    except OSError as e:
        c.blocked(f"could not open {node}: {e}")

    c.instruct(f"Generate a variety of MIDI traffic for {seconds:.0f}s: "
               f"press several buttons, move a fader or knob, rotate a jog "
               f"wheel. Which controls, or how many events, does not "
               f"matter -- keep going for the full window.")

    total_bytes = 0
    bad_bytes = 0
    bad_values = Counter()
    deadline = time.monotonic() + seconds

    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            ready, _, _ = select.select([fd], [], [], min(remaining, POLL_TIMEOUT_S))
            if ready:
                try:
                    chunk = os.read(fd, 4096)
                except (BlockingIOError, InterruptedError):
                    chunk = b""
                except OSError as e:
                    c.fail(f"read from {node} failed: {e}")
                    break
                total_bytes += len(chunk)
                for b in chunk:
                    if b >= PADDING_FLOOR:
                        bad_bytes += 1
                        bad_values[b] += 1
            c.status(f"monitoring  {max(0, int(deadline - time.monotonic()))}s "
                     f"left  ....  {total_bytes} byte(s) seen, "
                     f"{bad_bytes} unexpected")
    finally:
        os.close(fd)

    c.metric("bytes_seen", total_bytes)
    c.metric("padding_bytes_seen", bad_bytes)

    if total_bytes == 0:
        c.fail("no MIDI traffic observed during the window at all -- the "
               "operator may not have interacted with the controller, or "
               "the port is not delivering anything")
    elif bad_bytes:
        values = ", ".join(f"0x{v:02X}" for v in sorted(bad_values))
        c.fail(f"{bad_bytes} byte(s) >= 0x{PADDING_FLOOR:02X} reached the "
               f"rawmidi stream out of {total_bytes} total -- firmware "
               f"padding is not fully stripped (value(s) seen: {values})")
    else:
        c.progress(f"{total_bytes} byte(s) observed over {seconds:.0f}s, "
                   f"none >= 0x{PADDING_FLOOR:02X}")

    c.done()


if __name__ == "__main__":
    main()
