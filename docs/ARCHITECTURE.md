# How QuAsm works

Everything below is hand-written RISC-V assembly: the parser, the statevector maths, the
symbol tables, the PRNG, the loop machinery. There is no library underneath, and the only
thing the host provides is I/O through RARS's `ecall` interface.

## The files

| File | What lives there |
|------|------------------|
| `main.s` | gate matrices, error strings, the arenas, and the statement dispatcher |
| `script.s` | where the next line comes from: stdin, or a replaying loop body |
| `cond.s` | classical variables, conditions, `if`/`else`/`endif` |
| `qubit.s` | `qubit` declarations and `parse_float` |
| `oneQubitGate.s`, `twoQubitGate.s` | the `qubitop1` / `qubitop2` parsers |
| `gateFunctions.s` | `apply_gate1` / `apply_gate2`, the statevector kernel |
| `measure.s` | the PRNG, `measure`, `seed` |
| `noise.s` | the depolarising channel and `noise` |
| `print.s` | `print()` |
| `store.s`, `search.s` | the register symbol table and the amplitude arena |
| `utils.s` | token matching, `skip_ws`, `at_eol`, `parse_uint` |
| `errors.s` | error code to message |

`main.s` pulls in every other file with `.include`, so the whole interpreter assembles as
one unit and every label is visible everywhere. That is why RARS must **not** be given its
project flag — it would assemble each file a second time.

## The main loop

```
input_loop:
    next_line          -> fills `buffer`, normalised: tabs to spaces, comment
                          cut off, leading spaces dropped; or reports a
                          line too long for the buffer
    at_eol?            -> blank line or pure comment: next
    skip_kind set?     -> skip_line, and next
    dispatch on the leading keyword
        handler returns a0 = 0, or an error code
    a0 != 0            -> report_error, then next
```

Every statement handler follows one contract: **it unwinds its own stack frame and returns
`a0 = 0` or an error code.** No handler jumps to the error printer from inside itself. The
original code did exactly that — `j syntaxError` from a routine that had already pushed a
frame, landing back in the input loop with the frame leaked — and the stack grew without
bound across a session.

`report_error` prints `Line N: ` and the message for the code, and returns to the loop.
It also calls `abort_loops`, so one bad statement inside `repeat 400` is reported once
rather than 400 times. The line number is `cur_line`, which `next_line` sets from a count
of stdin lines — or, for a replayed loop line, from the number stored with it.

## Memory

All of it is fixed-size `.data`. There is no allocator and no stack discipline beyond
ordinary frames.

```
symbol_table   1000 bytes   82 entries of (name char, base address, qubit count)
value_storage  4096 bytes   amplitude arena, bump-allocated
cvar_table      256 bytes   31 entries of (name char, value), classical variables
if_stack         32 bytes   8 frames: has a branch of this `if` run yet?
loop_stack       64 bytes   8 frames of (body address, iterations left)
blk_kind/else     2 words   one bit per open block: kind, and "has had its else"
prog_store     2048 bytes   the recorded lines of any open loop body
buffer         1024 bytes   the statement being parsed
```

`.space` does not pad, so any `.space` region that a `lw`/`sw` will touch needs an explicit
`.align 2` in front of it. RARS terminates the program silently on a misaligned word
access — no message, exit status 0 — which is a memorable afternoon if you forget.

### Registers

A register of n qubits is `2^n` consecutive complex amplitudes. Each amplitude is two
float32 words, real then imaginary, so amplitude *i* of a register based at `p` lives at
`p + 8i`. A 6-qubit register is 512 bytes, and the 4096-byte arena therefore holds eight of
them. That cap is what stops a single declaration from ever outgrowing the arena in one
step; `alloc_room` also checks the arena bound independently.

**Qubit 0 is the most significant bit of the amplitude index.** Basis order is
`|q0 q1 ... qn-1>`, so in a 3-qubit register index 5 = `0b101` = `|101>`. The bit for qubit
k is therefore `1 << (n - 1 - k)`, a line that appears in the gate kernel, in `measure`,
and in the oracle.

### Allocation

