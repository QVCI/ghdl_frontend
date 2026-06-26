import subprocess
import os
import sys

VHDL_DIR = "vhdl"
WORK_DIR = "work"

def run(cmd):
    print(f"  >> {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())
    if result.returncode != 0:
        print(f"ERROR: codigo {result.returncode}")
        sys.exit(1)

def compile():
    os.makedirs(WORK_DIR, exist_ok=True)
    print("\n[1] Analizando...")
    run(["ghdl", "-a", "--workdir=" + WORK_DIR, os.path.join(VHDL_DIR, "blink.vhd")])
    run(["ghdl", "-a", "--workdir=" + WORK_DIR, os.path.join(VHDL_DIR, "tb_blink.vhd")])
    print("\n[2] Elaborando...")
    run(["ghdl", "-e", "--workdir=" + WORK_DIR, "tb_blink"])
    print("  OK")

def simulate():
    print("\n[3] Simulando...")

    # Todos los comandos de una vez
    commands = "\n".join([
        "S",   # step
        "S",   # step
        "1",   # sw = 1
        "S",
        "0",   # sw = 0
        "S",
        "S",
        "Q",   # quit
    ]) + "\n"

    print(f"  Enviando comandos:\n{commands}")

    proc = subprocess.run(
        ["ghdl", "-r", "--workdir=" + WORK_DIR, "tb_blink", "--stop-time=1ms"],
        input=commands,
        capture_output=True,
        text=True,
        timeout=10,
    )

    print(f"  STDOUT:\n{proc.stdout}")
    if proc.stderr:
        print(f"  STDERR:\n{proc.stderr}")
    print(f"  Codigo de retorno: {proc.returncode}")

if __name__ == "__main__":
    compile()
    simulate()