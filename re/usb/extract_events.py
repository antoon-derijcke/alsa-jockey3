#!/usr/bin/env python3
#
# Control-Plane Event Extractor
#
# Reduces a parsed (or reduced) OpenVizsla transaction log to just the EP0
# control sequences, grouped into "events" -- a burst of control transfers
# separated from the next burst by an idle gap.  In practice each event is one
# initialization or one rate change.
#
# The output is deliberately normalized: absolute timestamps are replaced by
# an offset from the start of the event, so two captures taken minutes apart
# on different machines can be diffed directly.  Each transfer carries the gap
# from the previous one, because the question this exists to answer is whether
# the vendor drivers use fixed delays or wait on the device.
#
# Two output modes:
#   --format detail   one line per control transfer, with gaps (default)
#   --format summary  one line per event, plus a gap table across events
#
# (C) 2026 Frank van de Pol
#

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reduce_transactions import parse_tx_line, decode_setup  # noqa: E402


def collect_transfers(lines, stream_eps=(5, 6)):
	"""Fold EP0 transactions into whole control transfers.

	A control transfer on the wire is a SETUP, an optional data stage and a
	status stage.  Folding them into one record is what makes the sequence
	readable and diffable; the SETUP timestamp is the one that matters for
	timing, and the completion timestamp is kept so a slow device response
	is still visible.

	Stream packets are counted rather than kept, so that each transfer can
	report how much audio flowed since the previous one -- the discriminator
	between "the device needs N packets" and "the device needs T seconds".
	"""
	transfers = []
	current = None
	stream_since = 0
	stream_bytes_since = 0

	for line in lines:
		tx = parse_tx_line(line)
		if tx is None:
			continue

		if tx["ep"] != 0:
			if tx["ep"] in stream_eps:
				stream_since += 1
				stream_bytes_since += tx["nbytes"]
			continue

		if tx["direction"] == "SETUP":
			if current is not None:
				transfers.append(current)
			current = {
				"start": tx["timestamp"],
				"end": tx["timestamp"],
				"setup": tx["bytes"],
				"decoded": decode_setup(tx["bytes"]) or "?",
				"data": None,
				"stream_since": stream_since,
				"stream_bytes_since": stream_bytes_since,
			}
			stream_since = 0
			stream_bytes_since = 0
			continue

		if current is None:
			continue

		current["end"] = tx["timestamp"]
		# The data stage is the non-zero-length one; the status stage is
		# always zero length and in the opposite direction.
		if tx["nbytes"] > 0 and current["data"] is None:
			current["data"] = tx["bytes"]

	if current is not None:
		transfers.append(current)
	return transfers


def group_events(transfers, gap):
	"""Split the transfer list into events on an idle gap."""
	events = []
	current = []
	for transfer in transfers:
		if current and (transfer["start"] - current[-1]["end"]) > gap:
			events.append(current)
			current = []
		current.append(transfer)
	if current:
		events.append(current)
	return events


def classify(event):
	"""Name an event from the requests it contains."""
	names = [t["decoded"].split()[0] for t in event]
	has = set(names)
	if "SET_INTERFACE" in has and "SET_RATE" in has:
		return "init+rate"
	if "SET_INTERFACE" in has:
		return "init"
	if "SET_RATE" in has:
		return "rate-change"
	if "GET_DESCRIPTOR" in has:
		return "enumeration"
	return "control"


def rate_of(transfer):
	"""Decode a 3-byte little-endian sample rate from a transfer's data."""
	data = transfer["data"]
	if not data or len(data) != 3:
		return None
	try:
		b = [int(x, 16) for x in data]
	except ValueError:
		return None
	return b[0] | (b[1] << 8) | (b[2] << 16)


def describe(transfer):
	"""Full description of a transfer, with the payload interpreted."""
	text = transfer["decoded"]
	rate = rate_of(transfer)
	if rate is not None and "RATE" in text:
		text += f" -> {rate} Hz"
	elif transfer["data"]:
		text += " -> " + " ".join(transfer["data"])
	return text


