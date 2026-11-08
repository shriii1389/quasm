#!/usr/bin/env python3
"""Static audit of the gate matrices declared in main.s.

Parses the `.float` gate declarations straight out of the assembly source and
checks each one is (a) unitary and (b) equal to the standard gate it claims to
be. This catches wrong *data* -- which the behavioural tests in run_tests.py
can miss, since a test only distinguishes two matrices if its input state has a
nonzero amplitude wherever they differ. Two shipped bugs were found this way:
the controlled-Z matrix encoding Z(x)I instead, and SNgate carrying a 0.707
normalisation that made it non-unitary instead of sqrt(NOT)'s 0.5.

Run standalone, or via run_tests.py which calls check() as a pre-flight.
"""
import os
import re
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_S = os.path.join(ROOT, 'main.s')

# Absolute tolerance: irrational entries are stored to 8 decimal places
# (0.70710678 for 1/sqrt(2)), finer than float32 resolves, so only rounding
# is expected here. A wrong matrix entry is off by O(0.1-1).
TOLERANCE = 1e-4

INV_SQRT2 = 1.0 / np.sqrt(2.0)
# A gate is one labelled .float directive optionally continued by further
# unlabelled .float lines, so each matrix row gets its own source line.
LABELLED_RE = re.compile(r'^\s*(\w+):\s*\.float\s+([-0-9.,\s]+?)\s*(?:#.*)?$')
CONTINUED_RE = re.compile(r'^\s*\.float\s+([-0-9.,\s]+?)\s*(?:#.*)?$')


def _ctrl(u):
    m = np.eye(4, dtype=complex)
    m[2:, 2:] = u
    return m


_Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
_Z = np.array([[1, 0], [0, -1]], dtype=complex)

# label -> ideal 2x2 matrix
EXPECTED_1Q = {
    'Hgate': INV_SQRT2 * np.array([[1, 1], [1, -1]], dtype=complex),
    'Igate': np.eye(2, dtype=complex),
    'Xgate': np.array([[0, 1], [1, 0]], dtype=complex),
    'Ygate': _Y,
    'Zgate': _Z,
    'Sgate': np.array([[1, 0], [0, 1j]], dtype=complex),
    'Tgate': np.array([[1, 0], [0, np.exp(1j * np.pi / 4)]], dtype=complex),
    'SNgate': 0.5 * np.array([[1 + 1j, 1 - 1j], [1 - 1j, 1 + 1j]], dtype=complex),
    'SDGgate': np.array([[1, 0], [0, -1j]], dtype=complex),
    'TDGgate': np.array([[1, 0], [0, np.exp(-1j * np.pi / 4)]], dtype=complex),
}

# label -> ideal 4x4 matrix, written in the |control target> basis.
EXPECTED_2Q = {
    'CNgate': np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]], dtype=complex),
    'SWgate': np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], dtype=complex),
    'CYgate': _ctrl(_Y),
    'CZgate': _ctrl(_Z),
}

# Controlled phase, diag(1, 1, 1, exp(2*pi*i / 2^k)). These carry irrational
# entries in both the real and imaginary halves, so a mistyped digit is exactly
# the kind of wrong-but-plausible data a behavioural test can miss.
for _k in range(1, 7):
    EXPECTED_2Q[f'CP{_k}gate'] = _ctrl(
        np.array([[1, 0], [0, np.exp(2j * np.pi / 2 ** _k)]], dtype=complex))


def _floats(text):
    return [float(x) for x in text.split(',') if x.strip()]


def parse_float_labels(path=MAIN_S):
    out = {}
    current = None
    with open(path, encoding='utf-8') as f:
        for line in f:
            m = LABELLED_RE.match(line)
            if m:
                current = m.group(1)
                out[current] = _floats(m.group(2))
                continue
            m = CONTINUED_RE.match(line)
            if m and current is not None:
                out[current].extend(_floats(m.group(1)))
                continue
            if line.strip():
                current = None      # any other content ends the declaration
    return out


def to_complex(floats):
    """Interleaved (re, im) float list -> complex vector."""
    return np.array([complex(floats[i], floats[i + 1])
                     for i in range(0, len(floats), 2)], dtype=complex)


def check(path=MAIN_S):
    """Returns a list of human-readable problem strings (empty if all good)."""
    labels = parse_float_labels(path)
    problems = []

    def audit(name, mat, expected):
        n = mat.shape[0]
        if not np.allclose(mat.conj().T @ mat, np.eye(n), atol=TOLERANCE, rtol=0):
            problems.append(f'{name} is not unitary:\n{mat}')
            return
        if not np.allclose(mat, expected, atol=TOLERANCE, rtol=0):
            problems.append(f'{name} differs from its ideal matrix:\n'
                            f'  got:\n{mat}\n  want:\n{expected}')

    for name, expected in EXPECTED_1Q.items():
        if name not in labels:
            problems.append(f'{name} not found in {os.path.basename(path)}')
            continue
        audit(name, to_complex(labels[name]).reshape(2, 2), expected)

    for name, expected in EXPECTED_2Q.items():
        if name not in labels:
            problems.append(f'{name} not found in {os.path.basename(path)}')
            continue
        audit(name, to_complex(labels[name]).reshape(4, 4), expected)

    return problems


def main():
    problems = check()
    for p in problems:
        print(f'[FAIL] {p}')
    total = len(EXPECTED_1Q) + len(EXPECTED_2Q)
    if problems:
        print(f'\n{len(problems)} gate matrix problem(s) found')
        return 1
    print(f'{total}/{total} gate matrices unitary and correct')
    return 0


if __name__ == '__main__':
    sys.exit(main())
