// SPDX-License-Identifier: BSD-2-Clause
// Kria K26 AXI4-Stream & AXI4-Lite Link Wrapper (XCK26-SFVC784-2LV-C)
//
// Bridges the 64b/66b PCS (link_pcs_rx + link_pcs_tx + link_rx_train_fsm) to:
//   - AXI4-Stream Master RX (m_axis_rx_*): 64-bit payload, TLAST on packet EOP,
//     TUSER[0] = crc_err latched from deframer /T/ validation, TID = stream_id,
//     elastic FIFO Absorbs arbitrary m_axis_rx_tready stalls.
//   - AXI4-Stream Slave TX  (s_axis_tx_*): 64-bit payload -> link_pcs_tx / link_pcs_single_tx,
//     with packet-length buffering when s_axis_tx_tuser[15:0] == 0.
//   - AXI4-Lite Slave CSR   (s_axi_*): LINK_PROTOCOL.md Section 7.2 registers (0x00..0x30).
//
// Mutation support:
//   -DMUTATE_IGNORE_TREADY : advances m_axis_rx output FIFO even when m_axis_rx_tready == 0

`timescale 1ns/1ps

module link_axis #(
    parameter integer RX_FIFO_DEPTH = 256,
    parameter integer TX_FIFO_DEPTH = 128
) (
    input  wire        clk,
    input  wire        rst,

    // -------------------------------------------------------------------------
    // AXI4-Stream Master RX (toward PS DMA / RF processing)
    // -------------------------------------------------------------------------
    output wire [63:0] m_axis_rx_tdata,
    output wire        m_axis_rx_tvalid,
    input  wire        m_axis_rx_tready,
    output wire        m_axis_rx_tlast,
    output wire [7:0]  m_axis_rx_tid,
    output wire [0:0]  m_axis_rx_tuser,   // [0] = crc_err (valid on tlast)

    // -------------------------------------------------------------------------
    // AXI4-Stream Slave TX (downlink command / telemetry -> PCS TX)
    // -------------------------------------------------------------------------
    input  wire [63:0] s_axis_tx_tdata,
    input  wire        s_axis_tx_tvalid,
    output wire        s_axis_tx_tready,
    input  wire        s_axis_tx_tlast,
    input  wire [7:0]  s_axis_tx_tid,
    input  wire [15:0] s_axis_tx_tuser,   // [15:0] = optional byte length (0 => auto words*8)

    // -------------------------------------------------------------------------
    // AXI4-Lite Slave CSR (LINK_PROTOCOL.md Section 7.2, 0x00 .. 0x30)
    // -------------------------------------------------------------------------
    input  wire [7:0]  s_axi_awaddr,
    input  wire        s_axi_awvalid,
    output wire        s_axi_awready,
    input  wire [31:0] s_axi_wdata,
    input  wire [3:0]  s_axi_wstrb,
    input  wire        s_axi_wvalid,
    output wire        s_axi_wready,
    output reg  [1:0]  s_axi_bresp,
    output reg         s_axi_bvalid,
    input  wire        s_axi_bready,
    input  wire [7:0]  s_axi_araddr,
    input  wire        s_axi_arvalid,
    output wire        s_axi_arready,
    output reg  [31:0] s_axi_rdata,
    output reg  [1:0]  s_axi_rresp,
    output reg         s_axi_rvalid,
    input  wire        s_axi_rready,

    // -------------------------------------------------------------------------
    // PCS RX Stream Inputs (from link_pcs_rx)
    // -------------------------------------------------------------------------
    input  wire        rx_out_valid,
    input  wire        rx_out_sop,
    input  wire        rx_out_eop,
    input  wire [7:0]  rx_out_stream_id,
    input  wire [15:0] rx_out_len,
    input  wire [31:0] rx_out_seq,
    input  wire [63:0] rx_out_timestamp,
    input  wire [63:0] rx_out_data,
    input  wire        rx_pkt_done_valid,
    input  wire        rx_pkt_done_ok,
    input  wire        rx_pkt_done_err,

    // -------------------------------------------------------------------------
    // PCS TX Stream Outputs (toward link_pcs_tx / link_pcs_single_tx)
    // -------------------------------------------------------------------------
    output reg         tx_pkt_valid,
    input  wire        tx_pkt_ready,
    output reg         tx_pkt_sop,
    output reg         tx_pkt_eop,
    output reg  [7:0]  tx_pkt_stream_id,
    output reg  [15:0] tx_pkt_len,
    output reg  [31:0] tx_pkt_seq,
    output wire [63:0] tx_pkt_timestamp,
    output reg  [63:0] tx_pkt_data,
    input  wire [63:0] timestamp_cnt,

    // -------------------------------------------------------------------------
    // Link Training & Control/Status Sideband (0x00 .. 0x30)
    // -------------------------------------------------------------------------
    output reg         ctrl_soft_rst,
    output reg         ctrl_loopback_en,
    output reg         ctrl_retrain_pulse,
    output reg         ctrl_tap_override_en,
    output reg         ctrl_prbs7_tx_en,
    output reg         ctrl_prbs7_rx_chk_en,
    output reg  [8:0]  cfg_tap_l0,
    output reg         cfg_load_l0,
    output reg  [8:0]  cfg_tap_l1,
    output reg         cfg_load_l1,

    input  wire [2:0]  st_train_state,
    input  wire        st_l0_block_lock,
    input  wire        st_l1_block_lock,
    input  wire        st_deskew_lock,
    input  wire        st_link_up,
    input  wire        st_idelayctrl_rdy,
    input  wire [7:0]  st_remote_status,
    input  wire [8:0]  active_tap_l0,
    input  wire [8:0]  active_tap_l1,
    input  wire [31:0] pcs_sh_err_cnt_l0,
    input  wire [31:0] pcs_sh_err_cnt_l1,
    input  wire [23:0] tx_dropped_cnt,
    input  wire [7:0]  skew_blocks,
    input  wire [15:0] am_seq,
    input  wire [31:0] pcs_prbs_err_cnt,
    input  wire [8:0]  eye_left_l0,
    input  wire [8:0]  eye_right_l0,
    input  wire [8:0]  eye_left_l1,
    input  wire [8:0]  eye_right_l1,

    // Latest received packet metadata snapshot (diagnostics / timestamp check)
    output reg  [31:0] last_rx_seq,
    output reg  [63:0] last_rx_timestamp,
    output reg  [15:0] last_rx_len
);

    localparam integer RX_AW = $clog2(RX_FIFO_DEPTH);
    localparam integer TX_AW = $clog2(TX_FIFO_DEPTH);

    // -------------------------------------------------------------------------
    // RX Elastic FIFO + Hold-Last-Word until Deframer /T/ CRC Decision
    //   Entry format [73:0]: {last_bit[73], crc_err[72], tid[71:64], tdata[63:0]}
    // -------------------------------------------------------------------------
    reg  [73:0] rx_fifo [0:RX_FIFO_DEPTH-1];
    reg  [RX_AW:0] rx_wr_ptr, rx_rd_ptr;
    wire [RX_AW:0] rx_count = rx_wr_ptr - rx_rd_ptr;
    wire           rx_empty = (rx_count == {(RX_AW+1){1'b0}});
    wire           rx_full  = (rx_count == RX_FIFO_DEPTH[RX_AW:0]);

    reg         hold_valid;
    reg  [63:0] hold_data;
    reg  [7:0]  hold_sid;
    reg         in_rx_pkt;
    reg  [7:0]  active_sid;
    reg  [7:0]  rx_fifo_drop_cnt;

    reg         rx_push_en;
    reg  [73:0] rx_push_word;

    always @* begin
        rx_push_en   = 1'b0;
        rx_push_word = 74'd0;
        if (hold_valid && rx_pkt_done_valid) begin
            rx_push_en   = 1'b1;
            rx_push_word = {1'b1, rx_pkt_done_err, hold_sid, hold_data};
        end else if (rx_pkt_done_valid && in_rx_pkt && !hold_valid) begin
            // Aborted frame interrupted before normal EOP word -> close TLAST with error
            rx_push_en   = 1'b1;
            rx_push_word = {1'b1, 1'b1, active_sid, 64'd0};
        end else if (rx_out_valid && !rx_out_eop) begin
            rx_push_en   = 1'b1;
            rx_push_word = {1'b0, 1'b0, rx_out_stream_id, rx_out_data};
        end
    end

    wire [73:0] rx_head = rx_fifo[rx_rd_ptr[RX_AW-1:0]];
    assign m_axis_rx_tvalid = ~rx_empty;
    assign m_axis_rx_tlast  = rx_empty ? 1'b0  : rx_head[73];
    assign m_axis_rx_tuser  = rx_empty ? 1'b0  : rx_head[72];
    assign m_axis_rx_tid    = rx_empty ? 8'd0  : rx_head[71:64];
    assign m_axis_rx_tdata  = rx_empty ? 64'd0 : rx_head[63:0];

`ifdef MUTATE_IGNORE_TREADY
    // Faulty FIFO read: pops every cycle regardless of downstream TREADY
    wire rx_pop = m_axis_rx_tvalid;
