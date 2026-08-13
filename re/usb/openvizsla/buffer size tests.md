### Test with different buffer sizes
capture_macos_44.1_128.txt
capture_macos_44.1_512.txt
capture_macos_44.1_1024.txt

observation: the data packets on the USB interface are still using the 512 byte Ploytec framing; so this buffer size is apparently related to the MacOS CoreAudio 

### Test with different sample rates

capture_macos_96k_512.txt 	-- capture with 96kHz
capture_macos_96k_to_44k1.txt	-- capture rate change 96k -> 44k1
capture_macos_rate_change.txt   -- various rate changes
