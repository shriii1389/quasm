# The QuAsm language

A QuAsm program is a sequence of statements, one per line, ending with `end`. There are
no expressions, no functions and no types beyond "qubit register" and "classical integer".
The interpreter reads a line, runs it, and reads the next — whether the lines arrive from
a file, a pipe, or someone typing at the `>> ` prompt.

```sh
python tools/quasm.py examples/bell.dsl
java -jar tools/rars1_6.jar nc sm main.s < examples/bell.dsl
```

## Conventions that apply everywhere

- **Variable names are a single character.** A qubit register is named by a letter, a digit
  or `_`; a classical variable by a letter. `alpha` is not a name — it is a syntax error.
- **Qubit registers and classical variables are separate namespaces.** `q` as a register
  and `q` as a classical variable are unrelated.
- **A line must fit in 1022 bytes.** A longer one is rejected with `Line too long`, never
  quietly cut short — the input buffer is 1024 bytes and the line needs room for its
  newline.
- `#` starts a comment that runs to the end of the line, anywhere, even straight after a
  keyword. Blank lines are ignored.
- Lines may be indented. A tab counts as a space everywhere, and whitespace around
  operators, brackets and commas is optional — `q[ 0 ]` is `q[0]`.

### Numbers

- **Integers** — register sizes, qubit indices, loop counts, seeds, and the values of
  classical variables — are decimal and must fit in 32 bits: 0 to 4294967295. A larger one
  is `Number out of range`, never wrapped around.
- **Decimals** — amplitudes and noise rates — are an optional `-`, digits with an optional
  point, and an optional exponent: `0.5`, `.5`, `5.`, `-0.25`, `6e-1`, `2.5E+2`. Anything
  but zero must have a magnitude from `1e-18` up to (not including) `1e18`, so that the
  squared amplitudes of a full register can neither overflow nor underflow float32 when
  they are summed; outside that is `Number out of range`. Any number of digits may be
  written, but only the first nine significant ones are kept — already more than float32
  holds — so `0.7071067811865476` is read as the float32 nearest `1/√2`.

## Qubit registers

```
qubit <v>[<n>]                       n-qubit register initialised to |0...0>
qubit <v> = [(re,im),(re,im),...]    explicit amplitudes
```

`n` runs from 1 to 6. A register of n qubits is `2^n` complex amplitudes stored
contiguously, in basis order `|q0 q1 ... qn-1>` — so **qubit 0 is the most significant bit
of an amplitude index**. In a 3-qubit register, amplitude 5 is `|101>`, meaning qubit 0
reads 1, qubit 1 reads 0, qubit 2 reads 1.

> **If you are comparing output against Qiskit, note the convention is the opposite.**
> QuAsm follows Nielsen & Chuang: qubit 0 is the most significant bit. Qiskit is
> little-endian — its qubit 0 is the *least* significant bit, and it prints bitstrings
> reversed relative to these. The states are the same; the labels are mirrored. Reverse
> the qubit indices when porting a circuit either way.

The explicit form takes any power-of-two count of `(real, imaginary)` pairs and declares a
register of the matching size. The amplitudes are stored exactly as given — nothing is
normalised for you, and `print` will show you back what you wrote. Measurement, however,
is always **proportional to the weights actually present**: both branch probabilities are
summed and the draw is scaled by their total, so `[(2,0),(2,0)]` is a fair coin just as
`[(0.70710678,0),(0.70710678,0)]` is. Collapse then renormalises the survivors, so a
register is normalised from its first measurement onwards.

```
qubit q[3]                           |000>
qubit a = [(0.70710678,0),(0,0.70710678)]
qubit b = [(0.8660254,0),(0.5,0)]    p(1) = 0.25
```

Redeclaring a name rebinds it. If the new register fits in the block the name already has,
that block is reused, so a loop can redeclare a register on every iteration forever. A name
that grows takes fresh space and leaks its old block — see [ARCHITECTURE.md](ARCHITECTURE.md).

## Gates

```
qubitop1 <v>[<k>] = <gate>           gate in H I X Y Z S T SN SDG TDG
qubitop2 <v>[<c>],<v>[<t>] = <gate>  gate in CN SW CY CZ CP1..CP6
```

Gates act in place on the named register. `k`, `c` and `t` are qubit indices into it, and
`c` and `t` must be distinct qubits of the *same* register.

| Gate | Meaning |
|------|---------|
| `H`  | Hadamard |
| `I`  | identity |
| `X` `Y` `Z` | Pauli gates |
| `S`  | phase, `diag(1, i)` |
| `T`  | `diag(1, e^{iπ/4})`; `T·T = S` |
| `SN` | sqrt(NOT), the principal square root of `X`; `SN·SN = X` |
| `SDG` `TDG` | the inverses S† = `diag(1, -i)` and T† = `diag(1, e^{-iπ/4})` |
| `CN` | controlled-NOT |
| `SW` | swap |
| `CY` `CZ` | controlled-Y, controlled-Z |
| `CP1`..`CP6` | controlled phase, `diag(1, 1, 1, e^{2πi/2^k})` |