`alloc_var` binds a name to storage. If the name already exists and the new register fits
in the block it has, that block is reused — which is what lets a loop redeclare a register
on every iteration without eating the arena. Only a name that has *grown* takes fresh space
off the bump pointer, and its old block is then leaked. Bounded by program length, and it
surfaces as a clean `Out of qubit storage` rather than corruption.

`s11` holds the arena bump pointer for the life of the program. It is the only globally
live saved register, written in `main` and in `alloc_room` and nowhere else. Every other
routine that writes `s0`-`s10` saves and restores it.

## The gate kernel

Two routines in `gateFunctions.s`, both acting in place, both taking everything in
registers rather than through shared globals.

**`apply_gate1(a0 = state, a1 = n, a2 = target, a3 = 2x2 matrix)`** walks all `2^n`
amplitude indices. For each pair of indices differing only in the target bit, it loads the
two amplitudes, multiplies by the matrix, and writes both back:

```
for i in 0 .. 2^n - 1:
    if i has the target bit clear:
        j = i | bit
        (s[i], s[j]) = (m00*s[i] + m01*s[j], m10*s[i] + m11*s[j])
```

**`apply_gate2(a0 = state, a1 = n, a2 = control, a3 = target, a4 = 4x4 matrix)`** does the
same for the groups of four indices that differ in the control and target bits: gather the
four amplitudes into `g2_amp`, apply the matrix into `g2_tmp`, scatter back through the
four addresses saved in `g2_addr`.

Complex multiply-add is inlined throughout: `(a+bi)(c+di) = (ac - bd) + (ad + bc)i`.

The gate *name* is resolved to a matrix address by the parser (`la s4, Hgate`), not by an
integer index that a second chain of comparisons has to turn back into an address. That
indirection is where 12 of the original 16 two-qubit selectors ended up pointing into the
middle of a matrix.

An earlier design had one generic `quantum_gate` driven by `.data` globals — `qubitnum`,
`row1`, `col2`, `tensor`, `res`. Passing arguments in registers deleted a whole class of
bugs by construction: a qubit count that was never reset between statements, and a routine
that clobbered `s7`-`s11` without saving them, `s11` included.

## Measurement

`rand_u32` is xorshift32 (`x ^= x<<13; x ^= x>>17; x ^= x<<5`), state in `rng_state`,
seeded to a fixed nonzero constant so a session is reproducible by default.

`rand_unit` returns a uniform in `[0,1)` from the **top 24 bits** of that word. Two reasons
for the top bits: xorshift's low bits are its weak ones, and 24 is exactly float32's
mantissa width, so both the numerator and `2^24` are exact and every sample is
representable without rounding.

`measure v[k]` sums `|amp|²` over the indices with bit k set and over those with it clear,
giving both branch weights; it draws `r`, takes outcome 1 iff `r * total < P(1)`, zeroes
the other branch and scales the survivors by `1/sqrt(p)`. `measure v` totals all `2^n`
weights, scales `r` by that total, then walks the cumulative distribution and collapses
onto the chosen basis state.

**Why both branches are summed rather than one taken as `1 - the other`.** That shortcut
is correct only for a normalised register, and the language deliberately lets you declare
one that is not. With it, `qubit a = [(2,0),(2,0)]` gave `P(1) = 4`, so `r < P(1)` was
true for every `r` in `[0,1)` and the measurement was *deterministic* — a fair coin that
always landed on 1. The two measurement forms also disagreed with each other on the same
state, since the whole-register path degraded differently. Summing both weights and
scaling `r` by the total costs one extra add and one multiply, makes the two forms agree,
and makes an unnormalised register sample in proportion to the amplitudes it actually has.

This one is worth dwelling on because **the test suite could not have caught it**. The
oracle computes both sums correctly, so it and the assembly agreed on the *collapsed*
state; the possibility check passed because the oracle gave the reported outcome
probability 4, not 0; and no test happened to use an unnormalised register with an
`expect_freq` check. It is the same blind spot as the controlled-Z bug in a different
place: a defect invisible unless a test puts weight exactly where the two behaviours
differ. `norm_unnorm_fair`, `norm_unnorm_biased` and `norm_unnorm_register` now do.

Three more details worth keeping:

