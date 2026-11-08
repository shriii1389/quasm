# Claims ledger

One row per claim the paper makes. Each names the evidence that supports it, whether that
evidence exists *now*, and the scope the claim is limited to. **A claim with no evidence
gets weakened in the text until its evidence lands** — not deferred, not left standing.

Status values:

- **OK** — evidence exists and has been re-run; the sentence in the paper matches it.
- **WEAKENED** — the paper has been softened to what is currently provable.
- **RETRACTED** — the earlier claim was wrong; the paper now says so and states what is true.
- **PENDING** — evidence is being produced; the paper does not yet assert this.
- **BLOCKED** — cannot be established here; needs an action outside this repo.

Last full re-verification: 2026-09-28, after the hardening round (docs/DEFECTS.md).

---

## A. The artifact

| # | Claim | Where | Evidence | Status | Scope limit |
|---|---|---|---|---|---|
| A1 | Interpreter is entirely hand-written RISC-V assembly, nothing generated or linked | abstract; intro | The 14 `.s` files; no build step, no linker script | OK | "No library underneath" means no *external* library. RARS supplies the `ecall` I/O layer, which the paper states. |
| A2 | "roughly 3,600 lines (3,050 excluding blanks and comments), across fourteen files" | intro | 3,568 lines in the `.s` files; 3,053 non-blank, non-comment | OK | Assembly only, not the Python in `tools/`. |
| A3 | Registers of 1-6 qubits; universal gate set incl. S-dagger and T-dagger; CP family sufficient for QFT | abstract; Sec. 3 | `MAX_QUBITS = 6`; {H, T, CNOT} universal; QFT and Toffoli tests pass | OK | Universality is in-principle expressibility, not a compilation result. |
| A4 | Measurement-conditioned real-time control flow | Sec. 3 | `cond_*.dsl`, `algo_teleport.dsl` | OK | Has the *shape* of feed-forward with none of the timing semantics. |
| A5 | Every input limit is enforced, never wrapped or truncated: 32-bit integers, decimals in [1e-18, 1e18), 1022-byte lines | Sec. 3/4 | `err_num_*`, `err_amp_range_*`, `err_line_too_long`, `line_max_length`; the fuzzer | OK | Resource limits (arena, loop store, variable table) are the assembly's own; the oracle does not model them. |

## B. Verification results

| # | Claim | Where | Evidence | Status | Scope limit |
|---|---|---|---|---|---|
| B1 | All 230 test programs pass under both RARS and the oracle | Sec. 7 | `run_tests.py -j 4`: 225/225 on 2026-09-28, plus the 5 targeted tests added after the code-mutant run (5/5) | OK | 230 is the corpus size, not a coverage claim. |
| B2 | All 20 gate matrices pass the static audit | Sec. 5, 7 | `check_gate_data.py`: 20/20 | OK | Audits the declared `.float` data, not the kernel. |
| B3 | 85 error paths, each rejected by the oracle too | Sec. 7 | 85 `expect_error` programs; `run_tests.py` requires the oracle to raise, except for the three resource-limit messages | OK | Resource-limit errors are checked against RARS only. |
| B4 | The suite is **gated in CI** | removed | `.github/workflows/tests.yml` exists but has never run — no remote | **WEAKENED** — not in the paper | Restore only once CI has actually gone green. |
| B5 | The oracle is independent: different algorithms, not a transcription | Sec. 5 | Tensor contraction and a parsed block tree, vs. bit-index loops and line replay | OK | Same author. Qiskit (B7) is the only externally authored check. |
| B6 | Replay checks fire in both directions | Sec. 5 | Wrong-amplitude and impossible-outcome injections | OK | A manual confirmation. |
| B7 | External cross-validation against Qiskit | Sec. 5, Table | `cross_validate.py` vs Qiskit 1.3.1: seed 1, 5,000 circuits, 1-5 qubits, worst 8.0e-16; seed 0, 500 circuits, 4.97e-16; seed 0, 200 circuits through RARS, worst 1.53e-07. Zero disagreements. Every register declared with explicit random amplitudes, all distinct and nonzero | OK | The mapping layer is ours; the paper says so. |
| B8 | Metamorphic and property-based invariants | Sec. 5 | `properties.py`: 8 properties, 1,500 oracle cases and 300 RARS cases, 0 failures; `--self-test`: each of the 8 fails when its invariant is broken | OK | Over the generated distribution only. `qft` is blind to a uniformly conjugated phase family, and says so. |
| B9 | Differential fuzzing finds no disagreement on the fixed code | Sec. 5, 7 | `fuzz.py`: 2,900 programs (seeds 1-3), both modes. The two disagreements it raised on the way were in the *harness* (unreplayed outcomes; absolute-only tolerance) and were fixed there | OK | Covers the grammar as the generator weights it; see B10 for what it does not reach. |
| B10 | The fuzzer, written from the grammar, re-finds most hand-found defect classes on the unfixed code | Sec. 7 | `fuzz.py --grammar v1 --root` on the pre-fix tree: 2,600 programs, 133 disagreements, covering 13 of 17 interpreter defect classes plus an oracle crash; it also hung on the oracle's runaway gap | OK | Missed: zero-norm and tiny registers, the doubled `else`, loop overflow inside an `if` — regions the generator gives no weight. The classification is by hand and reported as such. |

