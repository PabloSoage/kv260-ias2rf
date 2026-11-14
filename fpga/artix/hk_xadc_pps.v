// SPDX-License-Identifier: BSD-2-Clause
// XADC Environmental Monitor (DRP Poll: Die Temp, VCCINT, VCCAUX) + PPS Timestamp/PPM Unit
//
// 1) XADC (Artix-7 UG480 internal reference, VP/VN & VREFP/VREFN grounded on PCB):
//    Continuously polls DRP registers in sys_clk domain:
//      - 7'h00: Die Temp  -> [15:4] 12-bit unsigned (T_C = raw * 503.975 / 4096 - 273.15)
//      - 7'h01: VCCINT    -> [15:4] 12-bit unsigned (V   = raw * 3.0 / 4096)
//      - 7'h02: VCCAUX    -> [15:4] 12-bit unsigned (V   = raw * 3.0 / 4096)
//
// 2) PPS_SYNC (Pin H14, Bank 15 LVCMOS33):
//    Runs in adc_clk domain (synced 3-FF edge detector) to measure the PPS period
//    in adc_clk cycles, compute signed ppm frequency error vs nom_period_cyc using an
//    iterative 32-bit sequential divider, latch the 64-bit monotonic timestamp on PPS,
//    and transfer coherent telemetry snapshots safely into sys_clk.

