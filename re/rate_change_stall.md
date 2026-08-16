# Capture URB stall after a rate change

The open reliability problem of milestone 13: changing the sample rate leaves
the capture endpoint (`0x86`) not delivering, and the driver carries a stack of
mitigations for it -- stream liveness polling, a watchdog, a direction-aware
corrective reset, and deferred recovery at the next capture open.

This document records what is actually measured, as of 2026-08-15. It exists
because the mitigations were built before the fault was characterized, and the
measurements below do not all support the assumptions they were built on.

The hardware numbers are still those of 2026-08-14. What changed on 2026-08-15
is the instrument: the 2026-08-14 comparison turned out to be uninterpretable
for reasons that are visible in the driver source, so `JT-RATE-001` was made
able to answer the question before any more hardware time was spent on it.

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
path vs reset path) *and* the duration per rate (1 s vs 4 s).

Worse than confounded: **the two arms do not measure the same quantity**, and
no experiment design can make them. Three things, all readable in `jockey3.c`,
were established on 2026-08-15 before spending any more hardware time.

### The playback-only arm counts one outage, not nineteen stalls

`jockey3_recover_capture_stream()` is reached only from `jockey3_pcm_prepare()`,
on a capture open. In a run that never opens capture, nothing ever recovers a
deferred stall -- so after the first one the capture stream stays dead for the
rest of the run, and `jockey3_wait_urb_stream_started()` re-logs `Capture URB
has stalled.` at *every subsequent change* because the stream never came back.

19 of 20 is therefore one stall re-detected nineteen times. It is not a
per-change incidence and cannot be compared against the 9 of 20 from a run
where each change starts from a stream a reset had restored. Only the
capture-open arm measures incidence at all.

### The stall message is emitted from four call sites

`jockey3_wait_urb_stream_started()` logs one identical string from
`hw_params()`, from `prepare()`, and twice inside
`jockey3_recover_capture_stream()` (after the lightweight URB restart, and
after the full reset). A single change that escalated all the way can
legitimately produce four of them. Any figure derived by counting occurrences
of that string -- including `stalls_capture` in `lib/rules.yaml` -- counts
neither stalls nor changes.

Only the one from `hw_params()` measures the rate change itself. The case now
resolves each occurrence to its call site by the context line that follows it,
and reports that one as `capture_stall_hw_params`.

### Which branch runs was decided by a race nobody was watching

The rate change happens inside the *first* `hw_params()` of the pair; the second
finds the rate already set and returns. So whether `capture_open` is 1 or 0 --
reset on the spot, or defer to the next capture open -- was decided by whether
`aplay` or `arecord` got there first. Both were spawned back to back, so a run
nominally testing the reset path could have spent an unknown fraction of its
changes on the deferred one, and neither the run record nor the log said which.

### What the experiment should be instead

Hold `seconds_per_rate` at 4 (below that the timing checks are not enforced and
the measurement length changes with the variable), and vary one thing at a time:

```sh
cd tests/hw
./runner.py --case JT-RATE-001 --unattended                       # baseline: reset branch
./runner.py --case JT-RATE-001 --unattended \
    --param rate_change_stream=playback                           # deferred branch
./runner.py --case JT-RATE-001 --unattended --param gap_seconds=3 # recovery time
```

`gap_seconds` idles between changes with nothing open, which is the right
instrument for "the device needs time between changes" -- `seconds_per_rate` is
not, because it moves the measurement window at the same time. There is a
concrete mechanism for a gap to matter: the reset `hw_params()` queues via
`usb_queue_reset_device()` is **not** waited for there (only
`jockey3_recover_capture_stream()` waits), so at zero gap change N+1 can begin
while change N's reset is still in flight. Consecutive changes are not
independent events.

The playback-only arm is still worth one run, but as a question of its own --
*does a deferred stall ever clear by itself?* -- not as a third point on the
same axis.

## What is instrumented now

`JT-RATE-001` was, until 2026-08-14, a playback-only test wearing a general
name: it never opened capture, so it never checked capture data and never
exercised the reset path -- the path that carries the risk. It now:

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

and, as of 2026-08-15:

- **fixes which branch is under test.** `rate_change_stream: capture |
  playback | race` orders the two opens and waits for the leading one to pass
  `hw_params` before starting the other, so `capture_open` is what the run says
  it is. `branch_change_*` records what each change actually did, so a change
  that drifted onto the other branch is visible rather than assumed away
