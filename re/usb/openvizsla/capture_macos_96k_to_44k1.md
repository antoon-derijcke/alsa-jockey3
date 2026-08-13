---
capture: capture_macos_96k_to_44k1.txt
captured: 2026-06-28
platform: macOS
host: TODO -- machine this was captured on
os_version: macOS 10.15.7 "Catalina"
driver_version: Reloop/Ploytec CoreAudio driver 3.3.17
application: Native Instruments Traktor Pro 3, version 3.8.46
module_build_id: n/a (vendor driver)
kernel_config: n/a (not Linux)
device: Reloop Jockey 3 (confirm Remix 200c:1037 or Master Edition 200c:1009)
size_raw: 172.3 MB
usb_address: 7
has_control_traffic: no
---

# capture_macos_96k_to_44k1.txt

## Objective

**UNRESOLVED -- needs Frank to confirm.** The filename says this is a 96 kHz to
44.1 kHz rate change, but the trace contains no EP0 traffic whatsoever, so no
rate change is present in it. Two possibilities:

- it belongs to the buffer-size study alongside `capture_macos_96k_512` and
  the `capture_macos_44k1_*` traces, and is misnamed; or
- it was intended to capture the rate change and the capture missed the event.

## Conclusion

Cannot contribute to rate-change analysis either way. If the second reading is
right, the capture is worth re-taking. This trace is the clearest argument for
the sidecar convention: the filename asserts something the contents contradict,
and nothing recorded at the time can settle it.

## Contents (derived)

- Duration: 3.507 s, 75742 USB transactions
- Device address(es): 7
- Endpoints seen: 0x02 (7), 0x03 (1), 0x05 (33662), 0x06 (42072)
- Control transfers: 0 in 0 events
- Event kinds: none
- Sample rates programmed: none observed

> **No EP0 traffic.** This trace cannot contribute to any
> control-plane analysis (initialization, rate change). If that was
> not the intent, the capture missed the event; if it was, say so
> under Objective.
