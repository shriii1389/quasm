#!/usr/bin/env python3
"""Mutation testing for QuAsm.

The paper argues that a behavioural test suite cannot reach wrong *constant
data*, because a test only distinguishes two matrices where its input state has
weight at an index where they differ. That argument is currently supported by
three anecdotes. This tool turns it into a measurement: generate defects
systematically, and count how many each verification layer catches.

Mutation classes
----------------
Mirroring the two defect classes the paper describes:

1. **Constant mutations** on the `.float` gate matrices in main.s -- sign
   flips, single-digit changes, swapped entries, ULP nudges, zeroed entries.
   Both *unitary-preserving* mutants (the class the controlled-Z bug belongs
   to) and *non-unitary* ones (the sqrt(X) bug) are generated, and reported
   separately, because only the unitary-preserving subset is genuinely hard:
   a unitarity check catches the rest by construction.

2. **Code mutations** in gateFunctions.s and measure.s -- branch condition
   flips, off-by-one immediates, swapped register operands.

Equivalent mutants
------------------
A mutant that is semantically identical to the original cannot be killed by
anything, so counting it as a survivor understates the suite and flatters the
argument this tool exists to test. Two kinds are handled explicitly:

- **One-ULP nudges** to a gate constant sit below the suite's 1e-4 comparison
  tolerance by construction. They are generated (they show the tolerance is not
  accidentally tight) but reported on their own row and excluded from the
  headline totals.
- **Operand swaps on commutative operations** -- add, mul, and, or, xor, and
  IEEE-754 fadd.s and fmul.s -- are provably semantics-preserving, so
  swap_operands is restricted to non-commutative instructions. An earlier
  version did not do this, and five of nine apparent code-mutant survivors were
  simply `fadd.s a, b, c` rewritten as `fadd.s a, c, b`.

Getting a real mutation score rather than an oracle-level one
-------------------------------------------------------------
Screening every mutant through the 19-minute suite is infeasible, so screening
happens in the NumPy oracle -- but the screening proxy must not become the
published number. Three stages:

**Stage 1, screen (fast, exact).** Substitute the mutated matrix into the
oracle and re-run every test program that uses that gate, in exact arithmetic.
A mutation to gate G cannot change the behaviour of a program that never
applies G, so restricting to that subset is a sound restriction, not a
sampling shortcut. If no program's output moves by more than the suite's own
1e-4 tolerance, no behavioural test could have distinguished the mutant.

**Stage 2, confirm every survivor under RARS.** Stage 1 runs the *oracle* with
a substituted matrix; the real mutant lives in the *assembly*. Every survivor
is therefore rebuilt as a genuinely mutated main.s and run through the real
harness (run_tests.run_test, the same checks CI uses) against the programs that
exercise the mutated gate. This is what makes the reported score an
implementation-level result.

**Stage 3, confirm near-tolerance kills.** Stage 1 computes in complex128
while the assembly runs float32 against a 1e-4 tolerance, so a mutant whose
exact-arithmetic deviation sits just above tolerance may not actually be killed
in practice. Every mutant whose deviation falls in a stated band above 1e-4
also goes through RARS. Mutants killed by a wide margin need no confirmation.

Programs judged statistically (expect_freq) or with a noise channel are never
screened out: their prints are not compared at all, so a deviation of zero in
Stage 1 says nothing about them. They always go to RARS if they use the gate.

Two scores, both reported
-------------------------
(a) against the behavioural suite in tests/programs -- this is what supports
the paper's historical claim; and (b) against that suite plus the Phase C
properties, which is what the artifact actually ships. **The difference between
the two is the argument for the property tests.**

Ground truth
------------
`--historical` re-runs the paper's three shipped defects as seeded mutants and
checks the tool reports the killing layer the paper claims for each. A mutation
harness that cannot reproduce known defects is not measuring anything.

Usage
-----
    python tools/mutate.py --list                 # enumerate mutants, no runs
    python tools/mutate.py --stage1               # oracle screen only (fast)
    python tools/mutate.py --historical           # ground-truth check
    python tools/mutate.py --full                 # all stages, hours
    python tools/mutate.py --full --max-rars 40   # cap the RARS budget
"""
import argparse
import os
import re
import shutil
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_gate_data
import properties
import reference_sim
import run_tests
from reference_sim import Interpreter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_S = os.path.join(ROOT, 'main.s')
TEST_DIR = os.path.join(ROOT, 'tests', 'programs')

TOLERANCE = run_tests.TOLERANCE            # 1e-4, the suite's own tolerance

# Every program in the corpus finishes within 20 million instructions, so a
# mutant that runs past twice that has changed behaviour -- usually a loop that
# no longer ends -- and counts as killed by timeout, as mutation tools
# conventionally count one. The default cap is 200 million, which made each
# such mutant cost minutes.
import rars_server                                     # noqa: E402
rars_server.MAX_STEPS = 40_000_000
NEAR_BAND = 100 * TOLERANCE                # kills below this get RARS confirmation

# main.s label -> the gate name the DSL uses.
LABEL_TO_GATE = {'Hgate': 'H', 'Igate': 'I', 'Xgate': 'X', 'Ygate': 'Y',
                 'Zgate': 'Z', 'Sgate': 'S', 'Tgate': 'T', 'SNgate': 'SN',
                 'SDGgate': 'SDG', 'TDGgate': 'TDG',
                 'CNgate': 'CN', 'SWgate': 'SW', 'CYgate': 'CY', 'CZgate': 'CZ'}
for _k in range(1, 7):
    LABEL_TO_GATE[f'CP{_k}gate'] = f'CP{_k}'

GATE_TO_LABEL = {v: k for k, v in LABEL_TO_GATE.items()}


# ---------------------------------------------------------------------------
# Reading and rewriting the .float gate blocks in main.s
# ---------------------------------------------------------------------------

