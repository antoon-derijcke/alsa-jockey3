#ifndef STUB_UNALIGNED
#define STUB_UNALIGNED

#include <stdint.h>
#include <string.h>
#include <linux/types.h>

/* Detect Endianness at compile-time via GCC/Clang macros */
#if defined(__BYTE_ORDER__) && defined(__ORDER_BIG_ENDIAN__) && (__BYTE_ORDER__ == __ORDER_BIG_ENDIAN__)
#define SYSTEM_IS_BIG_ENDIAN 1
#else
#define SYSTEM_IS_BIG_ENDIAN 0
#endif

/* ----------------- 32-bit User-space Stubs ----------------- */

static inline u32 get_unaligned_le32(const void *p) {
	u32 val;
	memcpy(&val, p, sizeof(val)); /* Safe from alignment faults */
#if SYSTEM_IS_BIG_ENDIAN
 	return __builtin_bswap32(val); /* Zero-cost hardware byte swap on BE */
#else
	return val;
#endif
}

static inline void put_unaligned_le32(u32 val, void *p) {
#if SYSTEM_IS_BIG_ENDIAN
	val = __builtin_bswap32(val);
#endif
	memcpy(p, &val, sizeof(val));
}

/* ----------------- 64-bit User-space Stubs ----------------- */

static inline u64 get_unaligned_le64(const void *p) {
	u64 val;
	memcpy(&val, p, sizeof(val));
#if SYSTEM_IS_BIG_ENDIAN
	return __builtin_bswap64(val);
#else
	return val;
#endif
}

static inline void put_unaligned_le64(u64 val, void *p) {
#if SYSTEM_IS_BIG_ENDIAN
	val = __builtin_bswap64(val);
#endif
	memcpy(p, &val, sizeof(val));
}


#endif