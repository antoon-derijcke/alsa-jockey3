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

    bad = [c["id"] for c in catalog["cases"]
           if c["status"] == "implemented" and c["mode"] == "automated"
           and not c.get("exec")]
    check(not bad, "implemented automated cases name an executable", str(bad))

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
    import runner
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
            "requires": ["device", "usb-switch"]}
    check(runner.capability_gap(auto, {"device"}) == ["usb-switch"],
          "a missing capability is named")
    check(runner.capability_gap(auto, {"device", "human"}) == ["usb-switch"],
          "an automated case does not need a human")

    build = {"id": "X", "mode": "automated", "level": "L1",
             "requires": ["kernel-tree"]}
    check(runner.capability_gap(build, set()) == [],
          "build levels are exempt -- they check for themselves")

    steps = {"steps": ["do a thing"]}
    check(runner.demotes_to_manual(steps, ["usb-switch"]),
          "a missing actuator demotes to manual -- a person can unplug it")
    check(not runner.demotes_to_manual({}, ["usb-switch"]),
          "unless nobody wrote down how")
    check(not runner.demotes_to_manual(steps, ["device"]),
          "a missing DEVICE never demotes: there is nothing to test by hand")
    check(not runner.demotes_to_manual(steps, ["usb-switch", "device"]),
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
            [sys.executable, path], dict(os.environ), 30, seen.append)
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
             "reason": "no usb-switch -- do it by hand via checklist.py"},
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


def main():
    rules = load(os.path.join("lib", "rules.yaml"))
    catalog = load("catalog.yaml")
    targets = load("targets.yaml")
    profiles = load("profiles.yaml")

    test_classifier(rules)
    test_kunit_on_target(rules)
    test_targets(targets)
    test_build_id()
    test_catalog(catalog, targets, profiles)
    test_capabilities(targets)
    test_capability_gating()
    test_results_roundtrip()
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
