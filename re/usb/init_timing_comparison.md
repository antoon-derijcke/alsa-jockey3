# Initialization and Rate-Change Timing: macOS vs Windows vs Linux

Motivation: this driver's initialization is not reliably successful. It
succeeds every time on a debug kernel with dynamic debug printing enabled and
fails intermittently on a production kernel without it. Since the dynamic
debug output changes nothing except how long each step takes, that behavior
points at the timing of the initialization sequence rather than its content.

This document compares what the vendor drivers do on the wire against what
this driver does, using the captures in `usb capture 2026/` processed through
`parse_openvizsla.py` -> `extract_events.py`.

**Working assumption**, stated because it shapes every conclusion below: the
Windows and macOS drivers are correct. Where they agree with each other and
disagree with us, they are taken as the reference.

## Corpus

Only captures containing EP0 traffic can say anything here, and several of the
2026 captures turn out to be stream-only:

| Capture | Control-plane events |
|---|---|
| `capture_macos_44k_poweron` | 1 enumeration, **1 cold init** |
| `capture_macos_rate_change` | **7 warm rate changes** |
| `capture_2026-08-13_macos_poweron` | 6 enumerations, **6 cold inits** at 44.1 kHz |
| `capture_2026-08-13_macos_poweron_96k` | 6 enumerations, **6 cold inits**, 6 rate changes to 96 kHz |
| `capture_2026-08-13_macos_usb_disconnect_96k` | 5 enumerations, **5 cold inits**, 4 rate changes to 96 kHz |
| `capture_2026-08-13_macos_poweron_noapp` | 6 enumerations, **6 cold inits**, 6 rate changes, **no application running** |
| `capture_macos_96k_512` | none -- no EP0 traffic captured |
| `capture_macos_96k_to_44k1` | none -- no EP0 traffic captured |
| `capture_macos_44k1_{128,512,1024}` | none -- no SETUP tokens in the raw trace |
| `capture_win_power-on_samplerate` | **1 cold init**, 6 warm rate changes |
| `capture_win_power_on_off_cycle` | **4 cold inits** |
| `capture_linux` | 1 init (see caveat) |
| `capture_stalled_linux` | 8 init+rate sequences |
| `capture_linux_44k1`, `capture_linux_88k` | none -- no SETUP tokens |

Vendor sample sizes: macOS cold init **n=24**, macOS rate change **n=23**,
Windows cold init **n=5**, Windows warm rate change **n=6**. Fifty-eight
vendor sequences in total.

The four `2026-08-13` captures were taken specifically to close the macOS
cold-init gap, which stood at n=1 when this document was first written. They
also settle three questions the earlier corpus could not: whether the quiet
window is rate-dependent, whether the device retains its rate across a USB
disconnect, and whether the vendor driver streams without an application.

**Caveat on the Linux captures.** The driver revision that produced
`capture_linux` and `capture_stalled_linux` was not recorded, so every Linux
row below is provisional. Future captures must record the module GNU build-id
from `/sys/module/snd_reloop_jockey3/notes/`, which is the only reliable
identity for a loaded module here.

## Finding 1: the rate-write burst ends on the wrong endpoint

This is the hardest result in the data: an invariant that holds in all 58
vendor sequences, at every rate, on both platforms, and which we violate.

Both vendors end the `SET_RATE` burst on **EP 0x86** and then read the rate
back from **EP 0x86**.

| | Burst | Readback from |
|---|---|---|
| macOS cold init (n=24) | `86 05 86 05 86`, no pause | `0x86` |
| macOS rate change (n=23) | `86 \| 86 05 86 05 86` | `0x86` |
| Windows cold init | `86 05 \| 86 05 86` | `0x86` |
| Windows, samplerate capture | `86 05 \| 86 05 86 05 86` | `0x86` |
| **this driver** | `86 \| 86 05 86 05 86 05` | **`0x05`** |

(`\|` marks the mid-burst pause -- see finding 6.)

