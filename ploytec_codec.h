/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 *   ALSA driver for Reloop Jockey 3 devices
 *   Ploytec PCM encoding/decoding functions for the S24_3LE format (3 bytes per sample)
 *
 *   Copyright (c) 2026 by Frank van de Pol <fvdpol@gmail.com>
 */

#ifndef PLOYTEC_CODEC_H
#define PLOYTEC_CODEC_H

#include <linux/types.h>

/* Bit-shuffling codec for S24_3LE (3 bytes per sample) */
void ploytec_encode_s24_3le(u8 *dest, const u8 *src);
void ploytec_decode_s24_3le(u8 *dest, const u8 *src);

#endif /* PLOYTEC_CODEC_H */
