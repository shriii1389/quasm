"""Independent NumPy reference oracle for the QuAsm DSL.

Reimplements the language's semantics from scratch using exact complex math
(numpy complex128), deliberately not derived from the RISC-V assembly in
../*.s. Where the assembly walks amplitude indices bit by bit, this applies
gates by reshaping the state to an n-dimensional (2,2,...,2) tensor and
contracting -- a different enough route that the two agreeing is real signal.

Convention, shared with the assembly: an n-qubit register is 2^n amplitudes
in basis order |q0 q1 ... qn-1>, so qubit 0 is the *most* significant bit of
an amplitude index.

Grammar:
    qubit <v>[<n>]                      -- n-qubit register set to |0..0>
    qubit <v> = [(re,im),(re,im),...]   -- explicit amplitudes, 2^n of them
    qubitop1 <v>[<k>] = <gate>
    qubitop2 <v>[<c>],<v>[<t>] = <gate>
    measure <v>[<k>] [-> <c>]           -- one qubit; collapses and renormalises
    measure <v> [-> <c>]                -- whole register; collapses to a basis state
    seed <n>
    set <c> = <n>                       -- classical variable, integer valued
    print(<v>)
    repeat <n> ... endrepeat            -- runs the body n times; nests
    if <x> <op> <y> ... else if ... else ... endif
    end
    # comments, to end of line, and blank lines

What is checked, and when, matches the assembly's streaming interpreter:

  - The block structure of the whole program, up to the top-level `end`, is
    checked before anything runs -- including the parts that never run. So is
    the shape of every line that opens or closes a block, and the length of
    every line. The program must end with a top-level `end`.
  - A statement, and a condition, is checked only when it runs.

Measurement is the one place the oracle cannot predict the assembly, since the
two draw from different random streams. Instead the harness replays the
outcomes RARS actually reported (`forced_outcomes`), and the oracle checks each
one was possible and computes the collapsed state it implies -- so the
probabilities, the collapse and the renormalisation are all still verified
against independent math. `seed` is accepted and ignored under replay; it only
matters when this module samples on its own.
"""
import re
from decimal import Decimal

import numpy as np

INV_SQRT2 = 1.0 / np.sqrt(2.0)

MAX_QUBITS = 6

GATES1 = {
    'H': INV_SQRT2 * np.array([[1, 1], [1, -1]], dtype=complex),
    'I': np.eye(2, dtype=complex),
    'X': np.array([[0, 1], [1, 0]], dtype=complex),
    'Y': np.array([[0, -1j], [1j, 0]], dtype=complex),
    'Z': np.array([[1, 0], [0, -1]], dtype=complex),
    'S': np.array([[1, 0], [0, 1j]], dtype=complex),
    'T': np.array([[1, 0], [0, np.exp(1j * np.pi / 4)]], dtype=complex),
    # SN = sqrt(NOT), the principal square root of X: SN @ SN == X.
    'SN': 0.5 * np.array([[1 + 1j, 1 - 1j], [1 - 1j, 1 + 1j]], dtype=complex),
    'SDG': np.array([[1, 0], [0, -1j]], dtype=complex),
    'TDG': np.array([[1, 0], [0, np.exp(-1j * np.pi / 4)]], dtype=complex),
}

_Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
_Z = np.array([[1, 0], [0, -1]], dtype=complex)


def _controlled(u):
    m = np.eye(4, dtype=complex)
    m[2:, 2:] = u
    return m


# Two-qubit gates, written in the |control target> basis. The DSL names the
# control and target qubits explicitly, so which way round they sit in the
# register is the caller's business, not the matrix's.
GATES2 = {
    'CN': np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]], dtype=complex),
    'SW': np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], dtype=complex),
    'CY': _controlled(_Y),
    'CZ': _controlled(_Z),
}

# Controlled phase, diag(1, 1, 1, exp(2*pi*i / 2^k)). CP1 == CZ, CP2 is
# controlled-S, CP3 is controlled-T. The QFT needs exactly this family.
for _k in range(1, MAX_QUBITS + 1):
    GATES2[f'CP{_k}'] = _controlled(
        np.array([[1, 0], [0, np.exp(2j * np.pi / 2 ** _k)]], dtype=complex))


