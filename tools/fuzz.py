#!/usr/bin/env python3
"""Differential fuzzing of QuAsm: random programs, run through the assembly
under RARS and through the NumPy oracle, with every disagreement reported.

The 200-odd programs in tests/programs were each written by hand, to check a
case somebody thought of. A disagreement between two implementations of the
same language needs no expected output at all, so here the programs are
generated -- from the grammar in docs/LANGUAGE.md, not from any list of known
defects -- and only the two implementations are compared.

Two modes, run side by side:

  valid     A well-formed program: registers declared by size or by explicit
            amplitudes (normalised or not, in any number form the language
            accepts), every gate, prints, measurements with and without a
            classical target, `set`, if / else if / else on classical values
            -- including measured ones -- and nested loops, laid out with
            random indentation, spacing and comments. Judged as a test program
            is: every print and every collapse must agree, every reported
            outcome must have been possible, and neither side may report an
            error.

  mutated   A valid program with one line corrupted by a random edit: a
            number made enormous or malformed, a keyword, name or gate
            replaced, whitespace inserted, a block keyword duplicated, moved or
            deleted, a line padded past the buffer. Judged on one question
            first -- do both sides agree on whether this is an error? -- and,
            if both accept it, as a valid program.

Two things are deliberately not findings: runaway programs (the oracle stops
at 200,000 statements and RARS at its step limit, which are not the same
bound), and errors from the fixed-size memory the oracle does not model
(RESOURCE_ERRORS).

--grammar v1 restricts generation to the language as it was documented before
the 2026-09-27 fixes (no S/T daggers, no exponents, letter names, no
indentation or tabs), so the fuzzer can be pointed at the pre-fix tree to see
which of the hand-found defects it finds on its own.

Usage
-----
    python tools/fuzz.py --n 200 -j 2                # both modes, seed 0
    python tools/fuzz.py --n 500 --mode mutated
    python tools/fuzz.py --n 200 --grammar v1 --root /path/to/old/tree
    python tools/fuzz.py --replay findings/0007.dsl  # re-judge one program
"""
import argparse
import concurrent.futures
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

GATES1_V1 = ['H', 'I', 'X', 'Y', 'Z', 'S', 'T', 'SN']
GATES1_V2 = GATES1_V1 + ['SDG', 'TDG']
GATES2 = ['CN', 'SW', 'CY', 'CZ'] + [f'CP{k}' for k in range(1, 7)]
REGS = ['q', 'r', 'a']
CVARS = ['c', 'd', 'e', 'm']
OPS = ['==', '!=', '<', '<=', '>', '>=']
KEYWORDS = ['qubit', 'qubitop1', 'qubitop2', 'measure', 'print', 'seed', 'noise',
            'set', 'repeat', 'endrepeat', 'if', 'else', 'endif', 'end']


# ---------------------------------------------------------------------------
# Valid programs
# ---------------------------------------------------------------------------