## C. The defects — the paper's central argument

| # | Claim | Where | Evidence | Status | Scope limit |
|---|---|---|---|---|---|
| C1 | Controlled-Z shipped as diag(1,1,-1,-1), i.e. Z tensor I; unitary but wrong; survived four dedicated tests | Sec. 6 | Recorded at the time in the commit history | OK, as history | The history is not in this tree; the paper reports it rather than offering it for re-running. |
| C2 | sqrt(X) carried a 0.707 normalisation, not unitary | Sec. 6 | As C1; `check_gate_data.py` catches the reinstated value | OK | |
| C3 | Single-qubit measure computed P(0) as 1 - P(1); deterministic on an unnormalised register | Sec. 6 | Regression tests; `properties.py --self-test` reinstates it and `born` catches it | OK | |
| C4 | All three original layers missed C3 | Sec. 6 | As before | OK | |
| C5 | "structurally could not" | — | — | **RETRACTED** (2026-09-07) | Never restore. |
| C6 | Constant mutation scores | Sec. 7, Table | `mutate.py --full --all-code` on the 225-program corpus: 702 constant mutants, 628 meaningful, **628/628** killed behaviourally, 628/628 by the audit; 74 ULP nudges sit below tolerance by construction | OK | These operators, this corpus. |
| C7 | The 40-program suite that shipped C1 and C2 passed green with both present | Sec. 6, 7 | Run at the time via `mutate.py --historical-suite` (40/40) | **WEAKENED** to reported history | The revision it checks out is not in this tree, so it cannot be re-run here. |
| C8 | The mechanism: a test distinguishes two matrices only where its inputs place weight where they differ | Sec. 6, 7 | Controlled (`--zero-init-rewrite`): the same programs with every register started in the all-zeros state: 628 to **476**/628. Dropping the programs that declare other states instead (`--zero-init-only`): to **382**/628. Audit 628/628 in every condition. On the original 158-program corpus (`--corpus`, the 18 original gates): full 594/594, rewrite **426**/594, drop **302**/594 (the earlier paper reported 300/594 as halving) — 168 of the 292 lost kills are attributable to the inputs | OK | Only the starting states change in the rewrite arm, so that drop is attributable to inputs alone. The drop arm conflates inputs with which programs run, and the paper no longer presents it alone. |
| C9 | "Code mutants: the suite kills 25/30, all 5 survivors in measure.s" | — | Measured with a harness that ran each mutant against only the first 25 programs in file order, excluding every measurement test | **RETRACTED** | Replaced by C11. |
| C10 | A second round of defects — 17 in the interpreter, 7 in the oracle, 4 in the harness, 2 in the mutation tool — none reached by the 158 hand-written tests | Sec. 6 | `docs/DEFECTS.md`; one regression test per defect class in `tests/programs/` | OK | Counted by class, not by instance. |
| C11 | Code mutants: all 150 in the kernel and the measurement routine, against the full corpus including error tests | Sec. 7 | `mutate.py --full --all-code` on the 225-program corpus: **146/150**; the 4 survivors are all in measure.s (3 target-parsing, 1 whole-register sampling branch right only for two equally likely outcomes); 5 targeted tests then kill all 4 (`--match`): **150/150** | OK | Three operators; the rate carries an interval; where the survivors sit is the finding. |

