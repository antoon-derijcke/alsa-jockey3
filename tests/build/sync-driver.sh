#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Copy the driver sources into a kernel tree's sound/usb/jockey3/.
#
#   sync-driver.sh <kernel-tree>    copy the files
#   sync-driver.sh --list           print the mapping, one "src:dst" per line
#
# One file list, used by build_jockey3.sh (validation), build_kernel.sh (kernel
# packages) and use-committed.sh (the drift check). Two copies of this list
# would drift, and the failure mode is a build that silently omits a newly
# added source file -- or a check that silently fails to notice one changed.
#
# Three of the entries are renamed on the way in, which is why this is a
# mapping and not a plain list: the kernel tree wants Makefile, the repository
# keeps Makefile.kernel so its own out-of-tree Makefile can coexist.
#
# Deliberately plain `cp -u`, never `cp -pu`: preserving mtimes makes the copy
# look older than the previous build's objects, so make skips the rebuild and
# silently revalidates the old revision. That has bitten this project twice.

set -eu

SRC_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)

# src (in this repository) : dst (under sound/usb/jockey3)
FILES=(
	"Kconfig:Kconfig"
	"Makefile.kernel:Makefile"
	".kunitconfig:.kunitconfig"
	"jockey3.c:jockey3.c"
	"ploytec_proto.c:ploytec_proto.c"
	"ploytec_proto.h:ploytec_proto.h"
	"ploytec_codec.c:ploytec_codec.c"
	"ploytec_codec.h:ploytec_codec.h"
	"ploytec_midi.c:ploytec_midi.c"
	"ploytec_midi.h:ploytec_midi.h"
	"ploytec_codec_kunit.c:ploytec_codec_kunit.c"
	"ploytec_codec_test_vectors.h:ploytec_codec_test_vectors.h"
)

if [ "${1:-}" = "--list" ]; then
	printf '%s\n' "${FILES[@]}"
	exit 0
fi

TREE=${1:?usage: sync-driver.sh <kernel-tree> | --list}
DST=$TREE/sound/usb/jockey3

mkdir -p "$DST"
for pair in "${FILES[@]}"; do
	cp -uv "$SRC_DIR/${pair%%:*}" "$DST/${pair#*:}"
done
