---
capture: capture_2026-08-17_win_ratechange.txt
captured: 2026-08-17
platform: Windows
host: Dell Latitude 5540
os_version: Windows 11 Pro, booted in test mode so the older Reloop driver can load
driver_version: Reloop/Ploytec Windows driver 2.9.73
application: Native Instruments Traktor Pro 3, version 3.11.117
module_build_id: n/a (vendor driver)
kernel_config: n/a (not Linux)
device: Reloop Jockey 3 confirm Remix Firmware v1.0.6
size_raw: 1.7 GB
usb_address: 0, 51
has_control_traffic: yes
---

# capture_2026-08-17_win_ratechange.txt

## Objective

This trace was captured to gather more data investigating how the vendor drivers handles the rate-changing.

## Conclusion

TODO -- what the trace actually showed, once analyzed. Link the analysis
document if there is one.

## Contents (derived)

- Duration: 69.118 s, 639362 USB transactions
- Device address(es): 0, 51
- Endpoints seen: 0x00 (3892), 0x02 (165), 0x03 (23), 0x05 (283338), 0x06 (351944)
- Control transfers: 1409 in 69 events
- Event kinds: control x13, init+rate x56
- Sample rates programmed: 44100 Hz, 48000 Hz, 88200 Hz, 96000 Hz

### Events

| # | kind | at (s) | transfers | span (ms) |
|---|---|---|---|---|
| 1 | init+rate | 6.619776 | 32 | 467.813 |
| 2 | control | 7.503720 | 2 | 0.708 |
| 3 | init+rate | 12.155295 | 25 | 358.601 |
| 4 | init+rate | 13.914190 | 23 | 136.666 |
| 5 | control | 14.302183 | 2 | 0.930 |
| 6 | init+rate | 15.131952 | 25 | 388.800 |
| 7 | init+rate | 17.232869 | 23 | 134.856 |
| 8 | control | 17.617739 | 2 | 0.688 |
| 9 | init+rate | 18.248406 | 25 | 393.511 |
| 10 | init+rate | 19.472579 | 23 | 146.459 |
| 11 | control | 19.869116 | 2 | 0.916 |
| 12 | init+rate | 20.391194 | 25 | 393.844 |
| 13 | init+rate | 21.619904 | 25 | 386.886 |
| 14 | init+rate | 22.468351 | 25 | 389.210 |
| 15 | init+rate | 23.717335 | 25 | 391.426 |
| 16 | init+rate | 24.590159 | 23 | 138.653 |
| 17 | control | 24.978826 | 2 | 0.806 |
| 18 | init+rate | 25.806763 | 25 | 392.597 |
| 19 | init+rate | 26.682832 | 25 | 392.633 |
| 20 | init+rate | 27.896425 | 25 | 392.735 |
| 21 | init+rate | 28.770402 | 25 | 385.350 |
| 22 | init+rate | 29.932044 | 25 | 396.512 |
| 23 | init+rate | 30.815663 | 25 | 391.278 |
| 24 | init+rate | 31.896478 | 25 | 391.718 |
| 25 | init+rate | 32.725631 | 23 | 144.812 |
| 26 | control | 33.121513 | 2 | 0.944 |
| 27 | init+rate | 33.962493 | 25 | 392.625 |
| 28 | init+rate | 34.787114 | 25 | 393.016 |
| 29 | init+rate | 35.894785 | 25 | 395.375 |
| 30 | init+rate | 36.985623 | 23 | 144.678 |
| 31 | control | 37.380541 | 2 | 0.799 |
| 32 | init+rate | 39.370223 | 25 | 389.861 |
| 33 | init+rate | 40.525119 | 25 | 391.731 |
| 34 | init+rate | 41.575539 | 25 | 393.418 |
| 35 | init+rate | 42.662749 | 25 | 392.601 |
| 36 | init+rate | 43.829524 | 25 | 392.694 |
| 37 | init+rate | 44.803272 | 25 | 394.967 |
| 38 | init+rate | 45.809149 | 25 | 395.678 |
| 39 | init+rate | 46.800436 | 25 | 391.469 |
| 40 | init+rate | 47.751686 | 23 | 142.888 |
| 41 | control | 48.146023 | 2 | 0.942 |
| 42 | init+rate | 48.727109 | 25 | 390.860 |
| 43 | init+rate | 49.976644 | 25 | 396.211 |
| 44 | init+rate | 51.189932 | 25 | 385.692 |
| 45 | init+rate | 54.316852 | 25 | 398.221 |
| 46 | init+rate | 55.183266 | 25 | 392.663 |
| 47 | init+rate | 56.564725 | 25 | 390.405 |
| 48 | init+rate | 57.382528 | 23 | 142.081 |
| 49 | control | 57.775015 | 2 | 1.061 |
| 50 | init+rate | 58.443652 | 25 | 389.861 |
| 51 | init+rate | 59.288460 | 25 | 389.262 |
| 52 | init+rate | 60.396754 | 25 | 391.304 |
| 53 | init+rate | 61.255403 | 25 | 386.398 |
| 54 | init+rate | 62.313352 | 25 | 391.475 |
| 55 | init+rate | 63.108920 | 25 | 392.753 |
| 56 | init+rate | 64.889280 | 25 | 391.991 |
| 57 | init+rate | 65.729282 | 25 | 390.135 |
| 58 | init+rate | 66.549668 | 25 | 390.256 |
| 59 | init+rate | 67.369393 | 25 | 390.034 |
| 60 | init+rate | 68.263345 | 23 | 145.982 |
| 61 | control | 68.660737 | 2 | 0.808 |
| 62 | init+rate | 69.078177 | 25 | 387.804 |
| 63 | init+rate | 69.926966 | 25 | 391.802 |
| 64 | init+rate | 70.777736 | 23 | 141.359 |
| 65 | control | 71.170698 | 2 | 0.797 |
| 66 | init+rate | 71.791158 | 23 | 141.508 |
| 67 | control | 72.183823 | 2 | 0.939 |
| 68 | init+rate | 72.964710 | 23 | 146.522 |
| 69 | control | 73.361762 | 2 | 1.060 |
