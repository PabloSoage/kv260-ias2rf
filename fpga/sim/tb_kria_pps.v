`timescale 1ns / 1ps
// tb_kria_pps: capture, glitch filter, missing detection, output select, the
// fractional generator and its one-shot adjustment, and a closed loop that
// disciplines the generator to the GPS pulse the way R5F 0 does (sw/kria,
// pps::Discipline), all through the AXI4-Lite port.
//
// A "second" is CLK_HZ = 10,000 ticks of the 100 MHz clock (100 us), so a run
// covers dozens of seconds. The GPS second is 10,000.37 ticks long (the PL clock
// 37 ppm fast against GPS, scaled), with +-1 tick of jitter.
module tb_kria_pps;
    localparam integer CLK_HZ = 10_000;
    localparam integer MIN_HIGH = 10;

    reg clk = 1'b0;
    always #5 clk = ~clk;
    reg resetn = 1'b0;
    reg gps = 1'b0, swp = 1'b0;
    wire pps_out, irq;

    reg  [7:0]  awaddr = 0; reg awvalid = 0; wire awready;
    reg  [31:0] wdata = 0;  reg wvalid = 0;  wire wready;
    wire [1:0]  bresp; wire bvalid; reg bready = 1'b1;
    reg  [7:0]  araddr = 0; reg arvalid = 0; wire arready;
    wire [31:0] rdata; wire [1:0] rresp; wire rvalid; reg rready = 1'b1;

    kria_pps #(.CLK_HZ(CLK_HZ), .MIN_HIGH(MIN_HIGH)) dut (
        .clk(clk), .resetn(resetn), .gps_pps(gps), .sw_pps(swp), .pps_out(pps_out), .irq(irq),
        .s_axi_awaddr(awaddr), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(4'hF), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready));

    integer errors = 0;
    task check(input cond, input [8*80-1:0] what);
        begin
            if (!cond) begin
                errors = errors + 1;
                $display("FAIL: %0s", what);
            end
        end
    endtask

    task wr(input [7:0] a, input [31:0] d);
        begin
            @(posedge clk); #1;
            awaddr = a; awvalid = 1; wdata = d; wvalid = 1;
            fork
                begin wait (awready); @(posedge clk); #1; awvalid = 0; end
                begin wait (wready);  @(posedge clk); #1; wvalid = 0; end
            join
            wait (bvalid); @(posedge clk); #1;
        end
    endtask

    task rd(input [7:0] a, output [31:0] d);
        begin
            // arready and rvalid rise together and rvalid lasts one clock with
            // rready held high, so sample right after each edge.
            @(posedge clk); #1;
            araddr = a; arvalid = 1;
            @(posedge clk); #1;
            while (!rvalid) begin @(posedge clk); #1; end
            d = rdata; arvalid = 0;
            @(posedge clk); #1;
        end
    endtask

    // GPS source: period in ns as a real, so the fraction accumulates.
    real    gps_period_ns = 100_003.7;     // 10,000.37 ticks
    reg     gps_run = 1'b0;
    integer jit_seed = 7;
    real    t_next;
    time    gps_edges [0:255];
    integer n_edges = 0;
    initial begin : gps_gen
        integer j;
        wait (gps_run);
        t_next = $realtime + 20_000.0;
        forever begin
            if (!gps_run) begin
                wait (gps_run);
                t_next = $realtime + gps_period_ns;
            end
            j = $random(jit_seed) % 2;                // -1..1 tick of jitter
            #(t_next + j * 10.0 - $realtime);
            gps = 1'b1;
            if (n_edges < 256) gps_edges[n_edges] = $time;
            n_edges = n_edges + 1;
            #(10_000.0);                                // 100 ticks high
            gps = 1'b0;
            t_next = t_next + gps_period_ns;
        end
    end

    reg [31:0] v, lo, hi, per;
    integer i, k, prev_count;
    reg [63:0] cap, gen, prev_gen, cap0;
    integer last_adj, count0;
    integer err_ticks, worst, sum_d;

    // Closed loop, the shape of pps::Discipline in sw/kria: per GPS second,
    // phase error = generated edge - GPS edge; frequency from the capture
    // period; period written as int + frac; a fraction of the phase error
    // removed through GEN_ADJUST.
    real f_est;
    real phase_err;
    real per_r;
    reg [31:0] frac_w;

    initial begin
        $display("tb_kria_pps: CLK_HZ %0d, GPS second %0.2f ticks", CLK_HZ, gps_period_ns / 10.0);
        repeat (5) @(posedge clk);
        #1 resetn = 1'b1;
        repeat (5) @(posedge clk);

        rd(8'h34, v); check(v == 32'h50505331, "ID reads PPS1");
        rd(8'h00, v); check(v[1:0] == 2'd0, "reset mode is the software GPIO");

        // Mode 0: PPS_SYNC follows the software GPIO, as before this block.
        #1 swp = 1'b1; repeat (4) @(posedge clk); #1;
        check(pps_out == 1'b1, "mode 0 forwards sw_pps high");
        swp = 1'b0; repeat (4) @(posedge clk); #1;
        check(pps_out == 1'b0, "mode 0 forwards sw_pps low");

        // Capture, IRQ.
        wr(8'h00, 32'h0000_0005);                       // mode 1, irq_en
        gps_run = 1'b1;
        for (i = 0; i < 4; i = i + 1) begin
            wait (irq); rd(8'h04, v);
            check(v[0] == 1'b1, "cap_pending with the IRQ");
            wr(8'h04, 32'h1);
            #1 check(irq == 1'b0, "W1C clears the IRQ");
        end
        rd(8'h04, v); check(v[31:16] == 16'd4, "four GPS edges counted");
        rd(8'h10, per);
        check(per >= 32'd9999 && per <= 32'd10002, "capture period is one GPS second in ticks");

        // Mode 1 forwards the qualified pulse.
        wait (gps); repeat (MIN_HIGH + 6) @(posedge clk); #1;
        check(pps_out == 1'b1, "mode 1 forwards the GPS pulse after qualification");
        wait (!gps); repeat (4) @(posedge clk); #1;
        check(pps_out == 1'b0, "mode 1 drops with the GPS pulse");

        // Glitch: 5 ticks high between seconds is flagged and not captured.
        rd(8'h04, v); prev_count = v[31:16];
        rd(8'h08, lo);
        #20_000; gps = 1'b1; #50; gps = 1'b0;
        repeat (20) @(posedge clk);
        rd(8'h04, v);
        check(v[2] == 1'b1, "short pulse flagged as a glitch");
        check(v[31:16] == prev_count, "glitch not counted");
        rd(8'h08, v); check(v == lo, "glitch not captured");
        check(pps_out == 1'b0, "glitch never reaches PPS_SYNC");
        wr(8'h04, 32'h4);

        // Missing: stop the GPS. The edge already scheduled still comes, so
        // wait for it, then 1.6 s more.
        gps_run = 1'b0;
        #(110_000);
        #(160_000);
        rd(8'h04, v); check(v[1] == 1'b1, "missing after 1.25 s without an edge");
        wr(8'h04, 32'h1);                              // drop the capture of the glitch test
        gps_run = 1'b1;
        wait (irq); wr(8'h04, 32'h1);
        rd(8'h04, v); check(v[1] == 1'b0, "missing clears on the next edge");

        $display("t=%0t %0s", $time, "Generator");
        // Generator, open loop: period 10,000.25 ticks, 8 seconds.
        wr(8'h14, 32'd10000); wr(8'h18, 32'h4000_0000); wr(8'h28, 32'd200);
        wr(8'h00, 32'h0000_001A);                         // mode 2, gen_en, restart
        rd(8'h04, v);
        wait (pps_out); @(posedge clk);
        rd(8'h20, lo); rd(8'h24, hi); prev_gen = {hi, lo};
        sum_d = 0;
        for (i = 0; i < 8; i = i + 1) begin
            wait (!pps_out); wait (pps_out); @(posedge clk);
            rd(8'h20, lo); rd(8'h24, hi); gen = {hi, lo};
            sum_d = sum_d + (gen - prev_gen);
            check((gen - prev_gen) == 10000 || (gen - prev_gen) == 10001, "generated second is 10,000 or 10,001 ticks");
            prev_gen = gen;
        end
        check(sum_d == 80002, "eight generated seconds total 80,002 ticks (10,000.25 each)");
        $display("t=%0t %0s", $time, "One-shot adjust.");
        // One-shot adjust.
        wr(8'h1C, 32'd50);
        wait (!pps_out); wait (pps_out); @(posedge clk);
        rd(8'h20, lo); rd(8'h24, hi); gen = {hi, lo};
        wait (!pps_out); wait (pps_out); @(posedge clk);
        rd(8'h20, lo); rd(8'h24, hi);
        check(({hi, lo} - gen) >= 10049 && ({hi, lo} - gen) <= 10051, "adjust +50 lands on one second only");
        wait (!pps_out); wait (pps_out); @(posedge clk);
        rd(8'h20, v);
        check((v - lo) == 10000 || (v - lo) == 10001, "and the next second is back to the period");

        $display("t=%0t %0s", $time, "Closed loop");
        // Closed loop: lock the generator to the GPS second.
        f_est = 10000.0;
        worst = 0;
        wr(8'h04, 32'hD);
        wr(8'h00, 32'h0000_000E);                         // mode 2, irq_en, gen_en
        for (k = 0; k < 30; k = k + 1) begin
            v = 0;
            while (!v[0]) begin                            // a GPS capture, not a generated edge
                wait (irq);
                rd(8'h04, v); wr(8'h04, v & 32'h9);        // clear only what was seen
            end
            rd(8'h08, lo); rd(8'h0C, hi); cap = {hi, lo};
            rd(8'h10, per);
            rd(8'h20, lo); rd(8'h24, hi); gen = {hi, lo};
            // Generated edge nearest to this GPS edge.
            phase_err = $itor($signed(gen - cap));
            if (phase_err >  f_est / 2) phase_err = phase_err - f_est;
            if (phase_err < -f_est / 2) phase_err = phase_err + f_est;
            // Frequency over the whole run so far, not one second: one capture
            // carries +-1 tick of jitter, k of them +-1/k.
            if (k == 0) begin cap0 = cap; count0 = v[31:16]; end
            else        f_est = $itor(cap - cap0) / (v[31:16] - count0);
            per_r  = f_est;
            frac_w = (per_r - $floor(per_r)) * 4294967296.0;
            wr(8'h14, $rtoi($floor(per_r)));
            wr(8'h18, frac_w);
            last_adj = $rtoi(-0.5 * phase_err);
            wr(8'h1C, last_adj);
            err_ticks = (phase_err < 0) ? -$rtoi(phase_err) : $rtoi(phase_err);
            if (k >= 20 && err_ticks > worst) worst = err_ticks;
        end
        $display("closed loop: frequency %0.3f ticks/s (GPS %0.2f), worst phase error after 20 s: %0d ticks",
                 f_est, gps_period_ns / 10.0, worst);
        check(worst <= 3, "generator held within 3 ticks (30 ns) of the GPS second");
        check(f_est > 9999.9 && f_est < 10000.9, "frequency estimate within 0.5 tick of 10,000.37");

        $display("t=%0t %0s", $time, "Holdover");
        // Holdover: GPS gone, the generator keeps the second.
        rd(8'h20, lo); rd(8'h24, hi); prev_gen = {hi, lo};
        gps_run = 1'b0;
        for (i = 0; i < 5; i = i + 1) begin
            wait (!pps_out); wait (pps_out); @(posedge clk);
        end
        rd(8'h20, lo); rd(8'h24, hi); gen = {hi, lo};
        $display("holdover: 5 generated seconds without GPS, %0d ticks", gen - prev_gen);
        // Five learnt seconds, plus the last phase adjustment if it was still
        // pending, give or take the fraction.
        check($itor(gen - prev_gen) - 5.0 * f_est - last_adj > -2.0 &&
              $itor(gen - prev_gen) - 5.0 * f_est - last_adj <  2.0, "holdover keeps the learnt second");
        rd(8'h04, v); check(v[1] == 1'b1, "holdover reports missing GPS");

        if (errors == 0) $display("PASS: tb_kria_pps");
        else             $display("FAIL: tb_kria_pps (%0d errors)", errors);
        $finish;
    end

    initial begin
        #(200_000_000);
        $display("FAIL: tb_kria_pps timeout");
        $finish;
    end
endmodule
