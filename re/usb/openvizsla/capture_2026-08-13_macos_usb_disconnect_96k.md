---
capture: capture_2026-08-13_macos_usb_disconnect_96k.txt
captured: 2026-08-13
platform: macOS
host: Macbook Pro (13" Mid-2012)
os_version: macOS Catalina (10.15.7)
driver_version: Reloop/Ploytec CoreAudio driver 3.3.17
application: Native Instruments Traktor Pro 3, version 3.8.46
module_build_id: n/a
kernel_config: n/a
device: Reloop Jockey 3 Remix
size_raw: 730.7 MB
usb_address: 0, 23, 24, 25, 26, 27, 28
has_control_traffic: yes
---

# capture_2026-08-13_macos_usb_disconnect_96k.txt

## Objective

Capture the initialization sequence for MacOS during usb disconnect/reconnect events.
Multiple events captured, by un-/re-plugging the usb cable while playing in Traktor DJ.
During this session Traktor DJ was configured to play at 96kHz instead of the 
default 44.1 kHz. Since the device was not power-cycled, it should have retained the
configured sample rate, which may or not may be relfected in the initialization sequence.

## Conclusion

TODO -- what the trace actually showed, once analyzed. Link the analysis
document if there is one.

## Contents (derived)

- Duration: 42.629 s, 304068 USB transactions
- Device address(es): 0, 23, 24, 25, 26, 27, 28
- Endpoints seen: 0x00 (554), 0x02 (58), 0x03 (18), 0x05 (135126), 0x06 (168312)
- Control transfers: 207 in 14 events
- Event kinds: enumeration x5, init+rate x9
- Sample rates programmed: 44100 Hz, 96000 Hz

### Events

| # | kind | at (s) | transfers | span (ms) |
|---|---|---|---|---|
| 1 | enumeration | 8.355131 | 11 | 15.400 |
| 2 | init+rate | 10.399024 | 16 | 105.219 |
| 3 | init+rate | 10.963725 | 18 | 124.354 |
| 4 | enumeration | 16.865654 | 11 | 16.596 |
| 5 | init+rate | 18.911856 | 16 | 106.478 |
| 6 | init+rate | 19.438728 | 18 | 142.316 |
| 7 | enumeration | 23.716244 | 11 | 19.649 |
| 8 | init+rate | 25.767390 | 16 | 105.195 |
| 9 | init+rate | 26.371464 | 18 | 123.545 |
| 10 | enumeration | 30.659572 | 11 | 17.478 |
| 11 | init+rate | 32.979271 | 16 | 103.254 |
| 12 | init+rate | 34.934669 | 18 | 141.134 |
| 13 | enumeration | 38.559327 | 11 | 16.144 |
| 14 | init+rate | 42.127066 | 16 | 107.444 |
