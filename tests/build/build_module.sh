#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Build the driver module for one target kernel, ready to deploy.
#
#   ./build_module.sh x86_64-debug
#   ./build_module.sh x86_64-debug --manifest    also record build-id -> git
#
# Why this is not build_jockey3.sh
# --------------------------------
# build_jockey3.sh builds in KERNEL_SRC (~/sound) IN TREE, and exists to run
# the L1 gates: checkpatch, W=12, kernel-doc, codespell, size. What it produces
# is a verdict, not a module anyone should load.
#
# A module that will actually be inserted has to match the running kernel's
# vermagic exactly, which means building against the object tree that produced
# that kernel -- ~/kbuild/<target>, with ~/sound-build as its source. Using
# ~/sound instead produces a module for whatever configuration that tree was
# last built with, which is a different kernel whenever a target kernel is in
# use. Debug targets make this unmissable: a KASAN kernel will not take a
# module built without KASAN.
#
# The two builds are therefore both correct and not interchangeable. Run the
# gates before committing; run this before testing on hardware.
#
# Environment:
#   KERNEL_SRC     source of truth, never built in     (default ~/sound)
#   BUILD_TREE     clean worktree to build from        (default ~/sound-build)
#   BUILD_OUTPUT   root of per-target object dirs      (default ~/kbuild)

set -eu

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)

BUILD_TREE=${BUILD_TREE:-$HOME/sound-build}
BUILD_OUTPUT=${BUILD_OUTPUT:-$HOME/kbuild}
DST=sound/usb/jockey3
MANIFEST=0
TARGET=""

while [ $# -gt 0 ]; do
	case "$1" in
	--manifest) MANIFEST=1; shift ;;
	--help|-h)  sed -n '3,10p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'; exit 0 ;;
	-*) echo "unknown option: $1" >&2; exit 2 ;;
	*)  TARGET=$1; shift ;;
	esac
done
[ -n "$TARGET" ] || { echo "usage: build_module.sh <target> [--manifest]" >&2; exit 2; }

OBJ=$BUILD_OUTPUT/$TARGET
[ -d "$OBJ" ] || {
	echo "no object tree at $OBJ" >&2
	echo "build the target kernel first: ./build_kernel.sh $TARGET" >&2
	exit 2
}
[ -f "$OBJ/include/config/kernel.release" ] || {
	echo "$OBJ is not a configured kernel build" >&2; exit 2
}
RELEASE=$(cat "$OBJ/include/config/kernel.release")

# The file list lives in sync-driver.sh, shared with the other build scripts.
# Two copies would drift, and the failure mode is a module that silently omits
# a newly added source file.
"$HERE/sync-driver.sh" "$BUILD_TREE" >/dev/null

make -C "$BUILD_TREE" -j"$(nproc)" O="$OBJ" M=$DST modules

# With M=, kbuild writes objects next to the sources rather than into O=.
KO=$BUILD_TREE/$DST/snd-reloop-jockey3.ko
[ -f "$KO" ] || { echo "no module produced at $KO" >&2; exit 3; }

echo
echo "built for $TARGET ($RELEASE)"
/sbin/modinfo "$KO" | grep -E '^(vermagic|srcversion)' | sed 's/^/  /'
echo "  path: $KO"

# Refuse to hand over a module that cannot load. vermagic is what the kernel
# actually checks, so checking anything else here would be theatre.
VM=$(/sbin/modinfo "$KO" | sed -n 's/^vermagic: *//p')
case "$VM" in
"$RELEASE "*) ;;
*) echo "  *** vermagic does not start with '$RELEASE' -- will not load" >&2
   exit 3 ;;
esac

if [ "$MANIFEST" = 1 ]; then
	"$HERE/write-manifest.sh" "$KO" "$BUILD_TREE" "$RELEASE"
fi

echo
echo "deploy it with, on the test machine:"
echo "  tests/hw/actions/reload_driver.sh <path-to-ko>"
