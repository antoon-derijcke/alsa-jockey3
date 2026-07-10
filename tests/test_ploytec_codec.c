// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Test / Benchmark for ploytec_encode_s24_3le() and ploytec_decode_s24_3le()
 *
 * Validates correctness (bit-exact match) and measures performance.
 * Useful when adding hardware-specific optimized variants.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <stdint.h>
#include "ploytec_codec.h"
#include "ploytec_codec_new.h"

#define TEST_ITERATIONS		1000000
#define BENCHMARK_ITERATIONS	100000000

typedef void (*encode_fn_t)(uint8_t *dest, const uint8_t *src);
typedef void (*decode_fn_t)(uint8_t *dest, const uint8_t *src);

/* Simple random data generator */
static void fill_random(uint8_t *buf, size_t len)
{
	for (size_t i = 0; i < len; i++)
		buf[i] = rand() & 0xFF;
}

unsigned int validate_encoder(void)
{
	uint8_t src[3 * 4];		// 4ch * 3 bytes (encode input)
	uint8_t encoded_ref[48];	// 48 byte output frame to ploytec
	uint8_t encoded_opt[48];
	unsigned int errors = 0;
	
	for (int t = 0; t < TEST_ITERATIONS; t++) {
		fill_random(src, sizeof(src));
		fill_random(encoded_ref, sizeof(encoded_ref));  // noise

		/* 
		* Encode 4-channel S24_3LE to 48-byte Ploytec frame
		*
		* validate that the optimized version matches the reference;
		* input = src for both,
		* encoded_opt and encoded_ref are the outputs 
		*/

		ploytec_encode_s24_3le_version1(encoded_ref, src);	// "known good" reference implementation

		/* put here the different encoders we'd like to compare against the reference... */

		ploytec_encode_batch(encoded_opt, src, 1);	// version in the jockey3 driver
		if (memcmp(encoded_opt, encoded_ref, 48) != 0) {
			errors++;
			if (errors < 5)
				printf("Encode mismatch at iteration %d (loopcombined)\n", t);
		}	
		
		ploytec_encode_s24_3le_loopcombined(encoded_opt, src);
		if (memcmp(encoded_opt, encoded_ref, 48) != 0) {
			errors++;
			if (errors < 5)
				printf("Encode mismatch at iteration %d (loopcombined)\n", t);
		}

		ploytec_encode_s24_3le_lut32(encoded_opt, src);
		if (memcmp(encoded_opt, encoded_ref, 48) != 0) {
			errors++;
			if (errors < 5)
				printf("Encode mismatch at iteration %d (lut32)\n", t);
		}

		ploytec_encode_s24_3le_lut64(encoded_opt, src);
		if (memcmp(encoded_opt, encoded_ref, 48) != 0) {
			errors++;
			if (errors < 5)
				printf("Encode mismatch at iteration %d (lut64)\n", t);
		}
	}

	return errors;
}



unsigned int validate_decoder(void)
{
	uint8_t src[64];		// 64 byte input frame from ploytec
	uint8_t decoded_ref[6 * 3];	// 6ch * 3 bytes (decode output)
	uint8_t decoded_opt[6 * 3];
	unsigned int errors = 0;
	
	for (int t = 0; t < TEST_ITERATIONS; t++) {
		fill_random(src, sizeof(src));
		fill_random(decoded_ref, sizeof(decoded_ref));  // noise

		/* 
		* Decode 64-byte Ploytec frame to 6-channel S24_3LE
		*
		* validate that the optimized version matches the reference;
		* input = src for both,
		* decoded_opt and decoded_ref are the outputs 
		*/		
		ploytec_decode_s24_3le_version1(decoded_ref, src);	// "known good" reference implementation

		/* put here the different decoders we'd like to compare against the reference... */
		
		ploytec_decode_batch(decoded_opt, src, 1);	// version in the jockey3 driver
		if (memcmp(decoded_opt, decoded_ref, 6 * 3) != 0) {
			errors++;
			if (errors < 5)
				printf("Decode mismatch at iteration %d (loopcombined)\n", t);
		}
			
		ploytec_decode_s24_3le_loopcombined(decoded_opt, src);
		if (memcmp(decoded_opt, decoded_ref, 6 * 3) != 0) {
			errors++;
			if (errors < 5)
				printf("Decode mismatch at iteration %d (loopcombined)\n", t);
		}	
		
		ploytec_decode_s24_3le_pack32(decoded_opt, src);
		if (memcmp(decoded_opt, decoded_ref, 6 * 3) != 0) {
			errors++;
			if (errors < 5)
				printf("Decode mismatch at iteration %d (pack32)\n", t);
		}

		ploytec_decode_s24_3le_pack64(decoded_opt, src);
		if (memcmp(decoded_opt, decoded_ref, 6 * 3) != 0) {
			errors++;
			if (errors < 5)
				printf("Decode mismatch at iteration %d (pack64)\n", t);
		}
	}

	return errors;
}



