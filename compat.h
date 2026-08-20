/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 *   Backwards-compatibility header for snd-reloop-jockey3
 *   Supports Linux Kernel 4.4.x through 6.x+
 */

#ifndef _JOCKEY3_COMPAT_H_
#define _JOCKEY3_COMPAT_H_

#include <linux/version.h>
#include <linux/usb.h>
#include <linux/mutex.h>
#include <linux/spinlock.h>

/*
 * usb_control_msg_recv and usb_control_msg_send were added in Linux 5.8.
 * Provide inline shims for Linux 4.4 - 5.7.
 */
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 8, 0)
static inline int usb_control_msg_recv(struct usb_device *dev, __u8 endpoint,
				       __u8 request, __u8 requesttype,
				       __u16 value, __u16 index,
				       void *data, __u16 size, int timeout,
				       gfp_t memflags)
{
	return usb_control_msg(dev, usb_rcvctrlpipe(dev, endpoint),
			       request, requesttype, value, index,
			       data, size, timeout);
}

static inline int usb_control_msg_send(struct usb_device *dev, __u8 endpoint,
				       __u8 request, __u8 requesttype,
				       __u16 value, __u16 index,
				       const void *data, __u16 size, int timeout,
				       gfp_t memflags)
{
	return usb_control_msg(dev, usb_sndctrlpipe(dev, endpoint),
			       request, requesttype, value, index,
			       (void *)data, size, timeout);
}
#endif

/*
 * devm_mutex_init was added in Linux 5.17.
 */
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 17, 0)
static inline int devm_mutex_init(struct device *dev, struct mutex *lock)
{
	mutex_init(lock);
	return 0;
}
#endif

/*
 * scoped_guard and RAII cleanup were added in Linux 6.6.
 * Provide GNU C attribute((cleanup)) RAII guards for Linux 4.4 - 6.5.
 */
#if LINUX_VERSION_CODE < KERNEL_VERSION(6, 6, 0)

struct _jockey3_spinlock_guard {
	spinlock_t *lock;
	unsigned long flags;
};

static inline void _jockey3_spin_unlock_cleanup(struct _jockey3_spinlock_guard *g)
{
	if (g->lock)
		spin_unlock_irqrestore(g->lock, g->flags);
}

#define _GUARD_spinlock_irqsave(lock_ptr) \
	struct _jockey3_spinlock_guard _g_spin __attribute__((cleanup(_jockey3_spin_unlock_cleanup))) = { \
		.lock = (lock_ptr) \
	}; \
	spin_lock_irqsave((lock_ptr), _g_spin.flags)

static inline void _jockey3_mutex_unlock_cleanup(struct mutex **m)
{
	if (*m)
		mutex_unlock(*m);
}

#define _GUARD_mutex(lock_ptr) \
	struct mutex *_g_mut __attribute__((cleanup(_jockey3_mutex_unlock_cleanup))) = (lock_ptr); \
	mutex_lock(lock_ptr)

#define scoped_guard(type, lock_ptr) \
	for (int _d1 = 0; !_d1; _d1 = 1) \
		for (_GUARD_##type(lock_ptr); !_d1; _d1 = 1)

#endif /* LINUX_VERSION_CODE < 6.6.0 */

#endif /* _JOCKEY3_COMPAT_H_ */
