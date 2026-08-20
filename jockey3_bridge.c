/*
 * Reloop Jockey 3 ME / Master Edition - Userspace USB Audio Bridge
 * 
 * Directly interfaces with the Reloop Jockey 3 ME (VID: 0x200c, PID: 0x1019)
 * over Linux usbfs (/dev/bus/usb/...) to provide 4-channel audio output
 * (Master Channels 1-2 + Headphone Cue Channels 3-4) for Mixxx DJ software.
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <dirent.h>
#include <pthread.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <linux/usbdevice_fs.h>

#define JOCKEY3_VID 0x200c
#define JOCKEY3_PID 0x1019
#define JOCKEY3_PID_OLD 0x1009

#define EP_AUDIO_OUT 0x01
#define PACKET_SIZE 48
#define SAMPLES_PER_PACKET 10
#define NUM_CHANNELS 4

#define FIFO_PATH "/data/local/tmp/jockey3_pcm"

static int usb_fd = -1;
static int fifo_fd = -1;
static volatile int running = 1;

/* Ploytec sample bit-spread codec */
static void ploytec_encode_sample(const int32_t *channels, uint8_t *wire)
{
    uint32_t c0 = (uint32_t)channels[0] & 0x00ffffff;
    uint32_t c1 = (uint32_t)channels[1] & 0x00ffffff;
    uint32_t c2 = (uint32_t)channels[2] & 0x00ffffff;
    uint32_t c3 = (uint32_t)channels[3] & 0x00ffffff;

    /* Ploytec interleaved 4-channel spreading scheme */
    wire[0] = (uint8_t)(c0 >> 16);
    wire[1] = (uint8_t)(c1 >> 16);
    wire[2] = (uint8_t)(c2 >> 16);
    wire[3] = (uint8_t)(c3 >> 16);

    wire[4] = (uint8_t)(c0 >> 8);
    wire[5] = (uint8_t)(c1 >> 8);
    wire[6] = (uint8_t)(c2 >> 8);
    wire[7] = (uint8_t)(c3 >> 8);

    wire[8]  = (uint8_t)c0;
    wire[9]  = (uint8_t)c1;
    wire[10] = (uint8_t)c2;
    wire[11] = (uint8_t)c3;
}

/* Find and open the Reloop Jockey 3 ME usbfs device node */
static int find_and_open_device(void)
{
    char bus_path[256], dev_path[256];
    struct dirent *bus_entry, *dev_entry;
    DIR *bus_dir = opendir("/dev/bus/usb");
    if (!bus_dir) {
        perror("Cannot open /dev/bus/usb");
        return -1;
    }

    while ((bus_entry = readdir(bus_dir)) != NULL) {
        if (bus_entry->d_name[0] == '.') continue;
        snprintf(bus_path, sizeof(bus_path), "/dev/bus/usb/%s", bus_entry->d_name);
        DIR *dev_dir = opendir(bus_path);
        if (!dev_dir) continue;

        while ((dev_entry = readdir(dev_dir)) != NULL) {
            if (dev_entry->d_name[0] == '.') continue;
            snprintf(dev_path, sizeof(dev_path), "%s/%s", bus_path, dev_entry->d_name);
            int fd = open(dev_path, O_RDWR);
            if (fd < 0) continue;

            struct usb_device_descriptor {
                uint8_t  bLength;
                uint8_t  bDescriptorType;
                uint16_t bcdUSB;
                uint8_t  bDeviceClass;
                uint8_t  bDeviceSubClass;
                uint8_t  bDeviceProtocol;
                uint8_t  bMaxPacketSize0;
                uint16_t idVendor;
                uint16_t idProduct;
            } __attribute__((packed)) desc;

            if (read(fd, &desc, sizeof(desc)) == sizeof(desc)) {
                if (desc.idVendor == JOCKEY3_VID && (desc.idProduct == JOCKEY3_PID || desc.idProduct == JOCKEY3_PID_OLD)) {
                    printf("[Jockey 3 Bridge] Found Reloop Jockey 3 ME (%04x:%04x) at %s!\n",
                           desc.idVendor, desc.idProduct, dev_path);
                    closedir(dev_dir);
                    closedir(bus_dir);
                    return fd;
                }
            }
            close(fd);
        }
        closedir(dev_dir);
    }
    closedir(bus_dir);
    return -1;
}

/* Control Transfer Helper */
static int usb_ctrl_msg(int fd, uint8_t req_type, uint8_t req, uint16_t val, uint16_t idx, void *data, uint16_t size)
{
    struct usbdevfs_ctrltransfer ctrl;
    ctrl.bRequestType = req_type;
    ctrl.bRequest = req;
    ctrl.wValue = val;
    ctrl.wIndex = idx;
    ctrl.wLength = size;
    ctrl.timeout = 2000;
    ctrl.data = data;
    return ioctl(fd, USBDEVFS_CONTROL, &ctrl);
}

