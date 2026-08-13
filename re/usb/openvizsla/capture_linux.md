---
capture: capture_linux.txt
captured: 2026-07-09
platform: Linux
host: TODO -- machine this was captured on
os_version: TODO
driver_version: TODO -- for Linux, the alsa-jockey3 git hash
application: TODO -- what was driving the device (aplay, Traktor via wine, etc.)
module_build_id: TODO -- Linux only, from /sys/module/snd_reloop_jockey3/notes/
kernel_config: TODO -- Linux only; debug or production, and which config
device: Reloop Jockey 3 (confirm Remix 200c:1037 or Master Edition 200c:1009)
size_raw: 406.0 MB
usb_address: 0, 19
has_control_traffic: yes
---

# capture_linux.txt

## Objective

TODO -- why this trace was taken and what it was expected to show.
**This is the field that matters most.** A trace with no EP0 traffic is
indistinguishable from a botched capture unless the intent is recorded.

## Conclusion

TODO -- what the trace actually showed, once analyzed. Link the analysis
document if there is one.

## Contents (derived)

- Duration: 13.410 s, 131701 USB transactions
- Device address(es): 0, 19
- Endpoints seen: 0x00 (66), 0x03 (13), 0x05 (58529), 0x06 (73093)
- Control transfers: 25 in 1 events
- Event kinds: init x1
- Sample rates programmed: 44100 Hz

### Events

| # | kind | at (s) | transfers | span (ms) |
|---|---|---|---|---|
| 1 | init | 3.928035 | 25 | 225.503 |
