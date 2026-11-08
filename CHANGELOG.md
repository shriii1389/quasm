# Changelog

All notable changes to QuAsm. Versions follow [semantic versioning](https://semver.org/);
the format is loosely [Keep a Changelog](https://keepachangelog.com/).

## [1.0.0] - 2026-11-08

The first release.

### Language

- Registers of **1 to 6 qubits**, `qubit q[n]` or explicit amplitudes
  `qubit q = [(re,im),...]` (any power-of-two count; unnormalised registers are measured
  in proportion).
- Gates on **any** qubit of a register: `H I X Y Z S T SN SDG TDG`, and two-qubit
  `CN SW CY CZ CP1..CP6` on any distinct control and target
  (`qubitop2 q[2],q[0] = CN`).
- The controlled-phase family `CP1..CP6`, enough to write the quantum Fourier transform
  directly (`examples/qft.dsl`).
- `measure q[k]` and `measure q`, with collapse and renormalisation, and `-> c` to keep
  the outcome in a classical variable. A seedable PRNG (`seed n`) makes runs reproducible.
- `noise p`: a depolarising channel sampled as one quantum trajectory per run.
- Classical control: `set`, `if` / `else if` / `else` / `endif` with
  `== != < <= > >=`, and `repeat n ... endrepeat`, both nesting 8 deep.
- `end` inside a block stops execution early.
- **Every input limit is enforced with a line-numbered error** (`Line 12: Qubit index out
  of range`) instead of a silently wrapped or truncated value. A bad line is reported and
  skipped; the rest of the program still runs (`examples/errors.dsl`).

### Tooling

- `tools/quasm.py`: run a `.dsl` file from the command line; `--check` replays the run
  through the NumPy oracle and reports whether every printed state agreed.
- `tools/quasm_gui.py`: a Tkinter editor with a Run button, a dropdown of examples, and the
  same oracle check.
- `tools/rars_server.py`: one long-lived RARS per worker, so the whole test corpus runs
  in under a minute instead of paying for a cold JVM per program.
- `tools/fetch_rars.sh`: downloads RARS v1.6 and checks its SHA-256.

### Verification

Six independent layers, each answering a question the others cannot:

- `tools/reference_sim.py`: a NumPy oracle built on *different algorithms* from the
  assembly (tensor contraction vs bit-indexed walks, a parsed block tree vs line replay).
- `tools/run_tests.py`: 230 test programs through both engines, errors checked in both
  directions; measurement checked by replaying the outcomes RARS reported.
- `tools/check_gate_data.py`: a static audit that every gate matrix in `main.s` is
  unitary and is the gate it claims to be.
- `tools/cross_validate.py`: agreement with Qiskit over seeded random circuits, with a
  qubit mapping fixed a priori and a self-test that proves it.
- `tools/properties.py`: eight metamorphic properties, each with a self-test that breaks
  it on purpose.
- `tools/fuzz.py`: grammar-based differential fuzzing of the assembly against the oracle.
- `tools/mutate.py`: mutation analysis measuring what each of the above catches.

CI (`.github/workflows/tests.yml`) runs the fast checks and the full suite on every push;
the hours-long mutation and RARS-inclusive sweeps run weekly (`deep.yml`).

### Defects found on the way here

- Three that had got through a passing test suite: a controlled-Z that encoded `Z⊗I`,
  a non-unitary `SN` gate, and a measurement routine that computed `P(0) = 1 - P(1)`,
  which is wrong for any unnormalised register.
- A hardening round with hostile inputs and the fuzzer: seventeen more in the
  interpreter, all silent wrong behaviour, and thirteen in the oracle, the harness and the
  mutation tool.

Every one is listed by class, with what now guards against it, in
[docs/DEFECTS.md](docs/DEFECTS.md).

### Documentation

- [docs/LANGUAGE.md](docs/LANGUAGE.md), the full language reference.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), how the interpreter works.
- [docs/DEFECTS.md](docs/DEFECTS.md), the defect log.
- [docs/screenshots/](docs/screenshots/), the program running.
- [paper/quasm.pdf](paper/quasm.pdf), the write-up, with a claims ledger in
  [paper/CLAIMS.md](paper/CLAIMS.md).

[1.0.0]: https://github.com/shriii1389/quasm/releases/tag/v1.0.0
