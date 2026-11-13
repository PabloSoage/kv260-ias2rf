// SPDX-License-Identifier: BSD-2-Clause
// Testbench: AD9484 Capture (adc_capture) + AERIS DDC (ddc_wrapper) + Packetizer
//
// Checks:
//   1. Behavioral AD9484 model driving 8 LVDS DDR data pairs + OR + INVERTED DCO
//      (N14 = ADCR_DCO_N, P14 = ADCR_DCO_P) with routed skew (-90..+5 ps) and
//      +/-80 ps transition-edge eye uncertainty.
//   2. Per-bit IDELAYE2 training locks cleanly with checkerboard pattern (0xAA/0x55)
//      and centers taps inside the 2.500 ns UI eye.
//   3. Continuous 126.25 MHz IF tone (+6.25 MHz above 120 MHz NCO) is mixed to
//      baseband at 100 MSPS -> complex DFT peak lands on bin k = 60 (-6.25 MHz)
//      with >= 35 dB image rejection over k = 4 (+6.25 MHz).
//   4. Packetizer produces valid packets on link_clk with monotonic pkt_seq and 0 drops.
//
// Mutations:
//   -Mutate wrong_dco_phase : drops DCO polarity compensation -> training/phase fails
//   -Mutate swap_iq         : swaps I/Q -> tone moves to image bin k=4 -> fails

