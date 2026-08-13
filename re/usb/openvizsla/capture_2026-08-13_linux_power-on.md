---
capture: capture_2026-08-13_linux_power-on.txt
captured: 2026-08-13
platform: linux
host: alsa-test; Elitedesk G2; i5 6500; 32GB ram
os_version: Linux alsa-test 7.2.0-rc5-alsa-prod+ #4 SMP PREEMPT_DYNAMIC Sun Aug  9 21:11:53 AST 2026 x86_64 GNU/Linux
driver_version: git acd847724baa05107b2834274a079e0b435910bf
application: n/a
module_build_id: f6a71204642f03a5b00aea8d39b34456bba86534
kernel_config: x86_64-prod
device: Reloop Jockey 3 Remix
size_raw: 145.1 MB
usb_address: 0, 12
has_control_traffic: yes
---

# capture_2026-08-13_linux_power-on.txt

## Objective

Confirm reliable device initialization on Linux prod kernel; device successfully initialized
and able to play audio. however, the power-off triggered a kernel bug:

```
[ 8183.959426] usb 1-13: new high-speed USB device number 13 using xhci_hcd
[ 8184.101045] usb 1-13: New USB device found, idVendor=200c, idProduct=1037, bcdDevice= 1.00
[ 8184.109329] usb 1-13: New USB device strings: Mfr=1, Product=2, SerialNumber=3
[ 8184.116579] usb 1-13: Product: Jockey 3 Remix
[ 8184.120945] usb 1-13: Manufacturer: reloop
[ 8184.125055] usb 1-13: SerialNumber: no serial number
[ 8184.130612] snd-reloop-jockey3 1-13:1.0: Firmware 0x31 v1.0.6
[ 8184.140006] snd-reloop-jockey3 1-13:1.0: Firmware 0x31 v1.0.6
[ 8196.531478] snd-reloop-jockey3 1-13:1.0: Playback URB error: -71 (1 consecutive)
[ 8196.538941] snd-reloop-jockey3 1-13:1.0: Playback URB error: -71 (2 consecutive)
[ 8196.546370] snd-reloop-jockey3 1-13:1.0: MIDI IN URB error: -71 (1 consecutive)
[ 8196.553688] snd-reloop-jockey3 1-13:1.0: Capture URB error: -71 (1 consecutive)
[ 8196.561050] snd-reloop-jockey3 1-13:1.0: Playback URB error: -71 (3 consecutive)
[ 8196.568456] snd-reloop-jockey3 1-13:1.0: Capture URB error: -71 (2 consecutive)
[ 8196.575771] snd-reloop-jockey3 1-13:1.0: Playback URB error: -71 (4 consecutive)
[ 8196.583187] snd-reloop-jockey3 1-13:1.0: Capture URB error: -71 (3 consecutive)
[ 8196.590536] snd-reloop-jockey3 1-13:1.0: MIDI IN URB error: -71 (2 consecutive)
[ 8196.597879] snd-reloop-jockey3 1-13:1.0: Playback URB error: -71 (5 consecutive)
[ 8196.605319] snd-reloop-jockey3 1-13:1.0: Capture URB error: -71 (4 consecutive)
[ 8196.612635] snd-reloop-jockey3 1-13:1.0: Playback URB error: -71 (6 consecutive)
[ 8196.620104] snd-reloop-jockey3 1-13:1.0: Playback stopped after 8 consecutive URB errors; deferring recovery
[ 8196.629968] snd-reloop-jockey3 1-13:1.0: MIDI IN URB error: -71 (3 consecutive)
[ 8196.637296] snd-reloop-jockey3 1-13:1.0: Capture stopped after 8 consecutive URB errors; deferring recovery
[ 8196.647075] usb 1-13: USB disconnect, device number 13
[ 8196.652285] snd-reloop-jockey3 1-13:1.0: MIDI IN URB error: -71 (4 consecutive)
[ 8196.652286] snd-reloop-jockey3 1-13:1.0: Failed to resubmit MIDI IN URB: -19
[ 8196.667221] snd-reloop-jockey3 1-13:1.0: Playback URB stalled when preparing playback stream
[ 8196.702036] usercopy: Kernel memory exposure attempt detected from SLUB object 'kmalloc-4k' (offset 56, size 4096)!
[ 8196.712516] ------------[ cut here ]------------
[ 8196.717138] kernel BUG at mm/usercopy.c:102!
[ 8196.721425] Oops: invalid opcode: 0000 [#1] SMP PTI
[ 8196.726318] CPU: 0 UID: 1000 PID: 1749 Comm: python3 Tainted: G           OE       7.2.0-rc5-alsa-prod+ #4 PREEMPT(full)
[ 8196.737263] Tainted: [O]=OOT_MODULE, [E]=UNSIGNED_MODULE
[ 8196.742570] Hardware name: HP HP EliteDesk 800 G2 DM 65W/8056, BIOS N21 Ver. 02.61 03/17/2023
[ 8196.751087] RIP: 0010:usercopy_abort+0x78/0x7a
[ 8196.755532] Code: d7 10 22 b1 eb 0e 48 c7 c2 18 30 24 b1 48 c7 c7 c5 44 21 b1 56 48 89 fe 48 c7 c7 20 1e 1a b1 51 48 89 c1 41 52 e8 88 e6 fe ff <0f>       0b 48 89 d9 49 89 e8 44 89 e2 31 f6 48 29 c1 48 c7 c7 2c 11 22
[ 8196.774271] RSP: 0018:ffffd1d8c229fb88 EFLAGS: 00010246
[ 8196.779496] RAX: 0000000000000067 RBX: 0000000000000038 RCX: 0000000000000000
[ 8196.786626] RDX: 0000000000000000 RSI: 0000000000000001 RDI: ffff8d092f41d040
[ 8196.793757] RBP: 0000000000001000 R08: 0000000000000000 R09: 3fffffffffffefff
[ 8196.800888] R10: ffffd1d8c229fa10 R11: 0000000000000003 R12: ffff8cfa40042d00
[ 8196.808018] R13: 0000000000000001 R14: 00007f26300015a0 R15: ffff8cfb466da180
[ 8196.815140] FS:  00007f2634d136c0(0000) GS:ffff8d097d459000(0000) knlGS:0000000000000000
[ 8196.823222] CS:  0010 DS: 0000 ES: 0000 CR0: 0000000080050033
[ 8196.828968] CR2: 000055cb07b708c0 CR3: 000000040beba003 CR4: 00000000003726f0
[ 8196.836100] Call Trace:
[ 8196.838551]  <TASK>
[ 8196.840658]  __check_heap_object+0xd9/0x110
[ 8196.844843]  __check_object_size+0x1d1/0x220
[ 8196.849118]  copy_urb_data_to_user+0x111/0x130 [usbcore]
[ 8196.854456]  processcompl+0xcd/0x140 [usbcore]
[ 8196.858916]  usbdev_ioctl+0x11d/0x1340 [usbcore]
[ 8196.863545]  ? try_to_wake_up+0x154/0x660
[ 8196.867555]  ? __x64_sys_ioctl+0xb0/0xe0
[ 8196.871483]  __x64_sys_ioctl+0x96/0xe0
[ 8196.875258]  ? futex_wake+0x10f/0x240
[ 8196.878935]  do_syscall_64+0xea/0x640
[ 8196.882601]  ? do_futex+0x10c/0x210
[ 8196.886093]  ? __x64_sys_futex+0x126/0x1e0
[ 8196.890191]  ? do_syscall_64+0x128/0x640
[ 8196.894114]  ? __hrtimer_rearm_deferred+0x5d/0x130
[ 8196.898908]  ? __schedule+0x8ba/0x1070
[ 8196.902658]  ? schedule+0x27/0xa0
[ 8196.905977]  ? irqentry_exit+0x48/0x740
[ 8196.909817]  ? do_syscall_64+0x9f/0x640
[ 8196.913655]  entry_SYSCALL_64_after_hwframe+0x76/0x7e
[ 8196.918709] RIP: 0033:0x7f2635fe491b
[ 8196.922288] Code: 00 48 89 44 24 18 31 c0 48 8d 44 24 60 c7 04 24 10 00 00 00 48 89 44 24 08 48 8d 44 24 20 48 89 44 24 10 b8 10 00 00 00 0f 05 <89>       c2 3d 00 f0 ff ff 77 1c 48 8b 44 24 18 64 48 2b 04 25 28 00 00
[ 8196.941037] RSP: 002b:00007f2634d12200 EFLAGS: 00000246 ORIG_RAX: 0000000000000010
[ 8196.948604] RAX: ffffffffffffffda RBX: 0000000011171c20 RCX: 00007f2635fe491b
[ 8196.955728] RDX: 00007f2634d12270 RSI: 000000004008550d RDI: 0000000000000008
[ 8196.962854] RBP: 0000000000000012 R08: 0000000000000000 R09: 0000000000001000
[ 8196.969984] R10: 0000000000000000 R11: 0000000000000246 R12: 0000000011171c20
[ 8196.977114] R13: 0000000000000000 R14: 000000001118bf80 R15: 0000000000000000
[ 8196.984240]  </TASK>
[ 8196.986430] Modules linked in: snd_reloop_jockey3(OE) sd_mod snd_rawmidi snd_seq_device cfg80211 8021q garp stp mrp llc qrtr binfmt_misc snd_hda_code      c_intelhdmi snd_hda_codec_hdmi nls_ascii nls_cp437 vfat fat snd_hda_codec_alc269 snd_hda_codec_realtek_lib snd_hda_scodec_component snd_hda_codec_generi      c intel_rapl_msr snd_hda_intel intel_rapl_common snd_soc_avs snd_soc_hda_codec snd_hda_ext_core snd_hda_codec snd_hda_core x86_pkg_temp_thermal intel_po      werclamp coretemp snd_intel_dspcfg snd_intel_sdw_acpi kvm_intel snd_hwdep hp_bioscfg snd_soc_core snd_compress firmware_attributes_class snd_pcm_dmaengi      ne kvm snd_pcm mei_hdcp irqbypass mei_pxp aesni_intel mei_wdt hp_wmi gf128mul aead rapl snd_timer sparse_keymap intel_cstate snd rfkill mei_me wmi_bmof       intel_uncore pcspkr ee1004 soundcore mei intel_pch_thermal intel_pmc_core pmt_telemetry pmt_discovery pmt_class intel_pmc_ssram_telemetry intel_pmc_pwrm      _telemetry intel_vsec acpi_pad tpm_infineon evdev msr i2c_dev parport_pc ppdev lp parport efi_pstore configfs efivarfs
[ 8196.986491]  autofs4 ext4 crc16 mbcache jbd2 hid_generic usbhid hid i915 drm_buddy ttm i2c_algo_bit drm_display_helper cec ahci rc_core libahci xhci_      pci nvme drm_client_lib xhci_hcd libata nvme_core drm_kms_helper iTCO_wdt intel_pmc_bxt watchdog video nvme_keyring drm i2c_i801 nvme_auth scsi_mod usbc      ore e1000e i2c_smbus scsi_common wmi usb_common button [last unloaded: snd_reloop_jockey3(OE)]
[ 8197.110666] ---[ end trace 0000000000000000 ]---
[ 8197.160366] RIP: 0010:usercopy_abort+0x78/0x7a
[ 8197.164821] Code: d7 10 22 b1 eb 0e 48 c7 c2 18 30 24 b1 48 c7 c7 c5 44 21 b1 56 48 89 fe 48 c7 c7 20 1e 1a b1 51 48 89 c1 41 52 e8 88 e6 fe ff <0f>       0b 48 89 d9 49 89 e8 44 89 e2 31 f6 48 29 c1 48 c7 c7 2c 11 22
[ 8197.183665] RSP: 0018:ffffd1d8c229fb88 EFLAGS: 00010246
[ 8197.188902] RAX: 0000000000000067 RBX: 0000000000000038 RCX: 0000000000000000
[ 8197.196042] RDX: 0000000000000000 RSI: 0000000000000001 RDI: ffff8d092f41d040
[ 8197.203188] RBP: 0000000000001000 R08: 0000000000000000 R09: 3fffffffffffefff
[ 8197.210314] R10: ffffd1d8c229fa10 R11: 0000000000000003 R12: ffff8cfa40042d00
[ 8197.217447] R13: 0000000000000001 R14: 00007f26300015a0 R15: ffff8cfb466da180
[ 8197.224576] FS:  00007f2634d136c0(0000) GS:ffff8d097d459000(0000) knlGS:0000000000000000
[ 8197.232662] CS:  0010 DS: 0000 ES: 0000 CR0: 0000000080050033
[ 8197.238411] CR2: 000055cb07b708c0 CR3: 000000040beba003 CR4: 00000000003726f0
[ 8236.123030] usb 1-4: USB disconnect, device number 8
```



