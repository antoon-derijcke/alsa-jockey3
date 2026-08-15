#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""L3: PCM playback, capture and simultaneous duplex.

One file because the three modes share the tone generator, the arecord
invocation and the watch_pcm-based xrun/avail_max accounting. Selected by
argv[1] -- the same convention build_gate.py uses for its four gates.

    pcm.py playback | capture | duplex
"""

import math
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from lib.case import Case          # noqa: E402
from lib import alsa               # noqa: E402

PLAYBACK_CHANNELS = 4               # fixed by the driver: Master + Headphone
CAPTURE_CHANNELS = 6                # fixed by the driver: min == max
FORMAT = "S24_3LE"                  # the only format the device accepts
BYTES_PER_SAMPLE = 3

FULL_SCALE = 1 << 23                # S24_3LE's positive full scale, 2**23
# A channel that is bit-exact zero throughout has no RMS in dB -- log10(0) is
# -inf, which does not survive JSON and does not print usefully either. This
# reads instead as "digital silence", comfortably below any real noise floor,
# so it is distinguishable from a measured floor without a NaN in the record.
# See rms_dbfs_per_channel() and capture_outcome() in rate_change.py, which
# draws the same nodata/silent/live distinction for the same reason.
SILENT_DBFS = -150.0
# A steady noise floor does not need the whole file to measure -- capped for
# the same reason nonzero_channels() below caps at 20000 frames: 96 kHz x 6ch
# x 30s in pure Python would make the analyzer itself the slow part of a soak
# run rather than a one-off check on a few seconds of capture.
RMS_MAX_FRAMES = 200_000


def play(device, rate, seconds, workdir, channels=PLAYBACK_CHANNELS):
    """sox generates, aplay consumes. Returns (rc, stderr, elapsed_to_first_write)."""
    gen = subprocess.Popen(
        ["sox", "-n", "-r", str(rate), "-c", str(channels), "-b", "24",
         "-e", "signed-integer", "-t", "raw", "-",
         "synth", str(seconds), "sine", "E3", "gain", "-6"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    t0 = time.time()
    p = subprocess.Popen(
        ["aplay", "-D", device, "-r", str(rate), "-c", str(channels),
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


def start_playback_async(device, rate, seconds, channels=PLAYBACK_CHANNELS):
    """Non-blocking form of play(), for running alongside a concurrent capture.

    Returns (aplay, sox) so the caller can wait on both once the capture that
    runs beside it has also been started.
    """
    gen = subprocess.Popen(
        ["sox", "-n", "-r", str(rate), "-c", str(channels), "-b", "24",
         "-e", "signed-integer", "-t", "raw", "-",
         "synth", str(seconds), "sine", "E3", "gain", "-6"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    p = subprocess.Popen(
        ["aplay", "-D", device, "-r", str(rate), "-c", str(channels),
         "--format", FORMAT, "-t", "raw"],
        stdin=gen.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True)
    gen.stdout.close()
    return p, gen


def finish_playback(p, gen, seconds):
    try:
        _out, err = p.communicate(timeout=seconds + 30)
    except subprocess.TimeoutExpired:
        p.kill()
        gen.kill()
        return 124, "aplay did not finish"
    gen.wait(timeout=5)
    return p.returncode, err


def start_capture_async(device, rate, seconds, path, channels=CAPTURE_CHANNELS):
    """Non-blocking capture, to run concurrently with start_playback_async().

    arecord -d takes whole seconds and rounds to zero below half a second --
    where it means "no limit" -- so the recording would run until the case
    timed out rather than for the fraction of a second asked for.
    """
    duration = max(1, int(round(seconds)))
    return subprocess.Popen(
        ["arecord", "-D", device, "-r", str(rate), "-c", str(channels),
         "--format", FORMAT, "-t", "raw", "-d", str(duration), path],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)


def nonzero_channels(path, channels):
    """Which channels carry anything at all, from a raw S24_3LE capture."""
    frame = channels * BYTES_PER_SAMPLE
    seen = [False] * channels
    try:
        with open(path, "rb") as f:
            data = f.read(frame * 20000)
    except OSError:
        return []
    for off in range(0, len(data) - frame + 1, frame):
        for ch in range(channels):
            s = data[off + ch * BYTES_PER_SAMPLE:
                     off + (ch + 1) * BYTES_PER_SAMPLE]
            if s and any(s):
                seen[ch] = True
        if all(seen):
            break
    return [i for i, v in enumerate(seen) if v]


def rms_dbfs_per_channel(path, channels, max_frames=RMS_MAX_FRAMES):
    """Per-channel RMS level in dBFS, from a raw S24_3LE capture.

    Returns None when the file carries no frames at all -- "nodata" -- which
    must not be confused with a channel that has frames but is bit-exact zero
    throughout, reported as SILENT_DBFS. Both are legitimate outcomes here:
    with nothing plugged into the inputs a genuine noise floor around -90 to
    -110 dBFS is the correct reading, and only actual digital silence or a
    dead channel should read as SILENT_DBFS.
    """
    frame = channels * BYTES_PER_SAMPLE
    sumsq = [0] * channels
    count = 0
    try:
        with open(path, "rb") as f:
            while count < max_frames:
                chunk = f.read(frame * 8192)
                if not chunk:
                    break
                for off in range(0, len(chunk) - frame + 1, frame):
                    if count >= max_frames:
                        break
                    for ch in range(channels):
                        s = chunk[off + ch * BYTES_PER_SAMPLE:
                                  off + (ch + 1) * BYTES_PER_SAMPLE]
                        v = int.from_bytes(s, "little", signed=True)
                        sumsq[ch] += v * v
                    count += 1
    except OSError:
        return None
    if count == 0:
        return None
    out = []
    for ch in range(channels):
        if sumsq[ch] == 0:
            out.append(SILENT_DBFS)
        else:
            rms = math.sqrt(sumsq[ch] / count)
            out.append(round(20 * math.log10(rms / FULL_SCALE), 1))
    return out


def fmt_dbfs(levels):
    if levels is None:
        return "no data"
    return " ".join(f"ch{i}={v:.1f}" for i, v in enumerate(levels))


# --------------------------------------------------------------------- modes

def run_playback(c, device):
    c.require_tools("aplay", "sox")
    rates = c.params.get("rates", [44100, 48000, 88200, 96000])
    seconds = int(c.params.get("seconds", 3))

    total_xruns = 0
    unobserved = []
    for rate in rates:
        watch = alsa.watch_pcm(c.card, "pcm0p")
        watch.start()
        rc, err, elapsed = play(device, rate, seconds, c.workdir)
        watch.stop()

        total_xruns += watch.xruns
        if not watch.saw_open:
            unobserved.append(str(rate))

        if rc != 0:
            c.fail(f"{rate} Hz: aplay exited {rc}: "
                   f"{(err or '').strip().splitlines()[-1][:120] if err else ''}")
        elif watch.xruns:
            c.fail(f"{rate} Hz: {watch.xruns} xrun(s)")
        if elapsed is not None:
            c.metric(f"elapsed_s_{rate}", elapsed)
        c.metric(f"avail_max_{rate}", watch.avail_max)

    c.metric("xruns", total_xruns)
    c.metric("rates_tested", len(rates))
    if unobserved:
        c.note("stream never observed open at: " + ", ".join(unobserved)
               + " -- xrun figures for those rates mean nothing")


def run_capture(c, device):
    rates = c.params.get("rates", [44100, 48000, 88200, 96000])
    seconds = int(c.params.get("seconds", 3))

    total_xruns = 0
    unobserved = []
    for rate in rates:
        raw = os.path.join(c.workdir, f"capture_{rate}.raw")
        watch = alsa.watch_pcm(c.card, "pcm0c")
        watch.start()
        try:
            p = subprocess.run(
                ["arecord", "-D", device, "-d", str(seconds), "-f", FORMAT,
                 "-c", str(CAPTURE_CHANNELS), "-r", str(rate), "-t", "raw", raw],
                capture_output=True, text=True, timeout=seconds + 30)
            rc, err = p.returncode, p.stderr
        except subprocess.TimeoutExpired:
            rc, err = 124, "arecord did not finish"
        watch.stop()
        total_xruns += watch.xruns
        if not watch.saw_open:
            unobserved.append(str(rate))
        c.metric(f"avail_max_{rate}", watch.avail_max)

        if rc != 0:
            c.fail(f"{rate} Hz: arecord exited {rc}: "
                   f"{(err or '').strip()[:120]}")
            continue
        if watch.xruns:
            c.fail(f"{rate} Hz: {watch.xruns} xrun(s)")

        got = os.path.getsize(raw) if os.path.exists(raw) else 0
        expect = rate * seconds * CAPTURE_CHANNELS * BYTES_PER_SAMPLE
        c.metric(f"captured_bytes_{rate}", got)
        if got < expect * 0.9:
            c.fail(f"{rate} Hz: captured {got} bytes, expected about {expect}")

        live = nonzero_channels(raw, CAPTURE_CHANNELS)
        c.metric(f"nonzero_channels_{rate}", live)

    c.metric("xruns", total_xruns)
    c.metric("rates_tested", len(rates))
    if unobserved:
        c.note("stream never observed open at: " + ", ".join(unobserved)
               + " -- xrun figures for those rates mean nothing")


def run_duplex(c, device):
    """JT-PCM-005: playback and capture concurrently, at each rate.

    The pass criterion is that both directions run to completion without an
    xrun -- the same thing the manual steps checked by watching two
    terminals. The capture level is reported alongside it but never fails the
    case: with nothing plugged into the inputs, a noise floor around -90 to
    -110 dBFS is the correct reading, and with a loopback cable and a known
    source it will read far higher. Only the person who knows what is plugged
    in can say which is expected, so the level is surfaced on the terminal
    and in the record for them to judge, per JT-PCM-004's precedent that
    silence is not, by itself, a defect.
    """
    c.require_tools("aplay", "arecord", "sox")
    rates = c.params.get("rates", [44100, 96000])
    seconds = int(c.params.get("seconds", 4))

    total_xruns_p = total_xruns_c = 0
    unobserved = []
    for rate in rates:
        c.status(f"  {rate} Hz: running {seconds}s duplex...")
        raw = os.path.join(c.workdir, f"duplex_capture_{rate}.raw")

        watch_p = alsa.watch_pcm(c.card, "pcm0p")
        watch_c = alsa.watch_pcm(c.card, "pcm0c")
        watch_p.start()
        watch_c.start()

        arec = start_capture_async(device, rate, seconds, raw)
        p, gen = start_playback_async(device, rate, seconds)

        try:
            _out, cap_err = arec.communicate(timeout=seconds + 30)
            cap_rc = arec.returncode
        except subprocess.TimeoutExpired:
            arec.kill()
            cap_rc, cap_err = 124, "arecord did not finish"
        play_rc, play_err = finish_playback(p, gen, seconds)

        watch_p.stop()
        watch_c.stop()

        total_xruns_p += watch_p.xruns
        total_xruns_c += watch_c.xruns
        if not watch_p.saw_open or not watch_c.saw_open:
            unobserved.append(str(rate))
        c.metric(f"avail_max_playback_{rate}", watch_p.avail_max)
        c.metric(f"avail_max_capture_{rate}", watch_c.avail_max)

        if play_rc != 0:
            c.fail(f"{rate} Hz: aplay exited {play_rc}: "
                   f"{(play_err or '').strip().splitlines()[-1][:120] if play_err else ''}")
        elif watch_p.xruns:
            c.fail(f"{rate} Hz: {watch_p.xruns} playback xrun(s)")

        if cap_rc != 0:
            c.fail(f"{rate} Hz: arecord exited {cap_rc}: "
                   f"{(cap_err or '').strip().splitlines()[-1][:120] if cap_err else ''}")
        elif watch_c.xruns:
            c.fail(f"{rate} Hz: {watch_c.xruns} capture xrun(s)")

        levels = rms_dbfs_per_channel(raw, CAPTURE_CHANNELS)
        c.metric(f"rms_dbfs_{rate}", levels)
        c.metric(f"rms_dbfs_min_{rate}",
                 min(levels) if levels is not None else None)
        c.progress(f"  {rate} Hz: capture RMS  {fmt_dbfs(levels)} dBFS")

    c.metric("xruns_playback", total_xruns_p)
    c.metric("xruns_capture", total_xruns_c)
    c.metric("rates_tested", len(rates))
    if unobserved:
        c.note("a stream was never observed open at: " + ", ".join(unobserved)
               + " -- xrun figures for those rates mean nothing")


MODES = {"playback": run_playback, "capture": run_capture, "duplex": run_duplex}


def main():
    c = Case()
    c.require_card()

    mode = sys.argv[1] if len(sys.argv) > 1 else None
    if mode not in MODES:
        c.blocked(f"unknown pcm mode {mode!r}, want one of {sorted(MODES)}")

    device = c.device or alsa.device_name(c.card)
    MODES[mode](c, device)
    c.done()


if __name__ == "__main__":
    main()
