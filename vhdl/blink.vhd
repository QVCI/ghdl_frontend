library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity blink is
    port (
        clk   : in  std_logic;
        sw    : in  std_logic;
        led   : out std_logic
    );
end entity blink;

architecture rtl of blink is
    signal counter : unsigned(23 downto 0) := (others => '0');
    signal led_reg : std_logic := '0';
begin
    process(clk)
    begin
        if rising_edge(clk) then
            if sw = '1' then
                counter <= (others => '0');
                led_reg <= '0';
            else
                counter <= counter + 1;
                if counter = x"000004" then
                    led_reg <= not led_reg;
                    counter <= (others => '0');
                end if;
            end if;
        end if;
    end process;

    led <= led_reg;
end architecture rtl;