#!/usr/bin/env python3
"""Runs every tests/programs/*.dsl file through RARS (real execution) and
through reference_sim.py (independent NumPy oracle), diffs the two, and
reports pass/fail per test. Exit code is nonzero if any test fails, for use
as a CI gate.

Each .dsl file is plain DSL statement text (one statement per line, ending
in `end`). Comment lines of the form `# key: value` naming one of the
metadata keys below are directives to this harness and are stripped; every
other comment is left in place and sent to RARS, since the DSL understands
comments itself and the tests may as well exercise that:
  # name: <test name>            (defaults to the filename)
  # expect_error: <substring>    (if present, the test only checks that
                                   substring appears in RARS's output --
                                   no reference-oracle comparison is done)
  # expect_freq: <bits> <p> <tol>
                                 (statistical check: the fraction of measure
                                  outcomes equal to <bits> must be within
                                  <tol> of <p>)
  # expect_count: <n> <substring>
                                 (<substring> must appear exactly <n> times
                                  in the output -- how a test pins down how
                                  often something happened, e.g. that one
                                  error inside a loop is reported once and
                                  not once per iteration)

Errors are checked in both directions. An `expect_error` test must be rejected
by the oracle too -- an error only the assembly reports is a disagreement about
the language, not a pass -- except for the resource limits the oracle does not
model (RESOURCE_ERRORS). A test without `expect_error` must produce no error
message at all, since a stray error can otherwise leave every compared value
intact and pass unnoticed.

Every print() statement's output is compared against the oracle's value for
the same statement. Since Phase 3 gave registers real 2^n-amplitude storage,
print() shows the whole state, so this needs no back door into memory (it
used to dump the .data segment to see past a 2-amplitude truncation).

Measurement can't be compared value-for-value -- RARS and the oracle draw from
different random streams -- so it is checked three ways instead: every observed
outcome must have had nonzero probability under the oracle's exact math, the
state printed after a measurement must match the collapse-and-renormalise that
outcome implies, and `expect_freq` tests empirical frequencies against the
Born-rule probabilities over many trials.
"""
import argparse
import concurrent.futures
import glob
import os
import re
import subprocess
import sys

import numpy as np

import check_gate_data
import rars_server
from reference_sim import DslError, Interpreter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RARS_JAR = os.path.join(ROOT, 'tools', 'rars1_6.jar')
MAIN_S = os.path.join(ROOT, 'main.s')
TEST_DIR = os.path.join(ROOT, 'tests', 'programs')

JAVA = os.environ.get('QUASM_JAVA', 'java')

# Absolute-error tolerance for comparing RARS's float32 output against the
# reference oracle's exact-math values. The assembly stores irrational gate
# entries to 8 decimal places (0.70710678), well below float32's ~1e-7
# resolution, so the only real error source is float32 rounding accumulating
# over a handful of multiply-adds. A wrong matrix entry or misplaced
# amplitude differs by O(0.1-1), thousands of times larger.
TOLERANCE = 1e-4
# ...plus a relative term, because float32 precision is relative: an amplitude
# of 1e11 -- legal, since the language allows up to 1e18 -- is held only to
# about +/-4096. For the O(1) amplitudes of every normalised state this adds
# at most a few 1e-6 to the threshold, so it changes nothing there; found by
# tools/fuzz.py, which generated exactly such an amplitude.
RTOL = 1e-6

# An outcome the oracle gives less probability than this had no business being
# reported at all, and points at a broken probability or collapse.
MIN_OUTCOME_PROB = 1e-6

AMP_RE = re.compile(r'\(\s*([-0-9.eE+]+)\s*,\s*([-0-9.eE+]+)\s*\)')
# print() emits [(re,im),...] and measure emits |0110>, interleaved in one
# stream, so both are matched by a single pass to keep them in order.
EVENT_RE = re.compile(r'\[(\([^\]]*\))\]|\|([01]+)>')
META_RE = re.compile(r'#\s*(\w+):\s*(.*)')
META_KEYS = {'name', 'expect_error', 'expect_freq', 'expect_count'}