The write *count* is plainly not load-bearing: it varies from 5 to 7 within a
single platform, and even within a single capture. The **parity** may well be.
We are the only implementation that leaves `0x05` as the last endpoint
written, and the only one that verifies against `0x05` rather than `0x86`.

Given that the known rate-change failure mode is the *capture* endpoint
(`0x86`) failing to restart -- `implementation_plan.md` milestone 13 -- an
ordering difference that specifically concerns `0x86` deserves attention
beyond its size.

To be clear about what is *not* broken: in `capture_stalled_linux` the
`GET_RATE` from `0x05` does return the rate just programmed, so the
verification in `ploytec_set_rate()` is reading real data and its "Rate
mismatch!" warning is not silently defective. The divergence is about which
endpoint is written last, not about whether the readback works.

The change is small: drop the trailing `0x05` write from the loop in
`ploytec_set_rate()`, and give `ploytec_get_rate()` an endpoint argument so
the readback can target `0x86`.

Note that at probe this burst does not run at all -- see finding 7, which is
the more serious problem.

## Finding 2: the vendors leave a ~50 ms quiet window; we never do

Every vendor sequence contains at least one window of very close to 50 ms in
which the host sends nothing at all. Across 58 sequences the value lands
between 50.2 ms and 52.0 ms -- a spread under 4%.

**It is not rate-dependent.** That was the open question the 96 kHz captures
were taken to settle, and the answer is clean: 50.227 ms in a 44.1 kHz cold
init against 51.076 ms in a 96 kHz one, and 51.177 / 50.211 ms in a 96 kHz
rate change. A fixed 50 ms in the driver is correct at every supported rate;
there is nothing to scale.

| Sequence | n | Quiet window | Position |
|---|---|---|---|
| Windows cold init (power cycle) | 4 | 50.863 - 51.372 ms | after `SET_INTERFACE(1, alt 1)` |
| Windows, samplerate capture | 7 | 50.316 - 51.956 ms | after `SET_INTERFACE(1, alt 1)` |
| macOS rate change | 7 | 50.225 - 51.149 ms | before the first `SET_RATE` |
| macOS rate change | 7 | 50.210 - 50.893 ms | after the `GET_RATE` readback |
| macOS cold init, 44.1 kHz | 6 | ~50.2 ms | after the `GET_RATE` readback |
| macOS cold init, 96 kHz | 6 | ~51.1 ms | after the `GET_RATE` readback |
| macOS rate change to 96 kHz | 16 | 50.2 - 51.2 ms | both positions |

This driver has no such window anywhere. Its largest inter-transfer gap is the
deliberate ~11 ms inside the `SET_RATE` burst; every other step follows the
previous one within about 5 ms:

```
   114.988 |     1.505 | SET_INTERFACE intf=1 alt=1
   115.627 |     0.615 | CLEAR_FEATURE(ENDPOINT_HALT) ep=0x86
   116.137 |     0.486 | CLEAR_FEATURE(ENDPOINT_HALT) ep=0x05
   116.567 |     0.406 | CLEAR_FEATURE(ENDPOINT_HALT) ep=0x83
   117.029 |     0.433 | GET_STATUS len=1 -> 32
```

Both vendors wait ~50 ms somewhere in that span. We wait 2 ms.

### The window is genuine silence, not retries

`parse_openvizsla.py` discards NAK and STALL transactions, so a window full of
rejected transfers and a window of true silence look identical in the parsed
output. That distinction decides whether the vendor *waits* or *retries until
accepted*, which are different fixes, so it was checked against the raw trace.

Between the completion of `GET_RATE` at 10.832055 and the `SETUP` of the first
`SET_RATE` at 10.883037 in `capture_macos_rate_change.txt`, the wire carries
**nothing** -- no tokens, no NAKs, no PINGs, no bulk traffic. The same holds
for the Windows cold init between 9.409201 and 9.460573 in
`capture_win_power_on_off_cycle.txt`. The host is not polling. It is idle.

### It is a fixed sleep, not a periodic worker tick

