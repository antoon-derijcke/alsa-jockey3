#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""L3: JT-PCM-003, period and buffer size boundary matrix.

This is a positive AND negative test at once, and neither half is optional:

    inside the advertised limits  -> hw_params must succeed
    outside the advertised limits -> hw_params must be refused, not silently
                                      rounded to something legal and reported
                                      as a pass

That second half is why this case does NOT use aplay/arecord's exit code as
the accept/refuse signal, the way JT-PCM-006 does for channels and format.
alsa-lib's own CLI tools negotiate period and buffer size with
snd_pcm_hw_params_set_period_size_near() / *_buffer_size_near() -- "near"
meaning an out-of-range request is silently rounded to the closest legal
value rather than refused. Asking aplay for a 7-frame capture period would
not fail; it would open at 8 frames and exit 0, and a case that trusted that
exit code would report "in-limits config accepted" on a request that was
never honoured, missing the very thing JT-PCM-003 exists to catch. Channels
and format have no such rounding -- there is no "near" channel count -- which
is what makes JT-PCM-006's plain exit-code check correct for them and wrong
here.

So the accept/refuse verdict comes from probe_hw_params() below, a thin
ctypes binding straight to libasound's *exact* setters for period and buffer
size (snd_pcm_hw_params_set_period_size() / *_buffer_size(), no _near), which
either negotiate precisely what was asked or fail. That is ground truth for
"the driver's constraint table said yes or no" independent of any CLI
front-end's rounding behaviour. Rate is fixed at RATE (a rate the device
always supports) and set with dir=0, an exact match rather than a rounded
one; it is not swept here on purpose -- see the comment on RATE below.

hw: is used throughout, never plughw: -- see JT-PCM-006's note on the same
point. plughw exists precisely to paper over exactly what this case checks.

For a config the probe accepts, aplay/arecord are then used for a short real
transfer -- proof the negotiated parameters are actually usable, not just
acceptable on paper. An xrun there is recorded as a metric, not a failure: at
the legal minimum a playback period is under half a millisecond, far below
what any userspace process can keep fed, and buffer_limits_validation.md
treats that as something to measure rather than a defect. JT-PCM-007 is the
dedicated case for the smallest period that runs glitch-free; duplicating
that judgement here would fail this case for a limitation of process
scheduling, not of the driver.

