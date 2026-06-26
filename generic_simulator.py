"""
generic_simulator.py

Runtime counterpart to tb_generator.py. Drives a compiled generic
testbench (see orchestrator.compile_project) for ANY discovered project,
using the X<hex>/S<n> protocol and parsing "OUT <name> <bits>" lines.

Cross-platform execution:
  - On Windows, GHDL's mcode backend's `-e` step produces a real,
    directly-runnable <entity>.exe (this is what Carlo's existing,
    validated tb_tang setup already relies on).
  - On Linux mcode (this sandbox), `-e` only elaborates internally; you
    run the design with `ghdl -r -fsynopsys --workdir=... <entity>`.
  Both paths are supported automatically: we use the .exe if present,
  otherwise fall back to `ghdl -r`.
"""
import subprocess, os, threading, time, queue, sys

from port_layout import PortLayout, pack_inputs


class GenericBoardState:
    """Holds the latest known value of every output (and inout) port."""

    def __init__(self, out_ports):
        self.out_ports = out_ports
        self.bits = {p.name: "0" * p.width for p in out_ports}

    def parse(self, lines):
        for line in lines:
            parts = line.strip().split()
            if len(parts) != 3 or parts[0] != "OUT":
                continue
            _, name, bitstr = parts
            self.bits[name] = bitstr

    def snapshot(self):
        """Returns {port_name: {"bits": "0101", "value": 5, "width": 4}}"""
        out = {}
        for p in self.out_ports:
            bitstr = self.bits.get(p.name, "0" * p.width)
            try:
                value = int(bitstr, 2)
            except ValueError:
                value = 0
            out[p.name] = {"bits": bitstr, "value": value, "width": p.width}
        return out


class GenericSimulator:
    """
    One live GHDL process for a single compiled project. Mirrors the
    threading architecture of the original Simulator class (dedicated
    stdout/stderr reader threads, timeout-protected command/response
    pairing, auto-respawn on death) generalized to arbitrary ports.
    """

    def __init__(self, workdir, tb_entity, layout: PortLayout,
                 on_state_update=None, steps_per_frame=100, fps=30):
        self.workdir         = workdir
        self.tb_entity       = tb_entity
        self.layout          = layout
        self.on_state_update = on_state_update
        self.steps_per_frame = steps_per_frame
        self.fps             = fps

        self._lock    = threading.Lock()
        self._running = False
        self._thread  = None
        self._proc    = None
        self._q       = queue.Queue()
        self._reader  = None

        # current values for every data-input port (by name, case-insensitive
        # lookup handled in pack_inputs); default 0
        self.input_values = {p.name: 0 for p in layout.data_in_ports}
        self._inputs_dirty = True  # force one X<hex> on first frame

        self._board = GenericBoardState(layout.out_ports)

    # ── public API ──────────────────────────────────────────────────
    def start(self):
        if not self._spawn():
            return False
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._running = False
        self._kill()

    def set_input(self, port_name: str, value: int):
        with self._lock:
            for key in list(self.input_values.keys()):
                if key.lower() == port_name.lower():
                    self.input_values[key] = int(value)
                    self._inputs_dirty = True
                    return

    def get_output_snapshot(self):
        return self._board.snapshot()

    # ── process management ──────────────────────────────────────────
    def _exe_path(self):
        return os.path.join(self.workdir, self.tb_entity + ".exe")

    def _spawn_cmd(self):
        exe = self._exe_path()
        if os.path.exists(exe):
            return [exe, "--unbuffered"]
        return ["ghdl", "-r", "-fsynopsys", "--workdir=" + self.workdir, self.tb_entity]

    def _spawn(self):
        try:
            p = subprocess.Popen(
                self._spawn_cmd(),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, bufsize=0,
            )
            self._proc = p
            while not self._q.empty():
                self._q.get_nowait()
            self._reader = threading.Thread(target=self._read_stdout, daemon=True)
            self._reader.start()
            threading.Thread(target=self._read_stderr, daemon=True).start()
            return True
        except Exception as e:
            print(f"[GenericSimulator] Popen error: {e}", file=sys.stderr, flush=True)
            return False

    def _read_stdout(self):
        try:
            for raw in self._proc.stdout:
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    self._q.put(line)
        except Exception:
            pass
        self._q.put(None)  # sentinel: process ended

    def _read_stderr(self):
        try:
            for raw in self._proc.stderr:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    print(f"[ghdl stderr] {line}", file=sys.stderr, flush=True)
        except Exception:
            pass

    def _kill(self):
        p, self._proc = self._proc, None
        if p:
            try:
                p.terminate(); p.wait(timeout=2)
            except Exception:
                try: p.kill()
                except Exception: pass

    def _alive(self):
        return self._proc and self._proc.poll() is None

    def _send(self, cmd: str):
        self._proc.stdin.write((cmd + "\n").encode())
        self._proc.stdin.flush()

    def _recv(self, timeout=4.0):
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return "TIMEOUT"

    def _send_and_read_block(self, cmd: str, n_lines: int, timeout: float):
        self._send(cmd)
        lines = []
        for _ in range(n_lines):
            line = self._recv(timeout=timeout)
            if line is None:
                return lines, "dead"
            if line == "TIMEOUT":
                return lines, "timeout"
            lines.append(line)
        return lines, "ok"

    # ── main loop ────────────────────────────────────────────────────
    def _loop(self):
        n_out_lines = len(self.layout.out_ports)
        first_frame = True

        while self._running:
            if not self._alive():
                if not self._spawn():
                    time.sleep(1)
                    continue
                first_frame = True

            with self._lock:
                dirty = self._inputs_dirty
                values = dict(self.input_values)
                self._inputs_dirty = False
                steps = self.steps_per_frame

            timeout = 15.0 if first_frame else 4.0
            died = False
            all_lines = []

            try:
                if dirty and self.layout.total_in_bits > 0:
                    hexstr = pack_inputs(self.layout, values)
                    lines, status = self._send_and_read_block(f"X{hexstr}", n_out_lines, timeout)
                    all_lines = lines
                    if status != "ok":
                        died = True
                    timeout = 4.0

                if not died and self.layout.clk_port is not None:
                    lines, status = self._send_and_read_block(f"S{steps}", n_out_lines, timeout)
                    all_lines = lines  # most recent snapshot wins
                    if status != "ok":
                        died = True

                if died:
                    self._kill()
                else:
                    first_frame = False
                    if all_lines:
                        self._board.parse(all_lines)
                        if self.on_state_update:
                            self.on_state_update(self._board.snapshot())

            except Exception as e:
                print(f"[GenericSimulator] loop error: {e}", file=sys.stderr, flush=True)
                self._kill()

            time.sleep(1 / self.fps)

        self._running = False