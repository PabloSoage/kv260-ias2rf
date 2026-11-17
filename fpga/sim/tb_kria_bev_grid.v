`timescale 1ns / 1ps
// tb_kria_bev_grid: kria_bev_grid (fpga/kria/integrations/) against the bit-exact model in
// sw/integrations/bev_fusion_sim.py.
//
// Run the model first; it writes fpga/sim/out/bev/{bev_cfg.txt, bev_stim.hex, bev_expect.hex}: four frames of a
// LiDAR and a 77 GHz radar in 30 m fog (969 detections, ray casting on the LiDAR, a decay pass after each frame),
// then a dump. The bench feeds the words with random gaps, holds m_tready low at random, and compares all 65,536
// dumped cells with the model's grid.
// +BEV_DIR=<dir> overrides the directory.
module tb_kria_bev_grid;
    reg clk = 1'b0;
    always #5 clk = ~clk;
    reg rst = 1'b1;

    reg  [35:0] s_tdata = 36'd0;
    reg         s_tvalid = 1'b0;
    wire        s_tready;
    wire [63:0] m_tdata;
    wire        m_tvalid, m_tlast;
    reg         m_tready = 1'b0;
    reg  [31:0] cfg_origin_x, cfg_origin_y;
    reg  [27:0] cfg_hit, cfg_miss;
    reg  [3:0]  cfg_ray;
    wire        busy;

    kria_bev_grid dut (
        .clk(clk), .rst(rst), .s_tdata(s_tdata), .s_tvalid(s_tvalid), .s_tready(s_tready),
        .m_tdata(m_tdata), .m_tvalid(m_tvalid), .m_tlast(m_tlast), .m_tready(m_tready),
        .cfg_origin_x(cfg_origin_x), .cfg_origin_y(cfg_origin_y), .cfg_hit(cfg_hit), .cfg_miss(cfg_miss),
        .cfg_ray(cfg_ray), .busy(busy)
    );

    reg [35:0] stim [0:65535];
    reg [63:0] expect_mem [0:8191];
    integer nstim, i, k, fd, r, v0, v1, v2, v3, beats, errs, lastseen;
    reg [8*256-1:0] dir;
    reg [31:0] lf = 32'hACE1_2468;

    always @(posedge clk) lf <= {lf[30:0], lf[31] ^ lf[21] ^ lf[1] ^ lf[0]};

    // sink: random backpressure, compare each beat
    always @(posedge clk) begin
        if (!rst) begin
            m_tready <= lf[5] | lf[9];
            if (m_tvalid && m_tready) begin
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

    initial begin
        if (!$value$plusargs("BEV_DIR=%s", dir)) dir = "../bev";
        fd = $fopen({dir, "/bev_cfg.txt"}, "r");
        if (fd == 0) begin $display("FAIL: cannot open %0s/bev_cfg.txt (run sw/integrations/bev_fusion_sim.py)", dir); $finish; end
        r = $fscanf(fd, "%d %d %d %d", v0, v1, v2, v3); cfg_origin_x = {v3[7:0], v2[7:0], v1[7:0], v0[7:0]};
        r = $fscanf(fd, "%d %d %d %d", v0, v1, v2, v3); cfg_origin_y = {v3[7:0], v2[7:0], v1[7:0], v0[7:0]};
        r = $fscanf(fd, "%d %d %d %d", v0, v1, v2, v3); cfg_hit  = {v3[6:0], v2[6:0], v1[6:0], v0[6:0]};
        r = $fscanf(fd, "%d %d %d %d", v0, v1, v2, v3); cfg_miss = {v3[6:0], v2[6:0], v1[6:0], v0[6:0]};
        r = $fscanf(fd, "%d %d %d %d", v0, v1, v2, v3); cfg_ray  = {v3[0], v2[0], v1[0], v0[0]};
        $fclose(fd);
        for (i = 0; i < 65536; i = i + 1) stim[i] = 36'hF_FFFF_FFFF;
        $readmemh({dir, "/bev_stim.hex"}, stim);
        $readmemh({dir, "/bev_expect.hex"}, expect_mem);
        nstim = 0;
        while (stim[nstim] !== 36'hF_FFFF_FFFF) nstim = nstim + 1;
        errs = 0; beats = 0; lastseen = -1;

        repeat (5) @(posedge clk);
        #1 rst = 1'b0;
        for (i = 0; i < nstim; i = i + 1) begin
            // random gap of 0..3 clocks between words
            k = lf[3:2];
            repeat (k) @(posedge clk);
            #1 s_tdata = stim[i]; s_tvalid = 1'b1;
            // s_tready only changes on clock edges: look at it half a clock before the edge that takes the word
            @(negedge clk);
            while (!s_tready) @(negedge clk);
            @(posedge clk);
            #1 s_tvalid = 1'b0;
        end
        wait (beats == 8192);
        repeat (20) @(posedge clk);
        if (lastseen != 8191) begin
            errs = errs + 1;
            $display("FAIL: tlast on beat %0d, expected 8191", lastseen);
        end
        if (errs == 0)
            $display("PASS: tb_kria_bev_grid (%0d commands, 65536 cells match the model)", nstim);
        else
            $display("FAIL: tb_kria_bev_grid %0d mismatching beat(s)", errs);
        $finish;
    end

    initial begin
        #200_000_000;
        $display("FAIL: tb_kria_bev_grid timeout (beats %0d)", beats);
        $finish;
    end
endmodule
