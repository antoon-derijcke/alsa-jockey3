# tests/hw/priv/

The test suite's entire privileged surface, in one root-owned script.

| File | What it is |
|---|---|
| `jockey3-testctl` | The helper. Every root operation the suite performs is a verb in here. |
| `install.sh` | Installs it to `/usr/local/sbin` and writes the sudoers drop-in. Run once per machine. |

```sh
sudo ./install.sh      # install or update
./install.sh --check   # report status, needs no privilege
sudo ./install.sh --remove
```

## The verbs

| Verb | Why it needs root |
|---|---|
| `load` / `unload` | `modprobe` / `rmmod` the already-installed driver |
| ↳ | `load` also passes `dyndbg=` so the firmware revision is logged at probe |
| `dmesg-read` | `kernel.dmesg_restrict=1` on the test machines |
| `dmesg-mark <token>` | `/dev/kmsg` is writable only by root |
| `dyndbg-firmware on\|off` | `/sys/kernel/debug` is mode 0700 root |
| `printk-console <1-8>` | `/proc/sys/kernel/printk` is root-owned |
| `rtcwake-mem <1-3600>` | suspend to RAM |
| `status` | reports the helper is installed and reachable |

Everything else runs as an ordinary user: opening the card, playback, capture,
MIDI, stopping the session's sound server, reading sysfs and `/proc/config.gz`.
`/dev/snd/*` is `root:audio`, so the test user needs to be in the `audio`
group and needs nothing more.

`printk-console` is implemented but not yet called by the runner. It is here
because §8 of the test strategy says run preparation raises the console
loglevel, and adding a verb later means re-running the installer on every test
machine — the point of doing this now was to avoid exactly that.

## Why a script and not sudoers entries

`sudoers` matches a command line, and its wildcards are weaker than they look.
`NOPASSWD: /sbin/modprobe *` grants the right to load **any** module, which is
unrestricted root. Pinning every argument instead gives a dozen brittle entries
that must change whenever a case changes.

One root-owned script with a fixed verb interface and validated arguments gives
a boundary that can actually be reviewed. This directory *is* the boundary:
reading `jockey3-testctl` tells you everything the suite can do as root.

## Why it is installed rather than run in place

A script `sudo` runs must not be writable by the user it grants privilege to,
or the boundary is worthless. The working tree lives on a Seafile share and is
user-writable, so granting sudo rights to it in place would turn any local
write — or any sync from another machine — into root. `install.sh` copies it to
a root-owned path; the runner's preflight compares the two and complains when
the installed copy has fallen behind.

## What is deliberately not here

**Installing a kernel module.** Copying a `.ko` into `/lib/modules` and loading
it is arbitrary kernel code execution — root by another name. Wrapping it in a
narrow-looking verb would make the allowlist presentational rather than a real
boundary. Deploying a new driver build therefore asks for a password, once, in
`actions/reload_driver.sh`. Loading and unloading the already-installed module
is automated, which is what an unattended profile actually needs.
