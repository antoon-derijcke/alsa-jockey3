#!/usr/bin/env python3
#
# OpenVizsla Transaction Log Reducer
#
# parse_openvizsla.py turns a raw wire capture into one line per completed USB
# transaction.  That is still dominated by the audio streams: at 44.1 kHz the
# device moves ~200 bulk packets per second on each of EP 0x05 and EP 0x86, so
# a capture of a few seconds is hundreds of megabytes of payload that carries
# no information about the control-plane sequence we are trying to compare.
#
# This script collapses those runs.  A run of consecutive bulk transactions is
# printed as its first and last few packets with an elision marker in between
# that records how many were dropped, over what time span, and per endpoint --
# because "how much stream did the device see before it accepted the next
# control transfer" is itself one of the questions being asked.  Everything on
# EP0 is kept in full and annotated with the decoded Ploytec request.
#
# The result is a few hundred KB that can be diffed between captures and
# between platforms.
#
# (C) 2026 Frank van de Pol
#

import argparse
import os
import re
import sys

# One line of parse_openvizsla.py output:
#   3.313631     | OUT        | 7.5      | 512   | 00 00 03 ...
TX_PATTERN = re.compile(
	r"^\s*(?P<timestamp>[\d.]+)\s*\|"
	r"\s*(?P<direction>\S+)\s*\|"
	r"\s*(?P<target>\S*)\s*\|"
	r"\s*(?P<nbytes>\d+)\s*\|"
	r"\s*(?P<payload>.*?)\s*$"
)

# bRequest / bmRequestType pairs from ploytec_proto.h.  Keyed on both because
# the same bRequest 0x49 is used for get and set status, distinguished only by
# the direction bit in bmRequestType.
PLOYTEC_REQUESTS = {
	(0x22, 0x01): "SET_RATE",
	(0xA2, 0x81): "GET_RATE",
	(0x40, 0x49): "SET_STATUS",
	(0xC0, 0x49): "GET_STATUS",
	(0xC0, 0x56): "GET_FIRMWARE",
}

# Standard requests that show up in the init sequence.
STANDARD_REQUESTS = {
	(0x01, 0x0B): "SET_INTERFACE",
	(0x00, 0x0B): "SET_INTERFACE",
	(0x02, 0x01): "CLEAR_FEATURE(ENDPOINT_HALT)",
	(0x00, 0x05): "SET_ADDRESS",
	(0x00, 0x09): "SET_CONFIGURATION",
	(0x80, 0x06): "GET_DESCRIPTOR",
	(0x02, 0x03): "SET_FEATURE(ENDPOINT_HALT)",
}


def endpoint_of(target):
	"""Endpoint number from a "addr.ep" target string, or None.

	The device address is not stable across captures (the traces hold both
	8.5/8.6 and 7.5/7.6 for the same endpoints), so nothing may key on the
	full target string.
	"""
	if not target or "." not in target:
		return None
	try:
		return int(target.rsplit(".", 1)[1])
	except ValueError:
		return None


def parse_tx_line(line):
	match = TX_PATTERN.match(line)
	if not match:
		return None
	data = match.groupdict()

	payload = data["payload"]
	if payload == "[]":
		payload_bytes = []
	else:
		payload_bytes = payload.split()

	return {
		"timestamp": float(data["timestamp"]),
		"direction": data["direction"],
		"target": data["target"],
		"ep": endpoint_of(data["target"]),
		"nbytes": int(data["nbytes"]),
		"bytes": payload_bytes,
	}


def decode_setup(payload_bytes):
	"""Render an 8-byte SETUP packet as a readable request description."""
	if len(payload_bytes) != 8:
		return None
	try:
		b = [int(x, 16) for x in payload_bytes]
	except ValueError:
		return None

	bm_request_type, b_request = b[0], b[1]
	w_value = b[2] | (b[3] << 8)
	w_index = b[4] | (b[5] << 8)
	w_length = b[6] | (b[7] << 8)

	key = (bm_request_type, b_request)
	name = PLOYTEC_REQUESTS.get(key) or STANDARD_REQUESTS.get(key)
	if name is None:
		name = f"bRequest=0x{b_request:02x}"

	fields = [name]
	if name == "SET_INTERFACE":
		fields.append(f"intf={w_index} alt={w_value}")
	elif name.startswith("CLEAR_FEATURE") or name.startswith("SET_FEATURE"):
		fields.append(f"ep=0x{w_index:02x}")
	elif name in ("SET_RATE", "GET_RATE"):
		# wIndex carries the endpoint the rate applies to.  A wIndex of 0
		# is not an endpoint; the vendor drivers use it for a device-wide
		# read, which is worth seeing as distinct from a per-endpoint one.
		target = f"ep=0x{w_index:02x}" if w_index else "ep=none"
		fields.append(f"{target} wValue=0x{w_value:04x}")
	else:
		if w_value:
			fields.append(f"wValue=0x{w_value:04x}")
		if w_index:
			fields.append(f"wIndex=0x{w_index:04x}")
	if w_length:
		fields.append(f"len={w_length}")

	return " ".join(fields)


