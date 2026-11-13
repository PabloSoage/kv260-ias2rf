// SPDX-License-Identifier: BSD-2-Clause
// Simulation Testbench for Task 14: AD9708 Radar LFM Chirp (dac_radar) & AD9767 Interleaved SDR TX (dac_sdr)
// Verifies:
//   1) AD9708 digital setup/hold/pulsewidth timing (t_S >= 2.0 ns, t_H >= 1.5 ns, t_LPW >= 3.5 ns).
//   2) Radar up-chirp LFM DFT spectral progression (20 MHz -> 36 MHz @ 100 MSPS; early bin < late bin).
//   3) AD9767 interleaved protocol (IQSEL only transitions when IQCLK==0 & IQWRT==0, t_S/t_H/t_LPW,
//      IQRESET /2 divider synchronization) fed via link_pcs_tx -> link_pcs_rx (Stream ID 0x10).
//   4) Complex 64-point FFT on recovered AD9767 (I + jQ) verifies >40 dB SSB image rejection (+4 vs -4 bin),
//      plus FIFO underflow counter behavior.
// Required mutations checked by run.ps1:
//   -Mutate iq_swap            : flips +f_tone to -f_tone image -> fails complex FFT
//   -Mutate chirp_slope_sign   : reverses chirp frequency progression -> fails early/late DFT check
//   -Mutate dac_clk_edge_wrong : aligns DAC clock rising edges with data transitions -> fails t_S/t_H timing

