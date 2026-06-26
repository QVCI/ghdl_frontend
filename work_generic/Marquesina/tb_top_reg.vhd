library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;

entity tb_top_reg is
end entity tb_top_reg;

architecture sim of tb_top_reg is
    signal sig_clk : std_logic := '0';
    signal sig_clr : std_logic := '0';
    signal sig_led : std_logic := '0';
    signal sig_display : std_logic_vector(6 downto 0) := (others => '0');
    signal sig_tran : std_logic_vector(3 downto 0) := (others => '0');
    signal sig_ledapagado : std_logic_vector(5 downto 0) := (others => '0');
    signal all_in : std_logic_vector(0 downto 0) := (others => '0');

begin

    UUT: entity work.top_reg
        port map (
            clk => sig_clk,
            clr => sig_clr,
            led => sig_led,
            display => sig_display,
            tran => sig_tran,
            ledapagado => sig_ledapagado
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
        variable acc     : unsigned(3 downto 0);

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
            write(lout, string'("OUT led "));
            if sig_led = '1' then write(lout, string'("1"));
            else write(lout, string'("0")); end if;
            writeline(std.textio.output, lout);
            write(lout, string'("OUT display "));
            for i in 6 downto 0 loop
                if sig_display(i) = '1' then write(lout, string'("1"));
                else write(lout, string'("0")); end if;
            end loop;
            writeline(std.textio.output, lout);
            write(lout, string'("OUT tran "));
            for i in 3 downto 0 loop
                if sig_tran(i) = '1' then write(lout, string'("1"));
                else write(lout, string'("0")); end if;
            end loop;
            writeline(std.textio.output, lout);
            write(lout, string'("OUT ledapagado "));
            for i in 5 downto 0 loop
                if sig_ledapagado(i) = '1' then write(lout, string'("1"));
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
                n := 1;
                read(lin, tmp, ok);
                if ok then n := tmp; end if;
                for k in 1 to n loop
                    wait until rising_edge(sig_clk);
                end loop;
                wait for 1 ns;  -- let chained signal assignments settle

            elsif cmd = 'X' then
                acc := (others => '0');
                for i in 1 to 1 loop
                    read(lin, hexchar, good);
                    if good then nibble := hex_nibble(hexchar);
                    else nibble := 0; end if;
                    acc := to_unsigned(nibble, 4);
                end loop;
                all_in <= std_logic_vector(acc(0 downto 0));
                sig_clr <= acc(0);
                wait for 1 ns;

            else
                next;
            end if;

            emit_state;
        end loop;
        wait;
    end process;

end architecture sim;
