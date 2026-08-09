#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Install the privileged helper and grant it passwordless sudo.
#
#   sudo ./install.sh            install/update
#   sudo ./install.sh --remove   undo completely
#   ./install.sh --check         report status, needs no privilege
#
# Run this once per test machine. It asks for a password because it is the
# step that grants the privilege; nothing after it needs one.

set -eu

SRC_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HELPER_SRC=$SRC_DIR/jockey3-testctl
HELPER=/usr/local/sbin/jockey3-testctl
SUDOERS=/etc/sudoers.d/jockey3-testing
USER_NAME=${SUDO_USER:-$USER}

check() {
	echo "helper:  $HELPER"
	if [ -x "$HELPER" ]; then
		local owner
		owner=$(stat -c '%U:%G %a' "$HELPER")
		echo "  installed, $owner"
		if cmp -s "$HELPER_SRC" "$HELPER"; then
			echo "  up to date with $HELPER_SRC"
		else
			echo "  *** DIFFERS from $HELPER_SRC -- re-run install.sh"
		fi
	else
		echo "  not installed"
	fi
	echo "sudoers: $SUDOERS"
	[ -f "$SUDOERS" ] && echo "  present" || echo "  absent"
	printf 'usable:  '
	if sudo -n "$HELPER" status >/dev/null 2>&1; then
		echo "yes -- passwordless"
	else
		echo "NO -- 'sudo -n $HELPER status' failed"
	fi
}

if [ "${1:-}" = "--check" ]; then
	check
	exit 0
fi

[ "$(id -u)" = 0 ] || {
	echo "must run as root: sudo $0 $*" >&2
	exit 1
}

if [ "${1:-}" = "--remove" ]; then
	rm -f "$HELPER" "$SUDOERS"
	echo "removed $HELPER and $SUDOERS"
	exit 0
fi

[ -f "$HELPER_SRC" ] || { echo "no helper at $HELPER_SRC" >&2; exit 2; }
bash -n "$HELPER_SRC" || { echo "helper has a syntax error" >&2; exit 2; }

# Root-owned and not writable by the user it grants privilege to. This is the
# entire point of copying it out of the repository: the working tree is on a
# Seafile share and is user-writable, so granting sudo to it in place would
# let any local write become root.
install -o root -g root -m 0755 "$HELPER_SRC" "$HELPER"
echo "installed $HELPER"

# Validate into a temporary file first: a malformed sudoers drop-in can lock
# everyone out of sudo entirely, and visudo -c is the only thing standing
# between a typo here and a rebuild of the machine.
tmp=$(mktemp)
cat > "$tmp" <<EOF
# Jockey 3 test framework -- installed by tests/hw/priv/install.sh
#
# One entry, one script. The script is root-owned and its verbs take
# validated arguments, so this grants exactly the operations listed in
# $HELPER and nothing else.
#
# Deliberately NOT granted: installing a kernel module. That is arbitrary
# kernel code execution, so deploying a new driver build asks for a password.
$USER_NAME ALL=(root) NOPASSWD: $HELPER
EOF
chmod 0440 "$tmp"
visudo -cqf "$tmp" || { rm -f "$tmp"; echo "sudoers validation FAILED" >&2; exit 3; }
install -o root -g root -m 0440 "$tmp" "$SUDOERS"
rm -f "$tmp"
echo "installed $SUDOERS for user '$USER_NAME'"

visudo -c >/dev/null || { echo "*** system sudoers now invalid" >&2; exit 3; }
echo
sudo -u "$USER_NAME" sudo -n "$HELPER" status && echo "verified: passwordless"
