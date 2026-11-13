// SPDX-License-Identifier: BSD-2-Clause
// 1G Ethernet MAC + ARP Responder + UDP/IPv4 Framing & Control Engine (Rev06)
//
// Operates at clk_125 (125 MHz GMII):
//   - TX path: encapsulates LINK_PROTOCOL packet stream (64-bit words + 16 B
//     metadata header) into UDP/IPv4/Ethernet frames (supports 9000 B jumbo),
//     computing IPv4 header checksum and IEEE 802.3 FCS CRC-32 on the fly.
//     Wait-free 12-byte IPG. Also answers ARP requests for LOCAL_IP.
//   - RX path: validates SFD + IEEE 802.3 FCS CRC-32 residue (0x2144DF1C),
//     parses ARP requests and UDP/IPv4 control/keepalive packets targeting
//     LOCAL_UDP_PORT, and outputs registered control commands (ctrl_wr_en).

`timescale 1ns/1ps
`default_nettype none

module eth_mac_udp #(
    parameter [47:0] LOCAL_MAC       = 48'h02_0A_35_00_01_02,
    parameter [47:0] PEER_MAC        = 48'h02_0A_35_00_01_01, // KV260 PS GEM3 default / overwritten by ARP
    parameter [31:0] LOCAL_IP        = 32'hC0_A8_0A_02,       // 192.168.10.2
    parameter [31:0] PEER_IP         = 32'hC0_A8_0A_01,       // 192.168.10.1
    parameter [15:0] LOCAL_UDP_PORT  = 16'h4952,             // 'IR' = 18770
    parameter [15:0] PEER_UDP_PORT   = 16'h4952,
    parameter integer ALIVE_TIMEOUT  = 125_000_000           // 1 s keepalive timeout @ 125 MHz (override in sim)
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        link_up,

    // Packet TX Stream (same contract as link_pcs_tx)
    input  wire        pkt_valid,
    output reg         pkt_ready,
    input  wire        pkt_sop,
    input  wire        pkt_eop,
    input  wire [7:0]  pkt_stream_id,
    input  wire [15:0] pkt_len,       // payload bytes (multiple of 8, <= 8960)
    input  wire [31:0] pkt_seq,
    input  wire [63:0] pkt_timestamp,
    input  wire [63:0] pkt_data,

    // GMII interface (125 MHz)
    output reg         gmii_tx_en,
    output reg         gmii_tx_er,
    output reg  [7:0]  gmii_txd,

    input  wire        gmii_rx_dv,
    input  wire        gmii_rx_er,
    input  wire [7:0]  gmii_rxd,

    // Parsed UDP K->A Control Output (valid only on clean FCS)
    output reg         ctrl_wr_en,
    output reg  [15:0] ctrl_addr,
    output reg  [31:0] ctrl_wdata,
    output reg  [31:0] ctrl_seq,
    output reg         eth_remote_alive,
    output reg  [31:0] tx_pkt_cnt,
    output reg  [31:0] rx_pkt_cnt,
    output reg  [31:0] fcs_err_cnt
);

    // IEEE 802.3 reflected CRC-32 step (1 byte, LSB-first)
    function [31:0] crc32_byte(input [31:0] crc, input [7:0] data);
        reg [31:0] c;
        integer    i;
        begin
            c = crc;
            for (i = 0; i < 8; i = i + 1) begin
                if (c[0] ^ data[i])
                    c = (c >> 1) ^ 32'hEDB88320;
                else
                    c = (c >> 1);
            end
            crc32_byte = c;
        end
    endfunction

    // One-complement IPv4 header checksum helper
    function [15:0] ip_hdr_csum(
        input [15:0] total_len,
        input [15:0] ip_id,
        input [31:0] src_ip,
        input [31:0] dst_ip
    );
        reg [31:0] sum;
        begin
            // 0x4500 + total_len + ip_id + 0x4000(DF) + 0x4011(TTL=64,UDP) + src_ip + dst_ip
            sum = 32'h4500 + total_len + ip_id + 32'h4000 + 32'h4011
                + src_ip[31:16] + src_ip[15:0] + dst_ip[31:16] + dst_ip[15:0];
            sum = (sum[31:16] + sum[15:0]);
            sum = (sum[31:16] + sum[15:0]);
            ip_hdr_csum = ~sum[15:0];
        end
    endfunction

    // =========================================================================
    // 1. GMII RX MAC + FCS Check + ARP/UDP Parser
    // =========================================================================
    localparam [2:0] RX_WAIT_SFD = 3'd0, RX_FRAME = 3'd1, RX_DONE = 3'd2;
    reg [2:0]  rx_st;
    reg [13:0] rx_idx;
    reg [31:0] rx_crc;
    reg        rx_had_er;

    // Decoded header/control fields buffered during frame until FCS passes
    reg [47:0] rx_src_mac;
    reg [15:0] rx_ethertype;
    reg        rx_is_arp;
    reg [15:0] rx_arp_oper;
    reg [31:0] rx_arp_spa;
    reg [31:0] rx_arp_tpa;
    reg        rx_is_udp;
    reg [7:0]  rx_ip_ver_ihl;
    reg [7:0]  rx_ip_proto;
    reg [31:0] rx_src_ip;
    reg [31:0] rx_dst_ip;
    reg [15:0] rx_udp_dport;
    reg [15:0] rx_cmd_magic;
    reg [15:0] rx_cmd_addr;
    reg [31:0] rx_cmd_wdata;
    reg [31:0] rx_cmd_seq;

    reg        arp_reply_req;
    reg [47:0] arp_target_mac;
    reg [31:0] arp_target_ip;
    reg        arp_reply_ack;
    reg [47:0] peer_mac_learned;
    reg [31:0] peer_ip_learned;
    reg [31:0] alive_timer;

    // 4-byte delay pipeline so we do not parse FCS tail bytes as payload,
    // while feeding all raw bytes into rx_crc
    always @(posedge clk) begin
        if (rst) begin
            rx_st            <= RX_WAIT_SFD;
            rx_idx           <= 14'd0;
            rx_crc           <= 32'hFFFF_FFFF;
            rx_had_er        <= 1'b0;
            rx_src_mac       <= 48'd0;
            rx_ethertype     <= 16'd0;
            rx_is_arp        <= 1'b0;
            rx_arp_oper      <= 16'd0;
            rx_arp_spa       <= 32'd0;
            rx_arp_tpa       <= 32'd0;
            rx_is_udp        <= 1'b0;
            rx_ip_ver_ihl    <= 8'd0;
            rx_ip_proto      <= 8'd0;
            rx_src_ip        <= 32'd0;
            rx_dst_ip        <= 32'd0;
            rx_udp_dport     <= 16'd0;
            rx_cmd_magic     <= 16'd0;
            rx_cmd_addr      <= 16'd0;
            rx_cmd_wdata     <= 32'd0;
            rx_cmd_seq       <= 32'd0;
            ctrl_wr_en       <= 1'b0;
            ctrl_addr        <= 16'd0;
            ctrl_wdata       <= 32'd0;
            ctrl_seq         <= 32'd0;
            arp_reply_req    <= 1'b0;
            arp_target_mac   <= PEER_MAC;
            arp_target_ip    <= PEER_IP;
            peer_mac_learned <= PEER_MAC;
            peer_ip_learned  <= PEER_IP;
            eth_remote_alive <= 1'b0;
            alive_timer      <= 32'd0;
            rx_pkt_cnt       <= 32'd0;
            fcs_err_cnt      <= 32'd0;
        end else begin
            ctrl_wr_en <= 1'b0;
            if (arp_reply_ack)
                arp_reply_req <= 1'b0;

            if (alive_timer != 32'd0)
                alive_timer <= alive_timer - 32'd1;
            else
                eth_remote_alive <= 1'b0;

            case (rx_st)
                RX_WAIT_SFD: begin
                    if (gmii_rx_dv && !gmii_rx_er && gmii_rxd == 8'hD5) begin
                        rx_st         <= RX_FRAME;
                        rx_idx        <= 14'd0;
                        rx_crc        <= 32'hFFFF_FFFF;
                        rx_had_er     <= 1'b0;
                        rx_is_arp     <= 1'b0;
                        rx_is_udp     <= 1'b0;
                        rx_cmd_magic  <= 16'd0;
                    end
                end

                RX_FRAME: begin
                    if (gmii_rx_dv) begin
                        if (gmii_rx_er)
                            rx_had_er <= 1'b1;
                        rx_crc <= crc32_byte(rx_crc, gmii_rxd);
                        rx_idx <= rx_idx + 14'd1;

                        // Ethernet Header (0..13)
                        if (rx_idx >= 14'd6 && rx_idx <= 14'd11)
                            rx_src_mac <= {rx_src_mac[39:0], gmii_rxd};
                        if (rx_idx == 14'd12)
                            rx_ethertype[15:8] <= gmii_rxd;
                        if (rx_idx == 14'd13) begin
                            rx_ethertype[7:0] <= gmii_rxd;
                            rx_is_arp <= ({rx_ethertype[15:8], gmii_rxd} == 16'h0806);
                            rx_is_udp <= ({rx_ethertype[15:8], gmii_rxd} == 16'h0800);
                        end

                        // ARP Body (offset 14..41)
                        if (rx_idx == 14'd20) rx_arp_oper[15:8] <= gmii_rxd;
                        if (rx_idx == 14'd21) rx_arp_oper[7:0]  <= gmii_rxd;
                        if (rx_idx >= 14'd28 && rx_idx <= 14'd31) rx_arp_spa <= {rx_arp_spa[23:0], gmii_rxd};
                        if (rx_idx >= 14'd38 && rx_idx <= 14'd41) rx_arp_tpa <= {rx_arp_tpa[23:0], gmii_rxd};

                        // IPv4 + UDP Header (offset 14..41)
                        if (rx_idx == 14'd14) rx_ip_ver_ihl <= gmii_rxd;
                        if (rx_idx == 14'd23) rx_ip_proto   <= gmii_rxd;
                        if (rx_idx >= 14'd26 && rx_idx <= 14'd29) rx_src_ip <= {rx_src_ip[23:0], gmii_rxd};
                        if (rx_idx >= 14'd30 && rx_idx <= 14'd33) rx_dst_ip <= {rx_dst_ip[23:0], gmii_rxd};
                        if (rx_idx == 14'd36) rx_udp_dport[15:8] <= gmii_rxd;
                        if (rx_idx == 14'd37) rx_udp_dport[7:0]  <= gmii_rxd;

                        // Control / Keepalive UDP Payload (offset 42..53, big-endian network order):
                        //   [0..1] magic: 0xA55A = ctrl write, 0xA55B = keepalive ping
                        //   [2..3] addr[15:0]
                        //   [4..7] wdata[31:0]
                        //   [8..11] seq[31:0]
                        if (rx_idx == 14'd42) rx_cmd_magic[15:8] <= gmii_rxd;
                        if (rx_idx == 14'd43) rx_cmd_magic[7:0]  <= gmii_rxd;
                        if (rx_idx == 14'd44) rx_cmd_addr[15:8]  <= gmii_rxd;
                        if (rx_idx == 14'd45) rx_cmd_addr[7:0]   <= gmii_rxd;
                        if (rx_idx >= 14'd46 && rx_idx <= 14'd49) rx_cmd_wdata <= {rx_cmd_wdata[23:0], gmii_rxd};
                        if (rx_idx >= 14'd50 && rx_idx <= 14'd53) rx_cmd_seq   <= {rx_cmd_seq[23:0], gmii_rxd};
                    end else begin
                        // Frame ended: check length >= 64 (incl FCS) and CRC-32 residue
`ifdef MUTATE_ETH_SKIP_FCS
                        if (!rx_had_er && rx_idx >= 14'd64) begin
`else
                        if (!rx_had_er && rx_idx >= 14'd64 && (~rx_crc == 32'h2144_DF1C)) begin
`endif
                            rx_pkt_cnt <= rx_pkt_cnt + 32'd1;
                            if (rx_is_arp && rx_arp_oper == 16'h0001 && rx_arp_tpa == LOCAL_IP) begin
                                arp_reply_req    <= 1'b1;
                                arp_target_mac   <= rx_src_mac;
                                arp_target_ip    <= rx_arp_spa;
                                peer_mac_learned <= rx_src_mac;
                                peer_ip_learned  <= rx_arp_spa;
                            end else if (rx_is_udp && rx_ip_ver_ihl == 8'h45 && rx_ip_proto == 8'h11 &&
                                         rx_dst_ip == LOCAL_IP && rx_udp_dport == LOCAL_UDP_PORT) begin
                                eth_remote_alive <= 1'b1;
                                alive_timer      <= ALIVE_TIMEOUT;
                                peer_mac_learned <= rx_src_mac;
                                peer_ip_learned  <= rx_src_ip;
                                if (rx_cmd_magic == 16'hA55A) begin
                                    ctrl_wr_en <= 1'b1;
                                    ctrl_addr  <= rx_cmd_addr;
                                    ctrl_wdata <= rx_cmd_wdata;
                                    ctrl_seq   <= rx_cmd_seq;
                                end
                            end
                        end else begin
                            fcs_err_cnt <= fcs_err_cnt + 32'd1;
                        end
                        rx_st <= RX_WAIT_SFD;
                    end
                end

                default: rx_st <= RX_WAIT_SFD;
            endcase
        end
    end

    // =========================================================================
    // 2. GMII TX MAC: ARP Reply + Streaming Jumbo UDP/IPv4 Frame Transmitter
    // =========================================================================
    localparam [2:0] TX_IDLE    = 3'd0,
                     TX_PREAM   = 3'd1,
                     TX_HDR     = 3'd2,
                     TX_PAYLOAD = 3'd3,
                     TX_PAD     = 3'd4,
                     TX_FCS     = 3'd5,
                     TX_IPG     = 3'd6;

    reg [2:0]  tx_st;
    reg [6:0]  tx_hdr_idx;
    reg [15:0] tx_bytes_rem;
    reg [2:0]  tx_word_byte;
    reg [63:0] tx_word_buf;
    reg [31:0] tx_crc;
    reg [3:0]  tx_ipg_cnt;
    reg        tx_is_arp_pkt;

    reg [7:0]  lat_stream_id;
    reg [15:0] lat_pkt_len;
    reg [31:0] lat_pkt_seq;
    reg [63:0] lat_pkt_ts;
    reg [15:0] ip_id_cnt;
    reg [15:0] lat_ip_csum;
    reg [19:0] ip_csum_s1;
    reg [19:0] ip_csum_s2;
    reg [20:0] ip_csum_s3;
    reg [16:0] ip_csum_s4;
    reg [5:0]  tx_frame_bytes; // saturating counter up to 60 for min Ethernet length

    wire [15:0] udp_len_w      = 16'd8 + 16'd16 + lat_pkt_len;
    wire [15:0] ip_total_len_w = 16'd20 + udp_len_w;
    wire [15:0] nxt_ip_len_w   = 16'd20 + 16'd8 + 16'd16 + pkt_len;

    reg [7:0] hdr_byte_mux;
    always @(*) begin
        hdr_byte_mux = 8'h00;
        if (tx_is_arp_pkt) begin
            case (tx_hdr_idx)
                7'd0:  hdr_byte_mux = arp_target_mac[47:40];
                7'd1:  hdr_byte_mux = arp_target_mac[39:32];
                7'd2:  hdr_byte_mux = arp_target_mac[31:24];
                7'd3:  hdr_byte_mux = arp_target_mac[23:16];
                7'd4:  hdr_byte_mux = arp_target_mac[15:8];
                7'd5:  hdr_byte_mux = arp_target_mac[7:0];
                7'd6:  hdr_byte_mux = LOCAL_MAC[47:40];
                7'd7:  hdr_byte_mux = LOCAL_MAC[39:32];
                7'd8:  hdr_byte_mux = LOCAL_MAC[31:24];
                7'd9:  hdr_byte_mux = LOCAL_MAC[23:16];
                7'd10: hdr_byte_mux = LOCAL_MAC[15:8];
                7'd11: hdr_byte_mux = LOCAL_MAC[7:0];
                7'd12: hdr_byte_mux = 8'h08;
                7'd13: hdr_byte_mux = 8'h06; // ARP
                7'd14: hdr_byte_mux = 8'h00;
                7'd15: hdr_byte_mux = 8'h01; // Ethernet
                7'd16: hdr_byte_mux = 8'h08;
                7'd17: hdr_byte_mux = 8'h00; // IPv4
                7'd18: hdr_byte_mux = 8'd6;
                7'd19: hdr_byte_mux = 8'd4;
                7'd20: hdr_byte_mux = 8'h00;
                7'd21: hdr_byte_mux = 8'h02; // Reply
                7'd22: hdr_byte_mux = LOCAL_MAC[47:40];
                7'd23: hdr_byte_mux = LOCAL_MAC[39:32];
                7'd24: hdr_byte_mux = LOCAL_MAC[31:24];
                7'd25: hdr_byte_mux = LOCAL_MAC[23:16];
                7'd26: hdr_byte_mux = LOCAL_MAC[15:8];
                7'd27: hdr_byte_mux = LOCAL_MAC[7:0];
                7'd28: hdr_byte_mux = LOCAL_IP[31:24];
                7'd29: hdr_byte_mux = LOCAL_IP[23:16];
                7'd30: hdr_byte_mux = LOCAL_IP[15:8];
                7'd31: hdr_byte_mux = LOCAL_IP[7:0];
                7'd32: hdr_byte_mux = arp_target_mac[47:40];
                7'd33: hdr_byte_mux = arp_target_mac[39:32];
                7'd34: hdr_byte_mux = arp_target_mac[31:24];
                7'd35: hdr_byte_mux = arp_target_mac[23:16];
                7'd36: hdr_byte_mux = arp_target_mac[15:8];
                7'd37: hdr_byte_mux = arp_target_mac[7:0];
                7'd38: hdr_byte_mux = arp_target_ip[31:24];
                7'd39: hdr_byte_mux = arp_target_ip[23:16];
                7'd40: hdr_byte_mux = arp_target_ip[15:8];
                7'd41: hdr_byte_mux = arp_target_ip[7:0];
                default: hdr_byte_mux = 8'h00;
            endcase
        end else begin
            case (tx_hdr_idx)
                // Ethernet L2 (0..13)
                7'd0:  hdr_byte_mux = peer_mac_learned[47:40];
                7'd1:  hdr_byte_mux = peer_mac_learned[39:32];
                7'd2:  hdr_byte_mux = peer_mac_learned[31:24];
                7'd3:  hdr_byte_mux = peer_mac_learned[23:16];
                7'd4:  hdr_byte_mux = peer_mac_learned[15:8];
                7'd5:  hdr_byte_mux = peer_mac_learned[7:0];
                7'd6:  hdr_byte_mux = LOCAL_MAC[47:40];
                7'd7:  hdr_byte_mux = LOCAL_MAC[39:32];
                7'd8:  hdr_byte_mux = LOCAL_MAC[31:24];
                7'd9:  hdr_byte_mux = LOCAL_MAC[23:16];
                7'd10: hdr_byte_mux = LOCAL_MAC[15:8];
                7'd11: hdr_byte_mux = LOCAL_MAC[7:0];
                7'd12: hdr_byte_mux = 8'h08;
                7'd13: hdr_byte_mux = 8'h00;
                // IPv4 Header (14..33)
                7'd14: hdr_byte_mux = 8'h45;
                7'd15: hdr_byte_mux = 8'h00;
                7'd16: hdr_byte_mux = ip_total_len_w[15:8];
                7'd17: hdr_byte_mux = ip_total_len_w[7:0];
                7'd18: hdr_byte_mux = ip_id_cnt[15:8];
                7'd19: hdr_byte_mux = ip_id_cnt[7:0];
                7'd20: hdr_byte_mux = 8'h40; // Don't Fragment
                7'd21: hdr_byte_mux = 8'h00;
                7'd22: hdr_byte_mux = 8'd64; // TTL
                7'd23: hdr_byte_mux = 8'd17; // UDP
                7'd24: hdr_byte_mux = lat_ip_csum[15:8];
                7'd25: hdr_byte_mux = lat_ip_csum[7:0];
                7'd26: hdr_byte_mux = LOCAL_IP[31:24];
                7'd27: hdr_byte_mux = LOCAL_IP[23:16];
                7'd28: hdr_byte_mux = LOCAL_IP[15:8];
                7'd29: hdr_byte_mux = LOCAL_IP[7:0];
                7'd30: hdr_byte_mux = peer_ip_learned[31:24];
                7'd31: hdr_byte_mux = peer_ip_learned[23:16];
                7'd32: hdr_byte_mux = peer_ip_learned[15:8];
                7'd33: hdr_byte_mux = peer_ip_learned[7:0];
                // UDP Header (34..41)
                7'd34: hdr_byte_mux = LOCAL_UDP_PORT[15:8];
                7'd35: hdr_byte_mux = LOCAL_UDP_PORT[7:0];
                7'd36: hdr_byte_mux = PEER_UDP_PORT[15:8];
                7'd37: hdr_byte_mux = PEER_UDP_PORT[7:0];
                7'd38: hdr_byte_mux = udp_len_w[15:8];
                7'd39: hdr_byte_mux = udp_len_w[7:0];
                7'd40: hdr_byte_mux = 8'h00; // Optional IPv4 UDP checksum
                7'd41: hdr_byte_mux = 8'h00;
                // LINK_PROTOCOL 16-byte Metadata Header (42..57) for Kria merge:
                //   [42] stream_id, [43] flags(0), [44..45] pkt_len,
                //   [46..49] seq_num, [50..57] timestamp[63:0]
                7'd42: hdr_byte_mux = lat_stream_id;
                7'd43: hdr_byte_mux = 8'h00;
                7'd44: hdr_byte_mux = lat_pkt_len[15:8];
                7'd45: hdr_byte_mux = lat_pkt_len[7:0];
                7'd46: hdr_byte_mux = lat_pkt_seq[31:24];
                7'd47: hdr_byte_mux = lat_pkt_seq[23:16];
                7'd48: hdr_byte_mux = lat_pkt_seq[15:8];
                7'd49: hdr_byte_mux = lat_pkt_seq[7:0];
                7'd50: hdr_byte_mux = lat_pkt_ts[63:56];
                7'd51: hdr_byte_mux = lat_pkt_ts[55:48];
                7'd52: hdr_byte_mux = lat_pkt_ts[47:40];
                7'd53: hdr_byte_mux = lat_pkt_ts[39:32];
                7'd54: hdr_byte_mux = lat_pkt_ts[31:24];
                7'd55: hdr_byte_mux = lat_pkt_ts[23:16];
                7'd56: hdr_byte_mux = lat_pkt_ts[15:8];
                7'd57: hdr_byte_mux = lat_pkt_ts[7:0];
                default: hdr_byte_mux = 8'h00;
            endcase
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            tx_st          <= TX_IDLE;
            tx_hdr_idx     <= 7'd0;
            tx_bytes_rem   <= 16'd0;
            tx_word_byte   <= 3'd0;
            tx_word_buf    <= 64'd0;
            tx_crc         <= 32'hFFFF_FFFF;
            tx_ipg_cnt     <= 4'd0;
            tx_is_arp_pkt  <= 1'b0;
            arp_reply_ack  <= 1'b0;
            lat_stream_id  <= 8'd0;
            lat_pkt_len    <= 16'd0;
            lat_pkt_seq    <= 32'd0;
            lat_pkt_ts     <= 64'd0;
            ip_id_cnt      <= 16'd0;
            lat_ip_csum    <= 16'd0;
            ip_csum_s1     <= 20'd0;
            ip_csum_s2     <= 20'd0;
            ip_csum_s3     <= 21'd0;
            ip_csum_s4     <= 17'd0;
            tx_frame_bytes <= 6'd0;
            pkt_ready      <= 1'b0;
            gmii_tx_en     <= 1'b0;
            gmii_tx_er     <= 1'b0;
            gmii_txd       <= 8'h00;
            tx_pkt_cnt     <= 32'd0;
        end else begin
            pkt_ready     <= 1'b0;
            arp_reply_ack <= 1'b0;
            gmii_tx_er    <= 1'b0;

            case (tx_st)
                TX_IDLE: begin
                    gmii_tx_en <= 1'b0;
                    if (link_up) begin
                        if (arp_reply_req) begin
                            tx_is_arp_pkt  <= 1'b1;
                            arp_reply_ack  <= 1'b1;
                            tx_hdr_idx     <= 7'd0;
                            tx_frame_bytes <= 6'd0;
                            tx_st          <= TX_PREAM;
                        end else if (pkt_valid) begin
                            tx_is_arp_pkt  <= 1'b0;
                            lat_stream_id  <= pkt_stream_id;
                            lat_pkt_len    <= pkt_len;
                            lat_pkt_seq    <= pkt_seq;
                            lat_pkt_ts     <= pkt_timestamp;
                            tx_bytes_rem   <= pkt_len;
                            ip_id_cnt      <= ip_id_cnt + 16'd1;
                            tx_hdr_idx     <= 7'd0;
                            tx_frame_bytes <= 6'd0;
                            tx_st          <= TX_PREAM;
                        end
                    end
                end

                TX_PREAM: begin
                    gmii_tx_en <= 1'b1;
                    // Pipelined IPv4 header checksum during 8-byte preamble (0x4500+0x4000+0x4011 = 0xC511)
                    if (!tx_is_arp_pkt) begin
                        case (tx_hdr_idx)
                            7'd0: begin
                                ip_csum_s1 <= {4'd0, ip_total_len_w} + {4'd0, ip_id_cnt} + 20'h0C511;
                                ip_csum_s2 <= {4'd0, LOCAL_IP[31:16]} + {4'd0, LOCAL_IP[15:0]}
                                            + {4'd0, peer_ip_learned[31:16]} + {4'd0, peer_ip_learned[15:0]};
                            end
                            7'd1: ip_csum_s3 <= {1'b0, ip_csum_s1} + {1'b0, ip_csum_s2};
                            7'd2: ip_csum_s4 <= {12'd0, ip_csum_s3[20:16]} + {1'b0, ip_csum_s3[15:0]};
                            7'd3: lat_ip_csum <= ~(ip_csum_s4[15:0] + {15'd0, ip_csum_s4[16]});
                            default: ;
                        endcase
                    end
                    if (tx_hdr_idx < 7'd7) begin
                        gmii_txd   <= 8'h55;
                        tx_hdr_idx <= tx_hdr_idx + 7'd1;
                    end else begin
                        gmii_txd   <= 8'hD5; // SFD
                        tx_hdr_idx <= 7'd0;
                        tx_crc     <= 32'hFFFF_FFFF;
                        tx_st      <= TX_HDR;
                    end
                end

                TX_HDR: begin
                    gmii_tx_en <= 1'b1;
                    gmii_txd   <= hdr_byte_mux;
                    tx_crc     <= crc32_byte(tx_crc, hdr_byte_mux);
                    if (tx_frame_bytes < 6'd60)
                        tx_frame_bytes <= tx_frame_bytes + 6'd1;

                    if (tx_is_arp_pkt && tx_hdr_idx == 7'd41) begin
                        tx_st <= TX_PAD;
                    end else if (!tx_is_arp_pkt && tx_hdr_idx == 7'd57) begin
                        tx_word_buf  <= pkt_data;
                        tx_word_byte <= 3'd0;
                        // Pop first 64-bit word on last header byte so pipeline continues seamlessly
                        if (tx_bytes_rem != 16'd0) begin
                            pkt_ready <= 1'b1;
                            tx_st     <= TX_PAYLOAD;
                        end else begin
                            tx_st <= TX_PAD;
                        end
                    end else begin
                        tx_hdr_idx <= tx_hdr_idx + 7'd1;
                    end
                end

                TX_PAYLOAD: begin
                    gmii_tx_en <= 1'b1;
                    gmii_txd   <= tx_word_buf[7:0]; // Match link_framer little-endian byte order (byte 0 = [7:0])
                    tx_crc     <= crc32_byte(tx_crc, tx_word_buf[7:0]);
                    if (tx_frame_bytes < 6'd60)
                        tx_frame_bytes <= tx_frame_bytes + 6'd1;

                    tx_word_buf  <= {8'h00, tx_word_buf[63:8]};
                    tx_bytes_rem <= tx_bytes_rem - 16'd1;

                    if (tx_bytes_rem == 16'd1) begin
                        if (tx_frame_bytes >= 6'd59) begin
                            tx_hdr_idx <= 7'd0;
                            tx_st      <= TX_FCS;
                        end else begin
                            tx_st <= TX_PAD;
                        end
                    end else if (tx_word_byte == 3'd6 && tx_bytes_rem > 16'd2) begin
                        // Assert pkt_ready one cycle before word_byte==7 transition only if another 64-bit word remains
                        tx_word_byte <= 3'd7;
                        pkt_ready    <= 1'b1;
                    end else if (tx_word_byte == 3'd7) begin
                        tx_word_byte <= 3'd0;
                        tx_word_buf  <= pkt_data;
                    end else begin
                        tx_word_byte <= tx_word_byte + 3'd1;
                    end
                end

                TX_PAD: begin
                    gmii_tx_en <= 1'b1;
                    gmii_txd   <= 8'h00;
                    tx_crc     <= crc32_byte(tx_crc, 8'h00);
                    if (tx_frame_bytes >= 6'd59) begin
                        tx_hdr_idx <= 7'd0;
                        tx_st      <= TX_FCS;
                    end else begin
                        tx_frame_bytes <= tx_frame_bytes + 6'd1;
                    end
                end

                TX_FCS: begin
                    gmii_tx_en <= 1'b1;
                    case (tx_hdr_idx[1:0])
                        2'd0: gmii_txd <= ~tx_crc[7:0];
                        2'd1: gmii_txd <= ~tx_crc[15:8];
                        2'd2: gmii_txd <= ~tx_crc[23:16];
                        2'd3: gmii_txd <= ~tx_crc[31:24];
                    endcase
                    if (tx_hdr_idx[1:0] == 2'd3) begin
                        tx_ipg_cnt <= 4'd0;
                        if (!tx_is_arp_pkt)
                            tx_pkt_cnt <= tx_pkt_cnt + 32'd1;
                        tx_st <= TX_IPG;
                    end else begin
                        tx_hdr_idx <= tx_hdr_idx + 7'd1;
                    end
                end

                TX_IPG: begin
                    gmii_tx_en <= 1'b0;
                    gmii_txd   <= 8'h00;
                    if (tx_ipg_cnt == 4'd11)
                        tx_st <= TX_IDLE;
                    else
                        tx_ipg_cnt <= tx_ipg_cnt + 4'd1;
                end

                default: tx_st <= TX_IDLE;
            endcase
        end
    end

endmodule
`default_nettype wire
