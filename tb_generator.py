"""
tb_generator.py

Generates a generic VHDL testbench for any top-level Entity discovered by
project_discovery. Protocol over stdin/stdout (one command per line):

    S          -> advance 1 rising clock edge, then emit outputs
    S<N>       -> advance N rising clock edges, then emit outputs
    X<hex>     -> set ALL non-clock input ports at once (concatenated in
                  declaration order, MSB-first) from a hex string, then
                  emit outputs. Does NOT advance the clock.

Output per command: one line per output (and inout) port, in declaration
order:
    OUT <PORTNAME> <bits>

where <bits> is a binary string, MSB-first, of the port's declared width.

Design notes (kept deliberately simple to avoid the bit-ordering bug we
hit last time with manual per-bit indexing):
  - All non-clock inputs are packed into one big unsigned via the same
    shift-and-accumulate pattern as a hex parser: each hex digit shifts
    the accumulator left by 4 and ORs in the new nibble. First hex digit
    read = most-significant nibble. This matches how the existing,
    validated W-command in tb_tang.vhd already works.
  - Each port then gets a literal, Python-computed slice of that
    accumulator (no runtime index variables), so there is no off-by-one
    risk in the generated VHDL itself.
"""
import math
from project_discovery import Project
from vhdl_introspect import Port
from port_layout import compute_layout


CLOCK_PERIOD_NS = 10  # 5ns/5ns, same as the validated tb_tang.vhd


