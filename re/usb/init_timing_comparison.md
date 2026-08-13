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
| `capture_macos_96k_512` | none -- no EP0 traffic captured |
| `capture_macos_96k_to_44k1` | none -- no EP0 traffic captured |
| `capture_macos_44k1_{128,512,1024}` | none -- no SETUP tokens in the raw trace |
| `capture_win_power-on_samplerate` | **1 cold init**, 6 warm rate changes |
| `capture_win_power_on_off_cycle` | **4 cold inits** |
| `capture_linux` | 1 init (see caveat) |
| `capture_stalled_linux` | 8 init+rate sequences |
| `capture_linux_44k1`, `capture_linux_88k` | none -- no SETUP tokens |

Vendor sample sizes: macOS cold init **n=1**, macOS warm rate change **n=7**,
Windows cold init **n=5**, Windows warm rate change **n=6**. Eighteen vendor
sequences in total.

**Caveat on the Linux captures.** The driver revision that produced
`capture_linux` and `capture_stalled_linux` was not recorded, so every Linux
row below is provisional. Future captures must record the module GNU build-id
from `/sys/module/snd_reloop_jockey3/notes/`, which is the only reliable
identity for a loaded module here.

## Finding 1: the rate-write burst ends on the wrong endpoint

This is the hardest result in the data: an invariant that holds in all 18
vendor sequences, at every rate, on both platforms, and which we violate.

Both vendors end the `SET_RATE` burst on **EP 0x86** and then read the rate
back from **EP 0x86**.

| | Burst | Readback from |
|---|---|---|
| macOS cold init | `86 05 \| 86 05 86` | `0x86` |
| macOS warm rate change | `86 \| 86 05 86 05 86` | `0x86` |
| Windows cold init | `86 05 \| 86 05 86` | `0x86` |
| Windows, samplerate capture | `86 05 \| 86 05 86 05 86` | `0x86` |
| **this driver** | `86 \| 86 05 86 05 86 05` | **`0x05`** |

(`\|` marks the mid-burst pause -- see finding 3.)

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

## Finding 2: the vendors leave a ~50 ms quiet window; we never do

Every vendor sequence contains at least one window of very close to 50 ms in
which the host sends nothing at all. Across 18 sequences the value lands
between 50.2 ms and 52.0 ms -- a spread under 4%.

| Sequence | n | Quiet window | Position |
|---|---|---|---|
| Windows cold init (power cycle) | 4 | 50.863 - 51.372 ms | after `SET_INTERFACE(1, alt 1)` |
| Windows, samplerate capture | 7 | 50.316 - 51.956 ms | after `SET_INTERFACE(1, alt 1)` |
| macOS warm rate change | 7 | 50.225 - 51.149 ms | before the first `SET_RATE` |
| macOS warm rate change | 7 | 50.210 - 50.893 ms | after the `GET_RATE` readback |
| macOS cold init | 1 | 51.112 ms | after the `GET_RATE` readback |

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

## Finding 3: the mid-burst pause is real and ours is about right

Every implementation splits the rate writes with a pause:

| | Mid-burst pause |
|---|---|
| macOS warm rate change (n=7) | 10.468 - 11.175 ms |
| macOS cold init (n=1) | 13.444 ms |
| Windows (n=11) | 6.252 - 22.861 ms |
| this driver | 11.075 ms (`usleep_range(10000, 11000)`) |

Ours sits inside the observed vendor range. This one is fine, and the comment
in `ploytec_set_rate()` attributing it to macOS behavior is accurate.

## Finding 4: smaller divergences

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

**For the delay values, no.** Eighteen sequences with under 4% spread is not
noise-limited; more captures would refine a number that is already clearly
50 ms. The one thin cell is macOS cold init at n=1, which one more macOS
power-on capture would close -- worth having, not blocking.

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