def write_detail(events, out, label):
	out.write(f"# Control-plane events: {label}\n")
	out.write("#\n")
	out.write("# t(ms) is relative to the first transfer of the event.\n")
	out.write("# gap(ms) is from the completion of the previous transfer.\n")
	out.write("# stream is bulk packets seen on EP 0x05/0x86 since the "
		  "previous transfer.\n\n")

	for index, event in enumerate(events, 1):
		start = event[0]["start"]
		out.write("=" * 96 + "\n")
		out.write(f"EVENT {index}  [{classify(event)}]  "
			  f"at {start:.6f} s, {len(event)} transfers, "
			  f"span {(event[-1]['end'] - start) * 1000:.3f} ms\n")
		out.write("=" * 96 + "\n")
		out.write(f"{'t(ms)':>10} | {'gap(ms)':>9} | {'dur(us)':>8} | "
			  f"{'stream':>6} | Request\n")
		out.write("-" * 96 + "\n")
		previous_end = None
		for transfer in event:
			gap = ("" if previous_end is None
			       else f"{(transfer['start'] - previous_end) * 1000:9.3f}")
			out.write("{:10.3f} | {:>9} | {:8.1f} | {:6} | {}\n".format(
				(transfer["start"] - start) * 1000,
				gap,
				(transfer["end"] - transfer["start"]) * 1e6,
				transfer["stream_since"],
				describe(transfer),
			))
			previous_end = transfer["end"]
		out.write("\n")


def write_summary(events, out, label):
	out.write(f"# Control-plane event summary: {label}\n\n")
	out.write(f"{'#':>3} | {'kind':<12} | {'at (s)':>12} | {'n':>4} | "
		  f"{'span (ms)':>10} | requests\n")
	out.write("-" * 110 + "\n")
	for index, event in enumerate(events, 1):
		counts = {}
		for transfer in event:
			name = transfer["decoded"].split()[0]
			counts[name] = counts.get(name, 0) + 1
		requests = " ".join(f"{name}x{count}"
				    for name, count in sorted(counts.items()))
		out.write("{:3} | {:<12} | {:12.6f} | {:4} | {:10.3f} | {}\n".format(
			index, classify(event), event[0]["start"], len(event),
			(event[-1]["end"] - event[0]["start"]) * 1000, requests,
		))


def main():
	parser = argparse.ArgumentParser(
		description="Extract and time the EP0 control sequences from a "
			    "parsed OpenVizsla transaction log.")
	parser.add_argument("input", help="parsed or reduced log, or - for stdin")
	parser.add_argument("-o", "--output", help="output file (default: stdout)")
	parser.add_argument("--format", choices=("detail", "summary"),
			    default="detail", help="output format (default: detail)")
	parser.add_argument("--event-gap", type=float, default=0.25,
			    help="idle seconds on EP0 that separate two events "
				 "(default: 0.25)")
	parser.add_argument("--kind", default=None,
			    help="only show events of this kind "
				 "(init, rate-change, init+rate, enumeration)")
	args = parser.parse_args()

	infile = sys.stdin if args.input == "-" else open(
		args.input, "r", encoding="ascii", errors="replace")
	try:
		transfers = collect_transfers(infile)
	finally:
		if infile is not sys.stdin:
			infile.close()

	events = group_events(transfers, args.event_gap)
	if args.kind:
		events = [e for e in events if classify(e) == args.kind]

	label = os.path.basename(args.input)
	outfile = open(args.output, "w", encoding="ascii") if args.output else sys.stdout
	try:
		if args.format == "detail":
			write_detail(events, outfile, label)
		else:
			write_summary(events, outfile, label)
	finally:
		if outfile is not sys.stdout:
			outfile.close()

	print(f"{len(transfers)} control transfers in {len(events)} events.",
	      file=sys.stderr)


if __name__ == "__main__":
	main()
