# capture_midi_out

## capture_midi_out

this capture is from a stream where LED blink pattern is being sent. No audio sent/received

- Midi capture in the capture_midi_out_midilog.txt file
- OpenVizsla sniff in the capture_midi_out.txt file


computer: Windows 11 PC 
driver: Reloop driver 2.9.73 (latest)



## capture_macos_xxx

these are various captures from macos running Native Instruments Traktor Pro 3

Windows MIDI out at 44.1 kHz
T=0.034886 (dt=0.002072) | Packet   168 | MIDI: 90 | Sync: ff | Padding: ZERO
T=0.036966 (dt=0.002080) | Packet   178 | MIDI: 0e | Sync: ff | Padding: ZERO
T=0.040512 (dt=0.003546) | Packet   195 | MIDI: 7f | Sync: ff | Padding: ZERO
>>> 2.813 ms between bytes; 355 bytes per second



MacOS MIDI out at 44.1 kHz
T=0.396208 (dt=0.035353) | Packet  1749 | MIDI: 90 | Sync: ff | Padding: ZERO
T=0.396455 (dt=0.000247) | Packet  1750 | MIDI: 21 | Sync: ff | Padding: ZERO
T=0.396894 (dt=0.000439) | Packet  1752 | MIDI: 06 | Sync: ff | Padding: ZERO
>>> 0.343 ms between bytes; 2915 bytes per second


MacOS MIDI out at 96 kHz
T=0.502098 (dt=0.000440) | Packet  4821 | MIDI: 90 | Sync: ff | Padding: ZERO
T=0.502491 (dt=0.000393) | Packet  4825 | MIDI: 09 | Sync: ff | Padding: ZERO
T=0.502910 (dt=0.000419) | Packet  4829 | MIDI: 05 | Sync: ff | Padding: ZERO
>>> 0.406 ms between bytes; 2463 bytes per second


### Test with different buffer sizes
capture_macos_44.1_128.txt
capture_macos_44.1_512.txt
capture_macos_44.1_1024.txt

observation: the data packets on the USB interface are still using the 512 byte Ploytec framing; so this buffer size is apparently related to the MacOS CoreAudio 

### Test with different sample rates

capture_macos_96k_512.txt 	-- capture with 96kHz
capture_macos_96k_to_44k1.txt	-- capture rate change 96k -> 44k1
capture_macos_rate_change.txt   -- various rate changes


### capture_maxos_44k_poweron.txt
capture of power-on cycle, while running Traktor





capture_linux_44k1.txt 	-- capture of single MIDI LED blink at 44k1; which is picked up by device OK
capture_linux_88k.txt 	-- capture of single MIDI LED blink at 88k; which is not picked up by device for some reason


Linux 

Linux 88k ->> ALL DATA PRESENT
T=2.144707 (dt=0.020679) | Packet 15612 | MIDI: 00 | Sync: ff | Padding: ZERO
T=2.145060 (dt=0.000353) | Packet 15615 | MIDI: 91 | Sync: ff | Padding: ZERO
T=2.151854 (dt=0.006794) | Packet 15618 | MIDI: 1b | Sync: ff | Padding: ZERO
>>> 3.57 ms between bytes; 279 bytes per second


44k (kernel log, not usb capture)
[25846.525596] snd-reloop-jockey3 1-3:1.0: MIDI OUT: 0x90
[25846.530786] snd-reloop-jockey3 1-3:1.0: MIDI OUT: 0x1b
[25846.535943] snd-reloop-jockey3 1-3:1.0: MIDI OUT: 0x7f
>>> 5.17 ms between bytes; 193 bytes per second (WITH RATE LIMITER AT 3125 bytes/s)


[25846.541101] snd-reloop-jockey3 1-3:1.0: MIDI OUT: 0x91
[25846.546253] snd-reloop-jockey3 1-3:1.0: MIDI OUT: 0x1b
[25846.551395] snd-reloop-jockey3 1-3:1.0: MIDI OUT: 0x7f
[25846.765763] snd-reloop-jockey3 1-3:1.0: MIDI OUT: 0x90
[25846.770966] snd-reloop-jockey3 1-3:1.0: MIDI OUT: 0x1b
[25846.776135] snd-reloop-jockey3 1-3:1.0: MIDI OUT: 0x00
[25846.781285] snd-reloop-jockey3 1-3:1.0: MIDI OUT: 0x91
[25846.786441] snd-reloop-jockey3 1-3:1.0: MIDI OUT: 0x1b
[25846.791608] snd-reloop-jockey3 1-3:1.0: MIDI OUT: 0x00