- **separates the four call sites** that share the stall message, so
  `capture_stall_hw_params` is the incidence figure and
  `capture_stall_on_open` / `_after_urb_restart` / `_after_reset` are the
  recovery attempts
- **closes each change's log window when its streams close**, with a second
  marker. A reset completing after the streams are shut now lands in a
  "between changes" bucket instead of being charged to the change that runs
  next -- which, given that the reset is not waited for, is where a good deal
  of it was going
- **groups incidence by direction, by rate pair, and by clock family**
  (44k1 vs 48k), which is question 2 below, computed rather than eyeballed
- **adds `gap_seconds`**, idle time between changes with nothing open
- **measures the rate from the device's own clock instead of from a
  stopwatch on a process.** See below.

Arms are selected with `--param` rather than by editing `catalog.yaml`, and
`run.json` records the resolved parameters, so every run identifies its own
configuration.

### Measuring the rate from hw_ptr rather than from a stopwatch

The old effective-rate figure timed a whole `aplay` or `arecord` invocation:
frames delivered over wall clock from `Popen` to exit. That charges process
start-up, device open and every buffer in the path to the sample rate. The
result is

```
observed = rate / (1 + startup / duration)
```

which reads 10-17% low at four seconds even when the device is perfect. It is a
fixed additive offset, not a scaling error, so the only lever it offers is a
longer run: 5% needs ~10 s per rate, 1% needs ~50 s. That is where the
"observed rate deviates from the real rate" puzzle came from.

Shrinking the ALSA buffer is the wrong lever and was dropped rather than
deprioritized. It can only recover its own fill time -- 4096 frames at 48 kHz
is 85 ms against a start-up cost measured in hundreds -- and on a
`SNDRV_PCM_INFO_BATCH` device, where the pointer advances only once per
completed URB, a small buffer invites xruns that would corrupt the very
measurement.

What replaced it costs nothing and beats the 5% target by an order of
magnitude. `/proc/asound/cardN/pcmXc/sub0/status` carries `hw_ptr`, the total
frames the **hardware** has moved, and reading that file calls
`snd_pcm_update_hw_ptr()` while the stream is running, so the value is fresh as
of the read. Sample it every 20 ms alongside `CLOCK_MONOTONIC` and the slope is
the device's clock, with start-up, open and all buffering outside the window
rather than inside it. Buffer size does not enter at all: a buffer shifts
latency, not rate. No custom ALSA client is needed, and none is worth writing
for this question.

Two things are cut out of the window rather than averaged into it:

- **the settling time** -- 500 ms after the pointer first moves, per the
  estimate that prompted this
- **plateaus** -- stretches where the pointer stopped. This one is not an
  accuracy refinement but a correctness requirement: a 1.5 s stall inside a 4 s
  run drags the average down 37%, so a stall would be reported as a wrong
  clock, in the same bucket as a genuine rate error, on precisely the changes
  this case exists to study.

A backwards step is treated as a break, not a stall: `hw_ptr` restarts at zero
after a device reset, which on this driver is routine.

Three things fall out of it for free:

- **`startup_s_*`** -- `Popen` to the first frame the hardware moved. The
  excluded cost, measured rather than apportioned. This settles the
  startup-versus-buffering question with data.
- **stall onset and duration from the host**, at the 20 ms poll interval
  instead of the watchdog's one second, per change, with no dependence on the
  kernel log at all. For milestone 13 this may be worth more than the rate
  number.
- **a working `xruns` metric.** The old one sampled `alsa.xruns()` before and
  after the loop, both times with nothing open -- the status file reads
  `closed`, `pcm_status()` returns `{}`, and the difference of two absent
  values is zero. It has reported a clean run on every run ever recorded. The
  watchers sample during the stream, which fixes it, and it matters here
  because an xrun inside a measurement window invalidates that window's rate.

The tolerance is set at 5%, not at what the instrument can do. The question is
whether a rate change took effect; at much tighter bounds it would start
reporting the device's crystal.

One consequence worth noting: at 5% the 44100 <-> 48000 step (8.1%) is
resolvable, where at the old 20% it was not. The default sweep no longer has a
blind transition.

### Two things to check before believing the first run

- **`lead_stream_configure_timeouts` must be 0.** The ordering that
  `rate_change_stream` promises is achieved by waiting for the leading stream's
  `/proc/asound` status to leave `OPEN`. If that state string is not what this
  driver reports, every wait runs to its 5 s timeout, the ordering silently
  does not happen, and the branch labels are fiction. The metric says so; the
  stub in `selftest.py` cannot, because it is hardware-dependent by nature.
