# The paper

`quasm.tex` is the write-up: the artifact, the six verification layers, the defects they
found and why the tests of the time missed them, and the mutation measurements that test
that explanation. `quasm.pdf` is the built copy. `CLAIMS.md` is the claims ledger: every
claim the paper makes, the evidence for it, and the scope it is limited to.

## Building

Any TeX distribution with `pdflatex` and `bibtex` (TeX Live, MiKTeX, MacTeX):

```sh
pdflatex quasm.tex
bibtex quasm
pdflatex quasm.tex
pdflatex quasm.tex      # resolves the remaining cross-references
```

`quasm.bbl` is checked in, so without `bibtex` two `pdflatex` passes are enough as long as
`quasm.bib` has not changed.

## Reproducing the numbers

Every figure in the evaluation section comes from a script in `../tools/`:

| Claim | How to reproduce |
|-------|------------------|
| 230/230 tests pass, 20/20 matrices audited | `python ../tools/run_tests.py -j 4` (a minute or two) |
| Agreement with Qiskit | `python ../tools/cross_validate.py --seed 1 --n 5000 --max-qubits 5`; through RARS, `--seed 0 --n 200 --rars` |
| Metamorphic properties | `python ../tools/properties.py --n 200`; against RARS, `--engine rars --n 40` |
| Fuzzing, fixed code | `python ../tools/fuzz.py --n 300 -j 4`, seeds 1-3 |
| Mutation scores | `python ../tools/mutate.py --full --all-code`, then `--code-mutants 0 --zero-init-rewrite` and `--zero-init-only` (hours) |
| QFT of \|001⟩ | `python ../tools/quasm.py ../examples/qft.dsl` |
| Float32 fixed point | apply `H` in pairs and print; see below |
| Fidelity decay | `python ../tools/quasm.py ../examples/noise_decay.dsl` |
| Instruction cost | `python ../tools/measure_cost.py` (minutes, through the RARS server) |

The drift measurement is a one-liner per row — vary the repeat count:

```sh
printf 'qubit a[1]\nqubitop1 a[0] = H\nrepeat 500\nqubitop1 a[0] = H\nqubitop1 a[0] = H\nendrepeat\nprint(a)\nend\n' \
  | java -jar ../tools/rars1_6.jar nc sm ../main.s
```

`measure_cost.py` is slow because RARS only reports an instruction count when it stops at a
step limit rather than through the exit syscall, so each measurement is a binary search on
that limit.