def generate_testbench(proj: Project, tb_entity_name: str = None) -> str:
    ent = proj.top_entity
    if ent is None:
        raise ValueError(f"Project {proj.label} has no resolved top entity")

    tb_name = tb_entity_name or f"tb_{ent.name}"

    layout = compute_layout(ent)
    clk_port = layout.clk_port
    data_in_ports = layout.data_in_ports
    out_ports = layout.out_ports
    total_in_bits = layout.total_in_bits
    nhex = layout.nhex_in
    acc_bits = nhex * 4
    slices = layout.in_slices

    lines = []
    lines.append("library ieee;")
    lines.append("use ieee.std_logic_1164.all;")
    lines.append("use ieee.numeric_std.all;")
    lines.append("use std.textio.all;")
    lines.append("")
    lines.append(f"entity {tb_name} is")
    lines.append(f"end entity {tb_name};")
    lines.append("")
    lines.append(f"architecture sim of {tb_name} is")

    # Signal declarations: one per port, default '0' / all-zeros.
    for p in ent.ports:
        if p.width == 1:
            lines.append(f"    signal sig_{p.name} : std_logic := '0';")
        else:
            lines.append(
                f"    signal sig_{p.name} : std_logic_vector({p.width-1} downto 0)"
                f" := (others => '0');"
            )
    if total_in_bits > 0:
        lines.append(f"    signal all_in : std_logic_vector({total_in_bits-1} downto 0) := (others => '0');")

    lines.append("")
    lines.append(f"begin")
    lines.append("")

    # UUT instantiation
    lines.append(f"    UUT: entity work.{ent.name}")
    lines.append("        port map (")
    portmap_lines = [f"            {p.name} => sig_{p.name}" for p in ent.ports]
    lines.append(",\n".join(portmap_lines))
    lines.append("        );")
    lines.append("")

    # Clock process
    if clk_port is not None:
        half = CLOCK_PERIOD_NS // 2
        lines.append("    clk_proc: process")
        lines.append("    begin")
        lines.append(f"        sig_{clk_port.name} <= '0'; wait for {half} ns;")
        lines.append(f"        sig_{clk_port.name} <= '1'; wait for {half} ns;")
        lines.append("    end process;")
        lines.append("")

    # Control process
    lines.append("    ctrl_proc: process")
    lines.append("        variable lin     : line;")
    lines.append("        variable lout    : line;")
    lines.append("        variable cmd     : character;")
    lines.append("        variable good    : boolean;")
    lines.append("        variable ok      : boolean;")
    lines.append("        variable n       : integer;")
    lines.append("        variable tmp     : integer;")
    lines.append("        variable hexchar : character;")
    lines.append("        variable nibble  : integer;")
    if acc_bits > 0:
        lines.append(f"        variable acc     : unsigned({acc_bits-1} downto 0);")

    lines.append("")
    lines.append("        function hex_nibble(c : character) return integer is")
    lines.append("        begin")
    lines.append("            case c is")
    lines.append("                when '0' => return 0; when '1' => return 1;")
    lines.append("                when '2' => return 2; when '3' => return 3;")
    lines.append("                when '4' => return 4; when '5' => return 5;")
    lines.append("                when '6' => return 6; when '7' => return 7;")
    lines.append("                when '8' => return 8; when '9' => return 9;")
    lines.append("                when 'a'|'A' => return 10; when 'b'|'B' => return 11;")
    lines.append("                when 'c'|'C' => return 12; when 'd'|'D' => return 13;")
    lines.append("                when 'e'|'E' => return 14; when 'f'|'F' => return 15;")
    lines.append("                when others  => return 0;")
    lines.append("            end case;")
    lines.append("        end function;")
    lines.append("")
    lines.append("        procedure emit_state is")
    lines.append("        begin")
    for p in out_ports:
        if p.width == 1:
            lines.append(f'            write(lout, string\'("OUT {p.name} "));')
            lines.append(f"            if sig_{p.name} = '1' then write(lout, string'(\"1\"));")
            lines.append(f"            else write(lout, string'(\"0\")); end if;")
            lines.append("            writeline(std.textio.output, lout);")
        else:
            lines.append(f'            write(lout, string\'("OUT {p.name} "));')
            lines.append(f"            for i in {p.width-1} downto 0 loop")
            lines.append(f"                if sig_{p.name}(i) = '1' then write(lout, string'(\"1\"));")
            lines.append(f"                else write(lout, string'(\"0\")); end if;")
            lines.append("            end loop;")
            lines.append("            writeline(std.textio.output, lout);")
    lines.append("        end procedure;")
    lines.append("")
    lines.append("    begin")
    lines.append("        loop")
    lines.append("            readline(std.textio.input, lin);")
    lines.append("            read(lin, cmd, good);")
    lines.append("            if not good then next; end if;")
    lines.append("")
    lines.append("            if cmd = 'S' then")
    lines.append("                n := 1;")
    lines.append("                read(lin, tmp, ok);")
    lines.append("                if ok then n := tmp; end if;")
    if clk_port is not None:
        lines.append("                for k in 1 to n loop")
        lines.append(f"                    wait until rising_edge(sig_{clk_port.name});")
        lines.append("                end loop;")
        lines.append("                wait for 1 ns;  -- let chained signal assignments settle")
    else:
        lines.append("                wait for 1 ns;")
    lines.append("")
    if acc_bits > 0:
        lines.append("            elsif cmd = 'X' then")
        lines.append(f"                acc := (others => '0');")
        lines.append(f"                for i in 1 to {nhex} loop")
        lines.append("                    read(lin, hexchar, good);")
        lines.append("                    if good then nibble := hex_nibble(hexchar);")
        lines.append("                    else nibble := 0; end if;")
        if acc_bits > 4:
            lines.append(f"                    acc := acc({acc_bits-5} downto 0) & to_unsigned(nibble, 4);")
        else:
            lines.append(f"                    acc := to_unsigned(nibble, 4);")
        lines.append("                end loop;")
        lines.append(f"                all_in <= std_logic_vector(acc({total_in_bits-1} downto 0));")
        for p, hi, lo in slices:
            if p.width == 1:
                lines.append(f"                sig_{p.name} <= acc({lo});")
            else:
                lines.append(f"                sig_{p.name} <= std_logic_vector(acc({hi} downto {lo}));")
        lines.append("                wait for 1 ns;")
        lines.append("")
    lines.append("            else")
    lines.append("                next;")
    lines.append("            end if;")
    lines.append("")
    lines.append("            emit_state;")
    lines.append("        end loop;")
    lines.append("        wait;")
    lines.append("    end process;")
    lines.append("")
    lines.append("end architecture sim;")
    lines.append("")

    return "\n".join(lines)