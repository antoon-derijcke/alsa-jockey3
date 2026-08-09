# SPDX-License-Identifier: GPL-2.0-or-later
"""ALSA-side helpers: find the card, read its state, count xruns.

Everything here reads /proc/asound rather than shelling out, because the
numbers are what tests assert on and parsing `aplay` output for them is
fragile in a way that quietly passes.
"""

import glob
import os
import re
import subprocess
import threading

DRIVER_ID = "Jockey3"          # the card id the driver registers


def _read(path, default=""):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return default


def find_card():
    """Return (index, id) of the Jockey 3 card, or (None, None).

    Matched by card id rather than by index: index depends on what else is
    plugged in, and hardcoding hw:1 is how a test ends up driving the onboard
    audio and passing.
    """
    for path in sorted(glob.glob("/proc/asound/card[0-9]*")):
        if not os.path.isdir(path):
            continue
        idx = os.path.basename(path)[len("card"):]
        cid = _read(os.path.join(path, "id"))
        if cid and DRIVER_ID.lower() in cid.lower():
            return int(idx), cid
    # Fall back to the card list, which names the driver even when the id
    # differs.
    for line in _read("/proc/asound/cards").splitlines():
        m = re.match(r"\s*(\d+)\s+\[(\S+)\s*\]", line)
        if m and DRIVER_ID.lower() in line.lower():
            return int(m.group(1)), m.group(2)
    return None, None


def device_name(index, dev=0):
    return f"hw:{index},{dev}"


def substreams(index):
    """What the card actually exposes -- the shape probe should have created."""
    base = f"/proc/asound/card{index}"
    out = {"playback": [], "capture": [], "rawmidi": []}
    for p in sorted(glob.glob(os.path.join(base, "pcm*p"))):
        out["playback"].append(os.path.basename(p))
    for p in sorted(glob.glob(os.path.join(base, "pcm*c"))):
        out["capture"].append(os.path.basename(p))
    for p in sorted(glob.glob(os.path.join(base, "midi*"))):
        out["rawmidi"].append(os.path.basename(p))
    return out


# The field is "xrun_counter" in current kernels; "xruns" is accepted too in
# case an older one spells it that way. Matching only "xruns" is how this
# metric read zero on every run for a day: the regex never matched, and a
# missing key defaulted to 0, which is indistinguishable from a clean run.
XRUN_RE = re.compile(r"^\s*xrun(?:s|_counter)\s*:\s*(\d+)", re.M)
STATE_RE = re.compile(r"^\s*state\s*:\s*(\S+)", re.M)
AVAIL_MAX_RE = re.compile(r"^\s*avail_max\s*:\s*(\d+)", re.M)
DELAY_RE = re.compile(r"^\s*delay\s*:\s*(-?\d+)", re.M)


def pcm_status(index, pcm="pcm0p", sub="sub0"):
    """Parse a substream's status file.

    Returns {} when the substream is closed -- the status file exists but
    reports 'closed', which is not an error condition.

    IMPORTANT: everything here is readable only while the substream is OPEN.
    Sampling before and after a playback command therefore reads 'closed'
    twice and reports a difference of zero no matter what happened in
    between. Use watch_pcm() to sample during.
    """
    path = f"/proc/asound/card{index}/{pcm}/{sub}/status"
    text = _read(path)
    if not text or text.startswith("closed"):
        return {}
    out = {}
    for key, rx in (("xruns", XRUN_RE), ("avail_max", AVAIL_MAX_RE),
                    ("delay", DELAY_RE)):
        m = rx.search(text)
        if m:
            out[key] = int(m.group(1))
    m = STATE_RE.search(text)
    if m:
        out["state"] = m.group(1)
    return out


def xruns(index, pcm="pcm0p", sub="sub0"):
    return pcm_status(index, pcm, sub).get("xruns", 0)


class watch_pcm(threading.Thread):
    """Sample a substream's status for as long as it stays open.

    The counters vanish when the stream closes, so they have to be read while
    it runs. Returns the last values seen rather than the first: xrun_counter
    only rises, and avail_max is a high-water mark the kernel keeps for us.

    avail_max is worth as much as the xrun count here. It is how close the
    buffer came to running dry, so it distinguishes "comfortable" from "made
    it by one period" -- and a run that never xruns but whose avail_max climbs
    toward buffer_size is the one about to start crackling.
    """

    def __init__(self, index, pcm="pcm0p", sub="sub0", interval=0.02):
        super().__init__(daemon=True)
        self.index, self.pcm, self.sub = index, pcm, sub
        self.interval = interval
        self._stop = threading.Event()
        self.samples = 0
        self.xruns = 0
        self.avail_max = 0
        self.saw_open = False

    def run(self):
        while not self._stop.is_set():
            st = pcm_status(self.index, self.pcm, self.sub)
            if st:
                self.saw_open = True
                self.samples += 1
                self.xruns = max(self.xruns, st.get("xruns", 0))
                self.avail_max = max(self.avail_max, st.get("avail_max", 0))
            self._stop.wait(self.interval)

    def stop(self):
        self._stop.set()
        self.join(timeout=2)
        return self


def rawmidi_device(index):
    for p in sorted(glob.glob(f"/proc/asound/card{index}/midi*")):
        name = os.path.basename(p)
        m = re.match(r"midi(\d+)", name)
        if m:
            return f"hw:{index},{m.group(1)}"
    return None


def have(tool):
    from shutil import which
    return which(tool) is not None


def missing_tools(tools):
    return [t for t in tools if not have(t)]


def stop_sound_server():
    """Release the device from PipeWire/PulseAudio.

    Without this the card is opened by the session's sound server and every
    exclusive-access test fails for a reason that has nothing to do with the
    driver. Returns what was stopped so it can be restarted afterwards.
    """
    stopped = []
    for unit in ("wireplumber.service", "pipewire.service",
                 "pipewire-pulse.service"):
        r = subprocess.run(["systemctl", "--user", "is-active", "--quiet", unit],
                           capture_output=True)
        if r.returncode == 0:
            subprocess.run(["systemctl", "--user", "stop", unit],
                           capture_output=True)
            stopped.append(unit)
    return stopped


def start_sound_server(units):
    for unit in units:
        subprocess.run(["systemctl", "--user", "start", unit],
                       capture_output=True)
