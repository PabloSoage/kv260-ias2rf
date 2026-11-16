// SPDX-License-Identifier: Apache-2.0
// Unit Testbench for kria_adsb_rx (DF17 Mode-S Preamble + PPM + ICAO CRC-24)
`timescale 1ns/1ps

module tb_kria_adsb_rx;
    reg clk = 1'b0;
    always #5.0 clk = ~clk;

    reg                rst = 1'b1;
    reg                in_valid = 1'b0;
    reg signed [15:0]  in_i = 16'sd0, in_q = 16'sd0;
    wire               msg_valid, msg_crc_ok;
    wire [111:0]       msg_data;
    wire [15:0]        msg_snr_est;
    wire [31:0]        preamble_cnt, crc_ok_cnt, crc_err_cnt;

    kria_adsb_rx dut (
        .clk            (clk),
        .rst            (rst),
        .in_valid       (in_valid),
        .in_i           (in_i),
        .in_q           (in_q),
        .cfg_chip_osr   (8'd2), // 4 MSPS (2 samples per 0.5 us chip)
        .cfg_min_hi_sum (16'd4000),
        .msg_valid      (msg_valid),
        .msg_crc_ok     (msg_crc_ok),
        .msg_data       (msg_data),
        .msg_snr_est    (msg_snr_est),
        .preamble_cnt   (preamble_cnt),
        .crc_ok_cnt     (crc_ok_cnt),
        .crc_err_cnt    (crc_err_cnt)
    );

    // Known valid ICAO DF17 Extended Squitter frame:
    // 8D4840D6202CC371C32CE0576098 (CRC-24 remainder == 0)
    localparam [111:0] VALID_FRAME_1 = 112'h8D4840D6_202CC371_C32CE057_6098;
    // Flip 1 bit -> CRC must fail
    localparam [111:0] BAD_FRAME_1   = VALID_FRAME_1 ^ 112'h00000000_00000000_00010000_0000;

    task send_chip(input integer amp);
        integer r;
        begin
            for (r = 0; r < 2; r = r + 1) begin
                @(negedge clk);
                in_valid = 1'b1;
                in_i     = amp[15:0];
                in_q     = 16'sd0;
            end
        end
    endtask

    task send_frame(input [111:0] frm, input integer hi, input integer lo);
        integer b;
        reg [15:0] pre;
        begin
            // Quiet lead-in
            for (b = 0; b < 8; b = b + 1) send_chip(lo);
            // 16-chip Mode-S preamble [1,0,1,0,0,0,0,1,0,1,0,0,0,0,0,0]
            pre = 16'b1010_0001_0100_0000;
            for (b = 15; b >= 0; b = b - 1)
                send_chip(pre[b] ? hi : lo);
            // 112 PPM bits
            for (b = 111; b >= 0; b = b - 1) begin
                if (frm[b]) begin
                    send_chip(hi);
                    send_chip(lo);
                end else begin
                    send_chip(lo);
                    send_chip(hi);
                end
            end
            for (b = 0; b < 8; b = b + 1) send_chip(lo);
        end
    endtask

    reg [111:0] last_ok_frame;
    always @(posedge clk) begin
        if (msg_valid && msg_crc_ok)
            last_ok_frame <= msg_data;
    end

    initial begin
        repeat (6) @(negedge clk);
        rst = 1'b0;
        last_ok_frame = 112'd0;

        send_frame(VALID_FRAME_1, 8000, 150);
        send_frame(BAD_FRAME_1,   8000, 150);
        send_frame(VALID_FRAME_1, 5000, 300);

        @(negedge clk);
        in_valid = 1'b0;
        repeat (10) @(posedge clk);

        $display("[ADSB_RX] pre=%0d ok=%0d err=%0d last=%028h",
                 preamble_cnt, crc_ok_cnt, crc_err_cnt, last_ok_frame);
        if (preamble_cnt == 3 && crc_ok_cnt == 2 && crc_err_cnt == 1 && last_ok_frame === VALID_FRAME_1)
            $display("PASS: tb_kria_adsb_rx (2 valid DF17 CRC-24 pass, 1 bit-flip rejected)");
        else
            $display("FAIL: tb_kria_adsb_rx unexpected counts/frame");
        $finish;
    end
endmodule