`{H, T, CN}` is universal for quantum computation, so any unitary can in principle be
approximated by a program in this language. `SDG` and `TDG` add nothing to that, but they
make the standard Clifford+T circuits writable as published — the 15-gate Toffoli, for
one, which `tests/programs/toffoli_truth_table.dsl` checks on every basis state. The `CP` family is what makes that practical
for the one algorithm most worth demonstrating: `CP1` is `CZ`, `CP2` is controlled-`S`,
`CP3` is controlled-`T`, and `k` up to 6 is as fine a rotation as a 6-qubit register can
use. The quantum Fourier transform needs exactly these.

```
qubit q[3]                           the 3-qubit QFT
qubitop1 q[0] = H
qubitop2 q[1],q[0] = CP2
qubitop2 q[2],q[0] = CP3
qubitop1 q[1] = H
qubitop2 q[2],q[1] = CP2
qubitop1 q[2] = H
qubitop2 q[0],q[2] = SW              undo the bit reversal
```

The two-qubit matrices are written in the `|control target>` basis, so which of the two
qubits sits earlier in the register is your choice, not the matrix's:
`qubitop2 q[1],q[0] = CN` is a genuinely different operation from `qubitop2 q[0],q[1] = CN`.

```
qubit q[2]
qubitop1 q[0] = H
qubitop2 q[0],q[1] = CN              a Bell pair
```

## Measurement

```
measure <v>[<k>]                     collapse one qubit, print |0> or |1>
measure <v>                          collapse the register, print |q0q1...qn-1>
measure <v>[<k>] -> <c>              ...and keep the outcome in c
measure <v> -> <c>
seed <n>                             reseed the PRNG; n must be nonzero
```

`measure <v>[<k>]` computes `P(1)` as the total weight of the amplitudes whose bit k is
set, draws a uniform sample, takes outcome 1 when the sample falls below `P(1)`, zeroes the
amplitudes of the branch that did not happen, and renormalises the survivors. The register
stays in superposition over everything the outcome did not determine.

`measure <v>` samples one basis state from the full distribution and collapses the whole
register onto it.

The optional `-> <c>` tail additionally stores the outcome as an integer in a classical
variable: 0 or 1 for a single qubit, the basis index for a whole register. That is what
makes a measurement result available to `if`.

A register whose amplitudes are all zero has no outcome to measure, and measuring it is
the error `Cannot measure a register with zero norm` — the register is left as it was and
no variable is set. Any other register measures in proportion to its own weights, however
small they are: an outcome is only ever ruled out as float32 rounding when its share of the
register's *total* weight is below 1e-9, so `[(0.00001,0),(0,0)]` measures `|0>`, as it
should.

Measurement is **reproducible by default** — the PRNG starts from a fixed nonzero seed, so
the same program yields the same outcomes every run. `seed <n>` picks a different stream.
A seed of 0 is rejected: xorshift32 maps 0 to itself, which would freeze every subsequent
measurement on one outcome.

```
qubit q[2]
qubitop1 q[0] = H
qubitop2 q[0],q[1] = CN
measure q[0] -> c                    prints |0> or |1>
print(q)                             the other qubit is now determined too
```

## Noise

```
noise <p>                            depolarising rate per qubit per gate
```

By default QuAsm simulates a perfect machine. `noise <p>` turns on a depolarising channel:
after every gate, each qubit that gate touched has probability `p` of being hit by one of
`X`, `Y`, `Z`, chosen uniformly. `noise 0` turns it off again, and `p` outside `[0,1]` is
an error.

This is the **quantum-trajectory** form of the channel. A single run is one trajectory —
one particular sequence of errors — which is also what real hardware hands you. The
depolarising map itself is what the ensemble over many runs converges to, so noisy programs
are things you run many times and count, not things you print once.

Two consequences worth knowing, both of which the test suite pins down:

- A qubit in `|0>` reads `1` after one noisy gate with probability `2p/3`, not `p` — `X`
  and `Y` flip it, `Z` does not.
- Over `N` gates the Bloch `z` component shrinks by `(1 - 4p/3)` each time, so
  `P(|0>) = (1 + (1-4p/3)^N)/2` — the fidelity decay curve.

```
noise 0.1
repeat 300
qubit q[1]
repeat 10
qubitop1 q[0] = I
endrepeat
measure q[0]                         reads 0 about 62% of the time
endrepeat
```

## Classical variables

```
set <c> = <n>                        an integer; n may name another variable
```

Classical variables hold unsigned integers. They exist to carry measurement outcomes into
`if`, and `set` exists so a program can also count, flag and compare without measuring.
There is no arithmetic — a value comes from a literal, another variable, or a measurement.

## Conditionals

```
if <x> <op> <y>
...
else if <x> <op> <y>
...
else
...
endif
```

`<op>` is one of `==` `!=` `<` `<=` `>` `>=`, and each side is either a decimal literal or
the name of a classical variable. Comparisons are unsigned. Any number of `else if`
branches may follow the `if`; `else` is optional but, if present, comes last — anything
after it but `endif` is `else after else`; `endif` is required. The first branch whose
condition holds runs, and the rest are skipped. Conditionals nest up to 8 deep.

