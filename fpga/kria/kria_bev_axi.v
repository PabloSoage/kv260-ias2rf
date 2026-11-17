`timescale 1ns / 1ps
// kria_bev_axi: kria_bev_grid (fpga/kria/integrations/) on the K26's buses.
//
// The grid core takes 36-bit commands on a stream and dumps its 65,536 cells on another. This wrapper gives it:
//
//  - AXI4-Lite registers for the per-sensor configuration and a command port. A command is two writes: DET_XY
//    (staged) then DET_CMD, which pushes {DET_CMD[3:0], DET_XY} into a 512-entry queue. The A53s or R5F core 1
//    write the 77 GHz radar's objects, the 10.5 GHz radar's detections and the decay passes this way; at two
//    writes per detection a core sustains well over a million detections a second, far above the radars' few
//    thousand.
//  - An AXI4-Stream command input (s_axis_det, one command in the low 36 bits of each 64-bit beat) for a source
//    that needs more, such as a LiDAR point cloud through a DMA. The queue has priority, so register commands are
//    never stuck behind a long stream; within each source the order is kept.
//  - The dump on m_axis (8 cells per beat, tlast on the 8,192nd), for an AXI DMA S2MM into DDR: 64 KiB per frame
//    in about 82 us at 100 MHz.
//
// Configuration takes effect at once: change it only while STATUS shows the queue empty and the core idle.
//
// Registers (AXI4-Lite, 32-bit, byte addresses):
//   0x00 ID        "BEV1"
//   0x04 STATUS    [0] busy (core running a ray, decay or dump), [1] queue full, [2] overflow (W1C: a DET_CMD
//                  write found the queue full and was dropped), [3] queue empty, [25:16] queue level
//   0x08 ORIGIN_X  [8k+7:8k] origin x cell of sensor k (128 = grid centre)
//   0x0C ORIGIN_Y  [8k+7:8k] origin y cell of sensor k
//   0x10 HIT       [7k+6:7k] increment for a detection of sensor k
//   0x14 MISS      [7k+6:7k] decrement for a cell a beam of sensor k crossed
//   0x18 RAY       [3:0] ray casting on for sensor k
//   0x1C DET_XY    [15:0] x, [31:16] y: signed Q8.8 cells from the grid centre (staged; read back)
//   0x20 DET_CMD   W: [1:0] sensor, [3:2] command (0 detection, 1 decay pass, 2 dump); pushes the command
//   0x24 COUNT     commands the core has accepted, from both sources (RO, wraps)
//
// At reset the origins are 128 (the centre), HIT, MISS and RAY are 0: nothing changes the grid until software
// configures it.
module kria_bev_axi #(
    parameter integer DECAY_SHIFT = 3,
    parameter integer QUEUE_LOG2  = 9
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 clk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axi:m_axis:s_axis_det, ASSOCIATED_RESET resetn" *)
    input  wire        clk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 resetn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input  wire        resetn,

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
    input  wire        s_axi_rready,

    input  wire [63:0] s_axis_det_tdata,
    input  wire        s_axis_det_tvalid,
    output wire        s_axis_det_tready,

    output wire [63:0] m_axis_tdata,
    output wire [7:0]  m_axis_tkeep,
    output wire        m_axis_tvalid,
    output wire        m_axis_tlast,
    input  wire        m_axis_tready
);
    localparam [31:0] ID_BEV1 = 32'h4245_5631;   // "BEV1"
    localparam integer QD = 1 << QUEUE_LOG2;

    // --------------------------------------------------------------- registers
    reg [31:0] origin_x, origin_y, det_xy, count;
    reg [27:0] hit, miss;
    reg [3:0]  ray;
    reg        overflow;

    // --------------------------------------------------------------- queue
    (* ram_style = "distributed" *) reg [35:0] q_mem [0:QD-1];
    reg [QUEUE_LOG2:0]   q_level;
    reg [QUEUE_LOG2-1:0] q_wp, q_rp;
    wire q_empty = (q_level == 0);
    wire q_full  = (q_level == QD);
    reg        q_push;
    reg [35:0] q_din;

    // --------------------------------------------------------------- core input mux
    wire        c_ready;
    wire        use_q   = !q_empty;
    wire [35:0] c_data  = use_q ? q_mem[q_rp] : s_axis_det_tdata[35:0];
    wire        c_valid = use_q | s_axis_det_tvalid;
    wire        q_pop   = use_q && c_ready;
    assign s_axis_det_tready = !use_q && c_ready;

    wire busy;
    kria_bev_grid #(.DECAY_SHIFT(DECAY_SHIFT)) u_grid (
        .clk(clk), .rst(!resetn),
        .s_tdata(c_data), .s_tvalid(c_valid), .s_tready(c_ready),
        .m_tdata(m_axis_tdata), .m_tvalid(m_axis_tvalid), .m_tlast(m_axis_tlast), .m_tready(m_axis_tready),
        .cfg_origin_x(origin_x), .cfg_origin_y(origin_y), .cfg_hit(hit), .cfg_miss(miss), .cfg_ray(ray),
        .busy(busy)
    );
    assign m_axis_tkeep = 8'hFF;

    always @(posedge clk) begin
        if (q_push && !q_full) q_mem[q_wp] <= q_din;
    end

    always @(posedge clk) begin
        if (!resetn) begin
            q_level <= 0; q_wp <= 0; q_rp <= 0; count <= 32'd0;
        end else begin
            if (q_push && !q_full) q_wp <= q_wp + 1'b1;
            if (q_pop) q_rp <= q_rp + 1'b1;
            q_level <= q_level + ((q_push && !q_full) ? 1'b1 : 1'b0) - (q_pop ? 1'b1 : 1'b0);
            if (c_valid && c_ready) count <= count + 32'd1;
        end
    end

    // ------------------------------------------------------------ AXI4-Lite
    reg        aw_got, w_got;
    reg [7:0]  aw_q;
    reg [31:0] w_q;

    always @(posedge clk) begin
        if (!resetn) begin
            s_axi_awready <= 1'b0; s_axi_wready <= 1'b0;
            s_axi_bvalid <= 1'b0; s_axi_bresp <= 2'b00;
            s_axi_arready <= 1'b0; s_axi_rvalid <= 1'b0; s_axi_rresp <= 2'b00; s_axi_rdata <= 32'd0;
            aw_got <= 1'b0; w_got <= 1'b0; aw_q <= 8'd0; w_q <= 32'd0;
            origin_x <= 32'h8080_8080; origin_y <= 32'h8080_8080;
            hit <= 28'd0; miss <= 28'd0; ray <= 4'd0; det_xy <= 32'd0; overflow <= 1'b0;
            q_push <= 1'b0; q_din <= 36'd0;
        end else begin
            q_push        <= 1'b0;
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
                aw_got <= 1'b0; w_got <= 1'b0;
                s_axi_bvalid <= 1'b1; s_axi_bresp <= 2'b00;
                case ({aw_q[7:2], 2'b00})
                    8'h04: if (w_q[2]) overflow <= 1'b0;
                    8'h08: origin_x <= w_q;
                    8'h0C: origin_y <= w_q;
                    8'h10: hit  <= w_q[27:0];
                    8'h14: miss <= w_q[27:0];
                    8'h18: ray  <= w_q[3:0];
                    8'h1C: det_xy <= w_q;
                    8'h20: begin
                        // The level seen here lags a push by one clock; back-to-back pushes are two AXI writes
                        // apart, so q_full is always current when the next one arrives.
                        if (q_full) overflow <= 1'b1;
                        else begin
                            q_push <= 1'b1;
`ifdef MUTATE_BEV_AXI_NO_STAGE
                            q_din  <= {w_q[3:0], w_q};