`timescale 1ns/1ps

module tb_dac_tx;
    localparam real PI = 3.14159265358979323846;

    // -------------------------------------------------------------------------
    // Clocks & Reset
    // -------------------------------------------------------------------------
    reg rst      = 1'b1;
    reg dac_clk  = 1'b0; // 100 MHz (T = 10.0 ns -> t_S = 5 ns, t_H = 5 ns, t_LPW = 5 ns on ODDR)
    reg link_clk = 1'b0; // 125 MHz (T = 8.0 ns)

    always #5.0 dac_clk  = ~dac_clk;  // 100 MHz
    always #4.0 link_clk = ~link_clk; // 125 MHz

    // -------------------------------------------------------------------------
    // DUT 1: dac_radar (AD9708 LFM Chirp @ 100 MSPS)
    //   Start f0 = 20.0 MHz (0x3333_3333), sweep +16.0 MHz over 512 clocks -> 36.0 MHz
    // -------------------------------------------------------------------------
    reg         chirp_enable = 1'b0;
    reg         chirp_trig   = 1'b0;
    wire        chirp_active;
    wire [31:0] pulse_cnt;
    wire        dacr_clk;
    wire [7:0]  dacr_d;

    dac_radar u_dac_radar (
        .dac_clk      (dac_clk),
        .dac_rst      (rst),
        .chirp_enable (chirp_enable),
        .chirp_trig   (chirp_trig),
        .f0_ftw       (32'h3333_3333),      // 20.0 MHz @ 100 MHz
        .df_ftw       (32'sd1342177),       // +0.03125 MHz/clk -> +16 MHz over 512 clocks
        .pulse_len    (32'd512),
        .pri_len      (32'd0),
        .amp_scale    (8'd240),
        .chirp_active (chirp_active),
        .pulse_cnt    (pulse_cnt),
        .dacr_clk     (dacr_clk),
        .dacr_d       (dacr_d)
    );

    // Behavioral AD9708 timing & sample monitor
    real dacr_d_chg_t   = -100.0;
    real dacr_clk_rise_t = -100.0;
    real dacr_clk_fall_t = -100.0;
    reg  dacr_check_armed = 1'b0;
    integer dacr_timing_errs = 0;

    integer chirp_buf [0:511];
    integer chirp_cap_cnt = 0;

    always @(dacr_d) begin
        dacr_d_chg_t = $realtime;
        if (dacr_check_armed && (dacr_clk_rise_t > 0.0) && (($realtime - dacr_clk_rise_t) < 1.5)) begin
            $display("FAIL AD9708 hold violation t_H=%0.3f ns (< 1.5 ns) at t=%0.3f", $realtime - dacr_clk_rise_t, $realtime);
            dacr_timing_errs = dacr_timing_errs + 1;
        end
    end

    always @(posedge dacr_clk) begin
        if (dacr_check_armed) begin
            if (($realtime - dacr_d_chg_t) < 2.0) begin
                $display("FAIL AD9708 setup violation t_S=%0.3f ns (< 2.0 ns) at t=%0.3f", $realtime - dacr_d_chg_t, $realtime);
                dacr_timing_errs = dacr_timing_errs + 1;
            end
            if ((dacr_clk_fall_t > 0.0) && (($realtime - dacr_clk_fall_t) < 3.5)) begin
                $display("FAIL AD9708 low pulsewidth t_LPW=%0.3f ns (< 3.5 ns)", $realtime - dacr_clk_fall_t);
                dacr_timing_errs = dacr_timing_errs + 1;
            end
        end
        dacr_clk_rise_t = $realtime;

        if (chirp_active && (chirp_cap_cnt < 512)) begin
            chirp_buf[chirp_cap_cnt] = dacr_d - 128;
            chirp_cap_cnt = chirp_cap_cnt + 1;
        end
    end

    always @(negedge dacr_clk) begin
        if (dacr_check_armed && (dacr_clk_rise_t > 0.0) && (($realtime - dacr_clk_rise_t) < 3.5)) begin
            $display("FAIL AD9708 high pulsewidth t_LPW=%0.3f ns (< 3.5 ns)", $realtime - dacr_clk_rise_t);
            dacr_timing_errs = dacr_timing_errs + 1;
        end
        dacr_clk_fall_t = $realtime;
    end

    // -------------------------------------------------------------------------
    // DUT 2: link_pcs_tx -> link_pcs_rx -> dac_sdr (AD9767 Interleaved)
    // -------------------------------------------------------------------------
    reg         tx_pkt_valid = 1'b0;
    wire        tx_pkt_ready;
    reg         tx_pkt_sop   = 1'b0;
    reg         tx_pkt_eop   = 1'b0;
    reg  [31:0] tx_pkt_seq   = 32'd0;
    reg  [63:0] tx_pkt_data  = 64'd0;

    wire [7:0]  pcs_l0, pcs_l1;
    link_pcs_tx #(
        .AM_PERIOD (64)
    ) u_link_tx (
        .clk           (link_clk),
        .rst           (rst),
        .pkt_valid     (tx_pkt_valid),
        .pkt_ready     (tx_pkt_ready),
        .pkt_sop       (tx_pkt_sop),
        .pkt_eop       (tx_pkt_eop),
        .pkt_stream_id (8'h10),
        .pkt_len       (16'd128), // 16 x 64-bit words = 32 IQ pairs
        .pkt_seq       (tx_pkt_seq),
        .pkt_timestamp (64'h0000_0000_0000_1234),
        .pkt_data      (tx_pkt_data),
        .dropped_cnt   (24'd0),
        .local_status  (16'h0001),
        .tx_byte_l0    (pcs_l0),
        .tx_byte_l1    (pcs_l1)
    );

    wire        rx_valid, rx_sop, rx_eop;
    wire [7:0]  rx_stream_id;
    wire [63:0] rx_data;
    wire        deskew_lock;
    wire [31:0] crc_err_cnt;

    link_pcs_rx u_link_rx (
        .clk                (link_clk),
        .rst                (rst),
        .link_ready         (1'b1),
        .rx_byte_l0         (pcs_l0),
        .rx_byte_l1         (pcs_l1),
        .out_valid          (rx_valid),
        .out_sop            (rx_sop),
        .out_eop            (rx_eop),
        .out_stream_id      (rx_stream_id),
        .out_len            (),
        .out_seq            (),
        .out_timestamp      (),
        .out_data           (rx_data),
        .pkt_done_valid     (),
        .pkt_done_ok        (),
        .pkt_done_err       (),
        .l0_block_lock      (),
        .l1_block_lock      (),
        .deskew_lock        (deskew_lock),
        .skew_blocks        (),
        .remote_status      (),
        .remote_dropped_cnt (),
        .sh_err_cnt_l0      (),
        .sh_err_cnt_l1      (),
        .pkt_rx_cnt         (),
        .crc_err_cnt        (crc_err_cnt),
        .l0_rx_blk_valid    (),
        .l0_rx_blk_ok       (),
        .l1_rx_blk_valid    (),
        .l1_rx_blk_ok       ()
    );

    reg         sdr_tx_enable = 1'b0;
    wire        sdr_s_ready;
    wire [31:0] underflow_cnt;
    wire [13:0] dacs_d;
    wire        dacs_iqclk, dacs_iqwrt, dacs_iqsel, dacs_iqreset;

    dac_sdr #(
        .FIFO_AW (9)
    ) u_dac_sdr (
        .link_clk        (link_clk),
        .link_rst        (rst),
        .s_valid         (rx_valid && (rx_stream_id == 8'h10)),
        .s_ready         (sdr_s_ready),
        .s_data          (rx_data),
        .dac_clk         (dac_clk),
        .dac_rst         (rst),
        .tx_enable       (sdr_tx_enable),
        .underflow_cnt   (underflow_cnt),
        .fifo_level_link (),
        .dacs_d          (dacs_d),
        .dacs_iqclk      (dacs_iqclk),
        .dacs_iqwrt      (dacs_iqwrt),
        .dacs_iqsel      (dacs_iqsel),
        .dacs_iqreset    (dacs_iqreset)
    );

    // Behavioral AD9767 timing checker & interleaved DAC de-interleaver
    real dacs_d_chg_t     = -100.0;
    real dacs_iqsel_chg_t = -100.0;
    real dacs_wrt_rise_t  = -100.0;
    real dacs_wrt_fall_t  = -100.0;
    integer dacs_timing_errs = 0;

    reg [13:0] ad9767_latch_i = 14'h2000;
    reg [13:0] ad9767_latch_q = 14'h2000;
    reg        ad9767_div2    = 1'b0;
    integer    sdr_i_buf [0:127];
    integer    sdr_q_buf [0:127];
    integer    sdr_cap_cnt = 0;

    always @(dacs_d) begin
        dacs_d_chg_t = $realtime;
        if (sdr_tx_enable && (dacs_wrt_rise_t > 0.0) && (($realtime - dacs_wrt_rise_t) < 1.5)) begin
            $display("FAIL AD9767 hold violation on D: t_H=%0.3f ns (< 1.5 ns)", $realtime - dacs_wrt_rise_t);
            dacs_timing_errs = dacs_timing_errs + 1;
        end
    end

    always @(dacs_iqsel) begin
        dacs_iqsel_chg_t = $realtime;
        if (sdr_tx_enable && (dacs_iqclk !== 1'b0 || dacs_iqwrt !== 1'b0)) begin
            $display("FAIL AD9767 IQSEL changed while IQCLK=%b IQWRT=%b at t=%0.3f", dacs_iqclk, dacs_iqwrt, $realtime);
            dacs_timing_errs = dacs_timing_errs + 1;
        end
    end

    always @(posedge dacs_iqwrt) begin
        if (sdr_tx_enable) begin
            if (($realtime - dacs_d_chg_t) < 2.0) begin
                $display("FAIL AD9767 setup violation on D: t_S=%0.3f ns (< 2.0 ns) at t=%0.3f", $realtime - dacs_d_chg_t, $realtime);
                dacs_timing_errs = dacs_timing_errs + 1;
            end
            if (($realtime - dacs_iqsel_chg_t) < 2.0) begin
                $display("FAIL AD9767 setup violation on IQSEL: t_S=%0.3f ns (< 2.0 ns) at t=%0.3f", $realtime - dacs_iqsel_chg_t, $realtime);
                dacs_timing_errs = dacs_timing_errs + 1;
            end
            if ((dacs_wrt_fall_t > 0.0) && (($realtime - dacs_wrt_fall_t) < 3.5)) begin
                $display("FAIL AD9767 IQWRT low pulsewidth t_LPW=%0.3f ns (< 3.5 ns)", $realtime - dacs_wrt_fall_t);
                dacs_timing_errs = dacs_timing_errs + 1;
            end
            if (dacs_iqsel)
                ad9767_latch_i <= dacs_d;
            else
                ad9767_latch_q <= dacs_d;
        end
        dacs_wrt_rise_t = $realtime;
    end

    always @(negedge dacs_iqwrt) begin
        if (sdr_tx_enable && (dacs_wrt_rise_t > 0.0) && (($realtime - dacs_wrt_rise_t) < 3.5)) begin
            $display("FAIL AD9767 IQWRT high pulsewidth t_LPW=%0.3f ns (< 3.5 ns)", $realtime - dacs_wrt_rise_t);
            dacs_timing_errs = dacs_timing_errs + 1;
        end
        dacs_wrt_fall_t = $realtime;
    end

    // AD9767 /2 IQCLK divider synchronized by IQRESET
    integer s_i, s_q;
    reg sdr_active_started = 1'b0;
    always @(posedge dacs_iqclk or posedge dacs_iqreset) begin
        if (dacs_iqreset) begin
            ad9767_div2 <= 1'b0; // First rising IQCLK after reset releases updates DACs (0->1)
        end else if (sdr_tx_enable) begin
            ad9767_div2 <= ~ad9767_div2;
            if (ad9767_div2 == 1'b0) begin
                s_i = ad9767_latch_i - 8192;
                s_q = ad9767_latch_q - 8192;
                // Wait until non-midscale valid tone arrives (skipping empty startup intervals)
                if (!sdr_active_started && ((s_i != 0) || (s_q != 0)))
                    sdr_active_started = 1'b1;
                if (sdr_active_started && (sdr_cap_cnt < 128)) begin
                    sdr_i_buf[sdr_cap_cnt] = s_i;
                    sdr_q_buf[sdr_cap_cnt] = s_q;
                    sdr_cap_cnt = sdr_cap_cnt + 1;
                end
            end
        end
    end

    // -------------------------------------------------------------------------
    // Task to drive Link TX complex SSB packet (+f_iq = +f_sample / 16)
    // -------------------------------------------------------------------------
    integer iq_gen_idx = 0;
    function [31:0] gen_ssb_iq;
        input integer n;
        reg signed [15:0] ii, qq;
        begin
            ii = $rtoi(28000.0 * $cos(2.0 * PI * n / 16.0));
            qq = $rtoi(28000.0 * $sin(2.0 * PI * n / 16.0));
            gen_ssb_iq = {qq, ii};
        end
    endfunction

    task automatic send_sdr_packet;
        integer w;
        reg [31:0] iq0, iq1;
        begin
            for (w = 0; w < 16; w = w + 1) begin
                iq0 = gen_ssb_iq(iq_gen_idx);
                iq1 = gen_ssb_iq(iq_gen_idx + 1);
                iq_gen_idx = iq_gen_idx + 2;

                tx_pkt_valid <= 1'b1;
                tx_pkt_sop   <= (w == 0);
                tx_pkt_eop   <= (w == 15);
                tx_pkt_data  <= {iq1, iq0};
                @(posedge link_clk);
                while (!tx_pkt_ready)
                    @(posedge link_clk);
            end
            tx_pkt_valid <= 1'b0;
            tx_pkt_sop   <= 1'b0;
            tx_pkt_eop   <= 1'b0;
            tx_pkt_seq   <= tx_pkt_seq + 32'd1;
        end
    endtask

    // -------------------------------------------------------------------------
    // DFT / FFT Verification & Main Stimulus
    // -------------------------------------------------------------------------
    integer bin_1, bin_2;
    real    mag_pos, mag_neg;
    integer und_before, und_during;

    task automatic find_real_dft_peak;
        input  integer start_idx;
        output integer peak_bin;
        integer k, n;
        real re, im, mag, best_mag;
        begin
            best_mag = -1.0;
            peak_bin = 0;
            for (k = 1; k < 64; k = k + 1) begin
                re = 0.0;
                im = 0.0;
                for (n = 0; n < 128; n = n + 1) begin
                    re = re + chirp_buf[start_idx + n] * $cos(2.0 * PI * k * n / 128.0);
                    im = im - chirp_buf[start_idx + n] * $sin(2.0 * PI * k * n / 128.0);
                end
                mag = re*re + im*im;
                if (mag > best_mag) begin
                    best_mag = mag;
                    peak_bin = k;
                end
            end
        end
    endtask

    task automatic measure_complex_bin;
        input  integer bin_signed;
        output real mag_out;
        integer n;
        real re, im, angle;
        begin
            re = 0.0;
            im = 0.0;
            for (n = 0; n < 64; n = n + 1) begin
                angle = 2.0 * PI * bin_signed * n / 64.0;
                // (I + jQ) * (cos - j*sin)
                re = re + (sdr_i_buf[16 + n] * $cos(angle) + sdr_q_buf[16 + n] * $sin(angle));
                im = im + (sdr_q_buf[16 + n] * $cos(angle) - sdr_i_buf[16 + n] * $sin(angle));
            end
            mag_out = $sqrt(re*re + im*im);
        end
    endtask

    integer p;
    initial begin
        #100;
        rst = 1'b0;
        repeat (5) @(posedge dac_clk);
        dacr_check_armed = 1'b1;
        chirp_enable     = 1'b1;
        sdr_tx_enable    = 1'b1;

        // Wait for link lane deskew while observing AD9767 underflow counter increment on empty FIFO
        while (!deskew_lock) @(posedge link_clk);
        repeat (30) @(posedge dac_clk);
        und_before = underflow_cnt;
        if (und_before == 0) begin
            $display("FAIL underflow_cnt stayed 0 when FIFO was empty with tx_enable=1");
            $fatal(1, "FAIL underflow counter");
        end

        // Trigger AD9708 LFM chirp + stream 8 Link TX IQ packets (256 IQ pairs) to AD9767
        @(posedge dac_clk);
        chirp_trig <= 1'b1;
        @(posedge dac_clk);
        chirp_trig <= 1'b0;

        for (p = 0; p < 8; p = p + 1)
            send_sdr_packet();

        // Wait until chirp_cap_cnt == 512 and sdr_cap_cnt >= 96
        begin : wait_cap
            integer w_cnt;
            w_cnt = 0;
            while (((chirp_cap_cnt < 512) || (sdr_cap_cnt < 96)) && (w_cnt < 8000)) begin
                @(posedge dac_clk);
                w_cnt = w_cnt + 1;
            end
            if ((chirp_cap_cnt < 512) || (sdr_cap_cnt < 96)) begin
                $display("FAIL capture timeout: chirp=%0d sdr=%0d", chirp_cap_cnt, sdr_cap_cnt);
                $fatal(1, "FAIL capture timeout");
            end
        end

        if ((dacr_timing_errs > 0) || (dacs_timing_errs > 0)) begin
            $display("FAIL DAC timing errors: AD9708=%0d AD9767=%0d", dacr_timing_errs, dacs_timing_errs);
            $fatal(1, "FAIL DAC timing");
        end

        if (crc_err_cnt != 32'd0) begin
            $display("FAIL link RX CRC errors: %0d", crc_err_cnt);
            $fatal(1, "FAIL CRC error");
        end

        // Verify Radar LFM up-chirp DFT peak moved upward (early window -> late window)
        find_real_dft_peak(32,  bin_1);
        find_real_dft_peak(320, bin_2);
        if (bin_2 <= (bin_1 + 5)) begin
            $display("FAIL LFM chirp slope not increasing: bin_early=%0d bin_late=%0d", bin_1, bin_2);
            $fatal(1, "FAIL LFM chirp slope");
        end

        // Verify AD9767 complex FFT +4 bin (+f_sample/16) >> -4 bin (-f_sample/16)
        measure_complex_bin(4,  mag_pos);
        measure_complex_bin(-4, mag_neg);
        if (mag_pos < (100.0 * (mag_neg + 1.0))) begin : dbg_ssb
            integer di;
            for (di = 16; di < 32; di = di + 1)
                $display("DBG sdr[%0d]: I=%0d Q=%0d", di, sdr_i_buf[di], sdr_q_buf[di]);
            $display("FAIL AD9767 complex SSB image rejection low: mag(+4)=%0.1f mag(-4)=%0.1f", mag_pos, mag_neg);
            $fatal(1, "FAIL AD9767 I/Q complex spectrum");
        end

        $display("PASS tb_dac_tx: chirp_bins=(%0d->%0d) ssb_pos=%0.1f ssb_neg=%0.1f und_pre=%0d crc_err=%0d",
                 bin_1, bin_2, mag_pos, mag_neg, und_before, crc_err_cnt);
        $finish;
    end
endmodule
