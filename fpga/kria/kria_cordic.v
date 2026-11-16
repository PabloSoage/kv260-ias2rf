// SPDX-License-Identifier: Apache-2.0
// 16-Stage Pipelined Fixed-Point CORDIC (Vectoring + Rotation, 0 DSP48)
//
// Placed in Kria PL (XCK26) because Artix-7 only has 10 free DSP48E1 slices.
// Supports per-sample runtime mode selection:
//   mode == 0 (VECTORING): (in_x, in_y) -> (out_x = K_inv*|I+jQ|, out_angle = atan2(y,x))
//   mode == 1 (ROTATION) : (in_x, in_y, in_angle) -> rotated (out_x, out_y) * 1.0 (gain-compensated)
//
// Angle format: signed 16-bit fractional turns [-pi, +pi) mapped to [-32768, +32767],
// i.e., 16'h4000 = +pi/2, 16'hC000 = -pi/2, 16'h8000 = -pi.
// Output magnitude / rotated coordinates are compensated by 1/K_16 = 0.607252935 (19898 / 32768)
// at the input pre-scaling stage so zero DSP multipliers are needed at output (or optional exact).
// Wait: pre-scaling by 19898/32768 uses shift-add:
//   0.607252935 ~ 1/2 + 1/16 + 1/32 + 1/64 - 1/512 - 1/2048 = 0.6069336 (0.05% error)
//   + 1/4096 + 1/16384 = 0.6072388 (0.0023% = -92 dB accuracy, 0 DSPs!).

`timescale 1ns/1ps

module kria_cordic #(
    parameter integer IN_W = 16,
    parameter integer FRAC = 8      // fractional guard bits (G-8): small vectors keep their precision
) (
    input  wire                   clk,
    input  wire                   rst,
    input  wire                   in_valid,
    input  wire                   in_mode,   // 0 = vectoring (mag, atan2), 1 = rotation
    input  wire signed [IN_W-1:0] in_x,
    input  wire signed [IN_W-1:0] in_y,
    input  wire signed [15:0]     in_angle,

    output reg                    out_valid,
    output reg  signed [IN_W-1:0] out_x,     // Vectoring: unsigned/positive magnitude; Rotation: rotated X
    output reg  signed [IN_W-1:0] out_y,     // Vectoring: ~0 residual; Rotation: rotated Y
    output reg  signed [15:0]     out_angle  // Vectoring: atan2(in_y, in_x); Rotation: ~0 residual
);
    localparam integer STAGES = 16;
    // 4 guard bits against intermediate CORDIC growth (1.647x) and FRAC fractional bits: without them the 1/K
    // pre-scale and the x >> i steps dropped the low bits of a small vector (a weak AM carrier lost 5 dB of SINAD)
    localparam integer W      = IN_W + 4 + FRAC;

    // Pre-scale input by 1/K_16 = 0.6072388 using shift-adds (-92 dB vs exact 0.6072529)
    function automatic signed [W-1:0] inv_k_scale;
        input signed [IN_W-1:0] v;
        reg signed [W+15:0] ext;
        reg signed [W+15:0] acc;
        begin
            ext = {{(W+16-IN_W){v[IN_W-1]}}, v} <<< (14 + FRAC); // v * 16384, FRAC fractional bits
            // 0.60723877 * 16384 = 9949 = 8192 + 1024 + 512 + 256 - 32 - 8 + 4 + 1
            acc = (ext >>> 1) + (ext >>> 4) + (ext >>> 5) + (ext >>> 6)
                - (ext >>> 9) - (ext >>> 11) + (ext >>> 12) + (ext >>> 14);
            inv_k_scale = acc >>> 14;
        end
    endfunction

    // atan(2^-i) in signed 16-bit turns (pi = 32768 -> rad * 32768 / pi)
    function automatic signed [15:0] atan_lut;
        input integer idx;
        begin
            case (idx)
                0:  atan_lut = 16'sd8192; // 45.000 deg
`ifdef MUTATE_WRONG_ATAN_LUT
                1:  atan_lut = 16'sd1200; // MUTATION: corrupted 26.565 deg stage
