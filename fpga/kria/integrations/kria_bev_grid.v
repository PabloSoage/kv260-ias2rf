`timescale 1ns / 1ps
// ============================================================================
// kria_bev_grid: bird's-eye-view occupancy grid for sensor fusion (a possible integration, docs/INTEGRATIONS.md).
//
// A 256 x 256 grid of signed 8-bit log-odds cells around the vehicle; the host sets the cell size (0.5 m gives
// 128 m x 128 m). Detections arrive on s_axis already transformed to the vehicle frame:
//   s_tdata[15:0]  x, signed Q8.8 cells from the grid centre (forward)
//   s_tdata[31:16] y, signed Q8.8 cells from the grid centre (left)
//   s_tdata[33:32] sensor: 0 LiDAR, 1 77 GHz radar, 2 10.5 GHz radar, 3 spare
//   s_tdata[35:34] command: 0 detection, 1 decay pass, 2 dump the grid on m_axis
// A detection adds hit[sensor] to its cell. If ray[sensor] is set, every cell on the straight line from the
// sensor's origin up to it (Bresenham, one cell per clock) first gets -miss[sensor]: the beam went through, so
// that space is free. Cells saturate at +-127. A decay pass moves every cell toward 0 by max(1, |v| >> DECAY_SHIFT),
// so obstacles that are not seen again fade. A dump streams the 65,536 cells, eight per 64-bit beat, cell
// address {x cell, y cell} ascending, the lowest address in the low byte.
//
// Throughput: one cell update per clock, 100 M/s at 100 MHz (a 1.3 Mpoint/s LiDAR with 60-cell rays needs 78 M/s).
// Memory: one 64 K x 8 simple dual-port RAM. Updates are a three-stage read-modify-write (issue, read, write) with
// one forwarding path, so back-to-back updates of one cell are exact. s_tready is low while a ray, a decay pass
// or a dump runs.
// ============================================================================
module kria_bev_grid #(
    parameter integer DECAY_SHIFT = 3
) (
    input  wire        clk,
    input  wire        rst,
    input  wire [35:0] s_tdata,
    input  wire        s_tvalid,
    output wire        s_tready,
    output reg  [63:0] m_tdata,
    output reg         m_tvalid,
    output reg         m_tlast,
    input  wire        m_tready,
    input  wire [31:0] cfg_origin_x,   // [8k+7:8k]: origin x cell of sensor k (0..255, 128 = grid centre)
    input  wire [31:0] cfg_origin_y,   // [8k+7:8k]: origin y cell of sensor k
    input  wire [27:0] cfg_hit,        // [7k+6:7k]: increment for a detection of sensor k
    input  wire [27:0] cfg_miss,       // [7k+6:7k]: decrement for a cell a beam of sensor k crossed
    input  wire [3:0]  cfg_ray,        // ray casting on for sensor k
    output wire        busy
);
    (* ram_style = "block" *) reg signed [7:0] grid [0:65535];
    integer gi;
    initial for (gi = 0; gi < 65536; gi = gi + 1) grid[gi] = 8'sd0;

    localparam [1:0] S_IDLE = 2'd0, S_RAY = 2'd1, S_DECAY = 2'd2, S_DUMP = 2'd3;
    reg [1:0] st;
    assign s_tready = (st == S_IDLE) && !rst;
    assign busy     = (st != S_IDLE);

    wire [1:0] in_s = s_tdata[33:32];
    wire [1:0] in_c = s_tdata[35:34];
    wire [7:0] hx   = s_tdata[15:8]  + 8'd128;     // integer part of Q8.8, offset to the grid centre
    wire [7:0] hy   = s_tdata[31:24] + 8'd128;
    wire [7:0] ox   = cfg_origin_x[8*in_s +: 8];
    wire [7:0] oy   = cfg_origin_y[8*in_s +: 8];
    wire signed [9:0] adx = (hx >= ox) ? $signed({2'b00, hx - ox}) : $signed({2'b00, ox - hx});
    wire signed [9:0] ady = (hy >= oy) ? $signed({2'b00, hy - oy}) : $signed({2'b00, oy - hy});

    // Bresenham state
    reg [7:0]         bx, by, bx1, by1;
    reg signed [9:0]  bdx, bdy, berr;      // bdy is -|dy|
    reg               bsx, bsy;            // 1: step +1, 0: step -1
    reg [1:0]         bsen;
    wire signed [10:0] e2 = {berr, 1'b0};
    wire              stx = (e2 >= bdy);
    wire              sty = (e2 <= bdx);
    wire              at_end = (bx == bx1) && (by == by1);

    // stage 1: issue
    reg               u1_v, u1_decay;
    reg [15:0]        u1_a;
    reg signed [8:0]  u1_d;
    reg [15:0]        sweep;

    // dump (acc gathers eight cells; rd_q is the RAM's read data)
    reg  [63:0]       acc;
    reg  signed [7:0] rd_q;
    reg [12:0] dbeat;
    reg [3:0]  dk;
    reg        dhold;
    reg [1:0]  dwait;          // lets updates still in the pipeline land before the first read

    always @(posedge clk) begin
        if (rst) begin
            st <= S_IDLE; u1_v <= 1'b0; u1_decay <= 1'b0; sweep <= 16'd0;
            dbeat <= 13'd0; dk <= 4'd0; dhold <= 1'b0; dwait <= 2'd0; m_tvalid <= 1'b0; m_tlast <= 1'b0;
        end else begin
            u1_v <= 1'b0; u1_decay <= 1'b0;
            case (st)
                S_IDLE: if (s_tvalid) begin
                    case (in_c)
                        2'd1: begin st <= S_DECAY; sweep <= 16'd0; end
                        2'd2: begin st <= S_DUMP; dbeat <= 13'd0; dk <= 4'd0; dhold <= 1'b0; dwait <= 2'd3; end
                        2'd0: begin
                            if (cfg_ray[in_s] && !(ox == hx && oy == hy)) begin
                                st   <= S_RAY;
                                bx   <= ox;  by  <= oy;  bx1 <= hx;  by1 <= hy;
                                bdx  <= adx; bdy <= -ady; berr <= adx - ady;
                                bsx  <= (hx >= ox); bsy <= (hy >= oy);
                                bsen <= in_s;
                            end else begin
                                u1_v <= 1'b1; u1_a <= {hx, hy};
                                u1_d <= {2'b00, cfg_hit[7*in_s +: 7]};
                            end
                        end
                        default: ;
                    endcase
                end
                S_RAY: begin
                    u1_v <= 1'b1;
                    u1_a <= {bx, by};
                    if (at_end) begin
                        u1_d <= {2'b00, cfg_hit[7*bsen +: 7]};
                        st   <= S_IDLE;
                    end else begin
                        u1_d <= -$signed({2'b00, cfg_miss[7*bsen +: 7]});
                        berr <= berr + (stx ? bdy : 10'sd0) + (sty ? bdx : 10'sd0);
                        if (stx) bx <= bsx ? bx + 8'd1 : bx - 8'd1;
                        if (sty) by <= bsy ? by + 8'd1 : by - 8'd1;
                    end
                end
                S_DECAY: begin
                    u1_v <= 1'b1; u1_decay <= 1'b1; u1_a <= sweep; u1_d <= 9'sd0;
                    sweep <= sweep + 16'd1;
                    if (sweep == 16'hFFFF) st <= S_IDLE;
                end
                S_DUMP: begin
                    // read eight cells (dk 0..7; the RAM's data for dk-1 arrives with dk), then hold the beat
                    if (dwait != 2'd0) begin
                        dwait <= dwait - 2'd1;
                    end else if (!dhold) begin
                        dk <= dk + 4'd1;
                        if (dk != 4'd0) acc <= {rd_q, acc[63:8]};
                        if (dk == 4'd8) begin
                            m_tdata  <= {rd_q, acc[63:8]};
                            m_tvalid <= 1'b1;
                            m_tlast  <= (dbeat == 13'h1FFF);
                            dhold    <= 1'b1;
                        end
                    end else if (m_tready) begin
                        m_tvalid <= 1'b0; m_tlast <= 1'b0; dhold <= 1'b0; dk <= 4'd0;
                        dbeat <= dbeat + 13'd1;
                        if (dbeat == 13'h1FFF) st <= S_IDLE;
                    end
                end
            endcase
        end
    end

    // ---------------- RAM: one read port (updates, or the dump), one write port ----------------
    wire [15:0]       rd_a = (st == S_DUMP) ? {dbeat, dk[2:0]} : u1_a;
    reg               u2_v, u2_decay, u3_v;
    reg [15:0]        u2_a, u3_a;
    reg signed [8:0]  u2_d;
    reg signed [7:0]  u3_val;
    always @(posedge clk) begin
        rd_q     <= grid[rd_a];
        u2_v     <= u1_v && !rst;
        u2_a     <= u1_a; u2_d <= u1_d; u2_decay <= u1_decay;
    end
    // stage 3: the cell's current value (the write of the previous clock forwarded if it is the same cell)
`ifdef MUTATE_BEV_NO_FORWARD
    wire signed [7:0]  cur  = rd_q;
`else
    wire signed [7:0]  cur  = (u3_v && u3_a == u2_a) ? u3_val : rd_q;
`endif
    wire signed [9:0]  sum  = cur + u2_d;
    wire [7:0]         mag  = cur[7] ? -cur : cur;
    wire [7:0]         step = ((mag >> DECAY_SHIFT) == 8'd0) ? ((mag == 8'd0) ? 8'd0 : 8'd1) : (mag >> DECAY_SHIFT);
    wire signed [7:0]  dec  = cur[7] ? cur + $signed(step) : cur - $signed(step);
    wire signed [7:0]  nv   = u2_decay ? dec
                            : (sum > 10'sd127)  ? 8'sd127
                            : (sum < -10'sd127) ? -8'sd127 : sum[7:0];
    always @(posedge clk) begin
        u3_v <= u2_v && !rst; u3_a <= u2_a; u3_val <= nv;
        if (u2_v) grid[u2_a] <= nv;
    end
endmodule
