// SPDX-License-Identifier: GPL-2.0-or-later
/*
 *   ALSA driver for Reloop Jockey 3 devices
 *   KUnit tests for the MIDI 1.0 Running Status expander
 *
 *   Copyright (c) 2026 by Frank van de Pol <fvdpol@gmail.com>
 */

/**
 * DOC: Proving the Running Status expander correct without hardware
 *
 * ploytec_midi_running_status_expand() operates purely on a byte stream: no
 * USB, no locking, no device state. That makes it a clean unit to test in
 * isolation, but the function only returns *one* byte per call -- when a
 * data byte arrives while Running Status is active, the synthesised status
 * byte is returned and the data byte itself is queued in
 * @state->queued_byte / @state->has_queued_byte for the caller to send next,
 * ahead of consuming any further input. That queued-byte drain is part of
 * the function's documented contract (see ploytec_midi.h), even though the
 * only current caller, jockey3_get_next_midi_out_byte() in jockey3.c, has it
 * inlined among the rate limiter and snd_rawmidi_transmit() rather than as a
 * standalone helper. ploytec_midi_test_expand_stream() below reimplements
 * that same four-line drain loop -- generic to the documented contract, not
 * specific to jockey3.c -- so these tests exercise the real behavior a
 * caller sees, not just bare calls to expand().
 *
 * What stays out of scope here, and remains L3/hardware territory: the rate
 * limiter's interaction with the queued byte, and whether the resulting
 * stream actually reaches the device over the URB ring.
 *
 * Two complementary strategies, mirroring ploytec_codec_kunit.c:
 *
 * 1. A handful of directed cases pin documented behavior at the boundaries
 *    the opcode table treats differently: System Real-Time bytes leave
 *    Running Status state untouched, System Common and SysEx clear it, and a
 *    data byte arriving before any status byte passes through raw.
 *
 * 2. A randomized round-trip property, run many times: build a random
 *    stream of fully status-prefixed messages, compress consecutive
 *    same-status Channel Voice messages into Running Status form using a
 *    compression rule kept entirely in the generator (not by calling
 *    expand() and observing what it does), expand the compressed stream
 *    back out, and parse the result with a parser that has no concept of
 *    Running Status at all -- exactly the constraint the device firmware
 *    imposes. A data byte with no pending status fails the parse outright,
 *    which is the property that actually matters: nothing left the
 *    expander still relying on Running Status.
 */

#include <kunit/test.h>
#include <linux/string.h>
#include "ploytec_midi.h"

/* Random stream generation and parsing bounds */
#define PLOYTEC_MIDI_TEST_MSG_MIN	16
#define PLOYTEC_MIDI_TEST_MSG_MAX	48
#define PLOYTEC_MIDI_TEST_IN_CAP	256
#define PLOYTEC_MIDI_TEST_OUT_CAP	256
#define PLOYTEC_MIDI_TEST_ITERATIONS	512

/*
 * xorshift64*, self-contained to this file -- see ploytec_codec_kunit.c for
 * the same construction. A fixed seed per test case makes every failure
 * reproduce exactly.
 */
struct ploytec_midi_test_rng {
	u64 state;
};

static void ploytec_midi_rng_init(struct ploytec_midi_test_rng *rng, u64 seed)
{
	rng->state = seed ? seed : 1;
}

static u64 ploytec_midi_rng_next(struct ploytec_midi_test_rng *rng)
{
	u64 x = rng->state;

	x ^= x >> 12;
	x ^= x << 25;
	x ^= x >> 27;
	rng->state = x;

	return x * 0x2545F4914F6CDD1DULL;
}

/* One fully status-prefixed message: a Channel Voice, System Common or
 * System Real-Time event. Real-Time events carry no data bytes.
 */
struct ploytec_midi_test_msg {
	u8 status;
	u8 data[2];
	u8 ndata;
};

/* --- The driver's documented queued-byte drain contract -------------------
 *
 * Mirrors jockey3_get_next_midi_out_byte()'s ordering: a byte already queued
 * from a previous expansion is always sent before any new input byte is
 * consumed.
 */
