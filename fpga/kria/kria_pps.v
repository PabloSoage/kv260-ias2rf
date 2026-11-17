`timescale 1ns / 1ps
// kria_pps: GPS 1-PPS capture and a disciplined PPS generator for the K26 PL.
//
// The PPS that reaches the front end on Pmod J2 pin 8 (PPS_SYNC) used to be a PS
// GPIO toggled by software, with the jitter of whatever Linux was doing at the
// time. This block takes the PPS of a GPS receiver on a free PL pin (KV260 J9
// pin 12, HDA10, ball J12) and gives the rest of the system three things:
//
//  1. A timestamp of every GPS edge on the PL clock, 10 ns per tick at 100 MHz,
//     after a glitch filter (the pulse must stay high MIN_HIGH clocks; the
//     timestamp is still the edge's). The interval between the last two edges is
//     the PL clock's frequency measured against GPS.
//  2. A generated PPS: a fractional-period counter (PERIOD integer + 32-bit
//     fraction, in ticks) that pulses on its own, so the output keeps going when
//     the GPS loses its fix or the cable falls out (holdover). A real-time core
//     (R5F 0, sw/kria) measures the GPS edges against it, and writes the period
//     and a one-shot phase adjustment so that it stays on the GPS second.
//  3. The source of PPS_SYNC, chosen in CTRL: the software GPIO as before (mode
//     0, the reset default, so nothing changes until software says so), the GPS
//     pulse as it arrives (mode 1), or the generated pulse (mode 2).
//
// Registers (AXI4-Lite, 32-bit, byte addresses):
//   0x00 CTRL        [1:0] mode (0 sw GPIO, 1 GPS, 2 generated), [2] irq_en,
//                    [3] gen_en (the generator runs), [4] gen_restart (W1, self
//                    clearing: next generated edge = NOW + PERIOD)
//   0x04 STATUS      [0] cap_pending (W1C, raises the IRQ), [1] missing (no GPS
//                    edge for MISSING_TICKS), [2] glitch (W1C, a pulse shorter
//                    than MIN_HIGH), [3] gen_pending (W1C, a generated edge),
//                    [31:16] GPS edge count
//   0x08 CAP_LO/0x0C CAP_HI   timestamp of the last accepted GPS edge
//   0x10 CAP_PERIOD           ticks between the last two GPS edges
//   0x14 GEN_PERIOD_INT       generator period, whole ticks
//   0x18 GEN_PERIOD_FRAC      generator period, fraction (2^-32 tick)
//   0x1C GEN_ADJUST           signed ticks added once to the next generated edge
//   0x20 GEN_LO/0x24 GEN_HI   timestamp of the last generated edge
//   0x28 WIDTH                output pulse width in ticks
//   0x2C NOW_LO/0x30 NOW_HI   free-running tick counter (reading NOW_LO
//                             latches NOW_HI)
//   0x34 ID                   "PPS1"
module kria_pps #(
    parameter integer CLK_HZ   = 100_000_000,
    parameter integer MIN_HIGH = 100           // 1 us at 100 MHz
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 clk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axi, ASSOCIATED_RESET resetn" *)
    input  wire        clk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 resetn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input  wire        resetn,

    input  wire        gps_pps,                // async, from the pin
    input  wire        sw_pps,                 // PS EMIO GPIO[2], the old source
    output reg         pps_out,                // to PPS_SYNC and the link timestamps
    (* X_INTERFACE_INFO = "xilinx.com:signal:interrupt:1.0 irq INTERRUPT" *)
    (* X_INTERFACE_PARAMETER = "SENSITIVITY LEVEL_HIGH" *)
    output wire        irq,

    (* X_INTERFACE_PARAMETER = "PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 8" *)
    input  wire [7:0]  s_axi_awaddr,
    input  wire        s_axi_awvalid,
    output reg         s_axi_awready,
    input  wire [31:0] s_axi_wdata,
    input  wire [3:0]  s_axi_wstrb,
    input  wire        s_axi_wvalid,
    output reg         s_axi_wready,
    output reg  [1:0]  s_axi_bresp,
    output reg         s_axi_bvalid,
    input  wire        s_axi_bready,
    input  wire [7:0]  s_axi_araddr,
    input  wire        s_axi_arvalid,
    output reg         s_axi_arready,
    output reg  [31:0] s_axi_rdata,
    output reg  [1:0]  s_axi_rresp,
    output reg         s_axi_rvalid,
    input  wire        s_axi_rready
);
    localparam [63:0] MISSING_TICKS = (CLK_HZ / 4) * 5;      // 1.25 s
    localparam [31:0] ID_PPS1       = 32'h5050_5331;         // "PPS1"

    // ---------------------------------------------------------------- time base
    reg [63:0] now;
    always @(posedge clk) begin
        if (!resetn) now <= 64'd0;
        else         now <= now + 64'd1;
    end

    // ----------------------------------------------------------- GPS capture
    (* ASYNC_REG = "TRUE" *) reg [2:0] gps_s;
    (* ASYNC_REG = "TRUE" *) reg [1:0] sw_s;
    reg [63:0] edge_ts;          // timestamp of the rising edge being qualified
    reg [15:0] high_cnt;
    reg        qualifying;
    reg [63:0] cap_ts;
    reg [31:0] cap_period;
    reg [15:0] cap_count;
    reg        cap_valid;        // at least one edge accepted
    reg        cap_pending, glitch, missing;
    reg        gps_q;            // the accepted pulse, for mode 1

    // --------------------------------------------------------------- registers
    reg [1:0]  mode;
    reg        irq_en, gen_en;
    reg [31:0] gen_period_int, gen_period_frac, width;
    reg signed [31:0] gen_adjust;
    reg        adjust_pending, restart_req;

    // --------------------------------------------------------------- generator
    reg [63:0] gen_next;         // whole tick of the next generated edge
    reg [31:0] gen_frac;         // fractional accumulator
    reg [63:0] gen_ts;
    reg        gen_pending;
    reg [31:0] gen_high;         // ticks left in the generated pulse
    reg        gen_q;

    // AXI write strobes from the bus logic below
    reg        wr_stb;
    reg [7:0]  wr_addr;
    reg [31:0] wr_data;

    always @(posedge clk) begin
        if (!resetn) begin
            gps_s <= 3'b000; sw_s <= 2'b00;
            edge_ts <= 64'd0; high_cnt <= 16'd0; qualifying <= 1'b0;
            cap_ts <= 64'd0; cap_period <= 32'd0; cap_count <= 16'd0; cap_valid <= 1'b0;
            cap_pending <= 1'b0; glitch <= 1'b0; missing <= 1'b0; gps_q <= 1'b0;
            mode <= 2'd0; irq_en <= 1'b0; gen_en <= 1'b0;
            gen_period_int <= CLK_HZ; gen_period_frac <= 32'd0; width <= CLK_HZ / 10;
            gen_adjust <= 32'sd0; adjust_pending <= 1'b0; restart_req <= 1'b0;
            gen_next <= CLK_HZ; gen_frac <= 32'd0; gen_ts <= 64'd0;
            gen_pending <= 1'b0; gen_high <= 32'd0; gen_q <= 1'b0;
            pps_out <= 1'b0;
        end else begin
            gps_s <= {gps_s[1:0], gps_pps};
            sw_s  <= {sw_s[0], sw_pps};

            // Edge, then MIN_HIGH clocks high before it counts. A pulse that
            // drops early is a glitch: flagged, not captured, and the previous
            // capture (and so the period) is left alone.
            if (gps_s[1] && !gps_s[2] && !qualifying) begin
                qualifying <= 1'b1;
                edge_ts    <= now;
                high_cnt   <= 16'd1;
            end else if (qualifying) begin
`ifdef MUTATE_PPS_NO_FILTER
                // Mutation: a pulse that drops early is captured anyway.
                if (1'b0) begin
`else
                if (!gps_s[1]) begin
`endif
                    qualifying <= 1'b0;
                    glitch     <= 1'b1;
                end else if (high_cnt == MIN_HIGH[15:0] - 16'd1 || !gps_s[1]) begin
                    qualifying  <= 1'b0;
                    cap_period  <= edge_ts[31:0] - cap_ts[31:0];
                    cap_ts      <= edge_ts;
                    cap_count   <= cap_count + 16'd1;
                    cap_valid   <= 1'b1;
                    cap_pending <= 1'b1;
                    missing     <= 1'b0;
                end else begin
                    high_cnt <= high_cnt + 16'd1;
                end
            end
            // gps_q is the GPS pulse delayed by the qualification, so mode 1
            // never forwards a glitch.
            if (qualifying && high_cnt == MIN_HIGH[15:0] - 16'd1 && gps_s[1]) gps_q <= 1'b1;
            else if (!gps_s[1])                                             gps_q <= 1'b0;

            if (cap_valid && (now - cap_ts) > MISSING_TICKS
                && !(qualifying && gps_s[1] && high_cnt == MIN_HIGH[15:0] - 16'd1))
                missing <= 1'b1;

            // Generator: pulse at gen_next, then advance by the fractional
            // period. A pending adjustment is folded into the next advance.
            // `>=` rather than `==`: an adjustment that lands the next edge in
            // the past fires it at once instead of stopping the generator.
            if (restart_req) begin
                restart_req <= 1'b0;
                gen_next    <= now + {32'd0, gen_period_int};
                gen_frac    <= 32'd0;
                gen_q       <= 1'b0;
                gen_high    <= 32'd0;
            end else if (gen_en && now >= gen_next) begin
                gen_ts      <= now;
                gen_pending <= 1'b1;
                gen_q       <= 1'b1;
                gen_high    <= width;
                {gen_next, gen_frac} <= {gen_next, gen_frac} + {32'd0, gen_period_int, gen_period_frac}
                                        + (adjust_pending ? {{32{gen_adjust[31]}}, gen_adjust, 32'd0} : 96'd0);
                adjust_pending <= 1'b0;
            end else if (gen_high != 32'd0) begin
                gen_high <= gen_high - 32'd1;
                if (gen_high == 32'd1) gen_q <= 1'b0;
            end

            case (mode)
                2'd1:    pps_out <= gps_q;
                2'd2:    pps_out <= gen_q;
                default: pps_out <= sw_s[1];
            endcase

            // Register writes (after the hardware updates, so a W1C that lands
            // in the same clock as a new event loses to the event).
            if (wr_stb) begin
                case (wr_addr)
                    8'h00: begin
                        mode   <= wr_data[1:0];
                        irq_en <= wr_data[2];
                        gen_en <= wr_data[3];
                        if (wr_data[4]) restart_req <= 1'b1;
                    end
                    8'h04: begin
                        if (wr_data[0]) cap_pending <= 1'b0;
                        if (wr_data[2]) glitch      <= 1'b0;
                        if (wr_data[3]) gen_pending <= 1'b0;
                    end
                    8'h14: gen_period_int  <= wr_data;
                    8'h18: gen_period_frac <= wr_data;
                    8'h1C: begin gen_adjust <= wr_data; adjust_pending <= 1'b1; end
                    8'h28: width <= wr_data;
                    default: ;
                endcase
            end
        end
    end

    assign irq = irq_en & (cap_pending | gen_pending);

    // ------------------------------------------------------------ AXI4-Lite
    reg        aw_got, w_got;
    reg [7:0]  aw_q;
    reg [31:0] w_q;
    reg [31:0] now_hi_shadow;

    always @(posedge clk) begin
        if (!resetn) begin
            s_axi_awready <= 1'b0; s_axi_wready <= 1'b0;
            s_axi_bvalid <= 1'b0; s_axi_bresp <= 2'b00;
            s_axi_arready <= 1'b0; s_axi_rvalid <= 1'b0; s_axi_rresp <= 2'b00; s_axi_rdata <= 32'd0;
            aw_got <= 1'b0; w_got <= 1'b0; aw_q <= 8'd0; w_q <= 32'd0;
            wr_stb <= 1'b0; wr_addr <= 8'd0; wr_data <= 32'd0;
            now_hi_shadow <= 32'd0;
        end else begin
            wr_stb        <= 1'b0;
            s_axi_awready <= 1'b0;
            s_axi_wready  <= 1'b0;
            s_axi_arready <= 1'b0;

            if (s_axi_awvalid && !aw_got && !s_axi_bvalid && !s_axi_awready) begin
                s_axi_awready <= 1'b1; aw_got <= 1'b1; aw_q <= s_axi_awaddr;
            end
            if (s_axi_wvalid && !w_got && !s_axi_bvalid && !s_axi_wready) begin
                s_axi_wready <= 1'b1; w_got <= 1'b1; w_q <= s_axi_wdata;
            end
            if (aw_got && w_got && !s_axi_bvalid) begin
                wr_stb  <= 1'b1;
                wr_addr <= {aw_q[7:2], 2'b00};
                wr_data <= w_q;
                aw_got  <= 1'b0; w_got <= 1'b0;
                s_axi_bvalid <= 1'b1; s_axi_bresp <= 2'b00;
            end
            if (s_axi_bvalid && s_axi_bready) s_axi_bvalid <= 1'b0;

            if (s_axi_arvalid && !s_axi_rvalid && !s_axi_arready) begin
                s_axi_arready <= 1'b1;
                s_axi_rvalid  <= 1'b1;
                s_axi_rresp   <= 2'b00;
                case ({s_axi_araddr[7:2], 2'b00})
                    8'h00: s_axi_rdata <= {27'd0, 1'b0, gen_en, irq_en, mode};
                    8'h04: s_axi_rdata <= {cap_count, 12'd0, gen_pending, glitch, missing, cap_pending};
                    8'h08: s_axi_rdata <= cap_ts[31:0];
                    8'h0C: s_axi_rdata <= cap_ts[63:32];
                    8'h10: s_axi_rdata <= cap_period;
                    8'h14: s_axi_rdata <= gen_period_int;
                    8'h18: s_axi_rdata <= gen_period_frac;
                    8'h1C: s_axi_rdata <= gen_adjust;
                    8'h20: s_axi_rdata <= gen_ts[31:0];
                    8'h24: s_axi_rdata <= gen_ts[63:32];
                    8'h28: s_axi_rdata <= width;
                    8'h2C: begin s_axi_rdata <= now[31:0]; now_hi_shadow <= now[63:32]; end
                    8'h30: s_axi_rdata <= now_hi_shadow;
                    8'h34: s_axi_rdata <= ID_PPS1;
                    default: s_axi_rdata <= 32'd0;
                endcase
            end
            if (s_axi_rvalid && s_axi_rready) s_axi_rvalid <= 1'b0;
        end
    end
endmodule