- Both sum the weights **before** drawing `r`, so that a register with no weight at all is
  refused — `Cannot measure a register with zero norm` — without consuming a random number
  or touching the register. `rand_unit` clobbers only `fa0` and `ft0`, so the sums survive
  the call; anything else float that must outlive it has to be recomputed. The number of
  draws per successful measurement is unchanged, so every seeded outcome is too.
- **Degenerate-branch guard.** If the selected branch's weight comes out below `1e-9` *of
  the register's total weight*, the other branch is taken instead. In exact math a branch
  selected by `r < P(1)` always has positive probability, but float32 rounding can leave
  `P(1)` at 0.99999994 and hand back an `r` just inside it — and then `1/sqrt(~1e-7)`
  detonates the register. The guard used to be an absolute `1e-9`, which was right only for
  a normalised register: `[(0.00001,0),(0,0)]` has total weight `1e-10`, so both of its
  branches fell under it, the guard swapped the real outcome for the impossible one, and the
  collapse divided by zero — `|1>` and a register of NaN. Scaling the guard by the total
  makes it the same test on every register.
- `meas_all` does the same thing differently: it skips zero-probability indices and
  remembers the last viable one in case rounding starves the cumulative sum before it
  passes `r`.

## Noise

`noise p` sets a depolarising rate, and `apply_noise` in `noise.s` runs after every gate on
each qubit that gate touched. With probability `p` it applies one of `X`, `Y`, `Z`, drawn
uniformly from the same xorshift32 stream the measurements use.

This is a **quantum trajectory**, not a density matrix. Simulating the channel properly
would mean tracking a `2^n x 2^n` mixed state, which at n = 6 is 4096 complex entries
against the statevector's 64 — the arena could hold one register instead of eight. Sampling
one trajectory per run keeps the whole simulator inside the statevector it already has, and
the channel is recovered by running the program many times and counting, which is what you
do with hardware anyway.

Two consequences fall out of the algebra and are pinned down by tests:

- A qubit flips with probability `2p/3`, not `p`: `X` and `Y` flip it, `Z` does not.
- Each noisy gate shrinks the Bloch `z` component by `(1 - 4p/3)`, so over `N` gates
  `P(|0>) = (1 + (1-4p/3)^N)/2`. `noise_fidelity_decay` checks this at N = 10, p = 0.1.

`apply_noise` costs one float compare when noise is off, and pushes no stack frame on that
path — a program that never says `noise` pays essentially nothing for the feature.

## Cost

RARS reports executed instruction counts, but only when it stops at a step limit rather
than through the exit syscall, so `tools/measure_cost.py` recovers the exact count for a
terminating program by binary search on that limit. The cost of a gate is the difference
between a program applying twenty of them and one applying none, divided by twenty, so the
prompt, the parser and the declaration all cancel.

The kernel is `Θ(2^n)` in the register size, as the loop structure says it should be, at
roughly 24.5 instructions per amplitude for a single-qubit gate. The interesting part is
the constant: **parsing a statement costs about 650 instructions regardless of `n`** (923
for a two-qubit gate, which parses two operands), so for small registers the interpreter,
not the physics, is the workload, and the two only cross over around n = 5. The constant
was about 350 before every line was normalised and every number overflow-checked. That is the honest shape of an interpreted simulator, and it is
the number to beat if anyone ever compiles this language instead of interpreting it.

## Lines, loops and branches

The interpreter is not file-aware. A script is piped into stdin exactly as an interactive
session is, and `next_line` is the single place that decides where the next statement comes
from.

### Recording and replay

A loop body has to be read twice, and stdin cannot be rewound. So lines are copied into
`prog_store` as they arrive — **but only while a loop is open**, and the store is reset the
moment the outermost loop closes. A straight-line program of any length never touches it,
while a loop body is always sitting in memory when it needs re-reading. Each line is stored
already normalised, after its two-byte line number, so a replayed line reports errors
against the line it came from.

`loop_stack` holds a `(body address, iterations left)` frame per open loop.

- `repeat n` pushes a frame whose body address is wherever the *next* line is going to come
  from: `prog_end` on the first pass, `replay_ptr` if this `repeat` is itself inside a
  replaying body. That one rule is what makes nesting work without a second mechanism.