The limits below mirror jockey3_pcm_hw_playback/jockey3_pcm_hw_capture in
jockey3.c and must be kept in sync with them by hand; there is no exported
hook for a test to read them from the running driver (see
docs/environments.md and CLAUDE.md's "no test hooks" rule).
"""

import ctypes
import ctypes.util
import os
import sys

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from lib.case import Case          # noqa: E402
from lib import alsa               # noqa: E402

# Fixed, not swept: this case probes hw_params 30-odd times per run, and a
# rate change tears down and reprograms the device (see CLAUDE.md's "Rate
# changes are destructive"), the project's known reliability sore spot.
# Sweeping rates here would fold that into a case that isn't about rate
# changes; JT-RATE-001/002/003 already own that.
RATE = 44100
FORMAT = "S24_3LE"

PLAYBACK_CHANNELS = 4
CAPTURE_CHANNELS = 6
BYTES_PER_SAMPLE = 3
FRAME_BYTES = {"playback": PLAYBACK_CHANNELS * BYTES_PER_SAMPLE,     # 12
               "capture": CAPTURE_CHANNELS * BYTES_PER_SAMPLE}       # 18

# jockey3.c: 10 playback frames / 8 capture frames per URB, times the frame
# size above -- one URB's worth is the smallest period the driver can
# usefully schedule.
PERIOD_BYTES_MIN = {"playback": 10 * FRAME_BYTES["playback"],   # 120
                     "capture": 8 * FRAME_BYTES["capture"]}      # 144
PERIOD_BYTES_MAX = 512 * 1024
PERIODS_MIN = 2
PERIODS_MAX = 1024
BUFFER_BYTES_MAX = 1024 * 1024

# Caps how large a real-transfer attempt's --samples gets. Only reached by
# the largest in-limits configs (period_bytes_max at few periods), so this
# bounds run time without ever capping a config the probe is meant to accept
# below the size that would actually exercise it.
MAX_SAMPLES = 4 * 1024 * 1024

STREAMS = {
    "playback": dict(tool="aplay", pcm="pcm0p", channels=PLAYBACK_CHANNELS,
                      extra_args=["/dev/zero"]),
    "capture": dict(tool="arecord", pcm="pcm0c", channels=CAPTURE_CHANNELS,
                     extra_args=["/dev/null"]),
}


# ------------------------------------------------------------ libasound ctypes

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
        lib.snd_pcm_hw_params_get_period_size.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_int)]
        lib.snd_pcm_hw_params_get_buffer_size.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
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


def probe_hw_params(device, stream, channels, rate, period_frames, buffer_frames):
    """Ask libasound to negotiate these EXACT period/buffer sizes.

    Returns (ok, negotiated_period_frames, negotiated_buffer_frames, err).
    ok is whether snd_pcm_hw_params() -- the final commit of the whole
    parameter set -- accepted them unchanged. No _near rounding is involved
    anywhere in this path; see the module docstring for why that matters.
    Opens and closes the device on its own, holding it for a moment purely
    to negotiate parameters -- no data is transferred here.
    """
    lib = _lib()
    pcm = ctypes.c_void_p()
    stream_dir = (SND_PCM_STREAM_PLAYBACK if stream == "playback"
                  else SND_PCM_STREAM_CAPTURE)
    rc = lib.snd_pcm_open(ctypes.byref(pcm), device.encode(), stream_dir, 0)
    if rc < 0:
        return False, None, None, f"snd_pcm_open: {_errstr(lib, rc)}"

    params = ctypes.c_void_p()
    rc = lib.snd_pcm_hw_params_malloc(ctypes.byref(params))
    if rc < 0:
        lib.snd_pcm_close(pcm)
        return False, None, None, f"hw_params_malloc: {_errstr(lib, rc)}"
    try:
        rc = lib.snd_pcm_hw_params_any(pcm, params)
        if rc < 0:
            return False, None, None, f"hw_params_any: {_errstr(lib, rc)}"

        fmt = lib.snd_pcm_format_value(FORMAT.encode())
        setters = (
            ("access", lambda: lib.snd_pcm_hw_params_set_access(
                pcm, params, SND_PCM_ACCESS_RW_INTERLEAVED)),
            ("format", lambda: lib.snd_pcm_hw_params_set_format(
                pcm, params, fmt)),
            ("channels", lambda: lib.snd_pcm_hw_params_set_channels(
                pcm, params, channels)),
            ("rate", lambda: lib.snd_pcm_hw_params_set_rate(
                pcm, params, rate, 0)),
        )
        for label, setter in setters:
            rc = setter()
            if rc < 0:
                return False, None, None, f"set_{label}: {_errstr(lib, rc)}"

        rc = lib.snd_pcm_hw_params_set_period_size(
            pcm, params, ctypes.c_ulong(period_frames), 0)
        if rc < 0:
            return False, None, None, f"set_period_size: {_errstr(lib, rc)}"

        rc = lib.snd_pcm_hw_params_set_buffer_size(
            pcm, params, ctypes.c_ulong(buffer_frames))
        if rc < 0:
            return False, None, None, f"set_buffer_size: {_errstr(lib, rc)}"

        rc = lib.snd_pcm_hw_params(pcm, params)
        if rc < 0:
            return False, None, None, f"hw_params commit: {_errstr(lib, rc)}"

        neg_period = ctypes.c_ulong()
        neg_dir = ctypes.c_int()
        lib.snd_pcm_hw_params_get_period_size(
            params, ctypes.byref(neg_period), ctypes.byref(neg_dir))
        neg_buffer = ctypes.c_ulong()
        lib.snd_pcm_hw_params_get_buffer_size(params, ctypes.byref(neg_buffer))
        return True, neg_period.value, neg_buffer.value, None
    finally:
        lib.snd_pcm_hw_params_free(params)
        lib.snd_pcm_close(pcm)


# ------------------------------------------------------------------- sizing

def resolve_period_bytes(token, stream):
    """A period_sizes entry -> target bytes for this stream direction.

    'minimum' and 'maximum' are direction-relative (capture's minimum is
    above playback's), so they cannot be pre-resolved in the catalog params.
    A literal like 120 or 144 is deliberately tested against BOTH
    directions -- 144 is a legal playback period but below capture's
    minimum, which is exactly the boundary this case exists to catch.
    """
    if token == "minimum":
        return PERIOD_BYTES_MIN[stream]
    if token == "maximum":
        return PERIOD_BYTES_MAX
    return int(token)


def period_frames_for(token, target_bytes, frame_bytes):
    """Target bytes -> whole ALSA frames, rounded the direction 'minimum'
    and 'maximum' need to stay honest.

    Rounding to the nearest frame can push 'minimum' below the true minimum
    or 'maximum' above the true maximum -- 512 KiB is not a whole number of
    12-byte playback frames, and nearest-rounding it up lands 4 bytes past
    PERIOD_BYTES_MAX, turning the one config meant to prove the maximum is
    reachable into a config that is correctly refused for exceeding it. So
    'minimum' rounds up (never requests less than the advertised floor) and
    'maximum' rounds down (never requests more than the advertised ceiling);
    plain literals round to the nearest frame, since they are boundary
    probes rather than the boundary itself.
    """
    if token == "minimum":
        return max(1, -(-target_bytes // frame_bytes))    # ceil
    if token == "maximum":
        return max(1, target_bytes // frame_bytes)         # floor
    return max(1, round(target_bytes / frame_bytes))


# -------------------------------------------------------------- real transfer

def run_transfer(c, device, stream, period_frames, buffer_frames):
    """A short real transfer at an already-negotiated-legal size.

    Returns (rc, xruns, err). Not the accept/refuse verdict -- probe_hw_params
    already gave that -- this is proof the accepted parameters are actually
    usable, with any xrun reported back to the caller to record rather than
    to judge (see the module docstring on why xruns are not failed here).
    """
    info = STREAMS[stream]
    # watch_pcm polls every 20 ms (see lib/alsa.py); a transfer shorter than
    # that can open and close between two polls, reading xruns=0 regardless
    # of what happened. Half a second keeps the substream open across ~25
    # polls so an underrun there is actually observed, not just inferred
    # from aplay's exit code.
    samples = min(max(buffer_frames * 2, RATE // 2), MAX_SAMPLES)
    cmd = [info["tool"], "-q", "-D", device, "-f", FORMAT,
           "-c", str(info["channels"]), "-r", str(RATE),
           "--period-size", str(period_frames),
           "--buffer-size", str(buffer_frames),
           "--samples", str(samples)] + info["extra_args"]

    watch = alsa.watch_pcm(c.card, info["pcm"])
    watch.start()
    timeout = max(15, samples / RATE + 15)
    rc, _out, err = c.run(cmd, timeout=timeout)
    watch.stop()
    return rc, watch.xruns, err


def build_combo(stream, size_token, count):
    """Precompute everything about one (stream, period size, period count)
    combination, including expect_ok -- needed up front so combos can be
    partitioned into the positive and negative groups before any of them run.
    """
    frame_bytes = FRAME_BYTES[stream]
    target_bytes = resolve_period_bytes(size_token, stream)
    period_frames = period_frames_for(size_token, target_bytes, frame_bytes)
    actual_period_bytes = period_frames * frame_bytes
    buffer_frames = period_frames * count
    actual_buffer_bytes = buffer_frames * frame_bytes
    expect_ok = (PERIOD_BYTES_MIN[stream] <= actual_period_bytes <= PERIOD_BYTES_MAX
                 and PERIODS_MIN <= count <= PERIODS_MAX
                 and actual_buffer_bytes <= BUFFER_BYTES_MAX)
    return dict(stream=stream, size_token=size_token, count=count,
                period_frames=period_frames, buffer_frames=buffer_frames,
                actual_period_bytes=actual_period_bytes,
                actual_buffer_bytes=actual_buffer_bytes, expect_ok=expect_ok)


def run_one(c, device, combo, label, i, total):
    """Probe, and where legal transfer, one combo. Returns its result record.

    label/i/total are purely for the status line -- "positive 3/22" rather
    than a single index running across both groups -- so the two halves of
    the matrix read as two separate counts on the bench, not one interleaved
    one.
    """
    stream, size_token, count = combo["stream"], combo["size_token"], combo["count"]
    period_frames, buffer_frames = combo["period_frames"], combo["buffer_frames"]
    actual_period_bytes = combo["actual_period_bytes"]
    actual_buffer_bytes = combo["actual_buffer_bytes"]
    expect_ok = combo["expect_ok"]
    info = STREAMS[stream]

    c.status(f"  [{label} {i}/{total}] {stream} period={size_token}"
             f"({actual_period_bytes}B/{period_frames}fr) x{count} "
             f"-> expect {'ok' if expect_ok else 'refused'}...")

    ok, neg_period, neg_buffer, probe_err = probe_hw_params(
        device, stream, info["channels"], RATE, period_frames, buffer_frames)

    desc = (f"{stream} period={actual_period_bytes}B "
            f"({period_frames} frames) x{count} periods "
            f"({actual_buffer_bytes}B buffer)")

    record = {"stream": stream, "period_size_param": size_token,
              "period_bytes": actual_period_bytes,
              "period_frames": period_frames, "period_count": count,
              "buffer_bytes": actual_buffer_bytes, "expect_ok": expect_ok,
              "hw_params_accepted": ok}

    if not ok:
        record["probe_err"] = probe_err
        if expect_ok:
            c.fail(f"{desc}: in-limits config was refused: {probe_err}")
        return record

    record["negotiated_period_frames"] = neg_period
    record["negotiated_buffer_frames"] = neg_buffer
    if not expect_ok:
        c.fail(f"{desc}: out-of-limits config was accepted "
               f"(negotiated {neg_period} frames / {neg_buffer} frames)")
        return record
    if neg_period != period_frames or neg_buffer != buffer_frames:
        # An exact setter that reports success but hands back different
        # frame counts than requested would itself be a libasound bug, not
        # a driver one -- worth surfacing either way since it invalidates
        # the transfer that follows.
        c.fail(f"{desc}: accepted but negotiated "
               f"{neg_period}/{neg_buffer} frames, not "
               f"{period_frames}/{buffer_frames}")
        return record

    rc, xruns, err = run_transfer(c, device, stream, period_frames, buffer_frames)
    record["transfer_xruns"] = xruns
    err_lower = (err or "").lower()
    looks_like_underrun = (
        xruns or "xrun" in err_lower or "broken pipe" in err_lower)
    if looks_like_underrun:
        c.note(f"{desc}: underrun during transfer "
               f"(xruns={xruns}) -- legal config, not failed; "
               "see JT-PCM-007 for the clean-running latency floor")
    elif rc != 0:
        c.fail(f"{desc}: transfer failed with no underrun "
               f"indication (rc={rc}): "
               f"{(err or '').strip().splitlines()[-1][:120] if err else ''}")
    return record


def main():
    c = Case()
    c.require_card()
    c.require_tools("aplay", "arecord")

    device = c.device or alsa.device_name(c.card)
    period_sizes = c.params.get("period_sizes",
                                 ["minimum", 120, 144, 1024, "maximum"])
    period_counts = c.params.get("period_counts", [2, 4, 1024])

    all_combos = [build_combo(stream, size_token, count)
                  for stream in ("playback", "capture")
                  for size_token in period_sizes
                  for count in period_counts]
    # Positive (in-limits, expected to succeed) and negative (out-of-limits,
    # expected to be refused) run as two separate blocks -- see run_one()'s
    # status line -- rather than interleaved in matrix order, so the two
    # halves of the pass criterion are legible as they run, not just in the
    # metrics afterwards.
    positive = [combo for combo in all_combos if combo["expect_ok"]]
    negative = [combo for combo in all_combos if not combo["expect_ok"]]

    total_xruns = 0
    accepted = rejected = 0
    results = []
    for label, group in (("positive", positive), ("negative", negative)):
        for i, combo in enumerate(group, 1):
            record = run_one(c, device, combo, label, i, len(group))
            total_xruns += record.get("transfer_xruns") or 0
            if record["hw_params_accepted"]:
                accepted += 1
            else:
                rejected += 1
            results.append(record)

    c.metric("xruns", total_xruns)
    c.metric("configs_accepted", accepted)
    c.metric("configs_rejected", rejected)
    c.metric("configs_tested", len(all_combos))
    c.metric("results", results)

    c.done()


if __name__ == "__main__":
    main()
