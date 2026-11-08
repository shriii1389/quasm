#!/usr/bin/env python3
"""External cross-validation of QuAsm against Qiskit, an independently authored
simulator.

Why this exists
---------------
Every other check in this repo is self-authored: the behavioural tests, the
NumPy oracle in reference_sim.py and the static audit in check_gate_data.py all
encode one person's understanding of the semantics. If that understanding is
wrong in the same way twice, they agree and say nothing. Qiskit was written by
other people, so agreement with it is evidence of a different kind.

What it does and does not establish
-----------------------------------
Qiskit is genuinely independent, so agreement is real evidence about gate
semantics and about the kernel. But the *mapping* between QuAsm's conventions
and Qiskit's is written here, by us, and a wrong mapping quietly tuned until the
disagreements went away would manufacture false agreement. Two rules keep that
honest, and both are stated in the paper:

1. The mapping is fixed a priori from the two projects' documented conventions.
   QuAsm: qubit 0 is the *most* significant bit of an amplitude index (docs and
   paper Sec. 3). Qiskit: qubit 0 is the *least* significant. The consequence is
   a straight reversal, QuAsm qubit k <-> Qiskit qubit n-1-k, and under it the
   two amplitude-index orders coincide, so state vectors compare element for
   element with no permutation. That is the whole mapping. It is NEVER adjusted
   in response to a failing comparison -- a disagreement is a bug report.

2. The mapping is itself tested, by circuits whose output is asymmetric under
   qubit permutation (`--self-test`). X on qubit 0 alone of a 3-qubit register
   must give |100>, index 4, in QuAsm order. A reversed or identity mapping
   fails these loudly instead of hiding inside an averaged agreement.

Three engines, compared pairwise:

    QuAsm assembly (under RARS)  --.
    reference_sim.py oracle      --+--> all three must agree
    Qiskit                       --'

The oracle<->Qiskit sweep is fast (no JVM) and runs in CI on every push. The
RARS-inclusive sweep runs through tools/rars_server.py, about a minute for 200
circuits, and runs on a schedule.

Corpus reproducibility
----------------------
Generation is seeded and deterministic: `--seed S --n N` regenerates the same N
programs byte for byte on any machine. `--manifest` prints a SHA-256 over the
whole generated corpus so a reviewer can confirm they have the same one, and
`--dump DIR` writes the .dsl files out if they want to read them.

Usage
-----
    python tools/cross_validate.py --seed 0 --n 500            # oracle vs Qiskit
    python tools/cross_validate.py --seed 0 --n 200 --rars     # all three
    python tools/cross_validate.py --self-test                 # mapping + negative tests
    python tools/cross_validate.py --seed 0 --n 500 --manifest
"""
import argparse
import hashlib
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reference_sim import Interpreter, MAX_QUBITS

# ---------------------------------------------------------------------------
# The mapping. Fixed a priori. Do not adjust in response to a failure.
# ---------------------------------------------------------------------------

def quasm_to_qiskit_qubit(k, n):
    """QuAsm qubit k is Qiskit qubit n-1-k.

    QuAsm indexes an amplitude as sum_k q_k * 2^(n-1-k) (qubit 0 most
    significant); Qiskit as sum_j b_j * 2^j (qubit 0 least significant).
    Substituting j = n-1-k makes the two index expressions identical, which is
    why the amplitude vectors below are compared without any permutation.
    """
    return n - 1 - k


# QuAsm gate name -> (Qiskit gate factory, arity). SN is Qiskit's SX: both are
# 0.5 * [[1+i, 1-i], [1-i, 1+i]], the principal square root of X.
def _qiskit_gates():
    from qiskit.circuit.library import (CPhaseGate, CXGate, CYGate, CZGate,
                                        HGate, IGate, SdgGate, SGate, SwapGate,
                                        SXGate, TdgGate, TGate, XGate, YGate,
                                        ZGate)
    one = {'H': HGate, 'I': IGate, 'X': XGate, 'Y': YGate, 'Z': ZGate,
           'S': SGate, 'T': TGate, 'SN': SXGate, 'SDG': SdgGate, 'TDG': TdgGate}
    two = {'CN': CXGate, 'SW': SwapGate, 'CY': CYGate, 'CZ': CZGate}
    for k in range(1, MAX_QUBITS + 1):
        # CPk = diag(1,1,1, exp(2 pi i / 2^k)); CP1 == CZ.
        two[f'CP{k}'] = (lambda k=k: CPhaseGate(2 * np.pi / 2 ** k))
    return one, two


