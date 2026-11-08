#!/usr/bin/env python3
"""A small Tkinter front end for running QuAsm programs.

Deliberately minimal: an editor, a Run button, and an output pane. Run pipes
the program into RARS exactly as tools/run_tests.py does -- so what you see is
the real RISC-V assembly executing, not a Python reimplementation of it.

    python tools/quasm_gui.py

Tkinter ships with CPython, so there is nothing to install. Java and
tools/rars1_6.jar are needed, same as for the test suite; set QUASM_JAVA if
`java` is not on PATH.

The optional "compare against reference oracle" box additionally runs
tools/reference_sim.py (NumPy) on the same program and reports whether the two
agree -- the same check run_tests.py makes, on whatever you happen to be
typing. It needs numpy; the box disables itself if numpy is missing.
"""
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

# One place decides how a program reaches the interpreter; this is a window
# onto it, not a second way of running things.
from quasm import (JAVA, RARS_JAR, check_against_oracle, clean_output,
                   program_lines, run_rars)

try:
    import numpy as np
    HAVE_ORACLE = True
except ImportError:
    HAVE_ORACLE = False

EXAMPLES = {
    'Superposition': """\
qubit q[1]
qubitop1 q[0] = H
print(q)
""",
    'Bell pair': """\
qubit q[2]
qubitop1 q[0] = H
qubitop2 q[0],q[1] = CN
print(q)
""",
    'GHZ-3 and measure': """\
qubit q[3]
qubitop1 q[0] = H
qubitop2 q[0],q[1] = CN
qubitop2 q[1],q[2] = CN
print(q)
measure q
print(q)
""",
    'QFT of |001>': """\
# 3-qubit quantum Fourier transform; CP2/CP3 are the pi/2 and pi/4 phases
qubit q[3]
qubitop1 q[2] = X       # input |001>
qubitop1 q[0] = H
qubitop2 q[1],q[0] = CP2
qubitop2 q[2],q[0] = CP3
qubitop1 q[1] = H
qubitop2 q[2],q[1] = CP2
qubitop1 q[2] = H
qubitop2 q[0],q[2] = SW # undo the bit reversal
print(q)                # 8 amplitudes of modulus 0.3536, each 1/8 turn apart
""",
    'Measure one qubit': """\
qubit q[2]
qubitop1 q[0] = H
qubitop2 q[0],q[1] = CN
measure q[0]
print(q)
measure q[1]
""",
    'Explicit amplitudes': """\
qubit q = [(0.6,0),(0,0.8)]
print(q)
measure q[0]
print(q)
""",
    'Coin flips in a loop': """\
# repeat runs the lines up to endrepeat again and again
seed 12345
qubit q[1]
repeat 20
qubitop1 q[0] = H       # H reprepares a fair coin from either outcome
measure q[0]
endrepeat
""",
    'Loop: biased trials': """\
# a fresh state every trial, so the bias does not wash out
repeat 30
qubit q = [(0.8660254,0),(0.5,0)]   # p(1) = 0.25
measure q[0]
endrepeat
""",
    'Nested loops': """\
qubit q[3]
repeat 2
qubitop1 q[0] = H
repeat 2
qubitop2 q[0],q[1] = CN
endrepeat
print(q)
endrepeat
""",
    'Conditional correction': """\
# the measurement is random; the final state never is
qubit q[2]
qubitop1 q[0] = H
qubitop2 q[0],q[1] = CN
measure q[0] -> c
if c == 1
qubitop1 q[0] = X
qubitop1 q[1] = X
endif
print(q)                # always |00>
""",
    'if / else if / else': """\
set c = 5
qubit q[2]
if c == 1
qubitop1 q[0] = X
else if c == 5
qubitop1 q[0] = H
else
qubitop1 q[1] = Y
endif
print(q)
""",
    'Loop with a branch': """\
# measure and re-prepare, correcting every 1 back to 0
seed 31
qubit q[1]
repeat 8
qubitop1 q[0] = H
measure q[0] -> c
if c == 1
qubitop1 q[0] = X
endif
endrepeat
print(q)                # always |0>
""",
}

CHEATSHEET = (
    'qubit v[n]                      n-qubit register, |0..0>, n = 1..6\n'
    'qubit v = [(re,im),...]         explicit amplitudes, a power-of-two count\n'
    'qubitop1 v[k] = G               G in H I X Y Z S T SN SDG TDG\n'
    'qubitop2 v[c],v[t] = G          G in CN SW CY CZ CP1..CP6, c and t distinct\n'
    'measure v[k] / measure v        collapse one qubit, or the whole register\n'
    '  ... -> c                      also keep the outcome in classical c\n'
    'seed n                          reseed the measurement PRNG (n nonzero)\n'
    'noise p                         depolarising rate per qubit per gate; 0 disables\n'
    'set c = n                       classical variable, integer valued\n'
    'if x <op> y ... else if ... else ... endif\n'
    '                                <op> in == != < <= > >=; nests 8 deep\n'
    'repeat n ... endrepeat          run the body n times; nests 8 deep\n'
    'print(v)                        show every amplitude\n'
    '# comment                       to end of line, anywhere\n'
    'Variable names are a single character. `end` is added for you.'
)


