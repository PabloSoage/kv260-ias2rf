// SPDX-License-Identifier: Apache-2.0
// Artix-7 Debug UART (115,200 baud 8N1 default on PMOD_SPARE1 RX / PMOD_SPARE2 TX)
// Clocked from 125 MHz link_clk (MMCM 100 MHz PFD -> 1000 MHz VCO -> /8 = 125.000 MHz
// identical in both 400 MHz and 500 MHz master modes; div=1085 -> 115,207.4 baud, +0.0064% err).
//
// Features (REV08 G-1):
//   - Boot banner on clock lock/switch: design name, build date/time, git hash, clk mode, eth build
//   - Periodic key=value status line (1 Hz default, disableable via CSR, triggerable via 's')
//   - Interactive CSR monitor (4th CSR master alongside IAS1 downlink, UDP, Pmod SPI):
//       r <addr>          -> <8hex>\r\n
//       w <addr> <value>  -> ok\r\n
//       s                 -> immediate STAT line
//       h                 -> help summary
//     Hex, case-insensitive, backspace, echo (when no banner/status active), 'err\r\n' on bad input.
//   - Break / low-line / framing-error resilient: waits for stop-bit/idle high before re-arming.

`timescale 1ns/1ps
`default_nettype none

module dbg_uart #(
    parameter [31:0] BUILD_DATE       = 32'h2026_1116, // YYYYMMDD packed BCD
    parameter [31:0] BUILD_TIME       = 32'h0000_0000, // 00HHMMSS packed BCD
    parameter [31:0] GIT_HASH         = 32'hDEAD_C0DE, // 8-hex git short hash
    parameter [0:0]  ENABLE_ETH       = 1'b1,
    parameter [15:0] DEFAULT_BAUD_DIV = 16'd1085,      // 125 MHz / 1085 = 115,207.37 baud (+64 ppm)
    parameter [31:0] DEFAULT_STAT_CYC = 32'd125_000_000
) (
    input  wire        clk,
    input  wire        rst,

    // Physical Pmod J1102 pins (LVCMOS33)
    input  wire        uart_rx,
    output reg         uart_tx,

    // Configuration (CSR 0xF0 / 0xF4 in clk domain)
    input  wire [15:0] cfg_baud_div,
    input  wire [31:0] cfg_stat_cyc,
    input  wire        cfg_status_dis,
    input  wire        force_stat_p,

    // Live telemetry inputs (clk domain)
    input  wire        st_xo_ok,
    input  wire        st_xo_500m,
    input  wire        st_sys_mmcm,
    input  wire        st_eth_mmcm,
    input  wire        st_adcr_mmcm,
    input  wire [2:0]  st_dl_state,
    input  wire        st_dl_l0_lock,
    input  wire        st_dl_link_up,
    input  wire        st_eth_link_up,
    input  wire        st_eth_copper_up,
    input  wire        st_adcr_trained,
    input  wire        st_adcs_aligned,
    input  wire [15:0] st_adcr_clip_cnt,
    input  wire [15:0] st_adcs_clip_cnt,
    input  wire [11:0] st_xadc_temp_raw,
    input  wire [15:0] st_hk_tmp_raw,
    input  wire [6:0]  st_err_flags_lo,
    input  wire        st_radar_dis,

    // Diagnostic status back to CSR 0xF0
    output wire        rx_idle_high,
    output wire        tx_busy_o,
    output reg         banner_done,
    output reg  [4:0]  rx_ferr_cnt,

    // 4th CSR Master Port (clk domain arbiter)
    output reg         csr_req_valid,
    output reg         csr_req_wr,
    output reg  [15:0] csr_req_addr,
    output reg  [31:0] csr_req_wdata,
    input  wire        csr_req_ack,
    input  wire [31:0] csr_req_rdata
);