# Every error the interpreter reports carries its line number, so this finds
# all of them, whatever the message.
ERROR_RE = re.compile(r'Line \d+: [^\n]*|Unexpected end of input')
# Limits of the assembly's fixed-size memory that the oracle deliberately does
# not model: it has no arena, no loop store and no classical-variable table.
RESOURCE_ERRORS = ('Out of qubit storage', 'Loop body too long',
                   'Out of classical variable storage')


def read_program(path):
    meta = {}
    body = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            m = META_RE.match(line)
            if m and m.group(1) in META_KEYS:
                meta[m.group(1)] = m.group(2).strip()
                body.append('')   # blank, not dropped, so error line numbers match the file
                continue
            body.append(line)     # comments and blank lines included
    return meta, body


def run_rars(body):
    stdin_text = '\n'.join(body) + '\n'
    if os.environ.get('QUASM_RARS') != 'cli':
        # One long-lived RARS per thread; see rars_server.py.
        return rars_server.run(MAIN_S, stdin_text)
    args = [JAVA] + rars_server.JVM_FLAGS + ['-jar', RARS_JAR, 'nc', 'sm', MAIN_S]
    # Generous timeout: a run is ~7s, almost all of it JVM startup, and a
    # loaded machine can push that well past a tight limit (a 30s cap here
    # produced spurious failures).
    proc = subprocess.run(args, input=stdin_text.encode('utf-8'),
                          capture_output=True, timeout=600)
    return proc.stdout.decode('utf-8')


def parse_events(stdout):
    """Pull printed amplitude vectors and measurement outcomes out of RARS's
    stdout, in the order they were emitted."""
    events = []
    for m in EVENT_RE.finditer(stdout):
        if m.group(1) is not None:
            amps = [complex(float(re_), float(im))
                    for re_, im in AMP_RE.findall(m.group(1))]
            events.append(('print', np.array(amps, dtype=complex)))
        else:
            events.append(('measure', m.group(2)))
    return events


def close(a, b):
    return a.shape == b.shape and np.allclose(a, b, atol=TOLERANCE, rtol=RTOL)


def check_freq(spec, outcomes):
    """Empirical frequency of one outcome against its Born-rule probability."""
    bits, p, tol = spec.split()
    if not outcomes:
        return f'expect_freq given but the program made no measurements'
    freq = sum(1 for o in outcomes if o == bits) / len(outcomes)
    if abs(freq - float(p)) > float(tol):
        return (f'|{bits}> came up {freq:.4f} of {len(outcomes)} trials, '
                f'expected {float(p)} +/- {float(tol)}')
    return None


def check_count(spec, stdout):
    """Exact number of times a substring appears in the output."""
    want, _, needle = spec.partition(' ')
    got = stdout.count(needle)
    if got != int(want):
        return f'{needle!r} appears {got} times in the output, expected {want}'
    return None


