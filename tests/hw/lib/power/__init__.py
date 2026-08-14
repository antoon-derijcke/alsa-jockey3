# SPDX-License-Identifier: GPL-2.0-or-later
"""Control over the device's own mains power.

Named for what is controlled, not for what does the controlling: behind this
may be a relay, a solid-state switch or anything else, and no test has any
business caring which. That belongs to a backend.

The Jockey 3 is self-powered, and that turns out to matter: cutting VBUS at
the hub is a cable unplug, not a power-off, and the device does not treat the
two alike. JT-AUDIO-005 needs a real power cycle -- see its docstring for why
-- and until there was a way to switch the device's own supply, that case
could only be driven by hand.

WHAT IS HERE AND WHAT IS NOT
----------------------------
This module is the interface: is a switch present, what state is it in, put it
in another one, cycle it. It knows nothing about how any particular switch is
spoken to. Each backend in this package implements the same three methods and
keeps its protocol to itself, so replacing the switching hardware means adding a
file here and changing one line of configuration -- not touching a test.

A backend is a class with:

    available()        -> bool          does it answer at all
    state()            -> "ON"|"OFF"|None
    set_state(on)      -> (ok, detail)  switch, and confirm it took

`cycle()` is deliberately not a backend method. Off, wait, on is the same
sequence whichever switch is in the rack, and the waiting is the part that
carries the reasoning.

WHERE THE ADDRESS COMES FROM, AND WHY NOT FROM HERE
---------------------------------------------------
Nowhere in this package. The switch lives on somebody's private network under
somebody's hostname, and this repository is headed for mainline; a personal
address baked into it would be wrong on both counts and useless to anyone
else. It is read from the environment or from the machine-local config
file, the same one that already records what is plugged into this machine and
which deliberately sits outside the working tree -- see lib/machineconf.py.

    export JOCKEY3_POWER_SWITCH=http://powerswitch.example.com

or, in ~/.config/jockey3/machine.yaml, alongside the capabilities block:

    power_switch:
      type: tasmota                    # optional, tasmota is the default
      url: http://powerswitch.example.com
      user: admin                      # only if the switch has a password
      password: secret

An absent setting is not an error. It means this machine cannot switch the
device's power, the capability is simply not present, and JT-AUDIO-005 falls
back to asking an operator.

SAFETY
------
This cuts mains power to hardware. Nothing here runs on import, nothing polls,
and `cycle()` is the only function that turns anything off -- everything else
reads. Backends confirm by reading the state back rather than trusting the
reply, because a switch that accepts a command and does not act is exactly the
failure that would make a test look like a driver bug.
"""

import os
import time

from lib import machineconf

DEFAULT_TYPE = "tasmota"
DEFAULT_OFF_SECONDS = 5.0


def _settings():
    """Relay settings from the environment or the capabilities file."""
    url = os.environ.get("JOCKEY3_POWER_SWITCH")
    if url:
        return {"type": os.environ.get("JOCKEY3_POWER_SWITCH_TYPE",
                                       DEFAULT_TYPE),
                "url": url,
                "user": os.environ.get("JOCKEY3_POWER_SWITCH_USER"),
                "password": os.environ.get("JOCKEY3_POWER_SWITCH_PASSWORD")}
    cfg = dict(machineconf.section("power_switch"))
    if not cfg.get("url"):
        return None
    cfg.setdefault("type", DEFAULT_TYPE)
    return cfg


def backend():
    """The configured backend, or None. Never raises."""
    cfg = _settings()
    if not cfg:
        return None
    kind = str(cfg.get("type") or DEFAULT_TYPE).lower()
    if kind == "tasmota":
        from lib.power.tasmota import Tasmota
        return Tasmota(cfg)
    return None


def configured():
    """Is a switch configured at all? Does not touch the network."""
    return _settings() is not None


def available():
    """Is a switch configured and answering? Reads only."""
    b = backend()
    return bool(b and b.available())


def state():
    """"ON", "OFF", or None if no switch answered."""
    b = backend()
    return b.state() if b else None


def set_state(on):
    """Switch the device on or off and confirm it took."""
    b = backend()
    if not b:
        return False, "no power switch configured"
    return b.set_state(on)


def cycle(off_seconds=DEFAULT_OFF_SECONDS):
    """Power the device off, wait, and power it back on.

    The wait is not arbitrary. The point of this whole exercise is a cold
    boot: reconnecting mains before the device's own supply has drained gives
    a warm one, which is the case that already works and proves nothing.
    """
    ok, detail = set_state(False)
    if not ok:
        return False, f"power off failed: {detail}"
    time.sleep(off_seconds)
    ok, detail = set_state(True)
    if not ok:
        return False, f"power on failed: {detail}"
    return True, "cycled"