class Gen:
    def __init__(self, rng, grammar):
        self.rng = rng
        self.v2 = grammar == 'v2'
        self.gates1 = GATES1_V2 if self.v2 else GATES1_V1

    def chance(self, p):
        return self.rng.random() < p

    def pick(self, seq):
        return seq[int(self.rng.integers(len(seq)))]

    def number(self, x):
        """A decimal in one of the forms the language accepts."""
        if self.v2 and self.chance(0.15):
            m, e = f'{x:.4e}'.split('e')
            return f'{m}e{int(e)}' if self.chance(0.5) else f'{m}E{int(e):+d}'
        s = f'{x:.5f}'.rstrip('0')
        if s.endswith('.'):
            s = s + ('0' if self.chance(0.5) else '')
        if s in ('-0.', '-0.0', '-0'):
            s = '0'
        if self.chance(0.1) and s.startswith('0.'):
            s = s[1:]                              # .25
        return s

    def ws(self):
        return self.pick([' ', ' ', ' ', '  ']) if not self.v2 else \
            self.pick([' ', ' ', ' ', '  ', '\t'])

    def decl(self, name, n):
        if n <= 3 and self.chance(0.6):
            v = self.rng.normal(size=2 ** n) + 1j * self.rng.normal(size=2 ** n)
            v /= np.linalg.norm(v)
            if self.chance(0.4):
                v *= self.rng.uniform(0.3, 3.0)    # deliberately unnormalised
            pairs = ','.join(f'({self.number(a.real)},{self.number(a.imag)})'
                             for a in v)
            line = f'qubit {name} = [{pairs}]'
            if self.v2 or len(line) <= 99:   # v1 documented a 100-byte statement limit
                return line
        br = f'[ {n} ]' if self.v2 and self.chance(0.2) else f'[{n}]'
        return f'qubit {name}{br}'

    def idx(self, name, k):
        if self.v2 and self.chance(0.15):
            return f'{name}[ {k} ]'
        return f'{name}[{k}]'

    def stmt(self, regs, depth, cvars_set):
        r = self.pick(list(regs))
        n = regs[r]
        roll = self.rng.random()
        if roll < 0.35:
            return [f'qubitop1{self.ws()}{self.idx(r, int(self.rng.integers(n)))} = '
                    f'{self.pick(self.gates1)}']
        if roll < 0.55 and n >= 2:
            c, t = self.rng.choice(n, size=2, replace=False)
            return [f'qubitop2 {self.idx(r, c)},{self.idx(r, t)} = {self.pick(GATES2)}']
        if roll < 0.65:
            return [f'print({r})']
        if roll < 0.75:
            tgt = f' -> {self.pick(CVARS)}' if self.chance(0.6) else ''
            if self.chance(0.6):
                return [f'measure {self.idx(r, int(self.rng.integers(n)))}{tgt}']
            return [f'measure {r}{tgt}']
        if roll < 0.8:
            rhs = self.pick(CVARS) if self.chance(0.3) else str(int(self.rng.integers(0, 9)))
            return [f'set {self.pick(CVARS)} = {rhs}']
        if roll < 0.83:
            return [self.decl(r, n)]                 # redeclare, same size
        if depth >= 3:
            return [f'print({r})']
        if roll < 0.92:
            return self.if_block(regs, depth + 1, cvars_set)
        return self.repeat_block(regs, depth + 1, cvars_set)

    def body(self, regs, depth, cvars_set, lo=1, hi=4):
        out = []
        for _ in range(int(self.rng.integers(lo, hi + 1))):
            out += self.stmt(regs, depth, cvars_set)
        return out

    def cond(self):
        a = self.pick(CVARS) if self.chance(0.8) else str(int(self.rng.integers(0, 4)))
        b = str(int(self.rng.integers(0, 4))) if self.chance(0.7) else self.pick(CVARS)
        return f'{a} {self.pick(OPS)} {b}'

    def if_block(self, regs, depth, cvars_set):
        out = [f'if {self.cond()}'] + self.indent(self.body(regs, depth, cvars_set))
        for _ in range(int(self.rng.integers(0, 3))):
            out += [f'else if {self.cond()}'] + self.indent(self.body(regs, depth, cvars_set))
        if self.chance(0.5):
            out += ['else'] + self.indent(self.body(regs, depth, cvars_set))
        return out + ['endif']

    def repeat_block(self, regs, depth, cvars_set):
        count = int(self.rng.integers(0, 4))
        return [f'repeat {count}'] + self.indent(self.body(regs, depth, cvars_set)) + ['endrepeat']

    def indent(self, lines):
        if not self.v2 or not self.chance(0.4):
            return lines
        pad = self.pick(['  ', '    ', '\t'])
        return [pad + l for l in lines]

    def program(self):
        regs = {}
        out = []
        if self.chance(0.5):
            out.append(f'seed {int(self.rng.integers(1, 2 ** 31))}')
        for c in CVARS:                       # every classical variable bound
            out.append(f'set {c} = {int(self.rng.integers(0, 4))}')
        for name in self.rng.permutation(REGS)[:int(self.rng.integers(1, 3))]:
            regs[str(name)] = int(self.rng.integers(1, 5))
            out.append(self.decl(str(name), regs[str(name)]))
        out += self.body(regs, 0, set(CVARS), 3, 9)
        out.append(f'print({self.pick(list(regs))})')
        if self.v2 and self.chance(0.3):
            out = [l + '  # note' if self.chance(0.2) else l for l in out]
        return out + ['end']


# ---------------------------------------------------------------------------
# Mutations: one line, one random edit
# ---------------------------------------------------------------------------

