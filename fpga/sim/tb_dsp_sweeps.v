// SPDX-License-Identifier: Apache-2.0
// Fast Kria PL DSP RTL Sweep Bench (drives kria_channel_rx, kria_adsb_rx, kria_tx_mod, kria_radar_proc
// directly from file-backed realistic waveforms for multi-level SINAD, RDS GER, Pd curves).
`timescale 1ns/1ps

module tb_dsp_sweeps;
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
    reg [15:0]         cfg_deemph_alpha = 16'd16384;
    reg [31:0]         cfg_pilot_ftw = 32'd0;
    reg signed [15:0]  cfg_ctcss_coeff = 16'sd0;
    reg [15:0]         cfg_ctcss_n = 16'd0;
    reg [31:0]         cfg_ctcss_thresh = 32'd0;
    reg [15:0]         cfg_rds_sym_samps = 16'd0;

    wire               audio_valid, pilot_locked, ctcss_valid, ctcss_detected, rds_bit_valid, rds_bit;
    wire signed [15:0] audio_l, audio_r, audio_mono;
    wire [31:0]        ctcss_power;

    kria_channel_rx u_ch (
        .clk(clk), .rst(rst), .in_valid(in_valid), .in_i(in_i), .in_q(in_q),
        .cfg_mode(cfg_mode), .cfg_nco_ftw(cfg_nco_ftw),
        .cfg_cic_decim(cfg_cic_decim), .cfg_cic_shift(cfg_cic_shift), .cfg_fir_decim(cfg_fir_decim),
        .cfg_deemph_alpha(cfg_deemph_alpha), .cfg_pilot_ftw(cfg_pilot_ftw),
        .cfg_ctcss_coeff(cfg_ctcss_coeff), .cfg_ctcss_n(cfg_ctcss_n),
        .cfg_ctcss_thresh(cfg_ctcss_thresh), .cfg_rds_sym_samps(cfg_rds_sym_samps),
        .audio_valid(audio_valid), .audio_l(audio_l), .audio_r(audio_r), .audio_mono(audio_mono),
        .pilot_locked(pilot_locked), .ctcss_valid(ctcss_valid), .ctcss_detected(ctcss_detected),
        .ctcss_power(ctcss_power), .rds_bit_valid(rds_bit_valid), .rds_bit(rds_bit)
    );

    reg [7:0]  adsb_osr = 8'd2;
    reg [15:0] adsb_thr = 16'd2000;
    wire       adsb_msg_valid, adsb_crc_ok;
    wire [111:0] adsb_msg_data;
    wire [15:0]  adsb_snr;
    wire [31:0]  adsb_pre, adsb_ok, adsb_err;

    kria_adsb_rx u_adsb (
        .clk(clk), .rst(rst), .in_valid(in_valid), .in_i(in_i), .in_q(in_q),
        .cfg_chip_osr(adsb_osr), .cfg_min_hi_sum(adsb_thr),
        .msg_valid(adsb_msg_valid), .msg_crc_ok(adsb_crc_ok),
        .msg_data(adsb_msg_data), .msg_snr_est(adsb_snr),
        .preamble_cnt(adsb_pre), .crc_ok_cnt(adsb_ok), .crc_err_cnt(adsb_err)
    );

    reg        rad_win_en = 1'b1;
    reg [15:0] rad_alpha  = 16'd1536;
    reg [31:0] rad_minpwr = 32'd20000;
    wire       rad_in_ready, rad_out_valid, rad_out_det, rad_cpi_done;
    wire [5:0] rad_rbin, rad_pk_r;
    wire [3:0] rad_dbin, rad_pk_d;
    wire [31:0] rad_pwr, rad_pk_p;
    wire [15:0] rad_det_cnt;
    reg        rad_mode = 1'b0;

    kria_radar_proc #(.RANGE_N(64), .DOPPLER_M(16)) u_rad (
        .clk(clk), .rst(rst || !rad_mode),
        .in_valid(rad_mode && in_valid), .in_ready(rad_in_ready),
        .in_i(in_i), .in_q(in_q), .cpi_sync_start(1'b0),
        .cfg_win_en(rad_win_en), .cfg_cfar_alpha_q8(rad_alpha), .cfg_cfar_min_pwr(rad_minpwr),
        .rd_out_valid(rad_out_valid), .rd_out_rbin(rad_rbin), .rd_out_dbin(rad_dbin),
        .rd_out_pwr(rad_pwr), .rd_out_det(rad_out_det),
        .cpi_done_pulse(rad_cpi_done), .cpi_det_cnt(rad_det_cnt),
        .peak_rbin(rad_pk_r), .peak_dbin(rad_pk_d), .peak_pwr(rad_pk_p)
    );

    reg [2047:0] mode_str, in_path, out_path;
    integer      fd_in, fd_out, rc, s_i, s_q;
    reg [31:0]   tmpv;
    integer      dbg = 0, dbg_cnt = 0, dbg_cor_cnt = 0;
    reg          dbg_pmsb = 1'b0;

    always @(posedge clk) begin
        if (!rst && fd_out != 0) begin
            if (mode_str == "CH") begin
                if (u_ch.cor_valid) dbg_cor_cnt = dbg_cor_cnt + 1;
                if (dbg && u_ch.cor_valid && dbg_cnt < 15) begin
                    $display("DBG[%0d] mode=%0d cic=(%0d,%0d) ch=(%0d,%0d) mag=%0d dphi=%0d bp=%0d plk=%0d acc_e=%0d",
                             dbg_cnt, cfg_mode, u_ch.cic_out_i, u_ch.cic_out_q, u_ch.ch_i, u_ch.ch_q,
                             u_ch.cor_mag, u_ch.dphi_s, u_ch.pilot_bp_y1>>>8, u_ch.pilot_locked, u_ch.pilot_acc_err);
                    dbg_cnt = dbg_cnt + 1;
                end
                if (dbg && u_ch.cor_valid && (dbg_cor_cnt == 390)) begin
                    $display("TERMS: p=%08x ftw=%08x ep=%08x acc=%08x sum=%08x",
                             u_ch.pilot_phase, u_ch.cfg_pilot_ftw,
                             (u_ch.blk_demod.err_ph * 32'sd4096), (u_ch.pilot_acc_err >>> 1),
                             (u_ch.pilot_phase + u_ch.cfg_pilot_ftw + (u_ch.blk_demod.err_ph * 32'sd4096) + (u_ch.pilot_acc_err >>> 1)));
                end
                if (dbg && u_ch.cor_valid && (dbg_cor_cnt >= 390 && dbg_cor_cnt <= 394)) begin
                    $display("TRACE[%0d] bp=%0d ps=%0d pc=%0d err=%0d pphase=%08x acc=%0d",
                             dbg_cor_cnt, $signed(u_ch.pilot_bp_y1 >>> 8),
                             $signed(u_ch.lut_sin(u_ch.pilot_phase)), $signed(u_ch.lut_cos(u_ch.pilot_phase)),
                             $signed(($signed(u_ch.pilot_bp_y1[23:8]) * $signed(-u_ch.lut_sin(u_ch.pilot_phase))) >>> 15),
                             u_ch.pilot_phase, u_ch.pilot_acc_err);
                end
                if (dbg && u_ch.rds_bit_valid && dbg_cnt < 35) begin
                    $display("DBG_RDS[%0d] bit=%0d plk=%0d pphase=%08x acc=%0d rds_i=%0d cnt=%0d",
                             dbg_cnt, u_ch.rds_bit, u_ch.pilot_locked, u_ch.pilot_phase,
                             u_ch.pilot_acc_err, u_ch.rds_int, dbg_cor_cnt);
                    dbg_cnt = dbg_cnt + 1;
                end
                if (audio_valid)
                    $fwrite(fd_out, "%d %d %d %0d %0d\n", audio_l, audio_r, audio_mono, pilot_locked, ctcss_detected);
                if (rds_bit_valid)
                    $fwrite(fd_out, "RDS %0d\n", rds_bit);
            end else if (mode_str == "ADSB") begin
                if (adsb_msg_valid)
                    $fwrite(fd_out, "%0d %028h %0d\n", adsb_crc_ok, adsb_msg_data, adsb_snr);
            end else if (mode_str == "RADAR") begin
                if (rad_out_valid)
                    $fwrite(fd_out, "%0d %0d %0d %0d\n", rad_rbin, rad_dbin, rad_pwr, rad_out_det);
            end
        end
    end

    initial begin
        if (!$value$plusargs("SWEEP_MODE=%s", mode_str)) mode_str = "CH";
        if (!$value$plusargs("IN_FILE=%s", in_path))     in_path  = "in.txt";
        if (!$value$plusargs("OUT_FILE=%s", out_path))   out_path = "out.txt";
        if (!$value$plusargs("DBG=%d", dbg))             dbg = 0;

        if ($value$plusargs("CH_MODE=%d", tmpv))   cfg_mode = tmpv[2:0];
        if ($value$plusargs("CH_NCO=%h", tmpv))    cfg_nco_ftw = tmpv;
        if ($value$plusargs("CH_DECIM=%h", tmpv)) begin
            cfg_cic_decim = tmpv[15:0];
            cfg_cic_shift = tmpv[21:16];
            cfg_fir_decim = tmpv[31:24];
        end
        if ($value$plusargs("CH_DEMOD=%h", tmpv)) begin
            cfg_deemph_alpha = tmpv[15:0];
            cfg_ctcss_coeff  = tmpv[31:16];
        end
        if ($value$plusargs("CH_PILOT=%h", tmpv))  cfg_pilot_ftw = tmpv;
        if ($value$plusargs("CH_CTCSS=%h", tmpv)) begin
            cfg_ctcss_n       = tmpv[15:0];
            cfg_rds_sym_samps = tmpv[31:16];
        end
        if ($value$plusargs("CH_THR=%d", tmpv))    cfg_ctcss_thresh = tmpv;
        if ($value$plusargs("ADSB_OSR=%d", tmpv))  adsb_osr = tmpv[7:0];
        if ($value$plusargs("ADSB_THR=%d", tmpv))  adsb_thr = tmpv[15:0];
        if ($value$plusargs("RAD_ALPHA=%d", tmpv)) rad_alpha = tmpv[15:0];
        if ($value$plusargs("RAD_MIN=%d", tmpv))   rad_minpwr = tmpv;

        rad_mode = (mode_str == "RADAR");

        fd_in  = $fopen(in_path, "r");
        fd_out = $fopen(out_path, "w");
        if (fd_in == 0 || fd_out == 0) begin
            $display("FAIL: cannot open sweep IO files %0s -> %0s", in_path, out_path);
            $finish;
        end

        repeat (5) @(negedge clk);
        rst = 1'b0;

        while ($fscanf(fd_in, "%d %d\n", s_i, s_q) == 2) begin
            if (rad_mode) while (!rad_in_ready) @(posedge clk);
            @(negedge clk);
            in_valid = 1'b1;
            in_i     = s_i[15:0];
            in_q     = s_q[15:0];
            @(posedge clk);
            if (rad_mode) begin
                @(negedge clk);
                in_valid = 1'b0;
            end
        end
        @(negedge clk);
        in_valid = 1'b0;

        if (rad_mode) begin
            while (!rad_cpi_done) @(posedge clk);
        end
        repeat (40) @(posedge clk);

        $fclose(fd_in);
        $fclose(fd_out);
        $display("PASS: tb_dsp_sweeps (%0s)", mode_str);
        $finish;
    end
endmodule
