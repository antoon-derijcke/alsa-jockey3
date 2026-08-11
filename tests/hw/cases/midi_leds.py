#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""L3 semi-automated: LEDs respond to MIDI OUT.

THE MACHINE IS THE ACTUATOR; THE HUMAN IS THE SENSOR.

The exact inverse of JT-MIDI-001, and the reason both exist as examples. Here
the computer can do the doing but not the seeing: light leaving the front panel
is outside it, and nobody has wired a photodiode to the Load LEDs. So the
question at the end is unavoidable.

WHAT THIS ADDS OVER TYPING THE amidi LINE
-----------------------------------------
If it only sent the notes and asked "did they blink?", it would be the manual
case with the command typed for you, and not worth the promotion. What it adds
is that **a write that succeeds is not proof the device consumed it**. This
case checks the write path separately, so the two failures are told apart:

  write failed        -> the case fails on its own, no question asked, and the
                         operator is not invited to guess about a MIDI OUT
                         path that never delivered a byte
  write ok, no light  -> MIDI OUT reached the device and the LEDs did not
                         respond: firmware, wiring, or the note numbers

Attract mode is a second signal and costs nothing. The device runs an LED
animation until the first MIDI OUT message it has ever had, so an operator
seeing it stop has independent evidence that a byte arrived -- exactly the
thing a successful write cannot establish. It is stated as part of the
expected behavior rather than asked about separately: it is not an independent
verdict, and a second prompt made the operator adjudicate a detail instead of
simply reporting what they saw. It also only means anything on the first run
after a power cycle, which is a poor thing to put a question mark against.

ONE QUESTION, AND A WARNING BEFORE ANYTHING HAPPENS
---------------------------------------------------
The machine chooses the moment here, so the operator cannot pace it. Three
blinks are over in about a second and the controller is not necessarily next
to the monitor, so the case counts down first and gives them time to turn and
look. Without that the only way to see the blinks is to have been looking
already, and the honest answer to the question becomes "I missed it".

Derived from actions/blink_leds.sh, which remains the manual fallback.
"""

import os
import sys
import time

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from lib.case import Case          # noqa: E402

# Load button on deck A and deck B. Taken from blink_leds.sh, which took them
# from test-led.sh: note 0x1b on channels 1 and 2.
ON = "90 1b 7F 91 1b 7F"
OFF = "90 1b 00 91 1b 00"


def find_port(c):
    """The rawmidi port, resolved by card name rather than assumed.

    hw:1,0 depends on what else is plugged in, and hardcoding it is how a test
    ends up talking to the wrong device and passing.
    """
    rc, out, _err = c.run(["amidi", "-l"], timeout=20)
    if rc != 0:
        return None
    for line in out.splitlines():
        if "Jockey" in line:
            parts = line.split()
            if len(parts) >= 2:
                return parts[1]
    return None


def countdown(c, seconds):
    """Time to read the instruction, turn to the device, and be looking.

    This case is the one where the MACHINE decides when the thing happens, so
    the operator cannot pace it. The controller is not always next to the
    monitor -- it may be behind you -- and three LED blinks are over in about
    a second. Firing them the instant the instruction is printed means the
    only way to see them is to have been looking already.

    Drawn in place with Case.status(), so on a terminal it is one line
    ticking down rather than three stacked lines. Redirected to a file it
    becomes three lines, which is the right answer there.
    """
    for n in range(seconds, 0, -1):
        c.status(f"   blinking in {n}s ...")
        time.sleep(1)
    # Nothing to clear away here: the next ordinary line wipes whatever the
    # countdown left on the terminal. Emitting a blank status to "tidy up"
    # only adds an empty line to every redirected log.


def blink(c, port, repeats, interval):
    """Send the pattern. Returns the number of writes that failed."""
    failures = 0
    for i in range(1, repeats + 1):
        bad = 0
        for state, data in (("on", ON), ("off", OFF)):
            rc, _out, err = c.run(["amidi", "-p", port, "-S", data],
                                  timeout=20)
            if rc != 0:
                bad += 1
                c.fail(f"MIDI OUT write failed ({state}, blink {i}): "
                       f"{(err or '').strip()[:100]}")
            time.sleep(interval)
        failures += bad
        # Never claim to have sent what the write path rejected. An operator
        # reading "blink 1/3 sent" above a failure is being told two
        # contradictory things about the same event.
        c.progress(f"   blink {i}/{repeats} "
                   + ("sent" if not bad else f"-- {bad} write(s) FAILED"))
    return failures


def main():
    c = Case()
    c.require_card()
    c.require_tools("amidi")
    if not c.attended:
        c.blocked("nobody is at the keyboard; this case needs an operator")

    repeats = int(c.params.get("repeats", 3))
    interval = float(c.params.get("interval_seconds", 0.2))
    ask_timeout = int(c.params.get("answer_timeout", 120))
    lead_in = int(c.params.get("countdown_seconds", 3))

    port = find_port(c)
    if not port:
        c.blocked("no Jockey 3 rawmidi port found")
    c.progress(f"sending on {port}")

    # The expected behavior is stated up front, in full, so there is exactly
    # one question at the end. Attract mode used to be asked about separately
    # and should not be: it is not an independent verdict, it is part of what
    # "MIDI OUT works" looks like, and a second prompt made the operator
    # adjudicate a detail rather than simply report what they saw.
    c.instruct(f"Watch the LOAD LEDs on both decks. Expect them to blink "
               f"{repeats} times. If the LED attract animation was running, "
               f"it should stop.")

    while True:
        # Inside the retry loop on purpose: an operator who asked for another
        # go had to turn back to the keyboard to type 'r', so they need the
        # same warning again.
        countdown(c, lead_in)
        failures = blink(c, port, repeats, interval)
        c.metric("write_failures", failures)

        if failures:
            # No question. The write path did not deliver, so whether the LEDs
            # lit tells us nothing we do not already know, and asking would
            # invite a verdict on the wrong thing.
            c.progress("   MIDI OUT writes failed -- not asking about the "
                       "LEDs, the bytes never left")
            break

        answer = c.ask("Did the Load LEDs blink on BOTH decks?",
                       ("y", "n", "r"), ask_timeout)
        if answer == "r":
            continue
        if answer is None:
            c.fail("no answer about the LEDs")
            break
        c.metric("leds_seen", answer == "y")
        if answer == "n":
            c.fail("MIDI OUT writes all succeeded but the Load LEDs did not "
                   "blink -- the bytes left the host, so suspect the device "
                   "or the note numbers rather than the driver's write path")
        break

    c.done()


if __name__ == "__main__":
    main()
