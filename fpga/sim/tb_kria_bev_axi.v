`timescale 1ns / 1ps
// tb_kria_bev_axi: kria_bev_axi (the grid's AXI wrapper) against the bit-exact model in
// sw/integrations/bev_fusion_sim.py, through both command paths.
//
// Run the model first (it writes fpga/sim/out/bev/). The bench configures the grid over AXI-Lite, then sends the
// model's commands in blocks of 64 that alternate between the register port (DET_XY + DET_CMD) and the
// s_axis_det stream with random gaps; before switching source it waits until STATUS shows the queue empty, so the
// order is the model's. The final dump is asked for through DET_CMD and compared cell by cell with random
// backpressure. Then the overflow path: with the sink stalled during a second dump, 513 pushes must leave the
// queue full at 512 with STATUS.overflow set, and a W1C must clear it. COUNT must equal the commands sent.
// +BEV_DIR=<dir> overrides the directory. Mutation bev_axi_no_stage (DET_CMD ignores DET_XY) must fail.
module tb_kria_bev_axi;
    reg clk = 1'b0;
    always #5 clk = ~clk;
    reg resetn = 1'b0;

    reg  [7:0]  awaddr = 0, araddr = 0;
    reg         awvalid = 0, wvalid = 0, bready = 1, arvalid = 0, rready = 1;
    reg  [31:0] wdata = 0;
    wire        awready, wready, bvalid, arready, rvalid;
    wire [1:0]  bresp, rresp;
    wire [31:0] rdata;
    reg  [63:0] sd_tdata = 0;
    reg         sd_tvalid = 0;
    wire        sd_tready;
    wire [63:0] m_tdata;
    wire [7:0]  m_tkeep;
    wire        m_tvalid, m_tlast;
    reg         m_tready = 1'b0;
    reg         stall = 1'b0;

    kria_bev_axi dut (
        .clk(clk), .resetn(resetn),
        .s_axi_awaddr(awaddr), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(4'hF), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready),
        .s_axis_det_tdata(sd_tdata), .s_axis_det_tvalid(sd_tvalid), .s_axis_det_tready(sd_tready),
        .m_axis_tdata(m_tdata), .m_axis_tkeep(m_tkeep), .m_axis_tvalid(m_tvalid), .m_axis_tlast(m_tlast),
        .m_axis_tready(m_tready)
    );

    reg [35:0] stim [0:65535];
    reg [63:0] expect_mem [0:8191];
    integer nstim, i, j, k, fd, r, v0, v1, v2, v3, beats, errs, lastseen, n_reg, n_axis, checking;
    reg [8*256-1:0] dir;
    reg [31:0] lf = 32'hACE1_2468;
    reg [31:0] rd;
    reg        da, dw;
    reg [31:0] cfg [0:4];

    always @(posedge clk) lf <= {lf[30:0], lf[31] ^ lf[21] ^ lf[1] ^ lf[0]};

    always @(posedge clk) begin
        if (resetn) begin
            m_tready <= !stall && (lf[5] | lf[9]);
            if (m_tvalid && m_tready && checking) begin
                if (m_tkeep !== 8'hFF) errs = errs + 1;
                if (m_tdata !== expect_mem[beats]) begin
                    errs = errs + 1;
                    if (errs <= 8)
                        $display("FAIL beat %0d: got %016h expected %016h", beats, m_tdata, expect_mem[beats]);
                end
                if (m_tlast) lastseen = beats;
                beats = beats + 1;
            end
        end
    end

    // Handshakes are sampled on the falling edge, half a clock after the DUT's registers change.
    task axi_write(input [7:0] a, input [31:0] d);
        begin
            @(posedge clk); #1 awaddr = a; awvalid = 1'b1; wdata = d; wvalid = 1'b1;
            while (awvalid || wvalid) begin
                @(negedge clk); da = awready; dw = wready;
                @(posedge clk); #1 if (da) awvalid = 1'b0; if (dw) wvalid = 1'b0;
            end
            @(negedge clk);
            while (!bvalid) @(negedge clk);
            @(posedge clk);
        end
    endtask

    task axi_read(input [7:0] a, output [31:0] d);
        begin
            @(posedge clk); #1 araddr = a; arvalid = 1'b1;
            @(negedge clk);
            while (!rvalid) @(negedge clk);     // this slave raises arready and rvalid together
            d = rdata;
            @(posedge clk); #1 arvalid = 1'b0;
        end
    endtask

    task wait_queue_empty;
        begin
            rd = 0;
            while (!rd[3]) axi_read(8'h04, rd);
        end
    endtask

    task push_reg(input [35:0] w);
        begin
            axi_write(8'h1C, w[31:0]);
            axi_write(8'h20, {28'd0, w[35:32]});
        end
    endtask

    task push_axis(input [35:0] w);
        begin
            k = lf[3:2];
            repeat (k) @(posedge clk);
            #1 sd_tdata = {28'hDEAD_BEE, w}; sd_tvalid = 1'b1;
            @(negedge clk);
            while (!sd_tready) @(negedge clk);
            @(posedge clk);
            #1 sd_tvalid = 1'b0;
        end
    endtask

    initial begin
        if (!$value$plusargs("BEV_DIR=%s", dir)) dir = "../bev";
        fd = $fopen({dir, "/bev_cfg.txt"}, "r");
        if (fd == 0) begin $display("FAIL: cannot open %0s/bev_cfg.txt (run sw/integrations/bev_fusion_sim.py)", dir); $finish; end
        r = $fscanf(fd, "%d %d %d %d", v0, v1, v2, v3); cfg[0] = {v3[7:0], v2[7:0], v1[7:0], v0[7:0]};
        r = $fscanf(fd, "%d %d %d %d", v0, v1, v2, v3); cfg[1] = {v3[7:0], v2[7:0], v1[7:0], v0[7:0]};
        r = $fscanf(fd, "%d %d %d %d", v0, v1, v2, v3); cfg[2] = {4'd0, v3[6:0], v2[6:0], v1[6:0], v0[6:0]};
        r = $fscanf(fd, "%d %d %d %d", v0, v1, v2, v3); cfg[3] = {4'd0, v3[6:0], v2[6:0], v1[6:0], v0[6:0]};
        r = $fscanf(fd, "%d %d %d %d", v0, v1, v2, v3); cfg[4] = {28'd0, v3[0], v2[0], v1[0], v0[0]};
        $fclose(fd);
        for (i = 0; i < 65536; i = i + 1) stim[i] = 36'hF_FFFF_FFFF;
        $readmemh({dir, "/bev_stim.hex"}, stim);
        $readmemh({dir, "/bev_expect.hex"}, expect_mem);
        nstim = 0;
        while (stim[nstim] !== 36'hF_FFFF_FFFF) nstim = nstim + 1;
        errs = 0; beats = 0; lastseen = -1; n_reg = 0; n_axis = 0; checking = 1;

        repeat (5) @(posedge clk);
        #1 resetn = 1'b1;

        axi_read(8'h00, rd);
        if (rd !== 32'h4245_5631) begin errs = errs + 1; $display("FAIL: ID %08h", rd); end
        axi_read(8'h08, rd);
        if (rd !== 32'h8080_8080) begin errs = errs + 1; $display("FAIL: ORIGIN_X reset %08h", rd); end
        axi_read(8'h04, rd);
        if (rd !== 32'h0000_0008) begin errs = errs + 1; $display("FAIL: STATUS reset %08h", rd); end

        for (i = 0; i < 5; i = i + 1) axi_write(8'h08 + 4 * i, cfg[i]);
        for (i = 0; i < 5; i = i + 1) begin
            axi_read(8'h08 + 4 * i, rd);
            if (rd !== cfg[i]) begin errs = errs + 1; $display("FAIL: cfg %0d read %08h wrote %08h", i, rd, cfg[i]); end
        end

        // The model's last command is the dump; send everything before it in alternating blocks.
        for (i = 0; i < nstim - 1; i = i + 64) begin
            wait_queue_empty;
            for (j = i; j < i + 64 && j < nstim - 1; j = j + 1) begin
                if ((i / 64) % 2 == 0) begin push_reg(stim[j]);  n_reg  = n_reg + 1; end
                else                   begin push_axis(stim[j]); n_axis = n_axis + 1; end
            end
        end
        wait_queue_empty;
        push_reg(stim[nstim - 1]); n_reg = n_reg + 1;

        wait (beats == 8192);
        repeat (20) @(posedge clk);
        if (lastseen != 8191) begin errs = errs + 1; $display("FAIL: tlast on beat %0d, expected 8191", lastseen); end
        rd = 0;
        while (rd[0] || !rd[3]) axi_read(8'h04, rd);
        axi_read(8'h24, rd);
        if (rd !== nstim) begin errs = errs + 1; $display("FAIL: COUNT %0d, expected %0d", rd, nstim); end

        // Overflow: stall the sink so a dump holds the core busy, then push 513 commands.
        checking = 0; stall = 1'b1;
        push_reg({4'b1000, 32'd0});
        for (i = 0; i < 513; i = i + 1) push_reg({4'b0000, 32'd0});
        axi_read(8'h04, rd);
        if (rd[1] !== 1'b1 || rd[2] !== 1'b1 || rd[25:16] !== 10'd512 || rd[0] !== 1'b1) begin
            errs = errs + 1; $display("FAIL: overflow STATUS %08h (want busy, full, overflow, level 512)", rd);
        end
        axi_write(8'h04, 32'h4);
        axi_read(8'h04, rd);
        if (rd[2] !== 1'b0) begin errs = errs + 1; $display("FAIL: overflow not cleared by W1C, STATUS %08h", rd); end
        stall = 1'b0;

        if (errs == 0)
            $display("PASS: tb_kria_bev_axi (%0d commands, %0d by register and %0d by stream; 65536 cells match the model; overflow at 512)",
                     nstim, n_reg, n_axis);
        else
            $display("FAIL: tb_kria_bev_axi %0d error(s)", errs);
        $finish;
    end

    initial begin
        #400_000_000;
        $display("FAIL: tb_kria_bev_axi timeout (beats %0d)", beats);
        $finish;
    end
endmodule