- **`branch_reset` is a precedence label, not a clean count.** On the capture
  arm, `hw_params` queues its reset without waiting, and the `prepare` that
  follows can find capture still dead and start the URB-restart ladder on top
  of a reset already in flight. Such a change is labelled `reset`. Read
  `escalated_total` and `prepare_capture_total` beside it.
- **Polling the status file runs `snd_pcm_update_hw_ptr()` more often than the
  URB completion handler alone would.** On a stalled capture that is harmless,
  since `avail` stays at zero. But if `arecord` starts failing *differently*
  now that the watchers exist, that is the cause and not a driver change.
  Read `pointer_quantum_max` from the first run rather than deriving it: it is
  the measurement's resolution floor, and at a few hundred frames over a
  window of seconds it should be well under 1% (0.23% at 512-frame
  granularity over 3.5 s, computed).
- **`pointer_plateau_changes_*` should be near zero on healthy changes.** The
  static run at the end of every trace -- the process has stopped, the
  substream has not closed yet -- is excluded from the window but deliberately
  not counted as a plateau, and is reported as `pointer_tail_hold_s_*`
  instead. If the plateau count comes back equal to the number of changes, that
  exclusion is not working and the count means nothing.
- **`xruns` is summed over two windows of different lengths.** The playback
  watcher stops when `aplay` exits, which on the capture arm is while `arecord`
  is still running. Read the per-direction `xruns_*` metrics, not the total.

The distinction between `nodata` and `silent` matters for where it sends an
investigation: no samples is the URB stream not restarting, all-zero samples
would be the converter not running. They were conflated at first, producing a
verdict that blamed the audio engine while playback was audibly fine.

### One thing that is not instrumented, and should be

**The reset duration is no longer observable from the log.** `lib/rules.yaml`
looks for `waited N ms for reset completion`, `selftest.py` has a fixture for
it, and `catalog.yaml` listed a `reset_wait_ms_histogram` metric. The driver
does not emit it. It once did: `775b70e` ("Make the usb_reset asynchronous")
added

```c
dev_dbg(&chip->intf0->dev, "%s waited %d ms for reset completion.\n", ...);
```

and `c8fff65` ("prepare for batching") dropped it. What is left in
`jockey3_wait_for_reset_completion()` is a `dev_dbg` on entry and a `dev_warn`
only on timeout, so the metric has been empty since. Checked against all five
trees (`alsa-jockey3`, `~/sound`, `~/sound-build`), which agree.

The catalog entry no longer claims the metric. Restoring the line would cost
one `dev_dbg` and would answer directly whether the ~334 ms in the code comment
still holds under the sweep -- worth doing, but **not in the same change as the
instrument rewrite**, or the first comparison is read against a driver that
moved underneath it.

## The number this is judged on

**`resets_per_change_pct` — how often a rate change costs a USB device reset.
It must trend to zero.** `JT-RATE-001` prints it at the end of every run and
`ledger.py` trends it per target; `JT-RATE-003` reports the same figure so a
short run and a ten-hour one stay comparable.

**Baseline, 2026-08-15, `x86_64-prod`, `rate_change_stream=capture`:**

| run | changes | stalls | resets | `resets_per_change_pct` |
|---|---|---|---|---|
| first | 20 | 6 | 6 | 30.0% |
| second | 20 | 9 | 9 | 45.0% |

Two runs of the same build and the same arm, 30% and 45%. The fault is
probabilistic and twenty changes is a small sample, so **a single run cannot
show an improvement of less than roughly a factor of two.** Quote the metric
with its change count, and use `iterations_per_run` (or `JT-RATE-003`) before
concluding that a driver change moved it.

What is stable across both runs is the shape, not the rate: every stall was on
a downward, family-crossing transition, and every one resolved.

**The arm is part of the number and must be quoted with it.** On the capture
arm every capture stall reaches `hw_params()` with `capture_open=1` and resets
on the spot, so stalls and resets are the same event by construction. On the
playback arm the same stall is deferred and met by a URB restart first, which
may well clear it — so that arm can report a much lower percentage with the
driver completely unchanged. Compare like with like, or a change of arm will
read as a fix.

