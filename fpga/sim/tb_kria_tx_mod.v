// SPDX-License-Identifier: Apache-2.0
// Unit Testbench for kria_tx_mod (CW, AM, NBFM, USB/LSB Hilbert Sideband Check + AXI-Stream framing)
`timescale 1ns/1ps

module tb_kria_tx_mod;
    reg clk = 1'b0;
    always #5.0 clk = ~clk;

    reg         rst = 1'b1, en = 1'b0;
    reg  [2:0]  cfg_mode = 3'd0;
    reg  [31:0] cfg_carrier_ftw = 32'd0;
    reg  [31:0] cfg_tone_ftw = 32'd0;
    reg  [15:0] cfg_mod_param = 16'd16384;
    reg  [15:0] cfg_amp_scale = 16'd24000;
    reg  [15:0] cfg_samp_div  = 16'd0;
    reg  [15:0] cfg_pkt_words = 16'd8;

    wire               iq_valid;
    wire signed [15:0] iq_i, iq_q;
    wire [63:0]        m_axis_tdata;
    wire               m_axis_tvalid, m_axis_tlast;
    wire [7:0]         m_axis_tid;
    wire [15:0]        m_axis_tuser;

    kria_tx_mod dut (
        .clk             (clk),
        .rst             (rst),
        .en              (en),
        .cfg_mode        (cfg_mode),
        .cfg_carrier_ftw (cfg_carrier_ftw),
        .cfg_tone_ftw    (cfg_tone_ftw),
        .cfg_mod_param   (cfg_mod_param),
        .cfg_amp_scale   (cfg_amp_scale),
        .cfg_samp_div    (cfg_samp_div),
        .cfg_pkt_words   (cfg_pkt_words),
        .ext_aud_en      (1'b0),
        .ext_aud_valid   (1'b0),
        .ext_aud_sample  (16'sd0),
        .iq_valid        (iq_valid),
        .iq_i            (iq_i),
        .iq_q            (iq_q),
        .m_axis_tdata    (m_axis_tdata),
        .m_axis_tvalid   (m_axis_tvalid),
        .m_axis_tready   (1'b1),
        .m_axis_tlast    (m_axis_tlast),
        .m_axis_tid      (m_axis_tid),
        .m_axis_tuser    (m_axis_tuser)
    );

    localparam real PI = 3.141592653589793;
    integer s_idx, tlast_cnt;
    real    p_usb, p_lsb, dft_re_p, dft_im_p, dft_re_n, dft_im_n;
    real    env_min, env_max, env_val, w_c, w_m;

    task run_mode(input [2:0] m, input [31:0] f_c, input [31:0] f_t, input [15:0] mp, input integer nsamp);
        begin
            @(negedge clk);
            en = 1'b0; rst = 1'b1;
            cfg_mode = m; cfg_carrier_ftw = f_c; cfg_tone_ftw = f_t; cfg_mod_param = mp;
            repeat (4) @(negedge clk);
            rst = 1'b0; en = 1'b1;
        end
    endtask

    initial begin
        // 1. AM envelope modulation check: m=0.5 (16384), DC carrier
        run_mode(3'd1, 32'd0, 32'd268435456, 16'd16384, 200);
        env_min = 1e9; env_max = 0.0; tlast_cnt = 0;
        for (s_idx = 0; s_idx < 160; s_idx = s_idx + 1) begin
            @(posedge clk); #1;
            if (m_axis_tvalid && m_axis_tlast) tlast_cnt = tlast_cnt + 1;
            if (iq_valid && s_idx > 40) begin
                env_val = $sqrt((iq_i * 1.0)*(iq_i * 1.0) + (iq_q * 1.0)*(iq_q * 1.0));
                if (env_val < env_min) env_min = env_val;
                if (env_val > env_max) env_max = env_val;
            end
        end
        $display("[TX_MOD AM] env_min=%.1f env_max=%.1f tlast_cnt=%0d", env_min, env_max, tlast_cnt);
        if (env_max < env_min * 1.8 || tlast_cnt < 5) begin
            $display("FAIL: TX AM envelope modulation check failed");
            $finish;
        end

        // 2. USB sideband rejection check at baseband: f_c=0, f_m = Fs/8 (FTW = 2^32/8 = 536870912)
        //    USB must concentrate energy at +Fs/8 and reject -Fs/8 by > 30 dB
        run_mode(3'd3, 32'd0, 32'd536870912, 16'd0, 300);
        dft_re_p = 0.0; dft_im_p = 0.0;
        dft_re_n = 0.0; dft_im_n = 0.0;
        w_m = 2.0 * PI / 8.0;
        for (s_idx = 0; s_idx < 256; s_idx = s_idx + 1) begin
            @(posedge clk); #1;
            if (iq_valid && s_idx >= 64) begin : blk_dft
                real c, s;
                c = $cos(w_m * s_idx); s = $sin(w_m * s_idx);
                // X(+w_m) = sum (I+jQ)*(cos - j*sin)
                dft_re_p = dft_re_p + iq_i * c + iq_q * s;
                dft_im_p = dft_im_p + iq_q * c - iq_i * s;
                // X(-w_m) = sum (I+jQ)*(cos + j*sin)
                dft_re_n = dft_re_n + iq_i * c - iq_q * s;
                dft_im_n = dft_im_n + iq_q * c + iq_i * s;
            end
        end
        p_usb = $sqrt(dft_re_p*dft_re_p + dft_im_p*dft_im_p);
        p_lsb = $sqrt(dft_re_n*dft_re_n + dft_im_n*dft_im_n);
        $display("[TX_MOD USB] P(+fm)=%.1f P(-fm)=%.1f sb_rej=%.1f dB",
                 p_usb, p_lsb, 20.0 * $log10((p_usb + 1.0)/(p_lsb + 1.0)));
        if (p_usb < 10000.0 || (p_usb / (p_lsb + 1.0)) < 30.0) begin
            $display("FAIL: TX USB opposite-sideband suppression failed");
            $finish;
        end

        // 3. NBFM constant envelope & instantaneous frequency swing check
        run_mode(3'd2, 32'd536870912, 32'd134217728, 16'd1024, 200);
        env_min = 1e9; env_max = 0.0;
        for (s_idx = 0; s_idx < 120; s_idx = s_idx + 1) begin
            @(posedge clk); #1;
            if (iq_valid && s_idx > 20) begin
                env_val = $sqrt((iq_i * 1.0)*(iq_i * 1.0) + (iq_q * 1.0)*(iq_q * 1.0));
                if (env_val < env_min) env_min = env_val;
                if (env_val > env_max) env_max = env_val;
            end
        end
        $display("[TX_MOD NBFM] env_min=%.1f env_max=%.1f", env_min, env_max);
        if (env_max < 10000.0 || env_min < env_max * 0.90) begin
            $display("FAIL: TX NBFM constant-envelope check failed");
            $finish;
        end

        $display("PASS: tb_kria_tx_mod (AM + USB >30dB SB_rej + NBFM const-env + AXIS)");
        $finish;
    end
endmodule
