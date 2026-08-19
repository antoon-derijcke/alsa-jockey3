# Playback URB stall with no recovery path ("the wedge")

Log of every observed occurrence of a playback URB stream that stalls and
never recovers on its own. Distinct from the rate-change capture stall
documented in `rate_change_stall.md` (resolved 2026-08-17, cause identified
and fixed): this one hits **playback**, is not triggered by a rate change,
and the driver has no self-healing path for it at all — see the "gap" section
below. Kept separate per project memory (`jockey3-open-findings`, finding #3):
"It belongs with the existing open findings on device wedging, not folded
into the capture-stall mitigations that already handle the ordinary case."

Two occurrences so far. Too few to draw conclusions about trigger or
frequency; this file exists so a third occurrence has something to compare
against instead of starting from scratch.

## The gap

`jockey3_pcm_prepare()` checks capture liveness only
(`needs_recovery = substream->stream == SNDRV_PCM_STREAM_CAPTURE && !alive(&chip->capture)`)
and calls `jockey3_recover_capture_stream()` (URB restart → full USB reset →
give up) when it finds a dead ring. Playback has no equivalent: nothing ever
asks whether the playback ring is alive before or during use. Since MIDI OUT
rides in byte 480 of every playback packet and the playback URBs run for the
device's whole lifetime rather than around PCM open/close (see `jockey3.c`
`DOC:` blocks), a dead playback ring means MIDI OUT is silently gone until
something outside the driver (a full disconnect/replug, or opening capture
which happens to reset the whole device) clears it.

`jockey3_watchdog_work()` *detects* the stall (that machinery is solid — see
the heartbeat-capping fix below) but is deliberately detection-only; the
comment on it says outright that "a stall that survives this long means
nothing is dealing with it" for exactly this case.

Mitigation sketched in project memory, not yet implemented: extend
`jockey3_pcm_prepare()`'s `needs_recovery` check to be direction-agnostic so
a playback open can also discover and recover a dead ring. Two caveats noted
there: don't copy `jockey3_recover_capture_stream()` verbatim (it is
capture-specific in name, logging and escalation — needs a direction-agnostic
version); and the 1 ms liveness rule cannot be applied to MIDI IN (bulk EP
`0x83` only completes when the device sends something, so idle MIDI IN would
look like a false stall).

## Occurrences

### 2026-08-11 — first occurrence, x86_64, found by hand

