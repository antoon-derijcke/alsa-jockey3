// SPDX-License-Identifier: GPL-2.0-or-later
/*
 *   ALSA driver for Reloop Jockey 3 devices
 *   Ploytec PCM encoding/decoding functions for the S24_3LE format (3 bytes per sample)
 *   This file contains new/experimental codecs that are under development or evaluation
 *   and are not ready for inclusion in the Linux driver
 *
 *   Copyright (c) 2026 by Frank van de Pol <fvdpol@gmail.com>
 */
#include "ploytec_codec.h"
#include "ploytec_codec_new.h"
#include <string.h>


/*

Executed on alsa-dev (x86_64 dual xeon e5-2678v3)
Ploytec codec test / benchmark

=== Correctness validation (Encoder)===
✅ All 1000000 encode tests passed (bit-exact)
=== Correctness validation (Decoder)===
✅ All 1000000 decode tests passed (bit-exact)

=== Performance benchmark (100000000 iterations) ===
Encode         Original: 7448.79 ms (74.49 ns/call) - 100.0% 1.00x
Encode    Jockey3Driver: 5670.26 ms (56.70 ns/call) - 76.1% 1.31x
Encode     LoopCombined: 5971.77 ms (59.72 ns/call) - 80.2% 1.25x
Encode BitSpreadTable32: 1873.97 ms (18.74 ns/call) - 25.2% 3.97x
Encode BitSpreadTable64: 728.46 ms (7.28 ns/call) - 9.8% 10.23x      <<<<<<<
Decode         Original: 13211.14 ms (132.11 ns/call) - 100.0% 1.00x
Decode    Jockey3Driver: 12214.97 ms (122.15 ns/call) - 92.5% 1.08x
Decode     LoopCombined: 12070.58 ms (120.71 ns/call) - 91.4% 1.09x
Decode           Pack32: 2532.45 ms (25.32 ns/call) - 19.2% 5.22x
Decode           Pack64: 1494.62 ms (14.95 ns/call) - 11.3% 8.84x    <<<<<<<


Executed on alsa-test (x86_64 i5 6500T)
Ploytec codec test / benchmark

=== Correctness validation (Encoder)===
✅ All 1000000 encode tests passed (bit-exact)
=== Correctness validation (Decoder)===
✅ All 1000000 decode tests passed (bit-exact)

=== Performance benchmark (100000000 iterations) ===
Encode         Original: 6132.46 ms (61.32 ns/call) - 100.0% 1.00x
Encode    Jockey3Driver: 4940.73 ms (49.41 ns/call) - 80.6% 1.24x
Encode     LoopCombined: 4612.56 ms (46.13 ns/call) - 75.2% 1.33x
Encode BitSpreadTable32: 997.08 ms (9.97 ns/call) - 16.3% 6.15x
Encode BitSpreadTable64: 564.93 ms (5.65 ns/call) - 9.2% 10.86x      <<<<<<<
Decode         Original: 10910.59 ms (109.11 ns/call) - 100.0% 1.00x
Decode    Jockey3Driver: 10316.10 ms (103.16 ns/call) - 94.6% 1.06x
Decode     LoopCombined: 10172.36 ms (101.72 ns/call) - 93.2% 1.07x
Decode           Pack32: 2040.60 ms (20.41 ns/call) - 18.7% 5.35x
Decode           Pack64: 1309.47 ms (13.09 ns/call) - 12.0% 8.33x    <<<<<<<


Executed on Raspberry PI 4 Model B rev1.4

Ploytec codec test / benchmark

=== Correctness validation (Encoder)===
✅ All 1000000 encode tests passed (bit-exact)
=== Correctness validation (Decoder)===
✅ All 1000000 decode tests passed (bit-exact)

=== Performance benchmark (100000000 iterations) ===
Encode         Original: 12681.62 ms (126.82 ns/call) - 100.0% 1.00x
Encode    Jockey3Driver: 9844.73 ms (98.45 ns/call) - 77.6% 1.29x
Encode     LoopCombined: 9567.00 ms (95.67 ns/call) - 75.4% 1.33x
Encode BitSpreadTable32: 2892.39 ms (28.92 ns/call) - 22.8% 4.38x
Encode BitSpreadTable64: 1557.39 ms (15.57 ns/call) - 12.3% 8.14x    <<<<<<<
Decode         Original: 23746.06 ms (237.46 ns/call) - 100.0% 1.00x
Decode    Jockey3Driver: 22257.12 ms (222.57 ns/call) - 93.7% 1.07x
Decode     LoopCombined: 21861.36 ms (218.61 ns/call) - 92.1% 1.09x
Decode           Pack32: 4831.16 ms (48.31 ns/call) - 20.3% 4.92x
Decode           Pack64: 4152.74 ms (41.53 ns/call) - 17.5% 5.72x    <<<<<<<



Executed on Raspberry PI 1 Model B
Ploytec codec test / benchmark

=== Correctness validation (Encoder)===
✅ All 1000000 encode tests passed (bit-exact)
=== Correctness validation (Decoder)===
✅ All 1000000 decode tests passed (bit-exact)

=== Performance benchmark (100000000 iterations) ===
Encode         Original: 82102.29 ms (821.02 ns/call) - 100.0% 1.00x
Encode    Jockey3Driver: 72466.77 ms (724.67 ns/call) - 88.3% 1.13x
Encode     LoopCombined: 71105.79 ms (711.06 ns/call) - 86.6% 1.15x
Encode BitSpreadTable32: 20880.31 ms (208.80 ns/call) - 25.4% 3.93x
Encode BitSpreadTable64: 16745.03 ms (167.45 ns/call) - 20.4% 4.90x  <<<<<<<  INTERESTING! 
Decode         Original: 204418.65 ms (2044.19 ns/call) - 100.0% 1.00x
Decode    Jockey3Driver: 208449.56 ms (2084.50 ns/call) - 102.0% 0.98x
Decode     LoopCombined: 206030.51 ms (2060.31 ns/call) - 100.8% 0.99x
Decode           Pack32: 44847.87 ms (448.48 ns/call) - 21.9% 4.56x  <<<<<<<
Decode           Pack64: 78588.25 ms (785.88 ns/call) - 38.4% 2.60x


TODO: Test on x86 32 bit architecture

*/