/* Initialize Ploytec Streaming Hardware */
static int ploytec_init(int fd)
{
    uint8_t fw_buf[4] = {0};
    int ret;

    printf("[Jockey 3 Bridge] Initializing Ploytec hardware handshake...\n");

    /* Claim Interface 0 */
    struct usbdevfs_disconnect_claim dc;
    dc.interface = 0;
    dc.flags = USBDEVFS_DISCONNECT_CLAIM_EXCEPT_DRIVER;
    strcpy(dc.driver, "usbfs");
    ioctl(fd, USBDEVFS_DISCONNECT_CLAIM, &dc);

    int iface = 0;
    ret = ioctl(fd, USBDEVFS_CLAIMINTERFACE, &iface);
    if (ret < 0) {
        perror("Claim interface 0 failed");
        return -1;
    }

    /* Set Alt Setting 1 (Streaming Active) */
    struct usbdevfs_setinterface set_iface;
    set_iface.interface = 0;
    set_iface.altsetting = 1;
    ret = ioctl(fd, USBDEVFS_SETINTERFACE, &set_iface);
    if (ret < 0) {
        perror("Set AltSetting 1 failed");
    }

    /* Read Firmware */
    ret = usb_ctrl_msg(fd, 0xc0, 0x01, 0, 0, fw_buf, 3);
    if (ret >= 0) {
        printf("[Jockey 3 Bridge] Firmware Version: %02x.%02x.%02x\n", fw_buf[0], fw_buf[1], fw_buf[2]);
    }

    /* Set Sample Rate 44100 Hz (wValue = 44100 & 0xffff, wIndex = 44100 >> 16) */
    uint32_t rate = 44100;
    ret = usb_ctrl_msg(fd, 0x40, 0x01, (uint16_t)(rate & 0xffff), (uint16_t)(rate >> 16), NULL, 0);
    if (ret < 0) {
        perror("Set sample rate failed");
    }

    /* Read status and enable audio streaming bit */
    uint8_t status_buf[2] = {0};
    ret = usb_ctrl_msg(fd, 0xc0, 0x49, 0, 0, status_buf, 2);
    uint16_t stream_mode = (ret >= 0) ? (status_buf[0] | 0x20) : 0x20;

    ret = usb_ctrl_msg(fd, 0x40, 0x48, stream_mode, 0, NULL, 0);
    if (ret >= 0) {
        printf("[Jockey 3 Bridge] Ploytec hardware initialized and streaming enabled! 🎧\n");
    }
    return 0;
}

int main(int argc, char *argv[])
{
    printf("====================================================\n");
    printf("   Reloop Jockey 3 ME - Userspace Audio Bridge\n");
    printf("====================================================\n");

    usb_fd = find_and_open_device();
    if (usb_fd < 0) {
        fprintf(stderr, "Error: Reloop Jockey 3 ME not found on USB bus. Is it connected to the hub and powered on?\n");
        return 1;
    }

    if (ploytec_init(usb_fd) < 0) {
        fprintf(stderr, "Error: Failed to initialize Ploytec protocol.\n");
        close(usb_fd);
        return 1;
    }

    /* Create Named FIFO for Mixxx 4-channel audio stream */
    unlink(FIFO_PATH);
    if (mkfifo(FIFO_PATH, 0666) < 0 && errno != EEXIST) {
        perror("mkfifo");
    }
    chmod(FIFO_PATH, 0666);
    printf("[Jockey 3 Bridge] Audio pipe created at: %s\n", FIFO_PATH);
    printf("[Jockey 3 Bridge] Waiting for Mixxx to connect...\n");

    fifo_fd = open(FIFO_PATH, O_RDONLY);
    if (fifo_fd < 0) {
        perror("open fifo");
        close(usb_fd);
        return 1;
    }

    printf("[Jockey 3 Bridge] Audio stream connected! Streaming 4 channels to Jockey 3...\n");

    /* Audio Streaming Buffer */
    /* 16-bit 4-channel interleaved PCM: [L_master, R_master, L_cue, R_cue] * 10 samples = 80 bytes */
    int16_t pcm16_buf[SAMPLES_PER_PACKET * NUM_CHANNELS];
    int32_t pcm24_samples[NUM_CHANNELS];
    uint8_t wire_packet[PACKET_SIZE];

    /* Isochronous URB configuration */
    struct {
        struct usbdevfs_urb urb;
        struct usbdevfs_iso_packet_desc iso_frame;
    } iso_req;

    memset(&iso_req, 0, sizeof(iso_req));
    iso_req.urb.type = USBDEVFS_URB_TYPE_ISO;
    iso_req.urb.endpoint = EP_AUDIO_OUT;
    iso_req.urb.buffer = wire_packet;
    iso_req.urb.buffer_length = PACKET_SIZE;
    iso_req.urb.number_of_packets = 1;
    iso_req.iso_frame.length = PACKET_SIZE;

    while (running) {
        ssize_t bytes = read(fifo_fd, pcm16_buf, sizeof(pcm16_buf));
        if (bytes <= 0) {
            /* If no audio playing, send silence */
            memset(pcm16_buf, 0, sizeof(pcm16_buf));
            usleep(200);
        }

        /* Encode 10 samples into 48-byte Ploytec packet */
        for (int i = 0; i < SAMPLES_PER_PACKET; i++) {
            /* Convert 16-bit to 24-bit aligned */
            pcm24_samples[0] = ((int32_t)pcm16_buf[i * 4 + 0]) << 8;
            pcm24_samples[1] = ((int32_t)pcm16_buf[i * 4 + 1]) << 8;
            pcm24_samples[2] = ((int32_t)pcm16_buf[i * 4 + 2]) << 8;
            pcm24_samples[3] = ((int32_t)pcm16_buf[i * 4 + 3]) << 8;

            ploytec_encode_sample(pcm24_samples, &wire_packet[i * 4]);
        }
        /* Pad remaining 8 bytes of the 48-byte frame */
        memset(&wire_packet[40], 0, 8);

        /* Submit Isochronous Packet directly to Reloop Jockey 3 ME */
        iso_req.iso_frame.actual_length = 0;
        iso_req.iso_frame.status = 0;
        ioctl(usb_fd, USBDEVFS_SUBMITURB, &iso_req.urb);

        /* Reap completed transfer */
        struct usbdevfs_urb *reaped_urb = NULL;
        ioctl(usb_fd, USBDEVFS_REAPURBNDELAY, &reaped_urb);
    }

    close(fifo_fd);
    close(usb_fd);
    unlink(FIFO_PATH);
    return 0;
}