LABELLED_RE = re.compile(r'^(\s*)(\w+):(\s*)\.float\s+([-0-9.,\s]+?)\s*$')
CONTINUED_RE = re.compile(r'^(\s*)\.float\s+([-0-9.,\s]+?)\s*$')


def read_blocks(text):
    """label -> (start_line, end_line_exclusive, [float values])."""
    lines = text.split('\n')
    blocks = {}
    current = None
    for i, line in enumerate(lines):
        m = LABELLED_RE.match(line)
        if m:
            current = m.group(2)
            blocks[current] = [i, i + 1,
                               [float(x) for x in m.group(4).split(',') if x.strip()]]
            continue
        m = CONTINUED_RE.match(line)
        if m and current is not None:
            blocks[current][1] = i + 1
            blocks[current][2].extend(
                float(x) for x in m.group(2).split(',') if x.strip())
            continue
        if line.strip():
            current = None
    return blocks


def _fmt_float(x):
    """Render like the source does: plain decimal, no exponent.

    Both the assembly's own parser and check_gate_data's regex accept only
    [-0-9.], so exponent notation cannot be emitted here -- a value written as
    1.4e-45 would be silently misread. Nine decimal places is finer than
    float32 resolves and round-trips every constant in main.s.
    """
    if x == int(x) and abs(x) < 1e7:
        return str(int(x))
    s = f'{x:.9f}'.rstrip('0').rstrip('.')
    if s in ('', '-', '-0'):
        return '0'
    assert 'e' not in s and 'E' not in s, f'exponent leaked into .float: {s}'
    return s


def write_block(text, label, values):
    """Rewrite one gate's .float declaration with new values, keeping the
    original line layout (one matrix row per source line)."""
    lines = text.split('\n')
    start, end, old = read_blocks(text)[label]
    n_rows = end - start
    per_row = len(old) // n_rows
    indent_m = LABELLED_RE.match(lines[start])
    lead, gap = indent_m.group(1), indent_m.group(3)
    pad = ' ' * (len(lead) + len(label) + 1 + len(gap))

    out = []
    for r in range(n_rows):
        chunk = values[r * per_row:(r + 1) * per_row]
        body = ', '.join(f'{_fmt_float(chunk[i])},{_fmt_float(chunk[i + 1])}'
                         for i in range(0, len(chunk), 2))
        if r == 0:
            out.append(f'{lead}{label}:{gap}.float {body}')
        else:
            out.append(f'{pad}.float {body}')
    return '\n'.join(lines[:start] + out + lines[end:])


def to_matrix(values):
    v = np.array([complex(values[i], values[i + 1])
                  for i in range(0, len(values), 2)], dtype=complex)
    d = int(round(np.sqrt(len(v))))
    return v.reshape(d, d)


def is_unitary(m, atol=1e-6):
    return np.allclose(m.conj().T @ m, np.eye(m.shape[0]), atol=atol, rtol=0)


# ---------------------------------------------------------------------------
# Mutants
# ---------------------------------------------------------------------------

class Mutant:
    def __init__(self, kind, target, operator, detail, values=None,
                 file_edit=None):
        self.kind = kind              # 'constant' or 'code'
        self.target = target          # gate label, or source filename
        self.operator = operator
        self.detail = detail
        self.values = values          # mutated float list, for constants
        self.file_edit = file_edit    # (filename, old_line, new_line), for code
        self.unitary = None
        # results filled in as stages run
        self.audit_kill = None
        self.stage1_dev = None
        self.behavioural_kill = None
        self.property_kill = None
        self.confirmed_by = None      # 'stage1', 'rars', or None

    @property
    def gate(self):
        return LABEL_TO_GATE.get(self.target)

    def __str__(self):
        return f'{self.target}/{self.operator}: {self.detail}'


def constant_mutants(text, rng, per_gate=None):
    """Systematic single-entry mutations of every gate matrix."""
    blocks = read_blocks(text)
    out = []
    for label in LABEL_TO_GATE:
        if label not in blocks:
            continue
        base = blocks[label][2]
        n = len(base)
        for idx in range(n):
            v = base[idx]

            # sign flip -- only meaningful on a nonzero entry
            if v != 0:
                mv = list(base)
                mv[idx] = -v
                out.append(Mutant('constant', label, 'sign_flip',
                                  f'entry {idx}: {v} -> {-v}', mv))

            # zero an entry
            if v != 0:
                mv = list(base)
                mv[idx] = 0.0
                out.append(Mutant('constant', label, 'zero_entry',
                                  f'entry {idx}: {v} -> 0', mv))

            # single-digit change: perturb the 3rd decimal, the kind of typo a
            # human makes transcribing 0.70710678
            mv = list(base)
            mv[idx] = v + (0.001 if v >= 0 else -0.001)
            out.append(Mutant('constant', label, 'digit_change',
                              f'entry {idx}: {v} -> {mv[idx]:.8f}', mv))

            # ULP nudge in float32 -- below the suite's tolerance by design,
            # included to show the tolerance is not accidentally tight.
            #
            # Only on nonzero entries: one ULP above 0.0 is a denormal around
            # 1e-45, which cannot be written in the plain decimal the .float
            # parser accepts, and which rounds back to 0 anyway -- an
            # equivalent mutant dressed up as a real one.
            if v != 0:
                mv = list(base)
                f = np.float32(v)
                nudged = float(np.nextafter(f, np.float32(f + 1)))
                mv[idx] = float(_fmt_float(nudged))
                if mv[idx] != v:
                    out.append(Mutant('constant', label, 'ulp_nudge',
                                      f'entry {idx}: {v} -> {mv[idx]!r}', mv))

        # swapped entries: two distinct positions with different values
        pairs = [(i, j) for i in range(n) for j in range(i + 1, n)
                 if base[i] != base[j]]
        rng.shuffle(pairs)
        for i, j in pairs[:4]:
            mv = list(base)
            mv[i], mv[j] = mv[j], mv[i]
            out.append(Mutant('constant', label, 'swap_entries',
                              f'entries {i} and {j} swapped', mv))

    for m in out:
        m.unitary = bool(is_unitary(to_matrix(m.values)))
    if per_gate is not None:
        kept, seen = [], {}
        for m in out:
            seen.setdefault(m.target, 0)
            if seen[m.target] < per_gate:
                kept.append(m)
                seen[m.target] += 1
        return kept
    return out