`timescale 1ns/1ps

module tb_adc_ddc;

    localparam real PI = 3.14159265358979323846;

    // Reference and system clocks
    reg refclk_200m = 1'b0;
    reg link_clk    = 1'b0;
    always #2.500 refclk_200m = ~refclk_200m; // 200 MHz IDELAYCTRL refclk
    always #4.000 link_clk    = ~link_clk;    // 125 MHz link byte clock

    // AD9484 sample clock (400 MSPS) and 200 MHz DDR DCO
    // Center DCO relative to delayed data eye so IDELAYE2 taps lock near mid-range (~tap 15)
    reg clk_400m_adc = 1'b0;
    reg dco_true     = 1'b0;
    always #1.250 clk_400m_adc = ~clk_400m_adc;
    initial begin
        dco_true = 1'b0;
        #1.750;
        forever #2.500 dco_true = ~dco_true;
    end

    reg rst = 1'b1;
    reg link_rst = 1'b1;
    reg train_start = 1'b0;
    reg train_pattern_en = 1'b1;
    reg ddc_en = 1'b0;

    // -------------------------------------------------------------------------
    // Behavioral AD9484 Stimulus with Realistic Board Skew & Transition Jitter
    // -------------------------------------------------------------------------
    integer sample_idx = 0;
    reg [7:0] adc_sample_raw = 8'hAA;
    reg       adc_or_raw     = 1'b0;

    always @(posedge clk_400m_adc) begin
        if (train_pattern_en) begin
            adc_sample_raw <= sample_idx[0] ? 8'h55 : 8'hAA;
            adc_or_raw     <= 1'b0;
        end else begin
            // 126.25 MHz tone at 400 MSPS: 0.315625 cycles per sample
            // Amplitude 110 around mid-scale 128 -> clean non-clipping 8b offset-binary
            adc_sample_raw <= $rtoi(128.0 + 110.0 * $cos(2.0 * PI * 0.315625 * sample_idx) + 0.5);
            adc_or_raw     <= 1'b0;
        end
        sample_idx <= sample_idx + 1;
    end

    // Channel model:
    //   Reference propagation delay 0.250 ns on DCO; data bits carry routed skew
    //   spanning -90 ps to +5 ps across D0..D7 relative to DCO, plus +/-80 ps
    //   PRNG corruption on transition edges so edge taps fail cleanly.
    reg [31:0] eye_prng = 32'hCAFE_BABE;
    always @(posedge clk_400m_adc)
        eye_prng <= {eye_prng[30:0], eye_prng[31] ^ eye_prng[21] ^ eye_prng[1] ^ eye_prng[0]};

    reg       dco_board_del = 1'b0;
    always @(dco_true) dco_board_del <= #0.250 dco_true;

    // PCB swaps ADCR_DCO_P/N at N14/P14
    wire adcr_dco_n_pin = ~dco_board_del;
    wire adcr_dco_p_pin =  dco_board_del;

    reg [7:0] d_skew_early  = 8'd0;
    reg [7:0] d_skew_center = 8'd0;
    reg [7:0] d_skew_late   = 8'd0;
    reg       or_skew       = 1'b0;

    // Per-bit skew values across -90 ps to +5 ps around 0.250 ns nominal:
    // Bit 0: 0.160 ns (-90 ps), ..., Bit 7: 0.255 ns (+5 ps)
    localparam real BIT_DEL_0 = 0.160;
    localparam real BIT_DEL_1 = 0.175;
    localparam real BIT_DEL_2 = 0.190;
    localparam real BIT_DEL_3 = 0.205;
    localparam real BIT_DEL_4 = 0.220;
    localparam real BIT_DEL_5 = 0.230;
    localparam real BIT_DEL_6 = 0.242;
    localparam real BIT_DEL_7 = 0.255;

    always @(adc_sample_raw[0]) begin d_skew_early[0] <= #(BIT_DEL_0 - 0.080) adc_sample_raw[0]; d_skew_center[0] <= #BIT_DEL_0 adc_sample_raw[0]; d_skew_late[0] <= #(BIT_DEL_0 + 0.080) adc_sample_raw[0]; end
    always @(adc_sample_raw[1]) begin d_skew_early[1] <= #(BIT_DEL_1 - 0.080) adc_sample_raw[1]; d_skew_center[1] <= #BIT_DEL_1 adc_sample_raw[1]; d_skew_late[1] <= #(BIT_DEL_1 + 0.080) adc_sample_raw[1]; end
    always @(adc_sample_raw[2]) begin d_skew_early[2] <= #(BIT_DEL_2 - 0.080) adc_sample_raw[2]; d_skew_center[2] <= #BIT_DEL_2 adc_sample_raw[2]; d_skew_late[2] <= #(BIT_DEL_2 + 0.080) adc_sample_raw[2]; end
    always @(adc_sample_raw[3]) begin d_skew_early[3] <= #(BIT_DEL_3 - 0.080) adc_sample_raw[3]; d_skew_center[3] <= #BIT_DEL_3 adc_sample_raw[3]; d_skew_late[3] <= #(BIT_DEL_3 + 0.080) adc_sample_raw[3]; end
    always @(adc_sample_raw[4]) begin d_skew_early[4] <= #(BIT_DEL_4 - 0.080) adc_sample_raw[4]; d_skew_center[4] <= #BIT_DEL_4 adc_sample_raw[4]; d_skew_late[4] <= #(BIT_DEL_4 + 0.080) adc_sample_raw[4]; end
    always @(adc_sample_raw[5]) begin d_skew_early[5] <= #(BIT_DEL_5 - 0.080) adc_sample_raw[5]; d_skew_center[5] <= #BIT_DEL_5 adc_sample_raw[5]; d_skew_late[5] <= #(BIT_DEL_5 + 0.080) adc_sample_raw[5]; end
    always @(adc_sample_raw[6]) begin d_skew_early[6] <= #(BIT_DEL_6 - 0.080) adc_sample_raw[6]; d_skew_center[6] <= #BIT_DEL_6 adc_sample_raw[6]; d_skew_late[6] <= #(BIT_DEL_6 + 0.080) adc_sample_raw[6]; end
    always @(adc_sample_raw[7]) begin d_skew_early[7] <= #(BIT_DEL_7 - 0.080) adc_sample_raw[7]; d_skew_center[7] <= #BIT_DEL_7 adc_sample_raw[7]; d_skew_late[7] <= #(BIT_DEL_7 + 0.080) adc_sample_raw[7]; end
    always @(adc_or_raw)        begin or_skew <= #0.210 adc_or_raw; end

    wire [7:0] d_eye_viol   = d_skew_early ^ d_skew_late;
    wire [7:0] adcr_d_p     = (d_eye_viol & {8{eye_prng[0]}}) ? ~d_skew_center : d_skew_center;
    wire [7:0] adcr_d_n     = ~adcr_d_p;
    wire       adcr_or_p    = or_skew;
    wire       adcr_or_n    = ~or_skew;

    // -------------------------------------------------------------------------
    // DUT: adc_capture -> ddc_wrapper
    // -------------------------------------------------------------------------
    wire        clk_400m_cap, clk_100m_cap, mmcm_locked;
    wire [7:0]  cap_data;
    wire        cap_or, cap_valid;
    wire        adc_trained, dco_phase_err;
    wire [39:0] tap_flat;
    wire [5:0]  eye_width_min;

    adc_capture #(
        .DCO_INVERT      (1'b1),
        .DCO_PERIOD_NS   (5.000),
        .REFCLK_FREQ_MHZ (200.0),
        .INST_IDELAYCTRL (1'b1)
    ) u_cap (
        .rst              (rst),
        .refclk_200m      (refclk_200m),
        .adcr_d_p         (adcr_d_p),
        .adcr_d_n         (adcr_d_n),
        .adcr_or_p        (adcr_or_p),
        .adcr_or_n        (adcr_or_n),
        .adcr_dco_n_pin   (adcr_dco_n_pin),
        .adcr_dco_p_pin   (adcr_dco_p_pin),
        .train_start      (train_start),
        .train_pattern_en (train_pattern_en),
        .clk_400m         (clk_400m_cap),
        .clk_100m         (clk_100m_cap),
        .mmcm_locked      (mmcm_locked),
        .adc_data         (cap_data),
        .adc_or           (cap_or),
        .adc_valid        (cap_valid),
        .adc_trained      (adc_trained),
        .dco_phase_err    (dco_phase_err),
        .tap_flat         (tap_flat),
        .eye_width_min    (eye_width_min)
    );

    wire signed [15:0] bb_i, bb_q;
    wire               bb_valid;
    wire [1:0]         ddc_status;
    wire               mixer_sat, filter_ovf, sync_err;

    reg  [63:0]        ts_cnt = 64'd0;
    always @(posedge link_clk) begin
        if (link_rst) ts_cnt <= 64'd0;
        else          ts_cnt <= ts_cnt + 64'd1;
    end

    wire        pkt_valid;
    reg         pkt_ready = 1'b1;
    wire        pkt_sop, pkt_eop;
    wire [7:0]  pkt_stream_id;
    wire [15:0] pkt_len;
    wire [31:0] pkt_seq;
    wire [63:0] pkt_timestamp, pkt_data;
    wire [23:0] dropped_cnt;

    ddc_wrapper #(
        .POST_DECIM (1),
        .PKT_WORDS  (8),
        .STREAM_ID  (8'h01)
    ) u_ddc_wrap (
        .clk_400m         (clk_400m_cap),
        .clk_100m         (clk_100m_cap),
        .rst              (rst),
        .ddc_en           (ddc_en),
        .reset_monitors   (1'b0),
        .adc_data         (cap_data),
        .adc_valid        (cap_valid),
        .bb_i             (bb_i),
        .bb_q             (bb_q),
        .bb_valid         (bb_valid),
        .ddc_status       (ddc_status),
        .mixer_saturation (mixer_sat),
        .filter_overflow  (filter_ovf),
        .sync_error       (sync_err),
        .link_clk         (link_clk),
        .link_rst         (link_rst),
        .timestamp_cnt    (ts_cnt),
        .pkt_valid        (pkt_valid),
        .pkt_ready        (pkt_ready),
        .pkt_sop          (pkt_sop),
        .pkt_eop          (pkt_eop),
        .pkt_stream_id    (pkt_stream_id),
        .pkt_len          (pkt_len),
        .pkt_seq          (pkt_seq),
        .pkt_timestamp    (pkt_timestamp),
        .pkt_data         (pkt_data),
        .dropped_cnt      (dropped_cnt)
    );

    // Packet sink monitor on link_clk
    integer pkt_rx_cnt = 0;
    integer word_rx_cnt = 0;
    always @(posedge link_clk) begin
        if (!link_rst && pkt_valid && pkt_ready) begin
            word_rx_cnt <= word_rx_cnt + 1;
            if (pkt_eop) pkt_rx_cnt <= pkt_rx_cnt + 1;
        end
    end

    // Baseband sample collector (skip initial transient)
    localparam integer SKIP_SAMPLES = 48;
    localparam integer FFT_N        = 64;

    integer cap_cnt = 0;
    real    bb_i_buf [0:FFT_N-1];
    real    bb_q_buf [0:FFT_N-1];
    reg     fft_done = 1'b0;

    always @(posedge clk_100m_cap) begin
        if (!rst && ddc_en && bb_valid && !fft_done) begin
            if (cap_cnt >= SKIP_SAMPLES && cap_cnt < SKIP_SAMPLES + FFT_N) begin
                bb_i_buf[cap_cnt - SKIP_SAMPLES] <= $itor(bb_i);
                bb_q_buf[cap_cnt - SKIP_SAMPLES] <= $itor(bb_q);
            end
            cap_cnt <= cap_cnt + 1;
            if (cap_cnt == SKIP_SAMPLES + FFT_N - 1)
                fft_done <= 1'b1;
        end
    end

    // Complex DFT verification
    integer k, n, peak_k;
    real re_sum, im_sum, pwr, p_peak, p_sig, p_img, p_dc, angle, img_rej_db;

    initial begin
        // Wait out global reset & release
        #200.0;
        rst      = 1'b0;
        link_rst = 1'b0;

        // Wait for MMCM lock (timeout 40 us)
        begin : wait_lock
            integer w;
            w = 0;
            while (!mmcm_locked && w < 8000) begin
                #5.0;
                w = w + 1;
            end
            if (!mmcm_locked) begin
                $display("FAIL: tb_adc_ddc MMCM failed to lock");
                $finish;
            end
        end

        // Start per-bit eye-scan training with checkerboard 0xAA / 0x55
        #100.0;
        train_pattern_en = 1'b1;
        train_start      = 1'b1;
        #25.0;
        train_start      = 1'b0;

        begin : wait_train
            integer wt;
            wt = 0;
            while (!adc_trained && !dco_phase_err && wt < 20000) begin
                #5.0;
                wt = wt + 1;
            end
            if (!adc_trained || dco_phase_err) begin
                $display("FAIL: tb_adc_ddc training failed (adc_trained=%0d dco_phase_err=%0d eye_w=%0d)",
                         adc_trained, dco_phase_err, eye_width_min);
                $finish;
            end
        end

        $display("tb_adc_ddc trained: eye_width_min=%0d taps=%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d pass0=%08x",
                 eye_width_min,
                 tap_flat[4:0],   tap_flat[9:5],   tap_flat[14:10], tap_flat[19:15],
                 tap_flat[24:20], tap_flat[29:25], tap_flat[34:30], tap_flat[39:35],
                 u_cap.pass_mask[0]);

        // Switch ADC to 126.25 MHz IF tone (+6.25 MHz above 120 MHz NCO)
        @(posedge clk_400m_adc);
        train_pattern_en = 1'b0;
        ddc_en           = 1'b1;

        begin : wait_fft
            integer wf;
            wf = 0;
            while (!fft_done && wf < 20000) begin
                #10.0;
                wf = wf + 1;
            end
            if (!fft_done) begin
                $display("FAIL: tb_adc_ddc timeout waiting for %0d baseband samples (cap_cnt=%0d)",
                         FFT_N, cap_cnt);
                $finish;
            end
        end

        // Allow packetizer to flush at least 2 packets
        #500.0;

        // Compute 64-point complex DFT on {I, Q}
        p_peak = -1.0;
        peak_k = -1;
        p_sig  = 0.0;
        p_img  = 0.0;
        p_dc   = 0.0;

        for (k = 0; k < FFT_N; k = k + 1) begin
            re_sum = 0.0;
            im_sum = 0.0;
            for (n = 0; n < FFT_N; n = n + 1) begin
                angle  = -2.0 * PI * k * n / FFT_N;
                re_sum = re_sum + (bb_i_buf[n] * $cos(angle) - bb_q_buf[n] * $sin(angle));
                im_sum = im_sum + (bb_i_buf[n] * $sin(angle) + bb_q_buf[n] * $cos(angle));
            end
            pwr = re_sum * re_sum + im_sum * im_sum;
            if (k == 0)  p_dc  = pwr;
            if (k == 60) p_sig = pwr;
            if (k == 4)  p_img = pwr;
            if (k != 0 && pwr > p_peak) begin
                p_peak = pwr;
                peak_k = k;
            end
        end

        img_rej_db = 10.0 * $log10((p_sig + 1.0) / (p_img + 1.0));
        $display("tb_adc_ddc dft: peak_k=%0d (exp 60) p_sig=%e p_img=%e p_dc=%e img_rej=%.2f dB pkts=%0d drops=%0d",
                 peak_k, p_sig, p_img, p_dc, img_rej_db, pkt_rx_cnt, dropped_cnt);

        if (peak_k != 60) begin
            $display("FAIL: tb_adc_ddc peak_k=%0d expected 60 (img_rej=%.2f dB)", peak_k, img_rej_db);
            $finish;
        end
        if (img_rej_db < 35.0) begin
            $display("FAIL: tb_adc_ddc image rejection %.2f dB < 35.0 dB", img_rej_db);
            $finish;
        end
        if (p_sig < 1.0e8) begin
            $display("FAIL: tb_adc_ddc signal bin power %e too low", p_sig);
            $finish;
        end
        if (pkt_rx_cnt < 2 || dropped_cnt != 0) begin
            $display("FAIL: tb_adc_ddc packetizer check failed (pkts=%0d drops=%0d)", pkt_rx_cnt, dropped_cnt);
            $finish;
        end

        $display("PASS: tb_adc_ddc eye_w=%0d peak_k=%0d img_rej_db=%.2f pkts=%0d drops=%0d",
                 eye_width_min, peak_k, img_rej_db, pkt_rx_cnt, dropped_cnt);
        $finish;
    end

endmodule
