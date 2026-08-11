#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""L3 semi-automated: control surface events reach userspace.

THE HUMAN IS THE ACTUATOR; THE MACHINE IS THE JUDGE.

Nobody is asked whether the test passed. A finger on a fader is the one thing
no amount of code supplies, so that is the only thing asked for -- and the
moment the event arrives, mido has seen it and the verdict is settled without
an opinion being involved. Asking "did you see events?" would throw away the
one advantage this has over the manual form, and would record a human's
recollection where a measurement was available.

That division is worth stating because the sibling case, JT-MIDI-002, is the
other way round: it drives the LEDs itself and can only ask a person whether
they lit, because photons leaving the front panel are outside the computer.

WHAT IT DOES NOT TRY TO DO
--------------------------
Verify every control, or even tell one from another. That tests Reloop's
firmware, not this driver -- the code path does not know which control moved,
and neither can this case without a hardcoded map of CC numbers to physical
controls, which would be a second thing to maintain and to be wrong about.

Two shapes of traffic are what matter and what is checked: discrete events
from a button, and a sustained stream from any swept control.

Derived from scripts-alsa-dev/miditest/miditest.py, which does this
interactively with a hexdump and a human reading it.
"""

import os
import sys
import time

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from lib.case import Case          # noqa: E402


def find_input_port(mido):
    for name in mido.get_input_names():
        if "Jockey" in name:
            return name
    return None


def collect(inport, matches, seconds, want):
    """Watch for matching messages, stopping as soon as there are enough.

    Ending early matters for how this feels to use. Waiting out the full
    window after the operator has already done what was asked reads as the
    test having missed it, and invites them to do it again harder.
    """
    seen = []
    deadline = time.time() + seconds
    while time.time() < deadline:
        for msg in inport.iter_pending():
            if matches(msg):
                seen.append(msg)
        if len(seen) >= want:
            # Let the rest of the burst land, so the reported count is not an
            # artifact of which poll happened to cross the threshold.
            time.sleep(0.15)
            seen.extend(m for m in inport.iter_pending() if matches(m))
            return seen
        time.sleep(0.005)
    return seen


def drain(inport):
    """Discard anything already queued.

    Without this, the control a previous step left moving satisfies the next
    one before the operator has touched anything.
    """
    for _ in inport.iter_pending():
        pass


def step(c, inport, label, instruction, matches, want, seconds, timeout_ask):
    """Run one sub-test: ask for an action, watch, judge.

    Returns the number of matching messages, or None if it was skipped.
    """
    while True:
        drain(inport)
        # The ask is concrete and the bar is stated. "Touch three things in
        # turn" left the operator guessing how much was enough and whether
        # anything had registered; "Press 5 buttons -- need 5 events, 10s"
        # does not.
        c.instruct(f"{instruction}   (need {want} events, {seconds}s)")
        seen = collect(inport, matches, seconds, want)
        if len(seen) >= want:
            c.progress(f"   {label}: {len(seen)} events received "
                       f"(needed {want}) -- OK")
            return len(seen)

        c.progress(f"   {label}: {len(seen)} events received, needed {want}")
        answer = c.ask(f"{label}: nothing usable arrived. Retry, skip, or "
                       f"record a failure?", ("r", "s", "f"), timeout_ask)
        if answer == "r":
            continue
        if answer == "s":
            c.note(f"{label} skipped by the operator")
            return None
        # A timeout counts as a failure rather than a skip: nobody is there to
        # say it was fine, and silently passing an unanswered case is how a
        # suite starts lying.
        c.fail(f"{label}: {len(seen)} matching event(s), expected at least "
               f"{want}")
        return len(seen)


def main():
    c = Case()
    c.require_card()
    if not c.attended:
        # The runner normally withholds `human` under --unattended and demotes
        # this to the checklist before it ever starts. Reaching here means
        # that did not happen, and prompting would hang the run.
        c.blocked("nobody is at the keyboard; this case needs an operator")

    try:
        import mido
    except ImportError:
        c.blocked("python-mido is not installed")

    name = find_input_port(mido)
    if not name:
        c.blocked("no Jockey 3 MIDI input port found")

    seconds = int(c.params.get("watch_seconds", 10))
    ask_timeout = int(c.params.get("answer_timeout", 120))

    c.progress(f"listening on {name}")
    with mido.open_input(name) as inport:
        c.instruct("Two steps, one at a time. Each window closes as soon as "
                   "enough events arrive, so there is no need to keep going.")

        n = step(c, inport, "buttons",
                 "Press and release 5 BUTTONS.",
                 lambda m: m.type in ("note_on", "note_off"),
                 int(c.params.get("button_events", 5)), seconds, ask_timeout)
        if n is not None:
            c.metric("button_events", n)

        # ONE continuous step, not a fader step and a jog step.
        #
        # They were separate, and the separation was a lie. A jog wheel and a
        # fader both arrive as control_change, so the jog step was satisfied
        # by an operator who moved only the fader -- and reported a jog wheel
        # verified that nobody had touched. Telling them apart needs a map of
        # which CC number belongs to which physical control, which is exactly
        # the knowledge this case is documented as not wanting: the driver's
        # code path does not know which control moved, so a test that claims
        # to is testing Reloop's firmware and its own hardcoded table.
        #
        # What is worth proving is that CONTINUOUS traffic arrives and keeps
        # arriving, which any swept control demonstrates.
        n = step(c, inport, "continuous",
                 "Move a FADER, KNOB or JOG WHEEL -- keep it moving.",
                 lambda m: not m.is_realtime,
                 int(c.params.get("continuous_events", 20)),
                 seconds, ask_timeout)
        if n is not None:
            c.metric("continuous_events", n)

    c.done()


if __name__ == "__main__":
    main()