`ifdef MUTATE_WRONG_DIVISOR
    wire [15:0] eff_baud_div = (cfg_baud_div < 16'd8) ? 16'd8 : (cfg_baud_div >> 1);
`else
    wire [15:0] eff_baud_div = (cfg_baud_div < 16'd4) ? 16'd4 : cfg_baud_div;
`endif
    wire [31:0] eff_stat_cyc = (cfg_stat_cyc == 32'd0) ? DEFAULT_STAT_CYC : cfg_stat_cyc;

    // -------------------------------------------------------------------------
    // 1. UART TX Engine (8N1)
    // -------------------------------------------------------------------------
    reg         tx_active;
    reg  [9:0]  tx_shift;
    reg  [3:0]  tx_bit_cnt;
    reg  [15:0] tx_div_cnt;
    reg         tx_start;
    reg  [7:0]  tx_byte_in;

    assign tx_busy_o = tx_active;

    always @(posedge clk) begin
        if (rst) begin
            uart_tx    <= 1'b1;
            tx_active  <= 1'b0;
            tx_shift   <= 10'h3FF;
            tx_bit_cnt <= 4'd0;
            tx_div_cnt <= 16'd0;
        end else begin
            if (!tx_active) begin
                uart_tx <= 1'b1;
                if (tx_start) begin
                    tx_shift   <= {1'b1, tx_byte_in, 1'b0}; // Stop(1), Data[7:0], Start(0)
                    tx_active  <= 1'b1;
                    tx_bit_cnt <= 4'd9;
                    tx_div_cnt <= eff_baud_div - 16'd1;
                    uart_tx    <= 1'b0;
                end
            end else begin
                if (tx_div_cnt == 16'd0) begin
                    if (tx_bit_cnt == 4'd0) begin
                        tx_active <= 1'b0;
                        uart_tx   <= 1'b1;
                    end else begin
                        tx_shift   <= {1'b1, tx_shift[9:1]};
                        uart_tx    <= tx_shift[1];
                        tx_bit_cnt <= tx_bit_cnt - 4'd1;
                        tx_div_cnt <= eff_baud_div - 16'd1;
                    end
                end else begin
                    tx_div_cnt <= tx_div_cnt - 16'd1;
                end
            end
        end
    end

    // -------------------------------------------------------------------------
    // 2. UART RX Engine (8N1, BREAK / framing-error resilient)
    // -------------------------------------------------------------------------
    (* ASYNC_REG = "TRUE" *) reg [2:0] rx_sync_r = 3'b111;
    always @(posedge clk) begin
        if (rst) rx_sync_r <= 3'b111;
        else     rx_sync_r <= {rx_sync_r[1:0], uart_rx};
    end
    wire rx_s = rx_sync_r[2];
    assign rx_idle_high = rx_s;

    localparam [2:0] RX_IDLE      = 3'd0,
                     RX_START     = 3'd1,
                     RX_DATA      = 3'd2,
                     RX_STOP      = 3'd3,
                     RX_WAIT_HIGH = 3'd4;

    reg  [2:0]  rx_state;
    reg  [15:0] rx_div_cnt;
    reg  [2:0]  rx_bit_idx;
    reg  [7:0]  rx_shift;
    reg         rx_byte_valid;
    reg  [7:0]  rx_byte_out;

    always @(posedge clk) begin
        if (rst) begin
            rx_state      <= RX_WAIT_HIGH; // Do not trigger false start if pin rests low on reset
            rx_div_cnt    <= 16'd0;
            rx_bit_idx    <= 3'd0;
            rx_shift      <= 8'd0;
            rx_byte_valid <= 1'b0;
            rx_byte_out   <= 8'd0;
            rx_ferr_cnt   <= 5'd0;
        end else begin
            rx_byte_valid <= 1'b0;
            case (rx_state)
                RX_WAIT_HIGH: begin
                    if (rx_s) rx_state <= RX_IDLE;
                end

                RX_IDLE: begin
                    if (!rx_s) begin
                        rx_div_cnt <= {1'b0, eff_baud_div[15:1]} - 16'd1;
                        rx_state   <= RX_START;
                    end
                end

                RX_START: begin
                    if (rx_div_cnt == 16'd0) begin
                        if (!rx_s) begin
                            rx_div_cnt <= eff_baud_div - 16'd1;
                            rx_bit_idx <= 3'd0;
                            rx_state   <= RX_DATA;
                        end else begin
                            rx_state <= RX_IDLE;
                        end
                    end else begin
                        rx_div_cnt <= rx_div_cnt - 16'd1;
                    end
                end

                RX_DATA: begin
                    if (rx_div_cnt == 16'd0) begin
                        rx_shift   <= {rx_s, rx_shift[7:1]};
                        rx_div_cnt <= eff_baud_div - 16'd1;
                        if (rx_bit_idx == 3'd7)
                            rx_state <= RX_STOP;
                        else
                            rx_bit_idx <= rx_bit_idx + 3'd1;
                    end else begin
                        rx_div_cnt <= rx_div_cnt - 16'd1;
                    end
                end

                RX_STOP: begin
                    if (rx_div_cnt == 16'd0) begin
                        if (rx_s) begin
                            rx_byte_out   <= rx_shift;
                            rx_byte_valid <= 1'b1;
                            rx_state      <= RX_IDLE;
                        end else begin
                            if (rx_ferr_cnt != 5'h1F)
                                rx_ferr_cnt <= rx_ferr_cnt + 5'd1;
                            rx_state <= RX_WAIT_HIGH;
                        end
                    end else begin
                        rx_div_cnt <= rx_div_cnt - 16'd1;
                    end
                end

                default: rx_state <= RX_WAIT_HIGH;
            endcase
        end
    end

    // -------------------------------------------------------------------------
    // 3. Command Buffer, Parser & Echo Queue
    // -------------------------------------------------------------------------
    localparam integer CMD_MAX = 24;
    reg [8*CMD_MAX-1:0] cmd_vec;
    reg [4:0] cmd_len;
    reg       last_was_cr;
    reg       cmd_overflow;

    // Small 8-byte echo FIFO (drains only when no multi-char message is active)
    reg [7:0] echo_fifo [0:7];
    reg [2:0] echo_wp, echo_rp;
    reg [3:0] echo_cnt;

    // Message types for TX streamer
    localparam [3:0] MSG_NONE   = 4'd0,
                     MSG_BANNER = 4'd1,
                     MSG_STAT   = 4'd2,
                     MSG_RD_HEX = 4'd3,
                     MSG_OK     = 4'd4,
                     MSG_ERR    = 4'd5,
                     MSG_HELP   = 4'd6;

    reg [3:0]  msg_kind;
    reg [6:0]  msg_idx;
    reg        banner_sent_r;
    reg [4:0]  boot_wait_cnt;
    reg [31:0] stat_timer;
    reg        stat_pend;
    reg [3:0]  resp_pend_kind;
    reg        resp_pend_vld;
    reg [31:0] rd_val_lat;

    // Status snapshot registers (frozen when MSG_STAT begins)
    reg        snap_xo_ok, snap_xo_500m;
    reg        snap_sys_mmcm, snap_eth_mmcm, snap_adcr_mmcm;
    reg [2:0]  snap_dl_state;
    reg        snap_dl_l0, snap_dl_up;
    reg        snap_eth_up, snap_eth_cu;
    reg        snap_adcr_tr, snap_adcs_al;
    reg [15:0] snap_adcr_clip, snap_adcs_clip;
    reg [11:0] snap_xadc_raw;
    reg [15:0] snap_hk_tmp;
    reg [7:0]  snap_err_flags;
    reg        snap_radar_dis;

    // Helper: hex char <-> nibble
    function automatic [7:0] hex_char(input [3:0] n);
        begin
            hex_char = (n < 4'd10) ? (8'h30 + {4'd0, n}) : (8'h61 + {4'd0, (n - 4'd10)});
        end
    endfunction

    function automatic is_space(input [7:0] c);
        begin
            is_space = (c == 8'h20) || (c == 8'h09);
        end
    endfunction

    function automatic [7:0] to_lower(input [7:0] c);
        begin
            to_lower = ((c >= 8'h41) && (c <= 8'h5A)) ? (c + 8'h20) : c;
        end
    endfunction

    function automatic is_hex(input [7:0] c);
        reg [7:0] lc;
        begin
            lc = to_lower(c);
            is_hex = ((lc >= 8'h30) && (lc <= 8'h39)) || ((lc >= 8'h61) && (lc <= 8'h66));
        end
    endfunction

    function automatic [3:0] hex_val(input [7:0] c);
        reg [7:0] lc;
        begin
            lc = to_lower(c);
            if ((lc >= 8'h30) && (lc <= 8'h39))
                hex_val = lc[3:0];
            else
                hex_val = lc[3:0] + 4'd9; // 'a'=0x61 -> 1+9=10
        end
    endfunction

    // Sequential 1-char/clock line parser triggered on CR/LF (keeps ~350 LUTs & >+5 ns slack)
    reg        parse_busy;
    reg [4:0]  parse_idx, parse_len;
    reg        parse_ok;
    reg [2:0]  parse_op; // 0=err, 1=read, 2=write, 3=stat, 4=help
    reg [31:0] parse_addr, parse_val;
    reg [2:0]  pst; // 0=skip_lead, 1=skip_ws1, 2=addr_0x, 3=addr_hex, 4=skip_ws2, 5=val_0x, 6=val_hex, 7=trail_ws
    reg [3:0]  addr_ndig, val_ndig;
    reg        have_ws;

    wire [4:0] safe_pidx = (parse_idx < CMD_MAX[4:0]) ? parse_idx : 5'd0;
    wire [7:0] p_char    = cmd_vec[safe_pidx*8 +: 8];
    wire [7:0] p_char_lo = to_lower(p_char);
    wire       p_space   = is_space(p_char);
    wire       p_hex     = is_hex(p_char);
    wire [3:0] p_hex_v   = hex_val(p_char);

    // -------------------------------------------------------------------------
    // 4. Message Character LUT ROM + Field Formatter
    // -------------------------------------------------------------------------
    reg [7:0] msg_char;
    reg [6:0] msg_len;

    always @* begin
        msg_char = 8'h20;
        msg_len  = 7'd0;
        case (msg_kind)
            MSG_BANNER: begin
                msg_len = ENABLE_ETH ? 7'd66 : 7'd65;
                case (msg_idx)
                    7'd0:  msg_char = "K"; 7'd1:  msg_char = "V"; 7'd2:  msg_char = "2"; 7'd3:  msg_char = "6";
                    7'd4:  msg_char = "0"; 7'd5:  msg_char = "-"; 7'd6:  msg_char = "I"; 7'd7:  msg_char = "A";
                    7'd8:  msg_char = "S"; 7'd9:  msg_char = "2"; 7'd10: msg_char = "R"; 7'd11: msg_char = "F";
                    7'd12: msg_char = " "; 7'd13: msg_char = "b"; 7'd14: msg_char = "u"; 7'd15: msg_char = "i";
                    7'd16: msg_char = "l"; 7'd17: msg_char = "d"; 7'd18: msg_char = "=";
                    7'd19: msg_char = hex_char(BUILD_DATE[31:28]);
                    7'd20: msg_char = hex_char(BUILD_DATE[27:24]);
                    7'd21: msg_char = hex_char(BUILD_DATE[23:20]);
                    7'd22: msg_char = hex_char(BUILD_DATE[19:16]);
                    7'd23: msg_char = hex_char(BUILD_DATE[15:12]);
                    7'd24: msg_char = hex_char(BUILD_DATE[11:8]);
                    7'd25: msg_char = hex_char(BUILD_DATE[7:4]);
                    7'd26: msg_char = hex_char(BUILD_DATE[3:0]);
                    7'd27: msg_char = "-";
                    7'd28: msg_char = hex_char(BUILD_TIME[23:20]);
                    7'd29: msg_char = hex_char(BUILD_TIME[19:16]);
                    7'd30: msg_char = hex_char(BUILD_TIME[15:12]);
                    7'd31: msg_char = hex_char(BUILD_TIME[11:8]);
                    7'd32: msg_char = hex_char(BUILD_TIME[7:4]);
                    7'd33: msg_char = hex_char(BUILD_TIME[3:0]);
                    7'd34: msg_char = " "; 7'd35: msg_char = "g"; 7'd36: msg_char = "i"; 7'd37: msg_char = "t"; 7'd38: msg_char = "=";
                    7'd39: msg_char = hex_char(GIT_HASH[31:28]);
                    7'd40: msg_char = hex_char(GIT_HASH[27:24]);
                    7'd41: msg_char = hex_char(GIT_HASH[23:20]);
                    7'd42: msg_char = hex_char(GIT_HASH[19:16]);
                    7'd43: msg_char = hex_char(GIT_HASH[15:12]);
                    7'd44: msg_char = hex_char(GIT_HASH[11:8]);
                    7'd45: msg_char = hex_char(GIT_HASH[7:4]);
                    7'd46: msg_char = hex_char(GIT_HASH[3:0]);
                    7'd47: msg_char = " "; 7'd48: msg_char = "c"; 7'd49: msg_char = "l"; 7'd50: msg_char = "k"; 7'd51: msg_char = "=";
                    7'd52: msg_char = snap_xo_500m ? "5" : "4";
                    7'd53: msg_char = "0"; 7'd54: msg_char = "0"; 7'd55: msg_char = "M";
                    7'd56: msg_char = " "; 7'd57: msg_char = "e"; 7'd58: msg_char = "t"; 7'd59: msg_char = "h"; 7'd60: msg_char = "=";
                    7'd61: msg_char = ENABLE_ETH ? "y" : "n";
                    7'd62: msg_char = ENABLE_ETH ? "e" : "o";
                    7'd63: msg_char = ENABLE_ETH ? "s" : 8'h0D;
                    7'd64: msg_char = ENABLE_ETH ? 8'h0D : 8'h0A;
                    7'd65: msg_char = 8'h0A;
                    default: msg_char = 8'h0A;
                endcase
            end

            MSG_STAT: begin
                msg_len = 7'd95;
                case (msg_idx)
                    7'd0:  msg_char = "S"; 7'd1:  msg_char = "T"; 7'd2:  msg_char = "A"; 7'd3:  msg_char = "T";
                    7'd4:  msg_char = " "; 7'd5:  msg_char = "x"; 7'd6:  msg_char = "o"; 7'd7:  msg_char = "=";
                    7'd8:  msg_char = snap_xo_ok ? "1" : "0";
                    7'd9:  msg_char = " "; 7'd10: msg_char = "c"; 7'd11: msg_char = "l"; 7'd12: msg_char = "k"; 7'd13: msg_char = "=";
                    7'd14: msg_char = snap_xo_500m ? "5" : "4";
                    7'd15: msg_char = "0"; 7'd16: msg_char = "0";
                    7'd17: msg_char = " "; 7'd18: msg_char = "m"; 7'd19: msg_char = "m"; 7'd20: msg_char = "c"; 7'd21: msg_char = "m"; 7'd22: msg_char = "=";
                    7'd23: msg_char = snap_sys_mmcm  ? "1" : "0";
                    7'd24: msg_char = snap_eth_mmcm  ? "1" : "0";
                    7'd25: msg_char = snap_adcr_mmcm ? "1" : "0";
                    7'd26: msg_char = " "; 7'd27: msg_char = "d"; 7'd28: msg_char = "l"; 7'd29: msg_char = "=";
                    7'd30: msg_char = hex_char({1'b0, snap_dl_state});
                    7'd31: msg_char = snap_dl_l0 ? "1" : "0";
                    7'd32: msg_char = snap_dl_up ? "1" : "0";
                    7'd33: msg_char = " "; 7'd34: msg_char = "e"; 7'd35: msg_char = "t"; 7'd36: msg_char = "h"; 7'd37: msg_char = "=";
                    7'd38: msg_char = snap_eth_up ? "1" : "0";
                    7'd39: msg_char = snap_eth_cu ? "1" : "0";
                    7'd40: msg_char = " "; 7'd41: msg_char = "a"; 7'd42: msg_char = "d"; 7'd43: msg_char = "c"; 7'd44: msg_char = "=";
                    7'd45: msg_char = snap_adcr_tr ? "1" : "0";
                    7'd46: msg_char = snap_adcs_al ? "1" : "0";
                    7'd47: msg_char = " "; 7'd48: msg_char = "c"; 7'd49: msg_char = "l"; 7'd50: msg_char = "i"; 7'd51: msg_char = "p"; 7'd52: msg_char = "=";
                    7'd53: msg_char = hex_char(snap_adcr_clip[15:12]);
                    7'd54: msg_char = hex_char(snap_adcr_clip[11:8]);
                    7'd55: msg_char = hex_char(snap_adcr_clip[7:4]);
                    7'd56: msg_char = hex_char(snap_adcr_clip[3:0]);
                    7'd57: msg_char = hex_char(snap_adcs_clip[15:12]);
                    7'd58: msg_char = hex_char(snap_adcs_clip[11:8]);
                    7'd59: msg_char = hex_char(snap_adcs_clip[7:4]);
                    7'd60: msg_char = hex_char(snap_adcs_clip[3:0]);
                    7'd61: msg_char = " "; 7'd62: msg_char = "x"; 7'd63: msg_char = "a"; 7'd64: msg_char = "d"; 7'd65: msg_char = "c"; 7'd66: msg_char = "=";
                    7'd67: msg_char = hex_char(snap_xadc_raw[11:8]);
                    7'd68: msg_char = hex_char(snap_xadc_raw[7:4]);
                    7'd69: msg_char = hex_char(snap_xadc_raw[3:0]);
                    7'd70: msg_char = " "; 7'd71: msg_char = "t"; 7'd72: msg_char = "m"; 7'd73: msg_char = "p"; 7'd74: msg_char = "=";
                    7'd75: msg_char = hex_char(snap_hk_tmp[15:12]);
                    7'd76: msg_char = hex_char(snap_hk_tmp[11:8]);
                    7'd77: msg_char = hex_char(snap_hk_tmp[7:4]);
                    7'd78: msg_char = hex_char(snap_hk_tmp[3:0]);
                    7'd79: msg_char = " "; 7'd80: msg_char = "e"; 7'd81: msg_char = "r"; 7'd82: msg_char = "r"; 7'd83: msg_char = "=";
                    7'd84: msg_char = hex_char(snap_err_flags[7:4]);
                    7'd85: msg_char = hex_char(snap_err_flags[3:0]);
                    7'd86: msg_char = " "; 7'd87: msg_char = "r"; 7'd88: msg_char = "d"; 7'd89: msg_char = "i"; 7'd90: msg_char = "s"; 7'd91: msg_char = "=";
                    7'd92: msg_char = snap_radar_dis ? "1" : "0";
                    7'd93: msg_char = 8'h0D;
                    7'd94: msg_char = 8'h0A;
                    default: msg_char = 8'h0A;
                endcase
            end

            MSG_RD_HEX: begin
                msg_len = 7'd10;
                case (msg_idx)
                    7'd0: msg_char = hex_char(rd_val_lat[31:28]);
                    7'd1: msg_char = hex_char(rd_val_lat[27:24]);
                    7'd2: msg_char = hex_char(rd_val_lat[23:20]);
                    7'd3: msg_char = hex_char(rd_val_lat[19:16]);
                    7'd4: msg_char = hex_char(rd_val_lat[15:12]);
                    7'd5: msg_char = hex_char(rd_val_lat[11:8]);
                    7'd6: msg_char = hex_char(rd_val_lat[7:4]);
                    7'd7: msg_char = hex_char(rd_val_lat[3:0]);
                    7'd8: msg_char = 8'h0D;
                    7'd9: msg_char = 8'h0A;
                    default: msg_char = 8'h0A;
                endcase
            end

            MSG_OK: begin
                msg_len = 7'd4;
                case (msg_idx)
                    7'd0: msg_char = "o"; 7'd1: msg_char = "k";
                    7'd2: msg_char = 8'h0D; 7'd3: msg_char = 8'h0A;
                    default: msg_char = 8'h0A;
                endcase
            end

            MSG_ERR: begin
                msg_len = 7'd5;
                case (msg_idx)
                    7'd0: msg_char = "e"; 7'd1: msg_char = "r"; 7'd2: msg_char = "r";
                    7'd3: msg_char = 8'h0D; 7'd4: msg_char = 8'h0A;
                    default: msg_char = 8'h0A;
                endcase
            end

            MSG_HELP: begin
                msg_len = 7'd27;
                case (msg_idx)
                    7'd0:  msg_char = "r"; 7'd1:  msg_char = " "; 7'd2:  msg_char = "<"; 7'd3:  msg_char = "a"; 7'd4:  msg_char = ">";
                    7'd5:  msg_char = " "; 7'd6:  msg_char = "|"; 7'd7:  msg_char = " "; 7'd8:  msg_char = "w"; 7'd9:  msg_char = " ";
                    7'd10: msg_char = "<"; 7'd11: msg_char = "a"; 7'd12: msg_char = ">"; 7'd13: msg_char = " "; 7'd14: msg_char = "<";
                    7'd15: msg_char = "v"; 7'd16: msg_char = ">"; 7'd17: msg_char = " "; 7'd18: msg_char = "|"; 7'd19: msg_char = " ";
                    7'd20: msg_char = "s"; 7'd21: msg_char = " "; 7'd22: msg_char = "|"; 7'd23: msg_char = " "; 7'd24: msg_char = "h";
                    7'd25: msg_char = 8'h0D; 7'd26: msg_char = 8'h0A;
                    default: msg_char = 8'h0A;
                endcase
            end

            default: begin
                msg_len  = 7'd0;
                msg_char = 8'h20;
            end
        endcase
    end

    // -------------------------------------------------------------------------
    // 5. Coordinator FSM (Banner, 1 Hz Status, Monitor Commands, CSR Master)
    // -------------------------------------------------------------------------
    integer bi;
    reg [1:0] echo_push_n;
    reg       echo_pop;

    always @(posedge clk) begin
        if (rst) begin
            cmd_vec        <= {(8*CMD_MAX){1'b0}};
            cmd_len        <= 5'd0;
            last_was_cr    <= 1'b0;
            cmd_overflow   <= 1'b0;
            parse_busy     <= 1'b0;
            parse_idx      <= 5'd0;
            parse_len      <= 5'd0;
            parse_ok       <= 1'b0;
            parse_op       <= 3'd0;
            parse_addr     <= 32'd0;
            parse_val      <= 32'd0;
            pst            <= 3'd0;
            addr_ndig      <= 4'd0;
            val_ndig       <= 4'd0;
            have_ws        <= 1'b0;
            echo_wp        <= 3'd0;
            echo_rp        <= 3'd0;
            echo_cnt       <= 4'd0;
            msg_kind       <= MSG_NONE;
            msg_idx        <= 7'd0;
            tx_start       <= 1'b0;
            tx_byte_in     <= 8'd0;
            banner_done    <= 1'b0;
            banner_sent_r  <= 1'b0;
            boot_wait_cnt  <= 5'd0;
            stat_timer     <= 32'd0;
            stat_pend      <= 1'b0;
            resp_pend_kind <= MSG_NONE;
            resp_pend_vld  <= 1'b0;
            rd_val_lat     <= 32'd0;
            csr_req_valid  <= 1'b0;
            csr_req_wr     <= 1'b0;
            csr_req_addr   <= 16'd0;
            csr_req_wdata  <= 32'd0;
            snap_xo_ok     <= 1'b0;
            snap_xo_500m   <= 1'b1;
            snap_sys_mmcm  <= 1'b0;
            snap_eth_mmcm  <= 1'b0;
            snap_adcr_mmcm <= 1'b0;
            snap_dl_state  <= 3'd0;
            snap_dl_l0     <= 1'b0;
            snap_dl_up     <= 1'b0;
            snap_eth_up    <= 1'b0;
            snap_eth_cu    <= 1'b0;
            snap_adcr_tr   <= 1'b0;
            snap_adcs_al   <= 1'b0;
            snap_adcr_clip <= 16'd0;
            snap_adcs_clip <= 16'd0;
            snap_xadc_raw  <= 12'd0;
            snap_hk_tmp    <= 16'd0;
            snap_err_flags <= 8'd0;
            snap_radar_dis <= 1'b0;
        end else begin
            tx_start <= 1'b0;

            // Boot wait counter so clk_mode_ctrl syncs settle before printing banner
            if (!banner_sent_r) begin
                if (boot_wait_cnt != 5'h1F)
                    boot_wait_cnt <= boot_wait_cnt + 5'd1;
            end

            // Periodic 1 Hz status timer
            if (force_stat_p)
                stat_pend <= 1'b1;
            if (!cfg_status_dis && banner_done) begin
                if (stat_timer >= (eff_stat_cyc - 32'd1)) begin
                    stat_timer <= 32'd0;
                    stat_pend  <= 1'b1;
                end else begin
                    stat_timer <= stat_timer + 32'd1;
                end
            end else begin
                stat_timer <= 32'd0;
            end

            // CSR Master handshake completion
            if (csr_req_valid && csr_req_ack) begin
                csr_req_valid  <= 1'b0;
                rd_val_lat     <= csr_req_rdata;
                resp_pend_kind <= csr_req_wr ? MSG_OK : MSG_RD_HEX;
                resp_pend_vld  <= 1'b1;
            end

            // Sequential 1-char/clock command parser FSM
            if (parse_busy) begin
                if (parse_idx < parse_len) begin
                    parse_idx <= parse_idx + 5'd1;
                    case (pst)
                        3'd0: begin
                            if (!p_space) begin
                                if (p_char_lo == 8'h73) begin // 's'
                                    parse_op <= 3'd3;
                                    parse_ok <= 1'b1;
                                    pst      <= 3'd7;
                                end else if (p_char_lo == 8'h68) begin // 'h'
                                    parse_op <= 3'd4;
                                    parse_ok <= 1'b1;
                                    pst      <= 3'd7;
                                end else if (p_char_lo == 8'h72) begin // 'r'
                                    parse_op <= 3'd1;
                                    pst      <= 3'd1;
                                end else if (p_char_lo == 8'h77) begin // 'w'
                                    parse_op <= 3'd2;
                                    pst      <= 3'd1;
                                end else begin
                                    parse_op <= 3'd0;
                                    parse_ok <= 1'b0;
                                    pst      <= 3'd7;
                                end
                            end
                        end

                        3'd1: begin // require >= 1 space after r/w
                            if (p_space) begin
                                have_ws <= 1'b1;
                            end else if (!have_ws) begin
                                parse_ok <= 1'b0;
                                pst      <= 3'd7;
                            end else if (p_char == 8'h30) begin
                                parse_addr <= 32'd0;
                                addr_ndig  <= 4'd1;
                                parse_ok   <= (parse_op == 3'd1);
                                pst        <= 3'd2;
                            end else if (p_hex) begin
                                parse_addr <= {28'd0, p_hex_v};
                                addr_ndig  <= 4'd1;
                                parse_ok   <= (parse_op == 3'd1);
                                pst        <= 3'd3;
                            end else begin
                                parse_ok <= 1'b0;
                                pst      <= 3'd7;
                            end
                        end

                        3'd2: begin // saw leading '0' for addr: handle optional 'x' in "0x"
                            if (p_char_lo == 8'h78) begin
                                addr_ndig <= 4'd0;
                                parse_ok  <= 1'b0;
                                pst       <= 3'd3;
                            end else if (p_hex) begin
                                parse_addr <= {28'd0, p_hex_v};
                                addr_ndig  <= 4'd2;
                                parse_ok   <= (parse_op == 3'd1);
                                pst        <= 3'd3;
                            end else if (p_space) begin
                                if (parse_op == 3'd1) begin
                                    parse_ok <= 1'b1;
                                    pst      <= 3'd7;
                                end else begin
                                    have_ws  <= 1'b1;
                                    parse_ok <= 1'b0;
                                    pst      <= 3'd4;
                                end
                            end else begin
                                parse_ok <= 1'b0;
                                pst      <= 3'd7;
                            end
                        end

                        3'd3: begin // accumulate hex digits for addr
                            if (p_hex && (addr_ndig < 4'd8)) begin
                                parse_addr <= {parse_addr[27:0], p_hex_v};
                                addr_ndig  <= addr_ndig + 4'd1;
                                if (parse_op == 3'd1) parse_ok <= 1'b1;
                            end else if (p_space && (addr_ndig > 4'd0)) begin
                                if (parse_op == 3'd1) begin
                                    parse_ok <= 1'b1;
                                    pst      <= 3'd7;
                                end else begin
                                    have_ws <= 1'b1;
                                    pst     <= 3'd4;
                                end
                            end else begin
                                parse_ok <= 1'b0;
                                pst      <= 3'd7;
                            end
                        end

                        3'd4: begin // skip space before val
                            if (p_space) begin
                                have_ws <= 1'b1;
                            end else if (p_char == 8'h30) begin
                                parse_val <= 32'd0;
                                val_ndig  <= 4'd1;
                                parse_ok  <= 1'b1;
                                pst       <= 3'd5;
                            end else if (p_hex) begin
                                parse_val <= {28'd0, p_hex_v};
                                val_ndig  <= 4'd1;
                                parse_ok  <= 1'b1;
                                pst       <= 3'd6;
                            end else begin
                                parse_ok <= 1'b0;
                                pst      <= 3'd7;
                            end
                        end

                        3'd5: begin // saw leading '0' for val: handle optional 'x' in "0x"
                            if (p_char_lo == 8'h78) begin
                                val_ndig <= 4'd0;
                                parse_ok <= 1'b0;
                                pst      <= 3'd6;
                            end else if (p_hex) begin
                                parse_val <= {28'd0, p_hex_v};
                                val_ndig  <= 4'd2;
                                parse_ok  <= 1'b1;
                                pst       <= 3'd6;
                            end else if (p_space) begin
                                parse_ok <= 1'b1;
                                pst      <= 3'd7;
                            end else begin
                                parse_ok <= 1'b0;
                                pst      <= 3'd7;
                            end
                        end

                        3'd6: begin // accumulate hex digits for val
                            if (p_hex && (val_ndig < 4'd8)) begin
                                parse_val <= {parse_val[27:0], p_hex_v};
                                val_ndig  <= val_ndig + 4'd1;
                                parse_ok  <= 1'b1;
                            end else if (p_space && (val_ndig > 4'd0)) begin
                                parse_ok <= 1'b1;
                                pst      <= 3'd7;
                            end else begin
                                parse_ok <= 1'b0;
                                pst      <= 3'd7;
                            end
                        end

                        3'd7: begin // trailing whitespace only
                            if (!p_space)
                                parse_ok <= 1'b0;
                        end

                        default: parse_ok <= 1'b0;
                    endcase
                end else begin
                    parse_busy <= 1'b0;
                    if (parse_ok) begin
                        case (parse_op)
                            3'd1: begin // r <addr>
                                if (!csr_req_valid) begin
                                    csr_req_valid <= 1'b1;
                                    csr_req_wr    <= 1'b0;
                                    csr_req_addr  <= parse_addr[15:0];
                                    csr_req_wdata <= 32'd0;
                                end else begin
                                    resp_pend_kind <= MSG_ERR;
                                    resp_pend_vld  <= 1'b1;
                                end
                            end
                            3'd2: begin // w <addr> <val>
                                if (!csr_req_valid) begin
                                    csr_req_valid <= 1'b1;
                                    csr_req_wr    <= 1'b1;
                                    csr_req_addr  <= parse_addr[15:0];
                                    csr_req_wdata <= parse_val;
                                end else begin
                                    resp_pend_kind <= MSG_ERR;
                                    resp_pend_vld  <= 1'b1;
                                end
                            end
                            3'd3: begin // s
                                resp_pend_kind <= MSG_STAT;
                                resp_pend_vld  <= 1'b1;
                            end
                            3'd4: begin // h
                                resp_pend_kind <= MSG_HELP;
                                resp_pend_vld  <= 1'b1;
                            end
                            default: begin
                                resp_pend_kind <= MSG_ERR;
                                resp_pend_vld  <= 1'b1;
                            end
                        endcase
                    end else begin
                        resp_pend_kind <= MSG_ERR;
                        resp_pend_vld  <= 1'b1;
                    end
                end
            end

            // RX byte handler
            echo_push_n = 2'd0;
            echo_pop    = 1'b0;
            if (rx_byte_valid && !parse_busy) begin
                if (rx_byte_out == 8'h0D || rx_byte_out == 8'h0A) begin
                    if (rx_byte_out == 8'h0A && last_was_cr) begin
                        last_was_cr <= 1'b0;
                    end else begin
                        last_was_cr <= (rx_byte_out == 8'h0D);
                        if (echo_cnt <= 4'd6) begin
                            echo_fifo[echo_wp]        <= 8'h0D;
                            echo_fifo[echo_wp + 3'd1] <= 8'h0A;
                            echo_wp                   <= echo_wp + 3'd2;
                            echo_push_n               = 2'd2;
                        end
                        if (cmd_len != 5'd0 || cmd_overflow) begin
                            if (cmd_overflow) begin
                                resp_pend_kind <= MSG_ERR;
                                resp_pend_vld  <= 1'b1;
                            end else begin
                                parse_busy <= 1'b1;
                                parse_idx  <= 5'd0;
                                parse_len  <= cmd_len;
                                parse_ok   <= 1'b0;
                                parse_op   <= 3'd0;
                                parse_addr <= 32'd0;
                                parse_val  <= 32'd0;
                                pst        <= 3'd0;
                                addr_ndig  <= 4'd0;
                                val_ndig   <= 4'd0;
                                have_ws    <= 1'b0;
                            end
                            cmd_len      <= 5'd0;
                            cmd_overflow <= 1'b0;
                        end
                    end
                end else begin
                    last_was_cr <= 1'b0;
                    if (rx_byte_out == 8'h08 || rx_byte_out == 8'h7F) begin
                        if (cmd_len != 5'd0) begin
                            cmd_len <= cmd_len - 5'd1;
                            if (echo_cnt <= 4'd5) begin
                                echo_fifo[echo_wp]        <= 8'h08;
                                echo_fifo[echo_wp + 3'd1] <= 8'h20;
                                echo_fifo[echo_wp + 3'd2] <= 8'h08;
                                echo_wp                   <= echo_wp + 3'd3;
                                echo_push_n               = 2'd3;
                            end
                        end
                    end else if ((rx_byte_out >= 8'h20) && (rx_byte_out <= 8'h7E)) begin
                        if (cmd_len < CMD_MAX[4:0]) begin
                            cmd_vec[cmd_len*8 +: 8] <= rx_byte_out;
                            cmd_len                 <= cmd_len + 5'd1;
                        end else begin
                            cmd_overflow <= 1'b1;
                        end
                        if (echo_cnt < 4'd8) begin
                            echo_fifo[echo_wp] <= rx_byte_out;
                            echo_wp            <= echo_wp + 3'd1;
                            echo_push_n        = 2'd1;
                        end
                    end
                end
            end

            // TX Message Streamer / Scheduler
            if (msg_kind != MSG_NONE) begin
                if (!tx_active && !tx_start) begin
                    if (msg_idx < msg_len) begin
                        tx_byte_in <= msg_char;
                        tx_start   <= 1'b1;
                        msg_idx    <= msg_idx + 7'd1;
                    end else begin
                        if (msg_kind == MSG_BANNER)
                            banner_done <= 1'b1;
                        msg_kind <= MSG_NONE;
                        msg_idx  <= 7'd0;
                    end
                end
            end else if (!tx_active && !tx_start) begin
                if (!banner_sent_r && (boot_wait_cnt == 5'h1F)) begin
                    banner_sent_r <= 1'b1;
                    snap_xo_500m  <= st_xo_500m;
                    msg_kind      <= MSG_BANNER;
                    msg_idx       <= 7'd0;
                end else if (echo_cnt != 4'd0) begin
                    tx_byte_in <= echo_fifo[echo_rp];
                    tx_start   <= 1'b1;
                    echo_rp    <= echo_rp + 3'd1;
                    echo_pop   = 1'b1;
                end else if (resp_pend_vld) begin
                    resp_pend_vld <= 1'b0;
                    if (resp_pend_kind == MSG_STAT) begin
                        snap_xo_ok     <= st_xo_ok;
                        snap_xo_500m   <= st_xo_500m;
                        snap_sys_mmcm  <= st_sys_mmcm;
                        snap_eth_mmcm  <= st_eth_mmcm;
                        snap_adcr_mmcm <= st_adcr_mmcm;
                        snap_dl_state  <= st_dl_state;
                        snap_dl_l0     <= st_dl_l0_lock;
                        snap_dl_up     <= st_dl_link_up;
                        snap_eth_up    <= st_eth_link_up;
                        snap_eth_cu    <= st_eth_copper_up;
                        snap_adcr_tr   <= st_adcr_trained;
                        snap_adcs_al   <= st_adcs_aligned;
                        snap_adcr_clip <= st_adcr_clip_cnt;
                        snap_adcs_clip <= st_adcs_clip_cnt;
                        snap_xadc_raw  <= st_xadc_temp_raw;
                        snap_hk_tmp    <= st_hk_tmp_raw;
                        snap_err_flags <= {(rx_ferr_cnt != 5'd0), st_err_flags_lo};
                        snap_radar_dis <= st_radar_dis;
                    end
                    msg_kind <= resp_pend_kind;
                    msg_idx  <= 7'd0;
                end else if (stat_pend) begin
                    stat_pend      <= 1'b0;
                    snap_xo_ok     <= st_xo_ok;
                    snap_xo_500m   <= st_xo_500m;
                    snap_sys_mmcm  <= st_sys_mmcm;
                    snap_eth_mmcm  <= st_eth_mmcm;
                    snap_adcr_mmcm <= st_adcr_mmcm;
                    snap_dl_state  <= st_dl_state;
                    snap_dl_l0     <= st_dl_l0_lock;
                    snap_dl_up     <= st_dl_link_up;
                    snap_eth_up    <= st_eth_link_up;
                    snap_eth_cu    <= st_eth_copper_up;
                    snap_adcr_tr   <= st_adcr_trained;
                    snap_adcs_al   <= st_adcs_aligned;
                    snap_adcr_clip <= st_adcr_clip_cnt;
                    snap_adcs_clip <= st_adcs_clip_cnt;
                    snap_xadc_raw  <= st_xadc_temp_raw;
                    snap_hk_tmp    <= st_hk_tmp_raw;
                    snap_err_flags <= {(rx_ferr_cnt != 5'd0), st_err_flags_lo};
                    snap_radar_dis <= st_radar_dis;
                    msg_kind       <= MSG_STAT;
                    msg_idx        <= 7'd0;
                end
            end
            echo_cnt <= echo_cnt + {2'b00, echo_push_n} - {3'b000, echo_pop};
        end
    end

endmodule
`default_nettype wire