## Conclusion

### The initialization is now vendor-shaped

Confirmed on the wire. Every change from the alignment series is visible and
correct, and the sequence is essentially identical to a macOS cold init:

```
SET_INTERFACE intf=0 alt=1
SET_INTERFACE intf=1 alt=1          no alt-0 bounce
CLEAR_FEATURE x3
GET_STATUS -> 32
GET_RATE ep=none -> 44100 Hz        wIndex 0, the vendor form
<14.161 ms>                         cold-init lead-in
SET_RATE 86 05 86 05 86 -> 44100    programmed unconditionally, ends on 0x86
GET_RATE ep=0x86 -> 44100 Hz        verified from the capture endpoint
<51.352 ms>                         the quiet window
GET_STATUS -> 32
```

The rate burst now runs at all, which it never did before. The doubled
prologue is still present as expected -- the handshake appears twice, at
170.5 ms and again at 180.0 ms -- because probe runs jockey3_initialize_ploytec()
and then jockey3_set_rate(). macOS does one pass. Harmless, and the reason the
sequence ends with two GET_STATUS reads and no SET_STATUS: the streaming bit
was already set by the first pass.

**One occurrence only.** The initialization failure this was meant to address
is intermittent, so a single success is encouraging but not evidence. Repeat
the power-on cycle many times before drawing a conclusion.