def mutate(rng, lines, v2):
    """Returns (mutated lines, a short description of the edit)."""
    def pick(seq):
        return seq[int(rng.integers(len(seq)))]

    body = lines[:-1]                              # keep the final `end`
    i = int(rng.integers(len(body)))
    line = body[i]
    kind = pick(['digits', 'decimal', 'keyword', 'name', 'space', 'block',
                 'line', 'length', 'char', 'gate'])
    new = line
    if kind == 'digits' and re.search(r'\d+', line):
        m = pick(list(re.finditer(r'\d+', line)))
        rep = pick(['4294967295', '4294967296', '4294967297', '99999999999',
                    '0', '000', '1' + '0' * int(rng.integers(10, 45)), '18446744073709551617'])
        new = line[:m.start()] + rep + line[m.end():]
    elif kind == 'decimal' and re.search(r'\d', line):
        m = pick(list(re.finditer(r'-?\d*\.?\d+(?:[eE][+-]?\d+)?', line)))
        rep = pick(['1.2.3', '.', '-', '--1', '1e', '1e+', '1e999', '1e-999',
                    '0.' + '0' * 25 + '1', '1' + '0' * 30, '0.' + '9' * 40,
                    '1e18', '1e17', '1e-18', '1e-19', '+1', '-0', '1.', '.5'])
        new = line[:m.start()] + rep + line[m.end():]
    elif kind == 'keyword':
        words = line.split()
        if words:
            j = int(rng.integers(len(words)))
            words[j] = pick(KEYWORDS + ['', 'qubitop3', 'measur', 'ifx', 'els'])
            new = ' '.join(words)
    elif kind == 'name':
        m = list(re.finditer(r'\b[qracdem]\b', line))
        if m:
            m = pick(m)
            new = line[:m.start()] + pick(['!', '_', '7', 'zz', ']', 'é', '$']) + line[m.end():]
    elif kind == 'space':
        j = int(rng.integers(len(line) + 1))
        new = line[:j] + pick([' ', '\t', '  ', ' \t ']) + line[j:]
    elif kind == 'char':
        j = int(rng.integers(len(line) + 1))
        new = line[:j] + pick(['#', ']', '[', ',', '(', ')', '=', '-', '>', '0']) + line[j:]
    elif kind == 'gate' and '=' in line:
        new = re.sub(r'=\s*\S+\s*$', '= ' + pick(GATES1_V2 + GATES2 + ['CP0', 'CP7', 'h', 'SX', 'X X']), line)
    elif kind == 'length':
        new = line + ' ' * int(rng.integers(1000, 1100)) + pick(['', 'Y', '#'])
    elif kind == 'block':
        op = pick(['dup', 'else', 'elseif', 'endif', 'endrepeat', 'delete', 'end', 'if', 'repeat'])
        extra = {'else': 'else', 'elseif': 'else if c == 1', 'endif': 'endif',
                 'endrepeat': 'endrepeat', 'end': 'end', 'if': 'if c == 0',
                 'repeat': 'repeat 2'}
        if op == 'dup':
            return lines[:i] + [line] + lines[i:], f'block:dup line {i + 1}'
        if op == 'delete':
            return lines[:i] + lines[i + 1:], f'block:delete line {i + 1}'
        return lines[:i] + [extra[op]] + lines[i:], f'block:insert {extra[op]!r} at {i + 1}'
    elif kind == 'line':
        if i + 1 < len(body):
            return lines[:i] + [lines[i + 1], lines[i]] + lines[i + 2:], f'line:swap {i + 1}'
    if new == line:
        return mutate(rng, lines, v2)
    return lines[:i] + [new] + lines[i + 1:], f'{kind}: line {i + 1} {line!r} -> {new[:80]!r}'


# ---------------------------------------------------------------------------
# Judging
# ---------------------------------------------------------------------------

# Compared with the same tolerances and possibility threshold as run_tests.py.
TOLERANCE = 1e-4
RTOL = 1e-6
MIN_OUTCOME_PROB = 1e-6
AMP_RE = re.compile(r'\(\s*([-0-9.eE+]+)\s*,\s*([-0-9.eE+]+)\s*\)')
EVENT_RE = re.compile(r'\[(\([^\]]*\))\]|\|([01]+)>')
ERR_STRING_RE = re.compile(r'^\s*err_\w+:\s*\.string\s+"([^"\\]*)')
RESOURCE_ERRORS = ('Out of qubit storage', 'Loop body too long',
                   'Out of classical variable storage')


