# Defect log

Every defect the verification has found, by class, with what now guards against it. The
[paper](../paper/quasm.tex) argues why each was invisible to the tests of its time; this is
the list. Counts in the paper and in [paper/CLAIMS.md](../paper/CLAIMS.md) are by class, not
by instance.

## The first three

Found by the static audit and the property suite. All three passed the behavioural suite
that shipped them.

- **Controlled-Z was `diag(1,1,-1,-1)`**, i.e. `Z⊗I`: unitary, so nothing looked wrong, and
  it survived four dedicated CZ tests, because none of their inputs put weight where `CZ`
  and `Z⊗I` differ. `tools/check_gate_data.py` now checks every matrix is the gate it claims
  to be.
- **`SN` (sqrt X) carried a 0.707 normalisation** and was not unitary at all. Caught by the
  same audit.
- **Single-qubit measurement computed `P(0) = 1 - P(1)`** instead of summing it, which is
  right only for a normalised register, and the language allows unnormalised ones. On
  `qubit a = [(2,0),(2,0)]`, a fair coin, `P(1)` came out as 4, so 200 of 200 trials
  returned `|1>`; the whole-register form degraded differently on the same state (85/115).
  The oracle agreed (it derives the same collapsed state, the only value compared) and the
  possibility check passed (the oracle gave the outcome probability 4, not 0). Only a
  frequency check on an unnormalised register catches it. Regressions: `norm_unnorm_fair`,
  `norm_unnorm_biased`, `norm_unnorm_register`; `properties.py --self-test` reinstates it and
  the `born` property catches it.

Smaller, same period: the name check `'A' <= c <= 'z'` also admitted ASCII 91-96, so
`measure q[0] -> ]` bound a variable called `]`. Now `is_name_char` in `utils.s`.

## The mutation tooling, first version

Two bugs in `tools/mutate.py` that would have silently corrupted the numbers: `_fmt_float`
truncated by character count, so a denormal `1.4e-45` was written into the assembly as
`1.4012984643`; and `if limit:` / `if per_gate:` treated a legitimate 0 as "no limit". The
round-trip check (rewriting the unmutated constants must still pass the audit, with zero
drift) is what catches this class.

## Hardening round

A hostile-input probe and then the grammar-based fuzzer (`tools/fuzz.py`) found seventeen
interpreter defects, seven in the oracle, four in the test harness and two in the mutation
tool, none reached by the 158 hand-written tests of the time. All are fixed, with one
regression test per defect class in `tests/programs/`. Run against the unfixed code
(`fuzz.py --grammar v1 --root`), the fuzzer re-finds 13 of the 17 interpreter classes; it
misses zero-norm and tiny registers, the doubled `else` and the loop overflow inside an `if`,
regions its generator gives no weight.

### Interpreter (all silent wrong behaviour, none crashed)

- Integers wrapped mod 2^32 with no error: `q[4294967297]` was qubit 1, `repeat
  4294967296` ran 0 times, `set c = 99999999999` stored 1215752191. Now `Number out of
  range` (`parse_uint` checks with `mulhu` and a carry test).
- `parse_float` accumulated every fractional digit into an int32: `0.6000...0001`
  read as 2.4285715, a 42-digit integer as 0. Rewritten: 9 significant digits as an integer
  and a power of ten, exponents accepted, magnitude must be 0 or in [1e-18, 1e18). For up
  to 9 digits the arithmetic is unchanged, so every old literal reads to the same float.
- Measuring an all-zero register: the single-qubit form gave NaN and reported `|1>`, the
  whole-register form silently collapsed to `|00>`, the two forms disagreeing as in the Born
  rule defect above. Now `Cannot measure a register with zero norm`.
- The measurement guard was an absolute 1e-9, so `[(0.00001,0),(0,0)]` reported the
  *impossible* outcome `|1>` and a register of NaN. Now relative to the total weight.
- Tabs were syntax errors; indentation was a syntax error; `q[ 0 ]` was a syntax error
  (the docs said bracket whitespace was optional); `X#comment` broke the gate token. Now
  `next_line` normalises every line: tabs to spaces, comment cut, leading spaces dropped.
- Lines over 99 bytes were silently cut: `qubitop1 q[0] = X    ...Y` ran as `X`. The buffer
  is now 1024 bytes and an overlong line is `Line too long`.
- Block structure: a second `else` / an `else if` after `else` was accepted; closers of the
  wrong kind were accepted (`if / repeat / else`); malformed block lines inside skipped
  text were never checked; `end` inside an open block silently ignored the missing closer;
  `end junk` was accepted; a loop-store overflow inside an `if` swallowed the rest of the
  program. Replaced by one block stack (`blk_kind`/`blk_else` bitmasks in `script.s`) that
  tracks running *and* skipped blocks, plus a drain mode (skip kind 3) after an inner `end`.
- `else if` conditions were evaluated after a branch had run (reporting errors for
  branches that cannot run); now lazy, like the oracle.
- `qubit ![1]` accepted punctuation as a register name; now `[A-Za-z0-9_]`.
- Errors now print `Line N:`; replayed loop lines keep their original line numbers (two
  bytes stored before each line in `prog_store`).

### Oracle and harness

- `reference_sim.py` crashed (not `DslError`) on `if` with no condition, on malformed
  numbers (`float('1.2.3')`), and on a zero-norm measurement; accepted garbage between
  amplitude pairs, `endrepeat junk`, and a doubled `else`; and its runaway guard counted
  statements only, so `repeat 4294967295` around an empty body spun for hours (the fuzzer
  hung on it).
- `run_tests.py` never checked that the oracle agreed an `expect_error` program was an
  error, and passed a program that printed a stray error if its values still matched. Both
  are now checked. Outcome possibility is now judged on the normalised probability (raw
  weights falsely flag small unnormalised registers). A relative tolerance (1e-6) joins the
  1e-4 absolute one: float32 holds a legal 1e11 amplitude only to +/-4096.
- Metadata lines are sent as blank lines, not dropped, so `Line N:` matches the file.

### Mutation tool (these changed reported numbers)

- **`mutate.py` ran every code mutant against only the first 25 programs in file order**,
  which excluded the whole measurement section of the corpus. An earlier write-up's "the
  suite kills 25 of 30, and every survivor lies in measure.s" came from that, and is
  retracted. Against the full corpus the kernel and measurement mutants score 146/150.
- Code mutants also skipped every error test, which is exactly where a mutant that makes
  the interpreter accept bad input is caught.

Not a correctness defect, but fixed in the same pass: wide-margin constant kills were sent
to RARS for confirmation whenever a statistical program also used the gate, which cost
hours and decided nothing.
