// SPDX-License-Identifier: GPL-2.0-or-later
/*
 *   ALSA driver for Reloop Jockey 3 devices
 *   Ploytec USB Protocol Handling
 *
 *   Copyright (c) 2026 by Frank van de Pol <fvdpol@gmail.com>
 */

#include <linux/delay.h>
#include "ploytec_proto.h"

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
void ploytec_encode_s24_3le(u8 *dest, const u8 *src)
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
void ploytec_decode_s24_3le(u8 *dest, const u8 *src)
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

/**
 * ploytec_prepare_out_packet - Prepare a playback packet with default sync/MIDI padding
 * @buf: 512-byte destination buffer
 *
 * Sets the initial pattern: MIDI slot (480) is idle (0xFD), sync byte is
 * set to 0xFF at offset 481, and the padding gap (482-511) is zero-filled.
 */
void ploytec_prepare_out_packet(u8 *buf)
{
	memset(buf, 0, PLOYTEC_PKT_SIZE);
	buf[PLOYTEC_MIDI_OUT_OFFSET] = PLOYTEC_MIDI_IDLE_BYTE;
	buf[PLOYTEC_SYNC_BYTE_OFFSET] = PLOYTEC_SYNC_BYTE_VALUE;
}

/**
 * ploytec_get_firmware - Read firmware version from the device
 * @dev: USB device
 * @xfer_buf: Temporary transfer buffer (at least 3 bytes)
 *
 * Performs a request to the device to retrieve the firmware and/or hardware version.
 * We are doing anything useful with the firmware version yet, but it seems to be required
 * to request as per the USB traces.
 */
int ploytec_get_firmware(struct usb_device *dev, void *xfer_buf)
{
	u8 *buf = xfer_buf;
	int ret;

	if (!dev)
		return -ENODEV;
	if (!xfer_buf)
		return -EINVAL;

	ret = usb_control_msg_recv(dev, 0, PLOYTEC_REQ_FIRMWARE, PLOYTEC_REQ_FIRMWARE_TYPE, 0, 0,
				   buf, 3, 2000, GFP_KERNEL);
	if (ret < 0)
		return ret;

	// device with firmware v1.0.3  returns: 0x31, 0x01, 0x03
	// device with firmware v1.0.6  returns: 0x31, 0x01, 0x06
	// buf[0] = 0x31, educated guess this may be hardware model/revision
	pr_debug("ploytec: Firmware  0x%02x v%d.%d.%d\n", buf[0],
		 buf[1], buf[2] >> 4, buf[2] & 0x0F);
	return 0;
}

int ploytec_get_status(struct usb_device *dev, void *xfer_buf)
{
	u8 *buf = xfer_buf;
	int ret;

	if (!dev)
		return -ENODEV;
	if (!xfer_buf)
		return -EINVAL;

	/* Read Status (Request 0x49) */
	ret = usb_control_msg_recv(dev, 0, PLOYTEC_REQ_STATUS, PLOYTEC_REQ_STATUS_TYPE, 0, 0,
				   buf, 1, 2000, GFP_KERNEL);
	if (ret < 0)
		return ret;

	return buf[0];
}

/**
 * ploytec_initialise_device - Perform Ploytec handshake sequence as observed in USB traces.
 * @dev: USB device
 * @xfer_buf: Temporary transfer buffer
 */
int ploytec_initialise_device(struct usb_device *dev, void *xfer_buf)
{
	int ret;

	// USB trace shows we need to read firmware version after power-up
	ploytec_get_firmware(dev, xfer_buf);

	// Select Alt Setting 0 to deactivates the audio interface
	ret = usb_set_interface(dev, 0, 0);
	if (ret < 0)
		return ret;
	ret = usb_set_interface(dev, 1, 0);
	if (ret < 0)
		return ret;

	/* Give the hardware some time to respond, otherwise it might not be ready */
	usleep_range(3000, 5000);

	// Select Alt Setting 1 to activate the audio interface
	ret = usb_set_interface(dev, 0, 1);
	if (ret < 0)
		return ret;
	ret = usb_set_interface(dev, 1, 1);
	if (ret < 0)
		return ret;

	// Clear Feature (ENDPOINT_HALT):
	usb_clear_halt(dev, usb_rcvbulkpipe(dev, 0x86));
	usb_clear_halt(dev, usb_sndbulkpipe(dev, 0x05));
	usb_clear_halt(dev, usb_rcvbulkpipe(dev, 0x83));

	return ploytec_get_status(dev, xfer_buf);
}

/**
 * ploytec_start_streaming - Trigger the device to start streaming as observed in USB traces.
 * @dev: USB device
 * @xfer_buf: Temporary transfer buffer
 */
int ploytec_start_streaming(struct usb_device *dev, void *xfer_buf)
{
	u8 status;
	int ret;

	if (!dev)
		return -ENODEV;
	if (!xfer_buf)
		return -EINVAL;

	status = ploytec_get_status(dev, xfer_buf);
	pr_debug("ploytec: Start Streaming: Status: 0x%02x\n", status);

	/* Enable device if STREAMING bit is not set */
	if (!(status & PLOYTEC_STATUS_STREAMING)) {
		ret = usb_control_msg_send(dev, 0, PLOYTEC_REQ_STATUS, 0x40,
					   (uint16_t)((status | PLOYTEC_STATUS_STREAMING) & 0xFF),
					   0, NULL, 0, 2000, GFP_KERNEL);
		if (ret < 0)
			return ret;
	}
	return ploytec_get_status(dev, xfer_buf);
}

/**
 * ploytec_get_rate - Read hardware sample rate
 * @dev: USB device
 * @xfer_buf: Temporary transfer buffer
 * @rate: Pointer to store the rate
 */
