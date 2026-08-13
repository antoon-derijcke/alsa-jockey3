---
capture: capture_2026-08-13_macos_poweron_96k.txt
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
usb_address: 0, 17, 18, 19, 20, 21, 22
has_control_traffic: yes
---

# capture_2026-08-13_macos_poweron_96k.txt

## Objective

Capture the initialization sequence for MacOS during device power-on events.
Multiple events captured, by power-cycling the device while playing in Traktor DJ.
During this session Traktor DJ was configured to play at 96kHz instead of the 
default 44.1 kHz, so we can confirm how this impacts the initialization sequence.

## Conclusion

TODO -- what the trace actually showed, once analyzed. Link the analysis
document if there is one.

## Contents (derived)

- Duration: 64.435 s, 538668 USB transactions
- Device address(es): 0, 17, 18, 19, 20, 21, 22
- Endpoints seen: 0x00 (720), 0x02 (143), 0x03 (93), 0x05 (239633), 0x06 (298079)
- Control transfers: 270 in 18 events
- Event kinds: enumeration x6, init+rate x12
- Sample rates programmed: 44100 Hz, 96000 Hz

### Events

| # | kind | at (s) | transfers | span (ms) |
|---|---|---|---|---|
| 1 | enumeration | 3.067822 | 11 | 14.783 |
| 2 | init+rate | 4.113708 | 16 | 108.760 |
| 3 | init+rate | 4.679656 | 18 | 125.042 |
| 4 | enumeration | 14.167386 | 11 | 15.111 |
| 5 | init+rate | 16.213089 | 16 | 109.331 |
| 6 | init+rate | 16.785492 | 18 | 125.371 |
| 7 | enumeration | 22.939204 | 11 | 15.533 |
| 8 | init+rate | 24.985140 | 16 | 107.348 |
| 9 | init+rate | 25.583227 | 18 | 123.946 |
| 10 | enumeration | 41.056846 | 11 | 15.128 |
| 11 | init+rate | 42.101600 | 16 | 109.539 |
| 12 | init+rate | 42.661971 | 18 | 125.215 |
| 13 | enumeration | 52.542734 | 11 | 16.241 |
| 14 | init+rate | 53.588344 | 16 | 106.341 |
| 15 | init+rate | 54.220214 | 18 | 125.058 |
| 16 | enumeration | 61.184598 | 11 | 15.892 |
| 17 | init+rate | 63.226876 | 16 | 107.815 |
| 18 | init+rate | 63.796443 | 18 | 141.808 |
