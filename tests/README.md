# tests/

Everything used to test this driver, in three parts.

| Path | What it is |
|---|---|
| `codec/` | Codec correctness and benchmarking. Runs anywhere, needs no hardware. Guide: **[../docs/codec_testing.md](../docs/codec_testing.md)** |
| `hw/` | The test runner, catalog and cases that exercise the driver against real hardware. Guide: **[../docs/test_strategy.md](../docs/test_strategy.md)** |
| `build/` | Syncing sources into a kernel tree, the L1 gates, and building target kernels and modules. Guide: **[../docs/environments.md](../docs/environments.md)** |
| `scripts-alsa-dev/` | Archive of the ad-hoc scripts this suite grew out of. Kept for reference; not maintained. |

Before building anything, read **[../docs/environments.md](../docs/environments.md)**:
the driver lives in five trees at once, and which one you build in decides
whether you get a verdict, a loadable module, or a module that silently will
not insert.

---

## `codec/`

| Path | What it is |
|---|---|
| `ploytec_model.py` | Independent model of the wire format, derived structurally rather than copied from the C. The oracle everything else is anchored to. |
| `genvectors.py` | Turns the model into `../../ploytec_codec_test_vectors.h`, the golden vectors shared by the KUnit suite and the bench. |
| `run_kunit.sh` | Runs the in-kernel KUnit suite, under UML or cross-built for QEMU. |
| `codecbench.py` | Builds, validates and benchmarks the codec in user space. |
| `harness/` | The C bench: `main.c`, the implementation registry, and the kernel-header stubs that let driver source compile in user space. |
| `candidates/` | Experimental codec implementations. Drop a file in, rerun `./codecbench.py test`. |
| `build/` | Generated; git-ignored. Holds the verbatim copy of the driver codec plus its SHA-256 manifest. |

```sh
cd tests/codec
./run_kunit.sh                 # KUnit under UML
./run_kunit.sh --list          # which cross targets are runnable

./codecbench.py test           # correctness, every implementation
./codecbench.py bench --quick  # fast, noisy benchmark
./codecbench.py bench          # 30s per measurement, trustworthy
./codecbench.py check-sync     # is build/ still the current driver code?
```

### Two things worth knowing

**The driver source is copied, not symlinked.** `codecbench.py build` takes a
verbatim copy into `build/src/` and records its SHA-256. `check-sync` fails if
the driver has moved on since, so a benchmark number cannot be attributed to
the wrong revision. Run it before quoting figures.

**Nothing here requires changes to the driver.** All three codec variants are
built from that single copy by compiling it three times with different
`CONFIG_*` defines and renaming its public symbols on the command line. The
driver has no exports, `#ifdef`s or hooks added for testing, and it must stay
that way.

---

## `hw/`

| Path | What it is |
|---|---|
| `runner.py` | Coordinator. Runs a profile on this machine and writes a result record. |
| `catalog.yaml` | The register of every test case, implemented or not. |
| `targets.yaml` | The machines and kernel flavors tests run on. |
| `profiles.yaml` | Which cases run, how many times, with what parameters, per target. |
| `lib/` | Environment capture, dmesg classification, ALSA helpers, result schema. |
| `cases/` | One executable per automated case. |
| `actions/` | Small reusable steps (load the driver, play a tone, change rate). |
| `checklist.py` | Renders manual cases to a checklist and reads the answers back. |
| `ledger.py` | What has been tested, on what, how recently — and metric trends. |
| `selftest.py` | Tests for the framework itself. No hardware, no root. |
| `priv/` | The suite's entire privileged surface: one root-owned helper, one sudoers entry. Guide: **[priv/README.md](hw/priv/README.md)** |
| `results/` | Generated; git-ignored. |

```sh
cd tests/hw
sudo priv/install.sh                      # once per machine; the only password
./runner.py --list                        # cases and profiles
./runner.py --profile smoke --dry-run     # what would run here
./runner.py --profile smoke               # run it -- as an ordinary user
./ledger.py                               # coverage and staleness
./selftest.py                             # check the framework itself
```

The runner is **not** run under sudo. Playback, capture, MIDI and sysfs need no
privilege; the few operations that do go through `priv/jockey3-testctl`. The
test user needs to be in the `audio` group, and nothing more.

The runner executes **on the machine with the hardware attached**, not on a
build host. That is what lets the same suite run on a Raspberry Pi you plugged
in five minutes ago.

### Manual cases

Some cases need a human: nobody has wired a photodiode to the LEDs, and no
metric catches "slight crackle on headphone right, only at 96 kHz" as well as
an ear does. Those live in the same catalog and the same profiles as the
automated ones, so coverage is one picture rather than two — the runner marks
them `PENDING` and moves on.

`checklist.py` renders them to markdown, you fill it in, and it reads the
answers back into the same run record:

```sh
./runner.py --profile smoke                      # JT-MIDI-002 -> PENDING
./checklist.py --run results/.../run.json > /tmp/checklist.md
$EDITOR /tmp/checklist.md                        # do the tests, record verdicts
./checklist.py --import /tmp/checklist.md --run results/.../run.json
```

Pass `--run` and the profile and target come from the run record, so the
checklist cannot describe something other than what was run. Without it, name
a `--profile` (default `functional`) and the target is detected from the
running kernel exactly as the runner detects it. It is never assumed: the
target selects the per-target overrides in `profiles.yaml`, so a wrong one
renders the wrong cases with the wrong parameters — on `armhf-prod` the audio
cases run at two sample rates, not four.

Each case ends with one machine-readable line. Edit the `result:` and add a
comment; everything else in the file is for you:

```
- id: JT-MIDI-002 | result: pass | comment: all LEDs lit, attract mode stopped
```

`result:` takes `pass`, `fail`, `skip` or `blocked`. Leave it as `?` and that
case stays pending. On import the run's outcome is re-derived — with one
exception: a run already marked `INVESTIGATE` stays that way, because a kernel
defect outranks any number of manual passes. An answer for a case that was not
in the run is appended rather than discarded, since coverage that happened is
coverage.

A comment on a *passing* case is not wasted effort. It is how the next bug gets
found early.
