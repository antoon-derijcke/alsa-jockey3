// SPDX-License-Identifier: GPL-2.0-or-later
/*
 *   ALSA driver for Reloop Jockey 3 devices
 *   Ploytec USB Protocol Handling
 *
 *   Copyright (c) 2026 by Frank van de Pol <fvdpol@gmail.com>
 */

#include <linux/delay.h>
#include "ploytec_proto.h"

/*
 * None of the helpers below validate @intf/@xfer_buf for NULL: callers own
 * the chip's usb_interface and control-transfer buffer for the entire time
 * the PCM/rawmidi devices can be open, so these arguments are always valid
 * here.
 */

/**
 * ploytec_ctrl_ep_unresponsive - Has the control endpoint stopped answering?
 * @err: error returned by an EP0 control transfer
 *
 * Distinguishes a device that answered -- even to refuse -- from one whose
 * control endpoint has gone silent. A STALL (-EPIPE) or a short reply
 * (-EREMOTEIO) both mean live firmware: the transfer completed and the device
 * drove the bus. A timeout or a transport-level error means EP0 itself is gone,
 * and every further control transfer will only burn another
 * PLOYTEC_CTRL_TIMEOUT_MS before failing the same way.
 *
 * The list is affirmative rather than an exclusion, so an unfamiliar error
 * counts as "device still there" and a new class has to be added deliberately.
 *
 * Return: true if EP0 has stopped responding.
 */
static bool ploytec_ctrl_ep_unresponsive(int err)
{
	switch (err) {
	case -ETIMEDOUT:
	case -ENODEV:
	case -ESHUTDOWN:
	case -ECONNRESET:
	case -EPROTO:
	case -EILSEQ:
	case -ETIME:
		return true;
	default:
		return false;
	}
}

/**
 * ploytec_get_firmware - Read firmware version from the device
 * @intf: USB interface
 * @xfer_buf: Temporary transfer buffer (at least 3 bytes)
 *
 * Performs a request to the device to retrieve the firmware and/or hardware version.
 * We aren't doing anything useful with the firmware version yet, but it seems to be
 * required to request as per the USB traces.
 *
 * Return: 0 on success, negative errno on failure.
 */
int ploytec_get_firmware(struct usb_interface *intf, void *xfer_buf)
{
	struct usb_device *dev = interface_to_usbdev(intf);
	u8 *buf = xfer_buf;
	int ret;

	ret = usb_control_msg_recv(dev, 0, PLOYTEC_REQ_FIRMWARE, PLOYTEC_REQ_FIRMWARE_TYPE, 0, 0,
				   buf, 3, PLOYTEC_CTRL_TIMEOUT_MS, GFP_KERNEL);
	if (ret < 0)
		return ret;

	// device with firmware v1.0.3  returns: 0x31, 0x01, 0x03
	// device with firmware v1.0.6  returns: 0x31, 0x01, 0x06
	// buf[0] = 0x31, educated guess this may be hardware model/revision
	dev_dbg(&intf->dev, "Firmware 0x%02x v%d.%d.%d\n", buf[0],
		buf[1], buf[2] >> 4, buf[2] & 0x0F);
	return 0;
}

/**
 * ploytec_get_status - Read device status byte
 * @intf: USB interface
 * @xfer_buf: Temporary transfer buffer (at least 1 byte)
 * @status: Pointer to store the status byte
 *
 * Return: 0 on success, negative errno on failure.
 */
int ploytec_get_status(struct usb_interface *intf, void *xfer_buf, u8 *status)
{
	struct usb_device *dev = interface_to_usbdev(intf);
	u8 *buf = xfer_buf;
	int ret;

	// Read Status (Request 0x49)
	ret = usb_control_msg_recv(dev, 0, PLOYTEC_REQ_STATUS, PLOYTEC_REQ_STATUS_TYPE, 0, 0,
				   buf, 1, PLOYTEC_CTRL_TIMEOUT_MS, GFP_KERNEL);
	if (ret < 0)
		return ret;

	*status = buf[0];
	return 0;
}