## D. Evaluation numbers

| # | Claim | Where | Evidence | Status | Scope limit |
|---|---|---|---|---|---|
| D1 | 3-qubit QFT of the basis state 001 matches analytic values to about 5e-8 | Table | QFT tests | OK | One input on three qubits, plus 4 qubits via the oracle, plus QFT^4 = I as a property. |
| D2 | float32 error under repeated H^2 settles 1 ULP below and stays | Table | Measured series; the kernel is unchanged since | OK | This map at this value. |
| D3 | Depolarising fidelity decay matches the predicted curve | Table | 300 trials per point; the noise path is unchanged since | OK | Wide error bars. |
| D4 | Instruction cost is exactly linear in 2^n: 24.5 * 2^n + 645 (1-qubit), 103.25 * 2^n + 923 (2-qubit) | Table | `measure_cost.py`, 2026-09-28, through the RARS server; the server's step cap was checked against the CLI's to the exact instruction (17,910 on a probe program) | OK | Kernel coefficients unchanged from the earlier version; the constants grew from 349 and 524 with the new input handling, and the paper says so. |
| D5 | Parsing overhead exceeds the kernel up to n=4 (1-qubit) / n=3 (2-qubit); 29% of a 1-qubit gate at n=6 | Sec. 7 | From D4 | OK | Follows from D4. |

## E. Framing and positioning

| # | Claim | Where | Evidence | Status | Scope limit |
|---|---|---|---|---|---|
| E1 | QuAsm is not a fast simulator, not a quantum ISA, not control hardware | Sec. 8 | Argued directly | OK | Do not dilute. |
| E2 | Shares nothing with the RISC-Q of Liu et al. but an adjacency of subject matter | Sec. 2 | Read of that paper | OK | |
| E3 | Positioned against prior work in differential, metamorphic and mutation testing | Sec. 2 | 38 entries. The earlier sentence claiming quantum SE testing ignores the platform layer was false and is gone: QDiff, MorphQ and Paltenghi and Pradel are cited as platform-level testing, and the measured mechanism is named as PIE's infection condition | OK | Quito, QMutPy, Bugs4Q and test-set diversity are still uncited; a venue submission should add them. |
| E4 | "Coverage does not answer where the tests place their mass" | Sec. 6 | Inozemtseva and Holmes; our own measurement | OK | |
| E5 | Availability URL resolves | Sec. 9 | `https://github.com/shriii1389/quasm` | **OK once pushed** | For a double-anonymous submission, replace with an anonymised artifact link. |
| E6 | Named tools and languages carry citations | Sec. 2 | `quasm.bib`, 38 entries, clean build | OK | |
| E7 | The JCSC citation is complete | — | Never verified | **RETRACTED** | The citation and the sentence it supported are removed. |

---

## Standing rules

1. **No claim outruns its evidence.**
2. **Every scoped claim states its scope in the paper**, not only here.
3. **Self-authored evidence is labelled as such.** Qiskit is the only external check.
4. **A measurement tool's defect is a finding, not an embarrassment.** C9 is retracted in
   the paper, in so many words.
5. **Do not submit while any row is BLOCKED or PENDING.**
