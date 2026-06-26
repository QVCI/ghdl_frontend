library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- Tang Nano 9K board model
-- Switches: 16 total (SW1-SW16), active-high or active-low configurable
-- LEDs: 16 total in 4 groups, active-high or active-low configurable
-- 7-segment: 4 multiplexed displays, shared pins 71-79 with LED group 2/3/4
-- Jumper LEDS/DISPLAY selects which peripheral uses shared pins

entity tang_nano_9k is
    generic (
        SW_ACTIVE_HIGH  : boolean := true;   -- true = UP means '1'
        LED_ACTIVE_HIGH : boolean := true;   -- true = '1' turns LED on
        CLK_DIV         : integer := 16       -- divide 27MHz sim clock
    );
    port (
        clk         : in  std_logic;
        -- 16 switches
        sw          : in  std_logic_vector(15 downto 0);
        -- 16 LEDs (groups 1-4)
        led         : out std_logic_vector(15 downto 0);
        -- 7-segment: digit select (4 digits) + segments (a-g + dp)
        seg_digit   : out std_logic_vector(3 downto 0);  -- which digit active
        seg_segs    : out std_logic_vector(7 downto 0);  -- a,b,c,d,e,f,g,dp
        -- jumper: '1' = DISPLAY mode, '0' = LEDS mode (for shared pins)
        jumper_disp : in  std_logic
    );
end entity tang_nano_9k;

architecture rtl of tang_nano_9k is
    -- Internal logic: a simple counter-based demo
    -- 4-bit binary counter displayed on LEDs group 1
    -- Switches SW1-SW4 control reset, direction, speed, enable
    -- Display shows counter value as decimal digits (BCD)

    signal clk_div_cnt : unsigned(7 downto 0) := (others => '0');
    signal clk_slow    : std_logic := '0';

    signal counter     : unsigned(15 downto 0) := (others => '0');
    signal direction   : std_logic := '0';   -- sw(1): 0=up, 1=down
    signal enable      : std_logic := '1';

    -- Display mux
    signal dig_sel     : unsigned(1 downto 0) := "00";
    signal mux_cnt     : unsigned(9 downto 0) := (others => '0');

    -- BCD digits (registered, updated every slow clock)
    signal d0, d1, d2, d3 : unsigned(3 downto 0) := (others => '0');

    -- 7-seg encoding: a,b,c,d,e,f,g,dp (active high here, invert outside if needed)
    function to_seg(digit : unsigned(3 downto 0)) return std_logic_vector is
        variable s : std_logic_vector(7 downto 0);
    begin
        case digit is
            when x"0" => s := "11111100"; -- 0: a-f on, g off
            when x"1" => s := "01100000"; -- 1
            when x"2" => s := "11011010"; -- 2
            when x"3" => s := "11110010"; -- 3
            when x"4" => s := "01100110"; -- 4
            when x"5" => s := "10110110"; -- 5
            when x"6" => s := "10111110"; -- 6
            when x"7" => s := "11100000"; -- 7
            when x"8" => s := "11111110"; -- 8
            when x"9" => s := "11110110"; -- 9
            when others => s := "00000010"; -- '-'
        end case;
        return s;
    end function;