GATES1_NAMES = ['H', 'I', 'X', 'Y', 'Z', 'S', 'T', 'SN', 'SDG', 'TDG']
GATES2_NAMES = ['CN', 'SW', 'CY', 'CZ'] + [f'CP{k}' for k in range(1, MAX_QUBITS + 1)]

# The interpreter reads statements through a line buffer that holds 1022 bytes,
# enough for an explicit amplitude list on every register size generated here.
# If one ever does not fit, prepare() falls back to a gate prefix.
LINE_LIMIT = 1022
AMP_DECIMALS = 6


# ---------------------------------------------------------------------------
# Program generation
# ---------------------------------------------------------------------------

def _fmt(x):
    """Plain decimal, six places: finer than float32, and never out of range."""
    return f'{x:.{AMP_DECIMALS}f}'


def random_state(rng, n):
    """A normalised state with every amplitude distinct and nonzero.

    This is the property whose absence hid the controlled-Z defect: a corpus
    that only ever starts from |0...0> reproduces the original blind spot,
    because a wrong matrix entry is invisible wherever the input amplitude is
    zero.
    """
    while True:
        v = rng.normal(size=2 ** n) + 1j * rng.normal(size=2 ** n)
        v /= np.linalg.norm(v)
        # Round first, then test: the rounded values are what the DSL actually
        # parses, so distinctness has to hold after rounding.
        r = np.array([complex(float(_fmt(a.real)), float(_fmt(a.imag))) for a in v])
        if np.all(np.abs(r.real) > 1e-3) and np.all(np.abs(r.imag) > 1e-3):
            if len({(a.real, a.imag) for a in r}) == len(r):
                r /= np.linalg.norm(r)
                return np.array([complex(float(_fmt(a.real)), float(_fmt(a.imag)))
                                 for a in r])


def prepare(rng, n, name='a'):
    """Statements that leave register `name` in an asymmetric n-qubit state.

    Normally the amplitudes are declared directly: a random state with every
    amplitude distinct and nonzero, which exercises the declaration path as
    well as the kernel. If that line would not fit the buffer, the register is
    declared |0...0> and asymmetrised with a gate prefix; Qiskit applies the
    same prefix, so that is still an end-to-end comparison.
    """
    amps = random_state(rng, n)
    body = ','.join(f'({_fmt(a.real)},{_fmt(a.imag)})' for a in amps)
    line = f'qubit {name} = [{body}]'
    if len(line) <= LINE_LIMIT:
        return [line]
    lines = [f'qubit {name}[{n}]']
    for k in range(n):
        lines.append(f'qubitop1 {name}[{k}] = H')
        # T and S give the amplitudes distinct phases, so no two coincide.
        lines.append(f'qubitop1 {name}[{k}] = ' + ('T' if k % 2 == 0 else 'S'))
    for k in range(n):
        lines.append(f'qubitop1 {name}[{k}] = {rng.choice(GATES1_NAMES)}')
    return lines


def random_program(rng, name='a', max_qubits=4, depth=None):
    """One random unitary circuit as DSL statement lines.

    Unitary only: measurement draws from the assembly's own PRNG, so Qiskit
    cannot predict a trajectory. Measurement stays on the existing replay
    scheme in run_tests.py.
    """
    n = int(rng.integers(1, max_qubits + 1))
    if depth is None:
        depth = int(rng.integers(1, 9))
    lines = prepare(rng, n, name)
    for _ in range(depth):
        if n >= 2 and rng.random() < 0.5:
            c, t = rng.choice(n, size=2, replace=False)
            lines.append(f'qubitop2 {name}[{c}],{name}[{t}] = {rng.choice(GATES2_NAMES)}')
        else:
            k = int(rng.integers(0, n))
            lines.append(f'qubitop1 {name}[{k}] = {rng.choice(GATES1_NAMES)}')
    lines.append(f'print({name})')
    lines.append('end')
    return n, lines