`else
                            q_din  <= {w_q[3:0], det_xy};
`endif
                        end
                    end
                    default: ;
                endcase
            end
            if (s_axi_bvalid && s_axi_bready) s_axi_bvalid <= 1'b0;

            if (s_axi_arvalid && !s_axi_rvalid && !s_axi_arready) begin
                s_axi_arready <= 1'b1;
                s_axi_rvalid  <= 1'b1;
                s_axi_rresp   <= 2'b00;
                case ({s_axi_araddr[7:2], 2'b00})
                    8'h00: s_axi_rdata <= ID_BEV1;
                    8'h04: s_axi_rdata <= {{(15-QUEUE_LOG2){1'b0}}, q_level, 12'd0, q_empty, overflow, q_full, busy};
                    8'h08: s_axi_rdata <= origin_x;
                    8'h0C: s_axi_rdata <= origin_y;
                    8'h10: s_axi_rdata <= {4'd0, hit};
                    8'h14: s_axi_rdata <= {4'd0, miss};
                    8'h18: s_axi_rdata <= {28'd0, ray};
                    8'h1C: s_axi_rdata <= det_xy;
                    8'h24: s_axi_rdata <= count;
                    default: s_axi_rdata <= 32'd0;
                endcase
            end
            if (s_axi_rvalid && s_axi_rready) s_axi_rvalid <= 1'b0;
        end
    end
endmodule
