// SPDX-License-Identifier: BSD-2-Clause
// SGMII 1.25 Gb/s Over LVDS PHY + IEEE 802.3 Clause 36/37 PCS (Rev06)
//
// Architecture:
//   - TX path: 125 MHz GMII -> Clause 36/37 TX PCS (/C1/,/C2/,/I1/,/I2/,/S/,/T/,/R/)
//     -> eth_8b10b_enc -> 20-bit async Gray FIFO (clk_125 -> clk_312p5)
//     -> 20b-to-4b gearbox -> OSERDESE2 (625 MHz DDR) -> OBUFDS (Bank 34 R2/R1)
//   - RX path: IBUFDS_DIFF_OUT (Bank 34 R3/T2, DIFF_TERM=TRUE) -> dual IDELAYE2
//     -> dual ISERDESE2 (625 MHz 0/90 deg DDR 4x oversampling)
//     -> XAPP523-style shadow guardband tracker + 3/4/5->10b gearbox (312.5 MHz)
//     -> 32-entry async Gray FIFO -> 10b K28.5 barrel-shifter + /I2/ clock-rate
//        compensation -> eth_8b10b_dec -> Clause 36/37 RX PCS + AN -> 125 MHz GMII

`timescale 1ns/1ps
`default_nettype none

module eth_sgmii_phy #(
    parameter [0:0] DIFF_TERM_EN       = 1'b1,              // TRUE on Bank 34 (2.5V VCCO)
    parameter       IODELAY_GROUP_NAME = "bank34_idelay_grp",
    parameter [0:0] BYPASS_AN          = 1'b0               // 0: full Clause 37 /C/ AN handshake
) (
    // Differential SGMII pins
    input  wire        sgmii_rx_p,
    input  wire        sgmii_rx_n,
    output wire        sgmii_tx_p,
    output wire        sgmii_tx_n,

    // Clocks & Resets
    input  wire        clk_625_0,
    input  wire        clk_625_90,
    input  wire        clk_312p5,
    input  wire        clk_312p5_45,
    input  wire        clk_125,
    input  wire        rst_312p5,
    input  wire        rst_125,

    // GMII TX Interface (clk_125)
    input  wire        gmii_tx_en,
    input  wire        gmii_tx_er,
    input  wire [7:0]  gmii_txd,

    // GMII RX Interface (clk_125)
    output reg         gmii_rx_dv,
    output reg         gmii_rx_er,
    output reg  [7:0]  gmii_rxd,

    // Control & Status (clk_125)
    input  wire        an_restart,
    output reg         rx_comma_aligned,
    output reg         an_complete,
    output wire        link_up,
    output reg  [15:0] an_lp_ability,
    output reg         phase_sel_mon,
    output reg  [31:0] phase_switch_cnt,
    output reg  [31:0] code_err_cnt,
    output reg  [31:0] disp_err_cnt
);

    localparam [9:0] K28_5_RD_NEG = 10'h17C;
    localparam [9:0] K28_5_RD_POS = 10'h283;
    localparam [9:0] D16_2_IDLE   = 10'h289; // D16.2 encoded at RD+ after K28.5 RD-

    // 8b/10b Special Control Bytes (din_k=1) & AN ordered-set bytes
    localparam [7:0] K_28_5 = 8'hBC;
    localparam [7:0] K_27_7 = 8'hFB; // /S/ Start of Packet
    localparam [7:0] K_29_7 = 8'hFD; // /T/ End of Packet
    localparam [7:0] K_23_7 = 8'hF7; // /R/ Carrier Extend
    localparam [7:0] K_30_7 = 8'hFE; // /V/ Error Propagation
    localparam [7:0] D_5_6  = 8'hC5; // /I1/ second byte
    localparam [7:0] D_16_2 = 8'h50; // /I2/ second byte
    localparam [7:0] D_21_5 = 8'hB5; // /C1/ config marker
    localparam [7:0] D_2_2  = 8'h42; // /C2/ config marker

    // =========================================================================
    // 1. SGMII LVDS RX Frontend: IBUFDS_DIFF_OUT -> IDELAYE2 -> ISERDESE2
    // =========================================================================
    localparam [4:0] TAP_CENTER = 5'd0;
    localparam [4:0] TAP_RIGHT  = 5'd3;
    localparam [4:0] TAP_LEFT   = 5'd7;
    localparam [4:0] SETTLE_CYC = 5'd6;
    localparam [4:0] PROBE_CYC  = 5'd15;

    wire rx_p_ibuf, rx_n_ibuf;
    wire rx_p_dly,  rx_n_dly;

    IBUFDS_DIFF_OUT #(
        .DIFF_TERM  (DIFF_TERM_EN ? "TRUE" : "FALSE"),
        .IOSTANDARD ("LVDS_25")
    ) u_ibuf_diff (
        .I  (sgmii_rx_p),
        .IB (sgmii_rx_n),
        .O  (rx_p_ibuf),
        .OB (rx_n_ibuf)
    );

    reg  [4:0] tap_p_r = TAP_CENTER;
    reg  [4:0] tap_n_r = TAP_CENTER;
    reg        ld_p_r  = 1'b0;
    reg        ld_n_r  = 1'b0;

    (* IODELAY_GROUP = IODELAY_GROUP_NAME *)
    IDELAYE2 #(
        .CINVCTRL_SEL          ("FALSE"),
        .DELAY_SRC             ("IDATAIN"),
        .HIGH_PERFORMANCE_MODE ("TRUE"),
        .IDELAY_TYPE           ("VAR_LOAD"),
        .IDELAY_VALUE          (0),
        .PIPE_SEL              ("FALSE"),
        .REFCLK_FREQUENCY      (200.0),
        .SIGNAL_PATTERN        ("DATA")
    ) u_idelay_p (
        .CNTVALUEOUT (),
        .DATAOUT     (rx_p_dly),
        .C           (clk_312p5),
        .CE          (1'b0),
        .CINVCTRL    (1'b0),
        .CNTVALUEIN  (tap_p_r),
        .DATAIN      (1'b0),
        .IDATAIN     (rx_p_ibuf),
        .INC         (1'b0),
        .LD          (ld_p_r),
        .LDPIPEEN    (1'b0),
        .REGRST      (rst_312p5)
    );

    (* IODELAY_GROUP = IODELAY_GROUP_NAME *)
    IDELAYE2 #(
        .CINVCTRL_SEL          ("FALSE"),
        .DELAY_SRC             ("IDATAIN"),
        .HIGH_PERFORMANCE_MODE ("TRUE"),
        .IDELAY_TYPE           ("VAR_LOAD"),
        .IDELAY_VALUE          (0),
        .PIPE_SEL              ("FALSE"),
        .REFCLK_FREQUENCY      (200.0),
        .SIGNAL_PATTERN        ("DATA")
    ) u_idelay_n (
        .CNTVALUEOUT (),
        .DATAOUT     (rx_n_dly),
        .C           (clk_312p5),
        .CE          (1'b0),
        .CINVCTRL    (1'b0),
        .CNTVALUEIN  (tap_n_r),
        .DATAIN      (1'b0),
        .IDATAIN     (rx_n_ibuf),
        .INC         (1'b0),
        .LD          (ld_n_r),
        .LDPIPEEN    (1'b0),
        .REGRST      (rst_312p5)
    );

    wire qp1, qp2, qp3, qp4;
    wire qn1, qn2, qn3, qn4;

    ISERDESE2 #(
        .DATA_RATE          ("DDR"),
        .DATA_WIDTH         (4),
        .DYN_CLKDIV_INV_EN  ("FALSE"),
        .DYN_CLK_INV_EN     ("FALSE"),
        .INIT_Q1            (1'b0), .INIT_Q2(1'b0), .INIT_Q3(1'b0), .INIT_Q4(1'b0),
        .INTERFACE_TYPE     ("NETWORKING"),
        .IOBDELAY           ("IFD"),
        .IS_CLKB_INVERTED   (1'b1),
        .IS_CLKDIVP_INVERTED(1'b0),
        .IS_CLKDIV_INVERTED (1'b0),
        .IS_CLK_INVERTED    (1'b0),
        .IS_D_INVERTED      (1'b0),
        .IS_OCLKB_INVERTED  (1'b0),
        .IS_OCLK_INVERTED   (1'b0),
        .NUM_CE             (1),
        .OFB_USED           ("FALSE"),
        .SERDES_MODE        ("MASTER"),
        .SRVAL_Q1           (1'b0), .SRVAL_Q2(1'b0), .SRVAL_Q3(1'b0), .SRVAL_Q4(1'b0)
    ) u_iserdes_p (
        .O(), .Q1(qp1), .Q2(qp2), .Q3(qp3), .Q4(qp4),
        .Q5(), .Q6(), .Q7(), .Q8(), .SHIFTOUT1(), .SHIFTOUT2(),
        .BITSLIP(1'b0), .CE1(1'b1), .CE2(1'b1),
        .CLK(clk_625_0), .CLKB(clk_625_0), .CLKDIV(clk_312p5), .CLKDIVP(1'b0),
        .D(1'b0), .DDLY(rx_p_dly), .DYNCLKDIVSEL(1'b0), .DYNCLKSEL(1'b0),
        .OCLK(1'b0), .OCLKB(1'b0), .OFB(1'b0), .RST(rst_312p5),
        .SHIFTIN1(1'b0), .SHIFTIN2(1'b0)
    );

    (* ASYNC_REG = "TRUE" *) reg [1:0] rst_312p5_45_sync = 2'b11;
    always @(posedge clk_312p5_45 or posedge rst_312p5) begin
        if (rst_312p5) rst_312p5_45_sync <= 2'b11;
        else           rst_312p5_45_sync <= {rst_312p5_45_sync[0], 1'b0};
    end

    ISERDESE2 #(
        .DATA_RATE          ("DDR"),
        .DATA_WIDTH         (4),
        .DYN_CLKDIV_INV_EN  ("FALSE"),
        .DYN_CLK_INV_EN     ("FALSE"),
        .INIT_Q1            (1'b0), .INIT_Q2(1'b0), .INIT_Q3(1'b0), .INIT_Q4(1'b0),
        .INTERFACE_TYPE     ("NETWORKING"),
        .IOBDELAY           ("IFD"),
        .IS_CLKB_INVERTED   (1'b1),
        .IS_CLKDIVP_INVERTED(1'b0),
        .IS_CLKDIV_INVERTED (1'b0),
        .IS_CLK_INVERTED    (1'b0),
        .IS_D_INVERTED      (1'b0),
        .IS_OCLKB_INVERTED  (1'b0),
        .IS_OCLK_INVERTED   (1'b0),
        .NUM_CE             (1),
        .OFB_USED           ("FALSE"),
        .SERDES_MODE        ("MASTER"),
        .SRVAL_Q1           (1'b0), .SRVAL_Q2(1'b0), .SRVAL_Q3(1'b0), .SRVAL_Q4(1'b0)
    ) u_iserdes_n (
        .O(), .Q1(qn1), .Q2(qn2), .Q3(qn3), .Q4(qn4),
        .Q5(), .Q6(), .Q7(), .Q8(), .SHIFTOUT1(), .SHIFTOUT2(),
        .BITSLIP(1'b0), .CE1(1'b1), .CE2(1'b1),
        .CLK(clk_625_90), .CLKB(clk_625_90), .CLKDIV(clk_312p5_45), .CLKDIVP(1'b0),
        .D(1'b0), .DDLY(rx_n_dly), .DYNCLKDIVSEL(1'b0), .DYNCLKSEL(1'b0),
        .OCLK(1'b0), .OCLKB(1'b0), .OFB(1'b0), .RST(rst_312p5_45_sync[1]),
        .SHIFTIN1(1'b0), .SHIFTIN2(1'b0)
    );

    reg [3:0] p_vec, n_vec;
    reg       prev_n3;
    always @(posedge clk_312p5) begin
        if (rst_312p5) begin
            p_vec   <= 4'd0;
            n_vec   <= 4'd0;
            prev_n3 <= 1'b0;
        end else begin
            p_vec   <= {qp1, qp2, qp3, qp4};
            n_vec   <= {~qn1, ~qn2, ~qn3, ~qn4};
            prev_n3 <= n_vec[3];
        end
    end

    // =========================================================================
    // 2. XAPP523 Shadow Guardband Eye Monitor & Phase Handover (312.5 MHz)
    // =========================================================================
    localparam [2:0] ST_INIT_LOAD = 3'd0;
    localparam [2:0] ST_MON_RIGHT = 3'd1;
    localparam [2:0] ST_MON_LEFT  = 3'd2;
    localparam [2:0] ST_SW_SETTLE = 3'd3;
    localparam [2:0] ST_SW_DO     = 3'd4;

    reg [2:0]  mon_state;
    reg [4:0]  mon_timer;
    reg [4:0]  hit_cnt;
    reg        init_done;
    reg        probe_is_right;
    reg        handover_plus_ppm;
    reg        phase_sel;
    reg [31:0] sw_cnt_312;

    wire edge_on_p_right = |(p_vec ^ n_vec);
    wire edge_on_p_left  = |(p_vec[3:1] ^ n_vec[3:1]);
    wire edge_on_n_right = |(n_vec[2:0] ^ p_vec[3:1]);
    wire edge_on_n_left  = |(n_vec[2:0] ^ p_vec[3:1]);

    wire probe_edge_hit = (phase_sel == 1'b0)
                          ? (probe_is_right ? edge_on_p_right : edge_on_p_left)
                          : (probe_is_right ? edge_on_n_right : edge_on_n_left);

    reg [4:0] out_bits;
    reg [2:0] out_nbits;

    always @(posedge clk_312p5) begin
        if (rst_312p5) begin
            mon_state         <= ST_INIT_LOAD;
            mon_timer         <= 5'd0;
            hit_cnt           <= 5'd0;
            init_done         <= 1'b0;
            probe_is_right    <= 1'b1;
            handover_plus_ppm <= 1'b0;
            phase_sel         <= 1'b0;
            tap_p_r           <= TAP_CENTER;
            tap_n_r           <= TAP_CENTER;
            ld_p_r            <= 1'b1;
            ld_n_r            <= 1'b1;
            out_bits          <= 5'd0;
            out_nbits         <= 3'd0;
            sw_cnt_312        <= 32'd0;
        end else begin
            ld_p_r <= 1'b0;
            ld_n_r <= 1'b0;

`ifdef MUTATE_NO_PHASE_SELECT
            phase_sel <= 1'b0;
            tap_p_r   <= TAP_CENTER;
            tap_n_r   <= TAP_CENTER;
            out_bits  <= {1'b0, p_vec};
            out_nbits <= 3'd4;
`else
            case (mon_state)
                ST_INIT_LOAD: begin
                    out_bits  <= init_done ? (phase_sel ? {1'b0, n_vec} : {1'b0, p_vec}) : 5'd0;
                    out_nbits <= init_done ? 3'd4 : 3'd0;
                    if (mon_timer < SETTLE_CYC) begin
                        mon_timer <= mon_timer + 5'd1;
                    end else begin
                        probe_is_right <= 1'b1;
                        hit_cnt        <= 5'd0;
                        mon_timer      <= 5'd0;
                        if (phase_sel == 1'b0) begin
                            tap_n_r <= TAP_RIGHT; ld_n_r <= 1'b1;
                        end else begin
                            tap_p_r <= TAP_RIGHT; ld_p_r <= 1'b1;
                        end
                        mon_state <= ST_MON_RIGHT;
                    end
                end

                ST_MON_RIGHT: begin
                    out_bits  <= phase_sel ? {1'b0, n_vec} : {1'b0, p_vec};
                    out_nbits <= 3'd4;
                    if (mon_timer < SETTLE_CYC) begin
                        mon_timer <= mon_timer + 5'd1;
                    end else if (mon_timer < (SETTLE_CYC + PROBE_CYC)) begin
                        mon_timer <= mon_timer + 5'd1;
                        if (probe_edge_hit && hit_cnt != 5'h1F)
                            hit_cnt <= hit_cnt + 5'd1;
                    end else if (hit_cnt >= 5'd2) begin
                        handover_plus_ppm <= 1'b1;
                        if (phase_sel == 1'b0) begin
                            tap_n_r <= TAP_CENTER; ld_n_r <= 1'b1;
                        end else begin
                            tap_p_r <= TAP_CENTER; ld_p_r <= 1'b1;
                        end
                        mon_timer <= 5'd0;
                        mon_state <= ST_SW_SETTLE;
                    end else begin
                        probe_is_right <= 1'b0;
                        hit_cnt        <= 5'd0;
                        mon_timer      <= 5'd0;
                        if (phase_sel == 1'b0) begin
                            tap_n_r <= TAP_LEFT; ld_n_r <= 1'b1;
                        end else begin
                            tap_p_r <= TAP_LEFT; ld_p_r <= 1'b1;
                        end
                        mon_state <= ST_MON_LEFT;
                    end
                end

                ST_MON_LEFT: begin
                    out_bits  <= phase_sel ? {1'b0, n_vec} : {1'b0, p_vec};
                    out_nbits <= 3'd4;
                    if (mon_timer < SETTLE_CYC) begin
                        mon_timer <= mon_timer + 5'd1;
                    end else if (mon_timer < (SETTLE_CYC + PROBE_CYC)) begin
                        mon_timer <= mon_timer + 5'd1;
                        if (probe_edge_hit && hit_cnt != 5'h1F)
                            hit_cnt <= hit_cnt + 5'd1;
                    end else begin
                        init_done <= 1'b1;
                        if (hit_cnt >= 5'd2) begin
                            handover_plus_ppm <= 1'b0;
                            if (phase_sel == 1'b0) begin
                                tap_n_r <= TAP_CENTER; ld_n_r <= 1'b1;
                            end else begin
                                tap_p_r <= TAP_CENTER; ld_p_r <= 1'b1;
                            end
                            mon_timer <= 5'd0;
                            mon_state <= ST_SW_SETTLE;
                        end else begin
                            probe_is_right <= 1'b1;
                            hit_cnt        <= 5'd0;
                            mon_timer      <= 5'd0;
                            if (phase_sel == 1'b0) begin
                                tap_n_r <= TAP_RIGHT; ld_n_r <= 1'b1;
                            end else begin
                                tap_p_r <= TAP_RIGHT; ld_p_r <= 1'b1;
                            end
                            mon_state <= ST_MON_RIGHT;
                        end
                    end
                end

                ST_SW_SETTLE: begin
                    out_bits  <= phase_sel ? {1'b0, n_vec} : {1'b0, p_vec};
                    out_nbits <= 3'd4;
                    if (mon_timer < SETTLE_CYC)
                        mon_timer <= mon_timer + 5'd1;
                    else
                        mon_state <= ST_SW_DO;
                end

                ST_SW_DO: begin
                    init_done  <= 1'b1;
                    phase_sel  <= ~phase_sel;
                    sw_cnt_312 <= sw_cnt_312 + 32'd1;
                    if (phase_sel == 1'b0) begin
                        if (handover_plus_ppm) begin
                            out_bits  <= {n_vec, prev_n3};
                            out_nbits <= 3'd5;
                        end else begin
                            out_bits  <= {1'b0, n_vec};
                            out_nbits <= 3'd4;
                        end
                    end else begin
                        if (handover_plus_ppm) begin
                            out_bits  <= {1'b0, p_vec};
                            out_nbits <= 3'd4;
                        end else begin
                            out_bits  <= {2'b0, p_vec[3:1]};
                            out_nbits <= 3'd3;
                        end
                    end
                    mon_timer <= 5'd0;
                    mon_state <= ST_INIT_LOAD;
                end

                default: mon_state <= ST_INIT_LOAD;
            endcase
`endif
        end
    end

    // 3/4/5 -> 10b Packer (312.5 MHz)
    reg [15:0] bit_buf, comb_buf;
    reg [4:0]  bit_cnt, comb_cnt;
    reg [9:0]  word_wr_data;
    reg        word_wr_en;

    always @(posedge clk_312p5) begin
        if (rst_312p5) begin
            bit_buf      <= 16'd0;
            bit_cnt      <= 5'd0;
            word_wr_data <= 10'd0;
            word_wr_en   <= 1'b0;
        end else begin
            word_wr_en <= 1'b0;
            comb_buf = bit_buf;
            comb_cnt = bit_cnt;
            if (comb_cnt >= 5'd10) begin
                word_wr_data <= comb_buf[9:0];
                word_wr_en   <= 1'b1;
                comb_buf     = {10'd0, comb_buf[15:10]};
                comb_cnt     = comb_cnt - 5'd10;
            end
            bit_buf <= comb_buf | ({11'd0, out_bits} << comb_cnt[3:0]);
            bit_cnt <= comb_cnt + {2'b00, out_nbits};
        end
    end

    // =========================================================================
    // 3. RX Elastic Gray FIFO (312.5 MHz -> clk_125) + K28.5 Align + /I2/ CTC
    // =========================================================================
    (* ram_style = "distributed" *) reg [9:0] rx_fifo_mem [0:31];
    reg [5:0] rx_wr_bin = 6'd0, rx_wr_gray = 6'd0;
    reg [5:0] rx_rd_bin = 6'd0, rx_rd_gray = 6'd0;
    (* ASYNC_REG = "TRUE" *) reg [5:0] rx_wr_g1 = 6'd0, rx_wr_g2 = 6'd0;
    (* ASYNC_REG = "TRUE" *) reg [5:0] rx_rd_g1 = 6'd0, rx_rd_g2 = 6'd0;

    function [5:0] bin2gray6(input [5:0] b);
        bin2gray6 = b ^ (b >> 1);
    endfunction

    function [5:0] gray2bin6(input [5:0] g);
        integer gi;
        begin
            gray2bin6[5] = g[5];
            for (gi = 4; gi >= 0; gi = gi - 1)
                gray2bin6[gi] = gray2bin6[gi + 1] ^ g[gi];
        end
    endfunction

    wire [5:0] rx_wr_next_b = rx_wr_bin + 6'd1;
    wire [5:0] rx_wr_next_g = bin2gray6(rx_wr_next_b);
    wire       rx_fifo_full = (rx_wr_next_g == {~rx_rd_g2[5:4], rx_rd_g2[3:0]});

    always @(posedge clk_312p5) begin
        if (rst_312p5) begin
            rx_wr_bin  <= 6'd0;
            rx_wr_gray <= 6'd0;
            rx_rd_g1   <= 6'd0;
            rx_rd_g2   <= 6'd0;
        end else begin
            rx_rd_g1 <= rx_rd_gray;
            rx_rd_g2 <= rx_rd_g1;
            if (word_wr_en && !rx_fifo_full) begin
                rx_fifo_mem[rx_wr_bin[4:0]] <= word_wr_data;
                rx_wr_bin                   <= rx_wr_next_b;
                rx_wr_gray                  <= rx_wr_next_g;
            end
        end
    end

    wire [5:0] rx_wr_bin_sync = gray2bin6(rx_wr_g2);
    wire [5:0] rx_fifo_occ    = rx_wr_bin_sync - rx_rd_bin;
    wire       rx_fifo_empty  = (rx_rd_gray == rx_wr_g2);

    // Comma aligner + aligned 8-entry CTC elastic buffer in clk_125
    reg [9:0]  fifo_word_q, prev_word_10b;
    reg        fifo_word_vld, has_prev_word;
    reg [19:0] win20_r;
    reg        win20_vld;
    reg [3:0]  slip_sel;
    reg [2:0]  comma_streak;
    reg [4:0]  comma_gap;
    reg [9:0]  k28_5_match;
    integer    k_idx;

    always @(*) begin
        for (k_idx = 0; k_idx < 10; k_idx = k_idx + 1) begin
            k28_5_match[k_idx] = (win20_r[k_idx +: 10] == K28_5_RD_NEG) ||
                                 (win20_r[k_idx +: 10] == K28_5_RD_POS);
        end
    end
    wire [9:0] aligned_word = win20_r[slip_sel +: 10];

    // Synchronous 8-entry aligned symbol queue for +-100 ppm /I2/ drop/insert
    reg [9:0] ctc_mem [0:7];
    reg [3:0] ctc_wr_ptr, ctc_rd_ptr;
    wire [3:0] ctc_occ    = ctc_wr_ptr - ctc_rd_ptr;
    wire [9:0] ctc_head0  = ctc_mem[ctc_rd_ptr[2:0]];
    wire [3:0] ctc_rd_p1  = ctc_rd_ptr + 4'd1;
    wire [3:0] ctc_rd_p2  = ctc_rd_ptr + 4'd2;
    wire [9:0] ctc_head1  = ctc_mem[ctc_rd_p1[2:0]];
    wire [9:0] ctc_head2  = ctc_mem[ctc_rd_p2[2:0]];
    wire       head_is_i2 = (ctc_occ >= 4'd2) &&
                            ((ctc_head0 == K28_5_RD_NEG) || (ctc_head0 == K28_5_RD_POS)) &&
                            (ctc_head1 == D16_2_IDLE);

    reg       ctc_primed;
    reg       ctc_ins_d16;
    reg [9:0] rx_code_125;
    reg       rx_code_valid;
    reg [3:0] los_err_cnt;

    (* ASYNC_REG = "TRUE" *) reg        ph_sel_s1, ph_sel_s2;
    (* ASYNC_REG = "TRUE" *) reg [31:0] sw_cnt_s1, sw_cnt_s2;

    always @(posedge clk_125) begin
        if (rst_125) begin
            rx_rd_bin        <= 6'd0;
            rx_rd_gray       <= 6'd0;
            rx_wr_g1         <= 6'd0;
            rx_wr_g2         <= 6'd0;
            fifo_word_q      <= 10'd0;
            fifo_word_vld    <= 1'b0;
            prev_word_10b    <= 10'd0;
            has_prev_word    <= 1'b0;
            win20_r          <= 20'd0;
            win20_vld        <= 1'b0;
            slip_sel         <= 4'd0;
            comma_streak     <= 3'd0;
            comma_gap        <= 5'd0;
            rx_comma_aligned <= 1'b0;
            ctc_wr_ptr       <= 4'd0;
            ctc_rd_ptr       <= 4'd0;
            ctc_primed       <= 1'b0;
            ctc_ins_d16      <= 1'b0;
            rx_code_125      <= K28_5_RD_NEG;
            rx_code_valid    <= 1'b0;
            ph_sel_s1        <= 1'b0;
            ph_sel_s2        <= 1'b0;
            phase_sel_mon    <= 1'b0;
            sw_cnt_s1        <= 32'd0;
            sw_cnt_s2        <= 32'd0;
            phase_switch_cnt <= 32'd0;
        end else begin
            rx_wr_g1 <= rx_wr_gray;
            rx_wr_g2 <= rx_wr_g1;
            ph_sel_s1        <= phase_sel;
            ph_sel_s2        <= ph_sel_s1;
            phase_sel_mon    <= ph_sel_s2;
            sw_cnt_s1        <= sw_cnt_312;
            sw_cnt_s2        <= sw_cnt_s1;
            phase_switch_cnt <= sw_cnt_s2;

            // Drain async FIFO into 20b aligner window
            if (!rx_fifo_empty) begin
                fifo_word_q   <= rx_fifo_mem[rx_rd_bin[4:0]];
                fifo_word_vld <= 1'b1;
                rx_rd_bin     <= rx_rd_bin + 6'd1;
                rx_rd_gray    <= bin2gray6(rx_rd_bin + 6'd1);
            end else begin
                fifo_word_vld <= 1'b0;
            end

            win20_vld <= 1'b0;
            if (fifo_word_vld) begin
                prev_word_10b <= fifo_word_q;
                if (!has_prev_word) begin
                    has_prev_word <= 1'b1;
                end else begin
                    win20_r   <= {fifo_word_q, prev_word_10b};
                    win20_vld <= 1'b1;
                end
            end

            // Push aligned symbols into CTC queue
            if (win20_vld) begin
                if (!rx_comma_aligned) begin
                    if (k28_5_match[slip_sel]) begin
                        comma_gap <= 5'd0;
                        if (comma_streak == 3'd3) begin
                            rx_comma_aligned <= 1'b1;
                            ctc_mem[ctc_wr_ptr[2:0]] <= aligned_word;
                            ctc_wr_ptr               <= ctc_wr_ptr + 4'd1;
                        end else begin
                            comma_streak <= comma_streak + 3'd1;
                        end
                    end else if (k28_5_match != 10'd0) begin
                        comma_streak <= 3'd1;
                        comma_gap    <= 5'd0;
                        if      (k28_5_match[0]) slip_sel <= 4'd0;
                        else if (k28_5_match[1]) slip_sel <= 4'd1;
                        else if (k28_5_match[2]) slip_sel <= 4'd2;
                        else if (k28_5_match[3]) slip_sel <= 4'd3;
                        else if (k28_5_match[4]) slip_sel <= 4'd4;
                        else if (k28_5_match[5]) slip_sel <= 4'd5;
                        else if (k28_5_match[6]) slip_sel <= 4'd6;
                        else if (k28_5_match[7]) slip_sel <= 4'd7;
                        else if (k28_5_match[8]) slip_sel <= 4'd8;
                        else                     slip_sel <= 4'd9;
                    end else if (comma_gap >= 5'd12) begin
                        comma_streak <= 3'd0;
                    end else begin
                        comma_gap <= comma_gap + 5'd1;
                    end
                end else if (los_err_cnt >= 4'd8) begin
                    rx_comma_aligned <= 1'b0;
                    comma_streak     <= 3'd0;
                    comma_gap        <= 5'd0;
                    ctc_wr_ptr       <= 4'd0;
                    ctc_rd_ptr       <= 4'd0;
                    ctc_primed       <= 1'b0;
                end else begin
                    ctc_mem[ctc_wr_ptr[2:0]] <= aligned_word;
                    ctc_wr_ptr               <= ctc_wr_ptr + 4'd1;
                end
            end

            // Pop 1 word/cycle at local 125 MHz with /I2/ drop or insert
            rx_code_valid <= 1'b0;
            if (!ctc_primed) begin
                if (ctc_occ >= 4'd4)
                    ctc_primed <= 1'b1;
            end else begin
                rx_code_valid <= 1'b1;
                if (ctc_ins_d16) begin
                    rx_code_125 <= D16_2_IDLE;
                    ctc_ins_d16 <= 1'b0;
                end else if (ctc_occ == 4'd0) begin
                    // Underflow protection (-ppm): synthesize /I2/
                    rx_code_125 <= K28_5_RD_NEG;
                    ctc_ins_d16 <= 1'b1;
                end else if ((ctc_occ >= 4'd6) && head_is_i2) begin
                    // Overflow protection (+ppm): drop complete /I2/ pair (K28.5 + D16.2)
                    rx_code_125 <= ctc_head2;
                    ctc_rd_ptr  <= ctc_rd_ptr + 4'd3;
                end else begin
                    rx_code_125 <= ctc_head0;
                    ctc_rd_ptr  <= ctc_rd_ptr + 4'd1;
                end
            end
        end
    end

    // =========================================================================
    // 4. 8b/10b Decoder + Clause 36/37 RX PCS + Auto-Negotiation (clk_125)
    // =========================================================================
    wire       dec_k;
    wire [7:0] dec_d;
    wire       dec_code_err, dec_disp_err, dec_rd_pos;
    reg        dec_rst_sync = 1'b1;
    always @(posedge clk_125)
        dec_rst_sync <= rst_125;

    eth_8b10b_dec u_dec (
        .clk      (clk_125),
        .rst      (dec_rst_sync),
        .en       (rx_code_valid),
        .din      (rx_code_125),
        .dout_k   (dec_k),
        .dout     (dec_d),
        .code_err (dec_code_err),
        .disp_err (dec_disp_err),
        .rd_pos   (dec_rd_pos)
    );

    reg       dec_vld_d1;
    reg [1:0] an_cap_idx;
    reg       an_is_c;
    reg [15:0] an_rx_word, an_last_word;
    reg [2:0]  an_match_cnt;
    reg        rx_in_pkt;
    reg        rx_k28_5_seen;

    localparam [1:0] AN_CONFIG = 2'd0, AN_ACK = 2'd1, AN_DATA = 2'd2;
    reg [1:0] an_state;
    reg [3:0] an_ack_idle_cnt;

    assign link_up = BYPASS_AN ? rx_comma_aligned : (an_complete && rx_comma_aligned);

    always @(posedge clk_125) begin
        if (rst_125 || an_restart) begin
            dec_vld_d1      <= 1'b0;
            an_cap_idx      <= 2'd0;
            an_is_c         <= 1'b0;
            an_rx_word      <= 16'd0;
            an_last_word    <= 16'd0;
            an_match_cnt    <= 3'd0;
            an_lp_ability   <= 16'd0;
            an_complete     <= BYPASS_AN;
            an_state        <= BYPASS_AN ? AN_DATA : AN_CONFIG;
            an_ack_idle_cnt <= 4'd0;
            rx_in_pkt       <= 1'b0;
            rx_k28_5_seen   <= 1'b0;
            gmii_rx_dv      <= 1'b0;
            gmii_rx_er      <= 1'b0;
            gmii_rxd        <= 8'h00;
            code_err_cnt    <= 32'd0;
            disp_err_cnt    <= 32'd0;
            los_err_cnt     <= 4'd0;
        end else begin
            dec_vld_d1 <= rx_code_valid;
            gmii_rx_er <= 1'b0;

            if (!rx_comma_aligned) begin
                los_err_cnt  <= 4'd0;
                an_match_cnt <= 3'd0;
                an_state     <= BYPASS_AN ? AN_DATA : AN_CONFIG;
                an_complete  <= BYPASS_AN;
                rx_in_pkt    <= 1'b0;
                gmii_rx_dv   <= 1'b0;
            end else if (dec_vld_d1) begin
                if (dec_code_err) begin
                    code_err_cnt <= code_err_cnt + 32'd1;
                    if (los_err_cnt != 4'hF)
                        los_err_cnt <= los_err_cnt + 4'd1;
                end else begin
                    los_err_cnt <= 4'd0;
                end
                if (dec_disp_err) disp_err_cnt <= disp_err_cnt + 32'd1;

                // Track /C1/ or /C2/ configuration ordered sets for Clause 37 AN
                if (dec_k && (dec_d == K_28_5)) begin
                    an_cap_idx    <= 2'd1;
                    an_is_c       <= 1'b0;
                    rx_k28_5_seen <= 1'b1;
                end else begin
                    rx_k28_5_seen <= 1'b0;
                    if (an_cap_idx == 2'd1) begin
                        if (!dec_k && (dec_d == D_21_5 || dec_d == D_2_2)) begin
                            an_is_c    <= 1'b1;
                            an_cap_idx <= 2'd2;
                        end else begin
                            an_cap_idx <= 2'd0;
                        end
                    end else if (an_cap_idx == 2'd2 && an_is_c) begin
                        an_rx_word[7:0] <= dec_d;
                        an_cap_idx      <= 2'd3;
                    end else if (an_cap_idx == 2'd3 && an_is_c) begin
                        an_rx_word[15:8] <= dec_d;
                        an_cap_idx       <= 2'd0;
                        an_last_word     <= {dec_d, an_rx_word[7:0]};
                        if ({dec_d, an_rx_word[7:0]} == an_last_word && ({dec_d, an_rx_word[7:0]} != 16'd0)) begin
                            if (an_match_cnt != 3'd7)
                                an_match_cnt <= an_match_cnt + 3'd1;
                        end else begin
                            an_match_cnt <= 3'd1;
                        end
                        an_lp_ability <= {dec_d, an_rx_word[7:0]};
                    end else begin
                        an_cap_idx <= 2'd0;
                    end
                end

                // Clause 37 AN State Machine
                case (an_state)
                    AN_CONFIG: begin
                        an_complete <= 1'b0;
                        if (an_match_cnt >= 3'd3) begin
                            an_state        <= AN_ACK;
                            an_ack_idle_cnt <= 4'd0;
                        end
                    end
                    AN_ACK: begin
                        // Move to DATA once peer sends Ack (bit 14) or switches to /I/
                        if (an_lp_ability[14] || (!an_is_c && rx_k28_5_seen && !dec_k && (dec_d == D_16_2 || dec_d == D_5_6))) begin
                            if (an_ack_idle_cnt >= 4'd2) begin
                                an_state    <= AN_DATA;
                                an_complete <= 1'b1;
                            end else begin
                                an_ack_idle_cnt <= an_ack_idle_cnt + 4'd1;
                            end
                        end
                    end
                    AN_DATA: begin
                        an_complete <= 1'b1;
                        // Re-enter AN if peer restarts /C/ with non-zero and Ack=0
                        if (an_match_cnt >= 3'd3 && !an_lp_ability[14] && rx_in_pkt == 1'b0 && an_is_c) begin
                            an_state <= AN_ACK;
                        end
                    end
                    default: an_state <= AN_CONFIG;
                endcase

                // Packet Delimiters -> GMII RX
                if (an_state == AN_DATA) begin
                    if (!rx_in_pkt) begin
                        gmii_rx_dv <= 1'b0;
                        if (dec_k && (dec_d == K_27_7)) begin
                            rx_in_pkt  <= 1'b1;
                            gmii_rx_dv <= 1'b1;
                            gmii_rxd   <= 8'h55; // Restore replaced first preamble byte
                        end
                    end else begin
                        if (dec_k && (dec_d == K_29_7 || dec_d == K_28_5)) begin
                            rx_in_pkt  <= 1'b0;
                            gmii_rx_dv <= 1'b0;
                        end else if (dec_k && (dec_d == K_30_7)) begin
                            gmii_rx_dv <= 1'b1;
                            gmii_rx_er <= 1'b1;
                            gmii_rxd   <= 8'hFF;
                        end else if (dec_code_err || dec_disp_err) begin
                            gmii_rx_dv <= 1'b1;
                            gmii_rx_er <= 1'b1;
                            gmii_rxd   <= dec_d;
                        end else begin
                            gmii_rx_dv <= 1'b1;
                            gmii_rxd   <= dec_d;
                        end
                    end
                end else begin
                    rx_in_pkt  <= 1'b0;
                    gmii_rx_dv <= 1'b0;
                end
            end
        end
    end

    // =========================================================================
    // 5. TX PCS + 8b/10b Encoder + Async FIFO -> OSERDESE2 (clk_125 -> 625 MHz)
    // =========================================================================
    reg       tx_enc_k;
    reg [7:0] tx_enc_d;
    wire [9:0] tx_code_125;
    wire       tx_enc_rd_pos;

    eth_8b10b_enc u_enc (
        .clk    (clk_125),
        .rst    (rst_125),
        .en     (1'b1),
        .din_k  (tx_enc_k),
        .din    (tx_enc_d),
        .dout   (tx_code_125),
        .rd_pos (tx_enc_rd_pos)
    );

    localparam [2:0] TX_IDLE_0 = 3'd0, TX_IDLE_1 = 3'd1,
                     TX_PKT    = 3'd2, TX_TR_R1  = 3'd3,
                     TX_AN_SET = 3'd4;

    reg [2:0] tx_pcs_st;
    reg [1:0] tx_an_sub;
    reg       tx_an_c2;
    reg       tx_even_toggle;
    reg       tx_en_d1;

    // Next-word combinational PCS mux (feeds registered eth_8b10b_enc)
    wire [15:0] tx_cfg_word = (an_state == AN_ACK) ? 16'h4001 : 16'h0001; // SGMII MAC 1G FD

    always @(posedge clk_125) begin
        if (rst_125 || an_restart) begin
            tx_pcs_st      <= (BYPASS_AN ? TX_IDLE_0 : TX_AN_SET);
            tx_an_sub      <= 2'd0;
            tx_an_c2       <= 1'b0;
            tx_even_toggle <= 1'b0;
            tx_enc_k       <= 1'b1;
            tx_enc_d       <= K_28_5;
            tx_en_d1       <= 1'b0;
        end else begin
            tx_even_toggle <= ~tx_even_toggle;
            tx_en_d1       <= gmii_tx_en;

            case (tx_pcs_st)
                TX_AN_SET: begin
                    if (an_state == AN_DATA && tx_an_sub == 2'd0 && !tx_even_toggle) begin
                        tx_pcs_st <= TX_IDLE_1;
                        tx_enc_k  <= 1'b1;
                        tx_enc_d  <= K_28_5;
                    end else begin
                        case (tx_an_sub)
                            2'd0: begin tx_enc_k <= 1'b1; tx_enc_d <= K_28_5; end
                            2'd1: begin tx_enc_k <= 1'b0; tx_enc_d <= tx_an_c2 ? D_2_2 : D_21_5; tx_an_c2 <= ~tx_an_c2; end
                            2'd2: begin tx_enc_k <= 1'b0; tx_enc_d <= tx_cfg_word[7:0]; end
                            2'd3: begin tx_enc_k <= 1'b0; tx_enc_d <= tx_cfg_word[15:8]; end
                        endcase
                        tx_an_sub <= tx_an_sub + 2'd1;
                    end
                end

                TX_IDLE_0: begin
                    if (an_state != AN_DATA) begin
                        tx_pcs_st <= TX_AN_SET;
                        tx_an_sub <= 2'd1;
                        tx_enc_k  <= 1'b1;
                        tx_enc_d  <= K_28_5;
                    end else if (gmii_tx_en) begin
                        // Start packet directly on /S/ replacing first preamble byte
                        tx_enc_k  <= 1'b1;
                        tx_enc_d  <= K_27_7;
                        tx_pcs_st <= TX_PKT;
                    end else begin
                        tx_enc_k  <= 1'b1;
                        tx_enc_d  <= K_28_5;
                        tx_pcs_st <= TX_IDLE_1;
                    end
                end

                TX_IDLE_1: begin
                    // Choose /I1/ (D5.6) if RD before K28.5 was + (K28.5 flips +->-, D5.6 keeps -),
                    // or /I2/ (D16.2) if RD before K28.5 was - (K28.5 flips -->+, D16.2 flips +->-)
                    tx_enc_k  <= 1'b0;
                    tx_enc_d  <= (tx_enc_rd_pos == 1'b1) ? D_5_6 : D_16_2;
                    tx_pcs_st <= TX_IDLE_0;
                end

                TX_PKT: begin
                    if (gmii_tx_en) begin
                        tx_enc_k <= gmii_tx_er ? 1'b1 : 1'b0;
                        tx_enc_d <= gmii_tx_er ? K_30_7 : gmii_txd;
                    end else begin
                        tx_enc_k  <= 1'b1;
                        tx_enc_d  <= K_29_7; // /T/
                        tx_pcs_st <= TX_TR_R1;
                    end
                end

                TX_TR_R1: begin
                    tx_enc_k <= 1'b1;
                    tx_enc_d <= K_23_7; // /R/
                    // Keep even alignment for K28.5 on TX_IDLE_0
                    if (tx_even_toggle)
                        tx_pcs_st <= TX_TR_R1; // send second /R/
                    else
                        tx_pcs_st <= TX_IDLE_0;
                end

                default: tx_pcs_st <= TX_IDLE_0;
            endcase
        end
    end

    // Pack two 10b symbols @ 62.5 MHz into 16x20b Gray async FIFO (clk_125 -> clk_312p5)
    reg [9:0]  tx_prev_code;
    reg        tx_pair_tog;
    (* ram_style = "distributed" *) reg [19:0] tx_fifo_mem [0:15];
    reg [4:0]  tx_wr_bin = 5'd0, tx_wr_gray = 5'd0;
    reg [4:0]  tx_rd_bin = 5'd0, tx_rd_gray = 5'd0;
    (* ASYNC_REG = "TRUE" *) reg [4:0] tx_wr_g1 = 5'd0, tx_wr_g2 = 5'd0;

    function [4:0] bin2gray5(input [4:0] b);
        bin2gray5 = b ^ (b >> 1);
    endfunction

    always @(posedge clk_125) begin
        if (rst_125) begin
            tx_prev_code <= K28_5_RD_NEG;
            tx_pair_tog  <= 1'b0;
            tx_wr_bin    <= 5'd0;
            tx_wr_gray   <= 5'd0;
        end else begin
            tx_prev_code <= tx_code_125;
            tx_pair_tog  <= ~tx_pair_tog;
            if (tx_pair_tog) begin
                tx_fifo_mem[tx_wr_bin[3:0]] <= {tx_code_125, tx_prev_code};
                tx_wr_bin                   <= tx_wr_bin + 5'd1;
                tx_wr_gray                  <= bin2gray5(tx_wr_bin + 5'd1);
            end
        end
    end

    reg [19:0] tx_pair_312;
    reg [2:0]  tx_nib_idx;
    reg [3:0]  tx_nib;
    reg        tx_primed;
    wire       tx_fifo_empty = (tx_rd_gray == tx_wr_g2);

    always @(posedge clk_312p5) begin
        if (rst_312p5) begin
            tx_wr_g1    <= 5'd0;
            tx_wr_g2    <= 5'd0;
            tx_rd_bin   <= 5'd0;
            tx_rd_gray  <= 5'd0;
            tx_pair_312 <= {D16_2_IDLE, K28_5_RD_NEG};
            tx_nib_idx  <= 3'd0;
            tx_nib      <= 4'd0;
            tx_primed   <= 1'b0;
        end else begin
            tx_wr_g1 <= tx_wr_gray;
            tx_wr_g2 <= tx_wr_g1;

            if (!tx_primed) begin
                tx_nib <= tx_pair_312[3:0];
                if (!tx_fifo_empty && (tx_wr_g2 != bin2gray5(5'd1)) && (tx_wr_g2 != bin2gray5(5'd2))) begin
                    tx_primed   <= 1'b1;
                    tx_pair_312 <= tx_fifo_mem[tx_rd_bin[3:0]];
                    tx_rd_bin   <= tx_rd_bin + 5'd1;
                    tx_rd_gray  <= bin2gray5(tx_rd_bin + 5'd1);
                    tx_nib_idx  <= 3'd0;
                end
            end else begin
                if (tx_nib_idx == 3'd4) begin
                    tx_nib_idx <= 3'd0;
                    tx_nib     <= tx_pair_312[19:16];
                    if (!tx_fifo_empty) begin
                        tx_pair_312 <= tx_fifo_mem[tx_rd_bin[3:0]];
                        tx_rd_bin   <= tx_rd_bin + 5'd1;
                        tx_rd_gray  <= bin2gray5(tx_rd_bin + 5'd1);
                    end else begin
                        tx_pair_312 <= {D16_2_IDLE, K28_5_RD_NEG};
                    end
                end else begin
                    tx_nib_idx <= tx_nib_idx + 3'd1;
                    case (tx_nib_idx)
                        3'd0:    tx_nib <= tx_pair_312[3:0];
                        3'd1:    tx_nib <= tx_pair_312[7:4];
                        3'd2:    tx_nib <= tx_pair_312[11:8];
                        default: tx_nib <= tx_pair_312[15:12];
                    endcase
                end
            end
        end
    end

    wire ser_tx_oq;
    OSERDESE2 #(
        .DATA_RATE_OQ  ("DDR"),
        .DATA_RATE_TQ  ("BUF"),
        .DATA_WIDTH    (4),
        .INIT_OQ       (1'b0),
        .INIT_TQ       (1'b0),
        .SERDES_MODE   ("MASTER"),
        .SRVAL_OQ      (1'b0),
        .SRVAL_TQ      (1'b0),
        .TBYTE_CTL     ("FALSE"),
        .TBYTE_SRC     ("FALSE"),
        .TRISTATE_WIDTH(1)
    ) u_oserdes_tx (
        .OFB       (),
        .OQ        (ser_tx_oq),
        .SHIFTOUT1 (),
        .SHIFTOUT2 (),
        .TBYTEOUT  (),
        .TFB       (),
        .TQ        (),
        .CLK       (clk_625_0),
        .CLKDIV    (clk_312p5),
        .D1        (tx_nib[0]),
        .D2        (tx_nib[1]),
        .D3        (tx_nib[2]),
        .D4        (tx_nib[3]),
        .D5        (1'b0),
        .D6        (1'b0),
        .D7        (1'b0),
        .D8        (1'b0),
        .OCE       (1'b1),
        .RST       (rst_312p5),
        .SHIFTIN1  (1'b0),
        .SHIFTIN2  (1'b0),
        .T1        (1'b0), .T2(1'b0), .T3(1'b0), .T4(1'b0),
        .TBYTEIN   (1'b0), .TCE(1'b0)
    );

    OBUFDS #(
        .IOSTANDARD ("LVDS_25")
    ) u_obuf_tx (
        .I  (ser_tx_oq),
        .O  (sgmii_tx_p),
        .OB (sgmii_tx_n)
    );

endmodule
`default_nettype wire