GitHub issue #26. Found during manual `JT-MIDI-001`/`JT-MIDI-002` runs, not
under the automated harness (which didn't cover this yet). Full writeup in
project memory `jockey3-open-findings` finding #3; summary:

- All three endpoints (playback `0x05`, capture `0x86`, MIDI IN `0x83`) died
  together — every `usb_submit_urb()` returned `-2` (`ENOENT`), i.e.
  `usb_pipe_endpoint()` found no endpoint there while the driver still
  believed it was bound. EP0 control transfers timed out with `-110`.
- Earliest symptom: `rawmidi drain error (avail = 4090, buffer_size = 4096)`
  repeating every ~10.5s — 6 bytes short (one LED message), 10s being ALSA's
  drain timeout.
- Playback `open → hw_params → prepare → trigger → close` logged nothing
  wrong while `aplay` got `-EIO`. Only capture *open* detected the stall,
  restarted URBs, and — because the ladder escalated — forced a full USB
  reset that happened to fix everything, incidentally, for a direction
  nothing in that codepath was trying to fix.
- Rate changes did not help; they failed at EP0 first, consistent with the
  whole device being wedged rather than just the audio rings.
- Cause of entry unknown; appeared during/after a `JT-MIDI-001` run followed
  by `JT-MIDI-002`. Trigger not isolated — sustained MIDI traffic was present
  but not proven causal.

### 2026-08-18 — second occurrence, arm64 (pi4test), automated (`JT-MIDI-007`)

`arm64-prod/20260818T215659Z-functional`, first time reproduced under the
automated harness. `JT-MIDI-007` runs 1800s of sustained MIDI traffic at
`load_fraction=0.9`, 8 messages/burst — i.e. it floods MIDI OUT continuously,
which rides in the playback stream. Result: `outcome: fail`.

- Playback URB stream stalled at `urb_stall_onset_ms` 908ms into a completion
  gap, roughly 9994s wall-clock into the run (~166 minutes after the harness
  started, well after `JT-MIDI-007` itself began at t≈8420s per its own
  `JT-MARK`) — and **never recovered** for the remaining ~1800s of the test.
  Capture stalled at the same moment (`urb_stall_onset_ms` 1019ms) but that
  side is the expected/deferred idle-capture case, not part of this finding.
- Heartbeats at +61s/+122s/+182s after onset all still read "stalled".
  `rawmidi drain error` repeated every ~10s (ALSA's drain timeout) right up
  to the end of the run — MIDI OUT was dead for the rest of the test.
- `urb_stalls_playback: 1`, `urb_stalls_capture: 1`, `write_failures: 0` (the
  writer itself never saw an error — the loss was silent from userspace's
  point of view apart from the drain timeout).
- Unlike 2026-08-11, MIDI IN and EP0 were not confirmed dead — this run only
  exercises playback (MIDI OUT) and capture, so whether the whole device
  wedged the same way as issue #26 or only the playback ring died this time
  is unknown; would need an EP0 probe (e.g. a rate query) during the stall to
  tell them apart. Not attempted, since the finding was in dmesg after the
  fact, not caught live.
- **Caveat:** the driver under test was dirty (`git_describe: 8e05d2a-dirty`,
  `kernel_driver_dirty: true`, built on `alsa-dev` from `~/sound-build`).
  Not a clean-commit reproduction. Worth re-running once the tree is clean.

### Working hypothesis, unproven

Both occurrences happened during sustained/heavy MIDI OUT traffic (manual
flood-testing in 2026-08-11, `JT-MIDI-007`'s scripted flood in 2026-08-18).
Whether the wedge needs MIDI-OUT load specifically, or just needs the device
running long enough and MIDI happens to be what these two sessions were
exercising, is open. The next data point worth having: does the same wedge
ever show up in a long run with **no** MIDI traffic and an undisturbed
playback ring. `JT-RATE-001` does not qualify for this — a rate change tears
down and restarts the URBs (see `jockey3.c` `DOC:` blocks), so it can't
distinguish "URBs kept running the whole time and never stalled" from "the
ring got torn down and rebuilt before it had the chance to." `JT-PCM-008`
(sustained duplex, formerly `JT-SOAK-001`) is the right candidate: pure
audio, no MIDI, no rate changes, URBs run continuously for the whole soak. If
a long `JT-PCM-008` run never wedges, that argues for MIDI-OUT load as the
trigger; if it does, the wedge is unrelated to MIDI and `JT-MIDI-007` just
runs long enough to hit whatever the real trigger is.

## Heartbeat spam, fixed 2026-08-18

Not the wedge itself, but found while reading this run's dmesg: on an
otherwise idle pi4test with no wedge at all — just the ordinary
deferred-idle-capture case (`jockey3_pcm_hw_params()`'s designed behavior,
not a fault) — `jockey3_watchdog_work()`'s "still stalled" heartbeat repeated
every 60s indefinitely, for the entire uptime of the device. Flagged as a
mainline-submission blocker: unconditional log spam for a state the driver
itself considers benign is exactly what LKML review rejects.

Fixed by capping heartbeats per stall to `JOCKEY3_WATCHDOG_HEARTBEAT_MAX` (3)
in `jockey3_watchdog_check()`/`struct jockey3_pcm_urb_stream::stall_heartbeats`
(`jockey3.c`). After the third reminder the message says so
("; no further reports until it clears") and goes silent until the stream
either recovers (still logs a recovery line whenever that happens, no matter
how much later) or a fresh onset resets the counter. Applies to both the
idle-deferred-capture heartbeat and the "everything else" (this file's wedge)
heartbeat — a real, undealt-with wedge is exactly as capable of running for
days as the benign deferred case is, so it needs the same cap.
