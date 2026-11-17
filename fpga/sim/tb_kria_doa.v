`timescale 1ns / 1ps
// tb_kria_doa: the KrakenSDR's direction finding through kria_doa_axi, from the A53's own files.
//
// `kria-sdrd kraken-pre` (sw/kria/sdr) turns the synthetic USB capture (sw/integrations/kraken_sim.py) into:
//   doa_regs.txt    the register writes of its driver: weights, steering table, N_LOG2 (address data, hex)
//   doa_stim.hex    the aligned snapshots, two 64-bit beats each
//   doa_expect.txt  "N_LOG2 SHIFT", then R (15 lines, real imaginary), then P (360 lines), from its bit-exact model
// The bench runs the driver's sequence: the writes, a CPI with the scan off, R's diagonal read back and SHIFT
// chosen from it as the driver does, a rescan; then it reads R and P back, compares them with the model and writes
// them to doa_rtl.txt for `kria-sdrd kraken-post`. Gaps in the stream exercise tvalid.
//
//   fpga/sim/run.ps1 tb_kria_doa [-PlusArg DOA_DIR=../kraken] [-Mutate doa_no_conj]
module tb_kria_doa;
    reg clk = 0, resetn = 0;
    always #5 clk = ~clk;

    reg  [15:0] awaddr = 0, araddr = 0;
    reg         awvalid = 0, wvalid = 0, bready = 1, arvalid = 0, rready = 1;
    reg  [31:0] wdata = 0;
    wire        awready, wready, bvalid, arready, rvalid;
    wire [1:0]  bresp, rresp;
    wire [31:0] rdata;
    reg  [63:0] tdata = 0;
    reg         tvalid = 0, tlast = 0;
    wire        tready;

    kria_doa_axi dut (
        .clk(clk), .resetn(resetn),
        .s_axi_awaddr(awaddr), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(4'hF), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready),
        .s_axis_tdata(tdata), .s_axis_tvalid(tvalid), .s_axis_tready(tready), .s_axis_tlast(tlast)
    );

    task axi_w(input [15:0] a, input [31:0] d);
        begin
            @(posedge clk); awaddr <= a; awvalid <= 1; wdata <= d; wvalid <= 1;
            fork
                begin wait (awready); @(posedge clk); awvalid <= 0; end
                begin wait (wready);  @(posedge clk); wvalid <= 0; end
            join
            wait (bvalid); @(posedge clk);
        end
    endtask

    task axi_r(input [15:0] a, output [31:0] d);
        begin
            @(posedge clk); araddr <= a; arvalid <= 1;
            wait (arready); @(posedge clk); arvalid <= 0;
            wait (rvalid); d = rdata; @(posedge clk);
        end
    endtask

    reg [1023:0] dir;
    integer fd, rc, n_log2, shift_exp, shift, i, e, m, errors, nbeats;
    reg [31:0] a32, d32, lo, hi, st;
    reg signed [47:0] rre [0:14];
    reg signed [47:0] rim [0:14];
    reg signed [63:0] ere, eim;
    reg signed [31:0] p, ep;
    reg [63:0] stim [0:131071];
    reg [47:0] dmax;

    initial begin
        if (!$value$plusargs("DOA_DIR=%s", dir)) dir = "../kraken";
        errors = 0;
        repeat (10) @(posedge clk);
        resetn = 1;
        repeat (5) @(posedge clk);

        axi_r(16'h0000, d32);
        if (d32 !== 32'h444F4131) begin $display("FAIL: ID %h", d32); errors = errors + 1; end

        // the driver's writes
        fd = $fopen({dir, "/doa_regs.txt"}, "r");
        if (fd == 0) begin $display("FAIL: no doa_regs.txt in %0s", dir); $finish; end
        i = 0;
        while (!$feof(fd)) begin
            rc = $fscanf(fd, "%h %h\n", a32, d32);
            if (rc == 2) begin axi_w(a32[15:0], d32); i = i + 1; end
        end
        $fclose(fd);
        $display("tb_kria_doa: %0d register writes", i);

        fd = $fopen({dir, "/doa_expect.txt"}, "r");
        rc = $fscanf(fd, "%d %d\n", n_log2, shift_exp);
        nbeats = 2 << n_log2;
        $readmemh({dir, "/doa_stim.hex"}, stim, 0, nbeats - 1);

        // a CPI with the scan off
        axi_w(16'h0004, 32'h1);
        for (i = 0; i < nbeats; i = i + 1) begin
            if ((i % 977) == 500) begin tvalid <= 0; repeat (3) @(posedge clk); end
            tdata <= stim[i]; tvalid <= 1; tlast <= (i == nbeats - 1);
            @(posedge clk);
        end
        tvalid <= 0; tlast <= 0;
        st = 0;
        while (!st[2]) axi_r(16'h0008, st);

        // SHIFT from the diagonal, as the driver picks it
        dmax = 0;
        for (e = 0; e < 15; e = e + 1)
            if (e == 0 || e == 5 || e == 9 || e == 12 || e == 14) begin
                axi_r(16'h0100 + 16 * e, lo); axi_r(16'h0104 + 16 * e, hi);
                if ({hi[15:0], lo} > dmax) dmax = {hi[15:0], lo};
            end
        shift = 0;
        while ((dmax >> shift) >= 48'd16777216) shift = shift + 1;
        if (shift != shift_exp) begin $display("FAIL: SHIFT %0d, the model's %0d", shift, shift_exp); errors = errors + 1; end
        axi_w(16'h0010, shift);
        axi_w(16'h0004, 32'h4);
        st = 0;
        while (!st[2]) axi_r(16'h0008, st);

        axi_r(16'h0014, d32);
        if (d32 != 0) begin $display("FAIL: %0d beats dropped", d32); errors = errors + 1; end

        // R and P against the model
        fd = $fopen({dir, "/doa_rtl.txt"}, "w");
        $fdisplay(fd, "%0d %0d", n_log2, shift);
        for (e = 0; e < 15; e = e + 1) begin
            axi_r(16'h0100 + 16 * e, lo); axi_r(16'h0104 + 16 * e, hi); rre[e] = {hi[15:0], lo};
            axi_r(16'h0108 + 16 * e, lo); axi_r(16'h010C + 16 * e, hi); rim[e] = {hi[15:0], lo};
        end
        for (e = 0; e < 15; e = e + 1) begin
            $fdisplay(fd, "%0d %0d", rre[e], rim[e]);
        end
        for (m = 0; m < 360; m = m + 1) begin
            axi_r(16'h0800 + 4 * m, d32);
            p = d32;
            $fdisplay(fd, "%0d", p);
        end
        $fclose(fd);

        fd = $fopen({dir, "/doa_expect.txt"}, "r");
        rc = $fscanf(fd, "%d %d\n", n_log2, shift_exp);
        for (e = 0; e < 15; e = e + 1) begin
            rc = $fscanf(fd, "%d %d\n", ere, eim);
            if (ere != rre[e] || eim != rim[e]) begin
                if (errors < 10) $display("FAIL: R[%0d] = %0d %0d, model %0d %0d", e, rre[e], rim[e], ere, eim);
                errors = errors + 1;
            end
        end
        for (m = 0; m < 360; m = m + 1) begin
            rc = $fscanf(fd, "%d\n", ep);
            axi_r(16'h0800 + 4 * m, d32);
            p = d32;
            if (p != ep) begin
                if (errors < 10) $display("FAIL: P[%0d] = %0d, model %0d", m, p, ep);
                errors = errors + 1;
            end
        end
        $fclose(fd);

        if (errors == 0)
            $display("PASS: kria_doa matches the A53's bit-exact model: R (15 entries) and the Bartlett scan (360 bearings), N = %0d, SHIFT %0d", 1 << n_log2, shift);
        else
            $display("FAIL: %0d mismatches", errors);
        $finish;
    end

    initial begin
        #200_000_000;
        $display("FAIL: timeout");
        $finish;
    end
endmodule
