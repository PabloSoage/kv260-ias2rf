// SPDX-License-Identifier: Apache-2.0
// Unit Testbench for kria_adsb_rx (DF17 Mode-S Preamble + PPM + ICAO CRC-24)
`timescale 1ns/1ps

module tb_kria_adsb_rx;
    reg clk = 1'b0;
    always #5.0 clk = ~clk;

    reg                rst = 1'b1;
    reg                in_valid = 1'b0;
    reg signed [15:0]  in_i = 16'sd0, in_q = 16'sd0;
    reg [7:0]          osr = 8'd2;
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
        .cfg_chip_osr   (osr),  // 4 MSPS (2 samples per chip), then 25 MSPS (8'h8C, 12.5 samples per chip)
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

    // 25 MSPS: chip c covers samples [12.5 c, 12.5 (c + 1)); the frame starts off_q quarter chips into sample time
    integer off_q;
    reg [15:0] pre_bits;
    reg     ok4, ok25;
    task send_frame_25(input [111:0] frm, input integer hi, input integer lo, input integer offq);
        reg [255:0] chips;
        integer b, c, n, nch;
        begin
            pre_bits = 16'b1010_0001_0100_0000;
            chips = 256'd0;
            nch = 16 + 224;
            for (b = 0; b < 16; b = b + 1) chips[b] = pre_bits[15 - b];
            for (b = 0; b < 112; b = b + 1) begin
                chips[16 + 2 * b]     = frm[111 - b];
                chips[16 + 2 * b + 1] = ~frm[111 - b];
            end
            // 20 quiet chips, the frame, 20 quiet chips; sample n sits at chip time (8 n - 25 offq) / 100
            for (n = 0; n < (nch + 40) * 25 / 2; n = n + 1) begin
                c = (n * 8 - offq * 25) / 100 - 20;
                @(negedge clk);
                in_valid = 1'b1;
                in_i = (c >= 0 && c < nch && chips[c]) ? hi : lo;
                in_q = 16'sd0;
            end
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
        ok4 = (preamble_cnt == 3 && crc_ok_cnt == 2 && crc_err_cnt == 1 && last_ok_frame === VALID_FRAME_1);

        // 25 MSPS, 12.5 samples per chip: the same frame a quarter chip later each time, against a free-running
        // chip grid; every one must decode (Rev08 G-8: one grid alone fails half a chip off)
        osr = 8'h8C;
        rst = 1'b1; repeat (4) @(negedge clk); rst = 1'b0;
        for (off_q = 0; off_q < 4; off_q = off_q + 1)
            send_frame_25(VALID_FRAME_1, 8000, 150, off_q);
        @(negedge clk); in_valid = 1'b0; repeat (10) @(posedge clk);
        $display("[ADSB_RX 25 MSPS] pre=%0d ok=%0d err=%0d", preamble_cnt, crc_ok_cnt, crc_err_cnt);
        ok25 = (crc_ok_cnt == 4 && crc_err_cnt == 0);

        if (ok4 && ok25)
            $display("PASS: tb_kria_adsb_rx (4 MSPS: 2 valid, 1 bit-flip rejected; 25 MSPS: 4 of 4 at quarter-chip offsets)");
        else
            $display("FAIL: tb_kria_adsb_rx unexpected counts/frame (4 MSPS ok=%0d, 25 MSPS ok=%0d)", ok4, ok25);
        $finish;
    end
endmodule