The window's position varies -- Windows anchors it after the interface reaches
alt 1, macOS anchors it around the rate write, and macOS warm rate changes
have **two**. A varying position is also what a ~20 Hz periodic worker would
produce, with whichever step misses the tick showing up as ~50 ms, so the two
readings were separated by checking the phase of the window start against a
capture-wide clock.

Across the 7 macOS warm rate changes the window starts at phases of 0.0, 37.7,
0.7, 7.5, 43.5, 40.6 and 5.6 ms modulo 50 ms -- scattered across the whole
interval with no common phase. A periodic tick would cluster. These are fixed
sleeps that begin whenever the previous step finished.

## Finding 3: cold init and rate change are two different sequences

The 2026-08-13 captures make this unmistakable, and it is the finding with the
most direct consequence for our code. macOS uses two structurally distinct
sequences, and we use one.

| | macOS cold init | macOS rate change |
|---|---|---|
| Transfers | 16 | 18 |
| Interface handling | `SET_INTERFACE` to alt 1 only | bounce: alt 0 on both, then alt 1 on both |
| Preceded by | `SET_CONFIGURATION` | nothing |
| Lead-in before burst | ~14 ms | **~51 ms** |
| Burst | 5 writes, contiguous | 1 write, **~11 ms**, then 5 |
| Quiet windows | one, before the final `GET_STATUS` | two |

The cold init always programs **44100 Hz**, whatever the application is
configured for. When Traktor was set to 96 kHz, every power-on produced a
44.1 kHz cold init followed about half a second later by a *separate* rate
change to 96 kHz. The initialization is not parameterized by the desired rate
at all.

We have only one path: `ploytec_initialize_device()` followed by
`ploytec_set_rate()`, so our initialization uses the *rate-change* burst shape
-- one write, a 10 ms sleep, then a loop -- where macOS uses five contiguous
writes with a 14 ms lead-in and no mid-burst pause. We also perform the alt 0
bounce during initialization, which macOS does only on rate changes.

## Finding 4: no application is required, which validates the free-running URBs

`capture_2026-08-13_macos_poweron_noapp` was taken with nothing open on the
Mac. macOS still enumerated the device, ran the full cold init, programmed the
rate -- including the change to 96 kHz -- and then streamed continuously:
141524 packets on EP 0x05 over 38.4 s, about 3700 per second, with gaps only
while the device was physically powered off.

This driver keeps its URBs submitted for the device's lifetime rather than
starting and stopping them around PCM open and close. That was reasoned from
the MIDI multiplexing -- MIDI OUT rides in byte 480 of every playback packet,
so the stream cannot stop while MIDI is expected to work. It now has direct
vendor evidence behind it: the reference implementation streams with no
application in the picture at all.

## Finding 5: the device resets its rate on USB re-enumeration

`capture_2026-08-13_macos_usb_disconnect_96k` was taken to test whether the
device retains its configured rate when the USB cable is unplugged and
replugged, since that does not power-cycle it -- the Jockey 3 is self-powered
(`bmAttributes 0xc0`).

**It does not.** Every `GET_RATE wIndex=0` after a replug reads 44100 Hz, in
cycles where the device had been running at 96 kHz moments earlier.

After a power cycle that reading is unremarkable -- 44100 Hz is evidently the
power-on default. The unplug case is the informative one: the device kept its
power the whole time and still came back at 44100 Hz, so the reset is
triggered by USB re-enumeration rather than by loss of power.

That reading is genuinely live rather than a constant, which the older
`capture_macos_rate_change` establishes: there the same request tracks the
programmed rate through 44100, 48000, 44100, 48000, 88200, 96000 and 44100.

The status byte tells the same story. The first `GET_STATUS` of a cold init
reads **0x12** after a replug, exactly as it does after a power cycle, with
the streaming bit clear. On both paths the device presents itself to the host
as freshly initialized.

The likely explanation is that the firmware runs its own initialization when
USB is disconnected. It is not a full reset: the control surface LED pattern
is unchanged across an unplug, which it would not be after a genuine reset.

