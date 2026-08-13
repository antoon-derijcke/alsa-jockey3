#
# OpenVizsla USB Capture Parser
#
# The OpenViszla records USB traffic at the wire level, including all the
# low-level protocol handshake packets.  For our analysis to reverse
# engineer the Reloop Jockey 3 protocol this is far too detailed.  The
# purpose of this script to reduce the level op detail by parsing the USB
# transactions.
# 
# (C) 2026 Frank van de Pol
#

import sys
import os
import re
from pathlib import Path

# Same base regex to parse the raw line components
LOG_PATTERN = re.compile(
	r"^\[(?P<flags>[^\]]+)\]\s+"
	r"(?P<timestamp>[\d.]+)\s+"
	r"d=\s*(?P<delta>[\d.]+)\s+"
	r"\[\s*(?P<frame>[\d.]+)\s*\+\s*(?P<uframe>[\d.]+)\s*\]\s+"
	r"\[\s*(?P<len_info>\d+)\s*\]"
	r"(?:\s+(?P<packet_info>.*))?$"
)

def endpoint_of(target):
	"""Endpoint number from a "addr.ep" target string, or None."""
	if not target or "." not in target:
		return None
	try:
		return int(target.rsplit(".", 1)[1])
	except ValueError:
		return None


def parse_line(line):
	match = LOG_PATTERN.match(line.strip())
	if not match: return None
	data = match.groupdict()

	if data.get("packet_info") is None:
		return None
	else:
		packet_info = data.get("packet_info", "").strip()
	p_type, p_target, p_bytes = None, None, []

	if ":" in packet_info:
		p_type, remainder = packet_info.split(":", 1)
		p_type = p_type.strip()
		remainder = remainder.strip()
		if re.match(r'^([0-9a-fA-F]{2}\s*)+$', remainder):
			p_bytes = remainder.split()
		else:
			p_target = remainder
	else:
		p_type = packet_info

	return {
		"timestamp": float(data["timestamp"]),
		"type": p_type,
		"target": p_target,
		"bytes": p_bytes
	}

