---
capture: capture_stalled_linux.txt
captured: 2026-07-13
platform: Linux
host: TODO -- machine this was captured on
os_version: TODO
driver_version: TODO -- for Linux, the alsa-jockey3 git hash
application: TODO -- what was driving the device (aplay, Traktor via wine, etc.)
module_build_id: TODO -- Linux only, from /sys/module/snd_reloop_jockey3/notes/
kernel_config: TODO -- Linux only; debug or production, and which config
device: Reloop Jockey 3 (confirm Remix 200c:1037 or Master Edition 200c:1009)
size_raw: 733.5 MB
usb_address: 13
has_control_traffic: yes
---

# capture_stalled_linux.txt

## Objective

TODO -- why this trace was taken and what it was expected to show.
**This is the field that matters most.** A trace with no EP0 traffic is
indistinguishable from a botched capture unless the intent is recorded.

## Conclusion

TODO -- what the trace actually showed, once analyzed. Link the analysis
document if there is one.

## Contents (derived)

- Duration: 23.974 s, 249603 USB transactions
- Device address(es): 13
- Endpoints seen: 0x00 (448), 0x03 (11), 0x05 (113436), 0x06 (135708)
- Control transfers: 168 in 8 events
- Event kinds: init+rate x8
- Sample rates programmed: 44100 Hz, 48000 Hz, 88200 Hz, 96000 Hz

### Events

| # | kind | at (s) | transfers | span (ms) |
|---|---|---|---|---|
| 1 | init+rate | 7.438278 | 21 | 159.338 |
| 2 | init+rate | 9.780392 | 21 | 161.508 |
| 3 | init+rate | 12.489342 | 21 | 158.860 |
| 4 | init+rate | 14.149229 | 21 | 135.647 |
| 5 | init+rate | 15.869398 | 21 | 135.488 |
| 6 | init+rate | 18.828962 | 21 | 160.053 |
| 7 | init+rate | 21.649575 | 21 | 135.589 |
| 8 | init+rate | 23.262584 | 21 | 158.312 |
