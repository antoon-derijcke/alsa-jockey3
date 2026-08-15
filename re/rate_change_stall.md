# Capture URB stall after a rate change

The open reliability problem of milestone 13: changing the sample rate leaves
the capture endpoint (`0x86`) not delivering, and the driver carries a stack of
mitigations for it -- stream liveness polling, a watchdog, a direction-aware
corrective reset, and deferred recovery at the next capture open.

This document records what is actually measured, as of 2026-08-14. It exists
because the mitigations were built before the fault was characterized, and the
measurements below do not all support the assumptions they were built on.

Start here next session. The companion document `usb/init_timing_comparison.md`
covers the *cold-boot* fault, which is fixed and is a different mechanism.

## The fault, stated precisely

After a rate change the capture stream stops completing URBs. The driver
notices in one of three places:

- `jockey3_pcm_hw_params()` waits 50 ms per direction and logs
  `Capture URB has stalled.`
- with a capture stream **open**, it escalates to a full `usb_queue_reset_device()`
- with **no** capture stream open, it logs and defers recovery to the next
  capture open, to avoid an audible reset glitch on healthy playback

Playback is unaffected throughout -- audible on speakers, and confirmed by the
playback rate ratio being correct on every change.

## What the vendor traces say: this is not a settling problem

Measured by `usb/rate_change_stream_timing.py`, relative to `SET_STATUS`:

| | n | sequence span | EP 0x05 resumes | EP 0x86 resumes |
|---|---|---|---|---|
| macOS | 47 | 103-142 ms | **0-1 ms** | **1-21 ms** |
| this driver (power-on traces) | 4 | 166-211 ms | 70-76 ms | 70-85 ms |

macOS resumes playback within a millisecond of `SET_STATUS` and the device
produces capture data again within 21 ms, in all 47 sequences across four
captures. **The vendor leaves no settling window after reconfiguration**, so
the device does not need time to reconfigure -- which rules out the mechanism
that turned out to explain the cold-boot fault. A power cycle restarts the
firmware; a rate change does not.

## What was ruled out on hardware

**The 50 ms wait is not too short.** Our own traces showed capture returning at
70-85 ms, later than the wait, which suggested the driver was declaring a stall
for a stream about to return on its own. Raising the wait to 250 ms in
`jockey3_pcm_hw_params()` changed nothing: `stalls_capture` stayed at 19 of 20
changes. The only thing that moved was `urb_stall_restarted_ms`, from
1433-1683 ms to 1640-1878 ms -- the extra wait before escalating. **Capture
genuinely does not return within 250 ms.** The hypothesis is dead; the
mitigations are load-bearing.

**The watchdog's onset figure is not independent evidence.**
`urb_stall_onset_ms` reads ~1000-1030 ms, but that is the watchdog's polling
interval, not a measured onset -- it reports the age at the first poll after
the stall. It cannot resolve anything faster than 1 s.

## The measurements, 2026-08-14

All on `x86_64-prod`, build `c64d7744` unless noted, 20 rate changes per run.

| run | capture stream | s/rate | stalls | resets | capture data |
|---|---|---|---|---|---|
| 194246 | none (playback only) | 1 | **19/20** | 0 | not checked |
| 194739 | none, 250 ms wait experiment | 1 | **19/20** | 0 | not checked |
| 195536 | attempted, `arecord` broken | 1 | **19/20** | 0 | none delivered |
| 204834 | open and working | 4 | **9/20** | 9 | **live on 20/20** |

The last row is the first valid capture measurement this case has ever
produced. Everything before it was either playback-only or defeated by a test
bug (`arecord -d 1.0`, rejected as an invalid duration).

Two things follow. With a capture stream open the fault is **less frequent**
(9 of 20 rather than 19 of 20) and **always recovers**: every stall was
followed by a reset, and capture returned 83-85% non-zero frames on every
change. Without a capture stream open, the stall happens nearly every time and
nothing recovers it -- by design, since recovery is deferred.

**This comparison is confounded and must not be quoted as a result.** Two
variables changed between rows 3 and 4: the capture stream being open (deferred
path vs reset path) *and* the duration per rate (1 s vs 4 s). Either could
explain 19 to 9. Resolving it is one run each:

```sh
cd tests/hw
./runner.py --case JT-RATE-001 --unattended     # capture on, 4 s -- baseline
# then, editing params: capture true + seconds_per_rate 1
# and:                  capture false + seconds_per_rate 4
```

If the stall rate tracks duration, the device needs recovery time *between*
changes and the sweep has been rushing it. If it tracks the capture stream
being open, the two code paths differ in a way worth reading closely.

## What is instrumented now

`JT-RATE-001` was, until today, a playback-only test wearing a general name: it
never opened capture, so it never checked capture data and never exercised the
reset path -- the path that carries the risk. It now:

- plays and records simultaneously on every change
- classifies capture four ways: `live`, `nodata` (no frames -- the transport
  never restarted), `silent` (frames, all zero -- the converter never
  restarted), `error`
- measures the **effective** sample rate from the clock: playback elapsed
  against expected, and capture frames over the wall-clock time they took to
  arrive. Not frames over requested duration, which measures nothing, since
  `arecord -d` derives its frame target from the rate it asked for
- writes a `JT-MARK` per change and attributes every stall and reset to the
  change that caused it, reported on screen as the run proceeds
- counts resets by cause: `resets_capture_stall` vs `resets_playback_stall`

The distinction between `nodata` and `silent` matters for where it sends an
investigation: no samples is the URB stream not restarting, all-zero samples
would be the converter not running. They were conflated at first, producing a
verdict that blamed the audio engine while playback was audibly fine.

## Open questions, in the order worth attacking

1. **Resolve the confound above.** Two runs, ~10 minutes. Nothing else should
   be concluded until this is settled.
2. **Does the stall correlate with direction or rate pair?** The per-change
   attribution now makes this visible and it has never been looked at. If
   downward switches dominate, that matches the long-standing suspicion in
   `implementation_plan.md`; if it is the first change after probe, that is a
   different story entirely.
3. **What does the wire show during a failing rate change?** The corpus has no
   trace of one. `usb/parse_openvizsla.py --errors=0` would show whether the
   device NAKs or stalls the endpoint, or simply goes quiet. This is the
   expensive instrument and should follow 1 and 2, not precede them.
4. **Why does our sequence take 166-211 ms against macOS's 103-142 ms?** We are
   slower and resume later (70-85 ms vs 1-21 ms). Not obviously causal, but it
   is an unexplained divergence from a reference implementation that does not
   have the fault.

## Reproducing

```sh
cd tests/hw && ./runner.py --case JT-RATE-001 --unattended     # ~1.5 min
python3 re/usb/rate_change_stream_timing.py                    # vendor timings
```

The vendor timing script reads the checked-in `openvizsla/*_events.txt` and
`*_parsed.txt`, so it needs no hardware.
