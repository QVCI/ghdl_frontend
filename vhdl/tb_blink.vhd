library ieee;
use ieee.std_logic_1164.all;
use std.textio.all;

entity tb_blink is
end entity tb_blink;

architecture sim of tb_blink is
    signal clk : std_logic := '0';
    signal sw  : std_logic := '0';
    signal led : std_logic;
begin
    UUT: entity work.blink
        port map (clk => clk, sw => sw, led => led);

    clk_proc: process
    begin
        clk <= '0'; wait for 5 ns;
        clk <= '1'; wait for 5 ns;
    end process;

    ctrl_proc: process
        variable lin  : line;
        variable lout : line;
        variable cmd  : character;
        variable good : boolean;
    begin
        loop
            readline(std.textio.input, lin);
            read(lin, cmd, good);
            if not good then next; end if;

            if cmd = '1' then
                sw <= '1';
                wait for 1 ns;
            elsif cmd = '0' then
                sw <= '0';
                wait for 1 ns;
            elsif cmd = 'S' then
                wait until rising_edge(clk);
            else
                next;
            end if;

            write(lout, string'("LED "));
            if led = '1' then
                write(lout, string'("1"));
            else
                write(lout, string'("0"));
            end if;
            writeline(std.textio.output, lout);
        end loop;
        wait;
    end process;

end architecture sim;