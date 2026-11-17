`timescale 1ns / 1ps
// kria_sweep: a HackRF Pro's sweep mode, processed in the K26's PL.
//
// In sweep mode the HackRF retunes every block and sends 16,384-byte blocks over USB, each starting with 0x7F
// 0x7F and the block's frequency as a little-endian 64-bit number, then signed 8-bit I/Q at 20 MS/s
// (host/hackrf-tools/src/hackrf_sweep.c, firmware/hackrf_usb/usb_api_sweep.c). The LO sits 7.5 MHz above that
// frequency. The host program takes the last N samples of each block, applies a Hann window, runs an N-point FFT
// and keeps two quarter bands, [f, f + 5 MHz) from bins 1 + 5N/8 on and [f + 10, f + 15 MHz) from bins 1 + N/8
// on; the interleaved stepping (+5 MHz, +15 MHz alternately) fills the gaps.
//
// This block does the same for N = 256 (78.125 kHz bins), and averages: it transforms the last 2^NSEG_LOG2
// segments of 256 samples of the block (up to 16, 4,096 samples) and sums their powers bin by bin (Welch's method
// without overlap). One FFT of a noise-like signal (LTE, Wi-Fi, DVB-T) has a ragged spectrum, +/-5 dB from bin to
// bin; the sum of 8 is within +/-1.8 dB. A PC running hackrf_sweep keeps one FFT per block to save its CPU.
//
// Stream in (s_axis, 64 bits, from an AXI DMA MM2S): the USB transfers as received, 2,048 beats per block, byte 0
// of the block in bits [7:0] of its first beat. A block whose header is not 0x7F 0x7F is dropped and counted.
// Stream out (m_axis, 64 bits, to an AXI DMA S2MM): per block, one beat with the frequency, then 64 beats of two
// 32-bit powers each (bins 161 to 224, then 33 to 96, the lower bin in the low half), tlast on the last.
// A power is (sum over the segments of re^2 + im^2) >> PSHIFT, saturated to 32 bits.
//
// Timing: per segment 256 loads, 1,024 butterflies of 3 clocks and 128 power sums, 3,456 clocks; with 8 segments
// a block takes 30,000 clocks, 0.3 ms at 100 MHz, against the 0.82 ms between blocks of a HackRF Pro sweep
// (1,220 blocks/s). The input is held off (tready low) while a block is processed; the DMA's buffer absorbs it.
//
// Registers (AXI4-Lite, 32-bit, byte addresses, 12-bit address space):
//   0x000 ID        "SWP1"
//   0x004 STATUS    [0] busy (loading, transforming or sending)
//   0x008 BLOCKS    blocks processed (RO, wraps)
//   0x00C BAD       blocks dropped for their header (RO, wraps)
//   0x010 PSHIFT    [5:0], 3 at reset
//   0x014 NSEG_LOG2 [2:0], 0 to 4 (1 to 16 segments), 3 at reset
//   0x400 + 4i      window i = 0..255, Q1.15 in [15:0] (WO)
//   0x800 + 4k      twiddle W^k = exp(-j 2 pi k / 256), k = 0..127: [15:0] cos, [31:16] -sin, Q1.15 (WO)
// Software writes the window and the twiddles once at start; change NSEG_LOG2 and PSHIFT only between blocks.
module kria_sweep_axi (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 clk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axi:s_axis:m_axis, ASSOCIATED_RESET resetn" *)
    input  wire        clk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 resetn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input  wire        resetn,

    (* X_INTERFACE_PARAMETER = "PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 12" *)
    input  wire [11:0] s_axi_awaddr,
    input  wire        s_axi_awvalid,
    output reg         s_axi_awready,
    input  wire [31:0] s_axi_wdata,
    input  wire [3:0]  s_axi_wstrb,
    input  wire        s_axi_wvalid,
    output reg         s_axi_wready,
    output reg  [1:0]  s_axi_bresp,
    output reg         s_axi_bvalid,
    input  wire        s_axi_bready,
    input  wire [11:0] s_axi_araddr,
    input  wire        s_axi_arvalid,
    output reg         s_axi_arready,
    output reg  [31:0] s_axi_rdata,
    output reg  [1:0]  s_axi_rresp,
    output reg         s_axi_rvalid,
    input  wire        s_axi_rready,

    input  wire [63:0] s_axis_tdata,
    input  wire        s_axis_tvalid,
    output wire        s_axis_tready,
    input  wire        s_axis_tlast,

    output reg  [63:0] m_axis_tdata,
    output wire [7:0]  m_axis_tkeep,
    output reg         m_axis_tvalid,
    output reg         m_axis_tlast,
    input  wire        m_axis_tready
);
    localparam [31:0] ID_SWP1 = 32'h5357_5031;   // "SWP1"
    localparam integer DW = 22;                   // FFT data width

    // ------------------------------------------------------------------ tables (written by software)
    reg [15:0] win [0:255];
    reg [31:0] twd [0:127];
    reg        tw_we, wi_we;
    reg [7:0]  tab_a;
    reg [31:0] tab_d;
    always @(posedge clk) begin
        if (wi_we) win[tab_a] <= tab_d[15:0];
        if (tw_we) twd[tab_a[6:0]] <= tab_d;
    end

    reg [5:0]  pshift;
    reg [2:0]  nseg_log2;
    reg [31:0] blocks, bad;

    // ------------------------------------------------------------------ states
    localparam [2:0] S_RECV = 3'd0, S_LOAD = 3'd1, S_FFT = 3'd2, S_POW = 3'd3, S_OUT = 3'd4;
    reg [2:0]  state;
    reg [10:0] beat;          // beat index within the block
    reg [63:0] freq;
    reg        hdr_ok;
    // the block's last 1,024 beats (4,096 samples, 16 segments); segment s of 2^k starts at beat 1024 - 64 (2^k - s)
    (* ram_style = "block" *) reg [63:0] tail [0:1023];
    reg [63:0] tail_q;
    reg [9:0]  tail_ra;
    assign s_axis_tready = (state == S_RECV);
    assign m_axis_tkeep = 8'hFF;

    // FFT memory: 256 x (re, im)
    reg signed [DW-1:0] mre [0:255];
    reg signed [DW-1:0] mim [0:255];

    function automatic [7:0] bitrev8;
        input [7:0] v;
        integer b;
        begin
            for (b = 0; b < 8; b = b + 1) bitrev8[b] = v[7-b];
        end
    endfunction

    reg [4:0]  seg;           // segment being processed
    wire [4:0] nseg = 5'd1 << nseg_log2;
    // load: issue a tail read, then window and write
    reg [8:0]  ld_i;
    reg        ld_rd, ld_rd2; // a tail read was issued for sample ld_s; its data is in tail_q for ld_s2
    reg [7:0]  ld_s, ld_s2;
    // butterflies
    reg [2:0]  st;            // stage 0..7
    reg [6:0]  bf;            // butterfly 0..127
    reg [1:0]  ph;            // phase within a butterfly
    reg [7:0]  i0, i1;
    reg signed [DW-1:0] a_re, a_im;
    reg signed [15:0]   w_c, w_s;
    reg signed [DW-1:0] t_re, t_im;
    // power accumulators: pair j holds two bins
    reg [7:0]  pw_i;          // output pair index 0..63
    reg [47:0] acc_lo [0:63];
    reg [47:0] acc_hi [0:63];
    reg [6:0]  out_i;

    function automatic [47:0] pwr;
        input signed [DW-1:0] re, im;
        reg [2*DW:0] p;
        begin
            p = re * re + im * im;
            pwr = p;
        end
    endfunction

    function automatic [31:0] sat_sh;
        input [47:0] v;
        input [5:0]  sh;
        reg [47:0] q;
        begin
            q = v >> sh;
            sat_sh = (q > 48'hFFFF_FFFF) ? 32'hFFFF_FFFF : q[31:0];
        end
    endfunction

    // the bin of output pair j, half h: pairs 0-31 hold bins 161 + 2j and 162 + 2j; pairs 32-63 hold 33 + 2(j-32) ..
    function automatic [7:0] bin_of;
        input [5:0] j;
        input       h;
        begin
            if (j < 32) bin_of = 8'd161 + {j[4:0], 1'b0} + h;
            else        bin_of = 8'd33 + {j[4:0], 1'b0} + h;
        end
    endfunction

    wire [7:0] lo_bin = bin_of(pw_i[5:0], 1'b0);
    wire [7:0] hi_bin = bin_of(pw_i[5:0], 1'b1);

    always @(posedge clk) tail_q <= tail[tail_ra];

    always @(posedge clk) begin
        if (!resetn) begin
            state <= S_RECV; beat <= 11'd0; hdr_ok <= 1'b0; blocks <= 32'd0; bad <= 32'd0;
            m_axis_tvalid <= 1'b0; m_axis_tlast <= 1'b0; ld_rd <= 1'b0; ld_rd2 <= 1'b0;
        end else begin
            case (state)
            S_RECV: if (s_axis_tvalid) begin
                if (beat == 11'd0) begin
                    hdr_ok <= (s_axis_tdata[7:0] == 8'h7F) && (s_axis_tdata[15:8] == 8'h7F);
                    freq[47:0] <= s_axis_tdata[63:16];
                end
                if (beat == 11'd1) freq[63:48] <= s_axis_tdata[15:0];
                if (beat[10]) tail[beat[9:0]] <= s_axis_tdata;
                if (beat == 11'd2047) begin
                    beat <= 11'd0;
                    if (hdr_ok) begin
                        state <= S_LOAD; seg <= 5'd0; ld_i <= 9'd0; ld_rd <= 1'b0; ld_rd2 <= 1'b0;
                    end else bad <= bad + 1'b1;
                end else if (s_axis_tlast) begin
                    beat <= 11'd0;                       // a short block: start again at the next header
                end else beat <= beat + 1'b1;
            end
            S_LOAD: begin
                // sample i of the segment: tail beat (1024 - 64 (nseg - seg)) + i/4, lane i%4; windowed, written at
                // the bit-reversed address one clock after its read
                // pipeline: issue (tail_ra), memory (tail_q), write; two clocks from a read to its sample's write
                ld_s2 <= ld_s; ld_rd2 <= ld_rd;
                if (ld_rd2) begin
                    begin : ld
                        reg signed [7:0] xr, xi;
                        reg signed [16:0] wv;
                        reg signed [24:0] pr, pi;
                        xr = tail_q[16*ld_s2[1:0] +: 8];
                        xi = tail_q[16*ld_s2[1:0] + 8 +: 8];
                        wv = {1'b0, win[ld_s2]};
                        pr = xr * wv;
                        pi = xi * wv;
                        mre[bitrev8(ld_s2)] <= pr >>> 7;
                        mim[bitrev8(ld_s2)] <= pi >>> 7;
                    end
                end
                if (ld_i == 9'd256) begin
                    ld_rd <= 1'b0;
                    if (!ld_rd && !ld_rd2) begin
                        state <= S_FFT; st <= 3'd0; bf <= 7'd0; ph <= 2'd0;
                    end
                end else begin
                    tail_ra <= 10'd1024 - ({5'd0, nseg - seg} << 6) + ld_i[7:2];
                    ld_s <= ld_i[7:0];
                    ld_rd <= 1'b1;
                    ld_i <= ld_i + 1'b1;
                end
            end
            S_FFT: begin
                case (ph)
                2'd0: begin
                    // indices of butterfly bf in stage st: half = 2^st
                    begin : idx
                        reg [7:0] half, grp, pos;
                        half = 8'd1 << st;
                        pos  = {1'b0, bf} & (half - 1'b1);
                        grp  = {1'b0, bf} >> st;
                        i0 <= (grp << (st + 1)) | pos;
                        i1 <= ((grp << (st + 1)) | pos) + half;
                        w_c <= twd[(pos << (7 - st))][15:0];
                        w_s <= twd[(pos << (7 - st))][31:16];
                    end
                    ph <= 2'd1;
                end
                2'd1: begin
                    // t = W b, W = c + j s (s = -sin)
                    begin : mul
                        reg signed [DW-1:0] b_re, b_im;
                        reg signed [DW+16:0] tr, ti;
                        b_re = mre[i1]; b_im = mim[i1];
                        tr = w_c * b_re - w_s * b_im;
                        ti = w_c * b_im + w_s * b_re;
`ifdef MUTATE_SWEEP_TWIDDLE_CONJ
                        tr = w_c * b_re + w_s * b_im;   // MUTATION: conjugate twiddle mirrors the spectrum
                        ti = w_c * b_im - w_s * b_re;
