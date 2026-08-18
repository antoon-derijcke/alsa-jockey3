#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Fully disable (and re-enable) PipeWire/WirePlumber on this machine.
#
#   sound_server.sh disable
#   sound_server.sh enable
#
# `systemctl --user stop pipewire.service` is not enough: pipewire.socket
# stays listening and auto-respawns pipewire.service the instant anything
# touches it, which includes PipeWire's own ALSA monitor reacting to a card
# appearing -- exactly what happens mid cold-boot test. `disable` masks every
# unit in the chain so nothing can bring it back until `enable` undoes it.
#
# wireplumber.service has no socket of its own; it is pulled in by
# pipewire.service (Requires=) and D-Bus session activation, so masking
# pipewire's units is enough to keep it down too, but it is masked directly
# as well for a clear state independent of that wiring.
#
# `mask` rather than `stop`/`disable` because a masked unit refuses to start
# even via socket or D-Bus activation, not just via systemctl or boot -- the
# only kind of "off" that survives a device appearing mid-test.

set -eu

UNITS=(pipewire.socket pipewire.service pipewire-pulse.socket
       pipewire-pulse.service wireplumber.service)

case "${1:-}" in
disable)
	echo "stopping and masking: ${UNITS[*]}"
	systemctl --user stop "${UNITS[@]}" || true
	systemctl --user mask "${UNITS[@]}"
	;;
enable)
	echo "unmasking and starting: ${UNITS[*]}"
	systemctl --user unmask "${UNITS[@]}"
	systemctl --user start pipewire.socket pipewire-pulse.socket wireplumber.service
	;;
*)
	echo "usage: $0 disable|enable" >&2
	exit 2
	;;
esac

systemctl --user is-active --quiet pipewire.socket && state=active || state=inactive
echo "pipewire.socket is now $state"
