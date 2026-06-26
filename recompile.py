"""
Run this ONCE from the ghdl_frontend folder to force a clean recompile.
It deletes the old exe and recompiles from scratch.
"""
import os, shutil, subprocess, time

WORK_DIR = "work"
TOP      = "tb_tang"
FILES    = ["vhdl/tang_nano_9k.vhd", "vhdl/tb_tang.vhd"]

exe = os.path.join(WORK_DIR, TOP + ".exe")

# 1. Kill any process holding the file (best-effort via taskkill on Windows)
try:
    subprocess.run(["taskkill", "/F", "/IM", TOP+".exe"], 
                   capture_output=True)
    time.sleep(0.5)
except Exception:
    pass

# 2. Force-delete the exe
for _ in range(10):
    try:
        if os.path.exists(exe):
            os.remove(exe)
            print(f"Deleted {exe}")
        break
    except PermissionError as e:
        print(f"Still locked, retrying... ({e})")
        time.sleep(0.5)

# 3. Reanalyse
print("\n--- Analysing VHDL ---")
for f in FILES:
    r = subprocess.run(["ghdl", "-a", "--workdir="+WORK_DIR, f],
                       capture_output=True, text=True)
    print(f"  {f}: {'OK' if r.returncode==0 else 'FAIL'}")
    if r.returncode != 0:
        print(r.stderr)
        raise SystemExit(1)

# 4. Elaborate
print("\n--- Elaborating ---")
r = subprocess.run(["ghdl", "-e", "--workdir="+WORK_DIR, TOP],
                   capture_output=True, text=True)
print(f"  Elaborate: {'OK' if r.returncode==0 else 'FAIL'}")
if r.returncode != 0:
    print(r.stderr)
    raise SystemExit(1)

src = TOP + ".exe"
if os.path.exists(src):
    shutil.move(src, exe)
    print(f"  Moved to {exe}")

# 5. Quick smoke test
print("\n--- Smoke test ---")
r = subprocess.run([exe], input=b"S1\n",
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                   timeout=5)
print(f"  returncode : {r.returncode}")
print(f"  stdout     : {r.stdout!r}")
print(f"  stderr     : {r.stderr!r}")