`else
    wire rx_pop = m_axis_rx_tvalid & m_axis_rx_tready;
`endif

    // Clearable diagnostic counters
    reg        clr_err_pulse;
    reg [31:0] pkt_cnt_rx_reg;
    reg [31:0] err_cnt_crc_reg;
    reg [31:0] sh0_base, sh1_base, prbs_base;

    wire [31:0] err_cnt_sh_l0 = (pcs_sh_err_cnt_l0 >= sh0_base) ? (pcs_sh_err_cnt_l0 - sh0_base) : pcs_sh_err_cnt_l0;
    wire [31:0] err_cnt_sh_l1 = (pcs_sh_err_cnt_l1 >= sh1_base) ? (pcs_sh_err_cnt_l1 - sh1_base) : pcs_sh_err_cnt_l1;
    wire [31:0] prbs_err_cnt  = (pcs_prbs_err_cnt  >= prbs_base) ? (pcs_prbs_err_cnt - prbs_base) : pcs_prbs_err_cnt;

    always @(posedge clk) begin
        if (rst || ctrl_soft_rst) begin
            rx_wr_ptr         <= {(RX_AW+1){1'b0}};
            rx_rd_ptr         <= {(RX_AW+1){1'b0}};
            hold_valid        <= 1'b0;
            hold_data         <= 64'd0;
            hold_sid          <= 8'd0;
            in_rx_pkt         <= 1'b0;
            active_sid        <= 8'd0;
            rx_fifo_drop_cnt  <= 8'd0;
            pkt_cnt_rx_reg    <= 32'd0;
            err_cnt_crc_reg   <= 32'd0;
            sh0_base          <= 32'd0;
            sh1_base          <= 32'd0;
            prbs_base         <= 32'd0;
            last_rx_seq       <= 32'd0;
            last_rx_timestamp <= 64'd0;
            last_rx_len       <= 16'd0;
        end else begin
            if (clr_err_pulse) begin
                err_cnt_crc_reg  <= 32'd0;
                rx_fifo_drop_cnt <= 8'd0;
                sh0_base         <= pcs_sh_err_cnt_l0;
                sh1_base         <= pcs_sh_err_cnt_l1;
                prbs_base        <= pcs_prbs_err_cnt;
            end

            if (rx_out_valid) begin
                active_sid <= rx_out_stream_id;
                if (rx_out_sop) begin
                    last_rx_seq       <= rx_out_seq;
                    last_rx_timestamp <= rx_out_timestamp;
                    last_rx_len       <= rx_out_len;
                end
                if (rx_out_eop) begin
                    hold_valid <= 1'b1;
                    hold_data  <= rx_out_data;
                    hold_sid   <= rx_out_stream_id;
                    in_rx_pkt  <= 1'b0;
                end else begin
                    in_rx_pkt  <= 1'b1;
                end
            end

            if (rx_pkt_done_valid) begin
                hold_valid <= 1'b0;
                in_rx_pkt  <= 1'b0;
                if (rx_pkt_done_ok && (pkt_cnt_rx_reg != 32'hFFFF_FFFF))
                    pkt_cnt_rx_reg <= pkt_cnt_rx_reg + 32'd1;
                if (rx_pkt_done_err && !clr_err_pulse && (err_cnt_crc_reg != 32'hFFFF_FFFF))
                    err_cnt_crc_reg <= err_cnt_crc_reg + 32'd1;
            end

            if (rx_push_en) begin
                if (!rx_full) begin
                    rx_fifo[rx_wr_ptr[RX_AW-1:0]] <= rx_push_word;
                    rx_wr_ptr <= rx_wr_ptr + {{RX_AW{1'b0}}, 1'b1};
                end else if (rx_fifo_drop_cnt != 8'hFF) begin
                    rx_fifo_drop_cnt <= rx_fifo_drop_cnt + 8'd1;
                end
            end

            if (rx_pop) begin
                rx_rd_ptr <= rx_rd_ptr + {{RX_AW{1'b0}}, 1'b1};
            end
        end
    end

    // -------------------------------------------------------------------------
    // AXI4-Stream Slave TX -> PCS TX Store-and-Forward Buffer
    //   Buffers one or more packets cleanly so pkt_len is known at pkt_sop,
    //   then drives link_pcs_tx (pkt_sop asserted through ST_IDLE/ST_TS until tx_pkt_ready).
    // -------------------------------------------------------------------------
    localparam integer TX_META_DEPTH = 16;
    reg  [72:0] tx_data_mem [0:TX_FIFO_DEPTH-1]; // {eop[72], sid[71:64], data[63:0]}
    reg  [TX_AW:0] tx_wr_ptr, tx_rd_ptr;
    wire [TX_AW:0] tx_data_free = TX_FIFO_DEPTH[TX_AW:0] - (tx_wr_ptr - tx_rd_ptr);

    reg  [23:0] tx_pkt_meta [0:TX_META_DEPTH-1]; // {len[15:0], sid[7:0]}
    reg  [4:0]  tx_m_wr, tx_m_rd;
    wire [4:0]  tx_m_cnt  = tx_m_wr - tx_m_rd;
    wire        tx_m_full = (tx_m_cnt == 5'd16);

    reg  [15:0] tx_in_words;
    reg  [15:0] tx_in_user_len;
    wire [15:0] next_tx_words  = tx_in_words + 16'd1;
    wire [15:0] latched_in_len = (tx_in_words == 16'd0) ? s_axis_tx_tuser : tx_in_user_len;
    wire [15:0] final_tx_len   = (latched_in_len != 16'd0) ? latched_in_len : (next_tx_words << 3);

    assign s_axis_tx_tready = (tx_data_free > {{TX_AW{1'b0}}, 1'b1}) && !tx_m_full && !rst && !ctrl_soft_rst;
    assign tx_pkt_timestamp = timestamp_cnt;

    localparam [1:0] TX_IDLE = 2'd0,
                     TX_SEND = 2'd1;
    reg [1:0] tx_fsm;

    always @(posedge clk) begin
        if (rst || ctrl_soft_rst) begin
            tx_wr_ptr      <= {(TX_AW+1){1'b0}};
            tx_rd_ptr      <= {(TX_AW+1){1'b0}};
            tx_m_wr        <= 5'd0;
            tx_m_rd        <= 5'd0;
            tx_in_words    <= 16'd0;
            tx_in_user_len <= 16'd0;
            tx_fsm         <= TX_IDLE;
            tx_pkt_valid   <= 1'b0;
            tx_pkt_sop     <= 1'b0;
            tx_pkt_eop     <= 1'b0;
            tx_pkt_stream_id <= 8'd0;
            tx_pkt_len     <= 16'd0;
            tx_pkt_seq     <= 32'd0;
            tx_pkt_data    <= 64'd0;
        end else begin
            // Capture incoming AXI-Stream TX beats
            if (s_axis_tx_tvalid && s_axis_tx_tready) begin
                tx_data_mem[tx_wr_ptr[TX_AW-1:0]] <= {s_axis_tx_tlast, s_axis_tx_tid, s_axis_tx_tdata};
                tx_wr_ptr <= tx_wr_ptr + {{TX_AW{1'b0}}, 1'b1};
                if (tx_in_words == 16'd0)
                    tx_in_user_len <= s_axis_tx_tuser;
                if (s_axis_tx_tlast) begin
                    tx_pkt_meta[tx_m_wr[3:0]] <= {final_tx_len, s_axis_tx_tid};
                    tx_m_wr        <= tx_m_wr + 5'd1;
                    tx_in_words    <= 16'd0;
                    tx_in_user_len <= 16'd0;
                end else begin
                    tx_in_words <= next_tx_words;
                end
            end

            // Drive link_pcs_tx / link_pcs_single_tx packet interface
            case (tx_fsm)
                TX_IDLE: begin
                    if (tx_m_cnt != 5'd0) begin
                        tx_pkt_valid     <= 1'b1;
                        tx_pkt_sop       <= 1'b1;
                        tx_pkt_eop       <= tx_data_mem[tx_rd_ptr[TX_AW-1:0]][72];
                        tx_pkt_stream_id <= tx_pkt_meta[tx_m_rd[3:0]][7:0];
                        tx_pkt_len       <= tx_pkt_meta[tx_m_rd[3:0]][23:8];
                        tx_pkt_data      <= tx_data_mem[tx_rd_ptr[TX_AW-1:0]][63:0];
                        tx_fsm           <= TX_SEND;
                    end else begin
                        tx_pkt_valid <= 1'b0;
                        tx_pkt_sop   <= 1'b0;
                        tx_pkt_eop   <= 1'b0;
                    end
                end
                TX_SEND: begin
                    if (tx_pkt_valid && tx_pkt_ready) begin
                        tx_rd_ptr <= tx_rd_ptr + {{TX_AW{1'b0}}, 1'b1};
                        if (tx_pkt_eop) begin
                            tx_m_rd      <= tx_m_rd + 5'd1;
                            tx_pkt_seq   <= tx_pkt_seq + 32'd1;
                            tx_pkt_valid <= 1'b0;
                            tx_pkt_sop   <= 1'b0;
                            tx_pkt_eop   <= 1'b0;
                            tx_fsm       <= TX_IDLE;
                        end else begin
                            tx_pkt_sop  <= 1'b0;
                            tx_pkt_eop  <= tx_data_mem[(tx_rd_ptr + {{TX_AW{1'b0}}, 1'b1}) & {TX_AW{1'b1}}][72];
                            tx_pkt_data <= tx_data_mem[(tx_rd_ptr + {{TX_AW{1'b0}}, 1'b1}) & {TX_AW{1'b1}}][63:0];
                        end
                    end
                end
            endcase
        end
    end

    // -------------------------------------------------------------------------
    // AXI4-Lite Slave CSR (LINK_PROTOCOL.md Section 7.2, offsets 0x00 .. 0x30)
    // -------------------------------------------------------------------------
    reg        aw_captured, w_captured;
    reg [7:0]  aw_addr_reg;
    reg [31:0] w_data_reg;
    reg [3:0]  w_strb_reg;

    assign s_axi_awready = ~aw_captured && ~s_axi_bvalid;
    assign s_axi_wready  = ~w_captured  && ~s_axi_bvalid;
    assign s_axi_arready = ~s_axi_rvalid;

    function [31:0] csr_read;
        input [7:0] addr;
        begin
            case (addr[7:2])
                6'h00: csr_read = {25'd0, 1'b0, ctrl_prbs7_rx_chk_en, ctrl_prbs7_tx_en,
                                   ctrl_tap_override_en, 1'b0, ctrl_loopback_en, ctrl_soft_rst};
                6'h01: csr_read = {8'd0, st_remote_status, 8'd0,
                                   st_idelayctrl_rdy, st_link_up, st_deskew_lock,
                                   st_l1_block_lock, st_l0_block_lock, st_train_state};
                6'h02: csr_read = {7'd0, active_tap_l0, 7'd0, cfg_tap_l0};
                6'h03: csr_read = {7'd0, active_tap_l1, 7'd0, cfg_tap_l1};
                6'h04: csr_read = err_cnt_sh_l0;
                6'h05: csr_read = err_cnt_sh_l1;
                6'h06: csr_read = err_cnt_crc_reg;
                6'h07: csr_read = pkt_cnt_rx_reg;
                6'h08: csr_read = {rx_fifo_drop_cnt, tx_dropped_cnt};
                6'h09: csr_read = {8'd0, am_seq, skew_blocks};
                6'h0A: csr_read = prbs_err_cnt;
                6'h0B: csr_read = {7'd0, eye_right_l0, 7'd0, eye_left_l0};
                6'h0C: csr_read = {7'd0, eye_right_l1, 7'd0, eye_left_l1};
                default: csr_read = 32'h0000_0000;
            endcase
        end
    endfunction

    wire        wr_fire_now   = (aw_captured || (s_axi_awvalid && s_axi_awready)) &&
                                (w_captured  || (s_axi_wvalid  && s_axi_wready))  &&
                                !s_axi_bvalid;
    wire [7:0]  wr_addr_eff   = aw_captured ? aw_addr_reg : s_axi_awaddr;
    wire [31:0] wr_data_eff   = w_captured  ? w_data_reg  : s_axi_wdata;
    wire [3:0]  wr_strb_eff   = w_captured  ? w_strb_reg  : s_axi_wstrb;

    always @(posedge clk) begin
        if (rst) begin
            ctrl_soft_rst        <= 1'b0;
            ctrl_loopback_en     <= 1'b0;
            ctrl_retrain_pulse   <= 1'b0;
            ctrl_tap_override_en <= 1'b0;
            ctrl_prbs7_tx_en     <= 1'b0;
            ctrl_prbs7_rx_chk_en <= 1'b0;
            clr_err_pulse        <= 1'b0;
            cfg_tap_l0           <= 9'd0;
            cfg_load_l0          <= 1'b0;
            cfg_tap_l1           <= 9'd0;
            cfg_load_l1          <= 1'b0;
            aw_captured          <= 1'b0;
            w_captured           <= 1'b0;
            aw_addr_reg          <= 8'd0;
            w_data_reg           <= 32'd0;
            w_strb_reg           <= 4'd0;
            s_axi_bvalid         <= 1'b0;
            s_axi_bresp          <= 2'b00;
            s_axi_rvalid         <= 1'b0;
            s_axi_rresp          <= 2'b00;
            s_axi_rdata          <= 32'd0;
        end else begin
            ctrl_retrain_pulse <= 1'b0;
            clr_err_pulse      <= 1'b0;
            cfg_load_l0        <= 1'b0;
            cfg_load_l1        <= 1'b0;

            if (s_axi_bvalid && s_axi_bready)
                s_axi_bvalid <= 1'b0;

            if (s_axi_awvalid && s_axi_awready) begin
                aw_captured <= 1'b1;
                aw_addr_reg <= s_axi_awaddr;
            end
            if (s_axi_wvalid && s_axi_wready) begin
                w_captured <= 1'b1;
                w_data_reg <= s_axi_wdata;
                w_strb_reg <= s_axi_wstrb;
            end

            if (wr_fire_now) begin
                aw_captured  <= 1'b0;
                w_captured   <= 1'b0;
                s_axi_bvalid <= 1'b1;
                s_axi_bresp  <= 2'b00;
                case (wr_addr_eff[7:2])
                    6'h00: begin
                        if (wr_strb_eff[0]) begin
                            ctrl_soft_rst        <= wr_data_eff[0];
                            ctrl_loopback_en     <= wr_data_eff[1];
                            ctrl_retrain_pulse   <= wr_data_eff[2];
                            ctrl_tap_override_en <= wr_data_eff[3];
                            ctrl_prbs7_tx_en     <= wr_data_eff[4];
                            ctrl_prbs7_rx_chk_en <= wr_data_eff[5];
                            clr_err_pulse        <= wr_data_eff[6];
                        end
                    end
                    6'h02: begin
                        if (wr_strb_eff[0]) cfg_tap_l0[7:0] <= wr_data_eff[7:0];
                        if (wr_strb_eff[1]) cfg_tap_l0[8]   <= wr_data_eff[8];
                        if (wr_strb_eff[3]) cfg_load_l0     <= wr_data_eff[31];
                    end
                    6'h03: begin
                        if (wr_strb_eff[0]) cfg_tap_l1[7:0] <= wr_data_eff[7:0];
                        if (wr_strb_eff[1]) cfg_tap_l1[8]   <= wr_data_eff[8];
                        if (wr_strb_eff[3]) cfg_load_l1     <= wr_data_eff[31];
                    end
                    default: ;
                endcase
            end

            if (s_axi_arvalid && s_axi_arready) begin
                s_axi_rvalid <= 1'b1;
                s_axi_rresp  <= 2'b00;
                s_axi_rdata  <= csr_read(s_axi_araddr);
            end else if (s_axi_rvalid && s_axi_rready) begin
                s_axi_rvalid <= 1'b0;
            end
        end
    end

endmodule