`else
                1:  atan_lut = 16'sd4836; // 26.565 deg
`endif
                2:  atan_lut = 16'sd2555; // 14.036 deg
                3:  atan_lut = 16'sd1297; // 7.125 deg
                4:  atan_lut = 16'sd651;  // 3.576 deg
                5:  atan_lut = 16'sd326;  // 1.790 deg
                6:  atan_lut = 16'sd163;  // 0.895 deg
                7:  atan_lut = 16'sd81;   // 0.448 deg
                8:  atan_lut = 16'sd41;   // 0.224 deg
                9:  atan_lut = 16'sd20;   // 0.112 deg
                10: atan_lut = 16'sd10;   // 0.056 deg
                11: atan_lut = 16'sd5;    // 0.028 deg
                12: atan_lut = 16'sd3;    // 0.014 deg
                13: atan_lut = 16'sd1;    // 0.007 deg
                default: atan_lut = 16'sd0;
            endcase
        end
    endfunction

    // Stage 0: Quadrant pre-mapping into [-pi/2, +pi/2] (x >= 0)
    reg signed [W-1:0]  x_p [0:STAGES];
    reg signed [W-1:0]  y_p [0:STAGES];
    reg signed [16:0]   z_p [0:STAGES]; // Extra MSB prevents angle wrap ambiguity during +/-pi
    reg                 v_p [0:STAGES];
    reg                 m_p [0:STAGES];

    wire signed [W-1:0] xs_w = inv_k_scale(in_x);
    wire signed [W-1:0] ys_w = inv_k_scale(in_y);

    always @(posedge clk) begin
        if (rst) begin
            v_p[0] <= 1'b0;
            m_p[0] <= 1'b0;
            x_p[0] <= {W{1'b0}};
            y_p[0] <= {W{1'b0}};
            z_p[0] <= 17'sd0;
        end else begin
            v_p[0] <= in_valid;
            m_p[0] <= in_mode;
            if (!in_mode) begin
                // Vectoring: map in_x < 0 into half-plane x >= 0 by 180 deg reflection
                if (xs_w < 0) begin
                    x_p[0] <= -xs_w;
                    y_p[0] <= -ys_w;
                    z_p[0] <= (ys_w >= 0) ? 17'sd32768 : -17'sd32768;
                end else begin
                    x_p[0] <= xs_w;
                    y_p[0] <= ys_w;
                    z_p[0] <= 17'sd0;
                end
            end else begin
                // Rotation: bring angle into [-pi/2, +pi/2] via +/-pi/2 pre-rotation
                if (in_angle > 16'sd16384) begin
                    // > +90 deg: rotate by +90 first -> (-y, x), remaining = angle - 90
                    x_p[0] <= -ys_w;
                    y_p[0] <=  xs_w;
                    z_p[0] <= $signed({in_angle[15], in_angle}) - 17'sd16384;
                end else if (in_angle < -16'sd16384) begin
                    // < -90 deg: rotate by -90 first -> (y, -x), remaining = angle + 90
                    x_p[0] <=  ys_w;
                    y_p[0] <= -xs_w;
                    z_p[0] <= $signed({in_angle[15], in_angle}) + 17'sd16384;
                end else begin
                    x_p[0] <= xs_w;
                    y_p[0] <= ys_w;
                    z_p[0] <= $signed({in_angle[15], in_angle});
                end
            end
        end
    end

    // Stages 1 .. STAGES: micro-rotations
    genvar s;
    generate
        for (s = 0; s < STAGES; s = s + 1) begin : gen_stage
            wire signed [16:0] a_step = $signed({{1{1'b0}}, atan_lut(s)});
            wire rot_ccw = m_p[s] ? (z_p[s] >= 0) : (y_p[s] < 0);

            always @(posedge clk) begin
                if (rst) begin
                    v_p[s+1] <= 1'b0;
                    m_p[s+1] <= 1'b0;
                    x_p[s+1] <= {W{1'b0}};
                    y_p[s+1] <= {W{1'b0}};
                    z_p[s+1] <= 17'sd0;
                end else begin
                    v_p[s+1] <= v_p[s];
                    m_p[s+1] <= m_p[s];
                    if (rot_ccw) begin
                        x_p[s+1] <= x_p[s] - (y_p[s] >>> s);
                        y_p[s+1] <= y_p[s] + (x_p[s] >>> s);
                        z_p[s+1] <= z_p[s] - a_step;
                    end else begin
                        x_p[s+1] <= x_p[s] + (y_p[s] >>> s);
                        y_p[s+1] <= y_p[s] - (x_p[s] >>> s);
                        z_p[s+1] <= z_p[s] + a_step;
                    end
                end
            end
        end
    endgenerate

    // Saturation helper for 16-bit output
    function automatic signed [IN_W-1:0] sat_out;
        input signed [W-1:0] vf;
        localparam signed [W-1:0] MAXV = (1 << (IN_W - 1)) - 1;
        localparam signed [W-1:0] MINV = -(1 << (IN_W - 1));
        reg signed [W-1:0] v;
        begin
            v = (vf + (1 <<< (FRAC - 1))) >>> FRAC;       // round off the fractional bits
            if (v > MAXV)      sat_out = MAXV[IN_W-1:0];
            else if (v < MINV) sat_out = MINV[IN_W-1:0];
            else               sat_out = v[IN_W-1:0];
        end
    endfunction

    always @(posedge clk) begin
        if (rst) begin
            out_valid <= 1'b0;
            out_x     <= {IN_W{1'b0}};
            out_y     <= {IN_W{1'b0}};
            out_angle <= 16'sd0;
        end else begin
            out_valid <= v_p[STAGES];
            out_x     <= sat_out(x_p[STAGES]);
            out_y     <= sat_out(y_p[STAGES]);
            out_angle <= z_p[STAGES][15:0];
        end
    end
endmodule