def extract_transactions(log_lines, report_errors=False, error_gap=0.005,
			 error_max=0.1, error_eps=None, error_min=2):
	"""Yield completed transactions as they are recognized.

	This is a generator rather than a list builder because the raw captures
	reach 2.25 GB; nothing may hold the whole trace, or even the whole
	transaction list, in memory.

	NAK and STALL are dropped by default. A NAK is ordinary USB flow control
	-- the device says "not yet", the host retries, and the transfer usually
	completes a few microseconds later -- so keeping them per packet would
	bury the trace in noise, which is why the glitch-hunting workflow this
	parser was written for discards them.

	They matter when a transfer *fails*. With @report_errors, runs of NAK and
	STALL are collapsed into one record per burst, carrying the target, the
	counts, the span, and whether the burst was followed by a successful
	transaction on the same target. An unresolved burst is a transfer the
	device never accepted; a STALL is the device actively refusing. Both are
	invisible in the default output, and in a failed initialization they are
	the evidence.

	A burst is closed by a success on the same target, or by @error_gap
	seconds of quiet on it, or by @error_max seconds elapsing, or by end of
	input. The record is emitted at the point the burst closes rather than
	where it began, so the output stays monotonic in time; the true span is
	in the record itself.

	Each record says how the burst ended, and the distinction is the whole
	point:

	  resolved   a success followed on the same target -- ordinary flow
	             control, the overwhelmingly common case
	  abandoned  the target went quiet with no success: the host gave up,
	             which is what a failed transfer looks like
	  ongoing    still NAKing when the record was cut. Continuous NAK on an
	             idle interrupt endpoint is normal -- MIDI IN polls forever
	             and NAKs whenever nobody has touched a control -- so these
	             are context, not faults

	The @error_max cap exists for that last case: without it an idle MIDI
	endpoint produces a single burst spanning the entire capture, which is
	both useless and hides everything else.

	@error_eps restricts aggregation to a set of endpoint numbers. Passing
	{0} is usually what is wanted: a control transfer that is not accepted is
	always a fault, whereas the bulk and interrupt endpoints NAK as a matter
	of routine and swamp everything else if included.

	@error_min suppresses *resolved* bursts smaller than it. Practically
	every control transfer on this device NAKs once before it is accepted, so
	reporting those adds a line per transfer and says nothing. Bursts that
	were abandoned, are still ongoing, or contain a STALL are always
	reported regardless of size.
	"""
	current_tx = None
	bursts = {}		# target -> accumulating NAK/STALL record
	# Burst records are placed where the burst began, but traffic on other
	# endpoints may already have been emitted from later in the trace, so the
	# position is clamped to keep the output non-decreasing in time. The true
	# span is carried in the record text either way. A handful can still land
	# marginally out of order, when a transfer that started before the burst
	# closed is only acknowledged after it; downstream tools therefore leave
	# these records out of any capture-integrity check.
	last_emitted = [0.0]

	def make_record(target, burst, close_time, outcome):
		span_ms = (burst["last"] - burst["first"]) * 1000.0
		parts = []
		if burst["nak"]:
			parts.append(f"NAK x{burst['nak']}")
		if burst["stall"]:
			parts.append(f"STALL x{burst['stall']}")
		if (outcome == "resolved" and not burst["stall"] and
		    burst["nak"] + burst["stall"] < error_min):
			return None
		close_time = max(close_time, last_emitted[0])
		last_emitted[0] = close_time
		return {
			"start_time": close_time,
			"type": "STALL" if burst["stall"] else "NAK",
			"target": target,
			"data": None,
			"status": "SUCCESS" if outcome == "resolved" else "FAILED",
			"note": "[{} over {:.3f} ms from {:.6f}, {}]".format(
				" ".join(parts), span_ms, burst["first"], outcome),
			"count": burst["nak"] + burst["stall"],
		}

	def expire(now):
		"""Close bursts that have gone quiet or run past the cap."""
		for target in [t for t, b in bursts.items()
			       if now - b["last"] > error_gap
			       or now - b["first"] > error_max]:
			burst = bursts.pop(target)
			outcome = ("abandoned" if now - burst["last"] > error_gap
				   else "ongoing")
			record = make_record(target, burst, now, outcome)
			if record:
				yield record

	for line in log_lines:
		parsed = parse_line(line)
		if not parsed or not parsed["type"]:
			continue

		p_type = parsed["type"]

		if report_errors:
			yield from expire(parsed["timestamp"])

		# 1. Start of a new transaction block (SETUP, IN, OUT tokens)
		if p_type in ["SETUP", "IN", "OUT"]:
			current_tx = {
				"start_time": parsed["timestamp"],
				"type": p_type,
				"target": parsed["target"],
				"data": None,
				"status": None
			}
			continue

		if current_tx is None:
			continue

		# 2. Capture payload phase
		if "DATA" in p_type:
			raw_bytes = parsed["bytes"]
			if len(raw_bytes) >= 2:
				# Slice off the last 2 bytes (the CRC16)
				current_tx["data"] = raw_bytes[:-2]
			else:
				# If it's somehow less than 2 bytes, keep it as is
				current_tx["data"] = raw_bytes			
			continue

		# 3. Handshake phase (closes the transaction)
		# Treat NYET identically to ACK since data was accepted by the device
		if p_type in ["ACK", "NYET"]:
			# The device accepted, so any burst on this target resolved.
			if report_errors and current_tx["target"] in bursts:
				resolved = bursts.pop(current_tx["target"])
				record = make_record(current_tx["target"], resolved,
						     resolved["first"], "resolved")
				if record:
					yield record
			current_tx["status"] = "SUCCESS"
			last_emitted[0] = max(last_emitted[0], current_tx["start_time"])
			# Only emit transactions that actually completed cleanly with data or setup tokens
			yield current_tx
			current_tx = None
		elif p_type in ["NAK", "STALL"]:
			# Ordinary flow control unless the burst never resolves; see
			# the docstring. The transaction itself is still discarded,
			# because the host will retry it as a fresh token.
			if report_errors and (error_eps is None or
					      endpoint_of(current_tx["target"]) in error_eps):
				burst = bursts.setdefault(current_tx["target"],
							  {"nak": 0, "stall": 0,
							   "first": parsed["timestamp"],
							   "last": parsed["timestamp"]})
				burst["nak" if p_type == "NAK" else "stall"] += 1
				burst["last"] = parsed["timestamp"]
			current_tx = None

	if report_errors:
		# Close the remainder at one common time, so the output stays
		# monotonic rather than stepping back to each burst's own end.
		close = max((b["last"] for b in bursts.values()), default=0.0)
		for target, burst in list(bursts.items()):
			record = make_record(target, burst, close, "ongoing")
			if record:
				yield record



