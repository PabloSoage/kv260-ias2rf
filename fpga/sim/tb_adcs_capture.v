// SPDX-License-Identifier: BSD-2-Clause
// Simulation Testbench for Task 13: AD9253 One-Lane DDR Capture + 3-Wire SPI + SDR DDC + Link TX/RX
// Tests:
//   1) conv_spi power-up sequence against behavioral AD9253 (ID 0x8F) and AD9484 (ID 0x6C) SPI slaves.
//   2) adcs_capture 32-tap IDELAYE2 eye scan + simultaneous BITSLIP with skewed, unaligned AD9253 serial data.
//   3) Dual distinct tones (Ch A = f_S/8 = 6.25 MHz @ amp 6000, Ch B = f_S/4 = 12.50 MHz @ amp 4000).
//   4) sdr_ddc NCO tuning + CIC3 + Halfband decimation (div-8) -> link_pcs_tx -> link_pcs_rx CRC verification.
// Required mutations checked by run.ps1:
//   -Mutate fco_off_by_1 : fails sample framing & DDC recovery
//   -Mutate swap_ch      : fails channel tone assignment & DDC recovery

`timescale 1ns/1ps

module tb_adcs_capture;
    // -------------------------------------------------------------------------
    // Clocks & Reset
    // -------------------------------------------------------------------------
    reg rst        = 1'b1;
    reg refclk_200 = 1'b0;
    reg link_clk   = 1'b0;
    reg adc_dco    = 1'b0; // 400 MHz -> 800 Mb/s DDR -> 50 MSPS (1 UI = 1.25 ns)

    always #2.500 refclk_200 = ~refclk_200; // 200 MHz
    always #4.000 link_clk   = ~link_clk;   // 125 MHz
    always #1.250 adc_dco    = ~adc_dco;    // 400 MHz DCO

    // -------------------------------------------------------------------------
    // conv_spi + Behavioral AD9253 / AD9484 3-wire SPI Slaves
    // -------------------------------------------------------------------------
    wire       spi_sclk, spi_csb_r, spi_csb_s;
    wire       spi_sdio_o, spi_sdio_t;
    wire       init_done, init_err;
    wire [7:0] ad9253_id, ad9484_id;

    reg        req_valid = 1'b0;
    wire       req_ready;
    reg        req_target = 1'b1;
    reg        req_rw     = 1'b1;
    reg [12:0] req_addr   = 13'h0001;
    reg [7:0]  req_wdata  = 8'h00;
    wire       resp_valid;
    wire [7:0] resp_rdata;

    reg        slave_sdio_oe  = 1'b0;
    reg        slave_sdio_out = 1'b0;
    wire       sdio_pin_i     = !spi_sdio_t ? spi_sdio_o : (slave_sdio_oe ? slave_sdio_out : 1'b1);

    conv_spi #(
        .CLK_DIV           (2),   // 125 / 4 = 31.25 MHz fast sim SPI (or 3 -> 20.8 MHz < 25 MHz)
        .RESET_WAIT_CYCLES (16),
        .AUTO_INIT         (1'b1),
        .CHECK_AD9484      (1'b1)
    ) u_conv_spi (
        .clk        (link_clk),
        .rst        (rst),
        .start_init (1'b0),
        .req_valid  (req_valid),
        .req_ready  (req_ready),
        .req_target (req_target),
        .req_rw     (req_rw),
        .req_addr   (req_addr),
        .req_wdata  (req_wdata),
        .resp_valid (resp_valid),
        .resp_rdata (resp_rdata),
        .init_done  (init_done),
        .init_err   (init_err),
        .ad9253_id  (ad9253_id),
        .ad9484_id  (ad9484_id),
        .spi_sclk   (spi_sclk),
        .spi_csb_r  (spi_csb_r),
        .spi_csb_s  (spi_csb_s),
        .spi_sdio_o (spi_sdio_o),
        .spi_sdio_t (spi_sdio_t),
        .spi_sdio_i (sdio_pin_i)
    );

    // Behavioral AD9253 & AD9484 register models
    reg [7:0]  ad9253_regs [0:255];
    reg [7:0]  ad9484_regs [0:255];
    reg [4:0]  spi_bit_cnt;
    reg [23:0] spi_cmd;
    reg [7:0]  spi_addr_lat;
    reg        spi_is_read;
    reg [7:0]  spi_rd_shift;
    reg        spi_active_target; // 1 = AD9253, 0 = AD9484

    integer r_i;
    initial begin
        for (r_i = 0; r_i < 256; r_i = r_i + 1) begin
            ad9253_regs[r_i] = 8'h00;
            ad9484_regs[r_i] = 8'h00;
        end
        ad9253_regs[8'h01] = 8'h8F; // AD9253 Chip ID
        ad9253_regs[8'h05] = 8'h3F;
        ad9253_regs[8'h21] = 8'h30; // Default 2-lane bytewise
        ad9484_regs[8'h01] = 8'h6C; // AD9484 Chip ID
    end

    always @(negedge spi_csb_s or negedge spi_csb_r) begin
        spi_bit_cnt       <= 5'd0;
        spi_cmd           <= 24'd0;
        spi_is_read       <= 1'b0;
        spi_addr_lat      <= 8'h00;
        slave_sdio_oe     <= 1'b0;
        spi_active_target <= !spi_csb_s;
    end

    always @(posedge spi_csb_s or posedge spi_csb_r) begin
        if (spi_csb_s && spi_csb_r)
            slave_sdio_oe <= 1'b0;
    end

    always @(posedge spi_sclk) begin
        if (!spi_csb_s || !spi_csb_r) begin
            spi_cmd     <= {spi_cmd[22:0], spi_sdio_o};
            spi_bit_cnt <= spi_bit_cnt + 5'd1;
            if (spi_bit_cnt == 5'd15) begin
                // Capture R/W# (bit 23 shifted by 15 -> spi_cmd[14]) and A[7:0]
                spi_is_read  <= spi_cmd[14];
                spi_addr_lat <= {spi_cmd[6:0], spi_sdio_o};
                if (spi_cmd[14] == 1'b1) begin
                    spi_rd_shift <= !spi_csb_s ? ad9253_regs[{spi_cmd[6:0], spi_sdio_o}] :
                                                 ad9484_regs[{spi_cmd[6:0], spi_sdio_o}];
                end
            end else if (spi_bit_cnt == 5'd23) begin
                if (!spi_is_read) begin // Write
                    if (!spi_csb_s)
                        ad9253_regs[spi_addr_lat] <= {spi_cmd[6:0], spi_sdio_o};
                    else
                        ad9484_regs[spi_addr_lat] <= {spi_cmd[6:0], spi_sdio_o};
                end
            end
        end
    end

    always @(negedge spi_sclk) begin
        if ((!spi_csb_s || !spi_csb_r) && (spi_bit_cnt >= 5'd16) && (spi_bit_cnt <= 5'd23) && spi_is_read) begin
            slave_sdio_oe  <= 1'b1;
            slave_sdio_out <= spi_rd_shift[7];
            spi_rd_shift   <= {spi_rd_shift[6:0], 1'b0};
        end else begin
            slave_sdio_oe <= 1'b0;
        end
    end

    wire ad9253_configured = (ad9253_regs[8'h08] == 8'h00) &&
                             (ad9253_regs[8'h0B] == 8'h07) &&
                             (ad9253_regs[8'h14] == 8'h01) &&
                             (ad9253_regs[8'h18] == 8'h04) &&
                             (ad9253_regs[8'h21] == 8'h40);

    // -------------------------------------------------------------------------
    // Behavioral AD9253 One-Lane 16-bit DDR Serial Transmitter
    //   Ch A (D0): f_S / 8 = 6.25 MHz sine, amplitude 6000 LSB
    //   Ch B (D1): f_S / 4 = 12.50 MHz cosine, amplitude 4000 LSB
    //   Injected bit-slip offset (3 UI) + serial delay (0.55 ns wrt DCO edges)
    // -------------------------------------------------------------------------
    function automatic signed [13:0] tone_a_sample;
        input [2:0] idx;
        begin
            case (idx)
                3'd0: tone_a_sample =  14'sd0;
                3'd1: tone_a_sample =  14'sd4243;
                3'd2: tone_a_sample =  14'sd6000;
                3'd3: tone_a_sample =  14'sd4243;
                3'd4: tone_a_sample =  14'sd0;
                3'd5: tone_a_sample = -14'sd4243;
                3'd6: tone_a_sample = -14'sd6000;
                3'd7: tone_a_sample = -14'sd4243;
            endcase
        end
    endfunction

    function automatic signed [13:0] tone_b_sample;
        input [1:0] idx;
        begin
            case (idx)
                2'd0: tone_b_sample =  14'sd4000;
                2'd1: tone_b_sample =  14'sd0;
                2'd2: tone_b_sample = -14'sd4000;
                2'd3: tone_b_sample =  14'sd0;
            endcase
        end
    endfunction

    reg [3:0]  ui_idx = 4'd3; // Intentional non-zero UI start -> forces BITSLIP alignment!
    reg [2:0]  sample_idx = 3'd0;
    reg        fco_serial = 1'b0;
    reg        d0_serial  = 1'b0;
    reg        d1_serial  = 1'b0;
    reg [15:0] frame_a = 16'd0;
    reg [15:0] frame_b = 16'd0;
    localparam [15:0] FCO_WORD = 16'hFF00;

    // Launch serial data on BOTH edges of adc_dco (DDR 800 Mb/s); initial quadrature 90 deg via #0.625 on DCO -> capture sees skewed D
    reg adc_dco_quad = 1'b0;
    always @(adc_dco) adc_dco_quad <= #0.625 adc_dco; // 90 deg DCO phase wrt data transitions

    always @(adc_dco) begin
        if (!ad9253_configured) begin
            fco_serial <= 1'b0;
            d0_serial  <= 1'b0;
            d1_serial  <= 1'b0;
            ui_idx     <= 4'd3; // Non-zero UI offset so BITSLIP must engage
            sample_idx <= 3'd0;
            frame_a    <= {tone_a_sample(3'd0), 2'b00};
            frame_b    <= {tone_b_sample(2'd0), 2'b00};
        end else begin
            fco_serial <= FCO_WORD[15 - ui_idx];
            d0_serial  <= frame_a[15 - ui_idx];
            d1_serial  <= frame_b[15 - ui_idx];
            if (ui_idx == 4'd15) begin
                ui_idx     <= 4'd0;
                sample_idx <= sample_idx + 3'd1;
                frame_a    <= {tone_a_sample(sample_idx + 3'd1), 2'b00};
                frame_b    <= {tone_b_sample(sample_idx[1:0] + 2'd1), 2'b00};
            end else begin
                ui_idx <= ui_idx + 4'd1;
            end
        end
    end

    // Add board/package skew (+0.52 ns) to data+FCO relative to DCO so IDELAY eye scan must center tap
    wire fco_skewed, d0_skewed, d1_skewed;
    assign #0.52 fco_skewed = fco_serial;
    assign #0.52 d0_skewed  = d0_serial;
    assign #0.52 d1_skewed  = d1_serial;

    // -------------------------------------------------------------------------
    // DUT: adcs_capture + sdr_ddc + link_pcs_tx -> link_pcs_rx
    // -------------------------------------------------------------------------
    wire               adc_clk_div;
    wire               sample_valid;
    wire signed [13:0] cap_a, cap_b;
    wire               aligned, idelay_done, idelay_err, bitslip_err, idelay_rdy;
    wire [4:0]         best_tap;
    wire [3:0]         bitslip_cnt;

    adcs_capture #(
        .INST_IDELAYCTRL (1'b1)
    ) u_adcs_capture (
        .rst          (rst),
        .refclk_200m  (refclk_200),
        .enable       (init_done && !init_err),
        .adcs_dco_p   (adc_dco_quad),
        .adcs_dco_n   (~adc_dco_quad),
        .adcs_fco_p   (fco_skewed),
        .adcs_fco_n   (~fco_skewed),
        .adcs_d0_p    (d0_skewed),
        .adcs_d0_n    (~d0_skewed),
        .adcs_d1_p    (d1_skewed),
        .adcs_d1_n    (~d1_skewed),
        .clk_div      (adc_clk_div),
        .sample_valid (sample_valid),
        .sample_a     (cap_a),
        .sample_b     (cap_b),
        .aligned      (aligned),
        .idelay_done  (idelay_done),
        .idelay_err   (idelay_err),
        .bitslip_err  (bitslip_err),
        .best_tap     (best_tap),
        .bitslip_cnt  (bitslip_cnt),
        .idelay_rdy   (idelay_rdy)
    );

    reg [2:0] adc_rst_sync = 3'b111;
    always @(posedge adc_clk_div or posedge rst) begin
        if (rst) adc_rst_sync <= 3'b111;
        else     adc_rst_sync <= {adc_rst_sync[1:0], 1'b0};
    end
    wire adc_rst = adc_rst_sync[2];

    reg [63:0] timestamp_cnt = 64'd0;
    always @(posedge link_clk) begin
        if (rst) timestamp_cnt <= 64'd0;
        else     timestamp_cnt <= timestamp_cnt + 64'd1;
    end

    wire        pkt_valid, pkt_ready, pkt_sop, pkt_eop;
    wire [7:0]  pkt_stream_id;
    wire [15:0] pkt_len;
    wire [31:0] pkt_seq;
    wire [63:0] pkt_timestamp, pkt_data;
    wire [23:0] ddc_dropped;

    sdr_ddc #(
        .STREAM_ID_A (8'h04),
        .STREAM_ID_B (8'h05),
        .FIFO_AW     (9)
    ) u_sdr_ddc (
        .adc_clk       (adc_clk_div),
        .adc_rst       (adc_rst),
        .sample_valid  (sample_valid),
        .sample_a      (cap_a),
        .sample_b      (cap_b),
        .ch_enable     (2'b11),
        .nco_ftw_a     (32'h2000_0000), // f_S / 8 = 6.25 MHz
        .nco_ftw_b     (32'h4000_0000), // f_S / 4 = 12.50 MHz
        .decim_ratio   (16'd8),         // CIC div-4 + Halfband div-2 = 6.25 MSPS
        .words_per_pkt (10'd16),        // 16 words = 128 bytes = 32 IQ samples/pkt
        .link_clk      (link_clk),
        .link_rst      (rst),
        .timestamp_cnt (timestamp_cnt),
        .pkt_valid     (pkt_valid),
        .pkt_ready     (pkt_ready),
        .pkt_sop       (pkt_sop),
        .pkt_eop       (pkt_eop),
        .pkt_stream_id (pkt_stream_id),
        .pkt_len       (pkt_len),
        .pkt_seq       (pkt_seq),
        .pkt_timestamp (pkt_timestamp),
        .pkt_data      (pkt_data),
        .dropped_cnt   (ddc_dropped)
    );

    wire [7:0] tx_l0, tx_l1;
    link_pcs_tx #(
        .AM_PERIOD (64)
    ) u_link_tx (
        .clk           (link_clk),
        .rst           (rst),
        .pkt_valid     (pkt_valid),
        .pkt_ready     (pkt_ready),
        .pkt_sop       (pkt_sop),
        .pkt_eop       (pkt_eop),
        .pkt_stream_id (pkt_stream_id),
        .pkt_len       (pkt_len),
        .pkt_seq       (pkt_seq),
        .pkt_timestamp (pkt_timestamp),
        .pkt_data      (pkt_data),
        .dropped_cnt   (ddc_dropped),
        .local_status  (16'h0001),
        .tx_byte_l0    (tx_l0),
        .tx_byte_l1    (tx_l1)
    );

    wire        rx_valid, rx_sop, rx_eop;
    wire [7:0]  rx_stream_id;
    wire [15:0] rx_len;
    wire [31:0] rx_seq;
    wire [63:0] rx_timestamp, rx_data;
    wire        pkt_done_valid, pkt_done_ok, pkt_done_err;
    wire        l0_lock, l1_lock, deskew_lock;
    wire [31:0] pkt_rx_cnt, pkt_crc_err_cnt;

    link_pcs_rx u_link_rx (
        .clk                (link_clk),
        .rst                (rst),
        .link_ready         (1'b1),
        .rx_byte_l0         (tx_l0),
        .rx_byte_l1         (tx_l1),
        .out_valid          (rx_valid),
        .out_sop            (rx_sop),
        .out_eop            (rx_eop),
        .out_stream_id      (rx_stream_id),
        .out_len            (rx_len),
        .out_seq            (rx_seq),
        .out_timestamp      (rx_timestamp),
        .out_data           (rx_data),
        .pkt_done_valid     (pkt_done_valid),
        .pkt_done_ok        (pkt_done_ok),
        .pkt_done_err       (pkt_done_err),
        .l0_block_lock      (l0_lock),
        .l1_block_lock      (l1_lock),
        .deskew_lock        (deskew_lock),
        .skew_blocks        (),
        .remote_status      (),
        .remote_dropped_cnt (),
        .sh_err_cnt_l0      (),
        .sh_err_cnt_l1      (),
        .pkt_rx_cnt         (pkt_rx_cnt),
        .crc_err_cnt        (pkt_crc_err_cnt),
        .l0_rx_blk_valid    (),
        .l0_rx_blk_ok       (),
        .l1_rx_blk_valid    (),
        .l1_rx_blk_ok       ()
    );

    // -------------------------------------------------------------------------
    // Verification Logic & Scoreboards
    // -------------------------------------------------------------------------
    integer cap_ok_cnt   = 0;
    integer cap_err_cnt  = 0;
    reg     phase_locked = 1'b0;
    reg [2:0] exp_idx    = 3'd0;
    integer k_p;

    always @(posedge adc_clk_div) begin
        if (rst || !aligned) begin
            cap_ok_cnt   <= 0;
            cap_err_cnt  <= 0;
            phase_locked <= 1'b0;
        end else if (sample_valid) begin
            if (!phase_locked) begin : lock_phase_blk
                reg found_phase;
                found_phase = 1'b0;
                // Lock onto the tone_a_sample phase on first captured sample
                for (k_p = 0; k_p < 8; k_p = k_p + 1) begin
                    if (!found_phase && cap_a == tone_a_sample(k_p[2:0]) && cap_b == tone_b_sample(k_p[1:0])) begin
                        found_phase  = 1'b1;
                        phase_locked <= 1'b1;
                        exp_idx      <= k_p[2:0] + 3'd1;
                        cap_ok_cnt   <= cap_ok_cnt + 1;
                    end
                end
                if (!found_phase)
                    cap_err_cnt <= cap_err_cnt + 1;
            end else begin
                if ((cap_a == tone_a_sample(exp_idx)) && (cap_b == tone_b_sample(exp_idx[1:0]))) begin
                    cap_ok_cnt <= cap_ok_cnt + 1;
                end else begin
                    cap_err_cnt <= cap_err_cnt + 1;
                    if (cap_err_cnt < 8)
                        $display("WARN sample mismatch idx=%0d: got A=%0d B=%0d, exp A=%0d B=%0d",
                                 exp_idx, cap_a, cap_b, tone_a_sample(exp_idx), tone_b_sample(exp_idx[1:0]));
                end
                exp_idx <= exp_idx + 3'd1;
            end
        end
    end

    // Track DDC packets per stream ID & measure baseband IQ magnitude after filter settle
    integer pkts_a = 0, pkts_b = 0;
    integer mag_sum_a = 0, mag_cnt_a = 0;
    integer mag_sum_b = 0, mag_cnt_b = 0;
    reg signed [15:0] iq_i0, iq_q0, iq_i1, iq_q1;
    real mag0, mag1;

    always @(posedge link_clk) begin
        if (rst) begin
            pkts_a    <= 0;
            pkts_b    <= 0;
            mag_sum_a <= 0;
            mag_cnt_a <= 0;
            mag_sum_b <= 0;
            mag_cnt_b <= 0;
        end else begin
            if (rx_valid) begin
                iq_i0 = $signed(rx_data[15:0]);
                iq_q0 = $signed(rx_data[31:16]);
                iq_i1 = $signed(rx_data[47:32]);
                iq_q1 = $signed(rx_data[63:48]);
                mag0  = $sqrt(1.0 * iq_i0 * iq_i0 + 1.0 * iq_q0 * iq_q0);
                mag1  = $sqrt(1.0 * iq_i1 * iq_i1 + 1.0 * iq_q1 * iq_q1);

                // Ignore pkt 0 (CIC + Halfband step-response transient)
                if ((rx_stream_id == 8'h04) && (pkts_a >= 1)) begin
                    mag_sum_a <= mag_sum_a + $rtoi(mag0 + mag1);
                    mag_cnt_a <= mag_cnt_a + 2;
                end else if ((rx_stream_id == 8'h05) && (pkts_b >= 1)) begin
                    mag_sum_b <= mag_sum_b + $rtoi(mag0 + mag1);
                    mag_cnt_b <= mag_cnt_b + 2;
                end
            end

            if (pkt_done_valid) begin
                if (!pkt_done_ok || pkt_done_err) begin
                    $display("FAIL link packet CRC error on stream 0x%02h", rx_stream_id);
                    $fatal(1, "FAIL packet CRC error");
                end
                if (rx_stream_id == 8'h04) pkts_a <= pkts_a + 1;
                if (rx_stream_id == 8'h05) pkts_b <= pkts_b + 1;
            end
        end
    end

    // -------------------------------------------------------------------------
    // Main Test Sequence
    // -------------------------------------------------------------------------
    integer avg_mag_a, avg_mag_b;

    initial begin
        #100;
        rst = 1'b0;

        // Wait for conv_spi power-up sequence + Chip ID reads
        wait (init_done == 1'b1);
        if (init_err) begin
            $display("FAIL conv_spi init_err=1 (ad9253_id=0x%02h, ad9484_id=0x%02h)", ad9253_id, ad9484_id);
            $fatal(1, "FAIL conv_spi init");
        end
        if (!ad9253_configured) begin
            $display("FAIL AD9253 registers not configured to 1-lane DDR mode");
            $fatal(1, "FAIL AD9253 config");
        end
        $display("INFO conv_spi OK: ad9253_id=0x%02h ad9484_id=0x%02h reg21=0x%02h reg22=0x%02h",
                 ad9253_id, ad9484_id, ad9253_regs[8'h21], ad9253_regs[8'h22]);

        // Test host read via conv_spi (verify 0x18 == 0x04 on AD9253)
        @(posedge link_clk);
        wait (req_ready == 1'b1);
        req_target <= 1'b1;
        req_rw     <= 1'b1;
        req_addr   <= 13'h0018;
        req_valid  <= 1'b1;
        @(posedge link_clk);
        req_valid  <= 1'b0;
        wait (resp_valid == 1'b1);
        if (resp_rdata != 8'h04) begin
            $display("FAIL conv_spi host readback 0x18 = 0x%02h (expected 0x04)", resp_rdata);
            $fatal(1, "FAIL conv_spi host readback");
        end

        // Wait for adcs_capture IDELAY + BITSLIP lock (up to 6250 cycles = 50 us)
        begin : wait_align_blk
            integer to_cnt;
            to_cnt = 0;
            while (!aligned && (to_cnt < 6250)) begin
                @(posedge link_clk);
                to_cnt = to_cnt + 1;
            end
            if (!aligned) begin
                $display("FAIL timeout waiting for adcs_capture aligned (idelay_done=%b err=%b bitslip_err=%b)",
                         idelay_done, idelay_err, bitslip_err);
                $fatal(1, "FAIL align timeout");
            end
        end

        $display("INFO adcs_capture aligned: best_tap=%0d bitslip_cnt=%0d idelay_err=%b",
                 best_tap, bitslip_cnt, idelay_err);

        // Wait for raw samples AND settled DDC packets on both stream IDs (up to 30000 cycles = 240 us)
        begin : wait_pkts_blk
            integer to_cnt;
            to_cnt = 0;
            while (!((cap_ok_cnt >= 128) && (pkts_a >= 4) && (pkts_b >= 4)) && (to_cnt < 30000)) begin
                @(posedge link_clk);
                to_cnt = to_cnt + 1;
            end
            if (!((cap_ok_cnt >= 128) && (pkts_a >= 4) && (pkts_b >= 4))) begin
                $display("FAIL timeout: cap_ok=%0d cap_err=%0d pkts_a=%0d pkts_b=%0d deskew=%b",
                         cap_ok_cnt, cap_err_cnt, pkts_a, pkts_b, deskew_lock);
                $fatal(1, "FAIL packet/capture timeout");
            end
        end

        if (cap_err_cnt > 0 || cap_ok_cnt < 128) begin
            $display("FAIL raw ADC sample capture mismatch: ok=%0d err=%0d", cap_ok_cnt, cap_err_cnt);
            $fatal(1, "FAIL raw sample capture");
        end

        if (ddc_dropped != 24'd0 || pkt_crc_err_cnt != 32'd0) begin
            $display("FAIL link/DDC error: dropped=%0d crc_err=%0d", ddc_dropped, pkt_crc_err_cnt);
            $fatal(1, "FAIL ddc/link errors");
        end

        if (mag_cnt_a < 32 || mag_cnt_b < 32) begin
            $display("FAIL insufficient settled DDC samples: A=%0d B=%0d", mag_cnt_a, mag_cnt_b);
            $fatal(1, "FAIL insufficient DDC samples");
        end

        avg_mag_a = mag_sum_a / mag_cnt_a;
        avg_mag_b = mag_sum_b / mag_cnt_b;

        // Expected baseband IQ magnitudes (14-bit sample << 2 -> 16-bit scale * 0.5 mixer DC gain):
        //   Ch A (6000 * 4 * 0.5) = 12000, Ch B (4000 * 4 * 0.5) = 8000
        if ((avg_mag_a < 11000) || (avg_mag_a > 13000)) begin
            $display("FAIL Ch A DDC baseband magnitude out of range: %0d (expected ~12000)", avg_mag_a);
            $fatal(1, "FAIL Ch A DDC mag");
        end
        if ((avg_mag_b < 7200) || (avg_mag_b > 8800)) begin
            $display("FAIL Ch B DDC baseband magnitude out of range: %0d (expected ~8000)", avg_mag_b);
            $fatal(1, "FAIL Ch B DDC mag");
        end

        $display("PASS tb_adcs_capture: best_tap=%0d bitslip=%0d cap_ok=%0d pkts_a=%0d pkts_b=%0d mag_a=%0d mag_b=%0d crc_err=%0d",
                 best_tap, bitslip_cnt, cap_ok_cnt, pkts_a, pkts_b, avg_mag_a, avg_mag_b, pkt_crc_err_cnt);
        $finish;
    end
endmodule
