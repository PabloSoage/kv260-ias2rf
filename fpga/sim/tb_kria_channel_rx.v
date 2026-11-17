// SPDX-License-Identifier: Apache-2.0
// Unit Testbench for kria_channel_rx (AM, USB, LSB, NBFM + CTCSS Goertzel, WBFM Stereo + Pilot)
`timescale 1ns/1ps

module tb_kria_channel_rx;
    reg clk = 1'b0;
    always #5.0 clk = ~clk;

    reg                rst = 1'b1;
    reg                in_valid = 1'b0;
    reg signed [15:0]  in_i = 16'sd0, in_q = 16'sd0;
    reg [2:0]          cfg_mode = 3'd0;
    reg [31:0]         cfg_nco_ftw = 32'd0;
    reg [15:0]         cfg_cic_decim = 16'd1;
    reg [5:0]          cfg_cic_shift = 6'd0;
    reg [7:0]          cfg_fir_decim = 8'd0;
    reg [15:0]         cfg_deemph_alpha = 16'd4096;
    reg [31:0]         cfg_pilot_ftw = 32'd0;
    reg signed [15:0]  cfg_ctcss_coeff = 16'sd0;
    reg [15:0]         cfg_ctcss_n = 16'd0;
    reg [31:0]         cfg_ctcss_thresh = 32'd0;
    reg [15:0]         cfg_rds_sym_samps = 16'd0;

    wire               audio_valid;
    wire signed [15:0] audio_l, audio_r, audio_mono;
    wire               pilot_locked, ctcss_valid, ctcss_detected, rds_bit_valid, rds_bit;
    wire [31:0]        ctcss_power;

    kria_channel_rx dut (
        .clk               (clk),
        .rst               (rst),
        .in_valid          (in_valid),
        .in_i              (in_i),
        .in_q              (in_q),
        .cfg_mode          (cfg_mode),
        .cfg_nco_ftw       (cfg_nco_ftw),
        .cfg_cic_decim     (cfg_cic_decim),
        .cfg_cic_shift     (cfg_cic_shift),
        .cfg_cic_n5        (1'b0),
        .cfg_fir_decim     (cfg_fir_decim),
        .cfg_deemph_alpha  (cfg_deemph_alpha),
        .cfg_pilot_ftw     (cfg_pilot_ftw),
        .cfg_ctcss_coeff   (cfg_ctcss_coeff),
        .cfg_ctcss_n       (cfg_ctcss_n),
        .cfg_ctcss_thresh  (cfg_ctcss_thresh),
        .cfg_rds_sym_samps (cfg_rds_sym_samps),
        .audio_valid       (audio_valid),
        .audio_l           (audio_l),
        .audio_r           (audio_r),
        .audio_mono        (audio_mono),
        .pilot_locked      (pilot_locked),
        .ctcss_valid       (ctcss_valid),
        .ctcss_detected    (ctcss_detected),
        .ctcss_power       (ctcss_power),
        .rds_bit_valid     (rds_bit_valid),
        .rds_bit           (rds_bit)
    );

    localparam real PI = 3.141592653589793;
    integer s_idx, cnt;
    real    am_rms, usb_rms, lsb_reject_rms, fm_rms, fm_corr;
    integer ctcss_hits, saw_pilot_lock;

    task reset_dut;
        begin
            @(negedge clk);
            rst = 1'b1;
            in_valid = 1'b0;
            repeat (5) @(negedge clk);
            rst = 1'b0;
        end
    endtask

    // Feed N baseband samples at Fs_ch = 48 kHz (every 2 clocks for speed in unit bench)
    task run_am_test;
        real env, mod_s;
        begin
            cfg_mode = 3'd0; cfg_nco_ftw = 32'd0; cfg_cic_decim = 16'd1; cfg_fir_decim = 8'd0;
            reset_dut();
            am_rms = 0.0; cnt = 0;
            for (s_idx = 0; s_idx < 300; s_idx = s_idx + 1) begin
                mod_s = $sin(2.0 * PI * 1000.0 * s_idx / 48000.0);
                env = 12000.0 * (1.0 + 0.6 * mod_s);
                @(negedge clk);
                in_valid = 1'b1;
                in_i = $rtoi(env * $cos(0.35 * s_idx));
                in_q = $rtoi(env * $sin(0.35 * s_idx));
                @(posedge clk); #1;
                if (audio_valid && s_idx > 120) begin
                    am_rms = am_rms + (audio_l * 1.0) * (audio_l * 1.0);
                    cnt = cnt + 1;
                end
            end
            repeat (30) @(posedge clk);
            am_rms = $sqrt(am_rms / (cnt > 0 ? cnt : 1));
            $display("[CH_RX AM] rms=%.1f", am_rms);
            if (am_rms < 2500.0) begin
                $display("FAIL: AM demod RMS too low (%.1f)", am_rms);
                $finish;
            end
        end
    endtask

    task run_ssb_test;
        real w_tone;
        begin
            // Feed positive-frequency USB tone exp(+j * 2*pi*1500/12000 * n) at HF SSB Fs_ch=12 kHz
            w_tone = 2.0 * PI * 1500.0 / 12000.0;
            cfg_nco_ftw = 32'd0; cfg_cic_decim = 16'd1; cfg_fir_decim = 8'd0;

            // Mode 1: USB -> must pass positive frequency strongly
            cfg_mode = 3'd1;
            reset_dut();
            usb_rms = 0.0; cnt = 0;
            for (s_idx = 0; s_idx < 250; s_idx = s_idx + 1) begin
                @(negedge clk);
                in_valid = 1'b1;
                in_i = $rtoi(16000.0 * $cos(w_tone * s_idx));
                in_q = $rtoi(16000.0 * $sin(w_tone * s_idx));
                @(posedge clk); #1;
                if (audio_valid && s_idx > 40) begin
                    usb_rms = usb_rms + (audio_l * 1.0) * (audio_l * 1.0);
                    cnt = cnt + 1;
                end
            end
            usb_rms = $sqrt(usb_rms / (cnt > 0 ? cnt : 1));

            // Mode 2: LSB -> same +1500 Hz USB tone must be rejected (> 25 dB)
            cfg_mode = 3'd2;
            reset_dut();
            lsb_reject_rms = 0.0; cnt = 0;
            for (s_idx = 0; s_idx < 250; s_idx = s_idx + 1) begin
                @(negedge clk);
                in_valid = 1'b1;
                in_i = $rtoi(16000.0 * $cos(w_tone * s_idx));
                in_q = $rtoi(16000.0 * $sin(w_tone * s_idx));
                @(posedge clk); #1;
                if (audio_valid && s_idx > 40) begin
                    lsb_reject_rms = lsb_reject_rms + (audio_l * 1.0) * (audio_l * 1.0);
                    cnt = cnt + 1;
                end
            end
            lsb_reject_rms = $sqrt(lsb_reject_rms / (cnt > 0 ? cnt : 1));
            $display("[CH_RX SSB] usb_rms=%.1f lsb_rej_rms=%.1f ratio=%.1f dB",
                     usb_rms, lsb_reject_rms, 20.0 * $log10((usb_rms + 1.0) / (lsb_reject_rms + 1.0)));
            if (usb_rms < 8000.0 || (usb_rms / (lsb_reject_rms + 1.0)) < 20.0) begin
                $display("FAIL: SSB sideband rejection check failed");
                $finish;
            end
        end
    endtask

    task run_nbfm_ctcss_test;
        real ph, fs_ch, inst_f;
        begin
            // Fs_ch = 16000 Hz, 100 Hz CTCSS + 1000 Hz voice
            // 2*cos(2*pi*100/16000)*16384 = 32743
            fs_ch = 16000.0;
            cfg_mode = 3'd3;
            cfg_nco_ftw = 32'd0; cfg_cic_decim = 16'd1; cfg_fir_decim = 8'd0;
            cfg_deemph_alpha = 16'd24000;
            cfg_ctcss_coeff  = 16'sd32743;
            cfg_ctcss_n      = 16'd320; // 20 ms Goertzel block = 2 full 100 Hz cycles
            cfg_ctcss_thresh = 32'd2000;
            reset_dut();
            ph = 0.0; ctcss_hits = 0; fm_rms = 0.0; cnt = 0;
            for (s_idx = 0; s_idx < 700; s_idx = s_idx + 1) begin
                inst_f = 2500.0 * $sin(2.0 * PI * 1000.0 * s_idx / fs_ch)
                       +  600.0 * $sin(2.0 * PI *  100.0 * s_idx / fs_ch);
                ph = ph + 2.0 * PI * inst_f / fs_ch;
                @(negedge clk);
                in_valid = 1'b1;
                in_i = $rtoi(16000.0 * $cos(ph));
                in_q = $rtoi(16000.0 * $sin(ph));
                @(posedge clk); #1;
                if (ctcss_valid && ctcss_detected) ctcss_hits = ctcss_hits + 1;
                if (audio_valid && s_idx > 100) begin
                    fm_rms = fm_rms + (audio_l * 1.0) * (audio_l * 1.0);
                    cnt = cnt + 1;
                end
            end
            fm_rms = $sqrt(fm_rms / (cnt > 0 ? cnt : 1));
            $display("[CH_RX NBFM+CTCSS] fm_rms=%.1f ctcss_hits=%0d last_pwr=%0d", fm_rms, ctcss_hits, ctcss_power);
            if (fm_rms < 1500.0 || ctcss_hits < 1) begin
                $display("FAIL: NBFM/CTCSS detection failed");
                $finish;
            end
        end
    endtask

    task run_wbfm_stereo_test;
        real ph, fs_ch, mpx, L, R;
        begin
            // Fs_ch = 240 kS/s, 19 kHz pilot coeff = 2*cos(2*pi*19e3/240e3)*16384 = 28836
            fs_ch = 240000.0;
            cfg_mode = 3'd4;
            cfg_nco_ftw = 32'd0; cfg_cic_decim = 16'd1; cfg_fir_decim = 8'd0;
            cfg_deemph_alpha = 16'd20000;
            cfg_pilot_ftw    = 32'd340023730; // 2^32 * 19e3 / 240e3
            cfg_ctcss_coeff  = 16'sd28836;
            cfg_rds_sym_samps= 16'd202;
            reset_dut();
            ph = 0.0; saw_pilot_lock = 0; fm_rms = 0.0; cnt = 0;
            for (s_idx = 0; s_idx < 1200; s_idx = s_idx + 1) begin
                L = 0.8 * $sin(2.0 * PI * 1000.0 * s_idx / fs_ch);
                R = 0.2 * $sin(2.0 * PI * 1000.0 * s_idx / fs_ch);
                mpx = 0.45 * (L + R)
                    + 0.10 * $cos(2.0 * PI * 19000.0 * s_idx / fs_ch)
                    + 0.45 * (L - R) * $cos(2.0 * PI * 38000.0 * s_idx / fs_ch);
                ph = ph + 2.0 * PI * (75000.0 * mpx) / fs_ch;
                @(negedge clk);
                in_valid = 1'b1;
                in_i = $rtoi(16000.0 * $cos(ph));
                in_q = $rtoi(16000.0 * $sin(ph));
                @(posedge clk); #1;
                if (pilot_locked) saw_pilot_lock = 1;
                if (audio_valid && s_idx > 200) begin
                    fm_rms = fm_rms + (audio_mono * 1.0) * (audio_mono * 1.0);
                    cnt = cnt + 1;
                end
            end
            fm_rms = $sqrt(fm_rms / (cnt > 0 ? cnt : 1));
            $display("[CH_RX WBFM] mono_rms=%.1f pilot_locked=%0d", fm_rms, saw_pilot_lock);
            if (fm_rms < 1500.0 || saw_pilot_lock == 0) begin
                $display("FAIL: WBFM stereo/pilot failed");
                $finish;
            end
        end
    endtask

    initial begin
        run_am_test();
        run_ssb_test();
        run_nbfm_ctcss_test();
        run_wbfm_stereo_test();
        $display("PASS: tb_kria_channel_rx (AM + USB/LSB + NBFM/CTCSS + WBFM Pilot)");
        $finish;
    end
endmodule
