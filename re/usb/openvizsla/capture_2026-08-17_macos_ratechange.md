---
capture: capture_2026-08-17_macos_ratechange.txt
captured: 2026-08-17
platform: macOS
host: Macbook Pro (13" Mid-2012)
os_version: macOS Catalina (10.15.7)
driver_version: Reloop/Ploytec CoreAudio driver 3.3.17
application: Native Instruments Traktor Pro 3, version 3.8.46
module_build_id: n/a
kernel_config: n/a
device: Reloop Jockey 3 Remix Firmware v1.0.6
size_raw: 2.3 GB
usb_address: 0, 8, 9
has_control_traffic: yes
---

# capture_2026-08-17_macos_ratechange.txt

## Objective

This trace was captured to gather more data investigating how the vendor drivers handles the rate-changing.


## Conclusion

TODO -- what the trace actually showed, once analyzed. Link the analysis
document if there is one.

## Contents (derived)

- Duration: 78.233 s, 872119 USB transactions
- Device address(es): 0, 8, 9
- Endpoints seen: 0x00 (2777), 0x02 (335), 0x03 (94), 0x05 (387299), 0x06 (481614)
- Control transfers: 1083 in 61 events
- Event kinds: enumeration x1, init x1, init+rate x59
- Sample rates programmed: 44100 Hz, 48000 Hz, 88200 Hz, 96000 Hz

### Events

| # | kind | at (s) | transfers | span (ms) |
|---|---|---|---|---|
| 1 | enumeration | 5.118538 | 11 | 15.862 |
| 2 | init+rate | 6.166475 | 16 | 112.139 |
| 3 | init+rate | 6.769405 | 18 | 124.984 |
| 4 | init+rate | 11.215887 | 18 | 125.399 |
| 5 | init+rate | 13.077972 | 18 | 141.829 |
| 6 | init+rate | 14.212575 | 18 | 125.505 |
| 7 | init+rate | 16.064095 | 18 | 126.014 |
| 8 | init+rate | 17.020272 | 18 | 125.758 |
| 9 | init+rate | 18.880778 | 18 | 125.746 |
| 10 | init+rate | 19.755850 | 18 | 137.543 |
| 11 | init+rate | 20.982990 | 18 | 140.532 |
| 12 | init+rate | 21.979688 | 18 | 125.857 |
| 13 | init+rate | 23.273160 | 18 | 124.183 |
| 14 | init+rate | 24.194538 | 18 | 139.359 |
| 15 | init+rate | 25.399965 | 18 | 124.954 |
| 16 | init+rate | 26.318441 | 18 | 125.580 |
| 17 | init+rate | 28.026874 | 18 | 124.591 |
| 18 | init+rate | 28.940646 | 18 | 126.024 |
| 19 | init+rate | 30.430205 | 18 | 126.432 |
| 20 | init+rate | 31.321859 | 18 | 138.549 |
| 21 | init+rate | 33.684815 | 18 | 124.861 |
| 22 | init+rate | 34.621427 | 18 | 126.128 |
| 23 | init | 36.951694 | 13 | 307.814 |
| 24 | init+rate | 39.355089 | 17 | 162.208 |
| 25 | init+rate | 39.982604 | 18 | 126.064 |
| 26 | init+rate | 40.796030 | 18 | 135.039 |
| 27 | init+rate | 43.203428 | 18 | 125.555 |
| 28 | init+rate | 44.153485 | 18 | 125.086 |
| 29 | init+rate | 45.704360 | 18 | 140.472 |
| 30 | init+rate | 46.616406 | 18 | 137.637 |
| 31 | init+rate | 49.521525 | 18 | 125.091 |
| 32 | init+rate | 50.575546 | 18 | 125.827 |
| 33 | init+rate | 52.062932 | 18 | 124.637 |
| 34 | init+rate | 53.047694 | 18 | 124.155 |
| 35 | init+rate | 54.486304 | 18 | 139.873 |
| 36 | init+rate | 55.422756 | 18 | 126.032 |
| 37 | init+rate | 56.790411 | 18 | 125.066 |
| 38 | init+rate | 57.684644 | 18 | 125.017 |
| 39 | init+rate | 58.624323 | 18 | 125.758 |
| 40 | init+rate | 59.527616 | 18 | 125.132 |
| 41 | init+rate | 60.416556 | 18 | 124.474 |
| 42 | init+rate | 61.333602 | 18 | 138.993 |
| 43 | init+rate | 62.432961 | 18 | 125.516 |
| 44 | init+rate | 63.403302 | 18 | 125.005 |
| 45 | init+rate | 64.286295 | 18 | 124.595 |
| 46 | init+rate | 65.504234 | 18 | 143.140 |
| 47 | init+rate | 66.807634 | 18 | 126.497 |
| 48 | init+rate | 68.051338 | 18 | 125.125 |
| 49 | init+rate | 69.264163 | 18 | 142.462 |
| 50 | init+rate | 70.368326 | 18 | 140.370 |
| 51 | init+rate | 71.579232 | 18 | 125.744 |
| 52 | init+rate | 72.705611 | 18 | 124.469 |
| 53 | init+rate | 74.042067 | 18 | 139.938 |
| 54 | init+rate | 74.854174 | 18 | 139.434 |
| 55 | init+rate | 76.108618 | 18 | 124.693 |
| 56 | init+rate | 77.050611 | 18 | 126.201 |
| 57 | init+rate | 78.325186 | 18 | 125.259 |
| 58 | init+rate | 79.257555 | 18 | 125.305 |
| 59 | init+rate | 80.237495 | 18 | 125.855 |
| 60 | init+rate | 81.142826 | 18 | 125.316 |
| 61 | init+rate | 82.133031 | 18 | 124.800 |