### The kernel oops is not this driver

The BUG at power-off is in usbcore's usbdevfs path, not in this driver:

```
usercopy_abort
__check_heap_object
__check_object_size
copy_urb_data_to_user  [usbcore]
processcompl           [usbcore]
usbdev_ioctl           [usbcore]
__x64_sys_ioctl
```

No `jockey3_*` or `ploytec_*` frame appears anywhere in the trace. The failing
context is the `ioctl()` syscall of an unprivileged userspace process
(`Comm: python3`, `UID: 1000`), reaping URBs through `/dev/bus/usb` --
`copy_urb_data_to_user()` is reachable only from usbdevfs. This is a kernel
driver and never uses that interface; nothing in `tests/` uses pyusb or libusb
either. The python process is the OpenVizsla capture tool, which streams from
the OV board over USB via libusb, and the `usb 1-4: USB disconnect, device
number 8` at the end of the log is that board being unplugged afterwards.

What CONFIG_HARDENED_USERCOPY caught is a 4096-byte copy starting 56 bytes
into a 4096-byte allocation, so 56 bytes past the end. That length comes from
usbdevfs's own accounting of the completed URB, which this driver cannot
influence; heap corruption from elsewhere would not change it.

The disconnect handling that *is* ours behaved as designed: a flood of -71
(EPROTO) as the device lost power, the consecutive-error counters tripping at
8, both streams stopped with recovery deferred rather than a synchronous
reset, and "Playback URB stalled when preparing playback stream" reported
rather than swallowed when userspace touched the PCM afterwards.

**To confirm:** power-cycle the device with the OpenVizsla capture *not*
running. If the oops does not reproduce, it belongs to the capture tool and
usbdevfs, and is worth reporting upstream. Running the same scenario on the
KASAN debug kernel would independently rule out memory corruption from this
driver.

## Contents (derived)

- Duration: 4.960 s, 46808 USB transactions
- Device address(es): 0, 12
- Endpoints seen: 0x00 (96), 0x03 (9), 0x05 (20758), 0x06 (25945)
- Control transfers: 36 in 1 events
- Event kinds: init+rate x1
- Sample rates programmed: 44100 Hz

### Events

| # | kind | at (s) | transfers | span (ms) |
|---|---|---|---|---|
| 1 | init+rate | 6.544833 | 36 | 249.817 |
