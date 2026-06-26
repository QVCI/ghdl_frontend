library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;

entity tb_toplevel is
end entity tb_toplevel;

architecture sim of tb_toplevel is
    signal sig_pre : std_logic := '0';
    signal sig_clr : std_logic := '0';
    signal sig_s : std_logic := '0';
    signal sig_r : std_logic := '0';
    signal sig_t : std_logic := '0';
    signal sig_d : std_logic := '0';
    signal sig_j : std_logic := '0';
    signal sig_k : std_logic := '0';
    signal sig_sel : std_logic_vector(1 downto 0) := (others => '0');
    signal sig_q : std_logic := '0';
    signal sig_nq : std_logic := '0';
    signal sig_led : std_logic := '0';
    signal sig_clk : std_logic := '0';
    signal all_in : std_logic_vector(9 downto 0) := (others => '0');

begin

    UUT: entity work.toplevel
        port map (
            pre => sig_pre,
            clr => sig_clr,
            s => sig_s,
            r => sig_r,
            t => sig_t,
            d => sig_d,
            j => sig_j,
            k => sig_k,
            sel => sig_sel,
            q => sig_q,
            nq => sig_nq,
            led => sig_led,
            clk => sig_clk
        );

    clk_proc: process
    begin
        sig_clk <= '0'; wait for 5 ns;
        sig_clk <= '1'; wait for 5 ns;
    end process;

    ctrl_proc: process
        variable lin     : line;
        variable lout    : line;
        variable cmd     : character;
        variable good    : boolean;
        variable ok      : boolean;
        variable n       : integer;
        variable tmp     : integer;
        variable hexchar : character;
        variable nibble  : integer;
        variable acc     : unsigned(11 downto 0);

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
            write(lout, string'("OUT q "));
            if sig_q = '1' then write(lout, string'("1"));
            else write(lout, string'("0")); end if;
            writeline(std.textio.output, lout);
            write(lout, string'("OUT nq "));
            if sig_nq = '1' then write(lout, string'("1"));
            else write(lout, string'("0")); end if;
            writeline(std.textio.output, lout);
            write(lout, string'("OUT led "));
            if sig_led = '1' then write(lout, string'("1"));
            else write(lout, string'("0")); end if;
            writeline(std.textio.output, lout);
        end procedure;

    begin
        loop
            readline(std.textio.input, lin);
            read(lin, cmd, good);
            if not good then next; end if;

            if cmd = 'S' then
                n := 1;
                read(lin, tmp, ok);
                if ok then n := tmp; end if;
                for k in 1 to n loop
                    wait until rising_edge(sig_clk);
                end loop;
                wait for 1 ns;  -- let chained signal assignments settle

            elsif cmd = 'X' then
                acc := (others => '0');
                for i in 1 to 3 loop
                    read(lin, hexchar, good);
                    if good then nibble := hex_nibble(hexchar);
                    else nibble := 0; end if;
                    acc := acc(7 downto 0) & to_unsigned(nibble, 4);
                end loop;
                all_in <= std_logic_vector(acc(9 downto 0));
                sig_pre <= acc(9);
                sig_clr <= acc(8);
                sig_s <= acc(7);
                sig_r <= acc(6);
                sig_t <= acc(5);
                sig_d <= acc(4);
                sig_j <= acc(3);
                sig_k <= acc(2);
                sig_sel <= std_logic_vector(acc(1 downto 0));
                wait for 1 ns;

            else
                next;
            end if;

            emit_state;
        end loop;
        wait;
    end process;

end architecture sim;