class DslError(Exception):
    """Raised for any program the DSL itself would reject."""


# A qubit register is named by one letter, digit or underscore; a classical
# variable by one letter. re.ASCII keeps \d and the like to what the
# assembly, which reads bytes, can see.
REG = r'([A-Za-z0-9_])'
CVAR = r'([A-Za-z])'
# A decimal literal: optional '-', digits with an optional point, optional
# exponent. The assembly's parse_float accepts exactly this.
NUM = r'-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?'
_PAIR = rf'\(\s*{NUM}\s*,\s*{NUM}\s*\)'

QUBIT_SIZED_RE = re.compile(rf'^qubit\s+{REG}\s*\[\s*(\d+)\s*\]$', re.A)
QUBIT_AMPS_RE = re.compile(rf'^qubit\s+{REG}\s*=\s*\[(.*)\]$', re.A)
AMP_LIST_RE = re.compile(rf'^\s*{_PAIR}(?:\s*,\s*{_PAIR})*\s*$', re.A)
AMP_RE = re.compile(rf'\(\s*({NUM})\s*,\s*({NUM})\s*\)', re.A)
QUBITOP1_RE = re.compile(rf'^qubitop1\s+{REG}\s*\[\s*(\d+)\s*\]\s*=\s*(\S+)$', re.A)
QUBITOP2_RE = re.compile(
    rf'^qubitop2\s+{REG}\s*\[\s*(\d+)\s*\]\s*,\s*{REG}\s*\[\s*(\d+)\s*\]\s*=\s*(\S+)$',
    re.A)
PRINT_RE = re.compile(rf'^print\(\s*{REG}\s*\)$', re.A)
# The optional `-> <c>` tail keeps the outcome in a classical variable.
MEASURE1_RE = re.compile(rf'^measure\s+{REG}\s*\[\s*(\d+)\s*\]\s*(?:->\s*{CVAR}\s*)?$', re.A)
MEASUREALL_RE = re.compile(rf'^measure\s+{REG}\s*(?:->\s*{CVAR}\s*)?$', re.A)
SEED_RE = re.compile(r'^seed\s+(\d+)$', re.A)
NOISE_RE = re.compile(rf'^noise\s+({NUM})$', re.A)
SET_RE = re.compile(rf'^set\s+{CVAR}\s*=\s*([A-Za-z]|\d+)$', re.A)
REPEAT_RE = re.compile(r'^repeat\s+(\d+)$', re.A)
IF_RE = re.compile(r'^if\s+(.+)$', re.A)
ELSE_RE = re.compile(r'^else(?:\s+if\s+(.+))?$', re.A)
COND_RE = re.compile(r'^([A-Za-z]|\d+)\s*(==|!=|<=|>=|<|>)\s*([A-Za-z]|\d+)$', re.A)

# The interpreter's input buffer is 1024 bytes and holds at most 1023 of a
# line; a line needs its newline to be known complete, so 1022 is the most
# that fits.
MAX_LINE_BYTES = 1022
MAX_UINT = 2 ** 32 - 1
# Nonzero decimals must lie in [1e-18, 1e18): as powers of ten of the leading
# digit, -18 through 17.
MIN_EXP, MAX_EXP = -18, 17


def parse_uint(tok):
    """A decimal integer literal, which must fit in 32 bits."""
    v = int(tok)
    if v > MAX_UINT:
        raise DslError(f'number {tok} out of range')
    return v


def parse_decimal(tok):
    """A decimal literal. Anything but zero must be from 1e-18 up to 1e18."""
    d = Decimal(tok)
    if d != 0 and not MIN_EXP <= d.adjusted() <= MAX_EXP:
        raise DslError(f'number {tok} out of range')
    return float(d)


COMPARE = {
    '==': lambda x, y: x == y,
    '!=': lambda x, y: x != y,
    '<': lambda x, y: x < y,
    '<=': lambda x, y: x <= y,
    '>': lambda x, y: x > y,
    '>=': lambda x, y: x >= y,
}

MAX_LOOP_DEPTH = 8
MAX_IF_DEPTH = 8
# A program that executes this many statements is a runaway `repeat`, not a
# test case.
MAX_STEPS = 200000

# The keywords that open or close a block, as opposed to a plain statement.
BLOCK_KEYWORDS = frozenset({'repeat', 'endrepeat', 'if', 'else', 'endif'})


