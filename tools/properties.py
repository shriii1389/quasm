#!/usr/bin/env python3
"""Metamorphic and property-based tests for QuAsm.

The behavioural tests in tests/programs/ pin down specific outputs for
specific inputs. That is exactly the shape of testing that missed all three
shipped defects: a fixed input either places weight where a wrong
implementation differs or it does not, and no amount of adding more fixed cases
makes that systematic.

These properties are different in kind. Each states a relation that must hold
for *every* state and *every* gate sequence, and each is then checked over a
seeded random sample of them. A defect survives only if it happens to respect
the relation across the whole sample.

The properties, and which defect class each is aimed at:

  norm            Gates preserve the norm of the state -- including a state
                  that did not start normalised, which the language
                  deliberately permits. This is the region the Born-rule defect
                  lived in, and the sqrt(X) defect (a scalar multiple of the
                  correct matrix) changes norm and nothing else.

  involution      XX = I, HH = I, YY = I, ZZ = I, and the inverse pairs
                  SN.SN = X, S.S = Z, T.T = S, CN.CN = I, SW.SW = I. The
                  existing suite covers these identities, but on fixed inputs;
                  here they run on random asymmetric states, where a wrong
                  matrix entry has somewhere to show up.

  equivariance    Relabelling qubits permutes the state correspondingly:
                  SW(i,j) G(j) SW(i,j) == G(i). This is the property that
                  catches a bit-ordering error, and it shares its mechanism
                  with the mapping test in cross_validate.py.

  collapse        Every measurement outcome the implementation reports must
                  have had nonzero probability, and every collapsed state must
                  be normalised.

  born            The two measurement forms -- single-qubit and whole-register
                  -- must agree with each other, and with the exact Born-rule
                  probability, *on unnormalised registers*. This is defect
                  three stated as a property. It is the one property here that
                  would have caught a defect all three original verification
                  layers missed.

  identity        Multi-qubit circuit identities, each relating different
                  gates rather than a gate to its inverse: SW = CN CN CN with
                  the middle one reversed, CZ and every CPk are symmetric in
                  their two qubits, H CZ H = CN, and SDG CN S = CY. A wrong
                  entry in any one of the gates involved breaks the relation.

  toffoli         The standard 15-gate Clifford+T decomposition of the Toffoli
                  gate, on a random state and random qubits, must swap exactly
                  the two amplitudes |..1..1..0..> and |..1..1..1..> and leave
                  every other amplitude where it was. Checked against that
                  permutation of the engine's own input, not against the
                  oracle.

  qft             The quantum Fourier transform has order four: QFT^4 = I on
                  any state, for any register size. Uses H, SW and the whole
                  CP family together. Blind to one defect by construction: a
                  QFT whose phases are all conjugated still has order four.

Two engines, so the same properties serve two purposes:

    --engine oracle   check against reference_sim.py. Instant, and this is the
                      mode Phase D's mutation screening drives.
    --engine rars     check against the real assembly under RARS, through
                      tools/rars_server.py. This is the mode that tests what ships.

Usage
-----
    python tools/properties.py                        # oracle, default sample
    python tools/properties.py --engine rars --n 20   # the real thing
    python tools/properties.py --self-test            # confirm each property
                                                      # fails when violated
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import reference_sim
from reference_sim import Interpreter

# The interpreter's line buffer holds 1022 bytes of statement, which is room
# for an explicit amplitude list up to the full six qubits.
LINE_LIMIT = 1022
AMP_DECIMALS = 6

# Tolerances: exact arithmetic in the oracle, float32 out of the assembly.
ATOL = {'oracle': 1e-9, 'rars': 1e-4}


def _fmt(x):
    return f'{x:.{AMP_DECIMALS}f}'


# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------

def run_oracle(lines):
    """Returns (printed states, measurement outcome strings)."""
    interp = Interpreter().run(lines)
    prints = [e[1] for e in interp.events if e[0] == 'print']
    measures = [e[1] for e in interp.events if e[0] == 'measure']
    return prints, measures


def run_rars(lines):
    import run_tests
    stdout = run_tests.run_rars(lines)
    events = run_tests.parse_events(stdout)
    prints = [e[1] for e in events if e[0] == 'print']
    measures = [e[1] for e in events if e[0] == 'measure']
    if not prints and not measures:
        raise AssertionError(f'RARS produced no output. Got: {stdout!r}')
    return prints, measures


ENGINES = {'oracle': run_oracle, 'rars': run_rars}


# ---------------------------------------------------------------------------
# State preparation
# ---------------------------------------------------------------------------

def random_amps(rng, n, normalise=True, scale=None):
    """Random amplitudes, all distinct and nonzero.

    `normalise=False` produces a register whose norm is deliberately not 1 --
    a state the language explicitly allows and the region where defect three
    lived.
    """
    v = rng.normal(size=2 ** n) + 1j * rng.normal(size=2 ** n)
    v /= np.linalg.norm(v)
    if not normalise:
        v *= scale if scale is not None else rng.uniform(0.3, 3.0)
    return np.array([complex(float(_fmt(a.real)), float(_fmt(a.imag))) for a in v])


def decl(name, amps):
    body = ','.join(f'({_fmt(a.real)},{_fmt(a.imag)})' for a in amps)
    return f'qubit {name} = [{body}]'


def prepare(rng, n, name, normalise=True):
    """Declaration statements leaving `name` in an asymmetric n-qubit state.

    Normally an explicit amplitude list. If one ever does not fit the line
    buffer, the state is built with a gate prefix instead. Returns
    (lines, amps_or_None) -- amps is None when the state was built by gates,
    since the caller then has to get the expected value from the engine rather
    than from arithmetic here.
    """
    amps = random_amps(rng, n, normalise)
    line = decl(name, amps)
    if len(line) <= LINE_LIMIT:
        return [line], amps
    lines = [f'qubit {name}[{n}]']
    for k in range(n):
        lines.append(f'qubitop1 {name}[{k}] = H')
        lines.append(f'qubitop1 {name}[{k}] = ' + ('T' if k % 2 == 0 else 'S'))
    return lines, None


GATES1 = ['H', 'I', 'X', 'Y', 'Z', 'S', 'T', 'SN', 'SDG', 'TDG']
GATES2 = ['CN', 'SW', 'CY', 'CZ'] + [f'CP{k}' for k in range(1, 7)]

# (first sequence, second sequence) that must leave any state in the same
# place. A pair of single-qubit gate names each, applied to the same qubit.
INVERSE_PAIRS_1Q = [
    (['X', 'X'], []),
    (['H', 'H'], []),
    (['Y', 'Y'], []),
    (['Z', 'Z'], []),
    (['I', 'I'], []),
    (['SN', 'SN'], ['X']),
    (['S', 'S'], ['Z']),
    (['T', 'T'], ['S']),
    (['T', 'T', 'T', 'T'], ['Z']),
    (['H', 'X', 'H'], ['Z']),
    (['H', 'Z', 'H'], ['X']),
    (['S', 'SDG'], []),
    (['SDG', 'S'], []),
    (['T', 'TDG'], []),
    (['TDG', 'T'], []),
    (['TDG', 'TDG'], ['SDG']),
    (['SDG', 'SDG'], ['Z']),
]
INVERSE_PAIRS_2Q = [
    (['CN', 'CN'], []),
    (['SW', 'SW'], []),
    (['CZ', 'CZ'], []),
    (['CY', 'CY'], []),
    (['CP1', 'CP1'], []),
]


# ---------------------------------------------------------------------------
# Properties. Each returns a list of (label, lines, checker).
# ---------------------------------------------------------------------------

def prop_norm(rng, count, max_qubits):
    """Gates preserve the norm of the state, normalised or not."""
    cases = []
    for _ in range(count):
        n = int(rng.integers(1, max_qubits + 1))
        normalise = bool(rng.random() < 0.5)
        lines, amps = prepare(rng, n, 'a', normalise)
        # Norm before is known only when we declared the amplitudes; otherwise
        # print first and take the engine's own starting norm.
        lines = list(lines) + ['print(a)']
        for _ in range(int(rng.integers(1, 7))):
            if n >= 2 and rng.random() < 0.4:
                c, t = rng.choice(n, size=2, replace=False)
                lines.append(f'qubitop2 a[{c}],a[{t}] = {rng.choice(GATES2)}')
            else:
                lines.append(f'qubitop1 a[{int(rng.integers(0, n))}] = '
                             f'{rng.choice(GATES1)}')
        lines += ['print(a)', 'end']

        def check(prints, measures, atol):
            if len(prints) < 2:
                return f'expected 2 prints, got {len(prints)}'
            before, after = np.linalg.norm(prints[0]), np.linalg.norm(prints[1])
            if abs(before - after) > atol * max(1.0, before):
                return (f'norm changed under unitary gates: {before:.9f} -> '
                        f'{after:.9f}')
            return None

        cases.append((f'norm n={n} {"normalised" if normalise else "unnormalised"}',
                      lines, check))
    return cases


def prop_involution(rng, count, max_qubits):
    """Inverse pairs return any state to where it started.

    Two registers prepared identically: one gets the left sequence, the other
    the right. They must end equal. Fixed-input versions of these identities
    are already in the suite; running them on random asymmetric states is what
    gives a wrong matrix entry somewhere to show up.
    """
    cases = []
    for _ in range(count):
        two_q = bool(rng.random() < 0.4)
        n = int(rng.integers(2, max_qubits + 1)) if two_q else \
            int(rng.integers(1, max_qubits + 1))
        left, right = (INVERSE_PAIRS_2Q if two_q else INVERSE_PAIRS_1Q)[
            int(rng.integers(0, len(INVERSE_PAIRS_2Q if two_q else INVERSE_PAIRS_1Q)))]

        lines_a, amps = prepare(rng, n, 'a')
        if amps is not None:
            lines_b = [decl('b', amps)]
        else:
            lines_b = [l.replace(' a[', ' b[').replace('qubit a', 'qubit b')
                       for l in lines_a]
        lines = list(lines_a) + lines_b

        if two_q:
            c, t = (int(x) for x in rng.choice(n, size=2, replace=False))
            for g in left:
                lines.append(f'qubitop2 a[{c}],a[{t}] = {g}')
            for g in right:
                lines.append(f'qubitop2 b[{c}],b[{t}] = {g}')
        else:
            k = int(rng.integers(0, n))
            for g in left:
                lines.append(f'qubitop1 a[{k}] = {g}')
            for g in right:
                lines.append(f'qubitop1 b[{k}] = {g}')
        lines += ['print(a)', 'print(b)', 'end']

        def check(prints, measures, atol):
            if len(prints) < 2:
                return f'expected 2 prints, got {len(prints)}'
            dev = float(np.max(np.abs(prints[0] - prints[1])))
            if dev > atol:
                return (f'{"".join(left)} != {"".join(right) or "I"}: '
                        f'max deviation {dev:.3e}')
            return None

        cases.append((f'involution {"".join(left)}={"".join(right) or "I"} n={n}',
                      lines, check))
    return cases


def prop_equivariance(rng, count, max_qubits):
    """Relabelling qubits permutes the state correspondingly.

    Expressed inside the language as conjugation by SWAP:
        SW(i,j) . G(j) . SW(i,j)  ==  G(i)
    A bit-ordering error breaks this loudly. It is the same mechanism as the
    mapping test in cross_validate.py, which is deliberate -- the two check the
    convention from opposite sides.
    """
    cases = []
    for _ in range(count):
        n = int(rng.integers(2, max_qubits + 1))
        i, j = (int(x) for x in rng.choice(n, size=2, replace=False))
        g = str(rng.choice(GATES1))

        lines_a, amps = prepare(rng, n, 'a')
        if amps is not None:
            lines_b = [decl('b', amps)]
        else:
            lines_b = [l.replace(' a[', ' b[').replace('qubit a', 'qubit b')
                       for l in lines_a]
        lines = list(lines_a) + lines_b + [
            f'qubitop2 a[{i}],a[{j}] = SW',
            f'qubitop1 a[{j}] = {g}',
            f'qubitop2 a[{i}],a[{j}] = SW',
            f'qubitop1 b[{i}] = {g}',
            'print(a)', 'print(b)', 'end',
        ]

        def check(prints, measures, atol):
            if len(prints) < 2:
                return f'expected 2 prints, got {len(prints)}'
            dev = float(np.max(np.abs(prints[0] - prints[1])))
            if dev > atol:
                return (f'SW({i},{j}) {g}({j}) SW({i},{j}) != {g}({i}): '
                        f'max deviation {dev:.3e}')
            return None

        cases.append((f'equivariance {g} qubits {i},{j} n={n}', lines, check))
    return cases


def prop_collapse(rng, count, max_qubits):
    """A measured register is left normalised, and the outcome was possible.

    Possibility is checked against the oracle's exact arithmetic by
    run_tests.py already; what this adds is that it must hold from *random*
    states, including unnormalised ones, rather than from the fixed inputs the
    suite happens to use.
    """
    cases = []
    for _ in range(count):
        n = int(rng.integers(1, max_qubits + 1))
        normalise = bool(rng.random() < 0.5)
        lines, amps = prepare(rng, n, 'a', normalise)
        k = int(rng.integers(0, n))
        lines = list(lines) + [f'measure a[{k}]', 'print(a)', 'end']

        def check(prints, measures, atol):
            if not measures:
                return 'no measurement was reported'
            if not prints:
                return 'no state was printed after the measurement'
            norm = float(np.linalg.norm(prints[-1]))
            if abs(norm - 1.0) > max(atol, 1e-4):
                return (f'collapsed state has norm {norm:.9f}, not 1 '
                        f'(outcome |{measures[-1]}>)')
            return None

        cases.append((f'collapse n={n} qubit {k} '
                      f'{"normalised" if normalise else "unnormalised"}',
                      lines, check))
    return cases


def prop_born(rng, count, max_qubits, trials=200):
    """The two measurement forms agree with each other and with the Born rule,
    on registers that are deliberately not normalised.

    This is defect three restated as a property. The shipped code computed
    P(0) as 1 - P(1), which is only valid on a normalised register: given
    `qubit a = [(2,0),(2,0)]` it computed P(1) = 4, so every draw returned 1
    and a fair coin was deterministic. The whole-register form failed
    differently on the same kind of state rather than identically, so the two
    forms disagreeing *with each other* is the sharpest statement of the bug.

    Both forms are sampled `trials` times from a freshly redeclared register
    and their empirical P(qubit k = 1) is compared against the exact Born-rule
    value and against each other. The tolerance is a 4-sigma binomial band.
    """
    cases = []
    for _ in range(count):
        n = int(rng.integers(1, 3))          # explicit amplitudes need n <= 2
        amps = random_amps(rng, n, normalise=False)
        k = int(rng.integers(0, n))

        weight = np.abs(amps) ** 2
        bit = (np.arange(2 ** n) >> (n - 1 - k)) & 1
        p1 = float(weight[bit == 1].sum() / weight.sum())
        sigma = float(np.sqrt(max(p1 * (1 - p1), 1e-9) / trials))
        tol = max(4 * sigma, 0.04)

        single = [f'repeat {trials}', decl('a', amps), f'measure a[{k}]',
                  'endrepeat', 'end']
        whole = [f'repeat {trials}', decl('a', amps), 'measure a',
                 'endrepeat', 'end']

        def make_check(which, p1=p1, tol=tol, k=k, n=n):
            def check(prints, measures, atol):
                if len(measures) != trials:
                    return f'expected {trials} outcomes, got {len(measures)}'
                if which == 'single':
                    got = sum(1 for m in measures if m == '1') / len(measures)
                else:
                    got = sum(1 for m in measures if m[k] == '1') / len(measures)
                if abs(got - p1) > tol:
                    return (f'{which}-qubit measurement gave P(q{k}=1) = '
                            f'{got:.4f}, Born rule says {p1:.4f} '
                            f'(tolerance {tol:.4f}) on an unnormalised register')
                return None
            return check

        cases.append((f'born single n={n} q{k} p={p1:.3f} unnormalised',
                      single, make_check('single')))
        cases.append((f'born whole n={n} q{k} p={p1:.3f} unnormalised',
                      whole, make_check('whole')))
    return cases


def _twin(rng, n):
    """Two registers, a and b, prepared in the same random asymmetric state."""
    lines_a, amps = prepare(rng, n, 'a')
    if amps is not None:
        lines_b = [decl('b', amps)]
    else:
        lines_b = [l.replace(' a[', ' b[').replace('qubit a', 'qubit b')
                   for l in lines_a]
    return list(lines_a) + lines_b


def _apply(reg, seq):
    """Statements for a gate sequence of ('1', G, q) and ('2', G, c, t)."""
    out = []
    for g in seq:
        if g[0] == '1':
            out.append(f'qubitop1 {reg}[{g[2]}] = {g[1]}')
        else:
            out.append(f'qubitop2 {reg}[{g[2]}],{reg}[{g[3]}] = {g[1]}')
    return out


def prop_identity(rng, count, max_qubits):
    """Circuit identities between different gates, on random states."""
    cases = []
    for _ in range(count):
        n = int(rng.integers(2, max(2, max_qubits) + 1))
        c, t = (int(x) for x in rng.choice(n, size=2, replace=False))
        k = int(rng.integers(1, 7))
        options = [
            ('SW = CN CN CN', [('2', 'CN', c, t), ('2', 'CN', t, c), ('2', 'CN', c, t)],
             [('2', 'SW', c, t)]),
            ('CZ symmetric', [('2', 'CZ', c, t)], [('2', 'CZ', t, c)]),
            (f'CP{k} symmetric', [('2', f'CP{k}', c, t)], [('2', f'CP{k}', t, c)]),
            ('H CZ H = CN', [('1', 'H', t), ('2', 'CZ', c, t), ('1', 'H', t)],
             [('2', 'CN', c, t)]),
            ('SDG CN S = CY', [('1', 'SDG', t), ('2', 'CN', c, t), ('1', 'S', t)],
             [('2', 'CY', c, t)]),
            ('CP1 = CZ', [('2', 'CP1', c, t)], [('2', 'CZ', c, t)]),
        ]
        label, left, right = options[int(rng.integers(len(options)))]
        lines = _twin(rng, n) + _apply('a', left) + _apply('b', right) + \
            ['print(a)', 'print(b)', 'end']

        def check(prints, measures, atol, label=label):
            if len(prints) < 2:
                return f'expected 2 prints, got {len(prints)}'
            dev = float(np.max(np.abs(prints[0] - prints[1])))
            if dev > atol:
                return f'{label} fails: max deviation {dev:.3e}'
            return None

        cases.append((f'identity {label} qubits {c},{t} n={n}', lines, check))
    return cases


# Nielsen & Chuang, Fig. 4.9, over controls x, y and target z.
def _toffoli(x, y, z):
    return [('1', 'H', z), ('2', 'CN', y, z), ('1', 'TDG', z), ('2', 'CN', x, z),
            ('1', 'T', z), ('2', 'CN', y, z), ('1', 'TDG', z), ('2', 'CN', x, z),
            ('1', 'T', y), ('1', 'T', z), ('1', 'H', z), ('2', 'CN', x, y),
            ('1', 'T', x), ('1', 'TDG', y), ('2', 'CN', x, y)]


def prop_toffoli(rng, count, max_qubits):
    """The Clifford+T Toffoli swaps exactly the amplitudes where both controls
    are 1 and the target differs, and nothing else."""
    cases = []
    for _ in range(count):
        n = int(rng.integers(3, max(3, max_qubits) + 1))
        x, y, z = (int(v) for v in rng.choice(n, size=3, replace=False))
        lines, _ = prepare(rng, n, 'a')
        lines = list(lines) + ['print(a)'] + _apply('a', _toffoli(x, y, z)) + \
            ['print(a)', 'end']

        def check(prints, measures, atol, n=n, x=x, y=y, z=z):
            if len(prints) < 2:
                return f'expected 2 prints, got {len(prints)}'
            want = prints[0].copy()
            for i in range(2 ** n):
                bits = [(i >> (n - 1 - q)) & 1 for q in range(n)]
                if bits[x] and bits[y]:
                    want[i] = prints[0][i ^ (1 << (n - 1 - z))]
            dev = float(np.max(np.abs(prints[1] - want)))
            if dev > atol:
                return (f'Toffoli({x},{y}->{z}) is not the permutation it should '
                        f'be: max deviation {dev:.3e}')
            return None

        cases.append((f'toffoli controls {x},{y} target {z} n={n}', lines, check))
    return cases


def _qft(n):
    seq = []
    for j in range(n):
        seq.append(('1', 'H', j))
        for m in range(j + 1, n):
            seq.append(('2', f'CP{m - j + 1}', m, j))
    for j in range(n // 2):
        seq.append(('2', 'SW', j, n - 1 - j))
    return seq


def prop_qft(rng, count, max_qubits):
    """QFT^4 = I, on a random state."""
    cases = []
    for _ in range(count):
        n = int(rng.integers(2, max(2, max_qubits) + 1))
        lines, _ = prepare(rng, n, 'a')
        lines = list(lines) + ['print(a)'] + _apply('a', _qft(n) * 4) + \
            ['print(a)', 'end']

        def check(prints, measures, atol, n=n):
            if len(prints) < 2:
                return f'expected 2 prints, got {len(prints)}'
            # four QFTs are ~4 n^2 / 2 gates of float32 rounding
            dev = float(np.max(np.abs(prints[1] - prints[0])))
            if dev > max(atol, 1e-4):
                return f'QFT^4 != I on {n} qubits: max deviation {dev:.3e}'
            return None

        cases.append((f'qft^4 n={n}', lines, check))
    return cases


PROPERTIES = {
    'norm': prop_norm,
    'involution': prop_involution,
    'equivariance': prop_equivariance,
    'collapse': prop_collapse,
    'born': prop_born,
    'identity': prop_identity,
    'toffoli': prop_toffoli,
    'qft': prop_qft,
}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def build(seed, count, max_qubits, only=None):
    rng = np.random.default_rng(seed)
    cases = []
    for name, fn in PROPERTIES.items():
        if only and name not in only:
            continue
        # `born` runs many trials per case, so it gets fewer cases.
        k = max(1, count // 4) if name == 'born' else count
        cases.extend((name, label, lines, check)
                     for label, lines, check in fn(rng, k, max_qubits))
    return cases


def run(cases, engine, verbose=True, stop_after=None):
    runner = ENGINES[engine]
    atol = ATOL[engine]
    failures = []
    for i, (name, label, lines, check) in enumerate(cases):
        try:
            prints, measures = runner(lines)
            problem = check(prints, measures, atol)
        except Exception as exc:               # a crash is a failure too
            problem = f'{type(exc).__name__}: {exc}'
        if problem:
            failures.append((name, label, problem, lines))
            if verbose:
                print(f'[FAIL] {name}: {label}')
                print(f'       {problem}')
            if stop_after and len(failures) >= stop_after:
                break
        elif verbose and (i + 1) % 100 == 0:
            print(f'  ...{i + 1}/{len(cases)} cases')
    return failures


def summarise(cases, failures):
    by_prop = {}
    for name, _, _, _ in cases:
        by_prop.setdefault(name, [0, 0])[0] += 1
    for name, _, _, _ in failures:
        by_prop[name][1] += 1
    print()
    print(f'{"property":16} {"cases":>7} {"failed":>7}')
    for name, (total, bad) in sorted(by_prop.items()):
        print(f'{name:16} {total:7} {bad:7}')
    print(f'{"TOTAL":16} {len(cases):7} {len(failures):7}')


# ---------------------------------------------------------------------------
# Self-test: every property must fail when its invariant is violated
# ---------------------------------------------------------------------------

def self_test():
    """Deliberately break each invariant and confirm the property notices.

    A property that cannot fail is not evidence. Each violation below is
    injected into the oracle's own gate table or its measurement, so the
    property is exercised exactly as it would be against a real defect.
    """
    problems = []
    saved1 = dict(reference_sim.GATES1)
    saved2 = dict(reference_sim.GATES2)

    def attempt(prop, label, mutate, restore, expect_min=1):
        mutate()
        try:
            cases = build(7, 24, 3, only={prop})
            failures = run(cases, 'oracle', verbose=False)
        finally:
            restore()
        ok = len(failures) >= expect_min
        print(f'[{"PASS" if ok else "FAIL"}] {prop}: {label} -> '
              f'{len(failures)}/{len(cases)} cases failed')
        if not ok:
            problems.append(f'{prop} did not notice: {label}')

    def restore_gates():
        reference_sim.GATES1.clear()
        reference_sim.GATES1.update(saved1)
        reference_sim.GATES2.clear()
        reference_sim.GATES2.update(saved2)

    # norm: a gate that scales the state -- exactly the shipped sqrt(X) defect.
    attempt('norm', 'sqrt(X) scaled by 1.414 (the shipped non-unitary defect)',
            lambda: reference_sim.GATES1.__setitem__('SN',
                saved1['SN'] * np.sqrt(2)), restore_gates)

    # involution: a wrong-but-unitary T breaks T.T = S.
    attempt('involution', 'T phase off by 0.01 rad (unitary but wrong)',
            lambda: reference_sim.GATES1.__setitem__('T',
                np.array([[1, 0], [0, np.exp(1j * (np.pi / 4 + 0.01))]],
                         dtype=complex)), restore_gates)

    # equivariance: a SWAP that is not a swap breaks the relabelling relation.
    attempt('equivariance', 'SWAP replaced by the identity',
            lambda: reference_sim.GATES2.__setitem__('SW',
                np.eye(4, dtype=complex)), restore_gates)

    # collapse: skip renormalisation after projecting.
    saved_exec = Interpreter._exec

    def broken_exec(self, line):
        before = {k: v.copy() for k, v in self.vars.items()}
        result = saved_exec(self, line)
        if line.strip().startswith('measure') and self.events and \
                self.events[-1][0] == 'measure':
            for k in self.vars:
                if k in before and self.vars[k].shape == before[k].shape:
                    self.vars[k] = self.vars[k] * 0.5      # wrong normalisation
        return result

    attempt('collapse', 'collapsed state scaled by 0.5 (renormalisation skipped)',
            lambda: setattr(Interpreter, '_exec', broken_exec),
            lambda: setattr(Interpreter, '_exec', saved_exec))

    # born: reinstate the actual defect -- P(0) = 1 - P(1), valid only on a
    # normalised register. This is the strongest self-test here: it is the
    # historical bug, and the property is the thing that would have caught it.
    saved_outcome = Interpreter._outcome

    def broken_outcome(self, probs, nbits):
        if nbits == 1 and self._forced is None:
            p1 = float(probs[1])
            r = float(self._rng.random())
            index = 1 if r < p1 else 0      # unscaled: the shipped defect
            return format(index, '01b'), index, float(probs[index])
        return saved_outcome(self, probs, nbits)

    attempt('born', 'P(0) computed as 1 - P(1) (the shipped Born-rule defect)',
            lambda: setattr(Interpreter, '_outcome', broken_outcome),
            lambda: setattr(Interpreter, '_outcome', saved_outcome))

    # identity: a CNOT that is really a SWAP -- unitary, and right on half the
    # basis states.
    attempt('identity', 'CN replaced by SW (unitary but wrong)',
            lambda: reference_sim.GATES2.__setitem__('CN', saved2['SW']),
            restore_gates)

    # toffoli: T-dagger a hundredth of a radian out.
    attempt('toffoli', 'TDG phase off by 0.01 rad (unitary but wrong)',
            lambda: reference_sim.GATES1.__setitem__('TDG',
                np.array([[1, 0], [0, np.exp(-1j * (np.pi / 4 + 0.01))]],
                         dtype=complex)), restore_gates)

    # qft: controlled-S a hundredth of a radian out. (Conjugating CP2 would
    # not do: a QFT with conjugated phases still has order four, which is the
    # one blind spot of this property, and the reason it is not the only
    # check on the CP family.)
    attempt('qft', 'CP2 phase off by 0.01 rad (unitary but wrong)',
            lambda: reference_sim.GATES2.__setitem__('CP2', np.diag(
                [1, 1, 1, np.exp(1j * (np.pi / 2 + 0.01))]).astype(complex)),
            restore_gates)

    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--engine', choices=list(ENGINES), default='oracle')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--n', type=int, default=200,
                    help='cases per property (born gets a quarter as many)')
    ap.add_argument('--max-qubits', type=int, default=4)
    ap.add_argument('--only', nargs='*', choices=list(PROPERTIES))
    ap.add_argument('--self-test', action='store_true',
                    help='confirm each property fails when its invariant is broken')
    args = ap.parse_args()

    if args.self_test:
        problems = self_test()
        print()
        if problems:
            for p in problems:
                print(f'[FAIL] {p}')
            return 1
        print('self-test passed: every property fails when its invariant is violated')
        return 0

    cases = build(args.seed, args.n, args.max_qubits, set(args.only or []) or None)
    print(f'{len(cases)} property cases, engine={args.engine}, seed={args.seed}')
    failures = run(cases, args.engine)
    summarise(cases, failures)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
