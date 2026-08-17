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

TODO -- what the trace actually showed, once analyzed. Link the analysis
document if there is one.

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
