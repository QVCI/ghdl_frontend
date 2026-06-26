"""
orchestrator.py

Given a Project (from project_discovery) compiles all of its VHDL source
files plus a freshly generated testbench, using GHDL, exactly the way
Carlo's known-good tb_tang.vhd setup does (no explicit --std flag, just
GHDL's default).

Compilation order isn't tracked explicitly — VHDL analysis order matters
(a component must be analyzed before the entity that instantiates it).
Instead of building a real dependency graph, we retry: keep analyzing
whatever hasn't succeeded yet, in a loop, until either everything
succeeds or a full pass makes no progress (a real error).
"""
import os
import subprocess
import shutil

from tb_generator import generate_testbench


def _run_ghdl_analyze(workdir, filepath):
    # -fsynopsys: several of Carlo's real practicas use the legacy
    # ieee.std_logic_arith / std_logic_unsigned packages (common in
    # Quartus/Gowin-oriented student code). Stock GHDL refuses them
    # unless this flag is passed. It's a no-op for files that don't
    # use those packages, so it's safe to apply unconditionally.
    return subprocess.run(
        ["ghdl", "-a", "-fsynopsys", "--workdir=" + workdir, filepath],
        capture_output=True, text=True,
    )


def compile_project(proj, base_workdir):
    """
    Returns dict with keys:
        ok: bool
        tb_path: path to generated testbench (always written, even on failure)
        tb_entity: name of testbench entity
        workdir: GHDL work directory used
        log: human-readable log of what happened
        error: error text if ok=False
    """
    log = []
    workdir = os.path.join(base_workdir, _safe_name(proj.label))
    if os.path.exists(workdir):
        shutil.rmtree(workdir)
    os.makedirs(workdir, exist_ok=True)

    if proj.top_entity is None:
        return {
            "ok": False, "tb_path": None, "tb_entity": None,
            "workdir": workdir, "log": "\n".join(log),
            "error": proj.error or "No se pudo determinar la entidad top-level.",
        }

    tb_entity = f"tb_{proj.top_entity.name}"
    tb_code = generate_testbench(proj, tb_entity_name=tb_entity)
    tb_path = os.path.join(workdir, f"{tb_entity}.vhd")
    with open(tb_path, "w", encoding="utf-8") as f:
        f.write(tb_code)
    log.append(f"Testbench generado: {tb_path}")

    pending = list(proj.vhd_files) + [tb_path]
    last_errors = {}

    while pending:
        progressed = False
        still_pending = []
        for f in pending:
            r = _run_ghdl_analyze(workdir, f)
            if r.returncode == 0:
                progressed = True
                log.append(f"  OK   {os.path.basename(f)}")
            else:
                still_pending.append(f)
                last_errors[f] = r.stderr
        pending = still_pending
        if not progressed and pending:
            # Real errors, not just an ordering issue.
            error_text = "\n".join(
                f"--- {os.path.basename(f)} ---\n{last_errors[f]}"
                for f in pending
            )
            return {
                "ok": False, "tb_path": tb_path, "tb_entity": tb_entity,
                "workdir": workdir, "log": "\n".join(log),
                "error": error_text,
            }

    log.append("Análisis (ghdl -a) completado para todos los archivos.")

    r = subprocess.run(
        ["ghdl", "-e", "-fsynopsys", "--workdir=" + workdir, tb_entity],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return {
            "ok": False, "tb_path": tb_path, "tb_entity": tb_entity,
            "workdir": workdir, "log": "\n".join(log),
            "error": "Elaboración falló:\n" + r.stderr,
        }
    log.append(f"Elaboración (ghdl -e {tb_entity}) OK.")

    return {
        "ok": True, "tb_path": tb_path, "tb_entity": tb_entity,
        "workdir": workdir, "log": "\n".join(log), "error": None,
    }


def _safe_name(label: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in label)