def generate(seed, count, max_qubits=4):
    rng = np.random.default_rng(seed)
    return [random_program(rng, max_qubits=max_qubits) for _ in range(count)]


# ---------------------------------------------------------------------------
# The three engines
# ---------------------------------------------------------------------------

def run_oracle(lines):
    interp = Interpreter().run(lines)
    if not interp.prints:
        raise AssertionError('program produced no print()')
    return interp.prints[-1]


def run_qiskit(lines, n, gate_overrides=None, invert_mapping=False):
    """Rebuild the same circuit in Qiskit and return its final statevector,
    in QuAsm amplitude order.

    `gate_overrides` and `invert_mapping` exist only for the negative tests in
    --self-test, which deliberately break the harness to confirm it complains.
    """
    from qiskit import QuantumCircuit
    from qiskit.quantum_info import Statevector

    one, two = _qiskit_gates()
    if gate_overrides:
        one, two = dict(one), dict(two)
        for name, factory in gate_overrides.items():
            (one if name in one else two)[name] = factory

    def q(k):
        return k if invert_mapping else quasm_to_qiskit_qubit(k, n)

    qc = QuantumCircuit(n)
    init = None
    for line in lines:
        line = line.split('#')[0].strip()
        if not line or line == 'end' or line.startswith('print'):
            continue
        if line.startswith('qubit '):
            rest = line[len('qubit '):]
            if '=' in rest:
                amps = rest.split('=', 1)[1].strip().strip('[]')
                vals = []
                for pair in amps.split('),'):
                    pair = pair.strip().strip('()')
                    re_, im_ = pair.split(',')
                    vals.append(complex(float(re_), float(im_)))
                init = np.array(vals, dtype=complex)
            continue
        if line.startswith('qubitop1 '):
            spec, gate = line[len('qubitop1 '):].split('=')
            k = int(spec.strip().split('[')[1].rstrip('] '))
            g = one[gate.strip()]
            qc.append(g() if callable(g) else g, [q(k)])
            continue
        if line.startswith('qubitop2 '):
            spec, gate = line[len('qubitop2 '):].split('=')
            a, b = spec.strip().split(',')
            c = int(a.strip().split('[')[1].rstrip('] '))
            t = int(b.strip().split('[')[1].rstrip('] '))
            g = two[gate.strip()]
            qc.append(g() if callable(g) else g, [q(c), q(t)])
            continue
        raise AssertionError(f'cross_validate cannot map statement: {line!r}')

    # The QuAsm and Qiskit amplitude-index orders coincide under the mapping
    # above, so the initial vector goes in as-is and the result comes out as-is.
    sv = Statevector(init) if init is not None else Statevector.from_int(0, 2 ** n)
    return np.asarray(sv.evolve(qc).data, dtype=complex)


def run_rars_state(lines):
    """Final printed state from the real assembly under RARS."""
    import run_tests
    stdout = run_tests.run_rars(lines)
    events = run_tests.parse_events(stdout)
    prints = [e[1] for e in events if e[0] == 'print']
    if not prints:
        raise AssertionError(f'RARS produced no print(). Output: {stdout!r}')
    return prints[-1]


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def compare(a, b, atol=None):
    """Compare two states three ways, so that a disagreement is diagnosable
    rather than merely reported:

      - **deviation**, elementwise max |a - b|. This is the failure criterion:
        it catches every difference, including ones that change only the norm.
      - **overlap**, |<a|b>| / (|a| |b|). Insensitive to global phase *and* to
        global scale, so overlap = 1 with a large deviation means the two
        states differ by a phase or a scale factor, not in direction.
      - **norm ratio**, |b| / |a|. Separates those two cases.

    The distinction is not academic. The shipped sqrt(X) defect was a gate
    carrying a 0.707 normalisation instead of 0.5 -- i.e. exactly a scalar
    multiple of the correct matrix. It changes the norm of the state and
    nothing else, so *any* direction-only comparison calls it agreement. That
    is why the failure criterion here is deviation and why the unitarity audit
    in check_gate_data.py is a separate layer rather than a redundant one.

    Returns (max_dev, overlap, norm_ratio).
    """
    if a.shape != b.shape:
        return float('inf'), 0.0, float('nan')
    dev = float(np.max(np.abs(a - b))) if a.size else 0.0
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    ov = float(abs(np.vdot(a, b)) / (na * nb)) if na > 0 and nb > 0 else 0.0
    ratio = float(nb / na) if na > 0 else float('nan')
    return dev, ov, ratio


