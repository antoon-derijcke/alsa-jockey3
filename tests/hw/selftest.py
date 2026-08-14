#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Tests for the test framework itself.

    ./selftest.py

Needs no hardware and no root. Run it after touching lib/, rules.yaml,
catalog.yaml, targets.yaml or profiles.yaml.

The framework decides what counts as a pass, so a mistake in here does not
produce a visible failure -- it produces a green run that means nothing. That
is the one failure mode worth spending test code on: everything below either
proves a message lands in the bucket that changes the verdict, or proves a
target is identified as what it actually is.
"""

import io
import json
import ast
import os
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: apt install python3-yaml")

from lib import env, kmsg, results          # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = "snd-reloop-jockey3 1-3:1.0: "

_failures = []
_checks = 0


def check(ok, label, detail=""):
    global _checks
    _checks += 1
    if not ok:
        _failures.append(f"{label}{(': ' + detail) if detail else ''}")
    print(f"  {'ok ' if ok else 'FAIL'} {label}"
          + (f"   {detail}" if detail and not ok else ""))


def load(name):
    with open(os.path.join(HERE, name), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# --------------------------------------------------------------- classifier

def test_classifier(rules):
    print("\nkernel message classification")
    c = kmsg.Classifier(rules)

    # Timestamped, as dmesg actually renders them -- see test_kunit_on_target.
    T = "[ 5870.058393] "
    lines = [
        T + DRIVER + "Capture URB has stalled.",
        T + DRIVER + "jockey3_pcm_prepare waited 336 ms for reset completion.",
        T + DRIVER + "jockey3_pcm_prepare waited 1012 ms for reset completion.",
        T + DRIVER + "Inconsistent URB in-flight count: playback=2 != 0",
        T + DRIVER + "Some message nobody has ever seen",
        T + "usb 1-3: new high-speed USB device number 7 using xhci_hcd",
        T + "wlan0: authenticate with aa:bb:cc:dd:ee:ff",
        T + "BUG: unable to handle kernel NULL pointer dereference at 0000",
        T + DRIVER + "Playback URB has stalled.",
    ]
    b, m = c.classify(lines, [r"Capture URB has stalled\."])
    got = kmsg.summarize(b)

    # The stall is the whole point: it is expected on a healthy build, so it
    # must not be able to fail a run.
    check(got[kmsg.EXPECTED] == 4, "a stall is expected, not a failure",
          str(got))
    check(got[kmsg.UNEXPECTED] == 2,
          "driver self-check and unknown driver message both fail", str(got))
    check(got[kmsg.UNRELATED] == 1, "other subsystems' noise is ignored")
    check(got[kmsg.UNCLASSIFIED] == 1,
          "an unrecognized line is surfaced, not swallowed")
    check(got[kmsg.INVESTIGATE] == 1, "a kernel defect escalates")

    h = kmsg.histogram(m.get("reset_wait_ms", []))
    check(h and h["n"] == 2 and h["max"] == 1012,
          "reset delays are captured as a distribution", str(h))
    check(m.get("stalls_capture") == 1 and m.get("stalls_playback") == 1,
          "stalls are counted per direction")

    # A defect inside an otherwise expected message is still a defect.
    b2, _ = c.classify([DRIVER + "Capture URB has stalled. BUG: at foo.c:1"],
                       [r"Capture URB has stalled\."])
    check(len(b2[kmsg.INVESTIGATE]) == 1,
          "escalation wins over an expected-message match")


def test_wedged_device(rules):
    """The 2026-08-11 lockup, replayed line for line.

    Every message below was in the log of a device that had stopped answering
    while still enumerated, and NONE of them could fail a run at the time.
    The drain error was the earliest by several minutes and was invisible to
    the classifier because it names the ALSA card, not the module.
    """
    print("\nwedged-device signatures")
    c = kmsg.Classifier(rules)
    T = "[20748.130875] "
    lines = [
        T + "sound midiC1D0: rawmidi drain error (avail = 4090, buffer_size = 4096)",
        T + DRIVER + "Failed to initialize device to change rate: -110",
        T + DRIVER + "Failed to submit playback URB 0: -2",
        T + DRIVER + "Failed to submit MIDI IN URB: -2",
    ]
    b, _m = c.classify(lines, [])
    check(len(b[kmsg.UNEXPECTED]) == 4,
          "every symptom of the wedged device fails the run",
          str(kmsg.summarize(b)))
    check(not b[kmsg.UNCLASSIFIED],
          "and none of them is merely flagged for someone to notice")

    # The benign teardown message must NOT have been widened by any of this:
    # a resubmit racing a deliberate stop is still normal.
    b2, _ = c.classify([T + DRIVER + "Failed to resubmit playback URB: -2"], [])
    check(len(b2[kmsg.EXPECTED]) == 1,
          "while a resubmit lost to teardown stays benign -- a different "
          "message and a different event", str(kmsg.summarize(b2)))


def test_watchdog(rules):
    """The URB liveness watchdog's messages, and why they are bucketed as they are.

    The watchdog exists because the 2026-08-11 wedge was a SILENCE: every error
    path in the driver hangs off a URB completion, so when completions stopped,
    nothing ran and nothing was logged for about fourteen minutes. These rules
    are what turn that silence into a red run.

    The split between the onset (counted) and the heartbeat (failure) is not a
    severity judgement, it is forced by the classifier: driver_fail is tested
    before a case's expect_dmesg, so a driver_fail pattern cannot be whitelisted
    by the one case that provokes a stall deliberately.
    """
    print("\nURB liveness watchdog signatures")
    c = kmsg.Classifier(rules)
    T = "[21337.057880] "

    onset = (T + DRIVER + "Playback URB stream stalled: no completion for 517 ms "
             "(8 URBs in flight, substream open)")
    recovery = T + DRIVER + "Capture URB stream recovered after 2043 ms"

    b, m = c.classify([onset, recovery], [])
    check(len(b[kmsg.EXPECTED]) == 2,
          "a stall that recovered is counted, not failed", str(kmsg.summarize(b)))

    h = kmsg.histogram(m.get("urb_stall_onset_ms", []))
    check(h and h["n"] == 1 and h["max"] == 517,
          "the measured onset age is captured, not the threshold", str(h))
    h = kmsg.histogram(m.get("urb_stall_recovered_ms", []))
    check(h and h["max"] == 2043, "and so is the outage duration", str(h))

    # A minute of silence cannot be a power cut: the driver has disconnected by
    # then and the watchdog has stopped.
    b, _ = c.classify(
        [T + DRIVER + "Capture URB stream still stalled: no completion for 61003 ms"], [])
    check(len(b[kmsg.UNEXPECTED]) == 1, "a persistent stall fails the run",
          str(kmsg.summarize(b)))

    # ...unless the driver says it deferred it on purpose. Capture stalling
    # while nothing records is the documented M13 behavior and can persist
    # indefinitely. driver_fail is tested before benign, so this only works
    # while the pattern above stays narrower than this one.
    deferred = (T + DRIVER + "Capture URB stream still stalled while idle: "
                "no completion for 61631 ms; recovery deferred to next capture open")
    b, m = c.classify([deferred], [])
    check(len(b[kmsg.EXPECTED]) == 1,
          "a deliberately deferred capture stall does not fail the run",
          str(kmsg.summarize(b)))
    h = kmsg.histogram(m.get("urb_stall_deferred_ms", []))
    check(h and h["max"] == 61631, "but is still counted, with its age", str(h))

    # Playback is never deferred -- it carries MIDI OUT -- so the idle wording
    # must not be reachable for it. Guards against a future edit widening the
    # benign rule to any direction.
    b, _ = c.classify(
        [T + DRIVER + "Playback URB stream still stalled: no completion for 61003 ms"], [])
    check(len(b[kmsg.UNEXPECTED]) == 1,
          "a persistent playback stall always fails", str(kmsg.summarize(b)))

    # The onset must stay countable even when a case declares it expected --
    # benign short-circuits before expect_dmesg, which is what makes
    # JT-RATE-004 possible at all.
    b, m = c.classify([onset], [r"URB stream stalled"])
    check(len(b[kmsg.EXPECTED]) == 1 and m.get("urb_stall_onset_ms"),
          "an expected onset is still measured")

    # The common ending, and the reason it exists. The first hardware run with
    # the watchdog recorded 103 onsets and zero recoveries: every recovery path
    # goes through a URB stop/start, so the restart got there first every time
    # and used to clear the flag silently, leaving every onset unpaired.
    restart = T + DRIVER + "Capture URB stream restarted after stalling for 1219 ms"
    b, m = c.classify([restart], [])
    check(len(b[kmsg.EXPECTED]) == 1, "a restart closing an outage is counted",
          str(kmsg.summarize(b)))
    h = kmsg.histogram(m.get("urb_stall_restarted_ms", []))
    check(h and h["max"] == 1219, "with the outage it ended", str(h))


def test_error_handling(rules):
    """Signatures added with the issue #26 error-handling work.

    The -ENOENT cascade these describe is driver-triggered and deterministic:
    usb_set_interface() disables an interface's endpoints before sending
    SET_INTERFACE and does not re-enable them when that request fails.
    """
    print("\nerror-handling signatures")
    c = kmsg.Classifier(rules)
    T = "[21588.823651] "
    lines = [
        T + DRIVER + "Firmware version read failed: -110",
        T + DRIVER + "Failed to clear halt on EP 0x86: -110",
        T + DRIVER + "Started only 5/8 playback and 8/8 capture URBs; ring will not refill",
        T + DRIVER + "Endpoints are disabled after a failed rate change; "
                     "the device needs a reset to restore them",
        T + DRIVER + "Failed to start URBs during initialization: -19",
        T + DRIVER + "Playback URB cancelled without a driver-initiated stop: -2",
        T + DRIVER + "Playback URB stalled when preparing playback stream",
    ]
    b, _ = c.classify(lines, [])
    check(len(b[kmsg.UNEXPECTED]) == len(lines),
          "every new error signature fails the run", str(kmsg.summarize(b)))
    check(not b[kmsg.UNCLASSIFIED], "and none of them is merely surfaced")

    # Verbatim from the 2026-08-11 16:01 functional run, where these fired five
    # times on an ordinary rmmod. The driver is bound to two interfaces and the
    # USB core unbinds them one at a time, so the first one's endpoints are
    # flushed while the other is still bound; the URBs came back -ESHUTDOWN with
    # no teardown flag set yet. Kept as a fixture because the message is only
    # worth having if it stays silent on a normal unload.
    unload = [
        T + DRIVER + "MIDI IN URB cancelled without a driver-initiated stop: -108",
        T + DRIVER + "Playback URB cancelled without a driver-initiated stop: -108",
    ]
    b, _ = c.classify(unload, [])
    check(len(b[kmsg.UNEXPECTED]) == 2,
          "an unsolicited cancellation still fails if the driver ever emits one",
          str(kmsg.summarize(b)))

    # The dev_dbg counterpart is a trace, not a fault: nothing to start because
    # the device had already gone.
    b, _ = c.classify(
        [T + DRIVER + "Could not start URBs after a rate change: device is gone"], [])
    check(len(b[kmsg.EXPECTED]) == 1,
          "while an unplug during a restart stays benign", str(kmsg.summarize(b)))

    # The .prepare message must not have been folded into the counted one.
    b, m = c.classify([T + DRIVER + "Playback URB has stalled."], [])
    check(len(b[kmsg.EXPECTED]) == 1 and m.get("stalls_playback") == 1,
          "and the poll helper's own stall message stays a counted metric")


def test_kunit_on_target(rules):
    """Verbatim transcript of a module load, timestamps and all.

    These fixtures used to be bare message text. Every anchored rule therefore
    matched in the selftest and none of them matched a real dmesg line, which
    is how 1602 lines came back unclassified from the first hardware run
    against a rule set that had always looked correct. The prefixes below are
    the point of the test as much as the messages are.
    """
    print("\ncodec KUnit output at module load")
    c = kmsg.Classifier(rules)
    b, m = c.classify([
        "[ 5871.543119]     KTAP version 1",
        "[ 5871.543120]     # Subtest: ploytec-codec",
        "[ 5871.543121]     # module: snd_reloop_jockey3",
        "[ 5871.543122]     ok 1 ploytec_test_encode_known_vectors",
        "[ 5871.543123]     ok 5 zeros",
        "[ 5871.543124]     ok 12 random00",
        "[ 5871.543125]     1..75",
        "[ 5872.282635]     # ploytec-codec: pass:21 fail:0 skip:0 total:21",
        "[ 5872.290143]     # Totals: pass:75 fail:0 skip:0 total:75",
        "[ 5872.296836]     ok 1 ploytec-codec",
    ], [])
    check(not b[kmsg.UNEXPECTED] and not b[kmsg.UNCLASSIFIED],
          "a passing suite does not pollute the run", str(kmsg.summarize(b)))
    check(m.get("kunit_cases_passed_on_target") == [21],
          "the top-level case count is recorded as a metric", str(m))

    b2, _ = c.classify(
        ["[ 5872.1] not ok 3 ploytec_test_encode_is_linear"], [])
    check(len(b2[kmsg.UNEXPECTED]) == 1, "a failing codec case fails the run")

    # A parameterized failure carries nothing identifying it as ours, so the
    # suite summary is what has to catch it.
    b3, _ = c.classify([
        "[ 5872.2]     not ok 5 zeros",
        "[ 5872.3]     # ploytec-codec: pass:20 fail:1 skip:0 total:21",
    ], [])
    check(len(b3[kmsg.UNEXPECTED]) == 1,
          "a failing parameterized case fails the run via the suite summary",
          str(kmsg.summarize(b3)))


# ------------------------------------------------------------ target model

def _kernel(arch, release, debug=(), config_available=True):
    return {"arch": arch, "release": release, "debug_options": list(debug),
            "config_available": config_available, "source": "selftest"}


def test_targets(targets):
    print("\ntarget identification")
    T = targets["targets"]
    DBG = ["KASAN", "PROVE_LOCKING"]

    for label, kern, want in [
        ("debug kernel", _kernel("x86_64", "7.2.0-rc5-alsa-debug", DBG),
         "x86_64-debug"),
        ("prod kernel", _kernel("x86_64", "7.2.0-alsa-prod"), "x86_64-prod"),
        # setlocalversion appends "+" to an untagged git tree; an exact suffix
        # match would reject every kernel built from a working tree.
        ("trailing + from an untagged tree",
         _kernel("x86_64", "7.2.0-alsa-prod+"), "x86_64-prod"),
        ("same LOCALVERSION, different arch",
         _kernel("arm64", "6.12.0-alsa-prod+"), "arm64-prod"),
        ("32-bit arm", _kernel("armhf", "6.12.0-alsa-prod"), "armhf-prod"),
    ]:
        name, _spec, err = env.detect_target(T, kern)
        check(name == want, label, err or f"got {name}")

    # Refusing to guess is the point: a run recorded against the wrong target
    # corrupts that target's history.
    name, _s, err = env.detect_target(T, _kernel("x86_64", "7.0.12-1-pve"))
    check(name is None and err, "an unlabelled kernel is refused, not guessed")
    check("LOCALVERSION" in (err or ""), "the refusal says how to fix it")

    print("\nconfiguration cross-check")
    for label, kern, target, expect in [
        ("prod label, KASAN compiled in",
         _kernel("x86_64", "7.2-alsa-prod", DBG), "x86_64-prod",
         "expects a production kernel but KASAN"),
        ("debug label, no debug options",
         _kernel("x86_64", "7.2-alsa-debug"), "x86_64-debug",
         "expects a debug kernel but none of"),
        ("config unreadable",
         _kernel("arm64", "6.12-alsa-prod", (), False), "arm64-prod",
         "could not be cross-checked"),
    ]:
        problems = env.verify_target(T[target], kern)
        check(any(expect in p for p in problems), f"mislabel: {label}",
              str(problems))

    consistent = env.verify_target(
        T["x86_64-debug"], _kernel("x86_64", "7.2-alsa-debug", DBG))
    check(not consistent, "a correctly labelled kernel raises nothing")

    print("\narchitecture normalization")
    for machine, want in [("armv6l", "armhf"), ("armv7l", "armhf"),
                          ("aarch64", "arm64"), ("i686", "i386"),
                          ("amd64", "x86_64"), ("x86_64", "x86_64")]:
        check(env.canon_arch(machine) == want, f"uname {machine} -> {want}")

    check(env.arch_from_config({"ARM64": "y", "ARM": "y"}) == "arm64",
          "arm64 configs set CONFIG_ARM too, and must not read as armhf")


def test_build_id():
    print("\nmodule identity")
    # namesz=4 ("GNU\0"), descsz=4, type=3, then the 4-byte id.
    note = (b"\x04\x00\x00\x00\x04\x00\x00\x00\x03\x00\x00\x00"
            b"GNU\x00" + b"\xde\xad\xbe\xef")
    check(env.parse_build_id_note(note) == "deadbeef",
          "a build-id note is parsed")
    check(env.parse_build_id_note(b"") is None, "a truncated note is not fatal")


# ------------------------------------------------------------- consistency

def test_catalog(catalog, targets, profiles):
    print("\ncatalog, targets and profiles")
    cases = {c["id"]: c for c in catalog["cases"]}
    caps = set(targets["capabilities"])

    check(len(cases) == len(catalog["cases"]), "case ids are unique")

    bad = [f"{c['id']} needs {r}" for c in catalog["cases"]
           for r in (c.get("requires") or []) if r not in caps]
    check(not bad, "every requirement names a known capability", str(bad[:3]))

    bad = [f"{t} has {cp}" for t, d in targets["targets"].items()
           for cp in (d.get("capabilities") or []) if cp not in caps]
    check(not bad, "every target capability is known", str(bad[:3]))

    missing = [f"{t}.{k}" for t, d in targets["targets"].items()
               for k in ("arch", "flavor", "localversion")if not d.get(k)]
    check(not missing, "every target declares arch, flavor and localversion",
          str(missing))

    lv = {}
    for t, d in targets["targets"].items():
        lv.setdefault((d.get("arch"), d.get("localversion")), []).append(t)
    clashes = {k: v for k, v in lv.items() if len(v) > 1}
    check(not clashes, "no two targets share an arch and LOCALVERSION",
          str(clashes))

    bad = []
    for p, d in profiles["profiles"].items():
        for e in d["cases"]:
            if e["id"] not in cases:
                bad.append(f"{p} -> {e['id']}")
        for t, o in (d.get("overrides") or {}).items():
            if t not in targets["targets"]:
                bad.append(f"{p} overrides unknown target {t}")
            for cid in o:
                if cid not in cases:
                    bad.append(f"{p}/{t} -> {cid}")
    check(not bad, "profiles reference only known cases and targets",
          str(bad[:3]))

    import runner
    bad = [c["id"] for c in catalog["cases"]
           if c["status"] == "implemented"
           and c["mode"] in runner.RUNNABLE_MODES and not c.get("exec")]
    check(not bad, "implemented runnable cases name an executable", str(bad))

    # A semi-automated case only runs when somebody is at the keyboard, so it
    # needs a manual form for the nights when nobody is.
    bad = [c["id"] for c in catalog["cases"]
           if c["status"] == "implemented" and c["mode"] == "semi-automated"
           and not c.get("steps")]
    check(not bad, "semi-automated cases carry manual fallback steps", str(bad))

    bad = [c["id"] for c in catalog["cases"]
           if c.get("exec") and not os.path.exists(os.path.join(HERE, c["exec"]))]
    check(not bad, "every named executable exists", str(bad))

    bad = [c["id"] for c in catalog["cases"]
           if c["status"] == "implemented" and c["mode"] == "manual"
           and not c.get("steps")]
    check(not bad, "implemented manual cases have steps to follow", str(bad))

    # A case that needs hardware not every machine has must say how to do it
    # by hand, or the coverage simply vanishes on the machines without it.
    # HARDWARE is the subset that is genuinely rig-specific -- `device` and
    # `root` are not, since a hardware case is pointless without them.
    bad = [c["id"] for c in catalog["cases"]
           if c["status"] == "implemented"
           and runner.SUBSTITUTABLE & set(c.get("requires") or [])
           and not c.get("steps")]
    check(not bad, "cases gated on an actuator carry manual fallback steps",
          str(bad))


def test_capabilities(targets):
    """Resolution, and the rule that a declaration can only take away.

    The dangerous direction is a declaration that GRANTS something absent: a
    run would record a pass for a loopback measurement with no cable in the
    socket, and nothing downstream could tell.
    """
    print("\ncapabilities")
    from lib import capabilities as cap

    check(set(cap.ALL) == set(targets["capabilities"]),
          "targets.yaml documents exactly the known capabilities",
          str(set(cap.ALL) ^ set(targets["capabilities"])))
    check(not (set(cap.PROBED) & set(cap.DECLARED)),
          "no capability is both probed and declared")

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "caps.yaml")

        with open(path, "w") as f:
            f.write("version: 1\ncapabilities:\n  speakers: true\n"
                    "  loopback-cable: false\n")
        declared, note = cap.load_declared(path)
        check(declared == {"speakers": True, "loopback-cable": False},
              "declarations are read", str(declared))
        check(note is None, "a clean file produces no complaint")

        # The veto direction: probed true, declared false -> unavailable.
        avail, detail = cap.resolve(path=path, skip_probes=True)
        check("speakers" in avail, "a declared capability is granted")
        with open(path, "w") as f:
            f.write("capabilities:\n  rtc-wake: false\n")
        _avail, detail = cap.resolve(path=path, skip_probes=True)
        check(detail["rtc-wake"]["available"] is False,
              "a declaration can withhold a probed capability")

        # The direction that must NOT work.
        with open(path, "w") as f:
            f.write("capabilities:\n  device: true\n  sox: true\n")
        avail, detail = cap.resolve(path=path, skip_probes=True)
        check("device" not in avail and "sox" not in avail,
              "a declaration cannot grant a probed capability",
              str(sorted(avail)))

        with open(path, "w") as f:
            f.write("capabilities:\n  nonsense: true\n")
        _d, note = cap.load_declared(path)
        check(note is not None and "nonsense" in note,
              "an unknown capability name is reported, not silently obeyed")

        check(cap.load_declared(os.path.join(d, "absent.yaml")) == ({}, None),
              "an absent file grants nothing and is not an error")

    avail, _detail = cap.resolve(attended=False, skip_probes=True)
    check("human" not in avail, "--unattended withholds 'human'")
    avail, _detail = cap.resolve(attended=True, skip_probes=True)
    check("human" in avail, "and an attended run grants it")


def test_capability_gating():
    """Which cases run, which demote to manual, which block."""
    print("\ncapability gating")
    import runner

    semi = {"id": "X", "mode": "semi-automated", "level": "L3",
            "requires": ["device"]}
    check(runner.capability_gap(semi, {"device"}) == ["human"],
          "a semi-automated case needs a human without saying so",
          str(runner.capability_gap(semi, {"device"})))
    check(runner.capability_gap(semi, {"device", "human"}) == [],
          "and runs when one is there")

    auto = {"id": "X", "mode": "automated", "level": "L3",
            "requires": ["device", "usb-power"]}
    check(runner.capability_gap(auto, {"device"}) == ["usb-power"],
          "a missing capability is named")
    check(runner.capability_gap(auto, {"device", "human"}) == ["usb-power"],
          "an automated case does not need a human")

    build = {"id": "X", "mode": "automated", "level": "L1",
             "requires": ["kernel-tree"]}
    check(runner.capability_gap(build, set()) == [],
          "build levels are exempt -- they check for themselves")

    steps = {"steps": ["do a thing"]}
    check(runner.demotes_to_manual(steps, ["usb-power"]),
          "a missing actuator demotes to manual -- a person can unplug it")
    check(not runner.demotes_to_manual({}, ["usb-power"]),
          "unless nobody wrote down how")
    check(not runner.demotes_to_manual(steps, ["device"]),
          "a missing DEVICE never demotes: there is nothing to test by hand")
    check(not runner.demotes_to_manual(steps, ["usb-power", "device"]),
          "and one substitutable gap does not excuse an unsubstitutable one")


def test_results_roundtrip():
    print("\nresult records")
    run = results.Run(run_id="t", profile="smoke", target="x86_64-debug",
                      started=results.utc_iso())
    run.add(results.CaseResult(id="JT-PCM-002", status=results.PASS))
    run.add(results.CaseResult(id="JT-RATE-001", status=results.FAIL))
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "run.json")
        results.write(run, path)
        back = results.read(path)
    check(back["counts"] == {"pass": 1, "fail": 1}, "counts are derived",
          str(back.get("counts")))
    check(len(back["results"]) == 2, "results survive the round trip")


def test_case_streaming():
    """A case's progress reaches the terminal while it is still running.

    The failure this guards against is not a wrong answer but an unusable
    one: capture_output holds every byte until exit, so a case that
    power-cycles a device ten times was eighty seconds indistinguishable
    from a hang.

    The second half matters more. Once a case is chatty, the naive "first
    200 characters of stderr" reason reports its opening progress line as the
    cause of a failure that happened a minute later.
    """
    print("\ncase streaming")
    import runner

    script = ("import sys, time\n"
              "for i in (1, 2, 3):\n"
              "    print(f'cycle {i}/3', file=sys.stderr, flush=True)\n"
              "    time.sleep(0.05)\n"
              "print('artifact', flush=True)\n"
              "print('FAIL: cycle 3 broke', file=sys.stderr)\n"
              "print('cycle 3 broke', file=sys.stderr)\n"
              "sys.exit(1)\n")
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "case.py")
        with open(path, "w") as f:
            f.write(script)

        seen = []
        rc, out, err = runner.stream_case(
            [sys.executable, path], dict(os.environ), 30,
            lambda ln, transient=False: seen.append(ln))
        check(rc == 1, "the exit status survives streaming", str(rc))
        check(seen and seen[0] == "cycle 1/3",
              "progress is delivered line by line as it arrives", str(seen[:1]))
        check(len(seen) == 5, "every stderr line is echoed", str(len(seen)))
        check(out.strip() == "artifact",
              "stdout stays separate and is captured, not echoed", repr(out))
        check("cycle 1/3" in err and "cycle 3 broke" in err,
              "and stderr is captured in full as well")

        check(runner.failure_reason(err, out, rc) == "cycle 3 broke",
              "the reason is the LAST line, not the first progress line",
              runner.failure_reason(err, out, rc))

        # THE ONE THAT MATTERS FOR INTERACTIVE CASES.
        #
        # Several lines written at once, then a long silence -- which is
        # exactly a case reporting progress and then asking a question. Every
        # line must arrive during the silence, not be held until the next
        # write. A buffered readline() passes the test above, where each line
        # is separated by a sleep, and fails this one: it returns the first
        # line and leaves the rest in a buffer that select() cannot see, so
        # the prompt stays invisible and the operator and the case wait for
        # each other. Observed on hardware before it was pinned here.
        with open(path, "w") as f:
            f.write("import sys, time\n"
                    "for i in (1, 2, 3):\n"
                    "    print(f'blink {i}/3 sent', file=sys.stderr)\n"
                    "print('?? did it blink? [y/n]', file=sys.stderr)\n"
                    "sys.stderr.flush()\n"
                    "time.sleep(3)\n")
        seen, times = [], []
        t0 = time.time()
        runner.stream_case([sys.executable, path], dict(os.environ), 30,
                           lambda ln, transient=False: (
                               seen.append(ln), times.append(time.time() - t0)))
        check(len(seen) == 4, "every line written in one burst is delivered",
              str(seen))
        check(seen and seen[-1].startswith("??"),
              "including the prompt, which is the last thing written",
              str(seen[-1:]))
        check(times and times[-1] < 2.0,
              "and it arrives while the case is still waiting, not after",
              f"prompt shown after {times[-1] if times else -1:.1f}s of a 3s wait")

        # A case that wedges must be killed at the deadline, not waited on.
        with open(path, "w") as f:
            f.write("import time\ntime.sleep(60)\n")
        t0 = time.time()
        rc, _out, err = runner.stream_case(
            [sys.executable, path], dict(os.environ), 1, None)
        check(rc == 124 and time.time() - t0 < 10,
              "a silent case is killed at its timeout", f"rc={rc}")
        check("timed out" in err, "and says so", err)

    check(runner.mark(results.PASS) != runner.mark(results.FAIL),
          "pass and fail are visually distinct at a glance")


def test_terminal():
    """Styling is applied on the way to the screen and nowhere else.

    The property worth defending is that no escape sequence ever reaches a
    file. A coloured stderr.txt is unreadable a year later and defeats grep,
    so cases emit plain text and only the runner paints it.
    """
    print("\nterminal styling")
    from lib import term

    plain, painted = term.Style(enabled=False), term.Style(enabled=True)
    check(plain("hello", "bold", "red") == "hello",
          "disabled, styling is the identity function")
    check("\033[" in painted("hello", "bold", "red"),
          "enabled, it emits SGR codes")

    saved = os.environ.get("NO_COLOR")
    try:
        os.environ["NO_COLOR"] = "1"
        check(not term.supported(io.StringIO()), "NO_COLOR is honoured")
    finally:
        if saved is None:
            os.environ.pop("NO_COLOR", None)
        else:
            os.environ["NO_COLOR"] = saved
    check(not term.supported(io.StringIO()),
          "and a non-terminal is never painted")

    check(term.visible_len(painted("abc", "bold", "red")) == 3,
          "a styled string is measured by the columns it occupies, not bytes",
          str(term.visible_len(painted("abc", "bold", "red"))))

    check(term.decorate(plain, ">> do a thing") == "▶ do a thing",
          "an instruction is marked by the prefix the case wrote",
          term.decorate(plain, ">> do a thing"))
    check(term.decorate(plain, "?? really?") == "◆ really?",
          "and so is a question")

    # A transient line redraws in place on a terminal...
    out = io.StringIO()
    live = term.Live(out=out, enabled=True, indent="  ")
    live.write("counting 3", transient=True)
    live.write("counting 2", transient=True)
    live.write("done", transient=False)
    text = out.getvalue()
    check(text.count("\n") == 1,
          "on a terminal, only the line that stays gets a newline", repr(text))
    check(text.endswith("  done\n"), "and the last word is the one that stays",
          repr(text[-20:]))

    # ...and becomes ordinary lines anywhere else, because a log that
    # overwrote itself is a log that lost its history.
    out = io.StringIO()
    live = term.Live(out=out, enabled=False, indent="  ")
    live.write("counting 3", transient=True)
    live.write("counting 2", transient=True)
    live.write("done", transient=False)
    check(out.getvalue() == "  counting 3\n  counting 2\n  done\n",
          "redirected, every update is kept as its own line",
          repr(out.getvalue()))


def test_operator_prompts():
    """Asking a person something, without deadlocking on them.

    The prompt must end in a newline. The runner streams stderr with
    readline(), so a prompt written without one is held in the pipe forever:
    the operator waits for a question that never appears while the case waits
    for an answer to a question never asked. It is invisible in isolation and
    only shows up on hardware, which is exactly why it is pinned here.
    """
    print("\noperator prompts")
    from lib.case import Case

    saved_in, saved_err = sys.stdin, sys.stderr
    saved_env = os.environ.get("JT_ATTENDED")
    try:
        os.environ["JT_ATTENDED"] = "1"
        r, w = os.pipe()
        os.write(w, b"y\n")
        os.close(w)
        sys.stdin = os.fdopen(r)
        sys.stderr = io.StringIO()

        c = Case()
        answer = c.confirm("did the LEDs blink?", timeout=5)
        written = sys.stderr.getvalue()
        sys.stderr = saved_err

        check(answer is True, "a yes is read back as True", str(answer))
        check(written.endswith("\n"),
              "every byte written to the operator ends a line -- an "
              "unterminated prompt never leaves the pipe", repr(written[-30:]))
        check("did the LEDs blink?" in written,
              "and the question itself reaches them", repr(written))

        # The answer is evidence and belongs in the record, not only on screen.
        check(any("did the LEDs blink? -> y" in n for n in c._note),
              "the answer is recorded, not just displayed", str(c._note))

        # Unattended, asking must return at once rather than wait for a person
        # who is not there -- the runner normally prevents this, but a case
        # reached out of band must not hang the machine.
        os.environ["JT_ATTENDED"] = "0"
        sys.stderr = io.StringIO()
        t0 = time.time()
        c2 = Case()
        unattended = c2.confirm("anybody there?", timeout=30)
        sys.stderr = saved_err
        check(unattended is None and time.time() - t0 < 1.0,
              "unattended, a question is not asked and does not block",
              f"{unattended} after {time.time() - t0:.1f}s")
    finally:
        sys.stdin, sys.stderr = saved_in, saved_err
        if saved_env is None:
            os.environ.pop("JT_ATTENDED", None)
        else:
            os.environ["JT_ATTENDED"] = saved_env


def test_semi_automated_routing():
    """A semi-automated case runs; without an operator it defers."""
    print("\nsemi-automated routing")
    import runner

    check("semi-automated" in runner.RUNNABLE_MODES,
          "the runner executes semi-automated cases rather than filing them "
          "with the manual ones")

    case = {"id": "X", "mode": "semi-automated", "level": "L3",
            "requires": ["device"], "steps": ["do the thing"]}
    attended = runner.capability_gap(case, {"device", "human"})
    check(attended == [], "with an operator present it simply runs",
          str(attended))

    gap = runner.capability_gap(case, {"device"})
    check(gap == ["human"], "without one, the gap is the person", str(gap))
    check(runner.demotes_to_manual(case, gap),
          "which DEFERS to the checklist rather than blocking -- an "
          "unattended run postpones coverage, it does not lack it")

    check(not runner.demotes_to_manual({"mode": "semi-automated"}, ["human"]),
          "unless the case never wrote down its manual form")


def test_manual_fallback():
    """A case demoted to manual must reach the checklist intact.

    The parameters are the part that rots silently. checklist.py renders what
    the RUN RECORD says, so if the runner records a pending case without its
    resolved parameters, every per-target override is quietly undone -- the
    operator on a Pi 1B is handed the catalog's four sample rates when the
    profile deliberately says two, and nothing anywhere reports a problem.
    """
    print("\nmanual fallback")
    import checklist
    catalog = load("catalog.yaml")
    cases = {c["id"]: c for c in catalog["cases"]}

    with tempfile.TemporaryDirectory() as d:
        run = {"results": [
            {"id": "JT-AUDIO-001", "status": results.PENDING, "mode": "manual",
             "params": {"rates": [44100]},
             "reason": "manual -- answer via checklist.py"},
            {"id": "JT-PROBE-003", "status": results.PENDING, "mode": "manual",
             "params": {"iterations_per_run": 3},
             "reason": "no usb-power -- do it by hand via checklist.py"},
            {"id": "JT-PCM-002", "status": results.PASS, "mode": "automated",
             "params": {}},
            {"id": "JT-AUDIO-002", "status": results.BLOCKED,
             "mode": "automated", "params": {}},
        ]}
        with open(os.path.join(d, "run.json"), "w") as f:
            f.write(json.dumps(run))

        items = checklist.pending_cases(d, cases)
        ids = [c["id"] for c, _p, _r in items]
        check(ids == ["JT-AUDIO-001", "JT-PROBE-003"],
              "only pending cases reach the checklist", str(ids))
        check(all(s != "JT-AUDIO-002" for s in ids),
              "a blocked case is not offered -- it cannot be done here at all")

        params = {c["id"]: p for c, p, _r in items}
        check(params["JT-PROBE-003"] == {"iterations_per_run": 3},
              "the RESOLVED parameters are rendered, not the catalog defaults",
              str(params["JT-PROBE-003"]))

        md = checklist.render("functional", "armhf-prod", items, "t/x")
        demoted = "JT-PROBE-003 -- " in md and "Automated form could not run" in md
        check(demoted, "a demoted case says why it is being done by hand")
        after = md.split("## JT-AUDIO-001")[1].split("## ")[0]
        check("Automated form could not run" not in after,
              "a case that is manual by nature does not claim to be a fallback")


def test_run_resolution():
    """Finding the run a manual checklist belongs to.

    The failure this guards against is quiet: answers imported into the wrong
    run, or into a run from last week, look exactly like answers imported
    correctly.
    """
    print("\nrun resolution")
    import checklist
    with tempfile.TemporaryDirectory() as d:
        base = os.path.join(d, "x86_64-debug")
        os.makedirs(base)
        for stamp in ("20260808T100000Z-smoke", "20260809T100000Z-smoke",
                      "20260809T110000Z-functional"):
            os.makedirs(os.path.join(base, stamp))
            with open(os.path.join(base, stamp, "run.json"), "w") as f:
                f.write("{}")
        os.makedirs(os.path.join(base, "not-a-run"))

        p, _age = results.find_latest_run(d, "x86_64-debug", "smoke")
        check(os.path.basename(p) == "20260809T100000Z-smoke",
              "the newest run for the profile wins", str(p))
        p2, _ = results.find_latest_run(d, "x86_64-debug", "functional")
        check(os.path.basename(p2) == "20260809T110000Z-functional",
              "profiles do not bleed into each other")
        check(results.find_latest_run(d, "x86_64-debug", "soak") == (None, None),
              "an absent profile resolves to nothing, not to something else")
        check(results.parse_run_dir("not-a-run") is None,
              "a directory that is not a run is ignored")

        # Age is computed from the stamp, not from mtime: these directories
        # were created seconds ago but claim to be from 2026-08-08.
        old, age = results.find_latest_run(d, "x86_64-debug", "functional")
        check(age is not None and age >= 0, "age comes from the run stamp",
              str(age))

    # A rendered checklist must name its run, and that name must survive being
    # read back -- otherwise --import silently falls back to guessing.
    md = checklist.render("smoke", "x86_64-debug",
                          [({"id": "JT-MIDI-002", "title": "t", "level": "L3",
                             "area": "MIDI", "mode": "manual",
                             "steps": ["do a thing"], "pass": "it works"},
                            {}, "")],
                          "x86_64-debug/20260809T182522Z-smoke")
    m = checklist.RUN_RE.search(md)
    check(m and m.group("path") == "x86_64-debug/20260809T182522Z-smoke",
          "a rendered checklist carries the run it belongs to",
          str(m and m.group("path")))
    check(checklist.ANSWER_RE.search(md) is not None,
          "and still carries a machine-readable answer line")


def test_privilege_boundary():
    """The helper is the whole privileged surface, so drift in it is silent.

    None of this needs root: it compares the repository's helper against the
    Python that drives it. The failure these catch is a verb renamed on one
    side only, which shows up at runtime as a case that is blocked or, worse,
    as log slicing that quietly stops working.
    """
    print("\nprivilege boundary")
    helper = os.path.join(HERE, "priv", "jockey3-testctl")
    check(os.path.exists(helper), "the helper exists in the repository")
    if not os.path.exists(helper):
        return
    src = open(helper, encoding="utf-8").read()

    rc = subprocess.run(["bash", "-n", helper], capture_output=True)
    check(rc.returncode == 0, "the helper is syntactically valid",
          rc.stderr.decode()[:120])

    # Verbs the script implements, taken from the case labels of its dispatch.
    implemented = set(re.findall(r"^([a-z][a-z-]*)\)$", src, re.M))
    called = set(re.findall(r'call\(\s*"([a-z][a-z-]*)"',
                            open(os.path.join(HERE, "lib", "priv.py"),
                                 encoding="utf-8").read()))
    check(called <= implemented, "every verb priv.py calls is implemented",
          f"missing: {sorted(called - implemented)}")

    # The marker token is generated in kmsg.py and validated in the helper.
    # If those two drift, markers are silently rejected and every case gets
    # classified against the entire boot log instead of its own slice.
    pat = re.search(r"=~ (\^JT-MARK.*?) \]\]", src)
    check(pat is not None, "the helper validates the marker token")
    if pat:
        token = kmsg.Marker("JT-PROBE-001#1").token
        rx = pat.group(1).replace("\\ ", " ")
        check(re.match(rx, token) is not None,
              "a generated marker token passes the helper's validation",
              f"token={token!r} pattern={rx!r}")

    # Nothing outside priv.py may reach for root on its own.
    strays = []
    for sub in ("lib", "cases"):
        for name in sorted(os.listdir(os.path.join(HERE, sub))):
            if not name.endswith(".py") or name == "priv.py":
                continue
            body = open(os.path.join(HERE, sub, name), encoding="utf-8").read()
            if re.search(r'["\[]\s*"sudo"|geteuid\(\)\s*!=\s*0', body):
                strays.append(f"{sub}/{name}")
    check(not strays, "only priv.py reaches for privilege", str(strays))

    # A local read before it is assigned. Python only notices at run time, and
    # a dry run never executes a case body -- so JT-AUDIO-005 shipped with its
    # actuator chosen from a `settle` that was parsed three lines later, and
    # the first anyone knew was an UnboundLocalError on the bench.
    #
    # Deliberately conservative: names bound by a loop or comprehension are
    # skipped, since those legitimately read what an earlier iteration bound.
    # It catches straight-line ordering mistakes, which is the one that bit.
    early = []
    for sub in ("lib", "cases", "actions", "."):
        base = os.path.join(HERE, sub)
        for name in sorted(os.listdir(base)):
            if not name.endswith(".py"):
                continue
            path = os.path.join(base, name)
            try:
                tree = ast.parse(open(path, encoding="utf-8").read(), path)
            except SyntaxError as e:
                early.append(f"{sub}/{name}: {e}")
                continue
            for fn in ast.walk(tree):
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                bound, loopy = {}, set()
                for node in ast.walk(fn):
                    if isinstance(node, (ast.For, ast.While)):
                        for sub2 in ast.walk(node):
                            if (isinstance(sub2, ast.Name)
                                    and isinstance(sub2.ctx, ast.Store)):
                                loopy.add(sub2.id)
                    if isinstance(node, ast.comprehension):
                        for sub2 in ast.walk(node.target):
                            if isinstance(sub2, ast.Name):
                                loopy.add(sub2.id)
                    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                        bound[node.id] = min(bound.get(node.id, node.lineno),
                                             node.lineno)
                args = {a.arg for a in fn.args.args + fn.args.kwonlyargs}
                if fn.args.vararg:
                    args.add(fn.args.vararg.arg)
                if fn.args.kwarg:
                    args.add(fn.args.kwarg.arg)
                for node in ast.walk(fn):
                    if (isinstance(node, ast.Name)
                            and isinstance(node.ctx, ast.Load)
                            and node.id in bound and node.id not in args
                            and node.id not in loopy
                            and node.lineno < bound[node.id]):
                        early.append(f"{sub}/{name}:{node.lineno}: "
                                     f"{fn.name}() reads '{node.id}' before "
                                     f"line {bound[node.id]} assigns it")
    check(not early, "no local is read before it is assigned",
          "; ".join(early[:4]))


def main():
    rules = load(os.path.join("lib", "rules.yaml"))
    catalog = load("catalog.yaml")
    targets = load("targets.yaml")
    profiles = load("profiles.yaml")

    test_classifier(rules)
    test_wedged_device(rules)
    test_watchdog(rules)
    test_error_handling(rules)
    test_kunit_on_target(rules)
    test_targets(targets)
    test_build_id()
    test_catalog(catalog, targets, profiles)
    test_capabilities(targets)
    test_capability_gating()
    test_results_roundtrip()
    test_terminal()
    test_operator_prompts()
    test_semi_automated_routing()
    test_case_streaming()
    test_manual_fallback()
    test_run_resolution()
    test_privilege_boundary()

    print(f"\n{_checks - len(_failures)}/{_checks} checks passed")
    if _failures:
        print("\nfailed:")
        for f in _failures:
            print(f"  {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
