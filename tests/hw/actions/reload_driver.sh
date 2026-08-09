#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Install a freshly built module and reload it.
#
#   reload_driver.sh [path-to-ko]
#
# With no argument, fetches from the build host over ssh. Set JT_BUILD_HOST
# and JT_BUILD_PATH to point somewhere else, or pass a local path.
#
# THIS SCRIPT ASKS FOR A PASSWORD, AND THAT IS DELIBERATE
# ------------------------------------------------------
# Copying a .ko into /lib/modules and loading it is arbitrary kernel code
# execution -- root by another name. So installing a module is the one
# privileged operation the test framework does NOT automate: it is not a verb
# in jockey3-testctl, and no sudoers rule grants it. Deploying a new build is
# an occasional, deliberate act; a password there costs nothing.
#
# Loading and unloading the already-installed module IS automated, through the
# helper, which is what lets an unattended profile cycle the driver.
#
# Verifying the reload actually took effect is the caller's job, via the
# module's build-id: rmmod can fail silently if the module is in use, leaving
# the previous build resident and every subsequent result attributed to the
# wrong revision.
#
# Derived from reload_driver.sh and reload_bleeding_driver.sh in
# ../../scripts-alsa-dev.

set -eu

MODULE=snd-reloop-jockey3
HELPER=/usr/local/sbin/jockey3-testctl
KO=${1:-}
BUILD_HOST=${JT_BUILD_HOST:-alsa-dev}
BUILD_PATH=${JT_BUILD_PATH:-~/sound/sound/usb/jockey3/$MODULE.ko}
DEST=/lib/modules/$(uname -r)/kernel/sound/usb/jockey3

if [ -z "$KO" ]; then
	KO=$(mktemp -d)/$MODULE.ko
	echo "fetching from $BUILD_HOST..."
	scp -q "$BUILD_HOST:$BUILD_PATH" "$KO"
fi
[ -f "$KO" ] || { echo "no module at $KO" >&2; exit 2; }

echo "unloading..."
sudo -n "$HELPER" unload || sudo "$HELPER" unload

# Installing needs real root; everything above and below goes through the
# helper. sudo will prompt here unless a password was cached.
echo "installing (this is the step that needs a password)..."
sudo mkdir -p "$DEST"
# Remove every compressed variant first. Distribution kernels install the
# module as snd-reloop-jockey3.ko.xz, and dropping an uncompressed .ko beside
# it leaves two modules of the same name in one directory -- from which
# depmod and modprobe may pick either. That is precisely the "reload silently
# left the previous build resident" failure this script's header warns about,
# and it is invisible until a result is attributed to the wrong revision.
for ext in .ko.xz .ko.zst .ko.gz; do
	sudo rm -fv "$DEST/${MODULE}${ext}"
done
# Deliberately not `cp -p`: preserving the source timestamp has repeatedly
# caused tooling downstream to conclude nothing changed and skip work, which
# silently leaves the previous revision in play.
sudo cp -v "$KO" "$DEST/"
sudo depmod

echo "loading..."
sudo -n "$HELPER" load || sudo "$HELPER" load

bid=$(cat "/sys/module/${MODULE//-/_}/notes/.note.gnu.build-id" 2>/dev/null \
	| od -An -tx1 | tr -d ' \n' | tail -c 40)
echo "build-id: ${bid:-?}"
