/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 *   ALSA driver for Reloop Jockey 3 devices
 *   Ploytec USB Protocol Handling
 *
 *   Copyright (c) 2026 by Frank van de Pol <fvdpol@gmail.com>
 */

#ifndef PLOYTEC_PROTO_H
#define PLOYTEC_PROTO_H

#include <linux/types.h>
#include <linux/usb.h>

/* Ploytec Protocol Constants */
#define PLOYTEC_PKT_SIZE 512

/* Playback & MIDI Out (EP 0x05) */
#define PLOYTEC_EP_NUM_PCM_OUT	0x05
#define PLOYTEC_PLAYBACK_FRAMES	10	// number of samples per Frame
#define PLOYTEC_PLAYBACK_FRAME_SIZE 48
#define PLOYTEC_MIDI_OUT_OFFSET 480	// location of MIDI data in the playback packet
#define PLOYTEC_MIDI_IDLE_BYTE	0xFD	// send when no MIDI data is available
#define PLOYTEC_SYNC_BYTE_OFFSET 481
#define PLOYTEC_SYNC_BYTE_VALUE 0xFF

/* Capture (EP 0x86) */
#define PLOYTEC_EP_NUM_PCM_IN	0x06		// 0x86 & 0x0F
#define PLOYTEC_CAPTURE_FRAMES	8	// number of samples per frame
#define PLOYTEC_CAPTURE_FRAME_SIZE 64

/* MIDI In (EP 0x83) */
#define PLOYTEC_EP_NUM_MIDI_IN	0x03		// 0x83 & 0x0F

/* Protocol Commands */
#define PLOYTEC_SET_RATE        0x01	// bRequest to set sample rate
#define PLOYTEC_SET_RATE_TYPE   0x22	// bmRequestType to set sample rate
#define PLOYTEC_REQ_STATUS      0x49	// bRequest to get device status
#define PLOYTEC_REQ_FIRMWARE    0x56	// bRequest to get firmware version
#define PLOYTEC_REQ_GET_RATE    0x81	// bRequest to get current sample rate

/* Status Bits */
#define PLOYTEC_STATUS_BIT0     0x01
#define PLOYTEC_STATUS_BIT1     0x02
#define PLOYTEC_STATUS_BIT2     0x04
#define PLOYTEC_STATUS_BIT3     0x08
#define PLOYTEC_STATUS_BIT4     0x10
#define PLOYTEC_STATUS_READY    0x20

/* Bit-shuffling codec for S24_3LE (3 bytes per sample) */
void ploytec_encode_s24_3le(u8 *dest, const u8 *src);
void ploytec_decode_s24_3le(u8 *dest, const u8 *src);

struct ploytec_midi_state {
	int expected_data;	// number data bytes for the 'running status' voice message
	int data_count;
	u8 running_status;	// the 'running status' (voice message)
	u8 queued_byte;
	bool has_queued_byte;
};

/* MIDI protocol state machine */
u8 ploytec_midi_running_status(struct ploytec_midi_state *state, u8 b, struct device *dev);

/* Protocol Helpers */
void ploytec_prepare_out_packet(u8 *buf);
int ploytec_handshake_step(struct usb_device *dev, void *xfer_buf);
int ploytec_get_rate(struct usb_device *dev, void *xfer_buf, u32 *rate);
int ploytec_set_rate(struct usb_device *dev, void *xfer_buf, u32 rate);

#endif /* PLOYTEC_PROTO_H */