def run_test(path):
    meta, body = read_program(path)
    name = meta.get('name', os.path.splitext(os.path.basename(path))[0])

    stdout = run_rars(body)

    if 'expect_count' in meta:
        problem = check_count(meta['expect_count'], stdout)
        if problem:
            return name, False, problem

    if 'expect_error' in meta:
        expected = meta['expect_error']
        if expected not in stdout:
            return name, False, f'expected {expected!r} in RARS output, got: {stdout!r}'
        if expected in RESOURCE_ERRORS:
            return name, True, ''
        try:
            Interpreter().run(body)
        except DslError:
            return name, True, ''
        return name, False, (f'RARS reports {expected!r} but the oracle accepts '
                             f'the program')

    reported = ERROR_RE.findall(stdout)
    if reported:
        return name, False, f'unexpected error in RARS output: {reported[0]!r}'

    actual = parse_events(stdout)
    outcomes = [e[1] for e in actual if e[0] == 'measure']
    # The oracle replays RARS's outcomes so the collapsed states it derives
    # are the ones the assembly should have produced.
    try:
        interp = Interpreter(forced_outcomes=outcomes).run(body)
    except DslError as exc:
        return name, False, f'the oracle rejects a program RARS ran cleanly: {exc}'
    expected = interp.events

    if interp.noise > 0:
        # A noisy run is one trajectory through a random Pauli channel driven
        # by the assembly's own PRNG. The oracle cannot say which trajectory,
        # so there is nothing to diff -- these tests carry expect_freq (or
        # expect_count) and are judged on the statistics alone.
        if 'expect_freq' in meta:
            problem = check_freq(meta['expect_freq'], outcomes)
            if problem:
                return name, False, problem
            return name, True, ''
        if 'expect_count' in meta:
            return name, True, ''       # already checked above
        return name, False, (
            'a program that sets a nonzero noise rate needs expect_freq or '
            'expect_count: its state cannot be compared against the oracle')

    if len(actual) != len(expected):
        return name, False, (
            f'expected {len(expected)} output events, RARS produced '
            f'{len(actual)}. Full output: {stdout!r}')
    for i, (exp, act) in enumerate(zip(expected, actual)):
        if exp[0] != act[0]:
            return name, False, f'event #{i}: expected a {exp[0]}, got a {act[0]}'
        if exp[0] == 'print':
            if not close(exp[1], act[1]):
                return name, False, f'print() #{i}: expected {exp[1]}, got {act[1]}'
        elif exp[2] < MIN_OUTCOME_PROB:
            return name, False, (
                f'measure #{i}: reported |{act[1]}>, which the oracle gives '
                f'probability {exp[2]:.3g}')

    if 'expect_freq' in meta:
        problem = check_freq(meta['expect_freq'], outcomes)
        if problem:
            return name, False, problem

    return name, True, ''


def _run_test_safely(path):
    try:
        return run_test(path)
    except Exception as exc:          # a harness fault is a failure, not a crash
        return os.path.basename(path), False, f'harness error: {exc!r}'


def main(patterns=(), jobs=1):
    if not os.path.exists(RARS_JAR):
        print(f'RARS jar not found at {RARS_JAR} -- run tools/fetch_rars.sh first', file=sys.stderr)
        return 2

    # Static gate-data audit first: a behavioural test only distinguishes two
    # matrices where its input state has nonzero amplitude, so wrong data can
    # slip through the .dsl tests entirely.
    problems = check_gate_data.check()
    for p in problems:
        print(f'[FAIL] gate data: {p}', file=sys.stderr)
    if problems:
        return 1
    print('[PASS] gate-data audit (all matrices unitary and correct)')

    paths = sorted(glob.glob(os.path.join(TEST_DIR, '*.dsl')))
    if patterns:    # narrowing is still handy while working on one feature
        paths = [p for p in paths
                 if any(s in os.path.basename(p) for s in patterns)]
    if not paths:
        print(f'No test programs found in {TEST_DIR}', file=sys.stderr)
        return 2

    failures = []
    with concurrent.futures.ThreadPoolExecutor(max(1, jobs)) as pool:
        # map keeps the report in file order however the runs interleave
        for name, ok, msg in pool.map(_run_test_safely, paths):
            print(f'[{"PASS" if ok else "FAIL"}] {name}', flush=True)
            if not ok:
                print(f'       {msg}')
                failures.append(name)

    print(f'\n{len(paths) - len(failures)}/{len(paths)} passed')
    if failures:
        print('Failed: ' + ', '.join(failures))
    return 1 if failures else 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Run the QuAsm test corpus.')
    ap.add_argument('patterns', nargs='*',
                    help='only run programs whose filename contains one of these')
    ap.add_argument('-j', '--jobs', type=int, default=1,
                    help='programs to run at once (one RARS process each)')
    args = ap.parse_args()
    sys.exit(main(args.patterns, args.jobs))
