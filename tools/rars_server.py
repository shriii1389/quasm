"""Runs QuAsm programs through one long-lived RARS process instead of one JVM
per program.

A cold `java -jar rars1_6.jar` re-assembles all ~3,000 lines of the
interpreter before it runs a single statement, and that start-up is nearly all
of the ~7s a program used to cost. QuasmServer.java assembles once and then
runs any number of programs through the same RARS simulator, restoring the
assembled memory image before each one.

Nothing here is a second implementation: the programs run on RARS, from the
same main.s, through the same syscalls. What changes is only how often the JVM
starts. Two things are checked rather than assumed, by `check()`: that no
state leaks from one program into the next, and that the output is
byte-for-byte what the command line produces for the same input.

Set QUASM_RARS=cli to bypass the server and use the command line throughout.
"""
import os
import subprocess
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
JAR = os.path.join(HERE, 'rars1_6.jar')
SRC = os.path.join(HERE, 'QuasmServer.java')
BUILD = os.path.join(HERE, 'build')
JAVA = os.environ.get('QUASM_JAVA', 'java')
JAVAC = os.environ.get('QUASM_JAVAC', 'javac')

# A runaway program (`repeat 4000000000`) stops here and reports MAX_STEPS,
# which is the server's stand-in for the command line's wall-clock timeout.
MAX_STEPS = 200_000_000

# RARS's simulator thread drops its own priority below normal as it starts
# (Thread.setPriority(4) in Simulator$SimThread.run). On an idle machine that
# costs nothing; on a busy one it starves the simulation outright -- it runs
# only when a core would otherwise sit idle. With thread priorities ignored it
# competes on equal terms, no more. Every launcher uses these flags.
JVM_FLAGS = ['-XX:-UseThreadPriorities']

_compile_lock = threading.Lock()
_local = threading.local()


def _compile():
    cls = os.path.join(BUILD, 'QuasmServer.class')
    with _compile_lock:
        if os.path.exists(cls) and os.path.getmtime(cls) >= os.path.getmtime(SRC):
            return
        os.makedirs(BUILD, exist_ok=True)
        subprocess.run([JAVAC, '-cp', JAR, '-d', BUILD, SRC], check=True,
                       capture_output=True)


class Server:
    """One QuasmServer process, serving one interpreter source file."""

    def __init__(self, main_path, max_steps=None):
        _compile()
        self.main_path = main_path
        self._err = tempfile.TemporaryFile()
        self.proc = subprocess.Popen(
            [JAVA] + JVM_FLAGS + ['-cp', JAR + os.pathsep + BUILD, 'QuasmServer',
                                  main_path, str(max_steps or MAX_STEPS)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._err)

    def run(self, text, max_steps=None):
        """(reason, output) for one program's stdin text. `max_steps` caps
        this run alone, as the command line's numeric argument does."""
        data = text.encode('utf-8')
        cap = f' {max_steps}' if max_steps else ''
        try:
            self.proc.stdin.write(f'{len(data)}{cap}\n'.encode() + data)
            self.proc.stdin.flush()
            header = self.proc.stdout.readline().decode()
            reason, n = header.split()
            out = self.proc.stdout.read(int(n)).decode('utf-8')
        except (OSError, ValueError):
            self._err.seek(0)
            raise RuntimeError('QuasmServer failed: '
                               + self._err.read().decode(errors='replace')[:2000])
        return reason, out

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


def _source_digest(main_path):
    """A digest of every .s file beside main_path. The server assembles once,
    so an edited source -- mutate.py rewrites its workspace in place between
    mutants -- has to mean a fresh server, not a stale image."""
    import hashlib
    h = hashlib.sha256()
    folder = os.path.dirname(main_path)
    for name in sorted(os.listdir(folder)):
        if name.endswith('.s'):
            with open(os.path.join(folder, name), 'rb') as f:
                h.update(name.encode() + b'|' + f.read())
    return h.hexdigest()


def server_for(main_path):
    """This thread's server for `main_path`, started on first use and
    restarted whenever the source it assembled has changed."""
    servers = getattr(_local, 'servers', None)
    if servers is None:
        servers = _local.servers = {}
    path = os.path.abspath(main_path)
    digest = _source_digest(path)
    s = servers.get(path)
    if s is not None and (s.digest != digest or s.proc.poll() is not None):
        s.close()
        s = None
    if s is None:
        s = servers[path] = Server(path)
        s.digest = digest
    return s


def close_all():
    for s in getattr(_local, 'servers', {}).values():
        s.close()
    _local.servers = {}


def run(main_path, text):
    return server_for(main_path).run(text)[1]


def run_cli(main_path, text, timeout=600):
    proc = subprocess.run([JAVA] + JVM_FLAGS + ['-jar', JAR, 'nc', 'sm', main_path],
                          input=text.encode('utf-8'), capture_output=True,
                          timeout=timeout)
    return proc.stdout.decode('utf-8')


def check(main_path, compare_cli=True):
    """Returns a list of problems (empty if the server can be trusted).

    Isolation: a program that declares a register, sets a classical variable
    and advances the PRNG must leave nothing behind for the next one.
    Fidelity: the same inputs must produce the same bytes as the command line.
    """
    problems = []
    s = Server(os.path.abspath(main_path))
    try:
        first = 'qubit q[1]\nset c = 7\nqubitop1 q[0] = H\nmeasure q[0]\nmeasure q[0]\nend\n'
        probe = 'print(q)\nif c == 7\nendif\nqubit r[1]\nqubitop1 r[0] = H\nmeasure r[0]\nmeasure r[0]\nend\n'
        _, a = s.run(first)
        _, b = s.run(probe)
        _, a2 = s.run(first)
        if 'Variable not declared' not in b:
            problems.append(f'register state leaked between runs: {b!r}')
        if a != a2:
            problems.append(f'the same program gave different output on a rerun '
                            f'(PRNG state leaked?): {a!r} vs {a2!r}')
        if compare_cli:
            for text in (first, probe, 'qubit a = [(0.6,0),(0.8,0)]\nprint(a)\n'
                         'qubitop1 a[0] = SDG\nprint(a)\nend\n'):
                _, got = s.run(text)
                want = run_cli(main_path, text)
                if got != want:
                    problems.append(f'server and command line differ on {text!r}:\n'
                                    f'  server: {got!r}\n  cli:    {want!r}')
    finally:
        s.close()
    return problems


if __name__ == '__main__':
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(HERE), 'main.s')
    found = check(target)
    for p in found:
        print(f'[FAIL] {p}')
    print('[PASS] server isolated and byte-identical to the command line'
          if not found else f'{len(found)} problem(s)')
    sys.exit(1 if found else 0)
