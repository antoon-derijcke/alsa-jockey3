#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""L3: JT-PCM-007, achievable latency sweep.

JT-PCM-003 (pcm_limits.py) already answers "is this period size legal" --
its own docstring is explicit that an xrun at the legal minimum is recorded,
not failed, because the fixed 0.4 ms floor is far below what any userspace
process can keep fed and that is a scheduling fact, not a driver defect. This
case answers the question pcm_limits.py deliberately leaves open: of the
legal period sizes, which is the *smallest one that actually runs clean*,
i.e. the real achievable latency rather than the advertised legal floor.

Method: starting at the driver's legal minimum period (jockey3_pcm_hw_playback
/ jockey3_pcm_hw_capture in jockey3.c, mirrored in PERIOD_BYTES_MIN below,
same as pcm_limits.py), double the period size and run a real transfer at
each step -- period count fixed at 2, the smallest legal buffer, since this
case wants the smallest achievable *buffer*, not just the smallest period in
isolation -- until one size survives `repeats_per_size` consecutive
transfers with zero xruns. That size is "clean"; everything smaller is a
legal config that does not hold up under real playback/capture. The sweep
stops (and records nothing further) at the first clean size, on the
assumption -- true of every USB-audio device seen so far -- that a larger
period is never less stable than a smaller one.

