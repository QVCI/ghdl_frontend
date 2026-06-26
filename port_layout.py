"""
port_layout.py

Single source of truth for how an entity's ports map onto the wire
protocol's X<hex> input word. Both tb_generator.py (writes the VHDL that
reads X<hex>) and the runtime simulator (writes the X<hex> commands)
import this module, so the two sides can never drift out of sync on bit
ordering.
"""
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from vhdl_introspect import Entity, Port


def is_clock(p: Port) -> bool:
    return p.direction == "in" and p.width == 1 and p.name.lower() == "clk"


@dataclass
class PortLayout:
    clk_port: Optional[Port]
    data_in_ports: List[Port]                  # all inputs except clk, in declaration order
    out_ports: List[Port]                       # out + inout, in declaration order
    total_in_bits: int
    nhex_in: int                                 # hex chars needed for X<hex>
    in_slices: List[Tuple[Port, int, int]]       # (port, hi, lo), MSB-first packing


def compute_layout(ent: Entity) -> PortLayout:
    clk_port = next((p for p in ent.ports if is_clock(p)), None)
    data_in_ports = [p for p in ent.ports if p.direction == "in" and p is not clk_port]
    out_ports = [p for p in ent.ports if p.direction in ("out", "inout")]

    total_in_bits = sum(p.width for p in data_in_ports)
    nhex_in = math.ceil(total_in_bits / 4) if total_in_bits > 0 else 0

    slices = []
    cursor = total_in_bits
    for p in data_in_ports:
        hi = cursor - 1
        lo = cursor - p.width
        slices.append((p, hi, lo))
        cursor = lo

    return PortLayout(
        clk_port=clk_port,
        data_in_ports=data_in_ports,
        out_ports=out_ports,
        total_in_bits=total_in_bits,
        nhex_in=nhex_in,
        in_slices=slices,
    )


def pack_inputs(layout: PortLayout, values: dict) -> str:
    """
    values: {port_name (any case): int}  -- int value for that port's bits,
    (e.g. a 1-bit port is 0/1, a vector port is its unsigned value).
    Returns the hex string to send after 'X'.
    """
    if layout.total_in_bits == 0:
        return ""
    acc = 0
    for p, hi, lo in layout.in_slices:
        v = 0
        for key in values:
            if key.lower() == p.name.lower():
                v = int(values[key])
                break
        width = hi - lo + 1
        v &= (1 << width) - 1  # clamp to declared width
        acc |= v << lo
    nbits = layout.nhex_in * 4
    return format(acc, f"0{layout.nhex_in}X")[-layout.nhex_in:] if layout.nhex_in else ""