BRANCH_FLIPS = {'blt': 'bge', 'bge': 'blt', 'beq': 'bne', 'bne': 'beq',
                'ble': 'bgt', 'bgt': 'ble', 'bltu': 'bgeu', 'bgeu': 'bltu',
                'bgez': 'bltz', 'bltz': 'bgez', 'beqz': 'bnez', 'bnez': 'beqz'}

# The files code mutants are drawn from: by default the gate kernel and the
# measurement routine, the two the paper reports on. --code-files widens it.
CODE_FILES = ['gateFunctions.s', 'measure.s']


def code_mutants(rng, limit=None, files=None):
    """Branch flips, off-by-one immediates and swapped register operands in the
    gate kernel and the measurement routine (or in `files`)."""
    out = []
    for fname in files or CODE_FILES:
        path = os.path.join(ROOT, fname)
        with open(path, encoding='utf-8') as f:
            lines = f.read().split('\n')
        for i, line in enumerate(lines):
            code = line.split('#')[0].strip()
            if not code:
                continue
            head = code.split()[0] if code.split() else ''

            if head in BRANCH_FLIPS:
                new = line.replace(head, BRANCH_FLIPS[head], 1)
                out.append(Mutant('code', fname, 'branch_flip',
                                  f'line {i + 1}: {head} -> {BRANCH_FLIPS[head]}',
                                  file_edit=(fname, i, new)))

            m = re.match(r'^(\s*)(addi|li)\s+(\w+)\s*,\s*(\w+)\s*,\s*(-?\d+)\s*$',
                         code)
            if m:
                val = int(m.group(5))
                for delta in (1, -1):
                    new_code = f'{m.group(2)} {m.group(3)}, {m.group(4)}, {val + delta}'
                    if m.group(2) == 'li':
                        new_code = f'li {m.group(3)}, {val + delta}' \
                            if m.group(4).lstrip('-').isdigit() else new_code
                    new = line.replace(code, new_code, 1)
                    out.append(Mutant('code', fname, 'off_by_one',
                                      f'line {i + 1}: {code} -> {new_code}',
                                      file_edit=(fname, i, new)))

            # Only non-commutative operations. Swapping the operands of add,
            # mul, and, or, xor -- or of fadd.s and fmul.s, which are
            # commutative in IEEE-754 -- produces a mutant that is provably
            # equivalent to the original. Generating those inflates the
            # survivor count with mutants nothing *could* kill, which would
            # make the test suite look worse than it is.
            m = re.match(r'^(sub|slt|sltu|fsub\.s|fdiv\.s|div|rem)'
                         r'\s+(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*$', code)
            if m and m.group(3) != m.group(4):
                new_code = f'{m.group(1)} {m.group(2)}, {m.group(4)}, {m.group(3)}'
                new = line.replace(code, new_code, 1)
                out.append(Mutant('code', fname, 'swap_operands',
                                  f'line {i + 1}: {code} -> {new_code}',
                                  file_edit=(fname, i, new)))
    rng.shuffle(out)
    return out[:limit] if limit is not None else out


# ---------------------------------------------------------------------------
# Test corpus
# ---------------------------------------------------------------------------

def load_corpus():
    """Every test program, with the metadata run_tests uses."""
    import glob
    corpus = []
    for path in sorted(glob.glob(os.path.join(TEST_DIR, '*.dsl'))):
        meta, body = run_tests.read_program(path)
        text = '\n'.join(body)
        corpus.append({
            'path': path,
            'name': meta.get('name', os.path.basename(path)),
            'meta': meta,
            'body': body,
            'gates': set(re.findall(r'=\s*([A-Za-z]+\d*)\s*$', text, re.M)),
            'statistical': 'expect_freq' in meta or bool(
                re.search(r'^\s*noise\s', text, re.M)),
            # A program with no explicit-amplitude declaration starts every
            # register in |0...0>.
            'explicit_amps': bool(re.search(r'^\s*qubit\s+\w+\s*=', text, re.M)),
            'error': 'expect_error' in meta,
        })
    return corpus


ZERO_INIT_ONLY = False      # set by --zero-init-only

DECL_EXPLICIT_RE = re.compile(r'^(\s*)qubit\s+(\w)\s*=\s*\[(.*)\]\s*$')


def zero_init_rewrite(corpus, workdir):
    """The same programs, with every explicit-amplitude declaration replaced by
    a |0...0> declaration of the same size.

    This is the controlled form of --zero-init-only. That flag drops the
    programs that declare explicit amplitudes, which changes two things at once
    -- which inputs the corpus uses, and how many programs (and which gates in
    which orders) it runs. Rewriting instead keeps every program and every
    statement, and changes only the state each register starts in, so any
    difference in the kill rate is down to the inputs alone. Rewritten files
    go to `workdir`, so the RARS confirmations run the rewritten programs.
    """
    out = []
    for p in corpus:
        body = []
        changed = False
        for line in p['body']:
            m = DECL_EXPLICIT_RE.match(line.split('#')[0])
            if m:
                pairs = m.group(3).count('(')
                n = max(1, pairs.bit_length() - 1)
                body.append(f'{m.group(1)}qubit {m.group(2)}[{n}]')
                changed = True
            else:
                body.append(line)
        q = dict(p)
        q['body'] = body
        q['explicit_amps'] = False
        if changed:
            path = os.path.join(workdir, os.path.basename(p['path']))
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                for key, value in p['meta'].items():
                    f.write(f'# {key}: {value}\n')
                f.write('\n'.join(body) + '\n')
            q['path'] = path
        out.append(q)
    return out