# ---------------------------------------------------------------------------
# Mapping and negative tests
# ---------------------------------------------------------------------------

# Circuits whose output is asymmetric under qubit permutation: each names the
# QuAsm amplitude index that must carry the weight. A wrong qubit mapping moves
# the weight somewhere else and these fail loudly.
MAPPING_TESTS = [
    # X on qubit 0 alone of 3 qubits -> |100>, which is index 4 in QuAsm order.
    (3, ['qubit a[3]', 'qubitop1 a[0] = X', 'print(a)', 'end'], 4),
    # X on the last qubit -> |001>, index 1. Together with the above this pins
    # the direction of the mapping, not merely that one exists.
    (3, ['qubit a[3]', 'qubitop1 a[2] = X', 'print(a)', 'end'], 1),
    (4, ['qubit a[4]', 'qubitop1 a[0] = X', 'print(a)', 'end'], 8),
    (4, ['qubit a[4]', 'qubitop1 a[1] = X', 'print(a)', 'end'], 4),
    # CNOT control 0 target 2, with control set: |101>, index 5. Asymmetric in
    # both operands, so it also pins the control/target order.
    (3, ['qubit a[3]', 'qubitop1 a[0] = X', 'qubitop2 a[0],a[2] = CN',
         'print(a)', 'end'], 5),
    # Control and target swapped: control (qubit 2) is 0, so nothing happens.
    (3, ['qubit a[3]', 'qubitop1 a[0] = X', 'qubitop2 a[2],a[0] = CN',
         'print(a)', 'end'], 4),
]