A reset is an audible interruption to whatever was playing, so both places the
driver queues one count towards it: the on-the-spot reset in
`jockey3_pcm_hw_params()`, and the escalation in
`jockey3_recover_capture_stream()` after a URB restart failed. A URB restart
that *worked* is not counted — it is the outcome to want more of, and it is
reported beside the percentage so that "same stalls, handled more cheaply"
does not look identical to no progress at all.

That companion figure, `urb_restarts_that_avoided_a_reset`, is **structurally
zero on the capture arm** and says nothing there:
`jockey3_recover_capture_stream()` is only reached from `prepare()` on a
capture open, which the capture arm never takes. Zero means "not on this path",
not "the cheap path does not work". The playback arm is where it carries
information — one more reason to run it.

It is deliberately not part of the pass criterion. Any threshold above zero
would bless the fault, and a threshold at zero would fail every run until the
fault is gone. It is a trend line, not a gate.

It is computed from the run totals rather than from the per-change
attribution, and that is load-bearing: on this very run the markers failed and
every per-change figure read zero while the totals stayed correct. The one
number the driver is judged on must not be able to go quietly wrong.

## The 2026-08-15 run: the stall follows the downward transitions

First run on the rebuilt instrument. `x86_64-prod`, kernel
`7.2.0-rc5-alsa-prod+`, 20 changes, capture arm, 4 s per rate, no gap. Verdict
PASS: capture live on all 20, both clocks correct.

**The clock measurement works.** Worst error 0.10% on both directions against
the 5% bound, and the start-up it excludes measured 0.23-0.64 s on capture and
0.02-0.29 s on playback -- i.e. the old whole-invocation figure was carrying
6-16% of bias at four seconds, exactly as predicted. No plateaus, no xruns.

**Six of twenty changes stalled and reset**, and the on-screen output said
`0/20`. Both figures came from the same run because the per-change markers
never reached the kernel log: the labels contained `@`, which is outside the
charset `priv/jockey3-testctl` validates against, so every *start* marker was
rejected while every *end* marker (`#gapN`, no `@`) got through. With only end
markers, each window ran from one change's end to the next change's end -- so
every event was charged to the preceding change's gap, and the per-change table
read zero. `lib/kmsg.py` now sanitizes labels against the helper's own charset,
`selftest.py` checks the two against each other, and the case suppresses the
whole per-change table rather than printing zeros when markers are missing.

Reading the windows back with the one-change shift undone, the six stalls fall
on changes 4, 6, 10, 12, 16 and 20:

| transition | direction | family | stalled |
|---|---|---|---|
| 88200 -> 48000 | down | cross | **4/5** |
| 96000 -> 44100 | down | cross | **2/5** |
| 44100 -> 88200 | up | within | 0/5 |
| 48000 -> 96000 | up | within | 0/4 |

**Every stall is on a downward transition; no upward transition stalled.**
6/10 down against 0/9 up. That is the long-standing suspicion in
`implementation_plan.md`, measured for the first time.

It is one run and it does not separate two hypotheses. In this sweep both
downward steps cross between the 44k1 and 48k clock families and both upward
steps stay within one, so **direction and family crossing are perfectly
correlated** and a result that follows one follows the other. The earlier claim
in this document that the default sweep was balanced for the family question
was wrong. Breaking it needs a downward step within a family or an upward step
across one:

```sh
./runner.py --case JT-RATE-001 --unattended \
    --param sweep_order=as-given --param rates=[96000,48000,96000,44100]
```

which gives 96000->48000 down-within, 48000->96000 up-within, 96000->44100
down-cross and 44100->96000 up-cross. If the stall follows the downward steps
regardless of family, it is direction. If it follows the crossings, the clock
source is being reprogrammed and that is a different investigation.

Also worth noting from this run: all six stalls took the reset branch and all
six recovered -- `escalated` and `unrecovered` were zero, and capture came back
live on every change. The mitigations are working; what is unexplained is why
the fault is one-directional.

## 2026-08-16: the schematic explains what to rule out, not what to blame

Before more hardware time was spent, the service manual was read for the
clocking topology. The device has two independent clock domains fanned into
the Ploytec USB part through a 74HC00 NAND pair (oscillator select) and a
74HC74 flip-flop (divide-ratio select):

```
DSP oscillator   24.576  MHz  --> /512 = 48000 Hz   or  /256 = 96000 Hz
XTAL oscillator  22.5792 MHz  --> /512 = 44100 Hz   or  /256 = 88200 Hz
```