def programs_using(corpus, gate):
    """Programs that apply `gate`. A constant mutation to that gate cannot
    change the behaviour of any other program, so this restriction is sound.

    Under --zero-init-only the corpus is further restricted to programs whose
    registers all start in |0...0>, i.e. those with no explicit-amplitude
    declaration. This is the controlled experiment behind the paper's central
    claim: the difference between that corpus and the full one is precisely
    whether the inputs place weight at the indices where a wrong matrix
    differs from the right one.
    """
    progs = [p for p in corpus if gate in p['gates'] and not p['error']]
    if ZERO_INIT_ONLY:
        progs = [p for p in progs if not p['explicit_amps']]
    return progs


def oracle_events(body, gates1=None, gates2=None):
    """Run the oracle, optionally with substituted gate tables."""
    saved1, saved2 = None, None
    if gates1 is not None:
        saved1 = dict(reference_sim.GATES1)
        reference_sim.GATES1.clear()
        reference_sim.GATES1.update(gates1)
    if gates2 is not None:
        saved2 = dict(reference_sim.GATES2)
        reference_sim.GATES2.clear()
        reference_sim.GATES2.update(gates2)
    try:
        interp = Interpreter().run(body)
        return [e[1] for e in interp.events if e[0] == 'print']
    except Exception:
        return None
    finally:
        if saved1 is not None:
            reference_sim.GATES1.clear()
            reference_sim.GATES1.update(saved1)
        if saved2 is not None:
            reference_sim.GATES2.clear()
            reference_sim.GATES2.update(saved2)


# ---------------------------------------------------------------------------
# Stage 1: oracle screen
# ---------------------------------------------------------------------------

def stage1(mutant, corpus, baseline):
    """Max deviation any test program's printed output shows under the mutated
    matrix, in exact arithmetic. Returns (max_dev, needs_rars_names).

    A deviation of 0 across every program that uses the gate means no
    print-comparison in the suite could possibly distinguish the mutant. That
    is sound in the survival direction, which is the direction that matters.
    """
    gate = mutant.gate
    if gate is None:
        return None, []
    progs = programs_using(corpus, gate)
    if not progs:
        return 0.0, []

    mat = to_matrix(mutant.values)
    g1 = dict(reference_sim.GATES1)
    g2 = dict(reference_sim.GATES2)
    if gate in g1:
        g1[gate] = mat
    else:
        g2[gate] = mat

    worst = 0.0
    statistical = []
    for p in progs:
        # Programs judged on statistics never have their prints compared, so a
        # zero deviation here says nothing about them.
        if p['statistical']:
            statistical.append(p['name'])
            continue
        base = baseline.get(p['path'])
        got = oracle_events(p['body'], g1, g2)
        if base is None or got is None:
            if (base is None) != (got is None):
                return float('inf'), statistical    # one crashed, the other did not
            continue
        if len(base) != len(got):
            return float('inf'), statistical
        for a, b in zip(base, got):
            if a.shape != b.shape:
                return float('inf'), statistical
            worst = max(worst, float(np.max(np.abs(a - b))) if a.size else 0.0)
    return worst, statistical


# ---------------------------------------------------------------------------
# Layer: static audit
# ---------------------------------------------------------------------------

def audit_kills(mutant, base_text, workdir):
    """Does check_gate_data.py catch it? For constant mutants this is exact and
    costs nothing."""
    if mutant.kind != 'constant':
        return False
    path = os.path.join(workdir, 'audit_main.s')
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(write_block(base_text, mutant.target, mutant.values))
    return bool(check_gate_data.check(path))


# ---------------------------------------------------------------------------
# Layer: properties
# ---------------------------------------------------------------------------

_PROPERTY_CASES = None


def property_cases():
    global _PROPERTY_CASES
    if _PROPERTY_CASES is None:
        # Fixed seed and size so the property layer is identical for every
        # mutant and reproducible by a reviewer.
        _PROPERTY_CASES = properties.build(seed=0, count=40, max_qubits=3)
    return _PROPERTY_CASES


def property_kills(mutant):
    """Does the Phase C property suite catch it, in the oracle engine?"""
    if mutant.kind != 'constant':
        return None
    gate = mutant.gate
    mat = to_matrix(mutant.values)
    saved1 = dict(reference_sim.GATES1)
    saved2 = dict(reference_sim.GATES2)
    try:
        if gate in reference_sim.GATES1:
            reference_sim.GATES1[gate] = mat
        else:
            reference_sim.GATES2[gate] = mat
        failures = properties.run(property_cases(), 'oracle', verbose=False,
                                  stop_after=1)
        return bool(failures)
    finally:
        reference_sim.GATES1.clear()
        reference_sim.GATES1.update(saved1)
        reference_sim.GATES2.clear()
        reference_sim.GATES2.update(saved2)


# ---------------------------------------------------------------------------
# Stage 2/3: confirmation under RARS with a genuinely mutated assembly
# ---------------------------------------------------------------------------

