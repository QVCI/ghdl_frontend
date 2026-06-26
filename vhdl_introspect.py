"""
vhdl_introspect.py

Parses one or more .vhd files (VHDL-93 / VHDL-2008 subset) to extract
entity declarations and their port lists.

Public API
----------
    parse_file(path)  -> list[Entity]
    parse_files(paths) -> list[Entity]

Data classes
------------
    Port(name, direction, width)
    Entity(name, ports, source_file)

Limitations (by design — enough for student / hobbyist FPGA code):
  - Only explicit downto / to ranges are handled (e.g. "7 downto 0").
  - Generics are not parsed (they don't appear in the port list).
  - Comments inside port declarations may confuse the parser.
  - VHDL is case-insensitive; names are normalised to lower-case.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Port:
    name: str          # lower-case
    direction: str     # "in" | "out" | "inout" | "buffer"
    width: int         # 1 for std_logic, N for std_logic_vector


@dataclass
class Entity:
    name: str                       # lower-case
    ports: List[Port] = field(default_factory=list)
    source_file: Optional[str] = None

    def inputs(self):
        return [p for p in self.ports if p.direction == "in"]

    def outputs(self):
        return [p for p in self.ports if p.direction in ("out", "inout", "buffer")]


# ── helpers ──────────────────────────────────────────────────────────────────

_STRIP_COMMENTS = re.compile(r"--[^\n]*")

def _clean(text: str) -> str:
    """Remove VHDL line comments and normalise whitespace."""
    text = _STRIP_COMMENTS.sub(" ", text)
    return text


# Match:  entity <name> is
_ENTITY_START = re.compile(
    r"\bentity\s+(\w+)\s+is\b", re.IGNORECASE
)

# Match:  end [entity] [<name>] ;
_ENTITY_END = re.compile(
    r"\bend\s*(?:entity\s*)?(?:\w+\s*)?;", re.IGNORECASE
)

# Match:  port (
_PORT_SECTION = re.compile(
    r"\bport\s*\(", re.IGNORECASE
)

# One port declaration (may cover multiple names with the same type):
#   name1 [, name2 ...] : direction type ;
# We use a loose match and refine below.
_PORT_LINE = re.compile(
    r"([\w\s,]+?)\s*:\s*(in|out|inout|buffer)\s+(.*?)(?:;|$)",
    re.IGNORECASE | re.DOTALL,
)

# std_logic_vector(N downto 0) or (N to 0)
_VECTOR_RANGE = re.compile(
    r"std_logic_vector\s*\(\s*(\d+)\s+(downto|to)\s+(\d+)\s*\)",
    re.IGNORECASE,
)

_STD_LOGIC = re.compile(r"\bstd_logic\b", re.IGNORECASE)


def _parse_width(type_str: str) -> int:
    """Return bit-width from a VHDL type string; 1 for std_logic."""
    m = _VECTOR_RANGE.search(type_str)
    if m:
        hi, direction, lo = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        return abs(hi - lo) + 1
    if _STD_LOGIC.search(type_str):
        return 1
    # unknown type — treat as 1 bit rather than failing
    return 1


def _extract_port_section(text: str) -> Optional[str]:
    """
    Return the raw text between 'port (' and the matching ')' that closes
    the port list (not the entity end-paren).
    """
    m = _PORT_SECTION.search(text)
    if not m:
        return None
    start = m.end()
    depth = 1
    i = start
    while i < len(text) and depth > 0:
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
        i += 1
    return text[start: i - 1]  # contents between the outer parens


def _parse_ports(port_text: str) -> List[Port]:
    """Parse a port-section string into Port objects."""
    ports: List[Port] = []
    # Split on semicolons; each chunk is one port declaration (possibly
    # multiple names sharing the same type).
    chunks = port_text.split(";")
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        m = _PORT_LINE.match(chunk)
        if not m:
            continue
        names_raw, direction, type_str = m.group(1), m.group(2), m.group(3)
        direction = direction.lower()
        width = _parse_width(type_str.strip())
        for raw_name in names_raw.split(","):
            name = raw_name.strip().lower()
            if name:
                ports.append(Port(name=name, direction=direction, width=width))
    return ports


def parse_file(path: str) -> List[Entity]:
    """
    Parse a single .vhd file.  Returns a (possibly empty) list of Entity
    objects found in the file.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
    except OSError:
        return []

    text = _clean(raw)
    entities: List[Entity] = []

    pos = 0
    while True:
        m_start = _ENTITY_START.search(text, pos)
        if not m_start:
            break
        entity_name = m_start.group(1).lower()
        body_start = m_start.end()

        # Find the matching 'end' keyword
        m_end = _ENTITY_END.search(text, body_start)
        body_end = m_end.end() if m_end else len(text)
        body = text[body_start:body_end]

        port_text = _extract_port_section(body)
        ports = _parse_ports(port_text) if port_text else []

        entities.append(Entity(name=entity_name, ports=ports, source_file=path))
        pos = body_end

    return entities


def parse_files(paths) -> List[Entity]:
    """Parse multiple .vhd files and return all found entities."""
    result = []
    for p in paths:
        result.extend(parse_file(p))
    return result