`timescale 1ns/1ps

module hk_xadc_pps #(
    parameter [31:0]  DEFAULT_NOM_CYC  = 32'd125_000_000, // 1.0 s @ 125 MHz ADC clk
    parameter [15:0]  DEFAULT_STEP_Q8  = 16'h0800,        // 8.0 ns/clk (Q8.8) @ 125 MHz
    parameter integer XADC_POLL_DIV    = 100_000,         // ~1 ms @ 100 MHz (override small in sim)
    parameter         SIM_MONITOR_FILE = "design.txt"
) (
    // System / link clock domain (DRP XADC & host register readout)
    input  wire        sys_clk,
    input  wire        sys_rst,

    // ADC clock domain (PPS period counter & sample timestamp)
    input  wire        adc_clk,
    input  wire        adc_rst,

    // Physical pin (Bank 15 LVCMOS33)
    input  wire        pps_sync,

    // Runtime configuration (sys_clk domain)
    input  wire [31:0] cfg_nom_period_cyc, // 0 -> DEFAULT_NOM_CYC
    input  wire [15:0] cfg_ts_step_q8,     // 0 -> DEFAULT_STEP_Q8
    input  wire        cfg_pps_disc_en,    // 1 = discipline timestamp forward/hold to PPS grid
    input  wire        cfg_ts_clear,       // Level/pulse to clear counters

    // XADC telemetry (sys_clk domain)
    output reg  [11:0] xadc_temp_raw,
    output reg  [11:0] xadc_vccint_raw,
    output reg  [11:0] xadc_vccaux_raw,
    output reg         xadc_valid,
    output wire        xadc_overtemp,

    // PPS telemetry & timestamps (coherent snapshots in sys_clk + fast timestamp in adc_clk)
    output wire [63:0] timestamp_ns_adc,
    output reg  [63:0] timestamp_ns_sys,
    output reg  [63:0] pps_latch_ts,
    output reg  [31:0] pps_period_cyc,
    output reg  signed [31:0] pps_ppm_err,
    output reg  [31:0] pps_cnt,
    output reg         pps_locked
);

    // =========================================================================
    // 1. Artix-7 XADC DRP Polling Engine (sys_clk)
    // =========================================================================
    reg  [6:0]  drp_addr;
    reg         drp_en;
    wire [15:0] drp_do;
    wire        drp_rdy;
    wire        xadc_eos;
    wire [7:0]  xadc_alm;
    wire        xadc_busy_w;

    XADC #(
        .INIT_40          (16'h0000), // Internal ref, continuous sampling
        .INIT_41          (16'h2000), // Continuous sequence mode
        .INIT_42          (16'h0400), // ADCCLK = DCLK / 4 (25 MHz @ 100 MHz)
        .INIT_48          (16'h0701), // Sequence: Calib + Temp + VCCINT + VCCAUX
        .INIT_49          (16'h0000),
        .INIT_4A          (16'h0000),
        .INIT_4B          (16'h0000),
        .INIT_4C          (16'h0000),
        .INIT_4D          (16'h0000),
        .INIT_4E          (16'h0000),
        .INIT_4F          (16'h0000),
        .INIT_50          (16'hB5ED), // Temp upper alarm ~85 C
        .INIT_53          (16'hCA33), // OT limit ~125 C
        .SIM_DEVICE       ("7SERIES"),
        .SIM_MONITOR_FILE (SIM_MONITOR_FILE)
    ) u_xadc (
        .DADDR        (drp_addr),
        .DCLK         (sys_clk),
        .DEN          (drp_en),
        .DI           (16'd0),
        .DWE          (1'b0),
        .RESET        (sys_rst),
        .VAUXN        (16'd0),
        .VAUXP        (16'd0),
        .VN           (1'b0),
        .VP           (1'b0),
        .CONVST       (1'b0),
        .CONVSTCLK    (1'b0),
        .ALM          (xadc_alm),
        .BUSY         (xadc_busy_w),
        .CHANNEL      (),
        .DO           (drp_do),
        .DRDY         (drp_rdy),
        .EOC          (),
        .EOS          (xadc_eos),
        .JTAGBUSY     (),
        .JTAGLOCKED   (),
        .JTAGMODIFIED (),
        .MUXADDR      (),
        .OT           (xadc_overtemp)
    );

    localparam [1:0]
        XST_WAIT   = 2'd0,
        XST_ISSUE  = 2'd1,
        XST_DRP    = 2'd2;

    reg [1:0]  x_state;
    reg [1:0]  x_chan_idx; // 0=Temp(0x00), 1=VCCINT(0x01), 2=VCCAUX(0x02)
    reg [31:0] x_poll_cnt;

    always @(posedge sys_clk) begin
        if (sys_rst) begin
            x_state         <= XST_WAIT;
            x_chan_idx      <= 2'd0;
            x_poll_cnt      <= 32'd0;
            drp_addr        <= 7'h00;
            drp_en          <= 1'b0;
            xadc_temp_raw   <= 12'd0;
            xadc_vccint_raw <= 12'd0;
            xadc_vccaux_raw <= 12'd0;
            xadc_valid      <= 1'b0;
        end else begin
            drp_en <= 1'b0;

            case (x_state)
                XST_WAIT: begin
                    if (x_poll_cnt != 32'd0) begin
                        x_poll_cnt <= x_poll_cnt - 32'd1;
                    end else if (!xadc_busy_w || xadc_eos) begin
                        x_chan_idx <= 2'd0;
                        x_state    <= XST_ISSUE;
                    end
                end

                XST_ISSUE: begin
                    drp_addr <= {5'd0, x_chan_idx}; // 0x00, 0x01, 0x02
                    drp_en   <= 1'b1;
                    x_state  <= XST_DRP;
                end

                XST_DRP: begin
                    if (drp_rdy) begin
                        case (x_chan_idx)
                            2'd0: xadc_temp_raw   <= drp_do[15:4];
                            2'd1: xadc_vccint_raw <= drp_do[15:4];
                            default: begin
                                xadc_vccaux_raw <= drp_do[15:4];
                                xadc_valid      <= 1'b1;
                            end
                        endcase
                        if (x_chan_idx == 2'd2) begin
                            x_poll_cnt <= (XADC_POLL_DIV < 1) ? 32'd1 : XADC_POLL_DIV[31:0];
                            x_state    <= XST_WAIT;
                        end else begin
                            x_chan_idx <= x_chan_idx + 2'd1;
                            x_state    <= XST_ISSUE;
                        end
                    end
                end

                default: x_state <= XST_WAIT;
            endcase
        end
    end

    // =========================================================================
    // 2. PPS_SYNC Period Counter, Timestamp & PPM Divider (adc_clk domain)
    // =========================================================================
`ifdef MUTATE_WRONG_PPS_CLK
    wire pps_meas_clk = sys_clk;
    wire pps_meas_rst = sys_rst;
