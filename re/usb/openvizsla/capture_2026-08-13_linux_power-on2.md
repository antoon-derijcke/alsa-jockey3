---
capture: capture_2026-08-13_linux_power-on2.txt
captured: 2026-08-13
platform: Linux
host: alsa-test; Elitedesk G2; i5 6500; 32GB ram
os_version: Linux alsa-test 7.2.0-rc5-alsa-prod+ #4 SMP PREEMPT_DYNAMIC Sun Aug  9 21:11:53 AST 2026 x86_64 GNU/Linux
driver_version: git acd847724baa05107b2834274a079e0b435910bf
application: n/a
module_build_id: f6a71204642f03a5b00aea8d39b34456bba86534
kernel_config: x86_64-prod
device: Reloop Jockey 3 Remix
size_raw: 1018.5 MB
usb_address: 0, 7, 8, 9
has_control_traffic: yes
---

# capture_2026-08-13_linux_power-on2.txt

## Objective

Confirm reliable device initialization on the linux driver

1 - power on -> device detected OK, device initialized ok; playing audio without issues
2 - power-cylce -> device detected OK, able to start audio playback, but NO audio being reproduced
3 - power-cylce -> device detected OK, able to start audio playback, but NO audio being reproduced
4 - power-cylce -> device detected OK, able to start audio playback, but NO audio being reproduced

further tests not possible as the xHCI stopped responding