/*************************************************************************************************/
/*  Initial version of the ploytec encoder/decoder                                               */
/*                                                                                               */
/**
 * ploytec_encode_s24_3le - Encode 4-channel S24_3LE to 48-byte Ploytec frame
 * @dest: 48-byte destination buffer
 * @src: 12-byte source buffer (4 channels * 3 bytes)
 *
 * Ploytec Bit-Plane Interleaving (Playback):
 * The firmware uses a non-standard "bit-plane" format where bits from different
 * channels are interleaved into the same byte.
 * - Each 48-byte frame contains 8 samples for 2 pairs of channels.
 * - Bytes 0-23: ALSA Channels 1 & 3
 * - Bytes 24-47: ALSA Channels 2 & 4
 * - Within each 24-byte block, bits are grouped by significance:
 *   - [0-7]: Most significant bits
 *   - [8-15]: Middle bits
 *   - [16-23]: Least significant bits
 * - bit 0 of each byte corresponds to the first channel in the pair.
 * - bit 1 of each byte corresponds to the second channel in the pair.
 */
void ploytec_encode_s24_3le_version1(u8 *dest, const u8 *src)
{
	int i;

	/* First 24 bytes: odd channels (ALSA Ch 1 & 3) */
	for (i = 0; i < 8; i++) {
		dest[i] = (((src[2] >> (7 - i)) & 1) << 0) |
			  (((src[8] >> (7 - i)) & 1) << 1);
	}
	for (i = 0; i < 8; i++) {
		dest[8 + i] = (((src[1] >> (7 - i)) & 1) << 0) |
			      (((src[7] >> (7 - i)) & 1) << 1);
	}
	for (i = 0; i < 8; i++) {
		dest[16 + i] = (((src[0] >> (7 - i)) & 1) << 0) |
			       (((src[6] >> (7 - i)) & 1) << 1);
	}

	/* Second 24 bytes: even channels (ALSA Ch 2 & 4) */
	for (i = 0; i < 8; i++) {
		dest[24 + i] = (((src[5] >> (7 - i)) & 1) << 0) |
			       (((src[11] >> (7 - i)) & 1) << 1);
	}
	for (i = 0; i < 8; i++) {
		dest[24 + 8 + i] = (((src[4] >> (7 - i)) & 1) << 0) |
				   (((src[10] >> (7 - i)) & 1) << 1);
	}
	for (i = 0; i < 8; i++) {
		dest[24 + 16 + i] = (((src[3] >> (7 - i)) & 1) << 0) |
				    (((src[9] >> (7 - i)) & 1) << 1);
	}
}