static size_t ploytec_midi_test_expand_stream(struct ploytec_midi_running_status *state,
					      const u8 *in, size_t in_len,
					      u8 *out, size_t out_cap)
{
	size_t ii = 0, oi = 0;

	while (ii < in_len) {
		u8 b;

		if (state->has_queued_byte) {
			state->has_queued_byte = false;
			b = state->queued_byte;
		} else {
			b = ploytec_midi_running_status_expand(state, in[ii++], NULL);
		}

		if (oi >= out_cap)
			return oi;
		out[oi++] = b;
	}

	if (state->has_queued_byte) {
		state->has_queued_byte = false;
		if (oi < out_cap)
			out[oi++] = state->queued_byte;
	}

	return oi;
}

/* --- Independent parser: no concept of Running Status at all -------------
 *
 * Fails the moment it sees a data byte with no status in effect, which is
 * exactly what "Running Status was not fully expanded" looks like on the
 * wire.
 */
static bool ploytec_midi_test_parse(struct kunit *test, const u8 *in, size_t in_len,
				    struct ploytec_midi_test_msg *out, size_t out_cap,
				    size_t *n_out)
{
	u8 status = 0, data[2];
	int expected = 0, have = 0;
	size_t n = 0;

	for (size_t i = 0; i < in_len; i++) {
		u8 b = in[i];

		if (b >= 0x80) {
			if (b >= 0xf8) {
				KUNIT_ASSERT_LT_MSG(test, n, out_cap,
						    "parsed message count exceeds capacity");
				out[n++] = (struct ploytec_midi_test_msg){ .status = b };
				continue;
			}

			status = b;
			have = 0;
			if (b < 0xf0) /* Channel Voice */
				expected = ((b & 0xf0) == 0xc0 || (b & 0xf0) == 0xd0) ? 1 : 2;
			else if (b == 0xf1 || b == 0xf3) /* MTC quarter frame, Song Select */
				expected = 1;
			else if (b == 0xf2) /* Song Position Pointer */
				expected = 2;
			else /* SysEx start/end, Tune Request: no data bytes tracked here */
				expected = 0;

			if (expected == 0) {
				KUNIT_ASSERT_LT_MSG(test, n, out_cap,
						    "parsed message count exceeds capacity");
				out[n++] = (struct ploytec_midi_test_msg){ .status = status };
			}
			continue;
		}

		/* Data byte with nothing pending: Running Status was not expanded. */
		KUNIT_ASSERT_GT_MSG(test, expected, 0,
				    "naked data byte %#04x at offset %zu: Running Status was not fully expanded",
				    b, i);

		data[have++] = b;
		if (have == expected) {
			KUNIT_ASSERT_LT_MSG(test, n, out_cap,
					    "parsed message count exceeds capacity");
			out[n] = (struct ploytec_midi_test_msg){ .status = status, .ndata = have };
			memcpy(out[n].data, data, have);
			n++;
			expected = 0;
		}
	}

	KUNIT_EXPECT_EQ_MSG(test, expected, 0,
			    "input stream ended mid-message, %d data byte(s) still owed",
			    expected);

	*n_out = n;
	return true;
}

static void ploytec_midi_test_msg_expect_eq(struct kunit *test,
					    const struct ploytec_midi_test_msg *want,
					    const struct ploytec_midi_test_msg *got,
					    size_t idx)
{
	KUNIT_ASSERT_EQ_MSG(test, got->status, want->status,
			    "message %zu: status %#04x, expected %#04x",
			    idx, got->status, want->status);
	KUNIT_ASSERT_EQ_MSG(test, got->ndata, want->ndata,
			    "message %zu (status %#04x): %d data bytes, expected %d",
			    idx, want->status, got->ndata, want->ndata);
	for (int i = 0; i < want->ndata; i++)
		KUNIT_ASSERT_EQ_MSG(test, got->data[i], want->data[i],
				    "message %zu (status %#04x): data[%d] = %#04x, expected %#04x",
				    idx, want->status, i, got->data[i], want->data[i]);
}

/* --- Randomized round-trip property ---------------------------------------
 *
 * The compression rule below is the independent model: it decides on its
 * own bookkeeping (last_status) whether a Channel Voice status byte may be
 * omitted, without ever calling expand() to find out.
 */