Playback is driven by sox piped into aplay, a real tone rather than
/dev/zero (see pcm.py's play()), because /dev/zero can be read faster than
realtime and would understate how hard a genuinely time-paced source stresses
a small period. Capture has no analogous concern -- arecord itself paces the
read -- so it goes straight to /dev/null, as pcm_limits.py's transfer does.

hw: is used throughout, never plughw:, for the same reason JT-PCM-003 and
JT-PCM-006 give: plughw negotiates around exactly what this case measures.

If NOTHING is clean by CEILING_BYTES -- tens of milliseconds, already well
past anything "achievable" would mean in practice -- that is not a latency
number to report, it is a driver fault, and the case fails rather than
quietly publishing the ceiling as the answer (see CLAUDE.md's fault-handling
principle: never hide a fault behind a metric).
"""

import ctypes
import ctypes.util
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from lib.case import Case          # noqa: E402
from lib import alsa               # noqa: E402

# Fixed for the same reason pcm_limits.py fixes it: a rate change tears down
# and reprograms the device (CLAUDE.md's "Rate changes are destructive"),
# which this sweep -- dozens of opens per run -- has no business folding in.
RATE = 44100
FORMAT = "S24_3LE"

PLAYBACK_CHANNELS = 4
CAPTURE_CHANNELS = 6
BYTES_PER_SAMPLE = 3
FRAME_BYTES = {"playback": PLAYBACK_CHANNELS * BYTES_PER_SAMPLE,     # 12
               "capture": CAPTURE_CHANNELS * BYTES_PER_SAMPLE}       # 18

# jockey3.c: 10 playback frames / 8 capture frames per URB -- the smallest
# period the driver can usefully schedule. Mirrors pcm_limits.py; keep the
# two in sync by hand, same caveat as there (no exported hook to read it from
# the running driver).
PERIOD_BYTES_MIN = {"playback": 10 * FRAME_BYTES["playback"],   # 120
                     "capture": 8 * FRAME_BYTES["capture"]}      # 144

PERIODS = 2     # smallest legal period count -- see pcm_limits.py PERIODS_MIN

CEILING_BYTES = 32 * 1024      # see module docstring: past this, it's a fault

# The point of this case is a metric, not a pass/fail, so "clean" has to be
# a claim that holds up statistically, not one lucky window. At the legal
# minimum (0.2 ms) a 2 s transfer is thousands of period fills -- plenty of
# repetitions in itself -- but that says nothing about run-to-run jitter from
# USB scheduling, and a short run is exactly what let JT-PCM-003's transfer
# open and close between two 20 ms watch_pcm polls and read xruns=0 for
# something that actually broke (see its module docstring). 10 s per attempt,
# repeated 3 times, means a candidate only counts as clean after roughly
# 30 s of aggregate run time and tens of thousands of period fills, and any
# one bad repeat disqualifies it -- both params are overridable per profile
# via duration_s / repeats_per_size for a machine that needs it tighter.
DURATION_S = 10          # per transfer attempt -- see the reasoning above
REPEATS_PER_SIZE = 3     # consecutive clean transfers required before a size counts

STREAMS = {
    "playback": dict(pcm="pcm0p", channels=PLAYBACK_CHANNELS),
    "capture": dict(pcm="pcm0c", channels=CAPTURE_CHANNELS),
}


# ------------------------------------------------------------ libasound ctypes
#
# Identical in shape to pcm_limits.py's probe_hw_params(): an exact
# (non-"near") negotiation of period and buffer size, so a size this sweep
# calls "clean" was actually the size the transfer ran at, not something
# alsa-lib silently rounded to. Duplicated rather than imported -- cases in
# this suite are each meant to stand alone, the same choice pcm.py and
# rate_change.py make for their own near-identical tone generators.

def _lib():
    if _lib.cache is None:
        path = ctypes.util.find_library("asound") or "libasound.so.2"
        lib = ctypes.CDLL(path)
        lib.snd_pcm_open.argtypes = [ctypes.POINTER(ctypes.c_void_p),
                                     ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
        lib.snd_pcm_hw_params_malloc.argtypes = [
            ctypes.POINTER(ctypes.c_void_p)]
        lib.snd_pcm_hw_params_set_period_size.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int]
        lib.snd_pcm_hw_params_set_buffer_size.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        lib.snd_pcm_format_value.argtypes = [ctypes.c_char_p]
        lib.snd_strerror.restype = ctypes.c_char_p
        _lib.cache = lib
    return _lib.cache


_lib.cache = None

SND_PCM_STREAM_PLAYBACK = 0
SND_PCM_STREAM_CAPTURE = 1
SND_PCM_ACCESS_RW_INTERLEAVED = 3


def _errstr(lib, rc):
    return lib.snd_strerror(rc).decode(errors="replace")


def probe_hw_params(device, stream, channels, period_frames, buffer_frames):
    """Ask libasound to negotiate these EXACT period/buffer sizes.

    Returns (ok, err). Opens and closes the device purely to negotiate --
    see pcm_limits.py's probe_hw_params() for the full rationale, which
    applies unchanged here.
    """
    lib = _lib()
    pcm = ctypes.c_void_p()
    stream_dir = (SND_PCM_STREAM_PLAYBACK if stream == "playback"
                  else SND_PCM_STREAM_CAPTURE)
    rc = lib.snd_pcm_open(ctypes.byref(pcm), device.encode(), stream_dir, 0)
    if rc < 0:
        return False, f"snd_pcm_open: {_errstr(lib, rc)}"

    params = ctypes.c_void_p()
    rc = lib.snd_pcm_hw_params_malloc(ctypes.byref(params))
    if rc < 0:
        lib.snd_pcm_close(pcm)
        return False, f"hw_params_malloc: {_errstr(lib, rc)}"
    try:
        rc = lib.snd_pcm_hw_params_any(pcm, params)
        if rc < 0:
            return False, f"hw_params_any: {_errstr(lib, rc)}"

        fmt = lib.snd_pcm_format_value(FORMAT.encode())
        setters = (
            ("access", lambda: lib.snd_pcm_hw_params_set_access(
                pcm, params, SND_PCM_ACCESS_RW_INTERLEAVED)),
            ("format", lambda: lib.snd_pcm_hw_params_set_format(
                pcm, params, fmt)),
            ("channels", lambda: lib.snd_pcm_hw_params_set_channels(
                pcm, params, channels)),
            ("rate", lambda: lib.snd_pcm_hw_params_set_rate(
                pcm, params, RATE, 0)),
        )
        for label, setter in setters:
            rc = setter()
            if rc < 0:
                return False, f"set_{label}: {_errstr(lib, rc)}"

        rc = lib.snd_pcm_hw_params_set_period_size(
            pcm, params, ctypes.c_ulong(period_frames), 0)
        if rc < 0:
            return False, f"set_period_size: {_errstr(lib, rc)}"

        rc = lib.snd_pcm_hw_params_set_buffer_size(
            pcm, params, ctypes.c_ulong(buffer_frames))
        if rc < 0:
            return False, f"set_buffer_size: {_errstr(lib, rc)}"

        rc = lib.snd_pcm_hw_params(pcm, params)
        if rc < 0:
            return False, f"hw_params commit: {_errstr(lib, rc)}"
        return True, None
    finally:
        lib.snd_pcm_hw_params_free(params)
        lib.snd_pcm_close(pcm)


# -------------------------------------------------------------- real transfer

def transfer_playback(c, device, period_frames, buffer_frames, seconds):
    """sox generates a real tone, aplay consumes it at the exact size under
    test. Returns (rc, xruns, avail_max, hw_params, err).

    hw_params is what watch_pcm actually observed negotiated while the
    stream was open -- --period-size/--buffer-size on aplay go through
    snd_pcm_hw_params_set_*_near(), the same rounding trap JT-PCM-006's
    notes describe, so the request is not proof of what ran. The caller
    checks this against what was asked for."""
    gen = subprocess.Popen(
        ["sox", "-n", "-r", str(RATE), "-c", str(PLAYBACK_CHANNELS), "-b", "24",
         "-e", "signed-integer", "-t", "raw", "-",
         "synth", str(seconds), "sine", "E3", "gain", "-6"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    watch = alsa.watch_pcm(c.card, "pcm0p")
    watch.start()
    p = subprocess.Popen(
        ["aplay", "-q", "-D", device, "-r", str(RATE), "-c", str(PLAYBACK_CHANNELS),
         "--format", FORMAT, "-t", "raw",
         "--period-size", str(period_frames), "--buffer-size", str(buffer_frames)],
        stdin=gen.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True)
    gen.stdout.close()
    try:
        _out, err = p.communicate(timeout=seconds + 15)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        p.kill()
        gen.kill()
        rc, err = 124, "timed out"
    gen.wait(timeout=5)
    watch.stop()
    return rc, watch.xruns, watch.avail_max, watch.hw_params, err


def transfer_capture(c, device, period_frames, buffer_frames, seconds):
    """arecord to /dev/null at the exact size under test.

    Returns (rc, xruns, avail_max, hw_params, err) -- see transfer_playback()
    for why hw_params (not the requested size) is what gets compared."""
    samples = int(seconds * RATE)
    cmd = ["arecord", "-q", "-D", device, "-f", FORMAT,
           "-c", str(CAPTURE_CHANNELS), "-r", str(RATE),
           "--period-size", str(period_frames), "--buffer-size", str(buffer_frames),
           "--samples", str(samples), "/dev/null"]
    watch = alsa.watch_pcm(c.card, "pcm0c")
    watch.start()
    rc, _out, err = c.run(cmd, timeout=seconds + 15)
    watch.stop()
    return rc, watch.xruns, watch.avail_max, watch.hw_params, err


TRANSFER = {"playback": transfer_playback, "capture": transfer_capture}


# ------------------------------------------------------------------- sweeping

def candidate_periods(stream):
    """Legal minimum, then doubled, up to CEILING_BYTES."""
    frame_bytes = FRAME_BYTES[stream]
    frames = -(-PERIOD_BYTES_MIN[stream] // frame_bytes)      # ceil to a whole frame
    out = []
    while True:
        out.append(frames)
        if frames * frame_bytes >= CEILING_BYTES:
            return out
        frames *= 2


def run_one(c, device, stream, period_frames, seconds, repeats, i, total):
    """Probe once, then transfer `repeats` times. Clean only if every
    repeat ran with zero xruns, exited zero, AND actually negotiated the
    exact size asked for -- one lucky pass among several is not the same
    claim as "this size runs clean", and a size aplay/arecord silently
    rounded to (see transfer_playback()'s docstring on _near) is not a data
    point about the size under test at all."""
    info = STREAMS[stream]
    buffer_frames = period_frames * PERIODS
    period_bytes = period_frames * FRAME_BYTES[stream]

    c.status(f"  [{stream} {i}/{total}] period={period_bytes}B "
             f"({period_frames}fr) x{PERIODS}...")

    ok, probe_err = probe_hw_params(device, stream, info["channels"],
                                     period_frames, buffer_frames)
    record = {"stream": stream, "period_frames": period_frames,
              "period_bytes": period_bytes, "buffer_frames": buffer_frames}
    if not ok:
        # A period inside pcm_limits.py's advertised legal range that
        # hw_params itself refuses is a driver fault, not a latency data
        # point -- the two cases must agree on what is legal.
        c.fail(f"{stream} period={period_bytes}B: legal-range config "
               f"refused by hw_params: {probe_err}")
        record["clean"] = False
        record["error"] = probe_err
        return record

    total_xruns = 0
    max_avail_max = 0
    for attempt in range(1, repeats + 1):
        c.status(f"  [{stream} {i}/{total}] period={period_bytes}B "
                 f"({period_frames}fr) x{PERIODS} -- repeat {attempt}/{repeats}...")
        rc, xruns, avail_max, hw_params, err = TRANSFER[stream](
            c, device, period_frames, buffer_frames, seconds)
        total_xruns += xruns
        max_avail_max = max(max_avail_max, avail_max)

        neg_period = hw_params.get("period_size")
        neg_buffer = hw_params.get("buffer_size")
        if neg_period != period_frames or neg_buffer != buffer_frames:
            # aplay/arecord's --period-size/--buffer-size go through the
            # rounding *_near() setters, not the exact ones probe_hw_params()
            # used -- so a transfer that ran at a different size than what
            # was probed is not evidence about the size under test, and
            # trusting it would understate the achievable latency. Void the
            # attempt rather than silently accepting the wrong number.
            c.fail(f"{stream} period={period_bytes}B: transfer negotiated "
                   f"{neg_period}/{neg_buffer} frames, not "
                   f"{period_frames}/{buffer_frames} -- aplay/arecord rounded "
                   "away from the probed size")
            record["clean"] = False
            record["negotiated_period_frames"] = neg_period
            record["negotiated_buffer_frames"] = neg_buffer
            return record

        err_lower = (err or "").lower()
        looks_bad = xruns or rc != 0 or "xrun" in err_lower or "broken pipe" in err_lower
        if looks_bad:
            c.note(f"{stream} period={period_bytes}B: not clean on repeat "
                   f"{attempt}/{repeats} (rc={rc}, xruns={xruns}, "
                   f"avail_max={avail_max})")
            record["clean"] = False
            record["xruns"] = total_xruns
            record["avail_max"] = max_avail_max
            return record

    record["clean"] = True
    record["xruns"] = total_xruns
    record["avail_max"] = max_avail_max
    return record


def sweep_stream(c, device, stream, seconds, repeats):
    candidates = candidate_periods(stream)
    results = []
    for i, period_frames in enumerate(candidates, 1):
        record = run_one(c, device, stream, period_frames, seconds, repeats,
                          i, len(candidates))
        results.append(record)
        if record["clean"]:
            latency_ms = round(period_frames / RATE * 1000, 3)
            c.progress(f"{stream}: clean at period={record['period_bytes']}B "
                       f"({latency_ms} ms)")
            return results, record
    return results, None


def main():
    c = Case()
    c.require_card()
    c.require_tools("aplay", "arecord", "sox")

    device = c.device or alsa.device_name(c.card)
    seconds = c.params.get("duration_s", DURATION_S)
    repeats = c.params.get("repeats_per_size", REPEATS_PER_SIZE)

    clean = {}
    for stream in ("playback", "capture"):
        results, found = sweep_stream(c, device, stream, seconds, repeats)
        c.metric(f"{stream}_candidates", results)
        if found is None:
            c.fail(f"{stream}: nothing ran clean up to the {CEILING_BYTES}B "
                   "ceiling -- not a latency number, a driver fault")
            continue
        clean[stream] = found
        c.metric(f"{stream}_min_clean_period_bytes", found["period_bytes"])
        c.metric(f"{stream}_min_clean_period_frames", found["period_frames"])
        c.metric(f"{stream}_min_clean_latency_ms",
                 round(found["period_frames"] / RATE * 1000, 3))

    if clean:
        # The binding constraint for the device as a whole -- e.g. duplex
        # operation -- is whichever stream needed the larger buffer to run
        # clean, not whichever happens to be listed first.
        binding_stream = max(
            clean, key=lambda s: clean[s]["period_frames"] / RATE)
        c.metric("min_clean_period_bytes", clean[binding_stream]["period_bytes"])
        c.metric("min_clean_latency_ms",
                 round(clean[binding_stream]["period_frames"] / RATE * 1000, 3))
        c.metric("binding_stream", binding_stream)

    c.done()


if __name__ == "__main__":
    main()