So "crosses 44k1/48k family" and "switches the NAND oscillator mux" are the
same event in hardware, and every downward step in the original interleaved
sweep (`88200->48000`, `96000->44100`) happens to do both at once, alongside
switching the flip-flop's divide ratio from /256 to /512. Three candidate
mechanisms -- oscillator mux glitch, divider resync, and "downward" as a pure
host-side artifact -- were confounded in one bit each. This motivated the
`sweep_order=as-given`, `rates=[96000,48000,96000,44100]` run proposed in the
previous session, which puts one down step within a clock family
(`96000->48000`, oscillator unchanged) and one down step across it
(`96000->44100`, oscillator changed), and the mirror image upward.

## 2026-08-16: divider direction confirmed, oscillator crossing ruled out

Four hardware runs, all `x86_64-prod`, build unchanged across the session:

| run | config | down stalls | up stalls |
|---|---|---|---|
| `20260816T204542Z-functional` | interleave, `[44100,48000,88200,96000]`, 25 iter | 23/50 | 0/49 |
| `20260816T210602Z-smoke` | as-given, `[96000,48000,96000,44100]`, 25 iter | 25/50 | 0/49 |
| `20260816T223625Z-smoke` | as-given, `[96000,48000,96000,44100]`, **60 iter** | 62/120 | 0/119 |
| `20260816T231358Z-smoke` | interleave, `[44100,48000,88200,96000]`, 25 iter (repeat) | 22/50 | 0/49 |

Direction alone predicts every stall across all four runs -- 132/220 down,
**0/366 pooled up** -- which was already the 08-15 finding. What the as-given
runs add is the split by whether the oscillator mux also switched:

| pair | oscillator | divider | n=25 (`210602`) | n=60 (`223625`) |
|---|---|---|---|---|
| `96000->48000` | unchanged (DSP) | /256->/512 | 15/25 (60%) | 33/60 (55%) |
| `96000->44100` | DSP->XTAL | /256->/512 | 10/25 (40%) | 29/60 (48%) |
| `48000->96000` | unchanged (DSP) | /512->/256 | 0/25 | 0/60 |
| `44100->96000` | XTAL->DSP | /512->/256 | 0/24 | 0/59 |

