// SPDX-License-Identifier: BSD-2-Clause
// AD9484 8-bit LVDS DDR capture with per-bit IDELAYE2 and DCO eye-scan training.
//
// PINMAP: AD9484 (U501) -> XC7A50T-2FTG256I (U1101) Bank 14 (VCCO = 3.3 V)
// Standard: LVDS_25 inputs, DIFF_TERM = FALSE (external 100 ohm R1101..R1110).
// Data-to-DCO routed skew: -90 to +5 ps (docs/SIGNAL_INTEGRITY.md).
//
// +-------------+----------+-----------+------------+--------+-----------------------------------------------+
// | Signal      | ADC Pin  | FPGA Ball | Bank / Pin | Term   | Notes                                         |
// +-------------+----------+-----------+------------+--------+-----------------------------------------------+
// | ADCR_D0_P/N | 4 / 3    | P15 / P16 | Bank 14    | R1101  | 100 ohm ext at FPGA                           |
// | ADCR_D1_P/N | 6 / 5    | R15 / R16 | Bank 14    | R1102  | 100 ohm ext at FPGA                           |
// | ADCR_D2_P/N | 10 / 9   | T14 / T15 | Bank 14    | R1103  | 100 ohm ext at FPGA                           |
// | ADCR_D3_P/N | 12 / 11  | R13 / T13 | Bank 14    | R1104  | 100 ohm ext at FPGA                           |
// | ADCR_D4_P/N | 14 / 13  | R10 / R11 | Bank 14    | R1105  | 100 ohm ext at FPGA                           |
// | ADCR_D5_P/N | 16 / 15  | T9  / T10 | Bank 14    | R1106  | 100 ohm ext at FPGA                           |
// | ADCR_D6_P/N | 18 / 17  | T7  / T8  | Bank 14    | R1107  | 100 ohm ext at FPGA                           |
// | ADCR_D7_P/N | 20 / 19  | R6  / R7  | Bank 14    | R1108  | 100 ohm ext at FPGA                           |
// | ADCR_OR_P/N | 22 / 21  | M6  / N6  | Bank 14    | R1110  | Over-range input                              |
// | ADCR_DCO    | 49 / 50  | N14 / P14 | Bank 14    | R1109  | INVERTED! N14 (MRCC_P)=DCO_N, P14 (MRCC_N)=DCO_P |
// +-------------+----------+-----------+------------+--------+-----------------------------------------------+
// Note on ADCR_DCO inversion (docs/CONTROL_SPEC.md §1, SIGNAL_INTEGRITY.md §8):
//   Board swaps P/N to avoid a 51 mm detour around U501. Therefore N14 (IBUFDS.I)
//   receives ADCR_DCO_N and P14 (IBUFDS.IB) receives ADCR_DCO_P. Gateware compensates
//   the polarity via IDDR IS_C_INVERTED = DCO_INVERT (1 by default).

`timescale 1ns/1ps

module adc_capture #(
    parameter [0:0] DCO_INVERT       = 1'b1,
    parameter real  DCO_PERIOD_NS    = 5.000,   // 200 MHz DDR DCO -> 400 MSPS
    parameter real  REFCLK_FREQ_MHZ  = 200.0,
    parameter [0:0] INST_IDELAYCTRL  = 1'b1,
    parameter [7:0] TRAIN_PAT_EVEN   = 8'hAA,
    parameter [7:0] TRAIN_PAT_ODD    = 8'h55
) (
    input  wire        rst,
    input  wire        refclk_200m,

    // AD9484 LVDS pins (Bank 14)
    input  wire [7:0]  adcr_d_p,
    input  wire [7:0]  adcr_d_n,
    input  wire        adcr_or_p,
    input  wire        adcr_or_n,
    input  wire        adcr_dco_n_pin, // Ball N14 (MRCC_P pad, wired to ADCR_DCO_N)
    input  wire        adcr_dco_p_pin, // Ball P14 (MRCC_N pad, wired to ADCR_DCO_P)

    // Training control
    input  wire        train_start,
    input  wire        train_pattern_en,

    // Recovered synchronous ADC clocks (from DCO MMCM)
    output wire        clk_400m,
    output wire        clk_100m,
    output wire        mmcm_locked,

    // Captured 400 MSPS stream (clk_400m domain)
    output reg  [7:0]  adc_data,
    output reg         adc_or,
    output reg         adc_valid,

    // Diagnostics / training status (clk_200m domain, steady after training)
    output reg         adc_trained,
    output reg         dco_phase_err,
    output wire [39:0] tap_flat,       // 8 x 5-bit per-bit IDELAYE2 taps
    output reg  [5:0]  eye_width_min
);

`ifdef MUTATE_WRONG_DCO_PHASE
    localparam [0:0] EFF_DCO_INVERT = ~DCO_INVERT;