- `endrepeat` decrements, and either points `replay_ptr` back at the top of the body or
  closes the loop.
- Reading resumes from stdin whenever `replay_ptr` reaches `prog_end` — which covers "the
  inner loop finished but the outer body is still streaming in".

If the store fills up mid-body, no open loop can ever replay correctly. `discard_loops`
abandons them all and skips to the end of the outermost one. That is always safe, because
recording only ever happens while reading stdin, so the rest of those bodies is still ahead
in the input and skipping forward lands exactly where the loops would have ended. The
`if`s *around* the outermost loop stay open and running; the ones inside it become part of
the skipped text. (An earlier version counted every open `if` into the skip, including the
ones around the loop, so an overflow inside an `if` swallowed the rest of the program.)

### The block stack

Every block open at the current point in the text — running or skipped — has one bit in
`blk_kind` (1 for an `if`, 0 for a `repeat`) and one in `blk_else` (has this `if` had its
plain `else`?), innermost at `blk_depth - 1`. `blk_loops` and `blk_ifs` count each kind for
the 8-deep limits, which are therefore limits on the *text*, whether or not it runs.

That stack is what checks structure: a closer must match the innermost open block's kind
(`endif` cannot close an `if` while a loop inside it is open), and a second `else` is
`else after else`. The runtime stacks, `loop_stack` and `if_stack`, only ever hold running
blocks, and a running block is always on the block stack too, so they cannot overflow.

### Skipping

Four things need lines read but not run: a `repeat 0` body, an untaken `if` branch, the
rest of the loops after a store overflow, and the rest of the program after an `end`
inside a block. One mechanism covers all four.

```
skip_kind   0 = running
            1 = skipping to the `endrepeat` of a `repeat 0`, or of abandoned loops
            2 = skipping to the next else / else if / endif of an `if`
            3 = draining to the top-level `end`, after an `end` inside a block
skip_base   blk_depth of the block the skip belongs to
```

While `skip_kind` is set, `main` hands each line to `skip_line` instead of dispatching it.
Block keywords push and pop the block stack exactly as they would running, and are held to
the same rules — a malformed `repeat` head, `endif junk`, a mismatched closer or a doubled
`else` inside skipped text is still an error. Only the closer at `skip_base` ends the skip.
Statements and conditions are not looked at: a syntax error in a statement that never runs
is not reported.

`end` inside a block stops execution but switches to kind 3 rather than exiting, and reads
on until the top-level `end`. That is what lets `if c == 1` / `end` / `endif` stop a program
early while a block the program never closes is still reported, exactly as a parser that
saw the whole text would report it. If the `end` ran during a replay, stdin is already past
the outermost loop's `endrepeat`, so the block stack is cut back to the blocks around that
loop first.

A skip can never start while one is already in progress, because a statement that would
start one is never executed while skipping. So a single `(kind, base)` pair is enough.

### Conditionals

`if_stack` holds one word per open `if`: whether some branch of it has run yet. That single
flag is all `else` needs.

- `if <cond>` pushes a frame with the condition's truth. If false, `skip_kind` becomes 2.
  If the condition cannot be evaluated, the error is reported and the frame is pushed as
  though a branch had run, so the whole `if` is skipped rather than its body run bare.
- `else` / `else if` reached while **running** means the branch above it ran to completion,
  so the rest of the conditional is skipped and this condition is never evaluated. Reached
  while **skipping, as the `if` being decided**, it is a candidate: if no branch has run and
  this condition holds, the flag is set and skipping stops; otherwise skipping continues.
- `endif` pops the frame and, if we were skipping for it, stops.

Because branches are decided line by line on the stream rather than by seeking, an `if`
inside a loop body is re-evaluated on every iteration for free — the recorded lines replay,
and the condition is read again with whatever the classical variables now hold.

`else if` is not a separate construct. It is an `else` whose tail happens to carry a
condition, which is why both the running path and `skip_line` call the same `else_tail` and
therefore agree on exactly what may follow the keyword.

### End of input

