#!/usr/bin/env python3
"""Runs a QuAsm script file.

    python tools/quasm.py examples/bell.dsl
    python tools/quasm.py examples/coin_flips.dsl -o flips.txt
    cat prog.dsl | python tools/quasm.py -

The script is piped into the real RISC-V interpreter running under RARS, so
this is a front end, not a second implementation -- the same path the test
suite and the GUI take. Java and tools/rars1_6.jar are needed; set QUASM_JAVA
if `java` is not on PATH.

--check additionally replays the run through tools/reference_sim.py, the
NumPy oracle, and reports whether every printed state agreed. That needs
numpy; nothing else here does.
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

RARS_JAR = os.path.join(ROOT, 'tools', 'rars1_6.jar')
MAIN_S = os.path.join(ROOT, 'main.s')
JAVA = os.environ.get('QUASM_JAVA', 'java')


def program_lines(text):
    """Script text -> the lines to feed the interpreter. Comments and blank
    lines are the DSL's own and go through untouched; `end` is appended if
    the script has none, since without it the interpreter would sit waiting
    for input that is never coming."""
    lines = [l.rstrip() for l in text.splitlines()]
    if not any(l.strip() == 'end' for l in lines):
        lines.append('end')
    return lines


def run_rars(lines, timeout=300):
    """Feeds the program to the interpreter. Returns (stdout, stderr)."""
    # -XX:-UseThreadPriorities: RARS lowers its simulator thread's priority,
    # which starves it on a busy machine. See rars_server.JVM_FLAGS.
    proc = subprocess.run([JAVA, '-XX:-UseThreadPriorities', '-jar', RARS_JAR,
                           'nc', 'sm', MAIN_S],
                          input='\n'.join(lines) + '\n',
                          capture_output=True, text=True, timeout=timeout)
    return proc.stdout, proc.stderr


def clean_output(stdout):
    """The interpreter echoes a '>> ' prompt per line it reads from stdin;
    strip them so the output is just the program's own."""
    out = []
    for line in stdout.splitlines():
        while line.startswith('>>'):
            line = line[2:].lstrip()
        if line:
            out.append(line)
    return '\n'.join(out)


def check_against_oracle(lines, stdout):
    """Replays the run's measurement outcomes through the NumPy reference and
    reports whether every printed state matched. Returns a status string."""
    import numpy as np

    import run_tests
    from reference_sim import DslError, Interpreter

    actual = run_tests.parse_events(stdout)
    outcomes = [e[1] for e in actual if e[0] == 'measure']
    try:
        expected = Interpreter(forced_outcomes=outcomes).run(lines).events
    except DslError as exc:
        return f'oracle rejected the program: {exc}'
    if len(actual) != len(expected):
        return (f'MISMATCH: oracle expected {len(expected)} outputs, '
                f'the interpreter produced {len(actual)}')
    for i, (exp, act) in enumerate(zip(expected, actual)):
        if exp[0] != act[0]:
            return f'MISMATCH: output #{i} is a {act[0]}, oracle expected a {exp[0]}'
        if exp[0] == 'print':
            if not np.allclose(exp[1], act[1], atol=run_tests.TOLERANCE, rtol=0):
                return (f'MISMATCH on print() #{i}\n'
                        f'  oracle: {exp[1]}\n  QuAsm: {act[1]}')
        elif exp[2] < run_tests.MIN_OUTCOME_PROB:
            return (f'MISMATCH: measure #{i} reported |{act[1]}>, which the '
                    f'oracle gives probability {exp[2]:.3g}')
    return f'matches the NumPy reference oracle ({len(actual)} outputs checked)'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('program', help="script to run, or '-' for stdin")
    ap.add_argument('-o', '--out', help='write the output to this file')
    ap.add_argument('--raw', action='store_true',
                    help="keep the interpreter's '>> ' prompts")
    ap.add_argument('--check', action='store_true',
                    help='also verify the run against the NumPy oracle')
    ap.add_argument('--timeout', type=float, default=300,
                    help='seconds to allow the run (default 300)')
    args = ap.parse_args(argv)

    if not os.path.exists(RARS_JAR):
        print(f'RARS jar not found at {RARS_JAR} -- run tools/fetch_rars.sh first',
              file=sys.stderr)
        return 2

    if args.program == '-':
        text = sys.stdin.read()
    else:
        with open(args.program, encoding='utf-8') as f:
            text = f.read()
    lines = program_lines(text)

    try:
        stdout, stderr = run_rars(lines, timeout=args.timeout)
    except FileNotFoundError:
        print(f'could not run {JAVA!r} -- is Java on PATH? '
              f'(set QUASM_JAVA to override)', file=sys.stderr)
        return 2
    except subprocess.TimeoutExpired:
        print(f'the run did not finish within {args.timeout}s', file=sys.stderr)
        return 1

    body = stdout if args.raw else clean_output(stdout)
    if args.out:
        with open(args.out, 'w', encoding='utf-8', newline='\n') as f:
            f.write(body + '\n')
        print(f'wrote {args.out}')
    else:
        print(body)
    if stderr.strip():
        print(stderr.strip(), file=sys.stderr)

    if args.check:
        status = check_against_oracle(lines, stdout)
        print(status, file=sys.stderr)
        if 'MISMATCH' in status:
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
