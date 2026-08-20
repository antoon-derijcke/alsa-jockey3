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
#include <linux/wait.h>
#include <sound/core.h>
#include <sound/pcm.h>

#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 6, 0)
#include <linux/cleanup.h>
#endif

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
 * devm_add_action_or_reset was added in Linux 4.10.
 */
#if LINUX_VERSION_CODE < KERNEL_VERSION(4, 10, 0)
static inline int devm_add_action_or_reset(struct device *dev,
					   void (*action)(void *), void *data)
{
	int ret = devm_add_action(dev, action, data);
	if (ret)
		action(data);
	return ret;
}
#endif

/*
 * snd_devm_card_new was added in Linux 5.17.
 */
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 17, 0)
static inline int snd_devm_card_new(struct device *parent, int idx,
				    const char *xid, struct module *module,
				    size_t extra_size, struct snd_card **card_ret)
{
	return snd_card_new(parent, idx, xid, module, extra_size, card_ret);
}
#endif

/*
 * snd_pcm_set_managed_buffer_all was added in Linux 5.9.
 */
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 9, 0)
#ifndef SNDRV_DMA_TYPE_VMALLOC
#define SNDRV_DMA_TYPE_VMALLOC SNDRV_DMA_TYPE_CONTINUOUS
#endif
static inline void snd_pcm_set_managed_buffer_all(struct snd_pcm *pcm, int type,
						  struct device *dev,
						  size_t size, size_t max)
{
	snd_pcm_lib_preallocate_pages_for_all(pcm, type, dev, size, max);
}
#endif

/*
 * wait_event_lock_irq_timeout was added in Linux 4.12.
 */
#if LINUX_VERSION_CODE < KERNEL_VERSION(4, 12, 0)
#define wait_event_lock_irq_timeout(wq, condition, lock, timeout)	\
	wait_event_interruptible_timeout(wq, condition, timeout)
#endif

#endif /* _JOCKEY3_COMPAT_H_ */
