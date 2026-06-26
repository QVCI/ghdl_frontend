"""
project_discovery.py

Given a directory (or a list of .vhd files), discover the project
structure:
  - Find all .vhd files recursively.
  - Parse every entity declared in them.
  - Heuristically determine which entity is the top-level (not
    instantiated by any other entity in the set).
  - Return a Project object ready for orchestrator.compile_project().

Public API
----------
    discover(path_or_files) -> Project

    path_or_files:
        str   – path to a directory  (scans recursively for *.vhd / *.vhdl)
        list  – explicit list of .vhd file paths

Data classes
------------
    Project(label, vhd_files, top_entity, error)
"""

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

from vhdl_introspect import Entity, parse_files, parse_file


@dataclass
class Project:
    label: str                          # human-readable name
    vhd_files: List[str]                # all source files (absolute paths)
    top_entity: Optional[Entity]        # resolved top-level entity
    all_entities: List[Entity] = field(default_factory=list)
    error: Optional[str] = None         # set if something went wrong


# ── file discovery ────────────────────────────────────────────────────────────

def _find_vhd_files(directory: str) -> List[str]:
    found = []
    for root, _, files in os.walk(directory):
        for fname in files:
            if fname.lower().endswith((".vhd", ".vhdl")):
                found.append(os.path.join(root, fname))
    return sorted(found)


# ── top-level heuristic ───────────────────────────────────────────────────────

_INSTANTIATION_RE = re.compile(
    # Matches:   entity work.<name>    or    component <name>
    r"(?:entity\s+work\s*\.\s*(\w+)|component\s+(\w+))",
    re.IGNORECASE,
)

def _find_instantiated_names(vhd_files: List[str]) -> set:
    """
    Return the lower-case set of entity names that are *instantiated*
    somewhere in the given file set.
    """
    names = set()
    strip_comments = re.compile(r"--[^\n]*")
    for path in vhd_files:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        text = strip_comments.sub(" ", text)
        for m in _INSTANTIATION_RE.finditer(text):
            name = (m.group(1) or m.group(2) or "").lower()
            if name:
                names.add(name)
    return names


# Testbench heuristics: entities with no outputs or whose names start
# with "tb_" / "testbench" are not considered candidate top-levels
_TB_PREFIX = re.compile(r"^(tb_|testbench)", re.IGNORECASE)


def _is_testbench(ent: Entity) -> bool:
    if _TB_PREFIX.match(ent.name):
        return True
    if not ent.outputs():
        return True
    return False


def _pick_top(entities: List[Entity], instantiated: set) -> Optional[Entity]:
    """
    Choose the top-level entity.  Preference order:
      1. Only one non-testbench entity that is never instantiated.
      2. The non-testbench entity with the most ports (likely most complex).
      3. Any non-testbench entity.
    """
    candidates = [
        e for e in entities
        if not _is_testbench(e) and e.name not in instantiated
    ]
    if not candidates:
        # Relax: ignore instantiation filter
        candidates = [e for e in entities if not _is_testbench(e)]
    if not candidates:
        candidates = list(entities)

    if not candidates:
        return None

    # Prefer the one with the most ports
    candidates.sort(key=lambda e: -len(e.ports))
    return candidates[0]


# ── public API ────────────────────────────────────────────────────────────────

def discover(path_or_files) -> Project:
    """
    Discover a VHDL project.

    Parameters
    ----------
    path_or_files : str | list[str]
        Either a directory path (scanned recursively) or an explicit list
        of .vhd / .vhdl source files.

    Returns
    -------
    Project
    """
    if isinstance(path_or_files, str):
        directory = os.path.abspath(path_or_files)
        label = os.path.basename(directory)
        vhd_files = _find_vhd_files(directory)
    else:
        vhd_files = [os.path.abspath(p) for p in path_or_files]
        label = os.path.basename(os.path.dirname(vhd_files[0])) if vhd_files else "project"

    if not vhd_files:
        return Project(
            label=label, vhd_files=[], top_entity=None,
            error="No se encontraron archivos .vhd en la ruta indicada.",
        )

    all_entities = parse_files(vhd_files)

    if not all_entities:
        return Project(
            label=label, vhd_files=vhd_files, top_entity=None,
            all_entities=[],
            error="No se encontraron declaraciones de entidad en los archivos VHDL.",
        )

    instantiated = _find_instantiated_names(vhd_files)
    top = _pick_top(all_entities, instantiated)

    return Project(
        label=label,
        vhd_files=vhd_files,
        top_entity=top,
        all_entities=all_entities,
        error=None if top else "No se pudo determinar la entidad top-level.",
    )