RARS's `ReadString` hands back `"\n"` both for an empty line and at end of input, so **EOF
is not detectable**. Syscall 12 is no better: it discards the rest of the line and kills the
program at EOF. Since blank lines had to become legal for scripts to be readable, the
ambiguity is unavoidable, so `eof_guard` treats 32 consecutive empty reads as end of input
and stops with `Unexpected end of input`. Not elegant, but it is the only signal the
simulator offers, and without it a program that forgets `end` spins forever.

## Parsing

There is no tokenizer. Each handler walks `buffer` with a cursor and a handful of shared
helpers in `utils.s`:

- `starts_with(t0 = input, t1 = pattern)` — prefix match. **The needle terminates first**;
  several call sites in the original code had the arguments the wrong way round.
- `token_eq` — same, but the input token must end exactly where the pattern does, so `S`
  no longer matches the start of `SN` and `end` no longer matches `endrepeat` or `endif`.
- `skip_ws`, `at_eol`, `parse_uint`, and `parse_float` in `qubit.s`.

`next_line` cuts every line at its `#`, which is the whole implementation of comments, and
turns tabs into spaces and drops leading spaces, so no handler ever sees any of the three.

Parsing rules worth stating because their absence used to be a bug:

- `parse_float` returns a **digit count**, and callers reject a number with no digits.
  `qubit a = [(,0),(1,0)]` used to parse the empty field as 0.0 and declare a valid
  register. It also stops at any character that cannot continue a number, so malformed
  input can never run it off the end of the buffer.
- `parse_float` keeps at most **nine significant digits** as an integer and a power of ten,
  and drops the rest. It used to accumulate every fractional digit into a 32-bit integer,
  so `0.60000000000000000000000001` overflowed and read as 2.4285715, and a long integer
  part read as 0. For up to nine digits the arithmetic is unchanged — one conversion and
  one divide by an exact power of ten — so every literal that was read correctly before
  reads to the same float now. A magnitude outside `[1e-18, 1e18)` is `Number out of
  range`.
- `parse_uint` reports **overflow** past `2^32 - 1` (`mulhu` for the multiply, a carry test
  for the add). It used to wrap silently, which an earlier version of this document called
  deliberate; it was a bug — `q[4294967297]` was qubit 1, `repeat 4294967296` ran zero
  times, and `set c = 99999999999` stored 1215752191.
- **Trailing garbage is an error**, everywhere. `print(a) junk`, `endif junk`, `end junk`
  and `qubitop1 a[0] = H junk` are all rejected rather than silently ignored.
- A line that fills the 1024-byte buffer without its newline has lost its tail — RARS
  drops the rest — and is rejected as `Line too long` instead of being run as whatever
  prefix happened to fit.

## Testing

`tools/reference_sim.py` is an independent NumPy oracle written from the language
semantics, not from the assembly. Where the assembly walks amplitude indices bit by bit,
the oracle reshapes the state to an n-dimensional `(2,2,...,2)` tensor and contracts with
`tensordot`/`moveaxis`. Where the assembly executes control flow by recording lines and
replaying them against a frame stack, the oracle parses a real block tree and walks it.
Both differences are deliberate: agreement is then evidence, not a transcription check.

`tools/run_tests.py` runs every `tests/programs/*.dsl` through both and diffs them at a
`1e-4` tolerance — comfortably above float32 accumulation over a handful of multiply-adds,
and thousands of times below the `O(0.1-1)` error a wrong matrix entry produces.

Measurement cannot be compared value for value, since the two implementations draw from
different streams, and reimplementing xorshift32 in Python would turn the oracle into the
transcription check it was built to avoid. Instead the harness **replays the outcomes RARS
actually reported** and checks three independent things: every reported outcome must have
had nonzero probability under exact math, the state printed afterwards must match the
collapse that outcome implies, and `expect_freq` compares empirical frequencies against the
Born rule over many trials.

`tools/check_gate_data.py` runs first, parsing the `.float` declarations straight out of
`main.s` and checking every matrix is unitary and equal to the gate it claims to be. This
exists because **a behavioural test only distinguishes two matrices where its input state
has nonzero amplitude** — the controlled-Z matrix was wrong (`diag(1,1,-1,-1)`, which is
`Z⊗I`) and unitary, and invisible to all four CZ tests, because they shared an input whose
amplitude at `|10>` was 0, which is exactly where the two matrices differ.
