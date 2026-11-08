# Contributing to QuAsm

## Reporting a bug

Open an issue with the smallest program that shows it, what QuAsm printed, and what you
expected. Run it with `--check` first and say what that reported:

```sh
python tools/quasm.py yourprogram.dsl --check
```

If the oracle disagrees with the assembly, that alone is a bug in one of them, and the
`MISMATCH` line says which output differs. If they agree and both look wrong to you, say
why, ideally against the physics or against Qiskit. That is the case most worth reporting,
because no check here can see a misconception both implementations share.

## Getting set up

You need three things:

1. **A JDK**, 11 or newer. `winget install EclipseAdoptium.Temurin.21.JDK`, or your
   platform's equivalent.
2. **The RARS jar** — `tools/fetch_rars.sh`, or download `rars1_6.jar` from
   [the RARS releases page](https://github.com/TheThirdOne/rars/releases) into `tools/`.
   It is gitignored: it is a third-party binary and does not belong in this repo.
3. **Python 3.9+ with NumPy**, for the reference oracle and the test harness.

If `java` is not on your PATH, set `QUASM_JAVA` to the binary. Everything —
`run_tests.py`, `quasm.py`, `quasm_gui.py` — honours it.

Check the setup works:

```sh
python tools/quasm.py examples/bell.dsl --check
```

## Running the tests

```sh
python tools/run_tests.py               # everything
python tools/run_tests.py cond_ loop_   # only files whose names contain these
```

Programs run through `tools/rars_server.py`, which keeps one RARS process per worker and
assembles the interpreter once, so `python tools/run_tests.py -j 4` covers the whole corpus
in a minute or two. For a single program:

```sh
printf 'qubit q[2]\nqubitop1 q[0] = H\nprint(q)\nend\n' | java -jar tools/rars1_6.jar nc sm main.s
python tools/quasm.py somefile.dsl --check
```

`nc` suppresses the banner and `sm` starts at `main`. Do **not** pass RARS's `p` project
flag: `main.s` already `.include`s every other file, and project mode would assemble them
all a second time.

### The checks that are not the test suite

`run_tests.py` is one of six layers. These three need no JVM and run in seconds, so there
is no excuse for skipping them before you push:

```sh
python tools/check_gate_data.py       # the gate matrices are unitary and correct
python tools/properties.py --n 200    # metamorphic properties over random states
python tools/cross_validate.py --seed 0 --n 500     # agreement with Qiskit
```

`properties.py` and `cross_validate.py` carry a `--self-test` that deliberately breaks the
thing being checked and confirms the check notices. **Run these if you touch either harness** — a check that
cannot fail is worse than no check, because it looks like evidence:

```sh
python tools/properties.py --self-test
python tools/cross_validate.py --self-test
```

If you change the parser or the block machinery, `python tools/fuzz.py --n 300 -j 4` runs
generated programs through both engines in a few minutes. If you change a gate matrix or
the kernel, `python tools/mutate.py --stage1 --code-mutants 0` reports what the layers
would still catch. Note the rule the cross-validator is built
around: **the Qiskit qubit mapping is fixed a priori and is never adjusted to make a
comparison pass.** A disagreement is a bug report, not a prompt to retune the mapping.

## Conventions

**Comments stay sparse.** Short trailing `#` notes on lines that are not obvious, a few
lines above a routine saying what it takes and returns. No block comments, no boxes, no
restating what the instruction already says. Match what is already there.

**Every statement handler returns `a0 = 0` or an error code, having unwound its own frame.**
Never jump to the error printer from inside a routine that has pushed one — that was a real
bug, and it leaked a frame per error for the length of a session.

**Save what you write.** Any routine that writes `s0`-`s10` saves and restores it. `s11` is
the amplitude arena's bump pointer and is globally live: `main` and `alloc_room` write it,
nothing else may.

**Put `.align 2` before any `.space` region you will access with `lw`/`sw`.** `.space` does
not pad, and RARS kills the program silently on a misaligned word access — no message, exit
status 0.

**Keep `starts_with`'s arguments straight**: `t0` is the input, `t1` is the pattern, and the
pattern terminates first. Use `token_eq` when the input token must end where the pattern
does — that is what stops `end` matching `endrepeat`.

## Adding a language feature

Roughly the path `if`/`else` took:

1. Parse and execute it in the assembly. New error codes get a string in `main.s` and an
   arm in `report_error` (`errors.s`).
2. Add it to the dispatcher in `main.s`. Watch the ordering — a keyword that is a prefix of
   another must be checked after it, which is why `endrepeat` and `endif` come before `end`.
3. Teach `skip_line` about it if it opens or closes a block, or a `repeat 0` body
   containing it will be miscounted.
4. Implement it in `tools/reference_sim.py` **from the language semantics, not from your
   assembly**. The oracle is only worth having because it is an independent second opinion;
   transcribing the assembly into Python would make every test tautological.
5. Add test programs, including the error paths.
6. Document it in `docs/LANGUAGE.md`, and the mechanism in `docs/ARCHITECTURE.md`.

## Adding a test

Test programs are plain DSL text in `tests/programs/`, one statement per line, ending in
`end`. Comment lines of the form `# key: value` using a known key are directives to the
harness; every other comment is passed through to the interpreter, so the corpus exercises
DSL comments as a side effect.

| Key | Meaning |
|-----|---------|
| `name` | the test's name in the report; defaults to the filename |
| `expect_error` | this substring must appear in the output; no oracle comparison is done |
| `expect_freq` | `<bits> <p> <tol>` — an outcome's empirical frequency against the Born rule |
| `expect_count` | `<n> <substring>` — the substring must appear exactly n times |

Without `expect_error`, every `print()` is compared against the oracle and every
measurement outcome is checked for possibility and correct collapse.

Four things worth knowing when designing a case:

- **A behavioural test only distinguishes two matrices where its input state has nonzero
  amplitude.** A wrong controlled-Z survived four dedicated CZ tests for exactly this
  reason. Give gate tests inputs with every amplitude distinct and nonzero, and lean on
  `tools/check_gate_data.py` for the matrices themselves.
- **Ask what invariant every test happens to satisfy.** The measurement routine computed
  `P(0) = 1 - P(1)`, which is right only for a normalised register — and every test used
  one, so a fair coin that always landed the same way went unnoticed through the oracle,
  the possibility check and the collapse check alike. The generalisation of the previous
  bullet: a test suite is blind wherever it never places mass where a plausible wrong
  implementation would differ.
- **Statistical tolerances should be about 3.3 standard errors of the binomial**, and the
  trial count is bounded by the 4096-byte arena wherever a trial redeclares its register.
- **A program that sets a nonzero `noise` rate cannot be compared against the oracle**,
  since the trajectory depends on the assembly's own PRNG draws. Those tests must carry
  `expect_freq` or `expect_count`; the harness rejects a noisy program that carries
  neither, rather than silently passing it.

## Things deliberately not done

- **Porting off RARS.** The `ecall`s (`li a7,4/8/11/2`) are simulator-specific, not a real
  hardware or Linux ABI. Running on QEMU or hardware means rewriting all I/O, which is a
  different project.
- **Multi-character variable names, dynamic memory, float64.** Every one of these is a
  fixed-size region you can see in the source, and keeping them visible is the point.
- **A general expression language.** Conditions compare a classical variable or a literal
  against another. There is no arithmetic, and adding it would mean a real parser.