/**
 * ploytec_initialize_device - Perform Ploytec handshake sequence as observed in USB traces.
 * @intf: USB interface
 * @xfer_buf: Temporary transfer buffer
 * @bounce_alt0: drive both interfaces to alt 0 before selecting alt 1, which
 *	the vendors do only when changing the rate of a running device
 *
 * Aborts early if EP0 stops responding, rather than continuing into the
 * alt-setting sequence below; see the comment on the firmware read for why
 * that distinction matters.
 *
 * Return: 0 on success, negative errno on failure.
 */
int ploytec_initialize_device(struct usb_interface *intf, void *xfer_buf, bool bounce_alt0)
{
	struct usb_device *dev = interface_to_usbdev(intf);
	const unsigned int halt_pipes[] = {
		usb_rcvbulkpipe(dev, PLOYTEC_EP_NUM_PCM_IN),
		usb_sndbulkpipe(dev, PLOYTEC_EP_NUM_PCM_OUT),
		usb_rcvbulkpipe(dev, PLOYTEC_EP_NUM_MIDI_IN),
	};
	u8 status;
	unsigned int i;
	int ret;

	/*
	 * USB trace shows we need to read firmware version after power-up. The
	 * value itself is unused, but this is the first EP0 transfer of the
	 * sequence and therefore the last point at which the usb_set_interface()
	 * calls below can still be avoided -- which is what makes its return
	 * load-bearing. usb_set_interface() disables the interface's endpoints
	 * before it sends SET_INTERFACE and does not re-enable them if that
	 * request fails, so calling it on a device whose control endpoint has
	 * already gone silent leaves every endpoint of interface 0 permanently
	 * disabled, and usb_submit_urb() returns -ENOENT until the device is
	 * reset. A device that merely refuses the request is fine; one that has
	 * stopped answering is not.
	 */
	ret = ploytec_get_firmware(intf, xfer_buf);
	if (ret < 0) {
		dev_warn(&intf->dev, "Firmware version read failed: %d\n", ret);
		if (ploytec_ctrl_ep_unresponsive(ret))
			return ret;
	}

	/*
	 * Deactivate the audio interfaces before reactivating them, but only
	 * when the device is already running. On a device that has just been
	 * enumerated the interfaces are at alt 0 anyway, and neither vendor
	 * driver touches alt 0 there: all 29 captured cold initializations go
	 * straight to alt 1. macOS does bounce on a rate change, and takes
	 * interface 1 down first, which is the order used here.
	 */
	if (bounce_alt0) {
		ret = usb_set_interface(dev, 1, 0);
		if (ret < 0)
			return ret;
		ret = usb_set_interface(dev, 0, 0);
		if (ret < 0)
			return ret;

		/* Give the hardware some time to respond, otherwise it might not be ready */
		usleep_range(3000, 5000);
	}

	// Select Alt Setting 1 to activate the audio interface
	ret = usb_set_interface(dev, 0, 1);
	if (ret < 0)
		return ret;
	ret = usb_set_interface(dev, 1, 1);
	if (ret < 0)
		return ret;

	/*
	 * Clear Feature (ENDPOINT_HALT). A failure here has never been fatal on
	 * a device that is still answering, so only a silent EP0 aborts -- which
	 * also avoids burning two more PLOYTEC_CTRL_TIMEOUT_MS on the remaining
	 * pipes once the first one has timed out.
	 */
	for (i = 0; i < ARRAY_SIZE(halt_pipes); i++) {
		ret = usb_clear_halt(dev, halt_pipes[i]);
		if (ret < 0) {
			dev_warn(&intf->dev, "Failed to clear halt on EP 0x%02x: %d\n",
				 usb_pipeendpoint(halt_pipes[i]) |
					(usb_pipein(halt_pipes[i]) ? USB_DIR_IN : 0),
				 ret);
			if (ploytec_ctrl_ep_unresponsive(ret))
				return ret;
		}
	}

	return ploytec_get_status(intf, xfer_buf, &status);
}

