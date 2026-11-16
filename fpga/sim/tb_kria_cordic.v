// SPDX-License-Identifier: Apache-2.0
// Unit Testbench for kria_cordic (Vectoring Magnitude/Atan2 + Rotation across all 4 quadrants)
`timescale 1ns/1ps

module tb_kria_cordic;
    reg clk = 1'b0;
    always #5.0 clk = ~clk;

    reg                rst = 1'b1;
    reg                in_valid = 1'b0;
    reg                in_mode  = 1'b0;
    reg signed [15:0]  in_x = 16'sd0;
    reg signed [15:0]  in_y = 16'sd0;
    reg signed [15:0]  in_angle = 16'sd0;

    wire               out_valid;
    wire signed [15:0] out_x, out_y, out_angle;

    kria_cordic #(.IN_W(16)) dut (
        .clk       (clk),
        .rst       (rst),
        .in_valid  (in_valid),
        .in_mode   (in_mode),
        .in_x      (in_x),
        .in_y      (in_y),
        .in_angle  (in_angle),
        .out_valid (out_valid),
        .out_x     (out_x),
        .out_y     (out_y),
        .out_angle (out_angle)
    );

    integer vec_cnt = 0;
    integer err_cnt = 0;
    real    max_mag_err = 0.0;
    real    max_ang_err = 0.0;

    // Store expected values queued 17 cycles deep
    localparam integer LAT = 17;
    reg        exp_mode [0:31];
    real       exp_mag  [0:31];
    real       exp_ang  [0:31];
    real       exp_rx   [0:31];
    real       exp_ry   [0:31];
    integer    wr_idx = 0;
    integer    rd_idx = 0;

    task push_vec(input m, input integer ix, input integer iy, input integer iang);
        real rx, ry, ang_rad, em, ea;
        begin
            @(negedge clk);
            in_valid = 1'b1;
            in_mode  = m;
            in_x     = ix[15:0];
            in_y     = iy[15:0];
            in_angle = iang[15:0];
            exp_mode[wr_idx % 32] = m;
            rx = ix * 1.0;
            ry = iy * 1.0;
            if (!m) begin
                em = $sqrt(rx*rx + ry*ry);
                if (em > 32767.0) em = 32767.0;
                ea = $atan2(ry, rx) * 32768.0 / 3.141592653589793;
                exp_mag[wr_idx % 32] = em;
                exp_ang[wr_idx % 32] = ea;
            end else begin
                ang_rad = iang * 3.141592653589793 / 32768.0;
                exp_rx[wr_idx % 32] = rx * $cos(ang_rad) - ry * $sin(ang_rad);
                exp_ry[wr_idx % 32] = rx * $sin(ang_rad) + ry * $cos(ang_rad);
            end
            wr_idx = wr_idx + 1;
        end
    endtask

    always @(posedge clk) begin
        if (!rst && out_valid) begin
            if (!exp_mode[rd_idx % 32]) begin : blk_vec
                real dm, da, got_m, got_a;
                got_m = out_x * 1.0;
                got_a = out_angle * 1.0;
                dm = got_m - exp_mag[rd_idx % 32];
                if (dm < 0) dm = -dm;
                da = got_a - exp_ang[rd_idx % 32];
                while (da > 32768.0)  da = da - 65536.0;
                while (da < -32768.0) da = da + 65536.0;
                if (da < 0) da = -da;
                if (dm > max_mag_err) max_mag_err = dm;
                if (da > max_ang_err) max_ang_err = da;
                if (dm > 20.0 || da > 20.0) begin
                    $display("ERR VEC idx=%0d got=(%0d,%0d) exp=(%.1f,%.1f) dm=%.1f da=%.1f",
                             rd_idx, out_x, out_angle, exp_mag[rd_idx % 32], exp_ang[rd_idx % 32], dm, da);
                    err_cnt = err_cnt + 1;
                end
            end else begin : blk_rot
                real dx, dy;
                dx = (out_x * 1.0) - exp_rx[rd_idx % 32];
                dy = (out_y * 1.0) - exp_ry[rd_idx % 32];
                if (dx < 0) dx = -dx;
                if (dy < 0) dy = -dy;
                if (dx > 20.0 || dy > 20.0) begin
                    $display("ERR ROT idx=%0d got=(%0d,%0d) exp=(%.1f,%.1f)",
                             rd_idx, out_x, out_y, exp_rx[rd_idx % 32], exp_ry[rd_idx % 32]);
                    err_cnt = err_cnt + 1;
                end
            end
            rd_idx = rd_idx + 1;
        end
    end

    integer k;
    real th;
    initial begin
        repeat (5) @(negedge clk);
        rst = 1'b0;

        // Vectoring sweep across all 4 quadrants + axes
        for (k = 0; k < 64; k = k + 1) begin
            th = (k * 6.283185307179586 / 64.0) - 3.141592653589793 + 0.03;
            push_vec(1'b0, $rtoi(18000.0 * $cos(th)), $rtoi(18000.0 * $sin(th)), 0);
        end
        // Rotation sweep across all 4 quadrants
        for (k = 0; k < 32; k = k + 1) begin
            push_vec(1'b1, 16000, 0, -30000 + k * 1900);
        end

        @(negedge clk);
        in_valid = 1'b0;
        repeat (30) @(posedge clk);

        if (rd_idx != 96) begin
            $display("FAIL: tb_kria_cordic expected 96 outputs, got %0d", rd_idx);
            $finish;
        end
        if (err_cnt == 0)
            $display("PASS: tb_kria_cordic (96 vec/rot points, max_mag_err=%.2f LSB, max_ang_err=%.2f LSB)",
                     max_mag_err, max_ang_err);
        else
            $display("FAIL: tb_kria_cordic (%0d errors, max_mag_err=%.2f, max_ang_err=%.2f)",
                     err_cnt, max_mag_err, max_ang_err);
        $finish;
    end
endmodule