`else
    localparam [0:0] EFF_DCO_INVERT = DCO_INVERT;
`endif

    // Optional Bank 14 IDELAYCTRL (set INST_IDELAYCTRL=0 when shared at top)
    wire idelay_rdy;
    generate
        if (INST_IDELAYCTRL) begin : g_idelayctrl
            (* IODELAY_GROUP = "bank14_idelay_grp" *)
            IDELAYCTRL u_idelayctrl (
                .RDY    (idelay_rdy),
                .REFCLK (refclk_200m),
                .RST    (rst)
            );
        end else begin : g_no_idelayctrl
            assign idelay_rdy = 1'b1;
        end
    endgenerate

    // -------------------------------------------------------------------------
    // DCO Clock Path: IBUFDS -> BUFIO (IDDR) + MMCME2_ADV (clk_400m/200m/100m)
    // -------------------------------------------------------------------------
    wire dco_ibuf;
    wire dco_bufio;

    IBUFDS #(
        .DIFF_TERM  ("FALSE"),
        .IOSTANDARD ("LVDS_25")
    ) u_ibuf_dco (
        .O  (dco_ibuf),
        .I  (adcr_dco_n_pin),
        .IB (adcr_dco_p_pin)
    );

    BUFIO u_bufio_dco (
        .I (dco_ibuf),
        .O (dco_bufio)
    );

    wire clk_fb_unbuf, clk_fb_bufg;
    wire clk_400m_unbuf, clk_100m_unbuf, clk_200m_unbuf;
    wire clk_200m;

    MMCME2_ADV #(
        .BANDWIDTH            ("OPTIMIZED"),
        .CLKFBOUT_MULT_F      (5.000),        // 200 MHz * 5 = 1000 MHz VCO
        .CLKFBOUT_PHASE       (0.0),
        .CLKIN1_PERIOD        (DCO_PERIOD_NS),
        .CLKOUT0_DIVIDE_F     (2.500),        // 400 MHz
        .CLKOUT0_PHASE        (0.0),
        .CLKOUT1_DIVIDE       (10),           // 100 MHz
        .CLKOUT1_PHASE        (45.0),         // +1.25 ns (midpoint of clk_400m) avoids 0-ps CDC race
        .CLKOUT2_DIVIDE       (5),            // 200 MHz
        .CLKOUT2_PHASE        (EFF_DCO_INVERT ? 0.0 : 180.0),
        .DIVCLK_DIVIDE        (1),
        .COMPENSATION         ("ZHOLD"),
        .STARTUP_WAIT         ("FALSE")
    ) u_mmcm_adc (
        .CLKIN1       (dco_ibuf),
        .CLKIN2       (1'b0),
        .CLKINSEL     (1'b1),
        .CLKFBIN      (clk_fb_bufg),
        .CLKFBOUT     (clk_fb_unbuf),
        .CLKFBOUTB    (),
        .CLKOUT0      (clk_400m_unbuf),
        .CLKOUT0B     (),
        .CLKOUT1      (clk_100m_unbuf),
        .CLKOUT1B     (),
        .CLKOUT2      (clk_200m_unbuf),
        .CLKOUT2B     (),
        .CLKOUT3      (),
        .CLKOUT3B     (),
        .CLKOUT4      (),
        .CLKOUT5      (),
        .CLKOUT6      (),
        .LOCKED       (mmcm_locked),
        .PWRDWN       (1'b0),
        .RST          (rst),
        .DADDR        (7'd0),
        .DCLK         (1'b0),
        .DEN          (1'b0),
        .DI           (16'd0),
        .DWE          (1'b0),
        .DO           (),
        .DRDY         (),
        .PSCLK        (1'b0),
        .PSEN         (1'b0),
        .PSINCDEC     (1'b0),
        .PSDONE       (),
        .CLKFBSTOPPED (),
        .CLKINSTOPPED ()
    );

    BUFG u_bufg_fb   (.I(clk_fb_unbuf),   .O(clk_fb_bufg));
    BUFG u_bufg_400m (.I(clk_400m_unbuf), .O(clk_400m));
    BUFG u_bufg_100m (.I(clk_100m_unbuf), .O(clk_100m));
    BUFG u_bufg_200m (.I(clk_200m_unbuf), .O(clk_200m));

    // Synchronized reset in clk_200m domain (holds until MMCM & IDELAYCTRL ready)
    (* ASYNC_REG = "TRUE" *) reg [1:0] rst_sync_200;
    wire rst_src = rst | ~mmcm_locked | ~idelay_rdy;
    always @(posedge clk_200m or posedge rst_src) begin
        if (rst_src)
            rst_sync_200 <= 2'b11;
        else
            rst_sync_200 <= {rst_sync_200[0], 1'b0};
    end
    wire rst_200m = rst_sync_200[1];

    // -------------------------------------------------------------------------
    // Per-Bit IBUFDS -> IDELAYE2 -> IDDR (D[7:0] and OR)
    // -------------------------------------------------------------------------
    wire [8:0] pad_p = {adcr_or_p, adcr_d_p};
    wire [8:0] pad_n = {adcr_or_n, adcr_d_n};
    wire [8:0] data_ibuf;
    wire [8:0] data_dly;
    wire [8:0] q_rise;
    wire [8:0] q_fall;

    reg  [4:0] tap_val [0:8];
    reg  [8:0] tap_ld;

    genvar b;
    generate
        for (b = 0; b < 9; b = b + 1) begin : g_adc_bits
            IBUFDS #(
                .DIFF_TERM  ("FALSE"),
                .IOSTANDARD ("LVDS_25")
            ) u_ibuf_d (
                .O  (data_ibuf[b]),
                .I  (pad_p[b]),
                .IB (pad_n[b])
            );

            (* IODELAY_GROUP = "bank14_idelay_grp" *)
            IDELAYE2 #(
                .CINVCTRL_SEL          ("FALSE"),
                .DELAY_SRC             ("IDATAIN"),
                .HIGH_PERFORMANCE_MODE ("TRUE"),
                .IDELAY_TYPE           ("VAR_LOAD"),
                .IDELAY_VALUE          (0),
                .PIPE_SEL              ("FALSE"),
                .REFCLK_FREQUENCY      (REFCLK_FREQ_MHZ),
                .SIGNAL_PATTERN        ("DATA")
            ) u_idelay_d (
                .CNTVALUEOUT (),
                .DATAOUT     (data_dly[b]),
                .C           (clk_200m),
                .CE          (1'b0),
                .CINVCTRL    (1'b0),
                .CNTVALUEIN  (tap_val[b]),
                .DATAIN      (1'b0),
                .IDATAIN     (data_ibuf[b]),
                .INC         (1'b0),
                .LD          (tap_ld[b]),
                .LDPIPEEN    (1'b0),
                .REGRST      (1'b0)
            );

            IDDR #(
                .DDR_CLK_EDGE   ("SAME_EDGE_PIPELINED"),
                .INIT_Q1        (1'b0),
                .INIT_Q2        (1'b0),
                .SRTYPE         ("SYNC"),
                .IS_C_INVERTED  (EFF_DCO_INVERT)
            ) u_iddr_d (
                .Q1 (q_rise[b]),
                .Q2 (q_fall[b]),
                .C  (dco_bufio),
                .CE (1'b1),
                .D  (data_dly[b]),
                .R  (1'b0),
                .S  (1'b0)
            );
        end
    endgenerate

    generate
        for (b = 0; b < 8; b = b + 1) begin : g_tap_export
            assign tap_flat[b*5 +: 5] = tap_val[b];
        end
    endgenerate

    // Capture IDDR Q1/Q2 in clk_200m domain
    reg [8:0] q_rise_r, q_fall_r;
    reg       tog_200;
    always @(posedge clk_200m) begin
        if (rst_200m) begin
            q_rise_r <= 9'd0;
            q_fall_r <= 9'd0;
            tog_200  <= 1'b0;
        end else begin
            q_rise_r <= q_rise;
            q_fall_r <= q_fall;
            tog_200  <= ~tog_200;
        end
    end

    // -------------------------------------------------------------------------
    // Per-Bit Eye-Scan Training FSM (clk_200m domain)
    // -------------------------------------------------------------------------
    localparam [2:0] ST_IDLE       = 3'd0,
                     ST_LOAD_TAP   = 3'd1,
                     ST_SETTLE     = 3'd2,
                     ST_DWELL      = 3'd3,
                     ST_FIND_EYE   = 3'd4,
                     ST_APPLY      = 3'd5,
                     ST_VERIFY     = 3'd6,
                     ST_LOCKED     = 3'd7;

    reg [2:0]  tr_state;
    reg [4:0]  scan_tap;
    reg [4:0]  wait_cnt;
    reg [31:0] pass_mask [0:7];
    reg [7:0]  tap_ok_bits;

    // Circular eye-center finder state across k = 0..63
    reg [5:0]  find_k;
    reg [5:0]  cur_start [0:7];
    reg [5:0]  cur_len   [0:7];
    reg [5:0]  best_start[0:7];
    reg [5:0]  best_len  [0:7];
    reg [4:0]  final_tap [0:7];
    reg [5:0]  min_eye_w;

    integer i;
    always @(posedge clk_200m) begin
        if (rst_200m) begin
            tr_state      <= ST_IDLE;
            scan_tap      <= 5'd0;
            wait_cnt      <= 5'd0;
            tap_ld        <= 9'd0;
            adc_trained   <= 1'b0;
            dco_phase_err <= 1'b0;
            eye_width_min <= 6'd0;
            find_k        <= 6'd0;
            min_eye_w     <= 6'd0;
            tap_ok_bits   <= 8'd0;
            for (i = 0; i < 9; i = i + 1)
                tap_val[i] <= 5'd0;
            for (i = 0; i < 8; i = i + 1) begin
                pass_mask[i]  <= 32'd0;
                cur_start[i]  <= 6'd0;
                cur_len[i]    <= 6'd0;
                best_start[i] <= 6'd0;
                best_len[i]   <= 6'd0;
                final_tap[i]  <= 5'd0;
            end
        end else begin
            tap_ld <= 9'd0;

            case (tr_state)
                ST_IDLE: begin
                    adc_trained   <= 1'b0;
                    dco_phase_err <= 1'b0;
                    if (train_start && train_pattern_en) begin
                        scan_tap <= 5'd0;
                        for (i = 0; i < 8; i = i + 1)
                            pass_mask[i] <= 32'd0;
                        tr_state <= ST_LOAD_TAP;
                    end
                end

                ST_LOAD_TAP: begin
                    for (i = 0; i < 9; i = i + 1)
                        tap_val[i] <= scan_tap;
                    tap_ld      <= 9'h1FF;
                    wait_cnt    <= 5'd0;
                    tap_ok_bits <= 8'hFF;
                    tr_state    <= ST_SETTLE;
                end

                ST_SETTLE: begin
                    if (wait_cnt == 5'd7) begin
                        wait_cnt <= 5'd0;
                        tr_state <= ST_DWELL;
                    end else begin
                        wait_cnt <= wait_cnt + 5'd1;
                    end
                end

                ST_DWELL: begin
                    for (i = 0; i < 8; i = i + 1) begin
                        if ((q_rise_r[i] !== TRAIN_PAT_EVEN[i]) ||
                            (q_fall_r[i] !== TRAIN_PAT_ODD[i]))
                            tap_ok_bits[i] <= 1'b0;
                    end
                    if (wait_cnt == 5'd15) begin
                        for (i = 0; i < 8; i = i + 1)
                            pass_mask[i][scan_tap] <= tap_ok_bits[i];
                        if (scan_tap == 5'd31) begin
                            find_k <= 6'd0;
                            for (i = 0; i < 8; i = i + 1) begin
                                cur_start[i]  <= 6'd0;
                                cur_len[i]    <= 6'd0;
                                best_start[i] <= 6'd0;
                                best_len[i]   <= 6'd0;
                            end
                            tr_state <= ST_FIND_EYE;
                        end else begin
                            scan_tap <= scan_tap + 5'd1;
                            tr_state <= ST_LOAD_TAP;
                        end
                    end else begin
                        wait_cnt <= wait_cnt + 5'd1;
                    end
                end

                ST_FIND_EYE: begin
                    for (i = 0; i < 8; i = i + 1) begin
                        if (pass_mask[i][find_k[4:0]] && cur_len[i] < 6'd32) begin
                            if (cur_len[i] == 6'd0)
                                cur_start[i] <= find_k;
                            if (cur_len[i] + 6'd1 > best_len[i]) begin
                                best_len[i]   <= cur_len[i] + 6'd1;
                                best_start[i] <= (cur_len[i] == 6'd0) ? find_k : cur_start[i];
                            end
                            cur_len[i] <= cur_len[i] + 6'd1;
                        end else begin
                            cur_len[i] <= 6'd0;
                        end
                    end

                    if (find_k == 6'd31) begin
                        tr_state <= ST_APPLY;
                    end else begin
                        find_k <= find_k + 6'd1;
                    end
                end

                ST_APPLY: begin
                    min_eye_w <= 6'd32;
                    for (i = 0; i < 8; i = i + 1) begin
                        // Compute centered tap modulo 32
                        if (best_len[i] >= 6'd32)
                            final_tap[i] <= 5'd0;
                        else
                            final_tap[i] <= (best_start[i][4:0] + best_len[i][5:1]);
                        tap_val[i] <= (best_len[i] >= 6'd32) ? 5'd0 :
                                      (best_start[i][4:0] + best_len[i][5:1]);
                    end
                    // Use D0 centered tap as nominal OR tap (matched length bus)
                    tap_val[8] <= (best_len[0] >= 6'd32) ? 5'd0 :
                                  (best_start[0][4:0] + best_len[0][5:1]);
                    tap_ld   <= 9'h1FF;
                    wait_cnt <= 5'd0;
                    tr_state <= ST_VERIFY;
                end

                ST_VERIFY: begin
                    // Minimum eye width across D[7:0]
                    min_eye_w <= best_len[0];
                    for (i = 1; i < 8; i = i + 1) begin
                        if (best_len[i] < min_eye_w)
                            min_eye_w <= best_len[i];
                    end

                    if (wait_cnt == 5'd15) begin
                        eye_width_min <= min_eye_w;
                        if (min_eye_w >= 6'd4 &&
                            (q_rise_r[7:0] == TRAIN_PAT_EVEN) &&
                            (q_fall_r[7:0] == TRAIN_PAT_ODD)) begin
                            adc_trained   <= 1'b1;
                            dco_phase_err <= 1'b0;
                            tr_state      <= ST_LOCKED;
                        end else begin
                            adc_trained   <= 1'b0;
                            dco_phase_err <= 1'b1;
                            tr_state      <= ST_LOCKED;
                        end
                    end else begin
                        wait_cnt <= wait_cnt + 5'd1;
                    end
                end

                ST_LOCKED: begin
                    if (train_start && train_pattern_en) begin
                        adc_trained   <= 1'b0;
                        dco_phase_err <= 1'b0;
                        scan_tap      <= 5'd0;
                        tr_state      <= ST_LOAD_TAP;
                    end
                end

                default: tr_state <= ST_IDLE;
            endcase
        end
    end

    // -------------------------------------------------------------------------
    // Unfold DDR pair (q_rise_r, q_fall_r) onto 400 MHz clk_400m domain
    // -------------------------------------------------------------------------
    (* ASYNC_REG = "TRUE" *) reg [1:0] rst_sync_400;
    always @(posedge clk_400m or posedge rst_src) begin
        if (rst_src)
            rst_sync_400 <= 2'b11;
        else
            rst_sync_400 <= {rst_sync_400[0], 1'b0};
    end
    wire rst_400m = rst_sync_400[1];

    reg       tog_400_d1, tog_400_d2;
    reg [8:0] fall_hold;
    reg       trained_400_d1, trained_400_d2;

    always @(posedge clk_400m) begin
        if (rst_400m) begin
            tog_400_d1     <= 1'b0;
            tog_400_d2     <= 1'b0;
            fall_hold      <= 9'd0;
            adc_data       <= 8'd0;
            adc_or         <= 1'b0;
            adc_valid      <= 1'b0;
            trained_400_d1 <= 1'b0;
            trained_400_d2 <= 1'b0;
        end else begin
            tog_400_d1     <= tog_200;
            tog_400_d2     <= tog_400_d1;
            trained_400_d1 <= adc_trained;
            trained_400_d2 <= trained_400_d1;

            if (tog_400_d1 != tog_400_d2) begin
                adc_data  <= q_rise_r[7:0];
                adc_or    <= q_rise_r[8];
                fall_hold <= q_fall_r;
                adc_valid <= trained_400_d2;
            end else begin
                adc_data  <= fall_hold[7:0];
                adc_or    <= fall_hold[8];
                adc_valid <= trained_400_d2;
            end
        end
    end

endmodule