`else
    wire pps_meas_clk = adc_clk;
    wire pps_meas_rst = adc_rst;
`endif

    // Sync runtime configuration from sys_clk -> adc_clk cleanly via toggle + 2-FF
    (* ASYNC_REG = "TRUE" *) reg [1:0] disc_en_s, ts_clr_s;
    reg [31:0] nom_cyc_adc;
    reg [15:0] step_q8_adc;
    reg        cfg_req_tog_sys;
    reg [31:0] cfg_nom_hold_sys;
    reg [15:0] cfg_step_hold_sys;
    (* ASYNC_REG = "TRUE" *) reg [2:0] cfg_tog_adc_s;

    always @(posedge sys_clk) begin
        if (sys_rst) begin
            cfg_req_tog_sys   <= 1'b0;
            cfg_nom_hold_sys  <= DEFAULT_NOM_CYC;
            cfg_step_hold_sys <= DEFAULT_STEP_Q8;
        end else begin
            if ((cfg_nom_period_cyc != cfg_nom_hold_sys) ||
                (cfg_ts_step_q8 != cfg_step_hold_sys)) begin
                cfg_nom_hold_sys  <= cfg_nom_period_cyc;
                cfg_step_hold_sys <= cfg_ts_step_q8;
                cfg_req_tog_sys   <= ~cfg_req_tog_sys;
            end
        end
    end

    always @(posedge pps_meas_clk) begin
        if (pps_meas_rst) begin
            disc_en_s     <= 2'b00;
            ts_clr_s      <= 2'b00;
            cfg_tog_adc_s <= 3'b000;
            nom_cyc_adc   <= DEFAULT_NOM_CYC;
            step_q8_adc   <= DEFAULT_STEP_Q8;
        end else begin
            disc_en_s     <= {disc_en_s[0], cfg_pps_disc_en};
            ts_clr_s      <= {ts_clr_s[0], cfg_ts_clear};
            cfg_tog_adc_s <= {cfg_tog_adc_s[1:0], cfg_req_tog_sys};
            if (cfg_tog_adc_s[2] != cfg_tog_adc_s[1]) begin
                nom_cyc_adc <= (cfg_nom_hold_sys == 32'd0) ? DEFAULT_NOM_CYC : cfg_nom_hold_sys;
                step_q8_adc <= (cfg_step_hold_sys == 16'd0) ? DEFAULT_STEP_Q8 : cfg_step_hold_sys;
            end
        end
    end

    // 3-stage MTBF synchronizer for asynchronous PPS_SYNC pulse
    (* ASYNC_REG = "TRUE" *) reg [2:0] pps_in_sync;
    wire pps_rise = (pps_in_sync[2:1] == 2'b01);

    reg [71:0] ts_q8; // [71:8] = nanoseconds (64b), [7:0] = sub-ns Q8 fraction
    assign timestamp_ns_adc = ts_q8[71:8];

    reg [31:0] cur_period_cyc;
    reg [31:0] meas_period_adc;
    reg [63:0] meas_latch_ts_adc;
    reg [31:0] meas_pps_cnt_adc;
    reg        pps_seen_adc;
    reg        meas_locked_adc;
    reg signed [31:0] meas_ppm_adc;
    reg        snap_tog_adc;

    // Iterative unsigned restoring divider: num[55:0] / den[31:0] -> quotient for |diff|*1e6 / nom
    reg        div_busy;
    reg        div_neg;
    reg [5:0]  div_bit;
    reg [55:0] div_rem;
    reg [55:0] div_num;
    reg [31:0] div_den;
    reg [31:0] div_quot;

    wire [55:0] rem_shift = {div_rem[54:0], div_num[55]};
    wire [55:0] den_ext   = {24'd0, div_den};

    reg signed [32:0] diff_cyc;
    reg [31:0] abs_diff;
    reg [63:0] next_sec_ns;

    always @(posedge pps_meas_clk) begin
        if (pps_meas_rst || ts_clr_s[1]) begin
            pps_in_sync       <= 3'b000;
            ts_q8             <= 72'd0;
            cur_period_cyc    <= 32'd0;
            meas_period_adc   <= 32'd0;
            meas_latch_ts_adc <= 64'd0;
            meas_pps_cnt_adc  <= 32'd0;
            pps_seen_adc      <= 1'b0;
            meas_locked_adc   <= 1'b0;
            meas_ppm_adc      <= 32'sd0;
            snap_tog_adc      <= 1'b0;
            div_busy          <= 1'b0;
            div_neg           <= 1'b0;
            div_bit           <= 6'd0;
            div_rem           <= 56'd0;
            div_num           <= 56'd0;
            div_den           <= 32'd1;
            div_quot          <= 32'd0;
        end else begin
            pps_in_sync  <= {pps_in_sync[1:0], pps_sync};
            ts_q8        <= ts_q8 + {{56{1'b0}}, step_q8_adc};

            if (pps_seen_adc)
                cur_period_cyc <= cur_period_cyc + 32'd1;

            if (pps_rise) begin
                pps_seen_adc      <= 1'b1;
                cur_period_cyc    <= 32'd1;
                meas_pps_cnt_adc  <= meas_pps_cnt_adc + 32'd1;
                meas_latch_ts_adc <= ts_q8[71:8];

                if (disc_en_s[1] && pps_seen_adc) begin
                    // Monotonic PPS discipline: snap ahead cleanly if slower than nominal
                    next_sec_ns = (meas_pps_cnt_adc + 32'd1) * 64'd1_000_000_000;
                    if (ts_q8[71:8] < next_sec_ns)
                        ts_q8 <= {next_sec_ns, 8'd0};
                end

                if (pps_seen_adc) begin
                    meas_period_adc <= cur_period_cyc;
                    meas_locked_adc <= 1'b1;

                    // Start |cur_period_cyc - nom_cyc_adc| * 1_000_000 / nom_cyc_adc
                    diff_cyc = $signed({1'b0, cur_period_cyc}) - $signed({1'b0, nom_cyc_adc});
                    div_neg  <= diff_cyc[32];
                    abs_diff = diff_cyc[32] ? (~diff_cyc[31:0] + 32'd1) : diff_cyc[31:0];
                    div_num  <= abs_diff * 56'd1_000_000;
                    div_den  <= (nom_cyc_adc == 32'd0) ? 32'd1 : nom_cyc_adc;
                    div_rem  <= 56'd0;
                    div_quot <= 32'd0;
                    div_bit  <= 6'd55;
                    div_busy <= 1'b1;
                end else begin
                    snap_tog_adc <= ~snap_tog_adc;
                end
            end else if (div_busy) begin
                if (rem_shift >= den_ext) begin
                    div_rem  <= rem_shift - den_ext;
                    div_quot <= {div_quot[30:0], 1'b1};
                end else begin
                    div_rem  <= rem_shift;
                    div_quot <= {div_quot[30:0], 1'b0};
                end
                div_num <= {div_num[54:0], 1'b0};

                if (div_bit == 6'd0) begin
                    div_busy     <= 1'b0;
                    meas_ppm_adc <= div_neg ? -$signed({1'b0, ({div_quot[30:0], (rem_shift >= den_ext)})})
                                            :  $signed({1'b0, ({div_quot[30:0], (rem_shift >= den_ext)})});
                    snap_tog_adc <= ~snap_tog_adc;
                end else begin
                    div_bit <= div_bit - 6'd1;
                end
            end
        end
    end

    // Transfer coherent PPS snapshot & live sys timestamp into sys_clk domain
    (* ASYNC_REG = "TRUE" *) reg [2:0] snap_tog_sys_s;
    reg [71:0] sys_ts_q8;
    reg [15:0] eff_step_sys;

    always @(posedge sys_clk) begin
        if (sys_rst || cfg_ts_clear) begin
            snap_tog_sys_s   <= 3'b000;
            pps_latch_ts     <= 64'd0;
            pps_period_cyc   <= 32'd0;
            pps_ppm_err      <= 32'sd0;
            pps_cnt          <= 32'd0;
            pps_locked       <= 1'b0;
            sys_ts_q8        <= 72'd0;
            timestamp_ns_sys <= 64'd0;
        end else begin
            eff_step_sys     = (cfg_ts_step_q8 == 16'd0) ? DEFAULT_STEP_Q8 : cfg_ts_step_q8;
            sys_ts_q8        <= sys_ts_q8 + {{56{1'b0}}, eff_step_sys};
            timestamp_ns_sys <= sys_ts_q8[71:8];

            snap_tog_sys_s <= {snap_tog_sys_s[1:0], snap_tog_adc};
            if (snap_tog_sys_s[2] != snap_tog_sys_s[1]) begin
                pps_latch_ts   <= meas_latch_ts_adc;
                pps_period_cyc <= meas_period_adc;
                pps_ppm_err    <= meas_ppm_adc;
                pps_cnt        <= meas_pps_cnt_adc;
                pps_locked     <= meas_locked_adc;
                // Sync sys_clk timestamp forward gently on each PPS snapshot
                if (sys_ts_q8[71:8] < meas_latch_ts_adc)
                    sys_ts_q8 <= {meas_latch_ts_adc, 8'd0};
            end
        end
    end

endmodule
`default_nettype wire
