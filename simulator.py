import subprocess
import os
import threading
import time
import shutil

WORK_DIR = "work"


def compile_vhdl(files, top_entity):
    os.makedirs(WORK_DIR, exist_ok=True)
    for f in files:
        result = subprocess.run(
            ["ghdl", "-a", "--workdir=" + WORK_DIR, f],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return False, result.stderr

    exe_dst = os.path.join(WORK_DIR, top_entity + ".exe")
    if os.path.exists(exe_dst):
        os.remove(exe_dst)

    result = subprocess.run(
        ["ghdl", "-e", "--workdir=" + WORK_DIR, top_entity],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return False, result.stderr

    exe_src = top_entity + ".exe"
    if os.path.exists(exe_src):
        shutil.move(exe_src, exe_dst)
    return True, ""


class Simulator:
    def __init__(self, top_entity, on_state_update):
        self.top_entity = top_entity
        self.on_state_update = on_state_update
        self._thread = None
        self._running = False
        self._lock = threading.Lock()
        self.inputs = {"sw": 0}

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def set_input(self, name, value):
        with self._lock:
            self.inputs[name] = value

    def _run_batch(self, commands):
        exe = os.path.join(WORK_DIR, self.top_entity + ".exe")
        # Sin Q al final — EOF termina el exe
        batch = ("\n".join(commands) + "\n").encode("utf-8")
        try:
            result = subprocess.run(
                [exe],
                input=batch,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
                timeout=5,
            )
            output = result.stdout.decode("utf-8", errors="replace")
            lines = [l for l in output.strip().splitlines() if l.startswith("LED")]
            print(f"batch={len(commands)} responses={lines}", flush=True)
            return lines
        except subprocess.TimeoutExpired:
            print("TIMEOUT", flush=True)
            return []
        except Exception as e:
            print(f"Error: {e}", flush=True)
            return []

    def _loop(self):
        STEPS_PER_FRAME = 10

        while self._running:
            with self._lock:
                sw = self.inputs["sw"]

            cmds = ["1" if sw else "0"]
            for _ in range(STEPS_PER_FRAME):
                cmds.append("S")

            responses = self._run_batch(cmds)

            if responses:
                last = responses[-1]
                parts = last.strip().split()
                if len(parts) == 2:
                    try:
                        state = {parts[0]: int(parts[1])}
                        if self.on_state_update:
                            self.on_state_update(state)
                    except ValueError:
                        pass

            time.sleep(1 / 30)

        self._running = False