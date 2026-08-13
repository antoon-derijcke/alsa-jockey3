---
capture: capture_linux_88k.txt
captured: 2026-06-28
platform: Linux
host: TODO -- machine this was captured on
os_version: TODO
driver_version: TODO -- for Linux, the alsa-jockey3 git hash
application: TODO -- what was driving the device (aplay, Traktor via wine, etc.)
module_build_id: TODO -- Linux only, from /sys/module/snd_reloop_jockey3/notes/
kernel_config: TODO -- Linux only; debug or production, and which config
device: Reloop Jockey 3 (confirm Remix 200c:1037 or Master Edition 200c:1009)
size_raw: 56.7 MB
usb_address: 13
has_control_traffic: no
---

# capture_linux_88k.txt

## Objective

TODO -- why this trace was taken and what it was expected to show.
**This is the field that matters most.** A trace with no EP0 traffic is
indistinguishable from a botched capture unless the intent is recorded.

## Conclusion

TODO -- what the trace actually showed, once analyzed. Link the analysis
document if there is one.

## Contents (derived)

- Duration: 2.160 s, 15619 USB transactions
- Device address(es): 13
- Endpoints seen: 0x05 (15619)
- Control transfers: 0 in 0 events
- Event kinds: none
- Sample rates programmed: none observed

> **No EP0 traffic.** This trace cannot contribute to any
> control-plane analysis (initialization, rate change). If that was
> not the intent, the capture missed the event; if it was, say so
> under Objective.