/**
 * ploytec_decode_s24_3le - Decode 64-byte Ploytec frame to 6-channel S24_3LE
 * @dest: 18-byte destination buffer (6 channels * 3 bytes)
 * @src: 64-byte source buffer
 *
 * Ploytec Bit-Plane Interleaving (Capture):
 * Similar to encoding, the capture path interleaves 3 pairs of channels
 * into bit-planes (bit 0, 1, and 2 of each byte).
 * - Bytes 0x00-0x17: Pair 1 (bits 0,1,2)
 * - Bytes 0x20-0x37: Pair 2 (bits 0,1,2)
 */
void ploytec_decode_s24_3le_version1(u8 *dest, const u8 *src)
{
	int i;

	/* Channel 1: odd channel 1 (bit 0 of bytes 0x00-0x17) */
	dest[0x00] = 0;
	dest[0x01] = 0;
	dest[0x02] = 0;
	for (i = 0; i < 8; i++) {
		dest[0x00] |= ((src[0x10 + i] & 0x01) << (7 - i));
		dest[0x01] |= ((src[0x08 + i] & 0x01) << (7 - i));
		dest[0x02] |= ((src[0x00 + i] & 0x01) << (7 - i));
	}

	/* Channel 2: even channel 2 (bit 0 of bytes 0x20-0x37) */
	dest[0x03] = 0;
	dest[0x04] = 0;
	dest[0x05] = 0;
	for (i = 0; i < 8; i++) {
		dest[0x03] |= ((src[0x30 + i] & 0x01) << (7 - i));
		dest[0x04] |= ((src[0x28 + i] & 0x01) << (7 - i));
		dest[0x05] |= ((src[0x20 + i] & 0x01) << (7 - i));
	}

	/* Channel 3: odd channel 3 (bit 1 of bytes 0x00-0x17) */
	dest[0x06] = 0;
	dest[0x07] = 0;
	dest[0x08] = 0;
	for (i = 0; i < 8; i++) {
		dest[0x06] |= (((src[0x10 + i] & 0x02) >> 1) << (7 - i));
		dest[0x07] |= (((src[0x08 + i] & 0x02) >> 1) << (7 - i));
		dest[0x08] |= (((src[0x00 + i] & 0x02) >> 1) << (7 - i));
	}

	/* Channel 4: even channel 4 (bit 1 of bytes 0x20-0x37) */
	dest[0x09] = 0;
	dest[0x0A] = 0;
	dest[0x0B] = 0;
	for (i = 0; i < 8; i++) {
		dest[0x09] |= (((src[0x30 + i] & 0x02) >> 1) << (7 - i));
		dest[0x0A] |= (((src[0x28 + i] & 0x02) >> 1) << (7 - i));
		dest[0x0B] |= (((src[0x20 + i] & 0x02) >> 1) << (7 - i));
	}

	/* Channel 5: odd channel 5 (bit 2 of bytes 0x00-0x17) */
	dest[0x0C] = 0;
	dest[0x0D] = 0;
	dest[0x0E] = 0;
	for (i = 0; i < 8; i++) {
		dest[0x0C] |= (((src[0x10 + i] & 0x04) >> 2) << (7 - i));
		dest[0x0D] |= (((src[0x08 + i] & 0x04) >> 2) << (7 - i));
		dest[0x0E] |= (((src[0x00 + i] & 0x04) >> 2) << (7 - i));
	}

	/* Channel 6: even channel 6 (bit 2 of bytes 0x20-0x37) */
	dest[0x0F] = 0;
	dest[0x10] = 0;
	dest[0x11] = 0;
	for (i = 0; i < 8; i++) {
		dest[0x0F] |= (((src[0x30 + i] & 0x04) >> 2) << (7 - i));
		dest[0x10] |= (((src[0x28 + i] & 0x04) >> 2) << (7 - i));
		dest[0x11] |= (((src[0x20 + i] & 0x04) >> 2) << (7 - i));
	}
}



