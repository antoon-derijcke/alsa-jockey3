#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""L3: open and close the PCM substreams, back to back, many times.

Derived from scripts-alsa-dev/test_open_close.sh, which looped aplay against
the device to shake out anything that only breaks on repetition. Every other
PCM case (JT-PCM-002/004/005/...) also opens and closes a substream, but each
of those opens it once per run and spends the rest of the run on whatever it
is actually measuring -- a rate, a signal, a duration. None of them repeat the
open/close cycle enough times to be a stress test of the cycle itself. This
case does nothing else: it is the only one that opens and closes a substream
a few hundred times in a row, which is what it takes to catch a leak or a
state-release bug that only shows up on the Nth open rather than the first.

Playback and capture are cycled independently, each with the shortest
transfer aplay/arecord will do (--samples, not --duration, so the transfer
itself does not depend on the rate chosen). What is timed is not a clean
"just the open call" number -- it is the whole subprocess round trip, open
through close, in the same spirit as JT-PROBE-001's load_ms and
JT-PROBE-002's bind_ms/unbind_ms, both of which time a multi-step operation
rather than isolate one syscall. In practice this measures process spawn and
the device's own open/close handshake far more than the --samples transfer,
which is why a cycle lands around 100-130 ms rather than the few ms the
transfer alone would take -- that overhead is consistent run to run, so a
step change in it across builds is still a meaningful signal. After every
cycle, the substream's own status file is checked for "closed" --
confirmation that the close actually released it, not just that the tool
exited zero.
"""

import os
import sys
import time

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from lib.case import Case          # noqa: E402
from lib import alsa               # noqa: E402

RATE = 44100
SAMPLES = 128                       # frames -- negligible next to open/close overhead
PLAYBACK_CHANNELS = 4
CAPTURE_CHANNELS = 6
FORMAT = "S24_3LE"


def cycle(c, tool, device, channels, pcm, extra_args):
    """Run one open/close cycle of a substream. Returns elapsed ms, or None."""
    cmd = [tool, "-q", "-D", device, "-f", FORMAT, "-c", str(channels),
           "-r", str(RATE), "--samples", str(SAMPLES)] + extra_args
    t0 = time.time()
    rc, _out, err = c.run(cmd, timeout=10)
    elapsed_ms = (time.time() - t0) * 1000
    if rc != 0:
        c.fail(f"{tool} open/close failed: {err.strip()[:120]}")
        return None
    status = alsa.pcm_status(c.card, pcm)
    if status:
        c.fail(f"{pcm} still reports state={status.get('state')} "
               f"after {tool} exited")
        return None
    return round(elapsed_ms, 1)


def stats(values):
    return {"n": len(values), "min": min(values), "max": max(values),
            "mean": round(sum(values) / len(values), 1)}


def main():
    c = Case()
    c.require_card()
    c.require_tools("aplay", "arecord")

    device = c.device or alsa.device_name(c.card)
    iterations = int(c.params.get("iterations_per_run", 100))

    playback_ms, capture_ms = [], []

    for i in range(1, iterations + 1):
        ms = cycle(c, "aplay", device, PLAYBACK_CHANNELS, "pcm0p",
                   ["/dev/zero"])
        if ms is None:
            break
        playback_ms.append(ms)

        ms = cycle(c, "arecord", device, CAPTURE_CHANNELS, "pcm0c",
                   ["/dev/null"])
        if ms is None:
            break
        capture_ms.append(ms)

        c.progress(f"cycle {i}/{iterations}  "
                   f"playback {playback_ms[-1]:>6.1f} ms  "
                   f"capture {capture_ms[-1]:>6.1f} ms")

    open_ms = {}
    if playback_ms:
        open_ms["playback"] = stats(playback_ms)
    if capture_ms:
        open_ms["capture"] = stats(capture_ms)
    if open_ms:
        c.metric("open_ms", open_ms)

    c.done()


if __name__ == "__main__":
    main()