class App:
    def __init__(self, root):
        self.root = root
        root.title('QuAsm')
        root.geometry('880x620')
        self.queue = queue.Queue()
        self.running = False

        bar = ttk.Frame(root, padding=(8, 8, 8, 4))
        bar.pack(fill='x')
        self.run_btn = ttk.Button(bar, text='Run  (Ctrl+Enter)', command=self.run)
        self.run_btn.pack(side='left')
        ttk.Button(bar, text='Open', command=self.open_file).pack(side='left', padx=(6, 0))
        ttk.Button(bar, text='Save', command=self.save_file).pack(side='left', padx=(6, 0))
        ttk.Button(bar, text='Save output', command=self.save_output).pack(side='left', padx=(6, 0))
        ttk.Button(bar, text='Clear output', command=self.clear_output).pack(side='left', padx=(6, 0))

        ttk.Label(bar, text='Example:').pack(side='left', padx=(16, 4))
        self.example = ttk.Combobox(bar, values=list(EXAMPLES), state='readonly', width=22)
        self.example.pack(side='left')
        self.example.bind('<<ComboboxSelected>>', self.load_example)

        self.check_oracle = tk.BooleanVar(value=HAVE_ORACLE)
        cb = ttk.Checkbutton(bar, text='check vs oracle', variable=self.check_oracle)
        cb.pack(side='left', padx=(16, 0))
        if not HAVE_ORACLE:
            cb.state(['disabled'])

        panes = ttk.PanedWindow(root, orient='vertical')
        panes.pack(fill='both', expand=True, padx=8, pady=4)

        top = ttk.Frame(panes)
        ttk.Label(top, text='Program').pack(anchor='w')
        self.editor = tk.Text(top, height=14, wrap='none', undo=True,
                              font=('Consolas', 11))
        self.editor.pack(fill='both', expand=True)
        panes.add(top, weight=3)

        bottom = ttk.Frame(panes)
        ttk.Label(bottom, text='Output').pack(anchor='w')
        self.output = tk.Text(bottom, height=10, wrap='none', state='disabled',
                              font=('Consolas', 11))
        self.output.pack(fill='both', expand=True)
        self.output.tag_configure('info', foreground='#666666')
        self.output.tag_configure('bad', foreground='#b00020')
        self.output.tag_configure('good', foreground='#0a7d00')
        panes.add(bottom, weight=2)

        self.status = ttk.Label(root, text=CHEATSHEET, justify='left',
                                font=('Consolas', 8), foreground='#555555',
                                padding=(8, 2, 8, 6))
        self.status.pack(fill='x')

        self.editor.insert('1.0', EXAMPLES['Bell pair'])
        self.example.set('Bell pair')
        root.bind('<Control-Return>', lambda e: self.run())
        self.root.after(100, self.drain)

    # -- output helpers -----------------------------------------------------
    def write(self, text, tag=None):
        self.output.configure(state='normal')
        self.output.insert('end', text + '\n', tag)
        self.output.see('end')
        self.output.configure(state='disabled')

    def clear_output(self):
        self.output.configure(state='normal')
        self.output.delete('1.0', 'end')
        self.output.configure(state='disabled')

    # -- actions ------------------------------------------------------------
    def load_example(self, _event=None):
        self.editor.delete('1.0', 'end')
        self.editor.insert('1.0', EXAMPLES[self.example.get()])

    def open_file(self):
        path = filedialog.askopenfilename(
            initialdir=os.path.join(ROOT, 'tests', 'programs'),
            filetypes=[('QuAsm programs', '*.dsl'), ('All files', '*.*')])
        if not path:
            return
        with open(path, encoding='utf-8') as f:
            self.editor.delete('1.0', 'end')
            self.editor.insert('1.0', f.read())

    def save_file(self):
        path = filedialog.asksaveasfilename(
            defaultextension='.dsl',
            initialdir=os.path.join(ROOT, 'tests', 'programs'),
            filetypes=[('QuAsm programs', '*.dsl'), ('All files', '*.*')])
        if path:
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(self.editor.get('1.0', 'end-1c'))

    def save_output(self):
        text = self.output.get('1.0', 'end-1c')
        if not text.strip():
            self.write('no output to save', 'info')
            return
        path = filedialog.asksaveasfilename(
            defaultextension='.txt', initialdir=ROOT,
            filetypes=[('Text', '*.txt'), ('All files', '*.*')])
        if path:
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(text + '\n')
            self.write(f'output saved to {path}', 'info')

    def run(self):
        if self.running:
            return
        lines = program_lines(self.editor.get('1.0', 'end-1c'))
        if not lines:
            self.write('nothing to run', 'info')
            return
        if not os.path.exists(RARS_JAR):
            messagebox.showerror(
                'RARS not found',
                f'No jar at {RARS_JAR}.\nRun tools/fetch_rars.sh first.')
            return
        self.running = True
        self.run_btn.state(['disabled'])
        self.write(f'--- running {len(lines)} line(s) ---', 'info')
        threading.Thread(target=self.worker, args=(lines,), daemon=True).start()

    def worker(self, lines):
        started = time.time()
        try:
            stdout, stderr = run_rars(lines)
        except FileNotFoundError:
            self.queue.put(('bad', f'could not run {JAVA!r} -- is Java on PATH? '
                                   f'(set QUASM_JAVA to override)'))
        except subprocess.TimeoutExpired:
            self.queue.put(('bad', 'RARS timed out'))
        else:
            body = clean_output(stdout)
            self.queue.put((None, body if body else '(no output)'))
            if stderr.strip():
                self.queue.put(('bad', stderr.strip()))
            if self.check_oracle.get():
                status = check_against_oracle(lines, stdout)
                self.queue.put(('bad' if 'MISMATCH' in status else 'good', status))
            self.queue.put(('info', f'--- done in {time.time() - started:.1f}s ---'))
        self.queue.put(('__end__', None))

    def drain(self):
        while True:
            try:
                tag, text = self.queue.get_nowait()
            except queue.Empty:
                break
            if tag == '__end__':
                self.running = False
                self.run_btn.state(['!disabled'])
            else:
                self.write(text, tag)
        self.root.after(100, self.drain)


if __name__ == '__main__':
    root = tk.Tk()
    App(root)
    root.mainloop()