class Workspace:
    """A copy of the assembly that can be mutated and run under RARS."""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix='quasm_mut_')
        for name in os.listdir(ROOT):
            if name.endswith('.s'):
                shutil.copy(os.path.join(ROOT, name), self.dir)
        self.main = os.path.join(self.dir, 'main.s')
        with open(MAIN_S, encoding='utf-8') as f:
            self.base_main = f.read()
        self.base_files = {}
        for name in CODE_FILES:
            with open(os.path.join(ROOT, name), encoding='utf-8') as f:
                self.base_files[name] = f.read()

    def apply(self, mutant):
        self.reset()
        if mutant.kind == 'constant':
            with open(self.main, 'w', encoding='utf-8', newline='\n') as f:
                f.write(write_block(self.base_main, mutant.target, mutant.values))
        else:
            fname, i, new_line = mutant.file_edit
            lines = self.base_files[fname].split('\n')
            lines[i] = new_line
            with open(os.path.join(self.dir, fname), 'w',
                      encoding='utf-8', newline='\n') as f:
                f.write('\n'.join(lines))

    def reset(self):
        with open(self.main, 'w', encoding='utf-8', newline='\n') as f:
            f.write(self.base_main)
        for name, text in self.base_files.items():
            with open(os.path.join(self.dir, name), 'w',
                      encoding='utf-8', newline='\n') as f:
                f.write(text)

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def rars_kills(workspace, mutant, progs, verbose=False):
    """Run the real harness against a genuinely mutated assembly.

    Uses run_tests.run_test, the same checks CI runs -- not a model of them --
    so what comes back is an implementation-level result. Stops at the first
    kill, since one failing test is enough.
    """
    workspace.apply(mutant)
    saved = run_tests.MAIN_S
    run_tests.MAIN_S = workspace.main
    try:
        for p in progs:
            try:
                name, ok, msg = run_tests.run_test(p['path'])
            except Exception as exc:
                return True, f'{p["name"]}: harness error {exc}'
            if not ok:
                return True, f'{p["name"]}: {msg[:120]}'
        return False, ''
    finally:
        run_tests.MAIN_S = saved
        workspace.reset()


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def evaluate(mutants, corpus, baseline, base_text, workdir, workspace,
             max_rars=None, verbose=True, screen_only=False):
    """Run every layer over every mutant, with RARS confirmation where the
    screen cannot decide.

    `screen_only` decides everything from the Stage-1 oracle screen, with no
    RARS at all. That is a *proxy* result: sound in the survival direction but
    not an implementation-level measurement, and it must be labelled as such
    wherever it is reported.
    """
    rars_budget = max_rars if max_rars is not None else 10 ** 9
    rars_used = 0

    for i, m in enumerate(mutants):
        m.audit_kill = audit_kills(m, base_text, workdir)
        m.property_kill = property_kills(m)

        if m.kind == 'constant':
            dev, statistical = stage1(m, corpus, baseline)
            m.stage1_dev = dev
            progs = programs_using(corpus, m.gate)

            if dev == float('inf'):
                m.behavioural_kill, m.confirmed_by = True, 'stage1'
            elif dev >= NEAR_BAND:
                # Killed by a wide margin in a print-compared program: float32
                # cannot rescue it, and one failing test is a kill whatever the
                # statistical programs would say. (An earlier version sent
                # these to RARS whenever any statistical program also used the
                # gate, which cost a RARS run per mutant and decided nothing.)
                m.behavioural_kill, m.confirmed_by = True, 'stage1'
            elif screen_only:
                # Proxy decision: no RARS available. Sound in the survival
                # direction, but not an implementation-level result.
                m.behavioural_kill = dev >= TOLERANCE
                m.confirmed_by = 'stage1-proxy'
            else:
                # Survivor, near-tolerance kill, or a gate used only by
                # statistically judged programs -- all need the real thing.
                if rars_used < rars_budget and progs:
                    killed, why = rars_kills(workspace, m, progs)
                    m.behavioural_kill, m.confirmed_by = killed, 'rars'
                    m.detail_rars = why
                    rars_used += 1
                elif not progs:
                    m.behavioural_kill, m.confirmed_by = False, 'no-test-uses-gate'
                else:
                    m.behavioural_kill, m.confirmed_by = None, 'rars-budget-exhausted'
        else:
            # Code mutants cannot be screened in the oracle -- the oracle does
            # not run the assembly. Straight to RARS, against every program in
            # the corpus (an earlier version ran only the first 25 in file
            # order, which left the whole measurement section of the corpus
            # out of the code-mutant results).
            if rars_used < rars_budget:
                # Error tests included: a code mutant can make the interpreter
                # accept what it should reject, which only an error test sees.
                # (Constant mutants cannot change error handling, so they skip
                # them; code mutants used to as well, which hid such kills.)
                killed, why = rars_kills(workspace, m, list(corpus))
                m.behavioural_kill, m.confirmed_by = killed, 'rars'
                m.detail_rars = why
                rars_used += 1
            else:
                m.behavioural_kill, m.confirmed_by = None, 'rars-budget-exhausted'

        if verbose:
            print(f'[{i + 1}/{len(mutants)}] {m} | unitary={m.unitary} '
                  f'dev={m.stage1_dev if m.stage1_dev is None else f"{m.stage1_dev:.2e}"} '
                  f'audit={m.audit_kill} behav={m.behavioural_kill} '
                  f'prop={m.property_kill} ({m.confirmed_by})')
    return rars_used