/*************************************************************************************************/


/* variant of the standard encoder and decoder, now with the for-loop moved out
 * gives the compiler more options for optimization 
 * 
 * empirical userland testing shows that 
 * - encoding is between 10..25% faster than the orignal on x86_64 hardware
 * - decoding is between 2..10% faster than the original on x86_64 hardware
 * 
 * todo: get similar numbers for arm64 (maybe also for arm?)
 */
void ploytec_encode_s24_3le_loopcombined(u8 *dest, const u8 *src)
{
	int i;

	for (i = 0; i < 8; i++) {
		/* First 24 bytes: odd channels (ALSA Ch 1 & 3) */
		dest[i]     = (((src[2] >> (7 - i)) & 1) << 0) | (((src[8] >> (7 - i)) & 1) << 1);
		dest[8+i]   = (((src[1] >> (7 - i)) & 1) << 0) | (((src[7] >> (7 - i)) & 1) << 1);
		dest[16+i]  = (((src[0] >> (7 - i)) & 1) << 0) | (((src[6] >> (7 - i)) & 1) << 1);

		/* Second 24 bytes: even channels (ALSA Ch 2 & 4) */
		dest[24+i] = (((src[5] >> (7 - i)) & 1) << 0) | (((src[11] >> (7 - i)) & 1) << 1);
		dest[32+i] = (((src[4] >> (7 - i)) & 1) << 0) | (((src[10] >> (7 - i)) & 1) << 1);
		dest[40+i] = (((src[3] >> (7 - i)) & 1) << 0) | (((src[9] >> (7 - i)) & 1) << 1);
	}
}

void ploytec_decode_s24_3le_loopcombined(u8 *dest, const u8 *src)
{
	int i;
	
	memset(dest, 0, 18);
	for (i = 0; i < 8; i++) {
		/* Channel 1: odd channel 1 (bit 0 of bytes 0x00-0x17) */
		dest[0x00] |= ((src[0x10 + i] & 0x01) << (7 - i));	// Ch1 LSB byte
		dest[0x01] |= ((src[0x08 + i] & 0x01) << (7 - i));
		dest[0x02] |= ((src[0x00 + i] & 0x01) << (7 - i));	// Ch2 MSB byte

		/* Channel 2: even channel 2 (bit 0 of bytes 0x20-0x37) */
		dest[0x03] |= ((src[0x30 + i] & 0x01) << (7 - i));
		dest[0x04] |= ((src[0x28 + i] & 0x01) << (7 - i));
		dest[0x05] |= ((src[0x20 + i] & 0x01) << (7 - i));

		/* Channel 3: odd channel 3 (bit 1 of bytes 0x00-0x17) */
		dest[0x06] |= (((src[0x10 + i] & 0x02) >> 1) << (7 - i));
		dest[0x07] |= (((src[0x08 + i] & 0x02) >> 1) << (7 - i));
		dest[0x08] |= (((src[0x00 + i] & 0x02) >> 1) << (7 - i));

		/* Channel 4: even channel 4 (bit 1 of bytes 0x20-0x37) */
		dest[0x09] |= (((src[0x30 + i] & 0x02) >> 1) << (7 - i));
		dest[0x0A] |= (((src[0x28 + i] & 0x02) >> 1) << (7 - i));
		dest[0x0B] |= (((src[0x20 + i] & 0x02) >> 1) << (7 - i));

		/* Channel 5: odd channel 5 (bit 2 of bytes 0x00-0x17) */
		dest[0x0C] |= (((src[0x10 + i] & 0x04) >> 2) << (7 - i));
		dest[0x0D] |= (((src[0x08 + i] & 0x04) >> 2) << (7 - i));
		dest[0x0E] |= (((src[0x00 + i] & 0x04) >> 2) << (7 - i));

		/* Channel 6: even channel 6 (bit 2 of bytes 0x20-0x37) */
		dest[0x0F] |= (((src[0x30 + i] & 0x04) >> 2) << (7 - i));
		dest[0x10] |= (((src[0x28 + i] & 0x04) >> 2) << (7 - i));
		dest[0x11] |= (((src[0x20 + i] & 0x04) >> 2) << (7 - i));
	}
}

