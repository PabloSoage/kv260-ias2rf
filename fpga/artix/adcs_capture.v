// SPDX-License-Identifier: BSD-2-Clause
// AD9253 Serial LVDS Capture (One-Lane 16-bit DDR Wordwise Mode, Bank 14)
//   ADCS_DCO_P/N (P10/P11, SRCC) : IBUFDS -> BUFIO (bit clock) + BUFR(DIV4) (clk_div = 2*f_S)
//   ADCS_FCO_P/N (N9/P9)         : IBUFDS -> IDELAYE2 (VAR_LOAD) -> ISERDESE2 (1:8 DDR NETWORKING)
//   ADCS_D0_P/N  (P8/R8, Ch A)   : IBUFDS -> IDELAYE2 (VAR_LOAD) -> ISERDESE2 (1:8 DDR NETWORKING)
//   ADCS_D1_P/N  (R5/T5, Ch B)   : IBUFDS -> IDELAYE2 (VAR_LOAD) -> ISERDESE2 (1:8 DDR NETWORKING)
//
// AD9253 Figure 6 (One-Lane 16-bit DDR Wordwise, MSB first, Reg 0x21 = 0x40):
//   DCO = 8*f_S (DDR 16*f_S); FCO = f_S square wave (1 for bits [15:8], 0 for bits [7:0])
//   Serial bit order (earliest -> latest): {D13, D12, ..., D0, 1'b0, 1'b0}
//   ISERDESE2 NETWORKING DDR Q8..Q1 chronological [earliest..latest]:
//     During FCO == 8'hFF: {q8..q1} = D[13:6]
//     During FCO == 8'h00: {q8..q1} = {D[5:0], 2'b00}
//
// Calibration sequence:
//   1) 32-tap IDELAYE2 eye scan on FCO searching for widest contiguous stable plateau where
//      FCO alternates between pat0 and pat1 (~pat0), then loads midpoint tap onto FCO, D0, D1.
//   2) Simultaneous BITSLIP across FCO, D0, D1 ISERDESE2 until FCO cleanly frames 8'hFF / 8'h00.

