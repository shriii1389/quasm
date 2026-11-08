#!/usr/bin/env python3
"""Measures the instruction cost of a gate as a function of register size.

RARS reports an executed-instruction count (`ic`) only when it stops at a step
limit, not when the program exits through syscall 10. So the exact count for a
terminating program is recovered by binary search on that limit: a cap below
the true count produces the "maximum step limit" message, a cap at or above it
does not. Each probe runs on one long-lived RARS with a per-run step cap (see
rars_server.py); QUASM_RARS=cli makes each probe a fresh JVM instead, which is
the same search, slower.

The cost of one gate is the difference between a program applying N of them and
an otherwise identical program applying none, divided by N -- so the parser,
the prompt, and the declaration all cancel out and what is left is the kernel.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RARS_JAR = os.path.join(ROOT, 'tools', 'rars1_6.jar')
MAIN_S = os.path.join(ROOT, 'main.s')
JAVA = os.environ.get('QUASM_JAVA', 'java')

REPS = 20          # gates per measured program; the divisor for the marginal cost
LIMIT_MSG = 'maximum step limit'


def terminates_within(program, cap):
    """True if the program finishes in at most `cap` instructions."""
    if os.environ.get('QUASM_RARS') != 'cli':
        # The same step limit, set per run on one long-lived RARS (see
        # rars_server.py) instead of a fresh JVM for every probe of the search.
        import rars_server
        reason, _ = rars_server.server_for(MAIN_S).run(program, max_steps=cap)
        return reason != 'MAX_STEPS'
    proc = subprocess.run(
        [JAVA, '-XX:-UseThreadPriorities', '-jar', RARS_JAR, 'nc', 'sm', 'ic',
         str(cap), MAIN_S],
        input=program, capture_output=True, text=True, timeout=300)
    return LIMIT_MSG not in (proc.stdout + proc.stderr)


def exact_count(program, lo=1, hi=1 << 22):
    """Smallest cap at which the program still finishes: its instruction count."""
    if not terminates_within(program, hi):
        raise RuntimeError('program needs more than the search ceiling')
    while lo < hi:
        mid = (lo + hi) // 2
        if terminates_within(program, mid):
            hi = mid
        else:
            lo = mid + 1
    return lo


def prog(n, body_lines):
    return f'qubit q[{n}]\n' + ''.join(body_lines) + 'end\n'


def main():
    print(f'{"n":>2} {"amps":>5} {"1q gate":>9} {"per amp":>8} '
          f'{"2q gate":>9} {"per amp":>8}')
    for n in range(1, 7):
        base = exact_count(prog(n, []))
        one = exact_count(prog(n, [f'qubitop1 q[0] = H\n'] * REPS))
        c1 = (one - base) / REPS
        if n >= 2:
            two = exact_count(prog(n, [f'qubitop2 q[0],q[1] = CN\n'] * REPS))
            c2 = (two - base) / REPS
            c2s = f'{c2:9.1f} {c2 / 2 ** n:8.2f}'
        else:
            c2s = f'{"-":>9} {"-":>8}'
        print(f'{n:>2} {2 ** n:>5} {c1:9.1f} {c1 / 2 ** n:8.2f} {c2s}', flush=True)


if __name__ == '__main__':
    sys.exit(main())