dmesg output:
```
[  149.939801] usb 1-13: new high-speed USB device number 8 using xhci_hcd
[  150.081182] usb 1-13: New USB device found, idVendor=200c, idProduct=1037, bcdDevice= 1.00
[  150.089465] usb 1-13: New USB device strings: Mfr=1, Product=2, SerialNumber=3
[  150.096707] usb 1-13: Product: Jockey 3 Remix
[  150.101069] usb 1-13: Manufacturer: reloop
[  150.105173] usb 1-13: SerialNumber: no serial number
[  150.136126] snd_reloop_jockey3: loading out-of-tree module taints kernel.
[  150.142917] snd_reloop_jockey3: module verification failed: signature and/or required key missing - tainting kernel
[  150.229023] usbcore: registered new interface driver snd-reloop-jockey3
[  173.070434] snd-reloop-jockey3 1-13:1.0: Capture URB error: -71 (1 consecutive)
[  173.077750] snd-reloop-jockey3 1-13:1.0: MIDI IN URB error: -71 (1 consecutive)
[  173.085104] snd-reloop-jockey3 1-13:1.0: Playback URB error: -71 (1 consecutive)
[  173.092518] snd-reloop-jockey3 1-13:1.0: Capture URB error: -71 (2 consecutive)
[  173.099838] snd-reloop-jockey3 1-13:1.0: Playback URB error: -71 (2 consecutive)
[  173.107236] snd-reloop-jockey3 1-13:1.0: Capture URB error: -71 (3 consecutive)
[  173.114542] snd-reloop-jockey3 1-13:1.0: MIDI IN URB error: -71 (2 consecutive)
[  173.121845] snd-reloop-jockey3 1-13:1.0: Playback URB error: -71 (3 consecutive)
[  173.129272] snd-reloop-jockey3 1-13:1.0: Capture URB error: -71 (4 consecutive)
[  173.136595] snd-reloop-jockey3 1-13:1.0: Playback URB error: -71 (4 consecutive)
[  173.144053] snd-reloop-jockey3 1-13:1.0: Capture URB error: -71 (5 consecutive)
[  173.151375] snd-reloop-jockey3 1-13:1.0: Playback URB error: -71 (5 consecutive)
[  173.158789] snd-reloop-jockey3 1-13:1.0: MIDI IN URB error: -71 (3 consecutive)
[  173.166115] snd-reloop-jockey3 1-13:1.0: Capture stopped after 8 consecutive URB errors; deferring recovery
[  173.175878] snd-reloop-jockey3 1-13:1.0: Playback stopped after 8 consecutive URB errors; deferring recovery
[  173.185787] snd-reloop-jockey3 1-13:1.0: MIDI IN URB error: -71 (4 consecutive)
[  173.193128] usb 1-13: USB disconnect, device number 8
[  173.198218] snd-reloop-jockey3 1-13:1.0: MIDI IN URB error: -71 (5 consecutive)
[  173.198220] snd-reloop-jockey3 1-13:1.0: Failed to resubmit MIDI IN URB: -19
[  179.034136] usb 1-13: new high-speed USB device number 9 using xhci_hcd
[  179.175131] usb 1-13: New USB device found, idVendor=200c, idProduct=1037, bcdDevice= 1.00
[  179.183398] usb 1-13: New USB device strings: Mfr=1, Product=2, SerialNumber=3
[  179.190620] usb 1-13: Product: Jockey 3 Remix
[  179.194998] usb 1-13: Manufacturer: reloop
[  179.199110] usb 1-13: SerialNumber: no serial number
[  213.111206] jockey3_urb_error_give_up: 6 callbacks suppressed
[  213.116976] snd-reloop-jockey3 1-13:1.0: Playback URB error: -71 (1 consecutive)
[  213.124381] snd-reloop-jockey3 1-13:1.0: Capture URB error: -71 (1 consecutive)
[  213.131696] snd-reloop-jockey3 1-13:1.0: Playback URB error: -71 (2 consecutive)
[  213.139144] snd-reloop-jockey3 1-13:1.0: Capture URB error: -71 (2 consecutive)
[  213.146448] snd-reloop-jockey3 1-13:1.0: MIDI IN URB error: -71 (1 consecutive)
[  213.153796] snd-reloop-jockey3 1-13:1.0: Playback URB error: -71 (3 consecutive)
[  213.161202] snd-reloop-jockey3 1-13:1.0: Capture URB error: -71 (3 consecutive)
[  213.168501] snd-reloop-jockey3 1-13:1.0: Playback URB error: -71 (4 consecutive)
[  213.175926] snd-reloop-jockey3 1-13:1.0: Capture URB error: -71 (4 consecutive)
[  213.183282] snd-reloop-jockey3 1-13:1.0: Playback URB error: -71 (5 consecutive)
[  213.190671] snd-reloop-jockey3 1-13:1.0: Capture URB error: -71 (5 consecutive)
[  213.198110] snd-reloop-jockey3 1-13:1.0: MIDI IN URB error: -71 (2 consecutive)
[  213.205421] snd-reloop-jockey3 1-13:1.0: Playback stopped after 8 consecutive URB errors; deferring recovery
[  213.215264] snd-reloop-jockey3 1-13:1.0: Capture stopped after 8 consecutive URB errors; deferring recovery
[  213.225026] snd-reloop-jockey3 1-13:1.0: MIDI IN URB error: -71 (3 consecutive)
[  213.232376] usb 1-13: USB disconnect, device number 9
[  213.237499] snd-reloop-jockey3 1-13:1.0: MIDI IN URB error: -71 (4 consecutive)
[  213.244841] snd-reloop-jockey3 1-13:1.0: Failed to resubmit MIDI IN URB: -19
[  217.660579] usb 1-13: new high-speed USB device number 10 using xhci_hcd
[  217.801460] usb 1-13: New USB device found, idVendor=200c, idProduct=1037, bcdDevice= 1.00
[  217.809737] usb 1-13: New USB device strings: Mfr=1, Product=2, SerialNumber=3
[  217.816969] usb 1-13: Product: Jockey 3 Remix
[  217.821320] usb 1-13: Manufacturer: reloop
[  217.825413] usb 1-13: SerialNumber: no serial number
[  238.672285] jockey3_urb_error_give_up: 6 callbacks suppressed
[  238.678065] snd-reloop-jockey3 1-13:1.0: Playback URB error: -71 (1 consecutive)
[  238.685460] snd-reloop-jockey3 1-13:1.0: Capture URB error: -71 (1 consecutive)
[  238.692781] snd-reloop-jockey3 1-13:1.0: MIDI IN URB error: -71 (1 consecutive)
[  238.700164] snd-reloop-jockey3 1-13:1.0: Playback URB error: -71 (2 consecutive)
[  238.707589] snd-reloop-jockey3 1-13:1.0: Capture URB error: -71 (2 consecutive)
[  238.714942] snd-reloop-jockey3 1-13:1.0: Playback URB error: -71 (3 consecutive)
[  238.722348] snd-reloop-jockey3 1-13:1.0: Capture URB error: -71 (3 consecutive)
[  238.729648] snd-reloop-jockey3 1-13:1.0: Playback URB error: -71 (4 consecutive)
[  238.737041] snd-reloop-jockey3 1-13:1.0: Capture URB error: -71 (4 consecutive)
[  238.744347] snd-reloop-jockey3 1-13:1.0: Playback URB error: -71 (5 consecutive)
[  238.751735] snd-reloop-jockey3 1-13:1.0: Capture URB error: -71 (5 consecutive)
[  238.759048] snd-reloop-jockey3 1-13:1.0: MIDI IN URB error: -71 (2 consecutive)
[  238.766475] snd-reloop-jockey3 1-13:1.0: Playback stopped after 8 consecutive URB errors; deferring recovery
[  238.776280] snd-reloop-jockey3 1-13:1.0: Capture stopped after 8 consecutive URB errors; deferring recovery
[  238.786042] snd-reloop-jockey3 1-13:1.0: MIDI IN URB error: -71 (3 consecutive)
[  238.793382] usb 1-13: USB disconnect, device number 10
[  239.411978] snd-reloop-jockey3 1-13:1.0: Playback URB stream stalled: no completion for 618 ms (3 URBs in flight, substream idle)
[  239.423615] snd-reloop-jockey3 1-13:1.0: Capture URB stream stalled: no completion for 637 ms (4 URBs in flight, substream idle)
[  243.891861] xhci_hcd 0000:00:14.0: xHCI host not responding to stop endpoint command
[  243.899595] xhci_hcd 0000:00:14.0: xHCI host controller not responding, assume dead
[  243.907241] xhci_hcd 0000:00:14.0: HC died; cleaning up
[  243.914141] usb 1-2: USB disconnect, device number 2
[  243.919353] usb 1-3: USB disconnect, device number 3
[  243.924326] usb 1-3.1: USB disconnect, device number 5
[  244.028306] usb 1-3.2: USB disconnect, device number 6
[  244.056111] usb 1-3.4: USB disconnect, device number 7
[  244.061936] usb 1-4: USB disconnect, device number 4
```