/*************************************************************************************************/

/* encoder using a pre-computed lookup table (64 bit)

Instead of looping through bits, we can precompute how a single byte's bits map across an
8-byte block (u64). A 256-entry u64 table takes up exactly 2 KB, fitting comfortably inside
the CPU's L1 Data Cache.

For decoding, we need to extract a specific bit from 8 consecutive bytes and pack them into
a single destination byte. We can load 8 bytes at once into a u64 register, mask out the
unwanted bits, and use a magic multiplier (0x8040201008040201ULL) to collect and collapse
the bits into the top 8 bits of the register.

*/

static u64 ploytec_bit_spread[256];

static u32 ploytec_bit_spread_32_high[256];
static u32 ploytec_bit_spread_32_low[256];

void init_ploytec_bit_spread_table(void)
{
	for (int b = 0; b < 256; b++) {
		u64 spread = 0;
		u32 high_spread = 0;
                u32 low_spread  = 0;

		/* build the 64 bit lookup table */
		for (int i = 0; i < 8; i++)
			// Extract bit (7 - i) and place it into bit 0 of byte i
			spread |= (u64)((b >> (7 - i)) & 1) << (i * 8);

		ploytec_bit_spread[b] = spread;


		/* build the 32 bit lookup table */
		// Process high nibble (bits 7 down to 4) -> maps to bytes 0 to 3
                for (int i = 0; i < 4; i++) {
                        high_spread |= (u32)((b >> (7 - i)) & 1) << (i * 8);
                }
                // Process low nibble (bits 3 down to 0) -> maps to bytes 0 to 3
                for (int i = 0; i < 4; i++) {
                        low_spread  |= (u32)((b >> (3 - i)) & 1) << (i * 8);
                }

                ploytec_bit_spread_32_high[b] = high_spread;
                ploytec_bit_spread_32_low[b]  = low_spread;
	}
}

void ploytec_encode_s24_3le_lut64(u8 *dest, const u8 *src)
{
	// First 24 bytes: odd channels (ALSA Ch 1 & 3)
	*(u64*)(dest + 0)  = ploytec_bit_spread[src[2]] | (ploytec_bit_spread[src[8]] << 1);
	*(u64*)(dest + 8)  = ploytec_bit_spread[src[1]] | (ploytec_bit_spread[src[7]] << 1);
	*(u64*)(dest + 16) = ploytec_bit_spread[src[0]] | (ploytec_bit_spread[src[6]] << 1);

	// Second 24 bytes: even channels (ALSA Ch 2 & 4)
	*(u64*)(dest + 24) = ploytec_bit_spread[src[5]] | (ploytec_bit_spread[src[11]] << 1);
	*(u64*)(dest + 32) = ploytec_bit_spread[src[4]] | (ploytec_bit_spread[src[10]] << 1);
	*(u64*)(dest + 40) = ploytec_bit_spread[src[3]] | (ploytec_bit_spread[src[9]]  << 1);
}