`timescale 1ns/1ps

module adcs_capture #(
    parameter [0:0] INST_IDELAYCTRL = 1'b1
) (
    input  wire        rst,
    input  wire        refclk_200m,
    input  wire        enable,

    // AD9253 LVDS inputs (external 100-ohm termination on PCB -> DIFF_TERM=FALSE)
    input  wire        adcs_dco_p,
    input  wire        adcs_dco_n,
    input  wire        adcs_fco_p,
    input  wire        adcs_fco_n,
    input  wire        adcs_d0_p,
    input  wire        adcs_d0_n,
    input  wire        adcs_d1_p,
    input  wire        adcs_d1_n,

    // Captured parallel output in clk_div (= DCO/4 = 2*f_S) domain
    output wire        clk_div,
    output reg         sample_valid,
    output reg  signed [13:0] sample_a,
    output reg  signed [13:0] sample_b,

    // Diagnostics / training status
    output reg         aligned,
    output reg         idelay_done,
    output reg         idelay_err,
    output reg         bitslip_err,
    output reg  [4:0]  best_tap,
    output reg  [3:0]  bitslip_cnt,
    output wire        idelay_rdy
);
    // -------------------------------------------------------------------------
    // Differential input buffers + DCO clock network
    // -------------------------------------------------------------------------
    wire dco_ibuf, fco_ibuf, d0_ibuf, d1_ibuf;
    wire dco_bufio, dco_bufio_b;

    IBUFDS #(.DIFF_TERM("FALSE"), .IBUF_LOW_PWR("FALSE")) u_ibuf_dco (.I(adcs_dco_p), .IB(adcs_dco_n), .O(dco_ibuf));
    IBUFDS #(.DIFF_TERM("FALSE"), .IBUF_LOW_PWR("FALSE")) u_ibuf_fco (.I(adcs_fco_p), .IB(adcs_fco_n), .O(fco_ibuf));
    IBUFDS #(.DIFF_TERM("FALSE"), .IBUF_LOW_PWR("FALSE")) u_ibuf_d0  (.I(adcs_d0_p),  .IB(adcs_d0_n),  .O(d0_ibuf));
    IBUFDS #(.DIFF_TERM("FALSE"), .IBUF_LOW_PWR("FALSE")) u_ibuf_d1  (.I(adcs_d1_p),  .IB(adcs_d1_n),  .O(d1_ibuf));

    BUFIO u_bufio_dco (.I(dco_ibuf), .O(dco_bufio));
    assign dco_bufio_b = ~dco_bufio;

    BUFR #(.BUFR_DIVIDE("4"), .SIM_DEVICE("7SERIES")) u_bufr_dco (
        .I   (dco_ibuf),
        .CE  (1'b1),
        .CLR (1'b0),
        .O   (clk_div)
    );

    generate
        if (INST_IDELAYCTRL) begin : gen_idelayctrl
            (* IODELAY_GROUP = "bank14_idelay_grp" *)
            IDELAYCTRL u_idelayctrl (
                .RDY    (idelay_rdy),
                .REFCLK (refclk_200m),
                .RST    (rst)
            );
        end else begin : gen_no_idelayctrl
            assign idelay_rdy = 1'b1;
        end
    endgenerate

    // Synchronize rst, enable, idelay_rdy into clk_div domain
    reg [2:0] rst_sync_r = 3'b111;
    reg [1:0] en_sync_r  = 2'b00;
    reg [1:0] rdy_sync_r = 2'b00;

    always @(posedge clk_div or posedge rst) begin
        if (rst)
            rst_sync_r <= 3'b111;
        else
            rst_sync_r <= {rst_sync_r[1:0], 1'b0};
    end
    wire clk_rst = rst_sync_r[2];

    always @(posedge clk_div) begin
        en_sync_r  <= {en_sync_r[0], enable};
        rdy_sync_r <= {rdy_sync_r[0], idelay_rdy};
    end
    wire run_en = en_sync_r[1] && rdy_sync_r[1] && !clk_rst;

    // -------------------------------------------------------------------------
    // IDELAYE2 + ISERDESE2 for FCO, D0, D1
    // -------------------------------------------------------------------------
    reg        idelay_ld;
    reg  [4:0] idelay_tap;
    reg        bitslip_pulse;

    wire fco_dly, d0_dly, d1_dly;
    wire [7:0] fco_q, d0_q, d1_q;

    (* IODELAY_GROUP = "bank14_idelay_grp" *)
    IDELAYE2 #(
        .CINVCTRL_SEL          ("FALSE"),
        .DELAY_SRC             ("IDATAIN"),
        .HIGH_PERFORMANCE_MODE ("TRUE"),
        .IDELAY_TYPE           ("VAR_LOAD"),
        .IDELAY_VALUE          (0),
        .PIPE_SEL              ("FALSE"),
        .REFCLK_FREQUENCY      (200.0),
        .SIGNAL_PATTERN        ("DATA")
    ) u_idelay_fco (
        .CNTVALUEOUT (),
        .DATAOUT     (fco_dly),
        .C           (clk_div),
        .CE          (1'b0),
        .CINVCTRL    (1'b0),
        .CNTVALUEIN  (idelay_tap),
        .DATAIN      (1'b0),
        .IDATAIN     (fco_ibuf),
        .INC         (1'b0),
        .LD          (idelay_ld),
        .LDPIPEEN    (1'b0),
        .REGRST      (clk_rst)
    );

    (* IODELAY_GROUP = "bank14_idelay_grp" *)
    IDELAYE2 #(
        .CINVCTRL_SEL          ("FALSE"),
        .DELAY_SRC             ("IDATAIN"),
        .HIGH_PERFORMANCE_MODE ("TRUE"),
        .IDELAY_TYPE           ("VAR_LOAD"),
        .IDELAY_VALUE          (0),
        .PIPE_SEL              ("FALSE"),
        .REFCLK_FREQUENCY      (200.0),
        .SIGNAL_PATTERN        ("DATA")
    ) u_idelay_d0 (
        .CNTVALUEOUT (),
        .DATAOUT     (d0_dly),
        .C           (clk_div),
        .CE          (1'b0),
        .CINVCTRL    (1'b0),
        .CNTVALUEIN  (idelay_tap),
        .DATAIN      (1'b0),
        .IDATAIN     (d0_ibuf),
        .INC         (1'b0),
        .LD          (idelay_ld),
        .LDPIPEEN    (1'b0),
        .REGRST      (clk_rst)
    );

    (* IODELAY_GROUP = "bank14_idelay_grp" *)
    IDELAYE2 #(
        .CINVCTRL_SEL          ("FALSE"),
        .DELAY_SRC             ("IDATAIN"),
        .HIGH_PERFORMANCE_MODE ("TRUE"),
        .IDELAY_TYPE           ("VAR_LOAD"),
        .IDELAY_VALUE          (0),
        .PIPE_SEL              ("FALSE"),
        .REFCLK_FREQUENCY      (200.0),
        .SIGNAL_PATTERN        ("DATA")
    ) u_idelay_d1 (
        .CNTVALUEOUT (),
        .DATAOUT     (d1_dly),
        .C           (clk_div),
        .CE          (1'b0),
        .CINVCTRL    (1'b0),
        .CNTVALUEIN  (idelay_tap),
        .DATAIN      (1'b0),
        .IDATAIN     (d1_ibuf),
        .INC         (1'b0),
        .LD          (idelay_ld),
        .LDPIPEEN    (1'b0),
        .REGRST      (clk_rst)
    );

    ISERDESE2 #(
        .DATA_RATE         ("DDR"),
        .DATA_WIDTH        (8),
        .DYN_CLKDIV_INV_EN ("FALSE"),
        .DYN_CLK_INV_EN    ("FALSE"),
        .INIT_Q1           (1'b0),
        .INIT_Q2           (1'b0),
        .INIT_Q3           (1'b0),
        .INIT_Q4           (1'b0),
        .INTERFACE_TYPE    ("NETWORKING"),
        .IOBDELAY          ("IFD"),
        .NUM_CE            (2),
        .OFB_USED          ("FALSE"),
        .SERDES_MODE       ("MASTER"),
        .SRVAL_Q1          (1'b0),
        .SRVAL_Q2          (1'b0),
        .SRVAL_Q3          (1'b0),
        .SRVAL_Q4          (1'b0)
    ) u_iserdes_fco (
        .O            (),
        .Q1           (fco_q[0]),
        .Q2           (fco_q[1]),
        .Q3           (fco_q[2]),
        .Q4           (fco_q[3]),
        .Q5           (fco_q[4]),
        .Q6           (fco_q[5]),
        .Q7           (fco_q[6]),
        .Q8           (fco_q[7]),
        .SHIFTOUT1    (),
        .SHIFTOUT2    (),
        .BITSLIP      (bitslip_pulse),
        .CE1          (1'b1),
        .CE2          (1'b1),
        .CLKDIVP      (1'b0),
        .CLK          (dco_bufio),
        .CLKB         (dco_bufio_b),
        .CLKDIV       (clk_div),
        .OCLK         (1'b0),
        .DYNCLKDIVSEL (1'b0),
        .DYNCLKSEL    (1'b0),
        .D            (1'b0),
        .DDLY         (fco_dly),
        .OFB          (1'b0),
        .OCLKB        (1'b0),
        .RST          (clk_rst),
        .SHIFTIN1     (1'b0),
        .SHIFTIN2     (1'b0)
    );

    ISERDESE2 #(
        .DATA_RATE         ("DDR"),
        .DATA_WIDTH        (8),
        .DYN_CLKDIV_INV_EN ("FALSE"),
        .DYN_CLK_INV_EN    ("FALSE"),
        .INIT_Q1           (1'b0),
        .INIT_Q2           (1'b0),
        .INIT_Q3           (1'b0),
        .INIT_Q4           (1'b0),
        .INTERFACE_TYPE    ("NETWORKING"),
        .IOBDELAY          ("IFD"),
        .NUM_CE            (2),
        .OFB_USED          ("FALSE"),
        .SERDES_MODE       ("MASTER"),
        .SRVAL_Q1          (1'b0),
        .SRVAL_Q2          (1'b0),
        .SRVAL_Q3          (1'b0),
        .SRVAL_Q4          (1'b0)
    ) u_iserdes_d0 (
        .O            (),
        .Q1           (d0_q[0]),
        .Q2           (d0_q[1]),
        .Q3           (d0_q[2]),
        .Q4           (d0_q[3]),
        .Q5           (d0_q[4]),
        .Q6           (d0_q[5]),
        .Q7           (d0_q[6]),
        .Q8           (d0_q[7]),
        .SHIFTOUT1    (),
        .SHIFTOUT2    (),
        .BITSLIP      (bitslip_pulse),
        .CE1          (1'b1),
        .CE2          (1'b1),
        .CLKDIVP      (1'b0),
        .CLK          (dco_bufio),
        .CLKB         (dco_bufio_b),
        .CLKDIV       (clk_div),
        .OCLK         (1'b0),
        .DYNCLKDIVSEL (1'b0),
        .DYNCLKSEL    (1'b0),
        .D            (1'b0),
        .DDLY         (d0_dly),
        .OFB          (1'b0),
        .OCLKB        (1'b0),
        .RST          (clk_rst),
        .SHIFTIN1     (1'b0),
        .SHIFTIN2     (1'b0)
    );

    ISERDESE2 #(
        .DATA_RATE         ("DDR"),
        .DATA_WIDTH        (8),
        .DYN_CLKDIV_INV_EN ("FALSE"),
        .DYN_CLK_INV_EN    ("FALSE"),
        .INIT_Q1           (1'b0),
        .INIT_Q2           (1'b0),
        .INIT_Q3           (1'b0),
        .INIT_Q4           (1'b0),
        .INTERFACE_TYPE    ("NETWORKING"),
        .IOBDELAY          ("IFD"),
        .NUM_CE            (2),
        .OFB_USED          ("FALSE"),
        .SERDES_MODE       ("MASTER"),
        .SRVAL_Q1          (1'b0),
        .SRVAL_Q2          (1'b0),
        .SRVAL_Q3          (1'b0),
        .SRVAL_Q4          (1'b0)
    ) u_iserdes_d1 (
        .O            (),
        .Q1           (d1_q[0]),
        .Q2           (d1_q[1]),
        .Q3           (d1_q[2]),
        .Q4           (d1_q[3]),
        .Q5           (d1_q[4]),
        .Q6           (d1_q[5]),
        .Q7           (d1_q[6]),
        .Q8           (d1_q[7]),
        .SHIFTOUT1    (),
        .SHIFTOUT2    (),
        .BITSLIP      (bitslip_pulse),
        .CE1          (1'b1),
        .CE2          (1'b1),
        .CLKDIVP      (1'b0),
        .CLK          (dco_bufio),
        .CLKB         (dco_bufio_b),
        .CLKDIV       (clk_div),
        .OCLK         (1'b0),
        .DYNCLKDIVSEL (1'b0),
        .DYNCLKSEL    (1'b0),
        .D            (1'b0),
        .DDLY         (d1_dly),
        .OFB          (1'b0),
        .OCLKB        (1'b0),
        .RST          (clk_rst),
        .SHIFTIN1     (1'b0),
        .SHIFTIN2     (1'b0)
    );

    // Chronological [earliest .. latest] = [7:0] = {q8, q7, q6, q5, q4, q3, q2, q1} = q_bus[7:0]
    // -------------------------------------------------------------------------
    // Calibration & Frame Alignment FSM (clk_div)
    // -------------------------------------------------------------------------
    localparam [3:0] ST_WAIT_EN    = 4'd0,
                     ST_LOAD_TAP   = 4'd1,
                     ST_SETTLE_TAP = 4'd2,
                     ST_OBS_TAP    = 4'd3,
                     ST_EVAL_TAP   = 4'd4,
                     ST_LOAD_BEST  = 4'd5,
                     ST_SETTLE_BST = 4'd6,
                     ST_CHECK_SLIP = 4'd7,
                     ST_SLIP_PULSE = 4'd8,
                     ST_SLIP_WAIT  = 4'd9,
                     ST_RUN        = 4'd10,
                     ST_FAIL       = 4'd11;

`ifdef MUTATE_FCO_OFF_BY_1
    localparam [7:0] FCO_TARGET_HI = 8'h7F;
    localparam [7:0] FCO_TARGET_LO = 8'h80;