def main():

	args = [a for a in sys.argv[1:] if not a.startswith("--errors")]
	error_flag = [a for a in sys.argv[1:] if a.startswith("--errors")]
	report_errors = bool(error_flag)
	error_eps = None
	if error_flag and "=" in error_flag[0]:
		try:
			error_eps = {int(x) for x in error_flag[0].split("=", 1)[1].split(",") if x.strip()}
		except ValueError:
			sys.exit("error: --errors=<eps> takes comma-separated endpoint numbers, e.g. --errors=0")

	if not args:
		print("Usage: {} [--errors] <input_file> [output_file|-]".format(
			os.path.basename(sys.argv[0])))
		print("  Use - for the output file to write to stdout, so the parse")
		print("  can be piped straight into reduce_transactions.py without")
		print("  materializing the intermediate, which for the larger")
		print("  captures is over a gigabyte.")
		print()
		print("  --errors[=EPS]  also emit aggregated NAK/STALL bursts. Off")
		print("            by default: a NAK is ordinary flow control and")
		print("            keeping them buries the trace. Turn it on when")
		print("            investigating a transfer that failed -- an")
		print("            'abandoned' burst is one the host gave up on.")
		print("            EPS restricts it to those endpoint numbers;")
		print("            --errors=0 gives control transfers only, which")
		print("            is usually what is wanted, since the bulk and")
		print("            interrupt endpoints NAK as a matter of routine.")
		print("            Resolved bursts under 2 events are suppressed,")
		print("            since nearly every transfer NAKs once; abandoned")
		print("            and STALL bursts are always reported.")
		sys.exit(1)

	filename = args[0].strip()

	if len(args) > 1:
		parsed_filename = args[1].strip()
	else:
		path = Path(filename)
		parsed_filename = str(path.with_name(f"{path.stem}_parsed{path.suffix}"))

	to_stdout = parsed_filename == "-"

	infile = sys.stdin if filename == "-" else open(filename, "r", encoding="ascii")
	out_file = sys.stdout if to_stdout else open(parsed_filename, "w", encoding="ascii")
	try:
		out_file.write(f"{'Timestamp':<12} | {'Direction':<10} | {'Target':<8} | {'Bytes'} | {'Payload Data'}\n")
		out_file.write("-" * 100 + "\n")

		count = 0
		errors = 0
		unresolved = 0
		for tx in extract_transactions(infile, report_errors=report_errors,
					       error_eps=error_eps):
			if "note" in tx:
				# An aggregated NAK/STALL burst rather than a transfer.
				out_file.write(f"{tx['start_time']:<12.6f} | {tx['type']:<10} | {tx['target']:<8} | {tx['count']:<5} | {tx['note']}\n")
				errors += 1
				if tx["status"] == "FAILED":
					unresolved += 1
				continue
			# Format payload bytes cleanly or indicate no data (e.g., zero-length packets)
			data_str = " ".join(tx["data"]) if tx["data"] else "[]"
			data_len = len(tx["data"]) if tx["data"] else 0
			out_file.write(f"{tx['start_time']:<12.6f} | {tx['type']:<10} | {tx['target']:<8} | {data_len:<5} | {data_str}\n")
			count += 1
	finally:
		if infile is not sys.stdin:
			infile.close()
		if out_file is not sys.stdout:
			out_file.close()

	print(f"Extracted {count} successful transactions.", file=sys.stderr)
	if report_errors:
		print(f"Aggregated {errors} NAK/STALL bursts, {unresolved} unresolved.",
		      file=sys.stderr)


if __name__ == "__main__":
	try:
		main()
	except BrokenPipeError:
		# Normal when the output is piped into head(1); say nothing.
		sys.stderr.close()
		sys.exit(0)
