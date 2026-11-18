`timescale 1ns / 1ps
// kria_doa: direction finding for a KrakenSDR (five coherent RTL-SDR channels on USB) in the K26's PL.
//
// The A53s read the five channels over USB, align them to the sample from the noise source's bursts and estimate
// each channel's complex gain (sw/kria/sdr, `kraken`). What arrives here is the aligned stream, one snapshot of five
// signed 8-bit I/Q pairs per two 64-bit beats, from an AXI DMA (MM2S). The block:
//
//  1. multiplies each channel by its calibration weight w_k (complex Q2.14), y_k = (w_k x_k) >>> 10;
//  2. accumulates the spatial covariance R_ij = sum y_i conj(y_j) over 2^N_LOG2 snapshots (the 15 entries with
//     i <= j, 48 bits each);
//  3. then scans 360 bearings: P(m) = sum_i R_ii + 2 sum_{i<j} Re(b_ij(m) R_ij), with b_ij(m) = conj(a_i(m)) a_j(m)
//     the steering cross-products, written by the A53 for the array's geometry and the frequency (Q1.14). That is
//     the Bartlett beamformer a^H R a, one bearing per clock.
//
// The A53s read R back for MUSIC (an eigendecomposition of a 5 x 5 matrix, cheap on a core) and the Bartlett
// spectrum for the display. At 2.4 MS/s the stream is 4.8 M beats/s; the block takes one beat per clock.
//
// Stream format (s_axis, 64 bits): beat 0 holds channels 0-3, beat 1 channel 4 in bits [15:0]; channel k of a beat
// at bits [16k+15:16k], I in the low byte, Q in the high byte. tlast restarts the beat count.
//
// Registers (AXI4-Lite, 32-bit, byte addresses, 16-bit address space):
//   0x0000 ID       "DOA1"
//   0x0004 CTRL     W: [0] start a CPI (clears R and the count), [1] scan when the CPI ends, [2] scan the R now
//                   held (after a CPI run with [1] clear, once SHIFT is set from R's diagonal)
//   0x0008 STATUS   [0] accumulating, [1] scanning, [2] done (R and P valid; cleared by start), [31:16] CPIs done
//   0x000C N_LOG2   [4:0] snapshots per CPI = 2^N_LOG2, 1 to 16
//   0x0010 SHIFT    [5:0] R is shifted right by SHIFT and saturated to 25 bits before the scan
//   0x0014 DROPPED  beats that arrived while no CPI was running (RO, wraps)
//   0x0020 + 4k     W_k, k = 0..4: [15:0] real, [31:16] imaginary, Q2.14 (16384 = 1)
//   0x0100 + 16e    R entry e = 0..14 in the order (0,0) (0,1) .. (0,4) (1,1) .. (4,4): +0 real [31:0], +4 real
//                   [47:32] sign-extended, +8 imaginary [31:0], +12 imaginary [47:32]
//   0x0800 + 4m     P(m), m = 0..359, signed 32 bits (RO)
//   0x8000 + 64m + 4p  b_p(m), p = 0..9 in the order (0,1) (0,2) (0,3) (0,4) (1,2) (1,3) (1,4) (2,3) (2,4) (3,4):
//                   [15:0] real, [31:16] imaginary, Q1.14 (WO)
module kria_doa_axi (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 clk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axi:s_axis, ASSOCIATED_RESET resetn" *)
    input  wire        clk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 resetn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input  wire        resetn,

    (* X_INTERFACE_PARAMETER = "PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 16" *)
    input  wire [15:0] s_axi_awaddr,
    input  wire        s_axi_awvalid,
    output reg         s_axi_awready,
    input  wire [31:0] s_axi_wdata,
    input  wire [3:0]  s_axi_wstrb,
    input  wire        s_axi_wvalid,
    output reg         s_axi_wready,
    output reg  [1:0]  s_axi_bresp,
    output reg         s_axi_bvalid,
    input  wire        s_axi_bready,
    input  wire [15:0] s_axi_araddr,
    input  wire        s_axi_arvalid,
    output reg         s_axi_arready,
    output reg  [31:0] s_axi_rdata,
    output reg  [1:0]  s_axi_rresp,
    output reg         s_axi_rvalid,
    input  wire        s_axi_rready,

    input  wire [63:0] s_axis_tdata,
    input  wire        s_axis_tvalid,
    output wire        s_axis_tready,
    input  wire        s_axis_tlast
);
    localparam [31:0] ID_DOA1 = 32'h444F_4131;   // "DOA1"
    localparam integer NA = 360;

    // ------------------------------------------------------------------ configuration
    reg [4:0]  n_log2;
    reg [5:0]  shift;
    reg [31:0] w_reg [0:4];
    reg        scan_en;
    reg [31:0] dropped;
    reg [15:0] cpi_count;

    // ------------------------------------------------------------------ CPI state
    reg        acc_run, scanning, done;
    reg [16:0] snap_cnt;
    reg        beat_ph;
    reg [63:0] beat0;
    reg        start_req, rescan_req;

    assign s_axis_tready = 1'b1;
    wire beat_ok = s_axis_tvalid && acc_run;

    // ------------------------------------------------------------------ stage 1: calibration y_k = (w_k x_k) >>> 10
    reg               s1_v;
    reg signed [15:0] s1_yr [0:4];
    reg signed [15:0] s1_yi [0:4];
    integer k;
    always @(posedge clk) begin
        s1_v <= 1'b0;
        if (!resetn || start_req) begin
            beat_ph <= 1'b0;
        end else if (beat_ok) begin
            if (!beat_ph) begin
                beat0 <= s_axis_tdata;
                beat_ph <= !s_axis_tlast;
            end else begin
                beat_ph <= 1'b0;
                s1_v <= 1'b1;
                for (k = 0; k < 5; k = k + 1) begin : cal
                    reg signed [7:0]  xr, xi;
                    reg signed [15:0] wr, wi;
                    reg signed [25:0] pr, pi;
                    if (k < 4) begin
                        xr = beat0[16*k +: 8]; xi = beat0[16*k+8 +: 8];
                    end else begin
                        xr = s_axis_tdata[7:0]; xi = s_axis_tdata[15:8];
                    end
                    wr = w_reg[k][15:0]; wi = w_reg[k][31:16];
                    pr = wr * xr - wi * xi;
                    pi = wr * xi + wi * xr;
                    s1_yr[k] <= pr >>> 10;
                    s1_yi[k] <= pi >>> 10;
                end
            end
        end
    end

    // ------------------------------------------------------------------ stage 2: products y_i conj(y_j)
    // (yr_i + j yi_i)(yr_j - j yi_j) = (yr_i yr_j + yi_i yi_j) + j (yi_i yr_j - yr_i yi_j)
    reg               s2_v;
    reg signed [32:0] s2_re [0:14];
    reg signed [32:0] s2_im [0:14];
    integer i, j, e;
    always @(posedge clk) begin
        s2_v <= s1_v;
        if (s1_v) begin
            e = 0;
            for (i = 0; i < 5; i = i + 1)
                for (j = i; j < 5; j = j + 1) begin
                    s2_re[e] <= s1_yr[i] * s1_yr[j] + s1_yi[i] * s1_yi[j];
`ifdef MUTATE_DOA_NO_CONJ
                    s2_im[e] <= s1_yi[i] * s1_yr[j] + s1_yr[i] * s1_yi[j];   // MUTATION: y_j not conjugated