What the trace cannot distinguish is *when* the rate goes back to 44100 --
at the disconnect, or when the host sends `SET_CONFIGURATION` on the way back
up. Nothing is on the wire while the cable is out, and by the time any host
reads the rate it has already reconfigured the device. The LED observation is
what separates "partial firmware re-init" from "full reset", and that is an
out-of-band observation, not something in the capture.

Two consequences. A driver may not assume a rate survives re-enumeration, so
the rate must be reprogrammed on every probe -- which we do. And the vendors
issue this initial read with `wIndex = 0x0000`, a form our
`ploytec_get_rate()` cannot express; see finding 7.

## Finding 6: the mid-burst pause is real and ours is about right

Every implementation splits the rate writes with a pause:

| | Mid-burst pause |
|---|---|
| macOS warm rate change (n=7) | 10.468 - 11.175 ms |
| macOS cold init (n=1) | 13.444 ms |
| Windows (n=11) | 6.252 - 22.861 ms |
| this driver | 11.075 ms (`usleep_range(10000, 11000)`) |

Ours sits inside the observed vendor range. This one is fine, and the comment
in `ploytec_set_rate()` attributing it to macOS behavior is accurate.

## Finding 7: at probe we skip the rate programming altogether

This one is not visible on our wire as a *difference in* a sequence -- it is a
sequence that never happens. It lives in our control flow, and the vendor
corpus is what made it visible.

`jockey3_set_rate()` reads the hardware rate and only calls
`ploytec_set_rate()` if it differs from the requested one:

```c
ret = ploytec_get_rate(chip->intf0, chip->xfer_buf, &current_hw_rate);
...
if (current_hw_rate != rate) {
        ret = ploytec_set_rate(chip->intf0, chip->xfer_buf, rate);
```

`jockey3_initialize()` requests 44100 Hz at probe, and 44100 Hz is the
device's power-on default -- established by every macOS cold init in the
corpus, all of which read exactly that before programming anything. So on a
cold power-on the condition is false and **the entire rate burst is skipped**.
Our initialization is `initialize_device` -> `get_rate` -> `start_streaming`,
with no `SET_RATE` in it at all.

All 24 macOS cold inits program the rate unconditionally, writing 44100 Hz to
a device already reporting 44100 Hz, and only then read it back and set the
status. Windows does the same. No vendor sequence in the corpus, on either
platform, skips the burst.

If those writes are what arms the endpoints rather than merely setting a
frequency, this is not a timing bug at all but a missing step, and the
intermittency is in whatever sometimes makes the device work without it.

Two things make this the strongest candidate for the initialization failure:

- It is the only divergence that removes work entirely rather than
  reordering or re-timing it.
- `jockey3_initialize()` already retries the whole sequence ten times with
  50-100 ms between attempts. A device that merely needed a settling period
  would be very likely to succeed on the second attempt; ten consecutive
  failures over about a second fit an absent step far better than a missed
  window.

The fix is to program the rate unconditionally at probe, as both vendors do.
The `current_hw_rate != rate` guard is reasonable for a later rate *change*,
but initialization is not a rate change -- finding 3.

## Finding 8: smaller divergences

- **`GET_RATE` wIndex.** Both vendors issue the *initial* rate read with
  `wIndex = 0x0000` and the *readback* with `wIndex = 0x0086`. We use
  `wIndex = 0x0005` for both, because `ploytec_get_rate()` hardcodes
  `PLOYTEC_EP_NUM_PCM_OUT` and cannot express either vendor form.

- **The alt 0 bounce.** We always drive both interfaces to alt 0 and then back
  to alt 1. Windows never does this -- it goes straight to alt 1 on both cold
  init and rate change. macOS does it only on rate changes, never on cold
  init, and in the opposite order to ours: macOS deactivates interface 1 first
  (`intf=1 alt=0, intf=0 alt=0, intf=0 alt=1, intf=1 alt=1`), we deactivate
  interface 0 first.