static u8 ploytec_midi_test_realtime_byte(struct ploytec_midi_test_rng *rng)
{
	static const u8 bytes[] = { 0xf8, 0xf9, 0xfa, 0xfb, 0xfc, 0xfd, 0xfe, 0xff };

	return bytes[ploytec_midi_rng_next(rng) % ARRAY_SIZE(bytes)];
}

static void ploytec_midi_test_gen_channel_voice(struct ploytec_midi_test_rng *rng,
						struct ploytec_midi_test_msg *msg)
{
	static const u8 opcodes[] = { 0x80, 0x90, 0xa0, 0xb0, 0xc0, 0xd0, 0xe0 };
	u8 opcode = opcodes[ploytec_midi_rng_next(rng) % ARRAY_SIZE(opcodes)];
	u8 channel = ploytec_midi_rng_next(rng) & 0x0f;

	msg->status = opcode | channel;
	msg->ndata = (opcode == 0xc0 || opcode == 0xd0) ? 1 : 2;
	for (int i = 0; i < msg->ndata; i++)
		msg->data[i] = ploytec_midi_rng_next(rng) & 0x7f;
}

static void ploytec_midi_test_gen_system_common(struct ploytec_midi_test_rng *rng,
						struct ploytec_midi_test_msg *msg)
{
	static const u8 opcodes[] = { 0xf1, 0xf2, 0xf3 };
	u8 opcode = opcodes[ploytec_midi_rng_next(rng) % ARRAY_SIZE(opcodes)];

	msg->status = opcode;
	msg->ndata = (opcode == 0xf2) ? 2 : 1;
	for (int i = 0; i < msg->ndata; i++)
		msg->data[i] = ploytec_midi_rng_next(rng) & 0x7f;
}

static void ploytec_midi_test_round_trip_once(struct kunit *test,
					      struct ploytec_midi_test_rng *rng,
					      int iteration)
{
	struct ploytec_midi_test_msg expected[PLOYTEC_MIDI_TEST_MSG_MAX];
	struct ploytec_midi_test_msg actual[PLOYTEC_MIDI_TEST_MSG_MAX];
	struct ploytec_midi_running_status state = { };
	u8 in[PLOYTEC_MIDI_TEST_IN_CAP];
	u8 out[PLOYTEC_MIDI_TEST_OUT_CAP];
	size_t n_expected = 0, n_actual = 0, in_len = 0, out_len;
	u8 last_status = 0;
	int span = PLOYTEC_MIDI_TEST_MSG_MAX - PLOYTEC_MIDI_TEST_MSG_MIN;
	int count = PLOYTEC_MIDI_TEST_MSG_MIN + ploytec_midi_rng_next(rng) % span;

	for (int i = 0; i < count; i++) {
		struct ploytec_midi_test_msg msg = { };
		unsigned int pick = ploytec_midi_rng_next(rng) % 100;

		if (pick < 15) {
			msg.status = ploytec_midi_test_realtime_byte(rng);
		} else if (pick < 30) {
			ploytec_midi_test_gen_system_common(rng, &msg);
			last_status = 0;
		} else {
			ploytec_midi_test_gen_channel_voice(rng, &msg);
		}

		KUNIT_ASSERT_LT_MSG(test, n_expected, PLOYTEC_MIDI_TEST_MSG_MAX,
				    "iteration %d: generated message count exceeds capacity",
				    iteration);
		expected[n_expected++] = msg;

		if (msg.status >= 0xf8) {
			/* Real-Time: single byte, never affects Running Status. */
			KUNIT_ASSERT_LT_MSG(test, in_len, PLOYTEC_MIDI_TEST_IN_CAP,
					    "iteration %d: input stream exceeds capacity",
					    iteration);
			in[in_len++] = msg.status;
			continue;
		}

		/* Channel Voice with a repeated status may drop the status byte. */
		bool omit_status = msg.status < 0xf0 && msg.status == last_status &&
				    (ploytec_midi_rng_next(rng) & 1);

		KUNIT_ASSERT_LE_MSG(test, in_len + 1 + msg.ndata, PLOYTEC_MIDI_TEST_IN_CAP,
				    "iteration %d: input stream exceeds capacity", iteration);
		if (!omit_status)
			in[in_len++] = msg.status;
		for (int d = 0; d < msg.ndata; d++)
			in[in_len++] = msg.data[d];

		if (msg.status < 0xf0)
			last_status = msg.status;
	}

	out_len = ploytec_midi_test_expand_stream(&state, in, in_len, out, sizeof(out));
	KUNIT_ASSERT_LT_MSG(test, out_len, sizeof(out),
			    "iteration %d: expanded stream filled the output buffer",
			    iteration);

	ploytec_midi_test_parse(test, out, out_len, actual, PLOYTEC_MIDI_TEST_MSG_MAX, &n_actual);

	KUNIT_ASSERT_EQ_MSG(test, n_actual, n_expected,
			    "iteration %d: parsed %zu messages, generated %zu",
			    iteration, n_actual, n_expected);

	for (size_t i = 0; i < n_expected; i++)
		ploytec_midi_test_msg_expect_eq(test, &expected[i], &actual[i], i);
}

