---
capture: capture_2026-08-13_macos_poweron_noapp.txt
captured: 2026-08-13
platform: macOS
host: Macbook Pro (13" Mid-2012)
os_version: macOS Catalina (10.15.7)
driver_version: Reloop/Ploytec CoreAudio driver 3.3.17
application: None
module_build_id: n/a
kernel_config: n/a
device: Reloop Jockey 3 Remix
size_raw: 748.5 MB
usb_address: 0, 2, 3, 30, 31, 4, 5
has_control_traffic: yes
---

# capture_2026-08-13_macos_poweron_noapp.txt

## Objective

Capture the initialization sequence for MacOS during device power-on events.
Multiple events captured, by power-cycling the device. 
Note that NO application was running/active using/opening the device, so this
would confirm the working assumption that after detection the URBs would be 
started and kept running forever independent from application use.

## Conclusion

TODO -- what the trace actually showed, once analyzed. Link the analysis
document if there is one.

## Contents (derived)

- Duration: 39.583 s, 318641 USB transactions
- Device address(es): 0, 2, 3, 30, 31, 4, 5
- Endpoints seen: 0x00 (720), 0x02 (54), 0x03 (43), 0x05 (141524), 0x06 (176300)
- Control transfers: 270 in 18 events
- Event kinds: enumeration x6, init+rate x12
- Sample rates programmed: 44100 Hz, 96000 Hz

### Events

| # | kind | at (s) | transfers | span (ms) |
|---|---|---|---|---|
| 1 | enumeration | 3.426664 | 11 | 18.376 |
| 2 | init+rate | 4.471596 | 16 | 107.341 |
| 3 | init+rate | 5.008237 | 18 | 140.370 |
| 4 | enumeration | 14.114329 | 11 | 17.177 |
| 5 | init+rate | 15.156864 | 16 | 106.129 |
| 6 | init+rate | 15.671549 | 18 | 140.898 |
| 7 | enumeration | 20.305271 | 11 | 15.735 |
| 8 | init+rate | 22.348489 | 16 | 105.680 |
| 9 | init+rate | 22.894430 | 18 | 124.786 |
| 10 | enumeration | 26.507635 | 11 | 15.762 |
| 11 | init+rate | 28.548914 | 16 | 107.117 |
| 12 | init+rate | 29.096831 | 18 | 123.672 |
| 13 | enumeration | 32.425290 | 11 | 17.412 |
| 14 | init+rate | 34.471343 | 16 | 108.549 |
| 15 | init+rate | 34.977726 | 18 | 142.072 |
| 16 | enumeration | 38.530708 | 11 | 17.170 |
| 17 | init+rate | 40.578216 | 16 | 111.285 |
| 18 | init+rate | 41.085597 | 18 | 140.614 |