- **The 3-5 ms sleep between alt 0 and alt 1** in `ploytec_initialize_device()`
  has no counterpart in either vendor: macOS moves from alt 0 to alt 1 in
  about 0.5 ms. Whatever it was added for, it does not come from these traces.

- **`CLEAR_FEATURE(ENDPOINT_HALT)` placement.** macOS clears all three
  endpoints *before* reading status, and we match that. Windows clears only
  `0x86` and `0x05`, and does it several hundred milliseconds *after*
  `SET_STATUS`.

## What this evidence cannot settle

**The missing 50 ms window is not sufficient on its own to cause failure.**
`capture_linux` shows an initialization that omits the window entirely -- 2 ms
where the vendors leave 50 -- and still ends with `GET_STATUS -> 0x32`, the
streaming bit set. It worked. Both Linux captures available are, as far as
anyone knows, *successful* inits from unknown builds. So finding 2 identifies
a real divergence and a plausible mechanism, not a demonstrated cause.

Two hypotheses fit the debug-versus-production symptom, and the vendor traces
do not distinguish them:

1. The device needs a settling period we do not reliably give it.
2. The driver has an internal race that the extra latency of dynamic debug
   printing happens to paper over.

Only a capture of a **failing** initialization on a production kernel, paired
with a successful one from the same driver build, separates these.

Equally, the vendor traces cannot give the *tolerance*. They show what the
vendor chose, never what the device requires; a 50 ms sleep is consistent with
a device needing 45 ms and with one needing 2 ms. The usable minimum can only
come from bisecting the delay in our own driver against repeated init attempts
on a production kernel.

## Do we need more vendor traces?

**No.** This was an open question when the corpus held 18 sequences and a
single macOS cold init. The 2026-08-13 captures took it to 58 sequences and 24
macOS cold inits, and every number they added fell inside the range already
established. The delays are settled, and the two questions the numbers alone
could not answer -- rate dependence and the streaming-without-an-application
assumption -- are settled too.

Two scenarios were considered and ruled out rather than left open.

**Stream stop / application close.** Because the vendor driver brings the
device up and keeps the stream flowing as soon as the OS loads it, with no
application involved, closing an application leaves the device in the same
state as never having opened one -- and that state is already captured, in
`capture_2026-08-13_macos_poweron_noapp`. The transition is not expected to
hold surprises, and the question we actually care about at close is whether
*our* driver tears down cleanly, which is a hardware-in-the-loop test rather
than a capture.

**Suspend/resume.** What matters here is that this driver's URBs are running
correctly again after a resume. How macOS or Windows handle suspend does not
bear on that, so a vendor trace would not inform the fix. This belongs in the
test suite too.

With those set aside, the vendor-side capture work is essentially complete.

**The blocking artifact is on the Linux side**: a failing init and a passing
init captured back to back on a production kernel, same driver build, with the
module build-id recorded. Nothing in the vendor corpus substitutes for it.

## Method note

`extract_events.py --event-gap` defaults to 250 ms. Windows leaves its
trailing `CLEAR_FEATURE` pair between about 250 ms and 900 ms after
`SET_STATUS`, which straddles that threshold: in
`capture_win_power-on_samplerate` one event absorbs the pair (an internal gap
of 249.781 ms), while in `capture_win_power_on_off_cycle` they consistently
split off as separate `control` events. Raising the threshold to 500 ms does
not fix this -- it just moves which captures land on which side.

This affects the reported *span* of Windows events and nothing else. Every gap
the findings above rest on is measured within the rate sequence, well before
the trailing `CLEAR_FEATURE`s.

## Reproducing

```sh
cd re/usb
python3 extract_events.py <capture>_parsed.txt --format summary
python3 extract_events.py <capture>_parsed.txt -o <capture>_events.txt
```

Or straight from a raw trace, without writing the intermediate:

```sh
python3 parse_openvizsla.py <capture>.txt - | python3 extract_events.py - --format summary
```

The extracted event files for every capture in the corpus are checked in
alongside the traces in `openvizsla/`.
