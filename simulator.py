import subprocess, os, threading, time, shutil, queue

WORK_DIR = "work"

SWITCH_PINS    = [[38,37,36,39],[25,26,27,28],[29,30,33,34],[40,35,41,42]]
LED_PINS       = [[63,86,85,84],[83,82,81,80],[79,77,76,75],[74,73,72,71]]
SEG_PINS       = {'a':74,'b':73,'c':72,'d':71,'e':79,'f':77,'g':76,'dp':75}
SEG_DIGIT_PINS = [3,4,5,6]

_active_proc      = None
_active_proc_lock = threading.Lock()


def _kill_active():
    global _active_proc
    with _active_proc_lock:
        p, _active_proc = _active_proc, None
    if p:
        try: p.terminate(); p.wait(timeout=2)
        except Exception:
            try: p.kill()
            except Exception: pass
    time.sleep(0.4)


def compile_vhdl(files, top_entity):
    _kill_active()
    os.makedirs(WORK_DIR, exist_ok=True)
    for f in files:
        r = subprocess.run(["ghdl","-a","--workdir="+WORK_DIR,f],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return False, r.stderr
    exe_dst = os.path.join(WORK_DIR, top_entity+".exe")
    for _ in range(8):
        try:
            if os.path.exists(exe_dst): os.remove(exe_dst)
            break
        except PermissionError:
            time.sleep(0.4)
    r = subprocess.run(["ghdl","-e","--workdir="+WORK_DIR,top_entity],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return False, r.stderr
    src = top_entity+".exe"
    if os.path.exists(src):
        shutil.move(src, exe_dst)
    return True, ""


class BoardState:
    def __init__(self):
        self.leds           = [False]*16
        self.seg_digit      = [True]*4
        self.seg_segs       = [False]*8
        self.display_digits = ["00000000"]*4

    def parse(self, lines):
        for line in lines:
            parts = line.strip().split()
            if not parts: continue
            if parts[0]=="LED" and len(parts)==2 and len(parts[1])==16:
                self.leds = [b=='1' for b in parts[1]]
            elif parts[0]=="SEG" and len(parts)==3:
                self.seg_digit = [b=='1' for b in parts[1]]
                self.seg_segs  = [b=='1' for b in parts[2]]
                for i,d in enumerate(self.seg_digit):
                    if not d:
                        self.display_digits[i] = parts[2]

    def snapshot(self):
        return {
            "leds":           list(self.leds),
            "seg_digit":      list(self.seg_digit),
            "seg_segs":       list(self.seg_segs),
            "display_digits": list(self.display_digits),
        }


class Simulator:
    """
    Keeps one GHDL process alive for the whole session.

    Architecture:
    - A dedicated _reader thread reads stdout line-by-line and puts lines
      into a Queue. This avoids blocking the main loop on Windows pipes.
    - The main _loop thread writes commands to stdin and reads responses
      from the queue with a timeout.

    Protocol: every command (W, D, S) produces exactly 2 output lines
    (LED + SEG), because emit_state is called after every command in tb_tang.
    """

    def __init__(self, top_entity, on_state_update,
                 sw_active_high=True, led_active_high=True,
                 steps_per_frame=100, fps=30):
        self.top_entity      = top_entity
        self.on_state_update = on_state_update
        self.sw_active_high  = sw_active_high
        self.led_active_high = led_active_high
        self.steps_per_frame = steps_per_frame
        self.fps             = fps

        self._lock    = threading.Lock()
        self._running = False
        self._thread  = None
        self._proc    = None
        self._q       = queue.Queue()
        self._reader  = None

        self.sw_state       = [False]*16
        self.jumper_display = False
        self._board         = BoardState()

    # ── public ──────────────────────────────────────────────────────────────

    def start(self):
        if not self._spawn():
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        self._kill()

    def set_switch(self, index, value):
        with self._lock: self.sw_state[index] = value

    def set_jumper(self, display_mode):
        with self._lock: self.jumper_display = display_mode

    # ── private ─────────────────────────────────────────────────────────────

    def _sw_word(self):
        val = 0
        for i,s in enumerate(self.sw_state):
            if (s if self.sw_active_high else not s):
                val |= 1 << (15-i)
        return f"{val:04X}"

    def _spawn(self):
        global _active_proc
        exe = os.path.join(WORK_DIR, self.top_entity+".exe")
        if not os.path.exists(exe):
            print("exe not found", flush=True)
            return False
        try:
            p = subprocess.Popen(
                [exe, "--unbuffered"],
                stdin =subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
            self._proc = p
            with _active_proc_lock:
                _active_proc = p
            # Drain any stale data then start reader threads
            while not self._q.empty():
                self._q.get_nowait()
            self._reader = threading.Thread(
                target=self._read_stdout, daemon=True)
            self._reader.start()
            self._stderr_reader = threading.Thread(
                target=self._read_stderr, daemon=True)
            self._stderr_reader.start()
            self._first_frame = True
            print("process spawned", flush=True)
            return True
        except Exception as e:
            print(f"Popen error: {e}", flush=True)
            return False

    def _read_stdout(self):
        """Dedicated thread: reads stdout line by line into the queue."""
        try:
            for raw in self._proc.stdout:
                line = raw.decode("utf-8", errors="replace").strip()
                print(f"[stdout] {line!r}", flush=True)
                if line:
                    self._q.put(line)
        except Exception as e:
            print(f"[stdout reader error] {e}", flush=True)
        self._q.put(None)   # sentinel: process ended

    def _read_stderr(self):
        """Dedicated thread: reads stderr line by line and prints it.
        This is critical for diagnosing GHDL assertion failures, since
        GHDL writes runtime errors to stderr, not stdout."""
        try:
            for raw in self._proc.stderr:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    print(f"[stderr] {line}", flush=True)
        except Exception:
            pass

    def _kill(self):
        global _active_proc
        with _active_proc_lock:
            p, _active_proc = _active_proc, None
        self._proc = None
        if p:
            try: p.terminate(); p.wait(timeout=2)
            except Exception:
                try: p.kill()
                except Exception: pass

    def _alive(self):
        return self._proc and self._proc.poll() is None

    def _send(self, cmd: str):
        self._proc.stdin.write((cmd+"\n").encode())
        self._proc.stdin.flush()

    def _recv(self, timeout=4.0):
        """Get one line from the reader queue."""
        try:
            line = self._q.get(timeout=timeout)
            return line   # None = sentinel (process died)
        except queue.Empty:
            return "TIMEOUT"

    def _send_and_read_pair(self, cmd: str, timeout: float):
        """Send one command, then read its LED+SEG reply pair.
        Returns (lines, status) where status is 'ok', 'timeout', or 'dead'.
        Sending one command at a time (instead of firing W/D/S all at once)
        lets us see exactly which command stalls."""
        print(f"[send] {cmd!r}", flush=True)
        self._send(cmd)
        lines = []
        for _ in range(2):
            line = self._recv(timeout=timeout)
            if line is None:
                return lines, "dead"
            if line == "TIMEOUT":
                return lines, "timeout"
            lines.append(line)
        return lines, "ok"

    def _loop(self):
        # Each command produces 2 lines (LED + SEG).
        # We send W, D, S one at a time, reading each pair as it comes,
        # so a stall is attributable to a specific command.
        first_frame_after_spawn = True

        while self._running:
            if not self._alive():
                print("process died, respawning…", flush=True)
                if not self._spawn():
                    time.sleep(1)
                    continue
                first_frame_after_spawn = True

            with self._lock:
                sw_word = self._sw_word()
                jmp     = self.jumper_display
                steps   = self.steps_per_frame

            # GHDL can take noticeably longer to respond on the very first
            # command after the process is spawned (runtime init, first
            # Windows pipe round-trip). Give that one a generous timeout so
            # we don't kill a perfectly healthy process before it has even
            # had a chance to answer.
            timeout = 15.0 if first_frame_after_spawn else 4.0

            try:
                all_lines = []
                died = False
                for cmd in (f"W{sw_word}", f"D{'1' if jmp else '0'}", f"S{steps}"):
                    lines, status = self._send_and_read_pair(cmd, timeout)
                    all_lines.extend(lines)
                    if status == "dead":
                        print(f"process ended (sentinel) after sending {cmd!r}", flush=True)
                        self._kill()
                        died = True
                        break
                    if status == "timeout":
                        print(f"timeout waiting for response to {cmd!r}", flush=True)
                        self._kill()
                        died = True
                        break
                    # only the very first command of the first frame needs
                    # the generous timeout; subsequent commands this frame
                    # use the normal one
                    timeout = 4.0

                if not died:
                    first_frame_after_spawn = False
                    relevant = [l for l in all_lines
                                if l.startswith("LED") or l.startswith("SEG")]
                    self._board.parse(relevant[-2:] if len(relevant)>=2 else relevant)
                    snap = self._board.snapshot()
                    if not self.led_active_high:
                        snap["leds"] = [not v for v in snap["leds"]]
                    if self.on_state_update:
                        self.on_state_update(snap)

            except Exception as e:
                print(f"loop error: {e}", flush=True)
                self._kill()

            time.sleep(1/self.fps)

        self._running = False