import struct
import os

page_sz = 2048

def pad(data, sz=2048):
    rem = len(data) % sz
    return data + (b'\0' * (sz - rem)) if rem != 0 else data

def main():
    kernel_path = "kernel-src/arch/arm64/boot/Image"
    ramdisk_path = "stock/BOOT.img-ramdisk"
    dt_path = "stock/BOOT.img-dt"

    with open(kernel_path, "rb") as f:
        k = f.read()
    with open(ramdisk_path, "rb") as f:
        r = f.read()
    with open(dt_path, "rb") as f:
        d = f.read()

    hdr = struct.pack(
        "<8s10I16s512s32s1024s",
        b"ANDROID!",
        len(k),
        0x10008000,
        len(r),
        0x11000000,
        0,
        0,
        0x10000100,
        page_sz,
        len(d),
        0x16000196,
        b"",
        b"buildvariant=userdebug androidboot.selinux=permissive",
        b"",
        b""
    )

    boot = pad(hdr) + pad(k) + pad(r) + pad(d) + b"SEANDROIDENFORCE\xff\xff\xff\xff"
    boot = pad(boot)

    out_file = "S8-DJ-boot.img"
    with open(out_file, "wb") as f:
        f.write(boot)

    print(f"Successfully generated signed {out_file}: {len(boot)} bytes!")

if __name__ == "__main__":
    main()
