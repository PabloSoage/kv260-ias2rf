// SPDX-License-Identifier: BSD-2-Clause
// Behavioral AD9708 Radar DAC & AD9767 Dual 14-bit SDR DAC Monitors
//
// Checks:
//   - sim_dac_radar_mon: AD9708 setup (>=2.0 ns) & hold (>=1.5 ns) timing,
//     captures active LFM chirp samples, verifies positive chirp slope (f_hi > f_lo)
//     by zero-crossing rate in first vs second pulse halves.
//   - sim_dac_sdr_mon: AD9767 IQWRT/IQCLK/IQSEL capture of interleaved 14-bit I/Q
//     samples and quadrature activity check.

`timescale 1ps/10fs

module sim_dac_radar_mon (
    input  wire        dacr_clk,
    input  wire [7:0]  dacr_d,
    output integer     clk_edges,
    output integer     timing_errs,
    output integer     active_samples,
    output integer     zc_first_half,
    output integer     zc_second_half,
    output reg signed [7:0] max_amp
);
    real d_t = -100000.0;
    real c_t = -100000.0;

    reg signed [7:0] s_cur;
    reg signed [7:0] s_prev = 8'sd0;
    integer          pulse_idx = 0;

    initial begin
        clk_edges      = 0;
        timing_errs    = 0;
        active_samples = 0;
        zc_first_half  = 0;
        zc_second_half = 0;
        max_amp        = 8'sd0;
    end

    always @(dacr_d) begin
        d_t = $realtime;
        if (clk_edges > 2 && c_t > 0.0 && ($realtime - c_t) < 1500.0)
            timing_errs = timing_errs + 1;
    end

    always @(posedge dacr_clk) begin
        clk_edges = clk_edges + 1;
        if (clk_edges > 2 && ($realtime - d_t) < 2000.0)
            timing_errs = timing_errs + 1;
        c_t = $realtime;

        s_cur = $signed(dacr_d) - 8'sd128;
        if (s_cur > max_amp)  max_amp = s_cur;
        if (-s_cur > max_amp) max_amp = -s_cur;

        if (s_cur != 8'sd0 || active_samples > 0) begin
            if (active_samples < 512) begin
                active_samples = active_samples + 1;
                if (active_samples > 4 && ((s_prev < 0 && s_cur >= 0) || (s_prev >= 0 && s_cur < 0))) begin
                    if (active_samples <= 256)
                        zc_first_half = zc_first_half + 1;
                    else
                        zc_second_half = zc_second_half + 1;
                end
                s_prev = s_cur;
            end
        end
    end
endmodule

module sim_dac_sdr_mon (
    input  wire        dacs_iqclk,
    input  wire        dacs_iqwrt,
    input  wire        dacs_iqsel,
    input  wire [13:0] dacs_d,
    output integer     clk_edges,
    output integer     wrt_edges,
    output integer     i_samples,
    output integer     q_samples,
    output reg signed [13:0] last_i,
    output reg signed [13:0] last_q
);
    initial begin
        clk_edges = 0;
        wrt_edges = 0;
        i_samples = 0;
        q_samples = 0;
        last_i    = 14'sd0;
        last_q    = 14'sd0;
    end

    always @(posedge dacs_iqclk) clk_edges = clk_edges + 1;

    always @(posedge dacs_iqwrt) begin
        wrt_edges = wrt_edges + 1;
        if (dacs_iqsel) begin
            last_i    <= $signed(dacs_d);
            i_samples <= i_samples + 1;
        end else begin
            last_q    <= $signed(dacs_d);
            q_samples <= q_samples + 1;
        end
    end
endmodule
