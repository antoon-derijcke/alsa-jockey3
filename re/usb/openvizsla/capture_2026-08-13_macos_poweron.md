---
capture: capture_2026-08-13_macos_poweron.txt
captured: 2026-08-13
platform: macOS
host: Macbook Pro (13" Mid-2012)
os_version: macOS Catalina (10.15.7)
driver_version: Reloop/Ploytec CoreAudio driver 3.3.17
application: Native Instruments Traktor Pro 3, version 3.8.46
module_build_id: n/a
kernel_config: n/a
device: Reloop Jockey 3 Remix
size_raw: 1.2 GB
usb_address: 0, 11, 12, 13, 14, 15, 16
has_control_traffic: yes
---

# capture_2026-08-13_macos_poweron.txt

## Objective

Capture the initialization sequence for MacOS during device power-on events.
Multiple events captured, by power-cycling the device while playing in Traktor DJ.

## Conclusion

Six clean cold initializations at 44.1 kHz. Establishes the canonical macOS
cold-init sequence: enumeration, then a 16-transfer init that always programs
**44100 Hz** and ends with `SET_STATUS 0x32`. Because Traktor was already at
44.1 kHz, no rate change follows.

The ~50 ms quiet window appears once per init, between the `GET_RATE` readback
and the final `GET_STATUS`. Analyzed in `../init_timing_comparison.md`.

## Contents (derived)

- Duration: 70.721 s, 392903 USB transactions
- Device address(es): 0, 11, 12, 13, 14, 15, 16
- Endpoints seen: 0x00 (444), 0x02 (66), 0x03 (72), 0x05 (174605), 0x06 (217716)
- Control transfers: 162 in 12 events
- Event kinds: enumeration x6, init+rate x6
- Sample rates programmed: 44100 Hz

### Events

| # | kind | at (s) | transfers | span (ms) |
|---|---|---|---|---|
| 1 | enumeration | 3.593624 | 11 | 15.249 |
| 2 | init+rate | 4.642396 | 16 | 111.800 |
| 3 | enumeration | 19.152481 | 11 | 15.183 |
| 4 | init+rate | 20.196467 | 16 | 106.547 |
| 5 | enumeration | 28.710303 | 11 | 14.772 |
| 6 | init+rate | 30.754954 | 16 | 105.079 |
| 7 | enumeration | 41.673393 | 11 | 15.941 |
| 8 | init+rate | 42.718276 | 16 | 106.603 |
| 9 | enumeration | 53.128300 | 11 | 16.484 |
| 10 | init+rate | 55.184661 | 16 | 114.610 |
| 11 | enumeration | 65.786637 | 11 | 17.013 |
| 12 | init+rate | 66.832767 | 16 | 107.946 |