def format_payload(payload_bytes, head, tail):
	"""Truncate long payloads to a head and a tail slice.

	The tail matters: the MIDI OUT byte lives at offset 480 and the sync
	byte at 481, so a head-only truncation throws away the two bytes of a
	playback packet that are not audio.
	"""
	if not payload_bytes:
		return "[]"
	if len(payload_bytes) <= head + tail:
		return " ".join(payload_bytes)
	omitted = len(payload_bytes) - head - tail
	return "{} ... [{} bytes] ... {}".format(
		" ".join(payload_bytes[:head]),
		omitted,
		" ".join(payload_bytes[-tail:]),
	)


class Reducer:
	def __init__(self, args, out):
		self.args = args
		self.out = out
		self.run = []			# pending consecutive stream transactions
		self.prev_timestamp = None	# for the delta column
		self.prev_real = None		# for the capture-integrity check
		self.backward_jumps = 0
		self.n_input = 0
		self.n_output = 0
		self.n_elided = 0

	def is_stream(self, tx):
		# Aggregated NAK/STALL records are never elided: they are already a
		# summary, and they are the point of asking for them.
		if tx["direction"] in ("NAK", "STALL"):
			return False
		if tx["ep"] is None or tx["ep"] == 0:
			return False
		if self.args.stream_ep == "all":
			return True
		return tx["ep"] in self.args.stream_ep

	def emit(self, text):
		self.out.write(text + "\n")
		self.n_output += 1

	def emit_tx(self, tx):
		if self.args.delta and self.prev_timestamp is not None:
			delta_ms = (tx["timestamp"] - self.prev_timestamp) * 1000.0
			delta = f"{delta_ms:>9.3f}"
		elif self.args.delta:
			delta = f"{0.0:>9.3f}"
		else:
			delta = None

		payload = format_payload(tx["bytes"], self.args.head_bytes,
					 self.args.tail_bytes)

		annotation = ""
		if tx["direction"] == "SETUP":
			decoded = decode_setup(tx["bytes"])
			if decoded:
				annotation = f"   <- {decoded}"

		fields = [f"{tx['timestamp']:<12.6f}"]
		if delta is not None:
			fields.append(delta)
		fields += [
			f"{tx['direction']:<10}",
			f"{tx['target']:<8}",
			f"{tx['nbytes']:<5}",
			payload + annotation,
		]
		self.emit(" | ".join(fields))
		self.prev_timestamp = tx["timestamp"]

	def emit_elision(self, elided):
		"""Elision marker for a block of dropped stream transactions.

		Carries count, span and a per-endpoint breakdown, so the reduced
		log can still answer how much stream flowed between two control
		transfers without going back to the full parse.
		"""
		span = elided[-1]["timestamp"] - elided[0]["timestamp"]
		breakdown = {}
		for tx in elided:
			key = (tx["direction"], tx["target"])
			breakdown[key] = breakdown.get(key, 0) + 1
		parts = ", ".join(
			f"{count} {direction} {target}"
			for (direction, target), count in sorted(breakdown.items())
		)
		self.emit(
			".... {} transactions omitted over {:.6f} s "
			"({:.6f} -> {:.6f}): {}".format(
				len(elided), span,
				elided[0]["timestamp"], elided[-1]["timestamp"],
				parts,
			)
		)
		self.n_elided += len(elided)
		# The elided block did advance time; the next delta must be
		# measured from the last transaction actually seen, not from the
		# last one printed before the marker.
		self.prev_timestamp = elided[-1]["timestamp"]

	def flush_run(self):
		"""Print a pending run of stream transactions, collapsed."""
		if not self.run:
			return
		head, tail = self.args.head_packets, self.args.tail_packets
		if len(self.run) <= head + tail:
			for tx in self.run:
				self.emit_tx(tx)
		else:
			for tx in self.run[:head]:
				self.emit_tx(tx)
			self.emit_elision(self.run[head:len(self.run) - tail])
			for tx in self.run[len(self.run) - tail:]:
				self.emit_tx(tx)
		self.run = []

	def feed(self, tx):
		self.n_input += 1

		# Aggregated NAK/STALL records carry a synthetic position and may
		# sit marginally out of order, so they are excluded from the
		# integrity check entirely -- both as the thing compared and as the
		# thing compared against.
		if tx["direction"] not in ("NAK", "STALL"):
			if self.prev_real is not None and tx["timestamp"] < self.prev_real:
				self.backward_jumps += 1
			self.prev_real = tx["timestamp"]

		if self.is_stream(tx):
			self.run.append(tx)
		else:
			self.flush_run()
			self.emit_tx(tx)

	def finish(self):
		self.flush_run()


