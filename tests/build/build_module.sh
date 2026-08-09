#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Build the driver module for one target kernel, ready to deploy.
#
#   ./build_module.sh x86_64-debug
#   ./build_module.sh x86_64-debug --manifest    also record build-id -> git
#   ./build_module.sh x86_64-debug --uncommitted build sandbox sources as-is
#
# Builds from COMMITTED sources
# -----------------------------
# The driver is edited in this repository and must be committed to the kernel
# branch (feature/jockey3 in ~/sound) before a test build. Otherwise nothing
# identifies what was tested: the module would be compiled from whatever
# happened to be lying in a build worktree, and the manifest would name a
# revision that never contained those bytes.
#
# So this does not copy sources in. It checks that the branch's committed
# driver matches this repository, points the build worktree at that commit, and
# builds what is there. The kernel commit lands in the manifest alongside the
# repository revision, and both are real.
#
# --uncommitted restores the old copy-then-build behaviour for quick iteration.
# The manifest records kernel_driver_dirty: true, so such a build is still
# distinguishable after the fact -- but it should not be what a recorded test
# result was produced from.
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
#   BUILD_REF      kernel branch holding the driver    (default feature/jockey3)

set -eu

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)

KERNEL_SRC=${KERNEL_SRC:-$HOME/sound}
BUILD_TREE=${BUILD_TREE:-$HOME/sound-build}
BUILD_OUTPUT=${BUILD_OUTPUT:-$HOME/kbuild}
BUILD_REF=${BUILD_REF:-feature/jockey3}
DST=sound/usb/jockey3
MANIFEST=0
UNCOMMITTED=0
TARGET=""

while [ $# -gt 0 ]; do
	case "$1" in
	--manifest)    MANIFEST=1; shift ;;
	--uncommitted) UNCOMMITTED=1; shift ;;
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

if [ "$UNCOMMITTED" = 1 ]; then
	echo "*** --uncommitted: building unstaged sources; this module is not"
	echo "*** reproducible from any commit. Do not record a test result from it."
	# The file list lives in sync-driver.sh, shared with the other build
	# scripts. Two copies would drift, and the failure mode is a module that
	# silently omits a newly added source file.
	"$HERE/sync-driver.sh" "$BUILD_TREE" >/dev/null
else
	SHA=$(git -C "$KERNEL_SRC" rev-parse --verify "$BUILD_REF" 2>/dev/null) || {
		echo "no ref '$BUILD_REF' in $KERNEL_SRC" >&2; exit 2; }

	# Does the branch actually hold what is being tested? Comparing the files
	# rather than trusting a workflow: the whole point is that the module can
	# be rebuilt from this commit and come out the same.
	drift=""
	while IFS= read -r f; do
		a=$(git -C "$KERNEL_SRC" show "$SHA:$DST/$f" 2>/dev/null | sha256sum | cut -d' ' -f1)
		b=$(sha256sum "$REPO/$f" 2>/dev/null | cut -d' ' -f1)
		[ "$a" = "$b" ] || drift="$drift $f"
	done <<-'FILES'
	jockey3.c
	ploytec_proto.c
	ploytec_proto.h
	ploytec_codec.c
	ploytec_codec.h
	ploytec_midi.c
	ploytec_midi.h
	ploytec_codec_kunit.c
	ploytec_codec_test_vectors.h
	FILES

	if [ -n "$drift" ]; then
		echo "the driver in $BUILD_REF does not match this repository:" >&2
		for f in $drift; do echo "    $f" >&2; done
		echo >&2
		echo "commit the driver into the kernel branch first, so the build is" >&2
		echo "reproducible and the manifest names a revision that contains it:" >&2
		echo >&2
		echo "    tests/build/sync-driver.sh $KERNEL_SRC" >&2
		echo "    git -C $KERNEL_SRC add $DST" >&2
		echo "    git -C $KERNEL_SRC commit --amend --no-edit   # or a new commit" >&2
		echo >&2
		echo "or pass --uncommitted to build them as they are." >&2
		exit 3
	fi

	# The build worktree is disposable scratch whose only job is to hold the
	# committed source, so it is reset rather than merged. --force discards
	# leftovers from previous --uncommitted builds; untracked build output is
	# left in place so the rebuild stays incremental.
	git -C "$BUILD_TREE" checkout --detach --force --quiet "$SHA"
	echo "building $BUILD_REF at $(git -C "$KERNEL_SRC" rev-parse --short "$SHA")"
fi

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