static void ploytec_midi_test_round_trip(struct kunit *test)
{
	struct ploytec_midi_test_rng rng;

	ploytec_midi_rng_init(&rng, 0x0123456789ABCDEFULL);

	for (int t = 0; t < PLOYTEC_MIDI_TEST_ITERATIONS; t++)
		ploytec_midi_test_round_trip_once(test, &rng, t);
}

/* --- Directed cases --------------------------------------------------------
 *
 * A small, hand-readable example. If this fails while the randomized
 * property also fails, this is the one to read first.
 */
static void ploytec_midi_test_note_on_running_status_basic(struct kunit *test)
{
	static const u8 in[] = { 0x90, 0x40, 0x7f, 0x41, 0x60, 0x42, 0x50 };
	static const u8 want[] = {
		0x90, 0x40, 0x7f,
		0x90, 0x41, 0x60,
		0x90, 0x42, 0x50,
	};
	struct ploytec_midi_running_status state = { };
	u8 out[sizeof(want)];
	size_t out_len;

	out_len = ploytec_midi_test_expand_stream(&state, in, sizeof(in), out, sizeof(out));

	KUNIT_ASSERT_EQ(test, out_len, sizeof(want));
	KUNIT_EXPECT_MEMEQ(test, out, want, sizeof(want));
}

static void ploytec_midi_test_program_change_running_status(struct kunit *test)
{
	/* PC and Channel Pressure take one data byte, not two. */
	static const u8 in[] = { 0xc3, 0x05, 0x07, 0x09 };
	static const u8 want[] = { 0xc3, 0x05, 0xc3, 0x07, 0xc3, 0x09 };
	struct ploytec_midi_running_status state = { };
	u8 out[sizeof(want)];
	size_t out_len;

	out_len = ploytec_midi_test_expand_stream(&state, in, sizeof(in), out, sizeof(out));

	KUNIT_ASSERT_EQ(test, out_len, sizeof(want));
	KUNIT_EXPECT_MEMEQ(test, out, want, sizeof(want));
}

static void ploytec_midi_test_realtime_leaves_state_untouched(struct kunit *test)
{
	struct ploytec_midi_running_status state = { };
	struct ploytec_midi_running_status before;

	/* Establish Running Status. */
	ploytec_midi_running_status_expand(&state, 0x91, NULL);
	ploytec_midi_running_status_expand(&state, 0x40, NULL);
	before = state;

	for (u8 b = 0xf8; b != 0; b++) {
		u8 got = ploytec_midi_running_status_expand(&state, b, NULL);

		KUNIT_EXPECT_EQ_MSG(test, got, b,
				    "Real-Time byte %#04x was not passed through unchanged", b);
		KUNIT_EXPECT_EQ_MSG(test, state.running_status, before.running_status,
				    "Real-Time byte %#04x disturbed running_status", b);
		KUNIT_EXPECT_EQ_MSG(test, state.expected_data, before.expected_data,
				    "Real-Time byte %#04x disturbed expected_data", b);
		KUNIT_EXPECT_EQ_MSG(test, state.data_count, before.data_count,
				    "Real-Time byte %#04x disturbed data_count", b);
		KUNIT_EXPECT_FALSE_MSG(test, state.has_queued_byte,
				       "Real-Time byte %#04x queued a byte", b);

		if (b == 0xff)
			break;
	}
}