def strip_comment(line):
    head, _, _ = line.partition('#')
    return head.replace('\t', ' ').strip()


class Repeat:
    """`repeat n` ... `endrepeat`."""

    def __init__(self, count, body):
        self.count, self.body = count, body


class If:
    """`if` ... `else if` ... `else` ... `endif`, as (condition, body) pairs.
    A plain `else` is a branch whose condition is None."""

    def __init__(self, branches):
        self.branches = branches


class _Stop(Exception):
    """`end`: the interpreter stops there, wherever it is nested."""


def _keyword(line):
    """The block keyword a line opens or closes with, or '' for a statement."""
    head = line.split(None, 1)[0] if line.split() else ''
    return head if head in BLOCK_KEYWORDS else ''


def parse_block(lines, i=0, stop=frozenset(), loops=0, ifs=0):
    """Builds the block structure the interpreter walks. The assembly executes
    the same shapes by recording lines and replaying them against a frame
    stack, so a real tree here is a deliberately different route to the same
    control flow. `lines` holds (text, raw byte length) pairs.

    Returns (block, index of the line that stopped it, whether that line was
    the top-level `end`). The top-level `end` is where the program text ends:
    the interpreter never reads past it, so nothing after it is parsed.
    """
    block = []
    while i < len(lines):
        line, nbytes = lines[i]
        if nbytes > MAX_LINE_BYTES:
            raise DslError(f'line {i + 1} is {nbytes} bytes, over {MAX_LINE_BYTES}')
        if not line:
            i += 1
            continue
        if not stop and line == 'end':
            return block, i, True
        kw = _keyword(line)
        if kw in stop:
            return block, i, False

        if kw == 'repeat':
            m = REPEAT_RE.match(line)
            if not m:
                raise DslError(f'malformed repeat: {line!r}')
            count = parse_uint(m.group(1))
            if loops + 1 > MAX_LOOP_DEPTH:
                raise DslError(f'loops nested more than {MAX_LOOP_DEPTH} deep')
            body, j, _ = parse_block(lines, i + 1, {'endrepeat'}, loops + 1, ifs)
            if j >= len(lines):
                raise DslError('repeat without a matching endrepeat')
            if lines[j][0] != 'endrepeat':
                raise DslError(f'trailing text after endrepeat: {lines[j][0]!r}')
            block.append(Repeat(count, body))
            i = j + 1
        elif kw == 'if':
            m = IF_RE.match(line)
            if not m:
                raise DslError(f'if without a condition: {line!r}')
            if ifs + 1 > MAX_IF_DEPTH:
                raise DslError(f'ifs nested more than {MAX_IF_DEPTH} deep')
            cond = m.group(1).strip()
            branches = []
            plain_else = False
            while True:
                body, j, _ = parse_block(lines, i + 1, {'else', 'endif'},
                                         loops, ifs + 1)
                branches.append((cond, body))
                if j >= len(lines):
                    raise DslError('if without a matching endif')
                if _keyword(lines[j][0]) == 'endif':
                    if lines[j][0] != 'endif':
                        raise DslError(f'trailing text after endif: {lines[j][0]!r}')
                    i = j + 1
                    break
                m = ELSE_RE.match(lines[j][0])
                if not m:
                    raise DslError(f'malformed else: {lines[j][0]!r}')
                if plain_else:
                    raise DslError('else after else')
                cond = m.group(1) and m.group(1).strip()   # None for plain else
                plain_else = cond is None
                i = j
            block.append(If(branches))
        elif kw:
            raise DslError(f'{kw} without a matching opener')
        else:
            block.append(line)
            i += 1
    return block, i, False


def apply_gate1(state, n, target, u):
    """Apply a 2x2 gate to one qubit of a 2^n-amplitude state."""
    psi = state.reshape((2,) * n)
    psi = np.tensordot(u, psi, axes=([1], [target]))
    psi = np.moveaxis(psi, 0, target)
    return psi.reshape(2 ** n)