begin
    -- Effective switch value (handle active-low polarity via generic)
    direction <= sw(1) when SW_ACTIVE_HIGH else not sw(1);
    enable    <= not sw(0) when SW_ACTIVE_HIGH else sw(0);

    -- Slow clock divider
    process(clk)
    begin
        if rising_edge(clk) then
            clk_div_cnt <= clk_div_cnt + 1;
            if clk_div_cnt = CLK_DIV - 1 then
                clk_div_cnt <= (others => '0');
                clk_slow <= not clk_slow;
            end if;
        end if;
    end process;

    -- Main counter
    process(clk_slow)
    begin
        if rising_edge(clk_slow) then
            if enable = '0' then
                counter <= (others => '0');
            elsif direction = '0' then
                counter <= counter + 1;
            else
                counter <= counter - 1;
            end if;
        end if;
    end process;

    -- BCD conversion via successive subtraction (safe, no division)
    process(clk_slow)
        variable tmp : unsigned(15 downto 0);
    begin
        if rising_edge(clk_slow) then
            tmp := counter;
            -- clamp to 9999
            if tmp >= 10000 then tmp := tmp - 10000; end if;
            if tmp >= 10000 then tmp := (others => '0'); end if;
            -- thousands
            d3 <= (others => '0');
            if tmp >= 9000 then tmp := tmp - 9000; d3 <= "1001";
            elsif tmp >= 8000 then tmp := tmp - 8000; d3 <= "1000";
            elsif tmp >= 7000 then tmp := tmp - 7000; d3 <= "0111";
            elsif tmp >= 6000 then tmp := tmp - 6000; d3 <= "0110";
            elsif tmp >= 5000 then tmp := tmp - 5000; d3 <= "0101";
            elsif tmp >= 4000 then tmp := tmp - 4000; d3 <= "0100";
            elsif tmp >= 3000 then tmp := tmp - 3000; d3 <= "0011";
            elsif tmp >= 2000 then tmp := tmp - 2000; d3 <= "0010";
            elsif tmp >= 1000 then tmp := tmp - 1000; d3 <= "0001";
            end if;
            -- hundreds
            d2 <= (others => '0');
            if tmp >= 900 then tmp := tmp - 900; d2 <= "1001";
            elsif tmp >= 800 then tmp := tmp - 800; d2 <= "1000";
            elsif tmp >= 700 then tmp := tmp - 700; d2 <= "0111";
            elsif tmp >= 600 then tmp := tmp - 600; d2 <= "0110";
            elsif tmp >= 500 then tmp := tmp - 500; d2 <= "0101";
            elsif tmp >= 400 then tmp := tmp - 400; d2 <= "0100";
            elsif tmp >= 300 then tmp := tmp - 300; d2 <= "0011";
            elsif tmp >= 200 then tmp := tmp - 200; d2 <= "0010";
            elsif tmp >= 100 then tmp := tmp - 100; d2 <= "0001";
            end if;
            -- tens
            d1 <= (others => '0');
            if tmp >= 90 then tmp := tmp - 90; d1 <= "1001";
            elsif tmp >= 80 then tmp := tmp - 80; d1 <= "1000";
            elsif tmp >= 70 then tmp := tmp - 70; d1 <= "0111";
            elsif tmp >= 60 then tmp := tmp - 60; d1 <= "0110";
            elsif tmp >= 50 then tmp := tmp - 50; d1 <= "0101";
            elsif tmp >= 40 then tmp := tmp - 40; d1 <= "0100";
            elsif tmp >= 30 then tmp := tmp - 30; d1 <= "0011";
            elsif tmp >= 20 then tmp := tmp - 20; d1 <= "0010";
            elsif tmp >= 10 then tmp := tmp - 10; d1 <= "0001";
            end if;
            -- units
            d0 <= tmp(3 downto 0);
        end if;
    end process;

    -- Display multiplexer
    process(clk)
    begin
        if rising_edge(clk) then
            mux_cnt <= mux_cnt + 1;
            if mux_cnt = 0 then
                dig_sel <= dig_sel + 1;
            end if;
        end if;
    end process;

    -- LED outputs (group 1 = counter bits 0-3, group 2 = bits 4-7, etc.)
    -- Generics are elaboration-time constants: use concurrent assignment
    led <= std_logic_vector(counter) when LED_ACTIVE_HIGH else
           not std_logic_vector(counter);

    -- 7-seg outputs
    process(dig_sel, d0, d1, d2, d3)
    begin
        case dig_sel is
            when "00" =>
                seg_digit <= "1110"; seg_segs <= to_seg(d0);
            when "01" =>
                seg_digit <= "1101"; seg_segs <= to_seg(d1);
            when "10" =>
                seg_digit <= "1011"; seg_segs <= to_seg(d2);
            when others =>
                seg_digit <= "0111"; seg_segs <= to_seg(d3);
        end case;
    end process;

end architecture rtl;