def self_test(verbose=True):
    """Confirms the harness fails when it should. Three ways:
      1. the mapping tests above pass as written;
      2. inverting the mapping makes them fail;
      3. corrupting a gate constant makes a random sweep fail.
    A harness that cannot fail is not evidence of anything.
    """
    problems = []

    def say(msg):
        if verbose:
            print(msg)

    # 1. Mapping tests, on all three engines where available.
    for n, lines, want in MAPPING_TESTS:
        oracle = run_oracle(lines)
        qk = run_qiskit(lines, n)
        got_o = int(np.argmax(np.abs(oracle)))
        got_q = int(np.argmax(np.abs(qk)))
        ok = got_o == want and got_q == want and abs(abs(oracle[want]) - 1) < 1e-9
        say(f'[{"PASS" if ok else "FAIL"}] mapping: {lines[1:-2]} -> index {want} '
            f'(oracle {got_o}, qiskit {got_q})')
        if not ok:
            problems.append(f'mapping test {lines} expected index {want}, '
                            f'oracle gave {got_o}, qiskit gave {got_q}')

    # 2. Deliberately inverted mapping must break them.
    caught = 0
    for n, lines, want in MAPPING_TESTS:
        qk = run_qiskit(lines, n, invert_mapping=True)
        if int(np.argmax(np.abs(qk))) != want:
            caught += 1
    asymmetric = sum(1 for n, _, want in MAPPING_TESTS
                     if want != int(format(want, f'0{n}b')[::-1], 2))
    say(f'[{"PASS" if caught == asymmetric else "FAIL"}] inverted mapping is '
        f'detected by {caught}/{asymmetric} asymmetric mapping tests')
    if caught != asymmetric:
        problems.append(f'an inverted qubit mapping was caught by only {caught} of '
                        f'{asymmetric} asymmetric mapping tests')

    # 3. Corrupted gate constants must make the sweep fail.
    #
    # Note on choosing a corruption: a global sign on a single-qubit gate is
    # NOT a valid test. If X is only ever applied as a 1-qubit gate, -X differs
    # from X by a global phase, which is physically unobservable and which our
    # overlap check correctly reports as agreement. The corruptions below are
    # real physical differences. The first is the paper's own historical
    # defect, so this doubles as a check that the harness would have caught it.
    from qiskit.circuit.library import UnitaryGate

    # A reflection [[cos, sin], [sin, -cos]] is unitary for every angle, so
    # nudging the angle gives a wrong-but-unitary H: the same defect class as
    # the controlled-Z bug, and the class a unitarity check cannot catch.
    th = np.pi / 4 + 1e-3
    corruptions = {
        # Historical defect 1: the shipped controlled-Z was diag(1,1,-1,-1),
        # which is Z tensor I, not diag(1,1,1,-1). Perfectly unitary.
        'CZ': UnitaryGate(np.diag([1, 1, -1, -1]).astype(complex), label='badCZ'),
        # Unitary but wrong, by a thousandth of a radian.
        'H': UnitaryGate(np.array([[np.cos(th), np.sin(th)],
                                   [np.sin(th), -np.cos(th)]], dtype=complex),
                         label='badH'),
        # Historical defect 2: sqrt(X) carrying a 0.707 normalisation instead
        # of 0.5, so column norm squared is 2 and it is not unitary at all.
        # check_input=False is needed because Qiskit rightly refuses to build a
        # non-unitary gate -- we are deliberately injecting a broken one.
        'SN': UnitaryGate(0.70710678 * np.array([[1 + 1j, 1 - 1j],
                                                 [1 - 1j, 1 + 1j]], dtype=complex),
                          label='badSN', check_input=False),
    }

    progs = generate(12345, 60, max_qubits=3)
    for gate, bad in corruptions.items():
        applicable = 0
        disagreements = 0
        worst_ov = 1.0
        worst_ratio = 1.0
        for n, lines in progs:
            if not any(l.rstrip().endswith('= ' + gate) for l in lines):
                continue
            applicable += 1
            ok_state = run_qiskit(lines, n)
            bad_state = run_qiskit(lines, n, gate_overrides={gate: (lambda b=bad: b)})
            dev, ov, ratio = compare(ok_state, bad_state)
            if dev > 1e-9:
                disagreements += 1
                worst_ov = min(worst_ov, ov)
                worst_ratio = ratio
        ok = applicable > 0 and disagreements > 0
        note = ''
        if disagreements and worst_ov > 1 - 1e-12:
            note = (f' -- overlap stays 1.0 (norm ratio {worst_ratio:.6f}): this '
                    f'corruption is a scalar multiple, caught by deviation only')
        say(f'[{"PASS" if ok else "FAIL"}] a corrupted {gate} gate is detected on '
            f'{disagreements}/{applicable} circuits that use it{note}')
        if not ok:
            problems.append(f'corrupting the {gate} gate produced no detectable '
                            f'disagreement across {applicable} applicable circuits')

    return problems


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------

def corpus_digest(progs):
    h = hashlib.sha256()
    for n, lines in progs:
        h.update(('\n'.join(lines) + '\n').encode('utf-8'))
    return h.hexdigest()


