# MIDI output rates

Analysis of the inter-byte timing of MIDI output from a Mac and Windows machine, using the same USB MIDI interface. 


## Windows MIDI out at 44.1 kHz
T=0.034886 (dt=0.002072) | Packet   168 | MIDI: 90 | Sync: ff | Padding: ZERO
T=0.036966 (dt=0.002080) | Packet   178 | MIDI: 0e | Sync: ff | Padding: ZERO
T=0.040512 (dt=0.003546) | Packet   195 | MIDI: 7f | Sync: ff | Padding: ZERO
>>> 2.813 ms between bytes; 355 bytes per second



## MacOS MIDI out at 44.1 kHz
T=0.396208 (dt=0.035353) | Packet  1749 | MIDI: 90 | Sync: ff | Padding: ZERO
T=0.396455 (dt=0.000247) | Packet  1750 | MIDI: 21 | Sync: ff | Padding: ZERO
T=0.396894 (dt=0.000439) | Packet  1752 | MIDI: 06 | Sync: ff | Padding: ZERO
>>> 0.343 ms between bytes; 2915 bytes per second


## MacOS MIDI out at 96 kHz
T=0.502098 (dt=0.000440) | Packet  4821 | MIDI: 90 | Sync: ff | Padding: ZERO
T=0.502491 (dt=0.000393) | Packet  4825 | MIDI: 09 | Sync: ff | Padding: ZERO
T=0.502910 (dt=0.000419) | Packet  4829 | MIDI: 05 | Sync: ff | Padding: ZERO
>>> 0.406 ms between bytes; 2463 bytes per second