`endif
                        t_re <= tr >>> 15;
                        t_im <= ti >>> 15;
                    end
                    a_re <= mre[i0]; a_im <= mim[i0];
                    ph <= 2'd2;
                end
                default: begin
                    // sums one bit wider, then halved: each stage scales by 1/2, the FFT by 1/256
                    begin : bfly
                        reg signed [DW:0] sr0, si0, sr1, si1;
                        sr0 = a_re + t_re; si0 = a_im + t_im;
                        sr1 = a_re - t_re; si1 = a_im - t_im;
                        mre[i0] <= sr0 >>> 1; mim[i0] <= si0 >>> 1;
                        mre[i1] <= sr1 >>> 1; mim[i1] <= si1 >>> 1;
                    end
                    ph <= 2'd0;
                    if (bf == 7'd127) begin
                        bf <= 7'd0;
                        if (st == 3'd7) begin
                            state <= S_POW; pw_i <= 8'd0;
                        end else st <= st + 1'b1;
                    end else bf <= bf + 1'b1;
                end
                endcase
            end
            S_POW: begin
                if (pw_i == 8'd64) begin
                    if (seg + 1'b1 == nseg) begin
                        state <= S_OUT; out_i <= 7'd0;
                        m_axis_tdata <= freq; m_axis_tvalid <= 1'b1; m_axis_tlast <= 1'b0;
                    end else begin
                        seg <= seg + 1'b1; state <= S_LOAD; ld_i <= 9'd0; ld_rd <= 1'b0; ld_rd2 <= 1'b0;
                    end
                end else begin
                    acc_lo[pw_i[5:0]] <= (seg == 0 ? 48'd0 : acc_lo[pw_i[5:0]]) + pwr(mre[lo_bin], mim[lo_bin]);
                    acc_hi[pw_i[5:0]] <= (seg == 0 ? 48'd0 : acc_hi[pw_i[5:0]]) + pwr(mre[hi_bin], mim[hi_bin]);
                    pw_i <= pw_i + 1'b1;
                end
            end
            S_OUT: if (m_axis_tready) begin
                if (out_i == 7'd64) begin
                    m_axis_tvalid <= 1'b0; m_axis_tlast <= 1'b0;
                    state <= S_RECV; blocks <= blocks + 1'b1;
                end else begin
                    m_axis_tdata <= {sat_sh(acc_hi[out_i[5:0]], pshift), sat_sh(acc_lo[out_i[5:0]], pshift)};
                    m_axis_tlast <= (out_i == 7'd63);
                    out_i <= out_i + 1'b1;
                end
            end
            default: state <= S_RECV;
            endcase
        end
    end

    // ------------------------------------------------------------------ AXI4-Lite
    reg        aw_hold, w_hold;
    reg [11:0] aw_addr;
    reg [31:0] w_data;
    always @(posedge clk) begin
        tw_we <= 1'b0; wi_we <= 1'b0;
        if (!resetn) begin
            s_axi_awready <= 1'b0; s_axi_wready <= 1'b0; s_axi_bvalid <= 1'b0; s_axi_bresp <= 2'b00;
            aw_hold <= 1'b0; w_hold <= 1'b0; pshift <= 6'd3; nseg_log2 <= 3'd3;
        end else begin
            s_axi_awready <= 1'b0; s_axi_wready <= 1'b0;
            if (s_axi_awvalid && !aw_hold && !s_axi_awready) begin
                s_axi_awready <= 1'b1; aw_hold <= 1'b1; aw_addr <= s_axi_awaddr;
            end
            if (s_axi_wvalid && !w_hold && !s_axi_wready) begin
                s_axi_wready <= 1'b1; w_hold <= 1'b1; w_data <= s_axi_wdata;
            end
            if (aw_hold && w_hold && !s_axi_bvalid) begin
                aw_hold <= 1'b0; w_hold <= 1'b0; s_axi_bvalid <= 1'b1; s_axi_bresp <= 2'b00;
                tab_a <= aw_addr[9:2]; tab_d <= w_data;
                if (aw_addr[11:10] == 2'b01) wi_we <= 1'b1;
                else if (aw_addr[11:10] == 2'b10) tw_we <= 1'b1;
                else if (aw_addr[9:0] == 10'h010) pshift <= w_data[5:0];
                else if (aw_addr[9:0] == 10'h014) nseg_log2 <= (w_data[2:0] > 3'd4) ? 3'd4 : w_data[2:0];
            end
            if (s_axi_bvalid && s_axi_bready) s_axi_bvalid <= 1'b0;
        end
    end

    always @(posedge clk) begin
        if (!resetn) begin
            s_axi_arready <= 1'b0; s_axi_rvalid <= 1'b0; s_axi_rresp <= 2'b00;
        end else begin
            s_axi_arready <= 1'b0;
            if (s_axi_arvalid && !s_axi_rvalid && !s_axi_arready) begin
                s_axi_arready <= 1'b1; s_axi_rvalid <= 1'b1; s_axi_rresp <= 2'b00;
                case (s_axi_araddr)
                    12'h000: s_axi_rdata <= ID_SWP1;
                    12'h004: s_axi_rdata <= {31'd0, state != S_RECV};
                    12'h008: s_axi_rdata <= blocks;
                    12'h00C: s_axi_rdata <= bad;
                    12'h010: s_axi_rdata <= {26'd0, pshift};
                    12'h014: s_axi_rdata <= {29'd0, nseg_log2};
                    default: s_axi_rdata <= 32'd0;
                endcase
            end
            if (s_axi_rvalid && s_axi_rready) s_axi_rvalid <= 1'b0;
        end
    end
endmodule
