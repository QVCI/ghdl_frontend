library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;

entity tb_tang is
end entity tb_tang;

architecture sim of tb_tang is
    signal clk         : std_logic := '0';
    signal sw          : std_logic_vector(15 downto 0) := (others => '0');
    signal led         : std_logic_vector(15 downto 0);
    signal seg_digit   : std_logic_vector(3 downto 0);
    signal seg_segs    : std_logic_vector(7 downto 0);
    signal jumper_disp : std_logic := '0';
begin

    UUT: entity work.tang_nano_9k
        generic map (
            SW_ACTIVE_HIGH  => true,
            LED_ACTIVE_HIGH => true,
            CLK_DIV         => 4
        )
        port map (
            clk         => clk,
            sw          => sw,
            led         => led,
            seg_digit   => seg_digit,
            seg_segs    => seg_segs,
            jumper_disp => jumper_disp
        );

    clk_proc: process
    begin
        clk <= '0'; wait for 5 ns;
        clk <= '1'; wait for 5 ns;
    end process;

    -- Protocol over stdin/stdout:
    --   Commands (one per line):
    --     S            -> advance one rising clock edge, then emit state
    --     SN           -> advance N rising edges (e.g. S100), then emit state
    --     Wxx          -> set sw[15:0] from 16-bit hex (e.g. W0003 sets sw0+sw1)
    --     D0 / D1      -> jumper DISPLAY off/on
    --   Output per command:
    --     LED <hex16>
    --     SEG <digit_nibble> <segs_byte>
    --     (both lines always emitted after every command)

    ctrl_proc: process
        variable lin    : line;
        variable lout   : line;
        variable cmd    : character;
        variable good   : boolean;
        variable n      : integer;
        variable hexstr : string(1 to 4);
        variable sw_val : std_logic_vector(15 downto 0);
        variable hexchar: character;
        variable nibble : integer;
        variable tmp    : integer;
        variable ok     : boolean;

        function hex_nibble(c : character) return integer is
        begin
            case c is
                when '0' => return 0; when '1' => return 1;
                when '2' => return 2; when '3' => return 3;
                when '4' => return 4; when '5' => return 5;
                when '6' => return 6; when '7' => return 7;
                when '8' => return 8; when '9' => return 9;
                when 'a'|'A' => return 10; when 'b'|'B' => return 11;
                when 'c'|'C' => return 12; when 'd'|'D' => return 13;
                when 'e'|'E' => return 14; when 'f'|'F' => return 15;
                when others  => return 0;
            end case;
        end function;

        procedure emit_state is
        begin
            -- LED line
            write(lout, string'("LED "));
            for i in 15 downto 0 loop
                if led(i) = '1' then
                    write(lout, string'("1"));
                else
                    write(lout, string'("0"));
                end if;
            end loop;
            writeline(std.textio.output, lout);
            -- SEG line: digit nibble (4 bits) + space + segs byte (8 bits)
            write(lout, string'("SEG "));
            for i in 3 downto 0 loop
                if seg_digit(i) = '1' then write(lout, string'("1"));
                else write(lout, string'("0")); end if;
            end loop;
            write(lout, string'(" "));
            for i in 7 downto 0 loop
                if seg_segs(i) = '1' then write(lout, string'("1"));
                else write(lout, string'("0")); end if;
            end loop;
            writeline(std.textio.output, lout);
        end procedure;

    begin
        loop
            readline(std.textio.input, lin);
            read(lin, cmd, good);
            if not good then next; end if;

            if cmd = 'S' then
                -- Read optional integer N after 'S'
                n := 1;
                read(lin, tmp, ok);
                if ok then n := tmp; end if;
                for k in 1 to n loop
                    wait until rising_edge(clk);
                end loop;

            elsif cmd = 'W' then
                -- Read 4 hex chars for sw[15:0]
                for i in 1 to 4 loop
                    read(lin, hexchar, good);
                    if good then hexstr(i) := hexchar;
                    else hexstr(i) := '0'; end if;
                end loop;
                sw_val :=
                    std_logic_vector(to_unsigned(hex_nibble(hexstr(1)), 4)) &
                    std_logic_vector(to_unsigned(hex_nibble(hexstr(2)), 4)) &
                    std_logic_vector(to_unsigned(hex_nibble(hexstr(3)), 4)) &
                    std_logic_vector(to_unsigned(hex_nibble(hexstr(4)), 4));
                sw <= sw_val;
                wait for 1 ns;

            elsif cmd = 'D' then
                read(lin, hexchar, good);
                if good and hexchar = '1' then
                    jumper_disp <= '1';
                else
                    jumper_disp <= '0';
                end if;
                wait for 1 ns;

            else
                next;
            end if;

            emit_state;
        end loop;
        wait;
    end process;

end architecture sim;