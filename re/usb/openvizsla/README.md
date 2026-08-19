# OpenVizsla USB Traces

This directory contains the USB traces captured by the OpenVizsla USB protocol
capture device.

Due to the sheer size of the raw traces (between 50 MB and 1 GB depending on
the duration of the trace) these are *omitted* from the git repo. Only the
parsed and pruned versions are included.

The orignal, raw capture files are stored outside of this tree on a Seafile 
shared folder; with a symbolic link to this this file in this repository
directory.

---

## Diagnosing audio glitches that report nothing

Written down because it is the kind of thing that gets re-derived expensively.
See [`docs/test_strategy.md` §11a](../../../docs/test_strategy.md) for when
this is warranted — the short version is: only when the defect is reproducible
on a **production** kernel and every ALSA-side counter says the stream was
fine.

### What you are looking for

This driver's URBs run free for the device's lifetime, because playback also
carries MIDI OUT and the device expects an uninterrupted packet stream. So the
failure mode invisible to ALSA is a **late URB resubmission**: the ALSA buffer
was never short, but the wire went quiet long enough for the Ploytec stack on
the device to run its own FIFO dry. What you hear is the device underrunning,
not the host.

On the wire that is a **gap in the OUT stream on EP 0x05**. At 44.1 kHz the
device consumes one 512-byte packet per 10 frames, so packets should arrive at
a near-constant cadence; a glitch is a delta several times the median, and the
audible artifact lines up with it.

Capture the playback endpoint only. Tracing everything produces a gigabyte of
which almost all is MIDI IN polling and NAKs.

### Reducing the capture

`parse_openvizsla.py` turns a raw capture into completed transactions, dropping
handshake noise and NAK polling. That discarding is right for glitch hunting,
where NAKs are just flow control; when investigating a transfer that *failed*,
re-parse with `--errors=0` so unresolved bursts and STALLs on EP0 survive.
See `../README.md`.

```sh
python3 ../parse_openvizsla.py capture.txt      # writes capture_parsed.txt
```

The output is one line per successful transaction:

```
Timestamp    | Direction  | Target   | Bytes | Payload Data
```

### The measurement

Inter-packet delta on the playback endpoint, as a distribution. A healthy
stream is tightly clustered; starvation shows as a long tail.

```sh
awk -F'|' '$2 ~ /OUT/ {
        t = $1 + 0
        if (prev) printf "%.6f\n", t - prev
        prev = t
    }' capture_parsed.txt | sort -n | awk '
    { d[NR] = $1; s += $1 }
    END {
        printf "n=%d  mean=%.6f  median=%.6f  p99=%.6f  max=%.6f\n",
               NR, s/NR, d[int(NR*0.5)], d[int(NR*0.99)], d[NR]
    }'
```

Compare a clean run against a glitching one. The mean will barely move — the
average rate is set by the audio clock and cannot drift far without the pitch
being wrong. **The tail is the signal.** A p99 or max several times the median
is the ring having drained.

### Interpreting it

| Observation | Reading |
|---|---|
| Tight distribution, no tail | The wire is fine. The defect is elsewhere — suspect the data, and go to loopback |
| Isolated large gaps, host quiet during them | The driver did not resubmit in time: the ring drained |
| Gaps with NAKs or retries around them | The device was not accepting; a device-side or cabling problem, not scheduling |
| Regular small jitter, no outliers | Normal. USB bulk has no isochronous guarantee and the device tolerates it |

### Reference material

`../../../usb capture 2020/`, `usb capture 2022/` and `usb capture 2026/` in
the project directory hold traces of the **macOS and Windows drivers** doing
the same work. Those are the comparison worth having: they show what cadence
the device is happy with, which is a far better baseline than any figure
derived from this driver alone.

`re/protocol_analysis.md` documents the packet format those captures revealed.

### What this cannot tell you

Only timing. Whether the *bytes* were right is a different question with a
different instrument — the loopback case (`JT-AUDIO-002`) for output presence
and channel map (not bit-exact content; the round trip is analog), and the
KUnit suite plus `codecbench.py` for the codec itself. A trace showing clean
cadence and audible corruption means the problem is in the data, and no
amount of further tracing will find it.