A branch that is not taken is still *read* — the interpreter has no way to seek ahead in a
pipe — but nothing in it runs. What is checked, and when:

- **Block structure is checked everywhere**, run or not: every `repeat`, `if`, `else`,
  `endif` and `endrepeat` must be well formed and must match, and the nesting limits apply.
  An `else` or `endif` belongs to the innermost open block, so it cannot close an `if`
  while a loop inside it is still open.
- **Statements and conditions are checked when they run.** A condition that is never
  evaluated — an `else if` after a branch has already run — is never checked, so
  `else if z == 1` with no `z` is fine there. A condition that fails when it *is* evaluated
  is reported, and no branch of that `if` runs.

```
qubit q[2]
qubitop1 q[0] = H
qubitop2 q[0],q[1] = CN
measure q[0] -> c
if c == 1                            undo the flip, whichever way it landed
qubitop1 q[0] = X
qubitop1 q[1] = X
endif
print(q)                             always |00>
```

## Loops

```
repeat <n>
...
endrepeat
```

Runs the body `n` times; loops nest up to 8 deep. `repeat 0` reads the body and runs none
of it. A loop body is held in a 2048-byte store while the loop is open — each line costs
its length after comments are stripped, plus 3 bytes — so a body longer than that is
rejected with `Loop body too long`. The loop that overflowed, and any loops it is inside,
are abandoned; any `if` around them carries on.

**An error inside a loop breaks out of it.** The iteration in progress finishes and the
loop stops, rather than reporting the same typo once per iteration.

```
seed 12345
qubit q[1]
repeat 20
qubitop1 q[0] = H                    H reprepares a fair coin from either outcome
measure q[0]
endrepeat
```

## Output and termination

```
print(<v>)                           every amplitude, as [(re,im),(re,im),...]
end                                  stop
```

`print` shows the whole register in basis-state order. Amplitudes are float32, so expect
`0.70710677` rather than `0.70710678`.

`end` stops the interpreter, and takes nothing after it. It may appear inside a block —
`if c == 1` / `end` / `endif` stops a program early — and then nothing more runs, but the
rest of the text is still read up to the top-level `end`, so that a block the program never
closes is still reported. The top-level `end` is where the program ends; nothing after it
is read.

A program that never says `end` will stop anyway after 32 consecutive blank lines,
reporting `Unexpected end of input` — the simulator gives the interpreter no way to
distinguish a blank line from a closed pipe, so that run of blanks is the only end-of-input
signal available. `tools/quasm.py` appends `end` for you if a script does not have one.

## Errors

An error prints the line it is on and a message, and the interpreter carries on with the
next statement:

```
Line 12: Qubit index out of range
```

A line inside a loop reports its own line number on every pass, not the loop's.

| Message | Cause |
|---------|-------|
| `Syntax Error` | the statement did not parse |
| `Variable not declared` | no such qubit register, or no such classical variable |
| `Qubit index out of range` | index ≥ the register's qubit count |
| `Register size out of range (1 to 6 qubits)` | `qubit v[n]` with n outside 1..6 |
| `Out of qubit storage` | the 4096-byte amplitude arena is full |
| `Amplitude count must be a power of two` | explicit declaration with a bad count |
| `Two-qubit gate needs two distinct qubits` | `qubitop2 q[0],q[0]` |
| `Two-qubit gate operands must be one register` | `qubitop2 a[0],b[0]` |
| `Seed must be nonzero` | `seed 0` |
| `Loop body too long` | a loop body over 2048 bytes |
| `Loops nested more than 8 deep` | a 9th open `repeat` |
| `endrepeat without repeat` | a loop tail with no loop open, or with an `if` still open inside it |
| `Conditionals nested more than 8 deep` | a 9th open `if` |
| `else or endif without if` | a conditional tail with no `if` open, or with a loop still open inside it |
| `else after else` | an `else` or `else if` after an `if`'s plain `else` |
| `Out of classical variable storage` | more than 31 classical variables |
| `Noise rate must be between 0 and 1` | `noise p` with p outside [0,1] |
| `Number out of range` | an integer past 4294967295, or a nonzero decimal outside [1e-18, 1e18) |
| `Cannot measure a register with zero norm` | every amplitude of the measured register is zero |
| `Line too long` | a line over 1022 bytes |
| `Unexpected end of input` | the input ran out before the top-level `end` |

## Limits, in one place

| | |
|---|---|
| qubits per register | 6 (64 amplitudes, 512 bytes) |
| amplitude arena | 4096 bytes — eight maximum-size registers |
| qubit registers | 63 possible names; 82 symbol-table entries |
| classical variables | 31 |
| loop nesting / conditional nesting | 8 each |
| loop body | 2048 bytes |
| line length | 1022 bytes |
| integers | 0 to 4294967295 |
| decimals | 0, or magnitude in [1e-18, 1e18); 9 significant digits kept |
| variable names | one character |
| amplitude precision | float32 |

These are deliberate: QuAsm is a pedagogical simulator with no dynamic memory, and every
limit above is a fixed-size `.data` region you can see and change in the source.