`else
    localparam [7:0] FCO_TARGET_HI = 8'hFF;
    localparam [7:0] FCO_TARGET_LO = 8'h00;
`endif

    reg [3:0] state;
    reg [4:0] tap_idx;
    reg [4:0] obs_cnt;
    reg [7:0] pat0, pat1;
    reg [7:0] prev_pat0, prev_pat1;
    reg       tap_ok;
    reg       prev_ok;
    reg [4:0] cur_start, best_start;
    reg [5:0] cur_len, best_len;
    reg       slip_ok;
    reg [7:0] fco_prev, d0_prev, d1_prev;

    always @(posedge clk_div) begin
        if (clk_rst || !run_en) begin
            state         <= ST_WAIT_EN;
            idelay_ld     <= 1'b0;
            idelay_tap    <= 5'd0;
            bitslip_pulse <= 1'b0;
            tap_idx       <= 5'd0;
            obs_cnt       <= 5'd0;
            pat0          <= 8'd0;
            pat1          <= 8'd0;
            prev_pat0     <= 8'd0;
            prev_pat1     <= 8'd0;
            tap_ok        <= 1'b0;
            prev_ok       <= 1'b0;
            cur_start     <= 5'd0;
            cur_len       <= 6'd0;
            best_start    <= 5'd0;
            best_len      <= 6'd0;
            best_tap      <= 5'd16;
            bitslip_cnt   <= 4'd0;
            slip_ok       <= 1'b0;
            aligned       <= 1'b0;
            idelay_done   <= 1'b0;
            idelay_err    <= 1'b0;
            bitslip_err   <= 1'b0;
            sample_valid  <= 1'b0;
            sample_a      <= 14'sd0;
            sample_b      <= 14'sd0;
            fco_prev      <= 8'd0;
            d0_prev       <= 8'd0;
            d1_prev       <= 8'd0;
        end else begin
            idelay_ld     <= 1'b0;
            bitslip_pulse <= 1'b0;
            sample_valid  <= 1'b0;
            fco_prev      <= fco_q;
            d0_prev       <= d0_q;
            d1_prev       <= d1_q;

            case (state)
                ST_WAIT_EN: begin
                    if (obs_cnt == 5'd15) begin
                        tap_idx    <= 5'd0;
                        best_len   <= 6'd0;
                        best_start <= 5'd0;
                        cur_len    <= 6'd0;
                        prev_ok    <= 1'b0;
                        state      <= ST_LOAD_TAP;
                    end else begin
                        obs_cnt <= obs_cnt + 5'd1;
                    end
                end

                ST_LOAD_TAP: begin
                    idelay_tap <= tap_idx;
                    idelay_ld  <= 1'b1;
                    obs_cnt    <= 5'd0;
                    state      <= ST_SETTLE_TAP;
                end

                ST_SETTLE_TAP: begin
                    if (obs_cnt == 5'd5) begin
                        obs_cnt <= 5'd0;
                        tap_ok  <= 1'b1;
                        state   <= ST_OBS_TAP;
                    end else begin
                        obs_cnt <= obs_cnt + 5'd1;
                    end
                end

                ST_OBS_TAP: begin
                    if (obs_cnt == 5'd0) begin
                        pat0 <= fco_q;
                    end else if (obs_cnt == 5'd1) begin
                        pat1   <= fco_q;
                        tap_ok <= (fco_q == ~pat0);
                    end else begin
                        if (obs_cnt[0] == 1'b0) begin
                            if (fco_q != pat0) tap_ok <= 1'b0;
                        end else begin
                            if (fco_q != pat1) tap_ok <= 1'b0;
                        end
                    end

                    if (obs_cnt == 5'd15) begin
                        state <= ST_EVAL_TAP;
                    end else begin
                        obs_cnt <= obs_cnt + 5'd1;
                    end
                end

                ST_EVAL_TAP: begin
                    if (tap_ok) begin
                        if (prev_ok && (pat0 == prev_pat0) && (pat1 == prev_pat1)) begin
                            cur_len <= cur_len + 6'd1;
                            if ((cur_len + 6'd1) > best_len) begin
                                best_len   <= cur_len + 6'd1;
                                best_start <= cur_start;
                            end
                        end else begin
                            cur_start <= tap_idx;
                            cur_len   <= 6'd1;
                            if (6'd1 > best_len) begin
                                best_len   <= 6'd1;
                                best_start <= tap_idx;
                            end
                        end
                    end else begin
                        cur_len <= 6'd0;
                    end

                    prev_ok   <= tap_ok;
                    prev_pat0 <= pat0;
                    prev_pat1 <= pat1;

                    if (tap_idx == 5'd31) begin
                        state <= ST_LOAD_BEST;
                    end else begin
                        tap_idx <= tap_idx + 5'd1;
                        state   <= ST_LOAD_TAP;
                    end
                end

                ST_LOAD_BEST: begin
                    if (best_len == 6'd0) begin
                        best_tap   <= 5'd16;
                        idelay_tap <= 5'd16;
                        idelay_err <= 1'b1;
                    end else begin
                        best_tap   <= best_start + (best_len[5:1]);
                        idelay_tap <= best_start + (best_len[5:1]);
                        idelay_err <= 1'b0;
                    end
                    idelay_ld   <= 1'b1;
                    idelay_done <= 1'b1;
                    obs_cnt     <= 5'd0;
                    bitslip_cnt <= 4'd0;
                    state       <= ST_SETTLE_BST;
                end

                ST_SETTLE_BST: begin
                    if (obs_cnt == 5'd7) begin
                        obs_cnt <= 5'd0;
                        slip_ok <= 1'b1;
                        state   <= ST_CHECK_SLIP;
                    end else begin
                        obs_cnt <= obs_cnt + 5'd1;
                    end
                end

                ST_CHECK_SLIP: begin
                    if (obs_cnt != 5'd0) begin
                        if (!((fco_prev == FCO_TARGET_HI && fco_q == FCO_TARGET_LO) ||
                              (fco_prev == FCO_TARGET_LO && fco_q == FCO_TARGET_HI))) begin
                            slip_ok <= 1'b0;
                        end
                    end

                    if (obs_cnt == 5'd7) begin
                        if (slip_ok) begin
                            aligned <= 1'b1;
                            state   <= ST_RUN;
                        end else if (bitslip_cnt == 4'd8) begin
                            bitslip_err <= 1'b1;
                            state       <= ST_FAIL;
                        end else begin
                            state <= ST_SLIP_PULSE;
                        end
                    end else begin
                        obs_cnt <= obs_cnt + 5'd1;
                    end
                end

                ST_SLIP_PULSE: begin
                    bitslip_pulse <= 1'b1;
                    bitslip_cnt   <= bitslip_cnt + 4'd1;
                    obs_cnt       <= 5'd0;
                    state         <= ST_SLIP_WAIT;
                end

                ST_SLIP_WAIT: begin
                    if (obs_cnt == 5'd5) begin
                        obs_cnt <= 5'd0;
                        slip_ok <= 1'b1;
                        state   <= ST_CHECK_SLIP;
                    end else begin
                        obs_cnt <= obs_cnt + 5'd1;
                    end
                end

                ST_RUN: begin
                    aligned <= 1'b1;
                    if ((fco_prev == FCO_TARGET_HI) && (fco_q == FCO_TARGET_LO)) begin
                        sample_valid <= 1'b1;
`ifdef MUTATE_SWAP_CH
                        sample_a <= $signed({d1_prev, d1_q[7:2]});
                        sample_b <= $signed({d0_prev, d0_q[7:2]});
`else
                        sample_a <= $signed({d0_prev, d0_q[7:2]});
                        sample_b <= $signed({d1_prev, d1_q[7:2]});
`endif
                    end
                end

                ST_FAIL: begin
                    aligned     <= 1'b0;
                    bitslip_err <= 1'b1;
                end

                default: state <= ST_WAIT_EN;
            endcase
        end
    end
endmodule
