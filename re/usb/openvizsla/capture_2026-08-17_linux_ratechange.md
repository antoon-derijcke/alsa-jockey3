---
capture: capture_2026-08-17_linux_ratechange.txt
captured: 2026-08-17
platform: Linux
host: alsa-test; Elitedesk G2; i5 6500; 32GB ram
os_version: Linux alsa-test 7.2.0-rc5-alsa-prod+ #4 SMP PREEMPT_DYNAMIC Sun Aug  9 21:11:53 AST 2026 x86_64 GNU/Linux
driver_version: 2f259a4a6f6944a74da2a96fac3aa792124dfdf8
application: JT-RATE-001
module_build_id: c64d77446c298e08e08392aeea008107963ab764
kernel_config: x86_64-prod
device: Reloop Jockey 3 Remix Firmware v1.0.6
size_raw: 1.1 GB
usb_address: 0, 34, 57
has_control_traffic: yes
---

# capture_2026-08-17_linux_ratechange.txt

## Objective


This trace was captured to compare the linux driver response to rate-changes during the JT-RATE-001 tests.
Test run: 20260817T144709Z-smoke

## Conclusion

Captured alongside the macOS and Windows traces of the same date, as the
driver-side reference for the vendor comparison.

**This trace contains the failing rate change on the wire** -- open question
4 of `rate_change_stall.md`, which had been deferred as needing a dedicated
capture. Events 2, 5 and 7 each hold a stall followed by a re-enumeration and
a 5-write reprogram burst. Taking event 5 (`88200->48000`): the burst
completes normally, the verify read returns the new rate, EP0 reports no
fault, playback OUT on `0x05` resumes at full rate for ~60 ms until the
driver tears it down for the reset -- and **capture IN on `0x86` produces
nothing until the reset completes**, 410 ms after the burst.

Measured with `rate_burst_profile.py --resume`, the split across all 21
changes in this trace is total: playback always resumes at 50.7-51.7 ms, and
capture either follows within 52.3-71.0 ms (18 changes) or not until
410.0-433.8 ms (3 changes -- events 2, 5, 7, the reset episodes). Nothing
lands in between. Caveat: `parse_openvizsla.py` discards NAKs, so this does
not distinguish a silent endpoint from a NAKing one.

**Our sequence terminates differently from both vendors.** All 21 bursts here
end with a second `GET_STATUS` where the vendors send
`SET_STATUS wValue=0x0032` -- `ploytec_start_streaming()` skips the write
because the device already reports the `STREAMING` bit set. The quiet windows
and burst shape otherwise match macOS to within 1 ms.

**Do not use `classify_rate_transitions.py` on this trace.** It reports 10
transitions; the trace contains 21. That script keeps one GET/SET pair per
EVENT block, which is exact for vendor traces but wrong here -- event 5 alone
holds three rate changes and a re-enumeration. Use `rate_burst_profile.py`.

The sweep contains no `down`/`within` transition (9 `down`/`cross`, 8
`up`/`within`, 1 `up`/`cross`), so the wire evidence above is from
`down`/`cross`. See "Captures needed", priority 1b.

See `re/rate_change_stall.md`, section "2026-08-17: the vendor
sequence is direction-blind, and three concrete divergences", for the full
analysis. Profile any burst in this trace with
`re/usb/rate_burst_profile.py`.

## Contents (derived)

- Duration: 35.172 s, 398585 USB transactions
- Device address(es): 0, 34, 57
- Endpoints seen: 0x00 (1178), 0x01 (10), 0x03 (16), 0x05 (177574), 0x06 (219807)
- Control transfers: 438 in 11 events
- Event kinds: enumeration x1, init+rate x10
- Sample rates programmed: 44100 Hz, 48000 Hz, 88200 Hz, 96000 Hz

### Events

| # | kind | at (s) | transfers | span (ms) |
|---|---|---|---|---|
| 1 | enumeration | 3.364526 | 2 | 1000.830 |
| 2 | init+rate | 5.845873 | 125 | 7380.304 |
| 3 | init+rate | 14.135927 | 19 | 215.684 |
| 4 | init+rate | 16.139810 | 19 | 247.147 |
| 5 | init+rate | 17.354148 | 71 | 2610.391 |
| 6 | init+rate | 20.878293 | 37 | 2213.935 |
| 7 | init+rate | 24.034023 | 71 | 2636.475 |
| 8 | init+rate | 27.568975 | 19 | 233.657 |
| 9 | init+rate | 29.505917 | 19 | 245.638 |
| 10 | init+rate | 30.723574 | 37 | 2172.491 |
| 11 | init+rate | 33.866568 | 19 | 131.496 |
