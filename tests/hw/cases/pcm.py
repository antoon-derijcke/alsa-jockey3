#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""L3/L5: PCM playback, capture, simultaneous duplex, and a duplex soak.

One file because the four modes share the tone generator, the arecord
invocation and the watch_pcm-based xrun/avail_max accounting. Selected by
argv[1] -- the same convention build_gate.py uses for its four gates.

    pcm.py playback | capture | duplex | soak
"""

import math
import os
import select
import subprocess
import sys
import time

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from lib.case import Case          # noqa: E402
from lib import alsa, env, kmsg    # noqa: E402

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


def _accumulate_frames(sumsq, chunk, channels, limit=None):
    """Add every whole frame in chunk to sumsq (in place, S24_3LE, signed).

    Returns the number of frames added. Ignores any trailing partial frame --
    the caller is responsible for carrying those bytes into the next chunk,
    because a read() on a pipe or a fixed-size file read has no reason to
    land on a frame boundary. Silently mis-accumulating a partial frame does
    not crash or look wrong: it rotates one frame's channels against their
    neighbors and every reading still comes out plausible, which is what
    makes it dangerous rather than merely a bug.

    limit, when given, stops after that many frames even if chunk holds more
    -- used by the streaming reader to land on a report boundary without
    discarding the surplus bytes, which the caller gets back by slicing chunk
    at frames_added * frame itself.
    """
    frame = channels * BYTES_PER_SAMPLE
    n = 0
    for off in range(0, len(chunk) - frame + 1, frame):
        if limit is not None and n >= limit:
            break
        for ch in range(channels):
            s = chunk[off + ch * BYTES_PER_SAMPLE:
                      off + (ch + 1) * BYTES_PER_SAMPLE]
            v = int.from_bytes(s, "little", signed=True)
            sumsq[ch] += v * v
        n += 1
    return n


def _dbfs_from_sumsq(sumsq, count):
    """Turn accumulated sum-of-squares into per-channel dBFS, or None.

    None means "nodata" -- count is zero, nothing was ever accumulated. A
    channel whose sumsq is zero despite count > 0 is bit-exact digital
    silence, reported as SILENT_DBFS rather than the -inf that log10(0)
    would produce, which does not survive JSON and prints nothing useful.
    Both are legitimate: with nothing plugged into the inputs a genuine
    noise floor around -90 to -110 dBFS is the correct reading, and only
    actual digital silence or a dead channel should read as SILENT_DBFS.
    """
    if count == 0:
        return None
    out = []
    for sq in sumsq:
        if sq == 0:
            out.append(SILENT_DBFS)
        else:
            rms = math.sqrt(sq / count)
            out.append(round(20 * math.log10(rms / FULL_SCALE), 1))
    return out


def rms_dbfs_per_channel(path, channels, max_frames=RMS_MAX_FRAMES):
    """Per-channel RMS level in dBFS, from a raw S24_3LE capture file."""
    sumsq = [0] * channels
    count = 0
    try:
        with open(path, "rb") as f:
            while count < max_frames:
                chunk = f.read(channels * BYTES_PER_SAMPLE * 8192)
                if not chunk:
                    break
                count += _accumulate_frames(sumsq, chunk, channels,
                                            limit=max_frames - count)
    except OSError:
        return None
    return _dbfs_from_sumsq(sumsq, count)


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


# ----------------------------------------------------------------- soak mode

# Length of the RMS snapshot taken at each report interval. Short on purpose:
# the point is a periodic health check an analyst can line up against dmesg,
# not a precise long-window average, and a short window keeps the per-report
# CPU cost bounded on the slowest target (armhf-prod) as well as the fastest.
SOAK_SAMPLE_SECONDS = 4
# Bytes read and thrown away per drain call between reports -- no per-sample
# accumulation happens on this path at all, which is what lets one continuous
# capture stream run for hours without turning the analyzer itself into the
# bottleneck. See _accumulate_frames() for where the real cost is paid, and
# only during the bounded sample window.
DRAIN_CHUNK_FRAMES = 65536
# A capture pipe silent this long while the substream still reports RUNNING
# is not a measurement gap, it is the fault this case exists to catch: the
# capture URB stream died without the driver necessarily saying so in dmesg.
CAPTURE_GAP_S = 30.0


def _sample_window(stdout, leftover, channels, frames_wanted, timeout_s=15.0):
    """Read up to frames_wanted whole frames from a live pipe and return
    (dbfs_or_None, new_leftover).

    Bounded by timeout_s so a stalled capture stream turns into a "nodata"
    reading rather than a hang -- the report loop must get control back
    either way, because it is also what is watching for the run's end.
    Whatever whole frames arrived before the timeout are still measured;
    only a stream that produced nothing at all reports None.
    """
    frame = channels * BYTES_PER_SAMPLE
    sumsq = [0] * channels
    count = 0
    buf = leftover
    deadline = time.monotonic() + timeout_s
    while count < frames_wanted:
        n = _accumulate_frames(sumsq, buf, channels, limit=frames_wanted - count)
        count += n
        buf = buf[n * frame:]
        if count >= frames_wanted:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        ready, _w, _x = select.select([stdout], [], [], remaining)
        if not ready:
            break
        chunk = stdout.read(frame * 8192)
        if not chunk:
            break
        buf += chunk
    return _dbfs_from_sumsq(sumsq, count), buf


def run_soak(c, device):
    """JT-PCM-008: sustained duplex, watched rather than merely timed out.

    One continuous playback stream (/dev/urandom, as the manual steps used --
    not bounded by a fixed synth length, and the codec sees varied data for
    the whole run) and one continuous capture stream, both open for the whole
    duration. Capture goes straight to a pipe and is never written to disk: an
    eight-hour raw S24_3LE capture at 96 kHz is upward of 5 GB, and nothing
    here needs it kept. Most of it is read and discarded in large, cheap
    chunks; only a short RMS snapshot is retained at each report interval.

    xruns and avail_max come from watch_pcm, as everywhere else in this
    suite. What is new here is the capture pipe itself as a liveness signal:
    a gap longer than CAPTURE_GAP_S while the substream still reports RUNNING
    is recorded and failed, because that is a dead transport an xrun count
    alone would not show.
    """
    c.require_tools("aplay", "arecord")
    hours = float(c.params.get("hours", 8))
    rate = int(c.params.get("rate", 44100))
    report_s = float(c.params.get("report_interval_minutes", 10)) * 60
    duration_s = hours * 3600
    frame = CAPTURE_CHANNELS * BYTES_PER_SAMPLE

    mem_start = env.slab_kb()

    watch_p = alsa.watch_pcm(c.card, "pcm0p")
    watch_c = alsa.watch_pcm(c.card, "pcm0c")
    watch_p.start()
    watch_c.start()

    urandom = open("/dev/urandom", "rb")
    err_log = open(os.path.join(c.workdir, "soak_stderr.log"), "w",
                   encoding="utf-8")
    aplay = subprocess.Popen(
        ["aplay", "-D", device, "-r", str(rate), "-c", str(PLAYBACK_CHANNELS),
         "--format", FORMAT, "-t", "raw"],
        stdin=urandom, stdout=subprocess.DEVNULL, stderr=err_log)
    # bufsize=0: an ordinary buffered stdout blocks read() until it has
    # collected the requested size or EOF, which defeats select() entirely --
    # a select()-ready pipe with 4 bytes waiting would still hang a
    # read(frame * 65536) until 65536 more frames arrived. Unbuffered gives
    # the raw "return whatever is available now" semantics this loop depends
    # on for both the drain path and the gap timeout.
    arec = subprocess.Popen(
        ["arecord", "-D", device, "-r", str(rate), "-c", str(CAPTURE_CHANNELS),
         "--format", FORMAT, "-t", "raw", "-d", str(int(duration_s) + 60), "-"],
        stdout=subprocess.PIPE, stderr=err_log, bufsize=0)

    t0 = time.monotonic()
    deadline = t0 + duration_s
    next_report = t0 + min(report_s, duration_s)
    leftover = b""
    last_data_at = t0
    gap_open = False
    gap_start = t0
    gaps = []
    timeline = []
    playback_dead = False

    def teardown():
        for p in (aplay, arec):
            p.terminate()
        for p in (aplay, arec):
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        urandom.close()
        err_log.close()

    try:
        while True:
            now = time.monotonic()
            if now >= deadline:
                break
            if not playback_dead and aplay.poll() is not None:
                playback_dead = True
                c.fail(f"playback exited after {round(now - t0)}s "
                       f"(rc={aplay.returncode})")

            if now >= next_report:
                levels, leftover = _sample_window(
                    arec.stdout, leftover, CAPTURE_CHANNELS,
                    int(SOAK_SAMPLE_SECONDS * rate))
                minutes = round((now - t0) / 60, 1)
                c.progress(f"  t+{minutes:g}m  capture RMS  "
                           f"{fmt_dbfs(levels)} dBFS")
                kmsg.Marker(f"{c.id}#t{int(minutes)}m").write()
                timeline.append({"t_min": minutes, "dbfs": levels})
                if levels is not None:
                    last_data_at = now
                next_report = now + report_s
                continue

            poll_s = max(0.0, min(next_report, deadline) - now)
            ready, _w, _x = select.select([arec.stdout], [], [],
                                          min(poll_s, 5.0))
            if not ready:
                since = now - last_data_at
                if since > CAPTURE_GAP_S and not gap_open:
                    gap_open = True
                    gap_start = last_data_at
                    c.fail(f"no capture data for over {CAPTURE_GAP_S:g}s "
                           f"(substream state: {watch_c.state})")
                c.status(f"  t+{round((now - t0) / 60)}m / {hours:g}h  "
                         f"next report in {round(next_report - now)}s")
                continue

            chunk = leftover + arec.stdout.read(frame * DRAIN_CHUNK_FRAMES)
            if not chunk:
                c.fail(f"capture pipe closed after {round(now - t0)}s, "
                       f"before the {hours:g}h run finished")
                break
            last_data_at = now
            if gap_open:
                gaps.append(round(now - gap_start, 1))
                gap_open = False
            n_frames = len(chunk) // frame
            leftover = chunk[n_frames * frame:]
    finally:
        teardown()
        watch_p.stop()
        watch_c.stop()

    # A gap still open when the run hit its deadline was already failed above
    # at the moment it crossed CAPTURE_GAP_S -- close it out here so it is not
    # missing from capture_gap_max_s just because the run ended before the
    # stream recovered.
    if gap_open:
        gaps.append(round(time.monotonic() - gap_start, 1))

    elapsed_h = (time.monotonic() - t0) / 3600
    mem_end = env.slab_kb()
    if mem_start is not None and mem_end is not None:
        c.metric("memory_growth_kb", mem_end - mem_start)

    c.metric("hours_run", round(elapsed_h, 2))
    c.metric("xruns_playback", watch_p.xruns)
    c.metric("xruns_capture", watch_c.xruns)
    c.metric("xruns_per_hour",
             round((watch_p.xruns + watch_c.xruns) / elapsed_h, 2)
             if elapsed_h else None)
    c.metric("avail_max_playback", watch_p.avail_max)
    c.metric("avail_max_capture", watch_c.avail_max)
    c.metric("rms_dbfs_timeline", timeline)
    c.metric("capture_gaps", len(gaps))
    c.metric("capture_gap_max_s", max(gaps) if gaps else 0)

    if watch_p.xruns:
        c.fail(f"{watch_p.xruns} playback xrun(s) over the run")
    if watch_c.xruns:
        c.fail(f"{watch_c.xruns} capture xrun(s) over the run")


MODES = {"playback": run_playback, "capture": run_capture, "duplex": run_duplex,
         "soak": run_soak}


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