float encode_benchmark(const char *label, encode_fn_t encode_fn, float baseline)
{
	int frames = 1 << 10;	// 1024 frames (must be a power of 2)
	uint8_t src[frames * 3 * 4];		// 4ch * 3 bytes (encode input)
	uint8_t encoded[48];
	clock_t start, end;
	double time_ms;
	int frame = 0;

	fill_random(src, sizeof(src));

	start = clock();
	for (int i = 0; i < BENCHMARK_ITERATIONS; i++) {
		encode_fn(encoded, &src[frame * 3  * 4]);
		src[frame * 3 * 4] = encoded[12];
		frame = (frame + 1) % frames;
	}
	end = clock();
	time_ms = ((double)(end - start) * 1000.0) / CLOCKS_PER_SEC;

	if (baseline <0)
		baseline = time_ms;

	printf("Encode %16s: %.2f ms (%.2f ns/call) - %.1f%% %.2fx\n",
		label, time_ms, (time_ms * 1e6) / BENCHMARK_ITERATIONS, 100 * time_ms / baseline, baseline / time_ms);
	
	return time_ms;
}

float decode_benchmark(const char *label, decode_fn_t decode_fn, float baseline)
{
	int frames = 1 << 10;	// 1024 frames (must be a power of 2)
	uint8_t src[frames * 64];	// 64 byte input frame 
	uint8_t decoded[6 * 3];
	clock_t start, end;
	double time_ms;
	int frame = 0;

	fill_random(src, sizeof(src));

	start = clock();
	for (int i = 0; i < BENCHMARK_ITERATIONS; i++) {
		/* feed different data too the decoder to avoid the compiler from optimizing it out...*/
		decode_fn(decoded, &src[frame*64]);
		src[frame * 64] = decoded[12];
		frame = (frame + 1) % frames;
	}
	end = clock();
	time_ms = ((double)(end - start) * 1000.0) / CLOCKS_PER_SEC;

	if (baseline <0)
		baseline = time_ms;

	printf("Decode %16s: %.2f ms (%.2f ns/call) - %.1f%% %.2fx\n",
		label, time_ms, (time_ms * 1e6) / BENCHMARK_ITERATIONS, 100 * time_ms / baseline, baseline / time_ms);

	return time_ms;
}

/* wrapper to the version in the actual driver -- call using a batch size of 1 */
static inline void ploytec_encode_driver(u8 *dest, const u8 *src)
{
	ploytec_encode_batch(dest, src, 1);
}

static inline void ploytec_decode_driver(u8 *dest, const u8 *src)
{
	ploytec_decode_batch(dest, src, 1);
}

int main(void)
{
	unsigned int errors = 0;
	float baseline;
	
	printf("Ploytec codec test / benchmark\n\n");

	srand(time(NULL));

	/* build lookup table */
	init_ploytec_bit_spread_lut32();
	init_ploytec_bit_spread_lut64();	

	/* === Correctness test === */
	printf("=== Correctness validation (Encoder)===\n");
	errors = validate_encoder();
	if (errors == 0)
		printf("✅ All %d encode tests passed (bit-exact)\n", TEST_ITERATIONS);
	else
		printf("❌ %d encode errors detected!\n", errors);

	printf("=== Correctness validation (Decoder)===\n");
	errors = validate_decoder();
	if (errors == 0)
		printf("✅ All %d decode tests passed (bit-exact)\n", TEST_ITERATIONS);
	else
		printf("❌ %d decode errors detected!\n", errors);

	/* === Benchmark === */
	printf("\n=== Performance benchmark (%d iterations) ===\n", BENCHMARK_ITERATIONS);
	baseline = encode_benchmark("Original", ploytec_encode_s24_3le_version1, -1);
	encode_benchmark("Jockey3Driver", ploytec_encode_driver, baseline);
	encode_benchmark("LoopCombined", ploytec_encode_s24_3le_loopcombined, baseline);
	encode_benchmark("BitSpreadTable32", ploytec_encode_s24_3le_lut32, baseline);
	encode_benchmark("BitSpreadTable64", ploytec_encode_s24_3le_lut64, baseline);

	baseline = decode_benchmark("Original", ploytec_decode_s24_3le_version1, -1);
	decode_benchmark("Jockey3Driver", ploytec_decode_driver, baseline);
	decode_benchmark("LoopCombined", ploytec_decode_s24_3le_loopcombined, baseline);
	decode_benchmark("Pack32", ploytec_decode_s24_3le_pack32, baseline);
	decode_benchmark("Pack64", ploytec_decode_s24_3le_pack64, baseline);

	return errors ? 1 : 0;
}