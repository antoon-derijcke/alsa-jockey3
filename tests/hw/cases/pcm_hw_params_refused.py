#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""L3: JT-PCM-006, unsupported hw_params are refused.

Channels are fixed (4 playback, 6 capture) and the only format is S24_3LE, so
a wrong channel count, an unsupported format or an unsupported rate must all
be rejected at hw_params rather than accepted and then misbehaving.

hw: is used throughout, never plughw: -- plughw exists precisely to paper
over the rejection this case checks for, silently resampling or remapping an
unsupported request into one that succeeds around the driver rather than
through it.

The accept/refuse verdict does NOT come from aplay/arecord's exit code, for
the same reason pcm_limits.py (JT-PCM-003) does not trust it for period and
buffer size: aplay's -r option negotiates rate with
snd_pcm_hw_params_set_rate_near(), which silently rounds an unsupported rate
to the nearest one the device actually offers (22050 becomes 44100) and
exits 0. A case that read that exit code as "refused" would report a false
pass -- it would think it asked for 22050 and got refused, when what
actually happened is it asked for 22050 and was quietly given 44100
instead. Channels and format have no such rounding (there is no "near"
channel count, and snd_pcm_hw_params_set_format() only ever matches
exactly), but rate does, so all three are probed the same way for
consistency and because getting rate wrong here would defeat the case's
entire purpose.

So probe_hw_params() below binds straight to libasound's *exact* setters
(snd_pcm_hw_params_set_rate() with dir=0, not _near), which either negotiate
precisely what was asked or fail. That is ground truth for "the driver's
constraint table said yes or no", independent of any CLI front-end's
rounding behaviour.

For the control config (the one expected to succeed), a short real transfer
via aplay/arecord follows -- proof the negotiated parameters are actually
usable, not just acceptable on paper. The control is also the point of the
whole case: three refusals prove nothing if a fourth, identical-looking
request would also have failed for an unrelated reason (missing device
node, busy card, a typo in -D). Only a passing control turns the refusals
into evidence that the driver is validating, rather than the environment
being broken.
"""

import ctypes
import ctypes.util
import os
import sys

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from lib.case import Case          # noqa: E402
from lib import alsa               # noqa: E402

RATE = 44100
BAD_RATE = 22050
FORMAT = "S24_3LE"
BAD_FORMAT = "S16_LE"

# jockey3.c: fixed channel counts. Used to derive a channel count that is
# wrong in both directions never actually offered by the device.
STREAMS = {
    "playback": dict(tool="aplay", pcm="pcm0p", channels=4,
                      extra_args=["/dev/zero"]),
    "capture": dict(tool="arecord", pcm="pcm0c", channels=6,
                     extra_args=["/dev/null"]),
}

SAMPLES = 128   # negligible transfer -- only proves the negotiated config plays


# ------------------------------------------------------------ libasound ctypes

def _lib():
    if _lib.cache is None:
        path = ctypes.util.find_library("asound") or "libasound.so.2"
        lib = ctypes.CDLL(path)
        lib.snd_pcm_open.argtypes = [ctypes.POINTER(ctypes.c_void_p),
                                     ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
        lib.snd_pcm_hw_params_malloc.argtypes = [
            ctypes.POINTER(ctypes.c_void_p)]
        lib.snd_pcm_hw_params_set_rate.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_int]
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


def probe_hw_params(device, stream, channels, fmt, rate):
    """Ask libasound to negotiate this EXACT config. Returns (ok, err).

    No _near rounding is involved anywhere in this path -- see the module
    docstring for why that matters, especially for rate. Opens and closes
    the device on its own, holding it for a moment purely to negotiate
    parameters -- no data is transferred here.
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

        fmt_val = lib.snd_pcm_format_value(fmt.encode())
        setters = (
            ("access", lambda: lib.snd_pcm_hw_params_set_access(
                pcm, params, SND_PCM_ACCESS_RW_INTERLEAVED)),
            ("format", lambda: lib.snd_pcm_hw_params_set_format(
                pcm, params, fmt_val)),
            ("channels", lambda: lib.snd_pcm_hw_params_set_channels(
                pcm, params, channels)),
            ("rate", lambda: lib.snd_pcm_hw_params_set_rate(
                pcm, params, rate, 0)),
        )
        for label, setter in setters:
            rc = setter()
            if rc < 0:
                return False, f"set_{label}: {_errstr(lib, rc)}"

        rc = lib.snd_pcm_hw_params(pcm, params)
        if rc < 0:
            return False, f"hw_params commit: {_errstr(lib, rc)}"
        return True, None
    finally:
        lib.snd_pcm_hw_params_free(params)
        lib.snd_pcm_close(pcm)


# -------------------------------------------------------------- real transfer

def run_transfer(c, device, stream, extra_args_tool, channels, fmt, rate):
    cmd = [extra_args_tool["tool"], "-q", "-D", device, "-f", fmt,
           "-c", str(channels), "-r", str(rate),
           "--samples", str(SAMPLES)] + extra_args_tool["extra_args"]
    rc, _out, err = c.run(cmd, timeout=10)
    return rc, err


# -------------------------------------------------------------------- checks

def check(c, device, stream, label, channels, fmt, rate, expect_ok):
    info = STREAMS[stream]
    ok, probe_err = probe_hw_params(device, stream, channels, fmt, rate)
    desc = f"{stream} {label} (c={channels} f={fmt} r={rate})"
    c.progress(f"  {desc} -> {'accepted' if ok else 'refused'} "
               f"(expected {'accepted' if expect_ok else 'refused'})")

    record = {"stream": stream, "case": label, "channels": channels,
              "format": fmt, "rate": rate, "expect_ok": expect_ok,
              "accepted": ok}

    if expect_ok and not ok:
        c.fail(f"{desc}: control config was refused: {probe_err}")
        return record
    if not expect_ok and ok:
        c.fail(f"{desc}: unsupported config was accepted instead of refused")
        return record

    if expect_ok:
        rc, err = run_transfer(c, device, stream, info, channels, fmt, rate)
        record["transfer_rc"] = rc
        if rc != 0:
            c.fail(f"{desc}: accepted at hw_params but the real transfer "
                    f"failed (rc={rc}): "
                    f"{err.strip().splitlines()[-1][:160] if err else ''}")
    return record


def main():
    c = Case()
    c.require_card()
    c.require_tools("aplay", "arecord")

    device = c.device or alsa.device_name(c.card)

    results = []
    for stream, info in STREAMS.items():
        good_channels = info["channels"]
        wrong_channels = good_channels - 2

        results.append(check(c, device, stream, "wrong channel count",
                              wrong_channels, FORMAT, RATE, expect_ok=False))
        results.append(check(c, device, stream, "unsupported format",
                              good_channels, BAD_FORMAT, RATE, expect_ok=False))
        results.append(check(c, device, stream, "unsupported rate",
                              good_channels, FORMAT, BAD_RATE, expect_ok=False))
        results.append(check(c, device, stream, "control",
                              good_channels, FORMAT, RATE, expect_ok=True))

    accepted = sum(1 for r in results if r["accepted"])
    c.metric("configs_tested", len(results))
    c.metric("configs_accepted", accepted)
    c.metric("configs_refused", len(results) - accepted)
    c.metric("results", results)

    c.done()


if __name__ == "__main__":
    main()