void ploytec_encode_s24_3le_lut32(u8 *dest, const u8 *src)
{
	// First 24 bytes: Odd channels (ALSA Ch 1 [src 0,1,2] & Ch 3 [src 6,7,8])
	// Block 1: Most Significant Bytes
	*(u32*)(dest + 0) = ploytec_bit_spread_32_high[src[2]] | (ploytec_bit_spread_32_high[src[8]] << 1);
	*(u32*)(dest + 4) = ploytec_bit_spread_32_low[src[2]]  | (ploytec_bit_spread_32_low[src[8]]  << 1);

	// Block 2: Middle Bytes
	*(u32*)(dest + 8)  = ploytec_bit_spread_32_high[src[1]] | (ploytec_bit_spread_32_high[src[7]] << 1);
	*(u32*)(dest + 12) = ploytec_bit_spread_32_low[src[1]]  | (ploytec_bit_spread_32_low[src[7]]  << 1);

	// Block 3: Least Significant Bytes
	*(u32*)(dest + 16) = ploytec_bit_spread_32_high[src[0]] | (ploytec_bit_spread_32_high[src[6]] << 1);
	*(u32*)(dest + 20) = ploytec_bit_spread_32_low[src[0]]  | (ploytec_bit_spread_32_low[src[6]]  << 1);


	// Second 24 bytes: Even channels (ALSA Ch 2 [src 3,4,5] & Ch 4 [src 9,10,11])
	// Block 1: Most Significant Bytes
	*(u32*)(dest + 24) = ploytec_bit_spread_32_high[src[5]] | (ploytec_bit_spread_32_high[src[11]] << 1);
	*(u32*)(dest + 28) = ploytec_bit_spread_32_low[src[5]]  | (ploytec_bit_spread_32_low[src[11]]  << 1);

	// Block 2: Middle Bytes
	*(u32*)(dest + 32) = ploytec_bit_spread_32_high[src[4]] | (ploytec_bit_spread_32_high[src[10]] << 1);
	*(u32*)(dest + 36) = ploytec_bit_spread_32_low[src[4]]  | (ploytec_bit_spread_32_low[src[10]]  << 1);

	// Block 3: Least Significant Bytes
	*(u32*)(dest + 40) = ploytec_bit_spread_32_high[src[3]] | (ploytec_bit_spread_32_high[src[9]] << 1);
	*(u32*)(dest + 44) = ploytec_bit_spread_32_low[src[3]]  | (ploytec_bit_spread_32_low[src[9]]  << 1);
}



static inline u8 pack_bit_plane64(u64 val, int bit_index)
{
	// Shift target bit to bit 0 of each byte, then mask it
	u64 masked = (val >> bit_index) & 0x0101010101010101ULL;

	// Multiplier acts as a parallel shift-and-add, collecting 
	// the bits into the highest byte of the u64
	return (u8)((masked * 0x8040201008040201ULL) >> 56);
}

void ploytec_decode_s24_3le_pack64(u8 *dest, const u8 *src)
{
	u64 blocks_0_17_low  = *(const u64*)(src + 0x00);
	u64 blocks_0_17_mid  = *(const u64*)(src + 0x08);
	u64 blocks_0_17_high = *(const u64*)(src + 0x10);

	u64 blocks_20_37_low  = *(const u64*)(src + 0x20);
	u64 blocks_20_37_mid  = *(const u64*)(src + 0x28);
	u64 blocks_20_37_high = *(const u64*)(src + 0x30);

	// Channel 1 (Bit 0 of bytes 0x00-0x17)
	dest[0x00] = pack_bit_plane64(blocks_0_17_high, 0);
	dest[0x01] = pack_bit_plane64(blocks_0_17_mid,  0);
	dest[0x02] = pack_bit_plane64(blocks_0_17_low,  0);

	// Channel 2 (Bit 0 of bytes 0x20-0x37)
	dest[0x03] = pack_bit_plane64(blocks_20_37_high, 0);
	dest[0x04] = pack_bit_plane64(blocks_20_37_mid,  0);
	dest[0x05] = pack_bit_plane64(blocks_20_37_low,  0);

	// Channel 3 (Bit 1 of bytes 0x00-0x17)
	dest[0x06] = pack_bit_plane64(blocks_0_17_high, 1);
	dest[0x07] = pack_bit_plane64(blocks_0_17_mid,  1);
	dest[0x08] = pack_bit_plane64(blocks_0_17_low,  1);

	// Channel 4 (Bit 1 of bytes 0x20-0x37)
	dest[0x09] = pack_bit_plane64(blocks_20_37_high, 1);
	dest[0x0A] = pack_bit_plane64(blocks_20_37_mid,  1);
	dest[0x0B] = pack_bit_plane64(blocks_20_37_low,  1);

	// Channel 5 (Bit 2 of bytes 0x00-0x17)
	dest[0x0C] = pack_bit_plane64(blocks_0_17_high, 2);
	dest[0x0D] = pack_bit_plane64(blocks_0_17_mid,  2);
	dest[0x0E] = pack_bit_plane64(blocks_0_17_low,  2);

	// Channel 6 (Bit 2 of bytes 0x20-0x37)
	dest[0x0F] = pack_bit_plane64(blocks_20_37_high, 2);
	dest[0x10] = pack_bit_plane64(blocks_20_37_mid,  2);
	dest[0x11] = pack_bit_plane64(blocks_20_37_low,  2);
}


