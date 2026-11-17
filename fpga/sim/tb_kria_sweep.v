`timescale 1ns / 1ps
// tb_kria_sweep: a HackRF Pro sweep through kria_sweep_axi, from the A53's own files.
//
// `kria-sdrd hackrf-pre` (sw/kria/sdr) turns the synthetic USB capture (sw/integrations/hackrf_sim.py, 720 blocks
// from 0 to 7.2 GHz, one with a corrupted header) into:
//   sweep_regs.txt    its driver's register writes: window, twiddles, PSHIFT (address data, hex)
//   sweep_stim.hex    the transfers as 64-bit beats, 2,048 per block
//   sweep_expect.hex  the output beats of its bit-exact model (65 per good block)
//   sweep_counts.txt  good and bad blocks
// The bench sends the stream through the block with gaps in tvalid and back-pressure on the output, checks every
// output beat and tlast, the BLOCKS and BAD counters, and writes the output to sweep_rtl.hex for
// `kria-sdrd hackrf-post`.
//
//   fpga/sim/run.ps1 tb_kria_sweep [-PlusArg SWEEP_DIR=../hackrf] [-Mutate sweep_twiddle_conj]
module tb_kria_sweep;
    reg clk = 0, resetn = 0;
    always #5 clk = ~clk;

    reg  [11:0] awaddr = 0, araddr = 0;
    reg         awvalid = 0, wvalid = 0, bready = 1, arvalid = 0, rready = 1;
    reg  [31:0] wdata = 0;
    wire        awready, wready, bvalid, arready, rvalid;
    wire [1:0]  bresp, rresp;
    wire [31:0] rdata;
    reg  [63:0] tdata = 0;
    reg         tvalid = 0, tlast = 0;
    wire        tready;
    wire [63:0] m_tdata;
    wire [7:0]  m_tkeep;
    wire        m_tvalid, m_tlast;
    reg         m_tready = 1;

    kria_sweep_axi dut (
        .clk(clk), .resetn(resetn),
        .s_axi_awaddr(awaddr), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(4'hF), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready),
        .s_axis_tdata(tdata), .s_axis_tvalid(tvalid), .s_axis_tready(tready), .s_axis_tlast(tlast),
        .m_axis_tdata(m_tdata), .m_axis_tkeep(m_tkeep), .m_axis_tvalid(m_tvalid), .m_axis_tlast(m_tlast),
        .m_axis_tready(m_tready)
    );

    task axi_w(input [11:0] a, input [31:0] d);
        begin
            @(posedge clk); awaddr <= a; awvalid <= 1; wdata <= d; wvalid <= 1;
            fork
                begin wait (awready); @(posedge clk); awvalid <= 0; end
                begin wait (wready);  @(posedge clk); wvalid <= 0; end
            join
            wait (bvalid); @(posedge clk);
        end
    endtask

    task axi_r(input [11:0] a, output [31:0] d);
        begin
            @(posedge clk); araddr <= a; arvalid <= 1;
            wait (arready); @(posedge clk); arvalid <= 0;
            wait (rvalid); d = rdata; @(posedge clk);
        end
    endtask

    reg [8*256-1:0] dir;
    integer fd, fo, rc, i, nin, nexp, good, badn, errors, outn;
    reg [31:0] a32, d32;
    reg        hs;
    reg [63:0] stim [0:1572863];
    reg [63:0] expv [0:65535];

    // output checker, with back-pressure one clock in seven
    always @(posedge clk) begin
        m_tready <= ($random % 7) != 0;
        if (resetn && m_tvalid && m_tready) begin
            if (outn < nexp) begin
                if (m_tdata !== expv[outn]) begin
                    if (errors < 10) $display("FAIL: output beat %0d = %h, model %h", outn, m_tdata, expv[outn]);
                    errors = errors + 1;
                end
                if (m_tlast !== ((outn % 65) == 64)) begin
                    if (errors < 10) $display("FAIL: tlast at beat %0d", outn);
                    errors = errors + 1;
                end
            end
            $fdisplay(fo, "%016h", m_tdata);
            outn = outn + 1;
        end
    end

    initial begin
        if (!$value$plusargs("SWEEP_DIR=%s", dir)) dir = "../hackrf";
        errors = 0; outn = 0;
        fo = $fopen({dir, "/sweep_rtl.hex"}, "w");
        repeat (10) @(posedge clk);
        resetn = 1;
        repeat (5) @(posedge clk);
        axi_r(12'h000, d32);
        if (d32 !== 32'h53575031) begin $display("FAIL: ID %h", d32); errors = errors + 1; end

        fd = $fopen({dir, "/sweep_regs.txt"}, "r");
        if (fd == 0) begin $display("FAIL: no sweep_regs.txt in %0s", dir); $finish; end
        i = 0;
        while (!$feof(fd)) begin
            rc = $fscanf(fd, "%h %h\n", a32, d32);
            if (rc == 2) begin axi_w(a32[11:0], d32); i = i + 1; end
        end
        $fclose(fd);
        fd = $fopen({dir, "/sweep_counts.txt"}, "r");
        rc = $fscanf(fd, "%d %d\n", good, badn);
        $fclose(fd);
        nin = (good + badn) * 2048;
        nexp = good * 65;
        $readmemh({dir, "/sweep_stim.hex"}, stim, 0, nin - 1);
        $readmemh({dir, "/sweep_expect.hex"}, expv, 0, nexp - 1);
        $display("tb_kria_sweep: %0d register writes, %0d blocks (%0d bad), %0d output beats expected", i, good + badn, badn, nexp);

        i = 0;
        while (i < nin) begin
            tdata <= stim[i]; tvalid <= ((i % 613) != 300) || ($random % 2); tlast <= ((i % 2048) == 2047);
            @(negedge clk);
            hs = tvalid && tready;
            @(posedge clk);
            if (hs) i = i + 1;
        end
        tvalid <= 0; tlast <= 0;
        while (outn < nexp) @(posedge clk);
        repeat (20) @(posedge clk);

        axi_r(12'h008, d32);
        if (d32 != good) begin $display("FAIL: BLOCKS %0d, expected %0d", d32, good); errors = errors + 1; end
        axi_r(12'h00C, d32);
        if (d32 != badn) begin $display("FAIL: BAD %0d, expected %0d", d32, badn); errors = errors + 1; end
        $fclose(fo);
        if (errors == 0)
            $display("PASS: kria_sweep matches the A53's bit-exact model on %0d blocks (%0d output beats), %0d bad header dropped", good, nexp, badn);
        else
            $display("FAIL: %0d mismatches", errors);
        $finish;
    end

    initial begin
        #2_000_000_000;
        $display("FAIL: timeout");
        $finish;
    end
endmodule