class Judge:
    """Compares one tree's assembly (under RARS) against the same tree's
    oracle. Deliberately independent of that tree's run_tests.py, so it can
    judge the pre-fix tree too: the error messages are read out of the tree's
    own assembly source, and the output comparison is done here."""

    def __init__(self, root):
        self.root = root
        self.main = os.path.join(root, 'main.s')
        sys.path.insert(0, os.path.join(root, 'tools'))
        import reference_sim
        sys.path.insert(0, HERE)
        import rars_server
        self.ref = reference_sim
        self.rars = rars_server
        # No generated program needs more than a few hundred thousand
        # instructions, so a runaway loop is cut off at 20 million rather than
        # the default 200 million.
        rars_server.MAX_STEPS = 20_000_000
        # A runaway guard for whichever oracle this is. The pre-fix oracle
        # counted only statements towards its limit, so a huge loop around a
        # body that runs none spun for hours; counting every block entry bounds
        # that without changing what any program means.
        original = reference_sim.Interpreter._run_block

        def guarded(interp, block):
            interp._fuzz_blocks = getattr(interp, '_fuzz_blocks', 0) + 1
            if interp._fuzz_blocks > 2_000_000:
                raise reference_sim.DslError('program ran past the fuzzer block limit')
            return original(interp, block)

        reference_sim.Interpreter._run_block = guarded
        self.errors = []
        for name in os.listdir(root):
            if name.endswith('.s'):
                with open(os.path.join(root, name), encoding='utf-8') as f:
                    for line in f:
                        m = ERR_STRING_RE.match(line)
                        if m and len(m.group(1).strip()) > 4:   # not the "Line N: " prefix
                            self.errors.append(m.group(1))

    def oracle_verdict(self, lines, outcomes):
        """The oracle's verdict on the path RARS actually took: measurement
        decides which branches run, so the oracle replays RARS's outcomes
        rather than drawing its own -- otherwise a statement on a branch only
        one of them took looks like a disagreement about the language."""
        try:
            self.ref.Interpreter(forced_outcomes=outcomes).run(lines)
            return 'ok', ''
        except self.ref.DslError as e:
            if 'ran past' in str(e):
                return 'runaway', str(e)
            if 'more measurements than' in str(e):
                return 'short', str(e)
            return 'error', str(e)
        except Exception as e:                       # an oracle crash is a finding
            return 'crash', repr(e)

    @staticmethod
    def outcomes(out):
        return [m.group(2) for m in EVENT_RE.finditer(out) if m.group(2)]

    def rars_verdict(self, lines):
        text = '\n'.join(lines) + '\n'
        reason, out = self.rars.server_for(self.main).run(text)
        if reason == 'MAX_STEPS':
            return 'runaway', '', out
        if reason not in ('NORMAL_TERMINATION', 'CLIFF_TERMINATION'):
            return 'crash', f'{reason}: {out[-300:]}', out
        reported = [e for e in self.errors if e in out]
        errs = [e for e in reported if e not in RESOURCE_ERRORS]
        if errs:
            return 'error', errs[0], out
        return ('resource' if reported else 'ok'), out, out

    def compare(self, lines, out):
        """Every print and every collapse, as run_tests.py checks them."""
        events = []
        for m in EVENT_RE.finditer(out):
            if m.group(1) is not None:
                events.append(('print', np.array(
                    [complex(float(a), float(b)) for a, b in AMP_RE.findall(m.group(1))])))
            else:
                events.append(('measure', m.group(2)))
        outcomes = [e[1] for e in events if e[0] == 'measure']
        try:
            interp = self.ref.Interpreter(forced_outcomes=outcomes).run(lines)
        except self.ref.DslError as e:
            return f'the oracle rejects the replayed run: {e}'
        expected = interp.events
        if len(expected) != len(events):
            return (f'{len(expected)} output events expected, RARS gave '
                    f'{len(events)}: {out[-400:]!r}')
        for i, (exp, act) in enumerate(zip(expected, events)):
            if exp[0] != act[0]:
                return f'event #{i}: expected a {exp[0]}, got a {act[0]}'
            if exp[0] == 'print':
                if exp[1].shape != act[1].shape or not np.allclose(
                        exp[1], act[1], atol=TOLERANCE, rtol=RTOL):
                    return f'print #{i}: expected {exp[1]}, got {act[1]}'
            elif exp[2] < MIN_OUTCOME_PROB:
                return f'measure #{i}: |{act[1]}> had probability {exp[2]:.3g}'
        return None

    def judge(self, lines, tag):
        """None if the two agree, else a description of the disagreement."""
        a, adetail, out = self.rars_verdict(lines)
        if a == 'crash':
            return f'RARS stopped abnormally: {adetail}'
        o, odetail = self.oracle_verdict(lines, self.outcomes(out))
        if o == 'crash':
            return f'the oracle crashed: {odetail}'
        if o == 'runaway' or a in ('runaway', 'resource'):
            return None
        if o == 'short':
            # The oracle wanted more outcomes than RARS reported: fine if RARS
            # stopped at an error, a real disagreement if it did not.
            return None if a == 'error' else f'RARS measured less than the oracle: {out[-300:]!r}'
        if o == 'error' and a == 'error':
            return None
        if o == 'error':
            return f'the oracle rejects it ({odetail}) but RARS runs it cleanly'
        if a == 'error':
            return f'RARS reports {adetail!r} but the oracle accepts it'
        return self.compare(lines, adetail)