static inline u8 pack_bit_plane32(u32 high_4_bytes, u32 low_4_bytes, int bit_index)
{
	// Isolate the targeted bit index across all 4 bytes simultaneously
	u32 high_masked = (high_4_bytes >> bit_index) & 0x01010101U;
	u32 low_masked  = (low_4_bytes  >> bit_index) & 0x01010101U;

	// Use 32-bit multiplier to gather bits 0,1,2,3 into the highest byte
	u8 high_bits = (u8)((high_masked * 0x08040201U) >> 24);
	u8 low_bits  = (u8)((low_masked  * 0x08040201U) >> 24);

	// Combine the upper 4 bits and lower 4 bits into the single output audio byte
	return (high_bits << 4) | low_bits;
}


void ploytec_decode_s24_3le_pack32(u8 *dest, const u8 *src)
{
	// Pre-load all required 4-byte chunks into native 32-bit registers
	u32 src_00_high = *(const u32*)(src + 0x00);
	u32 src_04_low  = *(const u32*)(src + 0x04);
	u32 src_08_high = *(const u32*)(src + 0x08);
	u32 src_0C_low  = *(const u32*)(src + 0x0C);
	u32 src_10_high = *(const u32*)(src + 0x10);
	u32 src_14_low  = *(const u32*)(src + 0x14);

	u32 src_20_high = *(const u32*)(src + 0x20);
	u32 src_24_low  = *(const u32*)(src + 0x24);
	u32 src_28_high = *(const u32*)(src + 0x28);
	u32 src_2C_low  = *(const u32*)(src + 0x2C);
	u32 src_30_high = *(const u32*)(src + 0x30);
	u32 src_34_low  = *(const u32*)(src + 0x34);

	// --- Channel 1: Bit 0 of bytes 0x00-0x17 ---
	dest[0x00] = pack_bit_plane32(src_10_high, src_14_low, 0);
	dest[0x01] = pack_bit_plane32(src_08_high, src_0C_low, 0);
	dest[0x02] = pack_bit_plane32(src_00_high, src_04_low, 0);

	// --- Channel 2: Bit 0 of bytes 0x20-0x37 ---
	dest[0x03] = pack_bit_plane32(src_30_high, src_34_low, 0);
	dest[0x04] = pack_bit_plane32(src_28_high, src_2C_low, 0);
	dest[0x05] = pack_bit_plane32(src_20_high, src_24_low, 0);

	// --- Channel 3: Bit 1 of bytes 0x00-0x17 ---
	dest[0x06] = pack_bit_plane32(src_10_high, src_14_low, 1);
	dest[0x07] = pack_bit_plane32(src_08_high, src_0C_low, 1);
	dest[0x08] = pack_bit_plane32(src_00_high, src_04_low, 1);

	// --- Channel 4: Bit 1 of bytes 0x20-0x37 ---
	dest[0x09] = pack_bit_plane32(src_30_high, src_34_low, 1);
	dest[0x0A] = pack_bit_plane32(src_28_high, src_2C_low, 1);
	dest[0x0B] = pack_bit_plane32(src_20_high, src_24_low, 1);

	// --- Channel 5: Bit 2 of bytes 0x00-0x17 ---
	dest[0x0C] = pack_bit_plane32(src_10_high, src_14_low, 2);
	dest[0x0D] = pack_bit_plane32(src_08_high, src_0C_low, 2);
	dest[0x0E] = pack_bit_plane32(src_00_high, src_04_low, 2);

	// --- Channel 6: Bit 2 of bytes 0x20-0x37 ---
	dest[0x0F] = pack_bit_plane32(src_30_high, src_34_low, 2);
	dest[0x10] = pack_bit_plane32(src_28_high, src_2C_low, 2);
	dest[0x11] = pack_bit_plane32(src_20_high, src_24_low, 2);
}


