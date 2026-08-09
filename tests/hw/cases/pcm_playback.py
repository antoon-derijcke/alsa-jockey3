#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""L3: play a tone at each supported rate and check for xruns.

Reads the xrun count from /proc/asound rather than parsing aplay's output.
aplay reports xruns only in verbose mode, in a format that varies, and a test
that misparses it passes silently -- which is the worst way for a test to be
wrong.
"""

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from lib.case import Case          # noqa: E402
from lib import alsa               # noqa: E402

CHANNELS = 4                       # fixed by the driver: min == max
FORMAT = "S24_3LE"                 # the only format the device accepts


def play(device, rate, seconds, workdir):
    """sox generates, aplay consumes. Returns (rc, stderr, elapsed_to_first_write).

    Piping raw samples avoids writing a temporary wav per rate, and keeps the
    generated signal identical to the one the ad-hoc scripts used (E3 sine,
    -6 dB) so results stay comparable with what came before.
    """
    gen = subprocess.Popen(
        ["sox", "-n", "-r", str(rate), "-c", str(CHANNELS), "-b", "24",
         "-e", "signed-integer", "-t", "raw", "-",
         "synth", str(seconds), "sine", "E3", "gain", "-6"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    t0 = time.time()
    p = subprocess.Popen(
        ["aplay", "-D", device, "-r", str(rate), "-c", str(CHANNELS),
         "--format", FORMAT, "-t", "raw"],
        stdin=gen.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True)
    gen.stdout.close()
    try:
        _out, err = p.communicate(timeout=seconds + 30)
    except subprocess.TimeoutExpired:
        p.kill()
        gen.kill()
        return 124, "aplay did not finish", None
    gen.wait(timeout=5)
    return p.returncode, err, round(time.time() - t0, 3)


def main():
    c = Case()
    c.require_card()
    c.require_tools("aplay", "sox")

    rates = c.params.get("rates", [44100, 48000, 88200, 96000])
    seconds = int(c.params.get("seconds", 3))
    device = c.device or alsa.device_name(c.card)

    total_xruns = 0
    unobserved = []
    for rate in rates:
        # Sampled while the stream runs, not before and after it. The status
        # file reports "closed" whenever the substream is not open, so the
        # old before/after difference was always zero -- the metric could not
        # report a problem even in principle.
        watch = alsa.watch_pcm(c.card, "pcm0p")
        watch.start()
        rc, err, elapsed = play(device, rate, seconds, c.workdir)
        watch.stop()

        total_xruns += watch.xruns
        if not watch.saw_open:
            # Never caught the stream open. The verdict below would otherwise
            # be "no xruns", which is a statement about nothing.
            unobserved.append(str(rate))

        if rc != 0:
            c.fail(f"{rate} Hz: aplay exited {rc}: "
                   f"{(err or '').strip().splitlines()[-1][:120] if err else ''}")
        elif watch.xruns:
            c.fail(f"{rate} Hz: {watch.xruns} xrun(s)")
        if elapsed is not None:
            c.metric(f"elapsed_s_{rate}", elapsed)
        # How close the buffer came to running dry. A run with no xruns whose
        # avail_max keeps climbing is the one about to start crackling, and
        # that trend is invisible to a pass/fail verdict.
        c.metric(f"avail_max_{rate}", watch.avail_max)

    c.metric("xruns", total_xruns)
    c.metric("rates_tested", len(rates))
    if unobserved:
        c.note("stream never observed open at: " + ", ".join(unobserved)
               + " -- xrun figures for those rates mean nothing")
    c.done()


if __name__ == "__main__":
    main()