## Conclusion

### The failure has an objective signature: the capture endpoint returns silence

Measuring the bulk streams per USB address -- address 7 is cycle 1, 8 is
cycle 2, 9 is cycle 3 -- separates the working run from the failing ones
cleanly:

| addr | cycle | EP 0x05 OUT | EP 0x86 IN | capture non-zero |
|---|---|---|---|---|
| 7 | 1, audio OK | 59885 pkt, 100% non-zero | 74619 pkt | **95.5%** |
| 8 | 2, no audio | 66692 pkt, 100% non-zero | 82722 pkt | **0.0%** |
| 9 | 3, no audio | 21156 pkt, 100% non-zero | 26358 pkt | **0.0%** |

The host side is blameless: playback carries real audio every cycle, at the
right cadence (4430-4487 packets/s), with the MIDI idle byte 0xfd at offset
480 and the sync byte 0xff at 481 in every single packet. What fails is the
device -- it accepts the stream and returns nothing but zeros, which means its
audio engine never started. That is why nothing was heard.

**This is a pass/fail criterion that needs no OpenVizsla and no listening.**
Record from the device and check whether any sample is non-zero. It makes the
intermittent failure cheap to reproduce and to bisect against, and it belongs
in the hardware test suite.

### The control plane is identical between the working and failing cycles

Diffed transfer by transfer, the three initialization sequences are the same
apart from the USB address: same requests in the same order, same status
values (0x12 read, 0x32 written, 0x32 verified), same rate (44100 Hz
programmed and read back from EP 0x86), and the same inter-transfer gaps
including the 14-15 ms cold-init lead-in and the ~51 ms quiet window.

So the alignment changes work as intended and are not implicated. Whatever
distinguishes a working initialization from a failing one is not in the
sequence we send.

### The one measurable difference, and why it does not yet explain it

The only difference anywhere in the trace is *before* the driver speaks:

| | SET_CONFIGURATION -> first driver transfer |
|---|---|
| cycle 1, audio OK | **43.875 ms** |
| cycle 2, no audio | 0.100 ms |
| cycle 3, no audio | ~0.1 ms |

Cycle 1 is slow because the module was loaded while the device was already
attached, so probe ran from modprobe rather than from enumeration. That is
suggestive -- it is the same shape as the original observation that a debug
kernel always works and a production kernel does not -- but it is not
sufficient: `capture_2026-08-13_linux_power-on.txt` initialized with a
0.226 ms gap and produced 99.4% non-zero capture data. A short gap worked
there.

So the sample is one success and two failures on the fast path, one success on
the slow path. Too small to conclude. The zero-capture detector above is what
makes gathering a real sample cheap.

### The xHCI death is not the watchdog

`jockey3_watchdog_work()` is detection only -- it logs and takes no recovery
action -- and `jockey3_disconnect()` cancels it. The two "URB stream stalled"
lines at 239.4 s are a benign race: a watchdog tick fired between the USB
disconnect notification and the disconnect handler cancelling it, and reported
URBs that teardown was already about to reap.

The controller then failed a stop-endpoint command issued by ordinary
disconnect teardown, four seconds later. Nothing in this driver issues that
command directly, and nothing unusual happened in between. Four power cycles
in ninety seconds on a Skylake-era 100-series PCH is aggressive, and the same
symptom has been seen on this machine when unplugging unrelated devices.
Consistent with the controller rather than the driver, though not proof.

## Contents (derived)

- Duration: 44.385 s, 331889 USB transactions
- Device address(es): 0, 7, 8, 9
- Endpoints seen: 0x00 (288), 0x03 (25), 0x05 (147806), 0x06 (183770)
- Control transfers: 108 in 3 events
- Event kinds: init+rate x3
- Sample rates programmed: 44100 Hz

### Events

| # | kind | at (s) | transfers | span (ms) |
|---|---|---|---|---|
| 1 | init+rate | 5.348714 | 36 | 281.273 |
| 2 | init+rate | 25.059010 | 36 | 236.877 |
| 3 | init+rate | 44.721464 | 36 | 237.054 |
