# SPDX-License-Identifier: GPL-2.0-or-later
"""Tasmota relay backend.

Tasmota is worth the choice here because it speaks plain HTTP with no broker,
no cloud account and no client library: a GET returns JSON, which is the whole
protocol. Everything specific to it is in this file -- see lib/power/__init__.py
for the interface a backend has to satisfy.

    GET /cm?cmnd=Status      full device status
    GET /cm?cmnd=Power       {"POWER":"ON"}
    GET /cm?cmnd=Power%20Off {"POWER":"OFF"}

A relay with a password takes `user` and `password` as further query
parameters. That puts the password in a URL, which is Tasmota's design and not
something this can improve on; it is one reason the address and credentials
live in a machine-local file rather than in the repository.

Set PowerOnState to 3 ("last state") on the relay. On 1 the device would come
back on after any interruption to the relay's own supply, which for a test
that deliberately leaves it powered down is the wrong default.
"""

import json
import time
import urllib.parse
import urllib.request

DEFAULT_TIMEOUT = 8
SETTLE_SECONDS = 1.0


class Tasmota:
    def __init__(self, cfg, timeout=DEFAULT_TIMEOUT):
        self.url = str(cfg["url"]).rstrip("/")
        self.user = cfg.get("user")
        self.password = cfg.get("password")
        self.timeout = timeout

    def _command(self, cmnd):
        """Run one Tasmota command. Returns decoded JSON, or None."""
        query = {"cmnd": cmnd}
        if self.user:
            query["user"] = self.user
            query["password"] = self.password or ""
        url = self.url + "/cm?" + urllib.parse.urlencode(query)
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception:
            # Network, HTTP and JSON failures are all the same answer to the
            # caller: the relay did not respond usefully. Distinguishing them
            # would only produce error text nobody acts on differently.
            return None

    # ---------------------------------------------------------- the interface

    def available(self):
        return self._command("Status") is not None

    def state(self):
        reply = self._command("Power")
        if not reply:
            return None
        value = reply.get("POWER")
        return value if value in ("ON", "OFF") else None

    def set_state(self, on):
        """Switch, then read back to confirm.

        The confirmation is a second query rather than the command's own
        reply. A relay that answers and does not switch would otherwise be
        indistinguishable from one that worked, and the test built on top
        would blame the driver for a dead outlet.
        """
        want = "ON" if on else "OFF"
        if self._command(f"Power {want}") is None:
            return False, f"relay did not answer the Power {want} command"
        time.sleep(SETTLE_SECONDS)
        got = self.state()
        if got is None:
            return False, "relay stopped answering after the command"
        if got != want:
            return False, f"relay reports {got} after being told {want}"
        return True, got