At n=25 the within-family cell looked worse than the cross-family one (60%
against 40%), which read like the oscillator switch was *helping*. At n=60
that gap collapsed to 55% against 48% -- well inside the ~6.5pp standard
error for n=60 at p~0.5, i.e. noise. **The 96000->48000 cell never touches
the NAND oscillator mux at all** (both rates run off the same 24.576 MHz
DSP oscillator, only the flip-flop's divide ratio changes) and it stalls at
least as often as the cell that does switch oscillators. That rules out an
oscillator-mux glitch as the mechanism: the fault tracks the flip-flop's
divide-ratio transition (`/256 -> /512`, i.e. toward the lower rate in
either family), not the NAND gate's source select. "Family crossing" was a
correlate of the real variable, not the variable itself.

One thing this cannot separate, because the hardware doesn't offer the
combination: every within-family step on this device is exactly 2:1
(44100<->88200, 48000<->96000), so "the divide ratio changes" and "the ratio
is not a power of two" stay tied together here. If a future finding turns on
this, it cannot be resolved from this device alone.

## 2026-08-16: the within-run drift did not reproduce

The 08-15 run showed the downward-stall rate climbing from 0% to 44% across
one 100-change run, bucketed by quartile. Two more full-length runs came back
flat, bucketing every change (not just downward ones) by quartile of the run:

| run | Q1 | Q2 | Q3 | Q4 |
|---|---|---|---|---|
| `20260816T204542Z-functional` (the original climbing run) | 2/25 | 5/25 | 5/25 | 11/25 |
| `20260816T210602Z-smoke` | 6/25 | 7/25 | 6/25 | 6/25 |
| `20260816T223625Z-smoke` | 15/60 | 19/60 | 14/60 | 14/60 |
| `20260816T231358Z-smoke` (repeat of the original config) | 5/25 | 7/25 | 4/25 | 6/25 |

Only the original run shows a trend; the other three, including a same-config
repeat of it, do not. Treat the drift as an unreplicated one-off, not a
mechanism to build an explanation around. It is not ruled out -- one run each
way is a coin flip's worth of evidence -- but it no longer belongs on the
priority list above the direction finding.

## 2026-08-16: a device wedge under sustained resets, distinct from the everyday stall

`20260816T213343Z-smoke` (as-given, 60 iterations, `gap_seconds=0`) did not
just fail statistically -- it wedged the device. Reconstructed from
`dmesg.txt`, change-by-change:

- Changes 1-100 ran the ordinary pattern: some fraction of downward changes
  stall at `hw_params()`, `usb_queue_reset_device()` fires, capture comes
  back. Ordinary so far.
- From roughly change 70 onward the reset frequency climbed -- by change 90
  through 100, nearly every downward change was resetting (changes 70, 74,
  76, 78, 80, 82, 84, 86, 88, 90, 92, 96, 98 all reset in that stretch).
- Immediately after change 100, all three endpoints started returning `-71`
  (`EPROTO`) simultaneously: `Playback URB error`, `Capture URB error`,
  `MIDI IN URB error`, each counting consecutive failures, each hitting
  `stopped after 8 consecutive URB errors` within about 100 ms of the first
  one. This is not the capture-only stall the mitigations target -- it took
  down playback and MIDI too, which is otherwise unaffected throughout every
  other run in the corpus.
- The device dropped off the bus (`USB disconnect, device number 125`) and
  re-enumerated -- but the *same* `-71` cascade recurred immediately on the
  freshly-enumerated device, twice more (device numbers 126, then 127),
  three full disconnect/re-enumeration cycles in about 30 seconds before the
  firmware finally responded normally again (device number 2).
- After that recovery, rate-change reliability was markedly worse than
  baseline for an extended stretch: a second internal attempt sequence
  (visible in the log as `change1` recurring with a fresh device) shows a
  reset on very nearly every change, well above the 44-55% baseline
  established above.

`usb_queue_reset_device()` -- a USB port reset -- did not clear this; only a
full physical disconnect/re-enumeration did, and it took three tries. This
looks like sustained back-to-back stalls pushing the device into a state the
driver's existing recovery path cannot reach, which is a materially different
(and more serious) failure than the one this document otherwise
characterizes. `gap_seconds=0` means the reset `hw_params()` queues is never
waited for before the next change can start (noted already in the 08-15
"what should be instrumented" section) -- consecutive unwaited resets
overlapping is the most concrete mechanism on hand for why a sustained run
would degrade the device rather than just repeatedly recovering it.

The 240-change target was not reached because of this; a rerun of the same
config (`20260816T223625Z-smoke`) completed cleanly and did not wedge. One
wedge in five full-length runs across the session -- not frequent, but not
explained, and it is the more consequential open question of the two now
that direction/family is resolved. It belongs with the existing open
findings on device wedging (see project memory), not folded into the
capture-stall mitigations that already handle the ordinary case.

## Open questions, in the order worth attacking

1. ~~Measure per-change incidence on each branch, one variable at a time.~~
   Done 2026-08-15/16.
2. ~~Direction or clock family?~~ **Resolved 2026-08-16: direction, specifically
   the flip-flop's divide-ratio transition from /256 to /512. Not the NAND
   oscillator mux** -- see above. Power-of-two ratio remains entangled with
   divider-ratio change and cannot be separated on this hardware.
3. **Does the device wedge under sustained resets, and does spacing changes
   out prevent it?** New 2026-08-16, see above. `gap_seconds=3` is the
   instrument already identified in the 08-15 section for a related question
   (whether an unwaited reset overlapping the next change matters) and is the
   most direct test: if the wedge does not recur with a gap, back-to-back
   resets are implicated; if it does, the cause is elsewhere (cumulative
   device-side state, e.g. a counter or buffer that does not reset per-cycle).
4. **What does the wire show during a failing rate change?** Still open --
   `capture_stalled_linux.txt` in `usb capture 2026/` was checked and is not
   usable: its rate-write burst ends on EP 0x05 (playback), which predates
   `474cca8` ("end the rate-write burst on the capture endpoint"). It reflects
   retired driver behavior, not the current sequence.
   `usb/parse_openvizsla.py --errors=0` against a fresh trace of a failing
   *downward* change on the current driver would show whether the device
   NAKs, stalls the endpoint, or goes quiet -- this is the expensive
   instrument and should follow the vendor comparison below, not precede it.
5. **Why does our sequence take 166-211 ms against macOS's 103-142 ms?**
   Unchanged from 08-15. Folded into the vendor comparison below.

## Next steps: characterize vendor up/down behavior before touching the driver

The temptation after "it's the divide-ratio direction" is to start changing
`ploytec_set_rate()` -- longer waits before a downward change, an extra poll,
a different burst shape going down versus up. Resist that until there is a
reference to change *toward*. `ploytec_set_rate()` already replicates the
macOS/Windows burst shape, endpoint order and quiet-window timings faithfully
(see its kernel-doc and `init_timing_comparison.md`), and neither vendor
driver stalls, ever, in the existing corpus -- including on downward changes.
So either the vendor sequence contains something direction-dependent that
was missed the first time through (`init_timing_comparison.md` was written
for the cold-boot fault and never specifically asked "does the vendor treat
downward and upward rate changes differently"), or it doesn't, and the
answer lies somewhere this document hasn't looked yet (host-side URB
resubmission timing after `SET_STATUS`, for instance, rather than the EP0
sequence itself).

**The plan, in order:**

1. **Re-run the existing macOS/Windows corpus through a direction lens.**
   Done -- `usb/classify_rate_transitions.py` (new, 2026-08-16) parses every
   `GET_RATE(ep=none)`/`SET_RATE` pair in `usb/openvizsla/*_events.txt` and
   classifies it by direction and by divide-ratio class (`within` /
   `cross` / `lateral`), reading the *old* rate from the query the vendor
   always issues rather than assuming it from context -- which matters,
   since `capture_macos_rate_change.txt` starts mid-session with no
   enumeration in view. Run it with `--summary` for counts, no arguments
   for the full per-event listing, `--csv` to export.

   The corpus turned out thinner than the previous pass through it assumed.
   `capture_macos_rate_change` has **7** transitions, not the 5 the pasted
   LLM analysis in `capture_macos_rate_change_analysis.md` describes -- it
   silently skips two events and mis-transcribes a third (claims event 7 is
   `96000->48000`; the trace's own `GET_RATE` says its old rate was 44100).
   That is the concrete instance of the caution already on record about that
   file: it is a lead, not a source. Re-deriving from the parsed events
   instead of the prose changed the answer, immediately, on the first check.

   What actually exists, corpus-wide (macOS + Windows, `--summary` output):

   | direction | divider_class | n | pairs |
   |---|---|---|---|
   | up | lateral | 7 | `44100->48000`, `88200->96000` |
   | up | within | **1** | `48000->96000` (Windows only) |
   | up | cross | 18 | `44100->96000` (x16), `48000->88200` (x2) |
   | down | lateral | 1 | `48000->44100` (macOS only) |
   | down | within | **0** | -- |
   | down | cross | 3 | `96000->44100` (1 macOS + 2 Windows) |

   **`down`/`within` -- the exact class that stalls 55-60% of the time on
   this driver (`96000->48000` and its mirror `88200->44100`) -- has zero
   examples on either platform in the entire corpus.** Every claim this
   document could make about "what the vendor does differently going down"
   currently rests on `down`/`cross`, and on one specific pair
   (`96000->44100`) at that; `88200->48000`, the other `down`/`cross` pair,
   also has zero examples. This is a real gap, not a case of the existing
   traces being under-analyzed, and it means the corpus cannot currently
   answer the direction question at all for the stall's own strongest
   cell -- see "Captures needed" below before drawing a conclusion from
   what exists today.
2. **Compare, per direction, everything the previous macOS-only comparison in
   `capture_macos_rate_change_analysis.md` asserted but never checked against
   Windows or against direction:** burst length (5-7 writes, stated as varying
   "within a single platform" -- does it vary *with direction*?), the
   position and width of the ~10 ms and ~50 ms quiet windows, and the
   `resume_out_ms` / `resume_in_ms` figures from
   `rate_change_stream_timing.py`. That file is worth naming directly: it
   reads as an LLM chat transcript pasted in wholesale, mixes real trace
   excerpts with unverified speculation ("almost feels like a hack to cope
   with obscure firmware flaws"), and its pseudo-code does not match the
   actual event sequence in its own trace closely enough to trust without
   re-deriving. Treat its data as a lead, not a source -- redo the
   classification from the parsed events, the same standard the rest of this
   document holds itself to.
3. **Only if a direction-dependent asymmetry turns up in the vendor sequence
   itself** does this motivate a specific, targeted change to
   `ploytec_set_rate()` -- e.g. a different wait or an extra status poll on
   the /256->/512 transition specifically. If no asymmetry turns up, that is
   also a result: it would mean the vendor drivers get away with an
   identical EP0 sequence in both directions and something else (host URB
   timing, buffer state left over from the previous rate, or a firmware race
   that is simply less likely to lose when driven from a different USB host
   controller) accounts for the difference, which points the investigation
   at `jockey3.c`'s URB resubmission path after a rate change rather than at
   `ploytec_proto.c`'s EP0 sequence.
4. **Any change that does get made is validated the same way this session's
   findings were: `JT-RATE-001` with `sweep_order=as-given`, both cells of a
   direction, before/after, at n>=60 per cell** -- n=25 was not enough to
   trust the 60/40 split this session, and a real fix has to clear the same
   bar the noise did.

The wedge investigation (`gap_seconds=3`) and the vendor comparison are
independent and can proceed in either order; the vendor comparison is pure
analysis of already-captured traces and needs no hardware time, so it is the
better use of time between hardware sessions.

## Captures needed

OpenVizsla capture is a manual, one-trace-at-a-time process and the raw
files are large, so this is deliberately a short list, not "capture
everything and see." Each entry exists because `classify_rate_transitions.py`
found the corpus has zero examples of it, not as a hedge.

**Priority 1 -- blocking, currently zero examples anywhere:**

- **macOS: `96000<->48000`, cycled back and forth 4-6 times in one capture.**
  This is `down`/`within` and its mirror `up`/`within` in the same session --
  the class that stalls 55-60% of the time on this driver and has no vendor
  trace at all today.
- **Windows: the same pair, the same way.** Windows' only `up`/`within`
  example (`48000->96000`, once) has no downward companion either.

**Priority 2 -- thin, one pair covers the whole `down`/`cross` class today:**

- **One platform, `88200<->96000<->44100<->48000` cycled a few times**, or
  more simply `88200<->48000` back and forth 4-6 times if the capture can be
  targeted that precisely. This is the *other* `down`/`cross` pair --
  `96000->44100` has 3 samples, `88200->48000` has none -- and checks whether
  the vendor sequence (if it turns out to differ from the up-going one at
  all) does so consistently across both `down`/`cross` pairs or is specific
  to one. Do this only after priority 1 is in and has been looked at; if
  priority 1 already shows no direction asymmetry, this pair is unlikely to
  either, and is not worth the trace size on its own.

**Not requested -- existing coverage is enough:** `lateral` (7 up, 1 down)
and the well-covered `up`/`cross` pair (`44100->96000`, n=16) do not need
more. `48000<->44100` and `88200<->96000` are the two `lateral` pairs and
the divide-ratio hypothesis predicts they never stall regardless of
direction -- worth a hardware confirmation via `JT-RATE-001` eventually
(untested combination: neither the interleaved nor the as-given sweep so far
has isolated a lateral-only transition), but that is a hardware question,
not a reason to spend more OpenVizsla time on the vendor side.

**Sizing rationale:** JT-RATE-001 needs n>=60 per cell because the fault it
measures is probabilistic. A vendor EP0 sequence is not -- the existing
corpus already shows burst count and quiet-window width stable to under 4%
across 58 sequences (`init_timing_comparison.md`). 4-6 repeats per pair is
enough to see whether the sequence structure depends on direction at all; if
it does, that structure will show up on the first or second repeat, not the
fortieth.

**Keeping the capture small:** dwell only as long as it takes to see the
handshake complete and confirm streaming resumed -- a few seconds per rate,
not sustained playback. `capture_macos_rate_change.txt`'s own origin note
describes stripping "the many repetitive 512 byte audio in/out packets"
after the fact; avoiding recording minutes of steady-state audio in the
first place is cheaper than stripping it afterward. Run every new capture
through the existing pipeline (`parse_openvizsla.py` -> `extract_events.py`)
to produce the `*_events.txt` `classify_rate_transitions.py` reads, and give
it a metadata sidecar via `make_trace_sidecar.py` -- host, OS and driver
version, and the objective (which pair/direction this capture exists to
fill), same as every other trace in the corpus.

## Reproducing

```sh
cd tests/hw && ./runner.py --case JT-RATE-001 --unattended     # ~3.5 min
python3 re/usb/rate_change_stream_timing.py                    # vendor timings
python3 re/usb/classify_rate_transitions.py --summary          # vendor direction/divider coverage
```

The defaults are the reset-branch arm: capture open, 4 s per rate, no gap. Use
`--param` for the others (see above). `./selftest.py` covers the stall
attribution and the parameter parsing without hardware.

Both vendor-side scripts read the checked-in `openvizsla/*_events.txt` and
`*_parsed.txt`, so neither needs hardware or a fresh capture to run.