/**
 * ploytec_start_streaming - Trigger the device to start streaming as observed in USB traces.
 * @intf: USB interface
 * @xfer_buf: Temporary transfer buffer
 *
 * Reads the status byte and writes it back with the STREAMING bit set. The
 * write is unconditional, which is the whole point: the device already
 * reports STREAMING set after a rate change, so a conditional write is never
 * issued there at all.
 *
 * Every macOS and Windows rate change ends with this write -- 115 of 115
 * across the OpenVizsla corpus, always the same value, always from a device
 * whose own status read in the same sequence had already returned it. This
 * driver instead ended a rate change with a second status *read*, and its
 * capture endpoint fails to restart after roughly one rate change in six
 * (against one in 58 on macOS and none in 56 on Windows). The write
 * evidently does more than set a bit, the same lesson the rate writes taught
 * in jockey3_set_rate(). See re/rate_change_stall.md.
 *
 * The vendors do not read the status back afterwards, so neither do we.
 *
 * Return: 0 on success, negative errno on failure.
 */
int ploytec_start_streaming(struct usb_interface *intf, void *xfer_buf)
{
	struct usb_device *dev = interface_to_usbdev(intf);
	u8 status;
	int ret;

	ret = ploytec_get_status(intf, xfer_buf, &status);
	if (ret < 0)
		return ret;
	dev_dbg(&intf->dev, "Start Streaming: Status: 0x%02x\n", status);

	return usb_control_msg_send(dev, 0, PLOYTEC_SET_STATUS, PLOYTEC_SET_STATUS_TYPE,
				    status | PLOYTEC_STATUS_STREAMING,
				    0, NULL, 0, PLOYTEC_CTRL_TIMEOUT_MS, GFP_KERNEL);
}

/**
 * ploytec_get_rate - Read hardware sample rate
 * @intf: USB interface
 * @xfer_buf: Temporary transfer buffer
 * @index: wIndex to read from -- PLOYTEC_RATE_IDX_DEVICE before programming,
 *	PLOYTEC_RATE_IDX_PCM_IN to verify afterwards
 * @rate: Pointer to store the rate
 *
 * The wIndex is not cosmetic. The vendor drivers always read the current rate
 * with a wIndex of zero and always verify with the capture endpoint, and the
 * captures show the device answering both. Reading the device-wide form
 * tracks the live rate: in capture_macos_rate_change it follows the
 * programmed value through 44100, 48000, 88200 and 96000 Hz.
 *
 * Return: 0 on success, negative errno on failure.
 */
int ploytec_get_rate(struct usb_interface *intf, void *xfer_buf, u16 index, u32 *rate)
{
	struct usb_device *dev = interface_to_usbdev(intf);
	u8 *buf = xfer_buf;
	int ret;

	ret = usb_control_msg_recv(dev, 0, PLOYTEC_REQ_GET_RATE, PLOYTEC_REQ_GET_RATE_TYPE,
				   0x0100, index,
				   buf, 3, PLOYTEC_CTRL_TIMEOUT_MS, GFP_KERNEL);
	if (ret < 0)
		return ret;

	*rate = (u32)buf[0] | ((u32)buf[1] << 8) | ((u32)buf[2] << 16);
	return 0;
}

/**
 * ploytec_set_rate - Set hardware sample rate
 * @intf: USB interface
 * @xfer_buf: Temporary transfer buffer
 * @rate: Sample rate in Hz
 * @cold_init: true when this programs the rate as part of bringing the device
 *	up, false when it changes the rate of a device already running
 *
 * The vendor drivers use two shapes here, and the difference is not cosmetic
 * -- see re/usb/init_timing_comparison.md. Both end the burst on the capture
 * endpoint and verify from it, which is the invariant that holds across all
 * 58 captured vendor sequences on both platforms:
 *
 *	cold init:	          <14 ms>  86 05 86 05 86  read back <50 ms>
 *	rate change:	<50 ms> 86 <10 ms>  86 05 86 05 86  read back <50 ms>
 *
 * The write count itself is not load-bearing -- the captures show between
 * five and seven, varying within a single platform -- but no vendor sequence
 * ends the burst anywhere other than the capture endpoint, and none verifies
 * against the playback endpoint.
 *
 * The ~50 ms windows are periods in which the vendor host sends nothing at
 * all: the raw traces show no tokens, no NAKs and no retries in them, so the
 * driver is waiting rather than polling. Their width is stable to under 4%
 * across 58 sequences and does not vary with the sample rate.
 *
 * Return: 0 on success (including when the post-write rate verification
 * detects a mismatch, which is only logged), negative errno if a control
 * transfer fails.
 */
