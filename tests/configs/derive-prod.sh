#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Regenerate <arch>-prod.config from <arch>-debug.config.
#
#   ./derive-prod.sh x86_64
#
# The production configuration is the debug one with the debugging turned off,
# rather than an independently maintained file. That is deliberate: two
# hand-maintained configurations drift, and when they drift the difference
# between a prod and a debug result stops being "the debug options" and starts
# being "who knows". Deriving one from the other means the only difference is
# the list below.
#
# Environment:
#   KERNEL_SRC   kernel tree providing scripts/config and olddefconfig
#                (default ~/sound)

set -eu

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ARCH=${1:-x86_64}
KERNEL_SRC=${KERNEL_SRC:-$HOME/sound}

SRC=$HERE/$ARCH-debug.config
DST=$HERE/$ARCH-prod.config

[ -f "$SRC" ] || { echo "no such config: $SRC" >&2; exit 2; }
[ -x "$KERNEL_SRC/scripts/config" ] || {
	echo "no kernel tree at $KERNEL_SRC (set KERNEL_SRC)" >&2; exit 2; }

# Kernel ARCH= name and cross-compiler prefix for our target tokens -- must
# be passed to olddefconfig below. Without it, `make` defaults ARCH to the
# host architecture, and olddefconfig will silently rewrite a non-x86_64
# config into a host-arch one instead of just toggling the debug symbols.
case "$ARCH" in
x86_64) KARCH=x86   ; CROSS=                        ;;
i386)   KARCH=x86   ; CROSS=                        ;;
arm64)  KARCH=arm64 ; CROSS=aarch64-linux-gnu-       ;;
armhf)  KARCH=arm   ; CROSS=arm-linux-gnueabihf-     ;;
*) echo "unsupported architecture '$ARCH'" >&2; exit 2 ;;
esac

# shellcheck source=tests/configs/config-flags.sh
. "$HERE/config-flags.sh"

cp "$SRC" "$DST"
"$KERNEL_SRC/scripts/config" --file "$DST" --set-str LOCALVERSION "-alsa-prod"
for sym in "${DEBUG_ONLY[@]}"; do
	"$KERNEL_SRC/scripts/config" --file "$DST" --disable "$sym"
done

# olddefconfig resolves the cascade: symbols that only existed because
# something disabled above selected them.
make -s -C "$KERNEL_SRC" ARCH="$KARCH" CROSS_COMPILE="$CROSS" \
	olddefconfig KCONFIG_CONFIG="$DST"

echo "wrote $DST"
echo
printf '  %-34s %s\n' "LOCALVERSION" \
	"$(grep -E '^CONFIG_LOCALVERSION=' "$DST")"
for sym in KASAN PROVE_LOCKING LOCKDEP DEBUG_KMEMLEAK KUNIT; do
	printf '  %-34s %s\n' "$sym" \
		"$(grep -E "^CONFIG_$sym=" "$DST" || echo 'disabled')"
done