def report(mutants, rars_used):
    decided = [m for m in mutants if m.behavioural_kill is not None]
    const = [m for m in decided if m.kind == 'constant']
    code = [m for m in decided if m.kind == 'code']
    unit = [m for m in const if m.unitary]
    nonunit = [m for m in const if not m.unitary]

    def pct(a, b):
        return f'{100.0 * a / b:5.1f}%' if b else '    --'

    def row(label, group):
        if not group:
            return
        b = sum(1 for m in group if m.behavioural_kill)
        p = sum(1 for m in group if m.behavioural_kill or m.property_kill)
        a = sum(1 for m in group if m.behavioural_kill or m.property_kill
                or m.audit_kill)
        none = sum(1 for m in group if not (m.behavioural_kill or m.property_kill
                                            or m.audit_kill))
        print(f'{label:34} {len(group):5} {b:6} {pct(b, len(group))} '
              f'{p:7} {pct(p, len(group))} {a:7} {pct(a, len(group))} {none:6}')

    print()
    print('=' * 104)
    print('MUTATION SCORES')
    print('=' * 104)
    print(f'{"":34} {"total":>5} {"behav":>6} {"":>6} '
          f'{"+props":>7} {"":>6} {"+audit":>7} {"":>6} {"alive":>6}')
    # A ULP nudge moves a constant by one float32 unit in the last place. It is
    # below the suite's 1e-4 tolerance *by construction* -- the paper argues
    # exactly that, when it shows the tolerance sits three orders of magnitude
    # above observed rounding. Counting such mutants as "survivors" would make
    # the behavioural suite look far worse than it is, and would flatter the
    # paper's own thesis with an artifact. They are reported, and excluded from
    # the headline.
    ulp = [m for m in const if m.operator == 'ulp_nudge']
    meaningful = [m for m in const if m.operator != 'ulp_nudge']
    unit_meaningful = [m for m in meaningful if m.unitary]

    row('constant, unitary-preserving', unit)
    row('  of which ULP nudges', ulp)
    row('  of which meaningful', unit_meaningful)
    row('constant, non-unitary', nonunit)
    row('constant, all', const)
    row('constant, excluding ULP nudges', meaningful)
    row('code (kernel + measurement)', code)
    row('ALL', decided)
    print('=' * 104)

    print()
    print('By operator (behavioural layer only):')
    ops = {}
    for m in decided:
        ops.setdefault((m.kind, m.operator), [0, 0, 0])
        ops[(m.kind, m.operator)][0] += 1
        ops[(m.kind, m.operator)][1] += bool(m.behavioural_kill)
        ops[(m.kind, m.operator)][2] += bool(m.behavioural_kill or m.property_kill
                                             or m.audit_kill)
    print(f'  {"operator":28} {"total":>6} {"behav":>7} {"any layer":>10}')
    for (kind, op), (t, b, a) in sorted(ops.items()):
        print(f'  {kind + "/" + op:28} {t:6} {b:6} {pct(b, t)} {a:6} {pct(a, t)}')
    print()
    print('Columns are cumulative layers, in the order a developer would meet them:')
    print('  behav   killed by the behavioural suite in tests/programs (RARS-confirmed)')
    print('  +props  ...or by the Phase C property suite')
    print('  +audit  ...or by the static gate-data audit')
    print('  alive   survives every layer')
    print()
    print(f'RARS confirmations run: {rars_used}')
    undecided = [m for m in mutants if m.behavioural_kill is None]
    if undecided:
        print(f'UNDECIDED (RARS budget exhausted): {len(undecided)} -- '
              f'these are excluded from the scores above, not counted as survivors')

    alive = [m for m in decided if not (m.behavioural_kill or m.property_kill
                                        or m.audit_kill)]
    if alive:
        print()
        print(f'Mutants surviving every layer ({len(alive)}):')
        for m in alive[:25]:
            print(f'  {m} (unitary={m.unitary}, '
                  f'dev={m.stage1_dev:.2e})' if m.stage1_dev is not None
                  else f'  {m}')
    return alive


# ---------------------------------------------------------------------------
# Ground truth: the paper's three defects
# ---------------------------------------------------------------------------

def historical(corpus, baseline, base_text, workdir, workspace, use_rars=True):
    """Reproduce the three shipped defects as seeded mutants and check the tool
    reports the killing layer the paper claims for each."""
    blocks = read_blocks(base_text)

    # Defect 1: controlled-Z shipped as diag(1,1,-1,-1) = Z tensor I.
    cz = [1, 0, 0, 0, 0, 0, 0, 0,
          0, 0, 1, 0, 0, 0, 0, 0,
          0, 0, 0, 0, -1, 0, 0, 0,
          0, 0, 0, 0, 0, 0, -1, 0]
    d1 = Mutant('constant', 'CZgate', 'historical',
                'controlled-Z as diag(1,1,-1,-1), i.e. Z tensor I', cz)

    # Defect 2: sqrt(X) with a 0.707 normalisation instead of 0.5.
    sn = [0.70710678 if abs(v) == 0.5 else v for v in blocks['SNgate'][2]]
    sn = [np.sign(v) * 0.70710678 if abs(v) == 0.5 else v
          for v in blocks['SNgate'][2]]
    d2 = Mutant('constant', 'SNgate', 'historical',
                'sqrt(X) carrying 0.707 instead of 0.5 (not unitary)', sn)

    for m in (d1, d2):
        m.unitary = bool(is_unitary(to_matrix(m.values)))

    # IMPORTANT -- read before changing these expectations.
    #
    # The paper says the behavioural suite did not detect these defects. That is
    # true of the suite *as it stood when they were found*: 40 programs, at
    # commit 2e8d7a4^. It is NOT true of the suite as it stands now. After the
    # audit found these two, the corpus was deliberately strengthened to cover
    # every gate "on inputs with all amplitudes distinct and nonzero" (Sec. 7),
    # and that is precisely the property that makes a wrong matrix entry
    # visible. The current suite therefore kills both.
    #
    # That is not a contradiction; it is the paper's own thesis playing out. The
    # claim is not that behavioural testing is incapable, it is that a test only
    # distinguishes two matrices where its inputs place weight at an index where
    # they differ -- and once the inputs do, behavioural testing works fine.
    #
    # So the expectation below is KILLS for the current suite, and the
    # historical claim is verified separately and reproducibly by
    # --historical-suite, which checks out the 40-test corpus and shows it green
    # with both defects present.
    expectations = {
        'CZgate': dict(behavioural=True, audit=True,
                       note='paper: survived four dedicated CZ tests *of the '
                            'then-current 40-program suite*; found by the static '
                            'audit. The present suite kills it, '
                            'because the corpus was later strengthened with '
                            'asymmetric inputs. See --historical-suite.'),
        'SNgate': dict(behavioural=True, audit=True,
                       note='paper: not unitary at all; the 40-program suite had '
                            'not noticed; found by the audit. The present suite '
                            'kills it. See --historical-suite.'),
    }

    print('GROUND TRUTH: the paper\'s three shipped defects, re-run as mutants')
    print('(expectations are for the CURRENT suite; the historical')
    print(' 40-program claim is checked by --historical-suite)')
    print('=' * 104)
    problems = []
    for m in (d1, d2):
        m.audit_kill = audit_kills(m, base_text, workdir)
        m.property_kill = property_kills(m)
        dev, statistical = stage1(m, corpus, baseline)
        m.stage1_dev = dev
        progs = programs_using(corpus, m.gate)
        if use_rars:
            killed, why = rars_kills(workspace, m, progs)
            m.behavioural_kill, m.confirmed_by = killed, 'rars'
        else:
            m.behavioural_kill = dev >= TOLERANCE
            m.confirmed_by = 'stage1'

        exp = expectations[m.target]
        ok_b = (m.behavioural_kill == exp['behavioural'])
        ok_a = (m.audit_kill == exp['audit'])
        print(f'{m.target}: {m.detail}')
        print(f'  unitary            : {m.unitary}')
        print(f'  tests using gate   : {len(progs)}')
        print(f'  stage-1 deviation  : {dev:.3e}')
        print(f'  behavioural suite  : {"KILLS" if m.behavioural_kill else "MISSES"}'
              f'   (expected {"KILLS" if exp["behavioural"] else "MISSES"}) '
              f'{"OK" if ok_b else "MISMATCH"}   [{m.confirmed_by}]')
        print(f'  static gate audit  : {"KILLS" if m.audit_kill else "MISSES"}'
              f'   (expected {"KILLS" if exp["audit"] else "MISSES"}) '
              f'{"OK" if ok_a else "MISMATCH"}')
        print(f'  property suite     : {"KILLS" if m.property_kill else "MISSES"}')
        print(f'  {exp["note"]}')
        print()
        if not ok_b:
            problems.append(f'{m.target}: behavioural layer disagreed with the paper')
        if not ok_a:
            problems.append(f'{m.target}: audit layer disagreed with the paper')

    # Defect 3 is not a constant mutation -- it is a semantic bug in the
    # measurement routine (P(0) computed as 1 - P(1)). It is reproduced, and
    # shown to be caught by the property layer and by nothing else, in
    # properties.py --self-test, whose `born` case injects exactly that defect.
    print('Born-rule defect (defect 3): not a constant mutation -- a semantic')
    print('defect in the measurement routine. Reproduced as a seeded fault in')
    print('properties.py --self-test (`born`), where it is caught by the')
    print('property layer and, per the paper, by none of the original three.')
    print()
    return problems