int ploytec_set_rate(struct usb_interface *intf, void *xfer_buf, u32 rate, bool cold_init)
{
	static const u16 burst_index[] = {
		PLOYTEC_RATE_IDX_PCM_IN,
		PLOYTEC_RATE_IDX_PCM_OUT,
		PLOYTEC_RATE_IDX_PCM_IN,
		PLOYTEC_RATE_IDX_PCM_OUT,
		PLOYTEC_RATE_IDX_PCM_IN,
	};
	struct usb_device *dev = interface_to_usbdev(intf);
	u8 *buf = xfer_buf;
	u32 current_hw_rate = 0;
	unsigned int i;
	int ret;

	dev_dbg(&intf->dev, "Setting rate %u Hz (%s)\n",
		rate, cold_init ? "cold init" : "rate change");

	buf[0] = rate & 0xFF;
	buf[1] = (rate >> 8) & 0xFF;
	buf[2] = (rate >> 16) & 0xFF;

	if (cold_init) {
		/*
		 * macOS leaves ~14 ms between reading the rate and starting to
		 * program it on a fresh device, and no separate first write.
		 */
		usleep_range(14000, 15000);
	} else {
		/*
		 * A rate change waits before touching the rate at all. Measured
		 * at 50.2-51.2 ms on macOS; Windows leaves the same window a
		 * little earlier in its sequence. See the quiet-window note
		 * above.
		 */
		usleep_range(50000, 51000);

		ret = usb_control_msg_send(dev, 0, PLOYTEC_SET_RATE, PLOYTEC_SET_RATE_TYPE,
					   0x0100, PLOYTEC_RATE_IDX_PCM_IN,
					   buf, 3, PLOYTEC_CTRL_TIMEOUT_MS, GFP_KERNEL);
		if (ret < 0) {
			dev_err(&intf->dev, "Failed to set rate on EP 0x86: %d\n", ret);
			return ret;
		}

		/*
		 * A rate change writes once, pauses, then repeats the burst.
		 * Observed at 10.5-11.2 ms on macOS and 6-23 ms on Windows.
		 */
		usleep_range(10000, 11000);
	}

	for (i = 0; i < ARRAY_SIZE(burst_index); i++) {
		ret = usb_control_msg_send(dev, 0, PLOYTEC_SET_RATE, PLOYTEC_SET_RATE_TYPE,
					   0x0100, burst_index[i],
					   buf, 3, PLOYTEC_CTRL_TIMEOUT_MS, GFP_KERNEL);
		if (ret < 0) {
			dev_err(&intf->dev, "Failed to set rate on EP 0x%02x: %d\n",
				burst_index[i], ret);
			return ret;
		}
	}

	if (ploytec_get_rate(intf, xfer_buf, PLOYTEC_RATE_IDX_PCM_IN, &current_hw_rate) == 0) {
		if (current_hw_rate != rate)
			dev_warn(&intf->dev, "Rate mismatch! Requested %u Hz, Hardware at %u Hz\n",
				 rate, current_hw_rate);
		else
			dev_dbg(&intf->dev, "Rate verified as %u Hz\n", current_hw_rate);
	}

	/*
	 * Every vendor sequence goes quiet for ~50 ms between verifying the rate
	 * and programming the status byte, and the caller's next step is
	 * ploytec_start_streaming(). Measured at 50.2-51.1 ms across both
	 * platforms and independent of the rate, so there is nothing to scale.
	 */
	usleep_range(50000, 51000);

	return 0;
}