def build_parser():
	parser = argparse.ArgumentParser(
		description="Reduce a parsed OpenVizsla transaction log by "
			    "collapsing the bulk audio streams.")
	parser.add_argument("input", help="parsed transaction log, or - for stdin")
	parser.add_argument("-o", "--output",
			    help="output file (default: <input>_reduced.txt, "
				 "or stdout when reading stdin)")
	parser.add_argument("--stream-ep", type=str, default="5,6",
			    help="comma-separated endpoint numbers to treat as "
				 "bulk stream (default: 5,6, which keeps MIDI "
				 "IN on EP 0x83 visible), or \"all\" for every "
				 "endpoint except EP0 -- the mode to use when "
				 "the subject is the control plane")
	parser.add_argument("--head-packets", type=int, default=3,
			    help="stream packets kept at the start of a run (default: 3)")
	parser.add_argument("--tail-packets", type=int, default=3,
			    help="stream packets kept at the end of a run (default: 3)")
	parser.add_argument("--head-bytes", type=int, default=16,
			    help="payload bytes kept at the start of a packet (default: 16)")
	parser.add_argument("--tail-bytes", type=int, default=32,
			    help="payload bytes kept at the end of a packet "
				 "(default: 32, enough to cover the MIDI OUT and "
				 "sync bytes at offsets 480/481)")
	parser.add_argument("--start", type=float, default=None,
			    help="drop transactions before this timestamp (seconds)")
	parser.add_argument("--end", type=float, default=None,
			    help="drop transactions after this timestamp (seconds)")
	parser.add_argument("--no-delta", dest="delta", action="store_false",
			    help="omit the inter-transaction delta column")
	return parser


def main():
	args = build_parser().parse_args()

	if args.stream_ep.strip().lower() == "all":
		args.stream_ep = "all"
	else:
		try:
			args.stream_ep = {int(x) for x in args.stream_ep.split(",")
					  if x.strip()}
		except ValueError:
			sys.exit(f"error: --stream-ep must be \"all\" or "
				 f"comma-separated integers, got {args.stream_ep!r}")

	if args.input == "-":
		infile = sys.stdin
		out_path = args.output
	else:
		infile = open(args.input, "r", encoding="ascii", errors="replace")
		if args.output:
			out_path = args.output
		else:
			root, ext = os.path.splitext(args.input)
			out_path = f"{root}_reduced{ext or '.txt'}"

	if out_path == "-":
		out_path = None
	outfile = open(out_path, "w", encoding="ascii") if out_path else sys.stdout

	try:
		header = ["{:<12}".format("Timestamp")]
		if args.delta:
			header.append("{:>9}".format("d(ms)"))
		header += ["{:<10}".format("Direction"), "{:<8}".format("Target"),
			   "{:<5}".format("Bytes"), "Payload Data"]
		outfile.write(" | ".join(header) + "\n")
		outfile.write("-" * 100 + "\n")

		reducer = Reducer(args, outfile)
		n_lines = 0
		for line in infile:
			n_lines += 1
			tx = parse_tx_line(line)
			if tx is None:
				continue
			if args.start is not None and tx["timestamp"] < args.start:
				continue
			if args.end is not None and tx["timestamp"] > args.end:
				break
			reducer.feed(tx)
		reducer.finish()
	finally:
		if infile is not sys.stdin:
			infile.close()
		if outfile is not sys.stdout:
			outfile.close()

	print(f"Read {n_lines} lines, {reducer.n_input} transactions.",
	      file=sys.stderr)
	print(f"Wrote {reducer.n_output} lines to {out_path or 'stdout'} "
	      f"({reducer.n_elided} stream transactions elided).", file=sys.stderr)
	if reducer.backward_jumps:
		# A capture with a discontinuous timeline cannot support any
		# timing conclusion, so this must be loud rather than buried.
		print(f"WARNING: {reducer.backward_jumps} backward timestamp "
		      f"jump(s) -- the capture may have dropped packets, and "
		      f"timing analysis on it is not trustworthy.", file=sys.stderr)


if __name__ == "__main__":
	try:
		main()
	except BrokenPipeError:
		# Normal when the output is piped into head(1); say nothing.
		sys.stderr.close()
		sys.exit(0)
