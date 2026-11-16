// SPDX-License-Identifier: Apache-2.0
// Kria PL Integrated DSP & Demodulation/Radar/TX Suite (0x40..0x7C CSR Window)
//
// Aggregates:
//   - kria_channel_rx : Sub-DDC + CIC3 + 31-tap FIR + AM / USB / LSB / NBFM+CTCSS / WBFM+Stereo+RDS
//   - kria_adsb_rx    : 1090 MHz Mode-S Extended Squitter PPM Preamble + ICAO CRC-24 Decoder
//   - kria_tx_mod     : CW / AM / NBFM / USB / LSB TX Modulator -> s_axis_tx (8'h12 -> Artix dac_sdr)
//   - kria_radar_proc : 64x16 Range-Doppler 2D-FFT + CA-CFAR Detector
//
// Unpacks 64-bit IAS1 uplink packets ({Q1, I1, Q0, I0}) non-intrusively on m_axis_rx and exposes
// full control/status via 0x40..0x7C on pl_clk_100m. At reset dsp_rx_en=0 and dsp_tx_en=0 so all
// legacy AXI-DMA paths operate unchanged.

`timescale 1ns/1ps

module kria_dsp_suite (
    input  wire        clk,
    input  wire        rst,

    // Synchronized pl_clk_100m CSR interface (0x40 .. 0x7C)
    input  wire        csr_wr_en,
    input  wire [7:0]  csr_wr_addr,
    input  wire [31:0] csr_wr_wdata,
    input  wire [7:0]  csr_rd_addr,
    output reg  [31:0] csr_rd_rdata,

    // Non-intrusive RX stream tap (m_axis_rx from u_fifo_rx2pl)
    input  wire        rx_tap_valid,
    input  wire        rx_tap_ready,
    input  wire        rx_tap_last,
    input  wire [7:0]  rx_tap_tid,
    input  wire [63:0] rx_tap_data,

    // Optional TX Master Stream muxed ahead of u_fifo_pl2tx when dsp_tx_en=1
    output wire        dsp_tx_en,
    output wire [63:0] tx_axis_tdata,
    output wire        tx_axis_tvalid,
    input  wire        tx_axis_tready,
    output wire        tx_axis_tlast,
    output wire [7:0]  tx_axis_tid,
    output wire [15:0] tx_axis_tuser
);
    // CSR Registers (0x40..0x7C)
    reg [31:0] reg_dsp_ctrl;      // 0x40: [0]dsp_rx_en, [1]dsp_tx_en, [3:2]src_sel(0=01,1=05,2=04),
                                  //       [6:4]ch_mode, [7]adsb_en, [8]radar_en, [9]radar_win_en, [12:10]tx_mode
    reg [31:0] reg_ch_nco_ftw;    // 0x44
    reg [31:0] reg_ch_decim;      // 0x48: [15:0]cic_decim, [21:16]cic_shift, [31:24]fir_decim
    reg [31:0] reg_ch_demod_cfg;  // 0x4C: [15:0]deemph_alpha, [31:16]ctcss_coeff
    reg [31:0] reg_ch_pilot_ftw;  // 0x50
    reg [31:0] reg_ch_ctcss_cfg;  // 0x54: [15:0]ctcss_n, [31:16]rds_sym_samps
    reg [31:0] reg_ch_ctcss_thr;  // 0x58
    reg [31:0] reg_adsb_cfg;      // 0x64: [7:0]chip_osr, [23:8]min_hi_sum
    reg [31:0] reg_tx_car_ftw;    // 0x70
    reg [31:0] reg_tx_tone_ftw;   // 0x74
    reg [31:0] reg_tx_cfg;        // 0x78: [15:0]mod_param, [31:16]amp_scale
    reg [15:0] reg_radar_alpha;   // 0x7C write [15:0] cfar_alpha_q8

    wire       dsp_rx_en   = reg_dsp_ctrl[0];
    assign     dsp_tx_en   = reg_dsp_ctrl[1];
    wire [1:0] src_sid_sel = reg_dsp_ctrl[3:2];
    wire [2:0] ch_mode     = reg_dsp_ctrl[6:4];
    wire       adsb_en     = reg_dsp_ctrl[7];
    wire       radar_en    = reg_dsp_ctrl[8];
    wire       radar_win   = reg_dsp_ctrl[9];
    wire [2:0] tx_mode     = reg_dsp_ctrl[12:10];

    wire [7:0] target_tid = (src_sid_sel == 2'd0) ? 8'h01 :
                            (src_sid_sel == 2'd1) ? 8'h05 : 8'h04;

    // -------------------------------------------------------------------------
    // Unpack 64-bit beat {Q1, I1, Q0, I0} -> two consecutive 16-bit IQ samples
    // -------------------------------------------------------------------------
    reg               iq_valid;
    reg signed [15:0] iq_i, iq_q;
    reg               pend_half;
    reg signed [15:0] pend_i1, pend_q1;
    wire              beat_hit = dsp_rx_en && rx_tap_valid && rx_tap_ready && (rx_tap_tid == target_tid);

    always @(posedge clk) begin
        if (rst || !dsp_rx_en) begin
            iq_valid  <= 1'b0;
            iq_i      <= 16'sd0;
            iq_q      <= 16'sd0;
            pend_half <= 1'b0;
            pend_i1   <= 16'sd0;
            pend_q1   <= 16'sd0;
        end else begin
            iq_valid <= 1'b0;
            if (pend_half) begin
                iq_valid  <= 1'b1;
                iq_i      <= pend_i1;
                iq_q      <= pend_q1;
                pend_half <= 1'b0;
            end else if (beat_hit) begin
                iq_valid  <= 1'b1;
                iq_i      <= rx_tap_data[15:0];
                iq_q      <= rx_tap_data[31:16];
                pend_i1   <= rx_tap_data[47:32];
                pend_q1   <= rx_tap_data[63:48];
                pend_half <= 1'b1;
            end
        end
    end

    // -------------------------------------------------------------------------
    // Sub-modules: Channel RX, ADS-B RX, TX Mod, Radar Range-Doppler CFAR
    // -------------------------------------------------------------------------
    wire               mon_audio_valid;
    wire signed [15:0] mon_audio_l, mon_audio_r, mon_audio_mono;
    wire               mon_pilot_locked, mon_ctcss_valid, mon_ctcss_det;
    wire [31:0]        mon_ctcss_pwr;
    wire               mon_rds_valid, mon_rds_bit;

    kria_channel_rx u_ch_rx (
        .clk               (clk),
        .rst               (rst || !dsp_rx_en),
        .in_valid          (iq_valid && !adsb_en && !radar_en),
        .in_i              (iq_i),
        .in_q              (iq_q),
        .cfg_mode          (ch_mode),
        .cfg_nco_ftw       (reg_ch_nco_ftw),
        .cfg_cic_decim     (reg_ch_decim[15:0]),
        .cfg_cic_shift     (reg_ch_decim[21:16]),
        .cfg_fir_decim     (reg_ch_decim[31:24]),
        .cfg_deemph_alpha  (reg_ch_demod_cfg[15:0]),
        .cfg_pilot_ftw     (reg_ch_pilot_ftw),
        .cfg_ctcss_coeff   (reg_ch_demod_cfg[31:16]),
        .cfg_ctcss_n       (reg_ch_ctcss_cfg[15:0]),
        .cfg_ctcss_thresh  (reg_ch_ctcss_thr),
        .cfg_rds_sym_samps (reg_ch_ctcss_cfg[31:16]),
        .audio_valid       (mon_audio_valid),
        .audio_l           (mon_audio_l),
        .audio_r           (mon_audio_r),
        .audio_mono        (mon_audio_mono),
        .pilot_locked      (mon_pilot_locked),
        .ctcss_valid       (mon_ctcss_valid),
        .ctcss_detected    (mon_ctcss_det),
        .ctcss_power       (mon_ctcss_pwr),
        .rds_bit_valid     (mon_rds_valid),
        .rds_bit           (mon_rds_bit)
    );

    wire         mon_adsb_valid, mon_adsb_crc_ok;
    wire [111:0] mon_adsb_data;
    wire [15:0]  mon_adsb_snr;
    wire [31:0]  adsb_pre_cnt, adsb_ok_cnt, adsb_err_cnt;

    kria_adsb_rx u_adsb_rx (
        .clk            (clk),
        .rst            (rst || !adsb_en),
        .in_valid       (iq_valid && adsb_en),
        .in_i           (iq_i),
        .in_q           (iq_q),
        .cfg_chip_osr   (reg_adsb_cfg[7:0]),
        .cfg_min_hi_sum (reg_adsb_cfg[23:8]),
        .msg_valid      (mon_adsb_valid),
        .msg_crc_ok     (mon_adsb_crc_ok),
        .msg_data       (mon_adsb_data),
        .msg_snr_est    (mon_adsb_snr),
        .preamble_cnt   (adsb_pre_cnt),
        .crc_ok_cnt     (adsb_ok_cnt),
        .crc_err_cnt    (adsb_err_cnt)
    );

    kria_tx_mod #(.STREAM_ID(8'h12)) u_tx_mod (
        .clk             (clk),
        .rst             (rst),
        .en              (dsp_tx_en),
        .cfg_mode        (tx_mode),
        .cfg_carrier_ftw (reg_tx_car_ftw),
        .cfg_tone_ftw    (reg_tx_tone_ftw),
        .cfg_mod_param   (reg_tx_cfg[15:0]),
        .cfg_amp_scale   (reg_tx_cfg[31:16]),
        .cfg_samp_div    (16'd3), // 25 MSPS @ 100 MHz
        .cfg_pkt_words   (16'd32),
        .ext_aud_en      (1'b0),
        .ext_aud_valid   (1'b0),
        .ext_aud_sample  (16'sd0),
        .iq_valid        (),
        .iq_i            (),
        .iq_q            (),
        .m_axis_tdata    (tx_axis_tdata),
        .m_axis_tvalid   (tx_axis_tvalid),
        .m_axis_tready   (tx_axis_tready),
        .m_axis_tlast    (tx_axis_tlast),
        .m_axis_tid      (tx_axis_tid),
        .m_axis_tuser    (tx_axis_tuser)
    );

    wire        mon_rd_valid, mon_rd_det, mon_cpi_done;
    wire [5:0]  mon_rd_rbin, mon_peak_rbin;
    wire [3:0]  mon_rd_dbin, mon_peak_dbin;
    wire [31:0] mon_rd_pwr, mon_peak_pwr;
    wire [15:0] mon_cpi_det_cnt;

    kria_radar_proc #(.RANGE_N(64), .DOPPLER_M(16)) u_radar_proc (
        .clk               (clk),
        .rst               (rst || !radar_en),
        .in_valid          (iq_valid && radar_en),
        .in_ready          (),
        .in_i              (iq_i),
        .in_q              (iq_q),
        .cpi_sync_start    (1'b0),
        .cfg_win_en        (radar_win),
        .cfg_cfar_alpha_q8 (reg_radar_alpha),
        .cfg_cfar_min_pwr  (32'd20000),
        .rd_out_valid      (mon_rd_valid),
        .rd_out_rbin       (mon_rd_rbin),
        .rd_out_dbin       (mon_rd_dbin),
        .rd_out_pwr        (mon_rd_pwr),
        .rd_out_det        (mon_rd_det),
        .cpi_done_pulse    (mon_cpi_done),
        .cpi_det_cnt       (mon_cpi_det_cnt),
        .peak_rbin         (mon_peak_rbin),
        .peak_dbin         (mon_peak_dbin),
        .peak_pwr          (mon_peak_pwr)
    );

    // Status latches & telemetry counters
    reg signed [15:0] lat_aud_l, lat_aud_r;
    reg               lat_ctcss_det;
    reg [15:0]        aud_cnt, rds_cnt;
    reg [111:0]       lat_adsb_msg;

    always @(posedge clk) begin
        if (rst) begin
            reg_dsp_ctrl     <= 32'd0;
            reg_ch_nco_ftw   <= 32'd0;
            reg_ch_decim     <= 32'h0000_0001;
            reg_ch_demod_cfg <= 32'h7FE7_3000;
            reg_ch_pilot_ftw <= 32'd0;
            reg_ch_ctcss_cfg <= 32'h00CA_0140;
            reg_ch_ctcss_thr <= 32'd2000;
            reg_adsb_cfg     <= 32'h0FA0_02;
            reg_tx_car_ftw   <= 32'd0;
            reg_tx_tone_ftw  <= 32'd0;
            reg_tx_cfg       <= 32'h6000_4000;
            reg_radar_alpha  <= 16'd1536;
            lat_aud_l        <= 16'sd0;
            lat_aud_r        <= 16'sd0;
            lat_ctcss_det    <= 1'b0;
            aud_cnt          <= 16'd0;
            rds_cnt          <= 16'd0;
            lat_adsb_msg     <= 112'd0;
        end else begin
            if (mon_audio_valid) begin
                lat_aud_l <= mon_audio_l;
                lat_aud_r <= mon_audio_r;
                aud_cnt   <= aud_cnt + 16'd1;
            end
            if (mon_ctcss_valid)
                lat_ctcss_det <= mon_ctcss_det;
            if (mon_rds_valid)
                rds_cnt <= rds_cnt + 16'd1;
            if (mon_adsb_valid && mon_adsb_crc_ok)
                lat_adsb_msg <= mon_adsb_data;

            if (csr_wr_en) begin
                case (csr_wr_addr[7:2])
                    6'h10: reg_dsp_ctrl     <= csr_wr_wdata;
                    6'h11: reg_ch_nco_ftw   <= csr_wr_wdata;
                    6'h12: reg_ch_decim     <= csr_wr_wdata;
                    6'h13: reg_ch_demod_cfg <= csr_wr_wdata;
                    6'h14: reg_ch_pilot_ftw <= csr_wr_wdata;
                    6'h15: reg_ch_ctcss_cfg <= csr_wr_wdata;
                    6'h16: reg_ch_ctcss_thr <= csr_wr_wdata;
                    6'h19: reg_adsb_cfg     <= csr_wr_wdata;
                    6'h1C: reg_tx_car_ftw   <= csr_wr_wdata;
                    6'h1D: reg_tx_tone_ftw  <= csr_wr_wdata;
                    6'h1E: reg_tx_cfg       <= csr_wr_wdata;
                    6'h1F: reg_radar_alpha  <= csr_wr_wdata[15:0];
                    default: ;
                endcase
            end
        end
    end

    always @* begin
        case (csr_rd_addr[7:2])
            6'h10: csr_rd_rdata = reg_dsp_ctrl;
            6'h11: csr_rd_rdata = reg_ch_nco_ftw;
            6'h12: csr_rd_rdata = reg_ch_decim;
            6'h13: csr_rd_rdata = reg_ch_demod_cfg;
            6'h14: csr_rd_rdata = reg_ch_pilot_ftw;
            6'h15: csr_rd_rdata = reg_ch_ctcss_cfg;
            6'h16: csr_rd_rdata = reg_ch_ctcss_thr;
            6'h17: csr_rd_rdata = {lat_aud_r, lat_aud_l};
            6'h18: csr_rd_rdata = {aud_cnt, rds_cnt[7:0], 6'd0, lat_ctcss_det, mon_pilot_locked};
            6'h19: csr_rd_rdata = reg_adsb_cfg;
            6'h1A: csr_rd_rdata = {adsb_err_cnt[15:0], adsb_ok_cnt[15:0]};
            6'h1B: csr_rd_rdata = lat_adsb_msg[31:0];
            6'h1C: csr_rd_rdata = reg_tx_car_ftw;
            6'h1D: csr_rd_rdata = reg_tx_tone_ftw;
            6'h1E: csr_rd_rdata = reg_tx_cfg;
            6'h1F: csr_rd_rdata = {6'd0, mon_cpi_det_cnt, mon_peak_dbin, mon_peak_rbin};
            default: csr_rd_rdata = 32'd0;
        endcase
    end
endmodule