def apply_gate2(state, n, control, target, g):
    """Apply a 4x4 gate, indexed |control target>, to two qubits."""
    psi = state.reshape((2,) * n)
    g4 = g.reshape(2, 2, 2, 2)          # (c_out, t_out, c_in, t_in)
    psi = np.tensordot(g4, psi, axes=([2, 3], [control, target]))
    psi = np.moveaxis(psi, [0, 1], [control, target])
    return psi.reshape(2 ** n)


class Interpreter:
    """Executes DSL statement text, tracking one register per declared name."""

    def __init__(self, forced_outcomes=None):
        self.vars = {}          # name -> amplitude vector
        self.sizes = {}         # name -> qubit count
        self.cvars = {}         # name -> classical integer value
        self.noise = 0.0        # depolarising rate the program last asked for
        self.prints = []        # one amplitude vector per print(), in order
        self.events = []        # ('print', amps) / ('measure', bits, probability)
        # Outcomes observed from the assembly, replayed in order. None means
        # sample locally instead.
        self._forced = None if forced_outcomes is None else list(forced_outcomes)
        self._rng = np.random.default_rng(0)
        self._steps = 0

    def run(self, lines):
        entries = [(strip_comment(l), len(l.encode('utf-8'))) for l in lines]
        block, _, found_end = parse_block(entries)
        if not found_end:
            raise DslError('the program has no top-level end')
        try:
            self._run_block(block)
        except _Stop:
            pass
        return self

    def _run_block(self, block):
        for item in block:
            if isinstance(item, Repeat):
                for _ in range(item.count):
                    # An iteration counts as a step even if its body runs no
                    # statement, or `repeat 4294967295` around an empty body
                    # would spin here for hours without tripping the limit.
                    self._steps += 1
                    if self._steps > MAX_STEPS:
                        raise DslError(f'program ran past {MAX_STEPS} statements')
                    self._run_block(item.body)
            elif isinstance(item, If):
                for cond, body in item.branches:
                    if cond is None or self._cond(cond):
                        self._run_block(body)
                        break
            elif item == 'end':
                raise _Stop
            else:
                self._steps += 1
                if self._steps > MAX_STEPS:
                    raise DslError(f'program ran past {MAX_STEPS} statements')
                self._exec(item)

    def _operand(self, tok):
        """A condition operand: a literal, or a classical variable's value."""
        if tok.isdigit():
            return parse_uint(tok)
        if tok not in self.cvars:
            raise DslError(f'classical variable {tok!r} not declared')
        return self.cvars[tok]

    def _cond(self, text):
        m = COND_RE.match(text)
        if not m:
            raise DslError(f'malformed condition: {text!r}')
        return COMPARE[m.group(2)](self._operand(m.group(1)),
                                   self._operand(m.group(3)))

    def _outcome(self, probs, nbits):
        """Pick (or replay) a basis outcome from unnormalised branch weights.
        Returns (bits, index, the chosen branch's weight)."""
        if probs.sum() == 0:
            raise DslError('cannot measure a register with zero norm')
        if self._forced is not None:
            if not self._forced:
                raise DslError('more measurements than the harness observed')
            bits = self._forced.pop(0)
            if len(bits) != nbits or set(bits) - set('01'):
                raise DslError(f'observed outcome {bits!r} is not {nbits} bits')
            index = int(bits, 2)
        else:
            total = probs.sum()
            index = int(self._rng.choice(len(probs), p=probs / total))
            bits = format(index, f'0{nbits}b')
        return bits, index, float(probs[index])

    def _lookup(self, name):
        if name not in self.vars:
            raise DslError(f'variable {name!r} not declared')
        return self.vars[name], self.sizes[name]

    def _check_index(self, k, n):
        if not 0 <= k < n:
            raise DslError(f'qubit index {k} out of range for a {n}-qubit register')

    def _exec(self, line):
        m = QUBIT_SIZED_RE.match(line)
        if m:
            name, n = m.group(1), parse_uint(m.group(2))
            if not 1 <= n <= MAX_QUBITS:
                raise DslError(f'register size {n} out of range')
            state = np.zeros(2 ** n, dtype=complex)
            state[0] = 1
            self.vars[name], self.sizes[name] = state, n
            return

        m = QUBIT_AMPS_RE.match(line)
        if m:
            name = m.group(1)
            if not AMP_LIST_RE.match(m.group(2)):
                raise DslError(f'malformed amplitude list: {line!r}')
            amps = [complex(parse_decimal(re_), parse_decimal(im))
                    for re_, im in AMP_RE.findall(m.group(2))]
            count = len(amps)
            if count < 2 or count & (count - 1) or count > 2 ** MAX_QUBITS:
                raise DslError(f'amplitude count {count} is not a usable power of two')
            self.vars[name] = np.array(amps, dtype=complex)
            self.sizes[name] = count.bit_length() - 1
            return

        m = QUBITOP1_RE.match(line)
        if m:
            name, k, gate = m.group(1), parse_uint(m.group(2)), m.group(3)
            state, n = self._lookup(name)
            self._check_index(k, n)
            if gate not in GATES1:
                raise DslError(f'unknown single-qubit gate {gate!r}')
            self.vars[name] = apply_gate1(state, n, k, GATES1[gate])
            return

        m = QUBITOP2_RE.match(line)
        if m:
            name, c, name2, t, gate = (m.group(1), parse_uint(m.group(2)),
                                       m.group(3), parse_uint(m.group(4)),
                                       m.group(5))
            state, n = self._lookup(name)
            self._lookup(name2)
            if name != name2:
                raise DslError('two-qubit gate operands must be one register')
            self._check_index(c, n)
            self._check_index(t, n)
            if c == t:
                raise DslError('two-qubit gate needs two distinct qubits')
            if gate not in GATES2:
                raise DslError(f'unknown two-qubit gate {gate!r}')
            self.vars[name] = apply_gate2(state, n, c, t, GATES2[gate])
            return

        m = MEASURE1_RE.match(line)
        if m:
            name, k = m.group(1), parse_uint(m.group(2))
            state, n = self._lookup(name)
            self._check_index(k, n)
            bit = (np.arange(2 ** n) >> (n - 1 - k)) & 1   # qubit k is bit n-1-k
            weight = np.abs(state) ** 2
            probs = np.array([weight[bit == 0].sum(), weight[bit == 1].sum()])
            bits, index, w = self._outcome(probs, 1)
            collapsed = np.where(bit == index, state, 0)
            self.vars[name] = collapsed / np.sqrt(w) if w > 0 else collapsed
            if m.group(3):
                self.cvars[m.group(3)] = index
            # The event carries the outcome's probability, normalised, so an
            # unnormalised register is judged against its own total weight.
            self.events.append(('measure', bits, w / probs.sum()))
            return

        m = MEASUREALL_RE.match(line)
        if m:
            name = m.group(1)
            state, n = self._lookup(name)
            weight = np.abs(state) ** 2
            bits, index, w = self._outcome(weight, n)
            collapsed = np.zeros(2 ** n, dtype=complex)
            collapsed[index] = 1
            self.vars[name] = collapsed
            if m.group(2):
                self.cvars[m.group(2)] = index
            self.events.append(('measure', bits, w / weight.sum()))
            return

        m = SEED_RE.match(line)
        if m:
            seed = parse_uint(m.group(1))
            if seed == 0:
                raise DslError('seed must be nonzero')
            self._rng = np.random.default_rng(seed)
            return

        m = NOISE_RE.match(line)
        if m:
            rate = parse_decimal(m.group(1))
            if not 0.0 <= rate <= 1.0:
                raise DslError(f'noise rate {rate} is not a probability')
            # Recorded, not simulated. A trajectory depends on which Paulis the
            # assembly's own PRNG drew, so the oracle cannot predict the state;
            # run_tests.py checks noisy programs statistically instead.
            self.noise = rate
            return

        m = SET_RE.match(line)
        if m:
            self.cvars[m.group(1)] = self._operand(m.group(2))
            return

        m = PRINT_RE.match(line)
        if m:
            state, _ = self._lookup(m.group(1))
            self.prints.append(state.copy())
            self.events.append(('print', state.copy()))
            return

        raise DslError(f'unrecognized statement: {line!r}')


def format_amps(amps):
    return '[' + ','.join(f'({a.real:g},{a.imag:g})' for a in amps) + ']'


if __name__ == '__main__':
    import sys

    lines = [l.rstrip('\n') for l in sys.stdin]
    for event in Interpreter().run(lines).events:
        if event[0] == 'print':
            print(format_amps(event[1]))
        else:
            print(f'|{event[1]}>')
