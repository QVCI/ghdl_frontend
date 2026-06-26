import subprocess, os

exe = os.path.join("work", "tb_tang.exe")
print(f"exe exists: {os.path.exists(exe)}")

# Run with one command and capture everything
result = subprocess.run(
    [exe],
    input=b"S1\n",
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    timeout=5,
)
print(f"returncode: {result.returncode}")
print(f"stdout: {result.stdout!r}")
print(f"stderr: {result.stderr!r}")