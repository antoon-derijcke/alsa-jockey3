#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Play a real audio file to the device, for JT-AUDIO-003.
#
#   play_file.sh <file> [rate]
#
# Real content, listened to, is the only test that catches codec packing
# errors as they actually manifest -- as distortion rather than as a wrong
# byte. No automated check here would add anything the ear does not already
# do better.
#
# sox handles the decode and the rate conversion so the device sees exactly
# the format it accepts, rather than relying on plughw to paper over a
# mismatch. Testing through plughw would test the conversion plugin.
#
# Derived from play_flac.sh in ../../scripts-alsa-dev.

set -u

FILE=${1:-}
RATE=${2:-44100}
DEVICE=${JT_DEVICE:-hw:RJ3}

[ -n "$FILE" ] || { echo "usage: play_file.sh <file> [rate]" >&2; exit 2; }
[ -f "$FILE" ] || { echo "no such file: $FILE" >&2; exit 2; }
command -v sox >/dev/null || { echo "sox not installed" >&2; exit 3; }

echo "playing $(basename "$FILE") at ${RATE} Hz -> $DEVICE"

# The pipe is part of what gets tested here, and that is worth knowing when
# something crackles. aplay is fed by sox through a pipe, so every refill is a
# syscall pair and the audio only stays clean while sox keeps ahead. On a KASAN
# kernel that chain is measurably slower -- KASAN instruments kernel code, and
# every byte across the pipe crosses it -- so a marginal chain can starve aplay
# and produce an underrun that has nothing to do with the driver.
#
# To take the pipe out of the loop, decode once and play the file:
#
#   sox "$FILE" -r 44100 -c 4 -b 24 -e signed-integer -t raw /tmp/x.raw remix 1 2 1 2
#   aplay -D hw:RJ3 -r 44100 -c 4 --format S24_3LE -t raw /tmp/x.raw
#
# If the crackle goes away, it was the supply chain, not the driver. That is
# the first thing to establish, because everything downstream of it is a
# different investigation.
#
# -r on the sox side is not optional: without it sox emits the file's native
# rate while aplay is told $RATE, which plays at the wrong pitch. The archive
# copy of this script (scripts-alsa-dev/play_flac.sh) omits it.
#
# Upmix stereo to the device's four channels: Master L/R and Headphone L/R get
# the same signal, so both outputs can be checked from one pass.
sox "$FILE" -r "$RATE" -c 4 -b 24 -e signed-integer -t raw - remix 1 2 1 2 \
	| aplay -D "$DEVICE" -r "$RATE" -c 4 --format S24_3LE -t raw