`else
                    s2_im[e] <= s1_yi[i] * s1_yr[j] - s1_yr[i] * s1_yi[j];
`endif
                    e = e + 1;
                end
        end
    end

    // ------------------------------------------------------------------ stage 3: accumulation
    reg signed [47:0] r_re [0:14];
    reg signed [47:0] r_im [0:14];
    wire [16:0] n_snap = 17'd1 << n_log2;
    reg         acc_end;     // the last snapshot of the CPI has been counted; wait for it to drain
    reg [2:0]   drain;
    always @(posedge clk) begin
        if (!resetn) begin
            acc_run <= 1'b0; snap_cnt <= 17'd0; acc_end <= 1'b0; drain <= 3'd0;
        end else if (start_req) begin
            acc_run <= 1'b1; snap_cnt <= 17'd0; acc_end <= 1'b0; drain <= 3'd0;
            for (e = 0; e < 15; e = e + 1) begin
                r_re[e] <= 48'sd0; r_im[e] <= 48'sd0;
            end
        end else begin
            if (beat_ok && beat_ph) begin
                snap_cnt <= snap_cnt + 1'b1;
                if (snap_cnt + 1'b1 == n_snap) begin
                    acc_run <= 1'b0; acc_end <= 1'b1; drain <= 3'd3;
                end
            end
            if (s2_v)
                for (e = 0; e < 15; e = e + 1) begin
                    r_re[e] <= r_re[e] + s2_re[e];
                    r_im[e] <= r_im[e] + s2_im[e];
                end
            if (acc_end) begin
                if (drain != 0) drain <= drain - 1'b1;
                else acc_end <= 1'b0;
            end
        end
    end
    wire acc_done = acc_end && (drain == 0);

    // ------------------------------------------------------------------ steering table: 10 memories of 512 x 32
    reg [8:0]  sc_m;                  // bearing being read by the scan
    reg [31:0] bq [0:9];              // the steering table at sc_m, one clock later
    (* ram_style = "block" *) reg [31:0] btab0 [0:511];
    (* ram_style = "block" *) reg [31:0] btab1 [0:511];
    (* ram_style = "block" *) reg [31:0] btab2 [0:511];
    (* ram_style = "block" *) reg [31:0] btab3 [0:511];
    (* ram_style = "block" *) reg [31:0] btab4 [0:511];
    (* ram_style = "block" *) reg [31:0] btab5 [0:511];
    (* ram_style = "block" *) reg [31:0] btab6 [0:511];
    (* ram_style = "block" *) reg [31:0] btab7 [0:511];
    (* ram_style = "block" *) reg [31:0] btab8 [0:511];
    (* ram_style = "block" *) reg [31:0] btab9 [0:511];
    reg        tab_we;
    reg [3:0]  tab_p;
    reg [8:0]  tab_a;
    reg [31:0] tab_d;
    always @(posedge clk) begin
        if (tab_we) begin
            case (tab_p)
                4'd0: btab0[tab_a] <= tab_d; 4'd1: btab1[tab_a] <= tab_d;
                4'd2: btab2[tab_a] <= tab_d; 4'd3: btab3[tab_a] <= tab_d;
                4'd4: btab4[tab_a] <= tab_d; 4'd5: btab5[tab_a] <= tab_d;
                4'd6: btab6[tab_a] <= tab_d; 4'd7: btab7[tab_a] <= tab_d;
                4'd8: btab8[tab_a] <= tab_d; 4'd9: btab9[tab_a] <= tab_d;
                default: ;
            endcase
        end
        // reads every clock at the bearing being issued (block RAM with a registered output); the scan uses them
        // only while it runs
        bq[0] <= btab0[sc_m]; bq[1] <= btab1[sc_m]; bq[2] <= btab2[sc_m]; bq[3] <= btab3[sc_m];
        bq[4] <= btab4[sc_m]; bq[5] <= btab5[sc_m]; bq[6] <= btab6[sc_m]; bq[7] <= btab7[sc_m];
        bq[8] <= btab8[sc_m]; bq[9] <= btab9[sc_m];
    end

    // ------------------------------------------------------------------ scan
    // R scaled once per scan: R >>> SHIFT, saturated to 25 bits
    function automatic signed [24:0] sat25;
        input signed [47:0] v;
        input [5:0] sh;
        reg signed [47:0] s;
        begin
            s = v >>> sh;
            if (s > 48'sd16777215)       sat25 = 25'sd16777215;
            else if (s < -48'sd16777216) sat25 = -25'sd16777216;
            else                         sat25 = s[24:0];
        end
    endfunction

    reg signed [24:0] rs_re [0:9];    // off-diagonal pairs in table order
    reg signed [24:0] rs_im [0:9];
    reg signed [27:0] rs_tr;          // trace, sum of 5 diagonal entries
    reg        sc_rd;                 // a read was issued this clock
    reg        sc_load;               // scaling R this clock
    // pipeline: t0 read issued, t1 table data, t2 products, t3 pair sums, t4 total, t5 write
    reg        p1_v, p2_v, p3_v, p4_v;
    reg [8:0]  p1_m, p2_m, p3_m, p4_m;
    reg signed [41:0] p2_prod [0:9];
    reg signed [44:0] p3_sum_a, p3_sum_b;
    reg signed [45:0] p4_tot;
    reg [31:0] spec [0:511];
    reg        spec_we;
    reg [8:0]  spec_a;
    reg [31:0] spec_d;
    integer p;

    // pair p -> covariance entry index (order (0,0) (0,1) .. (0,4) (1,1) ..)
    function automatic [3:0] pair_e;
        input [3:0] pp;
        begin
            case (pp)
                4'd0: pair_e = 4'd1;  4'd1: pair_e = 4'd2;  4'd2: pair_e = 4'd3;  4'd3: pair_e = 4'd4;
                4'd4: pair_e = 4'd6;  4'd5: pair_e = 4'd7;  4'd6: pair_e = 4'd8;  4'd7: pair_e = 4'd10;
                4'd8: pair_e = 4'd11; default: pair_e = 4'd13;
            endcase
        end
    endfunction

    always @(posedge clk) begin
        spec_we <= 1'b0;
        if (spec_we) spec[spec_a] <= spec_d;
        if (!resetn) begin
            scanning <= 1'b0; done <= 1'b0; sc_rd <= 1'b0; sc_load <= 1'b0; cpi_count <= 16'd0;
            p1_v <= 1'b0; p2_v <= 1'b0; p3_v <= 1'b0; p4_v <= 1'b0;
        end else begin
            if (start_req || rescan_req) done <= 1'b0;
            sc_rd <= 1'b0;
            sc_load <= rescan_req && !acc_run && !scanning;
            if (acc_done) begin
                if (scan_en) begin
                    sc_load <= 1'b1;
                end else begin
                    done <= 1'b1; cpi_count <= cpi_count + 1'b1;
                end
            end
            if (sc_load) begin
                for (p = 0; p < 10; p = p + 1) begin
                    rs_re[p] <= sat25(r_re[pair_e(p)], shift);
                    rs_im[p] <= sat25(r_im[pair_e(p)], shift);
                end
                rs_tr <= sat25(r_re[0], shift) + sat25(r_re[5], shift) + sat25(r_re[9], shift)
                       + sat25(r_re[12], shift) + sat25(r_re[14], shift);
                scanning <= 1'b1; sc_m <= 9'd0;
            end
            // issue one table read per clock
            if (scanning && !sc_load) begin
                p1_m <= sc_m;
                if (sc_m == NA - 1) scanning <= 1'b0;
                else sc_m <= sc_m + 1'b1;
            end
            p1_v <= scanning && !sc_load;
            // products Re(b R) = b_re R_re - b_im R_im
            p2_v <= p1_v; p2_m <= p1_m;
            for (p = 0; p < 10; p = p + 1)
                p2_prod[p] <= $signed(bq[p][15:0]) * rs_re[p] - $signed(bq[p][31:16]) * rs_im[p];
            p3_v <= p2_v; p3_m <= p2_m;
            p3_sum_a <= p2_prod[0] + p2_prod[1] + p2_prod[2] + p2_prod[3] + p2_prod[4];
            p3_sum_b <= p2_prod[5] + p2_prod[6] + p2_prod[7] + p2_prod[8] + p2_prod[9];
            p4_v <= p3_v; p4_m <= p3_m;
            p4_tot <= ((p3_sum_a + p3_sum_b) <<< 1) + ($signed({rs_tr, 14'd0}));
            if (p4_v) begin
                spec_we <= 1'b1; spec_a <= p4_m;
                spec_d <= (p4_tot >>> 14);
                if (p4_m == NA - 1) begin
                    done <= 1'b1; cpi_count <= cpi_count + 1'b1;
                end
            end
        end
    end

    // ------------------------------------------------------------------ AXI4-Lite
    reg        aw_hold, w_hold;
    reg [15:0] aw_addr;
    reg [31:0] w_data;
    always @(posedge clk) begin
        tab_we <= 1'b0;
        start_req <= 1'b0;
        rescan_req <= 1'b0;
        if (!resetn) begin
            s_axi_awready <= 1'b0; s_axi_wready <= 1'b0; s_axi_bvalid <= 1'b0; s_axi_bresp <= 2'b00;
            aw_hold <= 1'b0; w_hold <= 1'b0;
            n_log2 <= 5'd12; shift <= 6'd0; scan_en <= 1'b1; dropped <= 32'd0;
            w_reg[0] <= 32'h0000_4000; w_reg[1] <= 32'h0000_4000; w_reg[2] <= 32'h0000_4000;
            w_reg[3] <= 32'h0000_4000; w_reg[4] <= 32'h0000_4000;
        end else begin
            if (s_axis_tvalid && !acc_run) dropped <= dropped + 1'b1;
            s_axi_awready <= 1'b0; s_axi_wready <= 1'b0;
            if (s_axi_awvalid && !aw_hold && !s_axi_awready) begin
                s_axi_awready <= 1'b1; aw_hold <= 1'b1; aw_addr <= s_axi_awaddr;
            end
            if (s_axi_wvalid && !w_hold && !s_axi_wready) begin
                s_axi_wready <= 1'b1; w_hold <= 1'b1; w_data <= s_axi_wdata;
            end
            if (aw_hold && w_hold && !s_axi_bvalid) begin
                aw_hold <= 1'b0; w_hold <= 1'b0; s_axi_bvalid <= 1'b1; s_axi_bresp <= 2'b00;
                if (aw_addr[15]) begin
                    tab_we <= 1'b1; tab_a <= aw_addr[14:6]; tab_p <= aw_addr[5:2]; tab_d <= w_data;
                end else begin
                    case (aw_addr[11:0])
                        12'h004: begin
                            if (w_data[0]) start_req <= 1'b1;
                            if (w_data[2]) rescan_req <= 1'b1;
                            scan_en <= w_data[1];
                        end
                        12'h00C: n_log2 <= (w_data[4:0] == 0) ? 5'd1 : (w_data[4:0] > 16) ? 5'd16 : w_data[4:0];
                        12'h010: shift <= w_data[5:0];
                        12'h020: w_reg[0] <= w_data;
                        12'h024: w_reg[1] <= w_data;
                        12'h028: w_reg[2] <= w_data;
                        12'h02C: w_reg[3] <= w_data;
                        12'h030: w_reg[4] <= w_data;
                        default: ;
                    endcase
                end
            end
            if (s_axi_bvalid && s_axi_bready) s_axi_bvalid <= 1'b0;
        end
    end

    reg        ar_pend;
    reg [15:0] ar_addr;
    reg [31:0] spec_q;
    always @(posedge clk) spec_q <= spec[ar_addr[10:2]];
    reg [1:0]  ar_wait;
    always @(posedge clk) begin
        if (!resetn) begin
            s_axi_arready <= 1'b0; s_axi_rvalid <= 1'b0; s_axi_rresp <= 2'b00; ar_pend <= 1'b0; ar_wait <= 2'd0;
        end else begin
            s_axi_arready <= 1'b0;
            if (s_axi_arvalid && !ar_pend && !s_axi_rvalid && !s_axi_arready) begin
                s_axi_arready <= 1'b1; ar_pend <= 1'b1; ar_addr <= s_axi_araddr; ar_wait <= 2'd2;
            end
            if (ar_pend) begin
                if (ar_wait != 0) ar_wait <= ar_wait - 1'b1;
                else begin
                    ar_pend <= 1'b0; s_axi_rvalid <= 1'b1; s_axi_rresp <= 2'b00;
                    if (ar_addr[15:11] == 5'b00001) begin
                        s_axi_rdata <= spec_q;
                    end else if (ar_addr[15:8] == 8'h01) begin
                        case (ar_addr[3:2])
                            2'd0: s_axi_rdata <= r_re[ar_addr[7:4]][31:0];
                            2'd1: s_axi_rdata <= {{16{r_re[ar_addr[7:4]][47]}}, r_re[ar_addr[7:4]][47:32]};
                            2'd2: s_axi_rdata <= r_im[ar_addr[7:4]][31:0];
                            default: s_axi_rdata <= {{16{r_im[ar_addr[7:4]][47]}}, r_im[ar_addr[7:4]][47:32]};
                        endcase
                    end else begin
                        case (ar_addr[11:0])
                            12'h000: s_axi_rdata <= ID_DOA1;
                            12'h004: s_axi_rdata <= {30'd0, scan_en, 1'b0};
                            12'h008: s_axi_rdata <= {cpi_count, 13'd0, done, scanning, acc_run};
                            12'h00C: s_axi_rdata <= {27'd0, n_log2};
                            12'h010: s_axi_rdata <= {26'd0, shift};
                            12'h014: s_axi_rdata <= dropped;
                            12'h020: s_axi_rdata <= w_reg[0];
                            12'h024: s_axi_rdata <= w_reg[1];
                            12'h028: s_axi_rdata <= w_reg[2];
                            12'h02C: s_axi_rdata <= w_reg[3];
                            12'h030: s_axi_rdata <= w_reg[4];
                            default: s_axi_rdata <= 32'd0;
                        endcase
                    end
                end
            end
            if (s_axi_rvalid && s_axi_rready) s_axi_rvalid <= 1'b0;
        end
    end
endmodule