static void ploytec_midi_test_system_common_clears_running_status(struct kunit *test)
{
	struct ploytec_midi_running_status state = { };
	u8 got;

	/* Establish Running Status with a complete Note On message. */
	ploytec_midi_running_status_expand(&state, 0x92, NULL);
	ploytec_midi_running_status_expand(&state, 0x40, NULL);
	ploytec_midi_running_status_expand(&state, 0x60, NULL);

	/* Song Select: one data byte, and it clears Running Status. */
	got = ploytec_midi_running_status_expand(&state, 0xf3, NULL);
	KUNIT_EXPECT_EQ(test, got, 0xf3);
	got = ploytec_midi_running_status_expand(&state, 0x02, NULL);
	KUNIT_EXPECT_EQ(test, got, 0x02);

	KUNIT_ASSERT_EQ(test, state.running_status, 0);

	/* A bare data byte now has nothing to expand against. */
	got = ploytec_midi_running_status_expand(&state, 0x55, NULL);
	KUNIT_EXPECT_EQ_MSG(test, got, 0x55,
			    "data byte was expanded even though System Common cleared Running Status");
	KUNIT_EXPECT_FALSE(test, state.has_queued_byte);
}

static void ploytec_midi_test_sysex_clears_running_status(struct kunit *test)
{
	struct ploytec_midi_running_status state = { };
	u8 got;

	ploytec_midi_running_status_expand(&state, 0x93, NULL);
	ploytec_midi_running_status_expand(&state, 0x40, NULL);
	ploytec_midi_running_status_expand(&state, 0x60, NULL);

	got = ploytec_midi_running_status_expand(&state, 0xf0, NULL); /* SysEx start */
	KUNIT_EXPECT_EQ(test, got, 0xf0);
	got = ploytec_midi_running_status_expand(&state, 0x7d, NULL); /* payload byte */
	KUNIT_EXPECT_EQ_MSG(test, got, 0x7d, "SysEx payload byte was not passed through raw");
	got = ploytec_midi_running_status_expand(&state, 0xf7, NULL); /* SysEx end */
	KUNIT_EXPECT_EQ(test, got, 0xf7);

	KUNIT_ASSERT_EQ(test, state.running_status, 0);

	got = ploytec_midi_running_status_expand(&state, 0x55, NULL);
	KUNIT_EXPECT_EQ_MSG(test, got, 0x55,
			    "data byte was expanded even though SysEx cleared Running Status");
}

/*
 * A data byte arriving with no status ever seen -- e.g. because rawmidi
 * output opened mid-stream -- has nothing to expand against. This pins that
 * as documented behavior, not an oversight.
 */
static void ploytec_midi_test_leading_data_byte_passthrough(struct kunit *test)
{
	struct ploytec_midi_running_status state = { };
	u8 got = ploytec_midi_running_status_expand(&state, 0x40, NULL);

	KUNIT_EXPECT_EQ(test, got, 0x40);
	KUNIT_EXPECT_FALSE(test, state.has_queued_byte);
	KUNIT_EXPECT_EQ(test, state.running_status, 0);
}

/* --- Suite ---------------------------------------------------------------- */

static struct kunit_case ploytec_midi_test_cases[] = {
	KUNIT_CASE(ploytec_midi_test_note_on_running_status_basic),
	KUNIT_CASE(ploytec_midi_test_program_change_running_status),
	KUNIT_CASE(ploytec_midi_test_realtime_leaves_state_untouched),
	KUNIT_CASE(ploytec_midi_test_system_common_clears_running_status),
	KUNIT_CASE(ploytec_midi_test_sysex_clears_running_status),
	KUNIT_CASE(ploytec_midi_test_leading_data_byte_passthrough),
	KUNIT_CASE(ploytec_midi_test_round_trip),
	{},
};

static struct kunit_suite ploytec_midi_suite = {
	.name = "ploytec-midi",
	.test_cases = ploytec_midi_test_cases,
};

kunit_test_suite(ploytec_midi_suite);