def sweep(seed, count, use_rars, max_qubits, atol_exact, atol_rars, verbose):
    progs = generate(seed, count, max_qubits=max_qubits)
    worst_oq = 0.0
    worst_rars = 0.0
    min_overlap = 1.0
    failures = []

    for i, (n, lines) in enumerate(progs):
        oracle = run_oracle(lines)
        qk = run_qiskit(lines, n)
        dev, ov, _ = compare(oracle, qk)
        worst_oq = max(worst_oq, dev)
        min_overlap = min(min_overlap, ov)
        if dev > atol_exact:
            failures.append((i, 'oracle vs qiskit', dev, ov, lines))

        if use_rars:
            rars = run_rars_state(lines)
            dev_r, ov_r, _ = compare(qk, rars)
            worst_rars = max(worst_rars, dev_r)
            min_overlap = min(min_overlap, ov_r)
            if dev_r > atol_rars:
                failures.append((i, 'qiskit vs RARS', dev_r, ov_r, lines))

        if verbose and (i + 1) % 50 == 0:
            print(f'  ...{i + 1}/{len(progs)} circuits, '
                  f'worst oracle-qiskit deviation {worst_oq:.2e}'
                  + (f', worst qiskit-RARS {worst_rars:.2e}' if use_rars else ''))

    return progs, worst_oq, worst_rars, min_overlap, failures


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--n', type=int, default=500, help='number of random circuits')
    ap.add_argument('--max-qubits', type=int, default=4)
    ap.add_argument('--rars', action='store_true',
                    help='also run each program through the real assembly')
    ap.add_argument('--self-test', action='store_true',
                    help='mapping tests and deliberate-corruption negative tests')
    ap.add_argument('--manifest', action='store_true',
                    help='print a SHA-256 over the generated corpus and exit')
    ap.add_argument('--dump', metavar='DIR', help='write the generated .dsl files out')
    ap.add_argument('--atol', type=float, default=1e-10,
                    help='tolerance for the exact-arithmetic oracle/Qiskit comparison')
    ap.add_argument('--atol-rars', type=float, default=1e-4,
                    help='tolerance against float32 assembly output')
    args = ap.parse_args()

    try:
        import qiskit
    except ImportError:
        print('qiskit is not installed. pip install -r requirements.txt', file=sys.stderr)
        return 2

    if args.manifest or args.dump:
        progs = generate(args.seed, args.n, max_qubits=args.max_qubits)
        print(f'corpus: seed={args.seed} n={args.n} max_qubits={args.max_qubits}')
        print(f'sha256: {corpus_digest(progs)}')
        if args.dump:
            os.makedirs(args.dump, exist_ok=True)
            for i, (n, lines) in enumerate(progs):
                with open(os.path.join(args.dump, f'xv_{i:04d}.dsl'), 'w',
                          encoding='utf-8', newline='\n') as f:
                    f.write('\n'.join(lines) + '\n')
            print(f'wrote {len(progs)} programs to {args.dump}')
        return 0

    print(f'qiskit {qiskit.__version__}')

    if args.self_test:
        problems = self_test()
        print()
        if problems:
            for p in problems:
                print(f'[FAIL] {p}')
            print(f'{len(problems)} self-test problem(s)')
            return 1
        print('self-test passed: the mapping is right, and the harness fails when '
              'the mapping or a gate constant is broken')
        return 0

    print(f'sweeping {args.n} random circuits, seed {args.seed}, '
          f'up to {args.max_qubits} qubits'
          + (' (including RARS)' if args.rars else ' (oracle vs qiskit only)'))
    progs, worst_oq, worst_rars, min_ov, failures = sweep(
        args.seed, args.n, args.rars, args.max_qubits,
        args.atol, args.atol_rars, verbose=True)

    print()
    print(f'corpus sha256:                {corpus_digest(progs)}')
    print(f'circuits compared:            {len(progs)}')
    print(f'worst oracle-Qiskit deviation: {worst_oq:.3e}  (tolerance {args.atol:.0e})')
    if args.rars:
        print(f'worst Qiskit-RARS deviation:   {worst_rars:.3e}  '
              f'(tolerance {args.atol_rars:.0e})')
    print(f'minimum overlap |<a|b>|:       {min_ov:.15f}')

    if failures:
        print(f'\n{len(failures)} DISAGREEMENT(S):')
        for i, what, dev, ov, lines in failures[:10]:
            print(f'  circuit {i} [{what}] deviation {dev:.3e}, overlap {ov:.12f}')
            for l in lines:
                print(f'    {l}')
        return 1

    print('\nno disagreements')
    return 0


if __name__ == '__main__':
    sys.exit(main())
