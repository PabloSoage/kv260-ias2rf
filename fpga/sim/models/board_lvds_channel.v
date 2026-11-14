// SPDX-License-Identifier: BSD-2-Clause
// Behavioral PCB + Package + Carrier Differential LVDS Channel Model
//
// Models:
//   - Independent per-leg propagation delays (DLY_P_PS, DLY_N_PS) matching
//     _work/layout/lvds_skew.py + PINMAP.md K26 SOM/carrier delays.
//   - Zero-crossing ISI / eye-spread + uniform PRNG timing jitter
//     (JITTER_SPREAD_PS) calibrated to docs/SIGNAL_INTEGRITY.md §3.3, §8, §9.7.
//   - Transport-delay non-blocking assignments so multi-UI delays (>1000 ps @ 1 Gbps)
//     preserve every transition without inertial pulse swallowing.
//   - Dynamic fault / glitch injection hooks for failover and retrain scenarios.

`timescale 1ps/10fs

module sim_board_lvds_channel #(
    parameter real    DLY_P_PS         = 1000.0,
    parameter real    DLY_N_PS         = 1000.0,
    parameter real    JITTER_SPREAD_PS = 20.0,
    parameter integer SEED             = 32'h1357_2468
) (
    input  wire tx_p,
    input  wire tx_n,
    input  wire cut_fault,
    input  wire glitch_inj,
    output reg  rx_p,
    output reg  rx_n
);
    reg [31:0] prng = SEED;
    integer    jit_int_ps;
    integer    dly_p_int, dly_n_int, spread_int;
    integer    eff_p_ps, eff_n_ps;

    initial begin
        rx_p       = 1'b0;
        rx_n       = 1'b1;
        dly_p_int  = DLY_P_PS;
        dly_n_int  = DLY_N_PS;
        spread_int = JITTER_SPREAD_PS;
    end

    // Update shared differential edge jitter via fast integer PRNG (preserves
    // static PCB P/N skew DLY_P_PS-DLY_N_PS while avoiding spurious I==IB X states).
    always @(tx_p or tx_n or cut_fault or glitch_inj) begin
        prng       = {prng[30:0], prng[31] ^ prng[21] ^ prng[1] ^ prng[0]};
        jit_int_ps = (($signed({1'b0, prng[7:0]}) - 128) * spread_int) >>> 8;
        eff_p_ps   = dly_p_int + jit_int_ps;
        eff_n_ps   = dly_n_int + jit_int_ps;
        if (eff_p_ps < 1) eff_p_ps = 1;
        if (eff_n_ps < 1) eff_n_ps = 1;

        if (cut_fault) begin
            rx_p <= #(eff_p_ps) 1'b0;
            rx_n <= #(eff_n_ps) 1'b1;
        end else begin
            rx_p <= #(eff_p_ps) (glitch_inj ? ~tx_p : tx_p);
            rx_n <= #(eff_n_ps) (glitch_inj ? ~tx_n : tx_n);
        end
    end
endmodule