int ploytec_get_rate(struct usb_device *dev, void *xfer_buf, u32 *rate)
{
	u8 *buf = xfer_buf;
	int ret;

	if (!dev)
		return -ENODEV;
	if (!xfer_buf)
		return -EINVAL;

	/* Read rate from Playback EP 0x05 */
	ret = usb_control_msg_recv(dev, 0, PLOYTEC_REQ_GET_RATE, PLOYTEC_REQ_GET_RATE_TYPE,
				   0x0100, PLOYTEC_EP_NUM_PCM_OUT | USB_DIR_OUT,
				   buf, 3, 2000, GFP_KERNEL);
	if (ret < 0)
		return ret;

	*rate = (u32)buf[0] | ((u32)buf[1] << 8) | ((u32)buf[2] << 16);
	return 0;
}

/**
 * ploytec_set_rate - Set hardware sample rate
 * @dev: USB device
 * @xfer_buf: Temporary transfer buffer
 * @rate: Sample rate in Hz
 */
int ploytec_set_rate(struct usb_device *dev, void *xfer_buf, u32 rate)
{
	u8 *buf = xfer_buf;
	u32 current_hw_rate = 0;
	int ret;

	if (!dev)
		return -ENODEV;
	if (!xfer_buf)
		return -EINVAL;

	ploytec_get_rate(dev, xfer_buf, &current_hw_rate);
	pr_debug("ploytec: Setting rate %u Hz (current hw rate: %u Hz)\n",
		 rate, current_hw_rate);

	buf[0] = rate & 0xFF;
	buf[1] = (rate >> 8) & 0xFF;
	buf[2] = (rate >> 16) & 0xFF;

	/* Set rate on Capture EP 0x86 */
	ret = usb_control_msg_send(dev, 0, PLOYTEC_SET_RATE, PLOYTEC_SET_RATE_TYPE,
				   0x0100, PLOYTEC_EP_NUM_PCM_IN | USB_DIR_IN,
				   buf, 3, 2000, GFP_KERNEL);
	if (ret < 0) {
		pr_err("ploytec: Failed to set rate on EP 0x86: %d\n", ret);
		return ret;
	}

	/* 10ms delay to allow device to process the command, as per MacOS driver behavior */
	usleep_range(10000, 11000);

	/* and after that delay the device is repeatedly "hammered" with rate again... */
	for (int i = 0; i < 3; i++) {
		/* Set rate on Capture EP 0x86 */
		ret = usb_control_msg_send(dev, 0, PLOYTEC_SET_RATE, PLOYTEC_SET_RATE_TYPE,
					   0x0100, PLOYTEC_EP_NUM_PCM_IN | USB_DIR_IN,
					   buf, 3, 2000, GFP_KERNEL);
		if (ret < 0) {
			pr_err("ploytec: Failed to set rate on EP 0x86: %d\n", ret);
			return ret;
		}

		/* Set rate on Playback EP 0x05 */
		ret = usb_control_msg_send(dev, 0, PLOYTEC_SET_RATE, PLOYTEC_SET_RATE_TYPE,
					   0x0100, PLOYTEC_EP_NUM_PCM_OUT | USB_DIR_OUT,
					   buf, 3, 2000, GFP_KERNEL);
		if (ret < 0) {
			pr_err("ploytec: Failed to set rate on EP 0x05: %d\n", ret);
			return ret;
		}
	}

	if (ploytec_get_rate(dev, xfer_buf, &current_hw_rate) == 0) {
		if (current_hw_rate != rate)
			pr_warn("ploytec: Rate mismatch! Requested %u Hz, Hardware at %u Hz\n",
				rate, current_hw_rate);
		else
			pr_debug("ploytec: Rate verified as %u Hz\n", current_hw_rate);
	}

	return 0;
}

/**
 * ploytec_midi_process_byte - Expand MIDI running status
 * @state: The MIDI state machine instance
 * @b: The raw MIDI byte
 * @dev: Pointer to the struct device for logging
 *
 * The Ploytec firmware does not handle MIDI Running Status. To avoid data issues processing
 * valid MIDI streams with Running Status, we implement a simple state machine to expand the
 * Running Status messages into full MIDI messages before sending them to the device.
 */
u8 ploytec_midi_running_status(struct ploytec_midi_state *state, u8 b, struct device *dev)
{
	u8 byte;

	if (b >= 0x80) { // Status byte
		if (b < 0xf0) { // Channel Voice Message (0x80-0xEF)
			state->running_status = b;
			/* Determine expected data bytes based on MIDI opcode */
			if ((b & 0xf0) == 0xc0 || (b & 0xf0) == 0xd0)
				state->expected_data = 1; // PC, Channel Pressure
			else
				state->expected_data = 2; // Note On/Off, CC, etc.
		} else if (b < 0xf8) { // System Common Message (0xf0-0xf7)
			/* System Common messages clear Running Status */
			state->running_status = 0;
			state->expected_data = 0;
		} else { // System Real-Time Message (0xf8-0xff), do not affect Running Status
			return b;
		}

		state->data_count = state->expected_data; // initialise expected data byte count
		return b;
	}

	/* Data byte */
	if (state->data_count > 0) {
		state->data_count--;
		return b;
	} else if (state->running_status >= 0x80) {
		/* Message is complete but we got a data byte -> expand Running Status */
		byte = state->running_status;
		state->queued_byte = b;
		state->has_queued_byte = true;
		state->data_count = state->expected_data - 1; // already 1 byte queued
		return byte;
	}

	/* No running status expansion active, just send the data byte */
	return b;
}