def one_case(args, judge, k):
    rng = np.random.default_rng([args.seed, k])
    gen = Gen(rng, args.grammar)
    lines = gen.program()
    desc = 'valid'
    if args.mode == 'mutated' or (args.mode == 'both' and k % 2):
        lines, desc = mutate(rng, lines, args.grammar == 'v2')
    try:
        problem = judge.judge(lines, f'case{k}')
    except Exception as exc:
        problem = f'harness error: {exc!r}'
    return k, desc, lines, problem


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--n', type=int, default=100)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--mode', choices=['valid', 'mutated', 'both'], default='both')
    ap.add_argument('--grammar', choices=['v1', 'v2'], default='v2')
    ap.add_argument('--root', default=os.path.dirname(HERE),
                    help='tree whose main.s and tools/ oracle to test')
    ap.add_argument('-j', '--jobs', type=int, default=1)
    ap.add_argument('--findings', default=None,
                    help='directory to write each disagreeing program into')
    ap.add_argument('--replay', default=None, help='judge one saved program')
    args = ap.parse_args()

    judge = Judge(os.path.abspath(args.root))
    if args.replay:
        with open(args.replay, encoding='utf-8') as f:
            lines = [l.rstrip('\n') for l in f if not l.startswith('#!')]
        problem = judge.judge(lines, 'replay')
        print(problem or 'the two implementations agree')
        return 1 if problem else 0

    if args.findings:
        os.makedirs(args.findings, exist_ok=True)
    found = []
    with concurrent.futures.ThreadPoolExecutor(max(1, args.jobs)) as pool:
        for k, desc, lines, problem in pool.map(lambda k: one_case(args, judge, k),
                                                range(args.n)):
            if problem:
                found.append((k, desc, lines, problem))
                print(f'[DIFF] case {k} ({desc})\n       {problem[:300]}', flush=True)
                if args.findings:
                    with open(os.path.join(args.findings, f'{k:04d}.dsl'), 'w',
                              encoding='utf-8', newline='\n') as f:
                        f.write(f'#! {desc}\n#! {problem[:500]}\n')
                        f.write('\n'.join(lines) + '\n')
            elif k % 25 == 0:
                print(f'[....] {k}/{args.n}', flush=True)
    print(f'\n{args.n} programs (seed {args.seed}, mode {args.mode}, grammar '
          f'{args.grammar}): {len(found)} disagreement(s)')
    if found:
        # One row per kind of disagreement, with numbers and quoted values
        # blurred, so one defect hit many times reads as one row.
        groups = {}
        for k, desc, _, problem in found:
            sig = re.sub(r"'[^']*'|\[[^\]]*\]|-?\d[\d.e+-]*", '_', problem)[:90]
            groups.setdefault(sig, []).append(k)
        print('\nBy kind:')
        for sig, ks in sorted(groups.items(), key=lambda g: -len(g[1])):
            print(f'  {len(ks):4}  {sig}   e.g. case {ks[0]}')
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