# ---------------------------------------------------------------------------
# The historical claim, verified against the suite that actually existed
# ---------------------------------------------------------------------------

PREFIX_COMMIT = '2e8d7a4'      # "Fix two more wrong gate matrices, found by a
                               #  static unitarity audit"


def historical_suite(keep=False):
    """Check out the test corpus as it stood *before* the two gate defects were
    fixed, and run it with the defects still in place.

    This is the paper's central empirical claim, and it is the one thing the
    mutation scores above cannot show, because the corpus they run against is
    the strengthened one. At commit 2e8d7a4^ the shipped assembly contains both
    wrong matrices and the suite is 40 programs. If that suite passes green,
    behavioural testing demonstrably did not detect them -- not as an anecdote,
    but as a re-runnable experiment.
    """
    import subprocess

    workdir = tempfile.mkdtemp(prefix='quasm_hist_')
    try:
        print(f'checking out the tree at {PREFIX_COMMIT}^ '
              f'(before the gate-matrix fixes)...')
        archive = subprocess.run(['git', 'archive', f'{PREFIX_COMMIT}^'],
                                 cwd=ROOT, capture_output=True)
        if archive.returncode != 0:
            print(f'git archive failed: {archive.stderr.decode()[:200]}',
                  file=sys.stderr)
            return ['could not check out the historical tree']
        tar = subprocess.run(['tar', '-x', '-C', workdir], input=archive.stdout,
                             capture_output=True)
        if tar.returncode != 0:
            print(f'tar failed: {tar.stderr.decode()[:200]}', file=sys.stderr)
            return ['could not extract the historical tree']

        shutil.copy(os.path.join(ROOT, 'tools', 'rars1_6.jar'),
                    os.path.join(workdir, 'tools'))

        hist_main = os.path.join(workdir, 'main.s')
        with open(hist_main, encoding='utf-8') as f:
            hist_text = f.read()

        problems = []
        # Confirm both defects really are present in that tree, so a green run
        # means what we say it means.
        checks = [
            ('sqrt(X) with the 0.707 normalisation',
             '0.707,0.707,0.707,-0.707'),
            ('controlled-Z encoding Z tensor I', 'CZgate3: .float 0,0,0,0,-1,0,0,0'),
        ]
        for label, needle in checks:
            present = needle in hist_text
            print(f'  defect present: {label}: {present}')
            if not present:
                problems.append(f'expected the {label} defect in {PREFIX_COMMIT}^')

        n_tests = len([f for f in os.listdir(os.path.join(workdir, 'tests',
                                                          'programs'))
                       if f.endswith('.dsl')])
        print(f'  suite size at that commit: {n_tests} programs')
        print('  running it (this is the suite that shipped with the defects)...')

        proc = subprocess.run([sys.executable, os.path.join('tools', 'run_tests.py')],
                              cwd=workdir, capture_output=True, text=True,
                              timeout=3600)
        tail = proc.stdout.strip().split('\n')[-3:]
        for line in tail:
            print(f'    {line}')

        passed = proc.returncode == 0
        print()
        if passed:
            print(f'  RESULT: the {n_tests}-program suite passes GREEN with both '
                  f'defects present.')
            print('  Behavioural testing did not detect them. This is the claim, '
                  'verified.')
        else:
            print('  RESULT: the historical suite FAILED, which contradicts the '
                  'paper.')
            problems.append('the historical suite did not pass with the defects '
                            'present')

        # And the audit, applied to that same tree, does flag the sqrt(X).
        audit = check_gate_data.check(hist_main)
        sn = [p for p in audit if p.startswith('SNgate')]
        print(f'  the current static audit, run against that same tree, reports '
              f'{len(audit)} problem(s), including SNgate: {bool(sn)}')
        print('  (the CZ defect sat under a different label and matrix layout in '
              'that revision -- CZgate3 rather than CZgate -- so the *current* '
              'audit parser does not reach it; the audit written at the time did, '
              'which is what the commit message records.)')
        return problems
    finally:
        if keep:
            print(f'  tree left at {workdir}')
        else:
            shutil.rmtree(workdir, ignore_errors=True)


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--list', action='store_true', help='enumerate mutants and exit')
    ap.add_argument('--stage1', action='store_true',
                    help='oracle screen and cheap layers only; no RARS')
    ap.add_argument('--full', action='store_true', help='all stages')
    ap.add_argument('--historical', action='store_true',
                    help='ground-truth check against the paper\'s three defects')
    ap.add_argument('--operators', nargs='*',
                    help='restrict to these mutation operators, e.g. ulp_nudge')
    ap.add_argument('--corpus', default=None,
                    help='directory of .dsl programs to use instead of '
                         'tests/programs, e.g. an earlier corpus to compare with')
    ap.add_argument('--match', nargs='*',
                    help='keep only mutants whose description contains one of '
                         'these, e.g. "measure.s/off_by_one: line 70"')
    ap.add_argument('--zero-init-only', action='store_true',
                    help='restrict the behavioural corpus to programs whose '
                         'registers all start in |0...0> (drops programs)')
    ap.add_argument('--zero-init-rewrite', action='store_true',
                    help='keep every program but start every register in '
                         '|0...0> (changes only the inputs)')
    ap.add_argument('--historical-suite', action='store_true',
                    help='check out the 40-program suite from before the gate '
                         'fixes and show it green with the defects present')
    ap.add_argument('--max-rars', type=int, default=None,
                    help='cap RARS confirmations (each is minutes)')
    ap.add_argument('--code-mutants', type=int, default=30)
    ap.add_argument('--all-code', action='store_true',
                    help='every code mutant, not a random --code-mutants of them')
    ap.add_argument('--code-files', nargs='*', default=None,
                    help=f'assembly files to draw code mutants from '
                         f'(default {" ".join(CODE_FILES)})')
    ap.add_argument('--per-gate', type=int, default=None,
                    help='cap constant mutants per gate')
    args = ap.parse_args()

    if args.historical_suite:
        problems = historical_suite()
        if problems:
            print()
            for p in problems:
                print(f'[FAIL] {p}')
            return 1
        return 0

    global ZERO_INIT_ONLY
    ZERO_INIT_ONLY = args.zero_init_only

    rng = np.random.default_rng(args.seed)
    with open(MAIN_S, encoding='utf-8') as f:
        base_text = f.read()

    global TEST_DIR
    if args.corpus:
        TEST_DIR = os.path.abspath(args.corpus)
        print(f'--corpus: programs from {TEST_DIR}')
    corpus = load_corpus()
    rewrite_dir = None
    if args.zero_init_rewrite:
        rewrite_dir = tempfile.mkdtemp(prefix='quasm_zinit_')
        corpus = zero_init_rewrite(corpus, rewrite_dir)
        print('--zero-init-rewrite: every explicit-amplitude declaration '
              'replaced by |0...0> of the same size; no program dropped')
    if ZERO_INIT_ONLY:
        n_expl = sum(1 for p in corpus if p['explicit_amps'] and not p['error'])
        print(f'--zero-init-only: excluding {n_expl} programs that declare '
              f'explicit amplitudes')
    print(f'{len(corpus)} test programs '
          f'({sum(1 for p in corpus if p["error"])} error paths, '
          f'{sum(1 for p in corpus if p["statistical"])} statistical)')

    mutants = constant_mutants(base_text, rng, per_gate=args.per_gate)
    if not args.historical:
        mutants += code_mutants(rng, limit=None if args.all_code else args.code_mutants,
                                files=args.code_files)
    if args.operators:
        mutants = [m for m in mutants if m.operator in args.operators]
    if args.match:
        mutants = [m for m in mutants if any(t in str(m) for t in args.match)]
    print(f'{len(mutants)} mutants '
          f'({sum(1 for m in mutants if m.kind == "constant")} constant, '
          f'{sum(1 for m in mutants if m.kind == "code")} code)')
    u = sum(1 for m in mutants if m.kind == 'constant' and m.unitary)
    print(f'  of the constant mutants, {u} are unitary-preserving '
          f'(the hard class) and '
          f'{sum(1 for m in mutants if m.kind == "constant") - u} are not')

    if args.list:
        for m in mutants:
            print(f'  {m.kind:9} {m} (unitary={m.unitary})')
        return 0

    print('computing oracle baseline...')
    baseline = {}
    for p in corpus:
        if not p['error']:
            baseline[p['path']] = oracle_events(p['body'])

    workdir = tempfile.mkdtemp(prefix='quasm_audit_')
    workspace = Workspace()
    try:
        if args.historical:
            problems = historical(corpus, baseline, base_text, workdir, workspace,
                                  use_rars=not args.stage1)
            if problems:
                for p in problems:
                    print(f'[FAIL] {p}')
                return 1
            print('ground truth reproduced: the tool assigns each shipped defect '
                  'to the layer the paper says caught it')
            return 0

        max_rars = 0 if args.stage1 else args.max_rars
        if args.stage1:
            # No RARS: decide from the screen alone, and say so.
            for m in mutants:
                if m.kind == 'code':
                    m.behavioural_kill = None
            print('stage-1 only: constant mutants decided by the oracle screen, '
                  'code mutants left undecided (they need RARS)')
        rars_used = evaluate(mutants, corpus, baseline, base_text, workdir,
                             workspace, max_rars=max_rars,
                             screen_only=args.stage1)
        report(mutants, rars_used)
        return 0
    finally:
        workspace.cleanup()
        shutil.rmtree(workdir, ignore_errors=True)
        if rewrite_dir:
            shutil.rmtree(rewrite_dir, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
