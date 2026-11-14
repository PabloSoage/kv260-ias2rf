// SPDX-License-Identifier: BSD-2-Clause
// Behavioral RTL8211FSI SGMII PHY + KV260 PS GEM3 UDP Peer Model
//
// Models:
//   - Clause 22 open-drain MDIO slave (PHYAD=1, BMSR link-up + R/W register array).
//   - Clause 37 /C1/,/C2/ SGMII Auto-Negotiation handshake.
//   - 1.25 Gb/s SGMII 8b/10b TX & oversampled RX CDR driven at configurable
//     asynchronous +/-100 ppm clock skew (peer_half_ui_ps).
//   - UDP/IPv4/Ethernet MAC peer with IEEE CRC-32 FCS verification, bad-FCS
//     frame injection, and RX sequence tracking per stream_id (0x01 / 0x02).

`timescale 1ps/10fs

module sim_sgmii_phy_peer (
    input  wire eth_rst_n,
    input  wire eth_mdc,
    inout  wire eth_mdio,

    input  wire eth_sgtx_p,
    input  wire eth_sgtx_n,
    output reg  eth_sgrx_p = 1'b0,
    output reg  eth_sgrx_n = 1'b1,

    input  wire [31:0] peer_half_ui_fs, // 399960 (+100ppm) or 400040 (-100ppm) in fs
    input  wire peer_rst_n,
    input  wire link_rx_cut,     // Simulate physical Ethernet RX drop

    output integer mdio_poll_reads,
    output integer mdio_custom_wrs,
    output integer eth_fcs_fail,
    output integer eth_s1_cnt,
    output integer eth_s2_cnt,
    output reg [1023:0] seen_eth_s1,
    output reg [1023:0] seen_eth_s2,
    output integer eth_max_s1,
    output integer eth_max_s2
);
    localparam [47:0] ARTIX_MAC = 48'h02_0A_35_00_01_02;
    localparam [47:0] KRIA_MAC  = 48'h02_0A_35_00_01_01;
    localparam [31:0] ARTIX_IP  = 32'hC0_A8_0A_02;
    localparam [31:0] KRIA_IP   = 32'hC0_A8_0A_01;
    localparam [15:0] UDP_PORT  = 16'h4952;

    localparam [7:0] K_28_5 = 8'hBC;
    localparam [7:0] K_27_7 = 8'hFB;
    localparam [7:0] K_29_7 = 8'hFD;
    localparam [7:0] K_23_7 = 8'hF7;
    localparam [7:0] D_5_6  = 8'hC5;
    localparam [7:0] D_16_2 = 8'h50;
    localparam [7:0] D_21_5 = 8'hB5;
    localparam [7:0] D_2_2  = 8'h42;
    localparam [9:0] K28_5_RD_NEG = 10'h17C;
    localparam [9:0] K28_5_RD_POS = 10'h283;

    // -------------------------------------------------------------------------
    // Async Peer 1.25 GHz Half-UI Bit Clock & Clause 22 MDIO Slave (PHYAD=1)
    // -------------------------------------------------------------------------
    reg peer_bit_clk = 1'b0;
    initial begin
        peer_bit_clk = 1'b0;
        forever begin
            if (peer_half_ui_fs < 32'd100_000)
                #400.000;
            else
                #(peer_half_ui_fs / 1000.0);
            peer_bit_clk = ~peer_bit_clk;
        end
    end

    reg [15:0] phy_regs [0:31];
    integer r_idx;
    initial begin
        mdio_poll_reads = 0;
        mdio_custom_wrs = 0;
        eth_fcs_fail    = 0;
        eth_s1_cnt      = 0;
        eth_s2_cnt      = 0;
        seen_eth_s1     = 1024'd0;
        seen_eth_s2     = 1024'd0;
        eth_max_s1      = -1;
        eth_max_s2      = -1;
        for (r_idx = 0; r_idx < 32; r_idx = r_idx + 1) phy_regs[r_idx] = 16'h0000;
        phy_regs[0] = 16'h1140;
        phy_regs[1] = 16'h796D; // Link UP
        phy_regs[2] = 16'h001C;
        phy_regs[3] = 16'hC916;
    end

    reg        mdio_drv_en  = 1'b0;
    reg        mdio_drv_val = 1'b1;
    assign eth_mdio = mdio_drv_en ? mdio_drv_val : 1'bz;

    reg [5:0]  mdio_bit = 6'd0;
    reg [31:0] mdio_sh  = 32'd0;
    reg [1:0]  mdio_op  = 2'd0;
    reg [4:0]  mdio_pa  = 5'd0;
    reg [4:0]  mdio_ra  = 5'd0;
    reg [15:0] mdio_rd_buf = 16'd0;
    reg [15:0] mdio_wr_buf = 16'd0;

    always @(posedge eth_mdc or negedge eth_rst_n) begin
        if (!eth_rst_n) begin
            mdio_bit    <= 6'd0;
            mdio_drv_en <= 1'b0;
        end else if (mdio_bit == 6'd0) begin
            mdio_drv_en <= 1'b0;
            if (mdio_sh[0] === 1'b1 && eth_mdio === 1'b0)
                mdio_bit <= 6'd1;
            mdio_sh <= {mdio_sh[30:0], eth_mdio};
        end else begin
            mdio_bit <= mdio_bit + 6'd1;
            if (mdio_bit == 6'd1 && eth_mdio !== 1'b1) mdio_bit <= 6'd0;
            else if (mdio_bit == 6'd2) mdio_op[1] <= eth_mdio;
            else if (mdio_bit == 6'd3) mdio_op[0] <= eth_mdio;
            else if (mdio_bit >= 6'd4 && mdio_bit <= 6'd8) mdio_pa <= {mdio_pa[3:0], eth_mdio};
            else if (mdio_bit >= 6'd9 && mdio_bit <= 6'd13) mdio_ra <= {mdio_ra[3:0], eth_mdio};
            else if (mdio_bit == 6'd14 && mdio_op == 2'b10 && mdio_pa == 5'd1) mdio_rd_buf <= phy_regs[mdio_ra];
            else if (mdio_bit == 6'd15 && mdio_op == 2'b10 && mdio_pa == 5'd1) begin
                mdio_drv_en <= 1'b1; mdio_drv_val <= 1'b0;
            end else if (mdio_bit >= 6'd16 && mdio_bit <= 6'd31) begin
                if (mdio_op == 2'b10 && mdio_pa == 5'd1) begin
                    mdio_drv_en  <= 1'b1;
                    mdio_drv_val <= mdio_rd_buf[31 - mdio_bit];
                    if (mdio_bit == 6'd31) mdio_poll_reads <= mdio_poll_reads + 1;
                end else if (mdio_op == 2'b01 && mdio_pa == 5'd1) begin
                    mdio_wr_buf <= {mdio_wr_buf[14:0], eth_mdio};
                    if (mdio_bit == 6'd31) begin
                        phy_regs[mdio_ra] <= {mdio_wr_buf[14:0], eth_mdio};
                        mdio_custom_wrs   <= mdio_custom_wrs + 1;
                    end
                end
            end else if (mdio_bit >= 6'd32) begin
                mdio_drv_en <= 1'b0;
                mdio_bit    <= 6'd0;
            end
        end
    end

    // -------------------------------------------------------------------------
    // SGMII Peer TX (8b/10b + Clause 37 AN + UDP Frame Queue)
    // -------------------------------------------------------------------------
    reg [3:0]  peer_bit_idx = 4'd0;
    reg        peer_clk_125 = 1'b0;
    reg        peer_tx_k    = 1'b1;
    reg [7:0]  peer_tx_d    = K_28_5;
    wire [9:0] peer_enc_code;
    wire       peer_enc_rd;
    reg [9:0]  peer_tx_sr   = K28_5_RD_NEG;
    reg        sgrx_drv     = 1'b0;

    eth_8b10b_enc u_peer_enc (
        .clk    (peer_clk_125),
        .rst    (!peer_rst_n),
        .en     (1'b1),
        .din_k  (peer_tx_k),
        .din    (peer_tx_d),
        .dout   (peer_enc_code),
        .rd_pos (peer_enc_rd)
    );

    always @(posedge peer_bit_clk) begin
        if (peer_bit_idx == 4'd9) begin
            peer_bit_idx <= 4'd0;
            peer_clk_125 <= 1'b1;
            peer_tx_sr   <= peer_enc_code;
            sgrx_drv     <= peer_enc_code[0];
        end else begin
            peer_bit_idx <= peer_bit_idx + 4'd1;
            if (peer_bit_idx == 4'd4) peer_clk_125 <= 1'b0;
            sgrx_drv     <= peer_tx_sr[peer_bit_idx + 1];
        end
        eth_sgrx_p <=  sgrx_drv;
        eth_sgrx_n <= ~sgrx_drv;
    end

    reg [7:0]  peer_q_mem [0:1535];
    integer    peer_q_wr = 0;
    integer    peer_q_rd = 0;
    reg [1:0]  peer_an_mode = 2'd0; // 0: /C/ Ack=0, 1: /C/ Ack=1, 2: DATA
    reg        peer_an_c2   = 1'b0;
    reg [1:0]  peer_an_sub  = 2'd0;
    reg        peer_even    = 1'b0;
    reg [2:0]  peer_pcs_st  = 3'd0;
    reg [15:0] peer_ip_id   = 16'd1;

    function [31:0] crc32_byte(input [31:0] crc, input [7:0] data);
        reg [31:0] c;
        integer    i;
        begin
            c = crc;
            for (i = 0; i < 8; i = i + 1) begin
                if (c[0] ^ data[i]) c = (c >> 1) ^ 32'hEDB88320;
                else                c = (c >> 1);
            end
            crc32_byte = c;
        end
    endfunction

    function [15:0] ipv4_csum(input [15:0] tot_len, input [15:0] ip_id,
                              input [31:0] sip, input [31:0] dip);
        reg [31:0] sum;
        begin
            sum = 32'h00004500 + tot_len + ip_id + 32'h00004000 + 32'h00004011 +
                  sip[31:16] + sip[15:0] + dip[31:16] + dip[15:0];
            sum = (sum[31:16] + sum[15:0]);
            sum = (sum[31:16] + sum[15:0]);
            ipv4_csum = ~sum[15:0];
        end
    endfunction

    always @(posedge peer_clk_125) begin
        if (!peer_rst_n) begin
            peer_pcs_st <= 3'd0;
            peer_an_sub <= 2'd0;
            peer_an_c2  <= 1'b0;
            peer_even   <= 1'b0;
            peer_tx_k   <= 1'b1;
            peer_tx_d   <= K_28_5;
        end else begin
            peer_even <= ~peer_even;
            case (peer_pcs_st)
                3'd0: begin
                    if (peer_an_mode == 2'd2 && peer_an_sub == 2'd0 && !peer_even) begin
                        peer_pcs_st <= 3'd2;
                        peer_tx_k   <= 1'b1;
                        peer_tx_d   <= K_28_5;
                    end else begin
                        case (peer_an_sub)
                            2'd0: begin peer_tx_k <= 1'b1; peer_tx_d <= K_28_5; end
                            2'd1: begin peer_tx_k <= 1'b0; peer_tx_d <= peer_an_c2 ? D_2_2 : D_21_5; peer_an_c2 <= ~peer_an_c2; end
                            2'd2: begin peer_tx_k <= 1'b0; peer_tx_d <= 8'h01; end
                            2'd3: begin peer_tx_k <= 1'b0; peer_tx_d <= (peer_an_mode == 2'd0) ? 8'h98 : 8'hD8; end
                        endcase
                        peer_an_sub <= peer_an_sub + 2'd1;
                    end
                end
                3'd1: begin
                    if (peer_q_rd < peer_q_wr) begin
                        peer_tx_k <= 1'b1; peer_tx_d <= K_27_7;
                        peer_q_rd <= peer_q_rd + 1;
                        peer_pcs_st <= 3'd3;
                    end else begin
                        peer_tx_k <= 1'b1; peer_tx_d <= K_28_5;
                        peer_pcs_st <= 3'd2;
                    end
                end
                3'd2: begin
                    peer_tx_k <= 1'b0;
                    peer_tx_d <= (peer_enc_rd == 1'b1) ? D_5_6 : D_16_2;
                    peer_pcs_st <= 3'd1;
                end
                3'd3: begin
                    if (peer_q_rd < peer_q_wr) begin
                        peer_tx_k <= 1'b0;
                        peer_tx_d <= peer_q_mem[peer_q_rd];
                        peer_q_rd <= peer_q_rd + 1;
                    end else begin
                        peer_tx_k <= 1'b1; peer_tx_d <= K_29_7;
                        peer_pcs_st <= 3'd4;
                    end
                end
                3'd4: begin
                    peer_tx_k <= 1'b1; peer_tx_d <= K_23_7;
                    peer_pcs_st <= peer_even ? 3'd4 : 3'd1;
                end
                default: peer_pcs_st <= 3'd1;
            endcase
        end
    end

    task automatic set_an_mode(input [1:0] m);
        begin
            peer_an_mode = m;
        end
    endtask

    task automatic send_udp_frame(
        input [15:0] magic,
        input [15:0] addr,
        input [31:0] wdata,
        input [31:0] seq,
        input        corrupt_fcs
    );
        reg [7:0]  fbuf [0:79];
        reg [31:0] crc;
        reg [15:0] icsum;
        integer    i;
        begin
            while (peer_q_rd < peer_q_wr) @(posedge peer_clk_125);
            peer_ip_id = peer_ip_id + 16'd1;
            icsum = ipv4_csum(16'd46, peer_ip_id, KRIA_IP, ARTIX_IP);

            for (i = 0; i < 7; i = i + 1) fbuf[i] = 8'h55;
            fbuf[7] = 8'hD5;
            {fbuf[8],fbuf[9],fbuf[10],fbuf[11],fbuf[12],fbuf[13]}   = ARTIX_MAC;
            {fbuf[14],fbuf[15],fbuf[16],fbuf[17],fbuf[18],fbuf[19]} = KRIA_MAC;
            {fbuf[20],fbuf[21]} = 16'h0800;
            fbuf[22] = 8'h45; fbuf[23] = 8'h00;
            {fbuf[24],fbuf[25]} = 16'd46;
            {fbuf[26],fbuf[27]} = peer_ip_id;
            {fbuf[28],fbuf[29]} = 16'h4000;
            fbuf[30] = 8'd64; fbuf[31] = 8'd17;
            {fbuf[32],fbuf[33]} = icsum;
            {fbuf[34],fbuf[35],fbuf[36],fbuf[37]} = KRIA_IP;
            {fbuf[38],fbuf[39],fbuf[40],fbuf[41]} = ARTIX_IP;
            {fbuf[42],fbuf[43]} = UDP_PORT;
            {fbuf[44],fbuf[45]} = UDP_PORT;
            {fbuf[46],fbuf[47]} = 16'd26;
            {fbuf[48],fbuf[49]} = 16'h0000;
            {fbuf[50],fbuf[51]} = magic;
            {fbuf[52],fbuf[53]} = addr;
            {fbuf[54],fbuf[55],fbuf[56],fbuf[57]} = wdata;
            {fbuf[58],fbuf[59],fbuf[60],fbuf[61]} = seq;
            for (i = 62; i < 68; i = i + 1) fbuf[i] = 8'h00;

            crc = 32'hFFFF_FFFF;
            for (i = 8; i < 68; i = i + 1) crc = crc32_byte(crc, fbuf[i]);
            fbuf[68] = ~crc[7:0];
            fbuf[69] = ~crc[15:8];
            fbuf[70] = ~crc[23:16];
            fbuf[71] = (~crc[31:24]) ^ (corrupt_fcs ? 8'hFF : 8'h00);

            @(posedge peer_clk_125);
            peer_q_rd = 0;
            peer_q_wr = 0;
            for (i = 0; i < 72; i = i + 1) peer_q_mem[i] = fbuf[i];
            peer_q_wr = 72;
            while (peer_q_rd < peer_q_wr) @(posedge peer_clk_125);
            repeat (24) @(posedge peer_clk_125);
        end
    endtask

    // -------------------------------------------------------------------------
    // SGMII Peer RX CDR & UDP Scoreboard
    // -------------------------------------------------------------------------
    reg cdr_tick = 1'b0;
    always #100.000 cdr_tick = ~cdr_tick; // 200 ps step = 4x oversampling @ 1.25 Gbps

    reg       prev_sgtx      = 1'b0;
    reg [1:0] ui_tick        = 2'd0;
    reg [49:0] cdr_hist      = 50'd0;
    reg [49:0] next_hist;
    reg       cdr_aligned    = 1'b0;
    reg [3:0] cdr_bit_phase  = 4'd0;
    reg [9:0] cdr_sym        = 10'd0;
    reg       cdr_sym_tgl    = 1'b0;
    reg       cdr_relock_tog = 1'b0;
    reg       cdr_relock_ack = 1'b0;

    always @(posedge cdr_tick) begin
        if (link_rx_cut) begin
            ui_tick        <= 2'd0;
            cdr_aligned    <= 1'b0;
            cdr_hist       <= 50'd0;
            cdr_relock_ack <= cdr_relock_tog;
        end else begin
            if (cdr_relock_tog !== cdr_relock_ack) begin
                cdr_relock_ack <= cdr_relock_tog;
                cdr_aligned    <= 1'b0;
            end
            if (eth_sgtx_p !== prev_sgtx) begin
                prev_sgtx <= eth_sgtx_p;
                ui_tick   <= 2'd3; // sample 2 ticks (400 ps) after detect (~400..600 ps into 800 ps UI)
            end else begin
                ui_tick <= ui_tick + 2'd1;
            end

            if (ui_tick == 2'd0) begin
                next_hist = {eth_sgtx_p, cdr_hist[49:1]};
                cdr_hist <= next_hist;
                if (!cdr_aligned) begin
                    if ((next_hist[49:40] == K28_5_RD_NEG || next_hist[49:40] == K28_5_RD_POS) &&
                        ((next_hist[29:20] == K28_5_RD_NEG || next_hist[29:20] == K28_5_RD_POS) ||
                         (next_hist[9:0]   == K28_5_RD_NEG || next_hist[9:0]   == K28_5_RD_POS))) begin
                        cdr_aligned   <= 1'b1;
                        cdr_bit_phase <= 4'd0;
                        cdr_sym       <= next_hist[49:40];
                        cdr_sym_tgl   <= ~cdr_sym_tgl;
                    end
                end else if (cdr_bit_phase == 4'd9) begin
                    cdr_bit_phase <= 4'd0;
                    cdr_sym       <= next_hist[49:40];
                    cdr_sym_tgl   <= ~cdr_sym_tgl;
                end else begin
                    cdr_bit_phase <= cdr_bit_phase + 4'd1;
                end
            end
        end
    end

    wire       peer_dec_rd_pos;
    wire       peer_rx_k, peer_rx_code_err, peer_rx_disp_err;
    wire [7:0] peer_rx_d;
    reg        peer_rec_clk = 1'b0;
    always @(cdr_sym_tgl) begin
        peer_rec_clk = 1'b1;
        #100.000;
        peer_rec_clk = 1'b0;
    end

    eth_8b10b_dec u_peer_dec (
        .clk      (peer_rec_clk),
        .rst      (!peer_rst_n),
        .en       (1'b1),
        .din      (cdr_sym),
        .dout_k   (peer_rx_k),
        .dout     (peer_rx_d),
        .code_err (peer_rx_code_err),
        .disp_err (peer_rx_disp_err),
        .rd_pos   (peer_dec_rd_pos)
    );

    reg [2:0]  cdr_err_cnt      = 3'd0;
    reg        eth_rx_in_pkt    = 1'b0;
    reg        eth_rx_sfd_seen  = 1'b0;
    reg [31:0] eth_rx_crc       = 32'hFFFF_FFFF;
    integer    eth_rx_idx       = 0;
    reg [15:0] eth_rx_ethertype = 16'd0;
    reg [7:0]  eth_rx_sid       = 8'd0;
    reg [31:0] eth_rx_seq       = 32'd0;
    reg        eth_rx_bad       = 1'b0;

    always @(posedge peer_rec_clk) begin
        if (!peer_rst_n || link_rx_cut) begin
            cdr_err_cnt     <= 3'd0;
            eth_rx_in_pkt   <= 1'b0;
            eth_rx_sfd_seen <= 1'b0;
        end else begin
            if (peer_rx_code_err) begin
                if (cdr_err_cnt >= 3'd3) begin
                    cdr_err_cnt    <= 3'd0;
                    cdr_relock_tog <= ~cdr_relock_tog;
                end else begin
                    cdr_err_cnt <= cdr_err_cnt + 3'd1;
                end
            end else begin
                cdr_err_cnt <= 3'd0;
            end

            if (!eth_rx_in_pkt) begin
            if (peer_rx_k && peer_rx_d == K_27_7) begin
                eth_rx_in_pkt   <= 1'b1;
                eth_rx_sfd_seen <= 1'b0;
                eth_rx_bad      <= 1'b0;
            end
        end else begin
            if (peer_rx_k && (peer_rx_d == K_29_7 || peer_rx_d == K_28_5)) begin
                eth_rx_in_pkt <= 1'b0;
                if (eth_rx_sfd_seen) begin
                    if (eth_rx_bad || eth_rx_idx < 64 || (~eth_rx_crc != 32'h2144_DF1C)) begin
                        eth_fcs_fail <= eth_fcs_fail + 1;
                    end else if (eth_rx_ethertype == 16'h0800) begin
                        if (eth_rx_sid == 8'h01) begin
                            eth_s1_cnt                   <= eth_s1_cnt + 1;
                            seen_eth_s1[eth_rx_seq[9:0]] <= 1'b1;
                            if ($signed(eth_rx_seq) > eth_max_s1) eth_max_s1 <= eth_rx_seq;
                        end else if (eth_rx_sid == 8'h02) begin
                            eth_s2_cnt                   <= eth_s2_cnt + 1;
                            seen_eth_s2[eth_rx_seq[9:0]] <= 1'b1;
                            if ($signed(eth_rx_seq) > eth_max_s2) eth_max_s2 <= eth_rx_seq;
                        end
                    end
                end
            end else if (peer_rx_k || peer_rx_code_err) begin
                eth_rx_bad <= 1'b1;
            end else if (!eth_rx_sfd_seen) begin
                if (peer_rx_d == 8'hD5) begin
                    eth_rx_sfd_seen <= 1'b1;
                    eth_rx_idx      <= 0;
                    eth_rx_crc      <= 32'hFFFF_FFFF;
                end
            end else begin
                eth_rx_crc <= crc32_byte(eth_rx_crc, peer_rx_d);
                eth_rx_idx <= eth_rx_idx + 1;
                if (eth_rx_idx == 12) eth_rx_ethertype[15:8] <= peer_rx_d;
                if (eth_rx_idx == 13) eth_rx_ethertype[7:0]  <= peer_rx_d;
                if (eth_rx_idx == 42) eth_rx_sid             <= peer_rx_d;
                if (eth_rx_idx >= 46 && eth_rx_idx <= 49) eth_rx_seq <= {eth_rx_seq[23:0], peer_rx_d};
            end
        end
        end
    end
endmodule
