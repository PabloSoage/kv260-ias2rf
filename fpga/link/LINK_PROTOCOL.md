# IAS1-to-RF LVDS Link Protocol & PCS Specification

**Scope:** Line coding, scrambling, gearbox, framing, 2-lane striping/deskew, training state machine, packet format, and register map for the bidirectional AC-coupled LVDS link between the Artix-7 RF/DAQ FPGA (`XC7A50T-FTG256`) and Kria K26 (`XCK26-SFVC784`).

---

## 1. Physical & PCS Layering

| Direction | Data Lanes | Clock Pair | Raw Rate / Lane (Nom.) | Aggregate Raw Rate | Net 64b/66b Rate | SERDES Width | Parallel Clock (`CLKDIV`) |
| :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| **Uplink (Artix -> Kria)** | 2 (`LINK_RX_D0`, `LINK_RX_D1`) | `LINK_RX_CLK` (500 MHz DDR) | 1.0 Gb/s | **2.0 Gb/s** | 1.939 Gb/s | 8-bit DDR | 125 MHz |
| **Downlink (Kria -> Artix)** | 1 (`LINK_TX_D0`) | `LINK_TX_CLK` (500 MHz DDR) | 1.0 Gb/s | **1.0 Gb/s** | 0.970 Gb/s | 8-bit DDR | 125 MHz |

- **Rate scaling (`link-decisions.md` #6):** All PCS and SERDES RTL is clock-rate agnostic; `400 MHz DDR` (`800 Mb/s/lane`, `CLKDIV = 100 MHz`) and `500 MHz DDR` (`1.0 Gb/s/lane`, `CLKDIV = 125 MHz`, nominal operating point) run on the exact same gateware.
- **Forwarded clock (`link-decisions.md` #8):** Edge-aligned source-synchronous forwarding driven by an `OSERDES` lane transmitting constant `8'b1010_1010` (`10101010` LSB-first = `0,1,0,1,0,1,0,1` on wire) from the same serial/parallel clocks as the data lanes. Each receiver independently centers the sampling eye with `IDELAY`.
- **Bit ordering on wire (LSB-first):** Within each parallel SERDES byte `tx_byte[7:0]`, bit `0` (`tx_byte[0]`) is transmitted first in time and bit `7` (`tx_byte[7]`) last. Within each 66-bit block `blk[65:0]`, `sync[1:0] = blk[1:0]` is transmitted first (`blk[0]` then `blk[1]`), followed by payload bits `blk[2]` through `blk[65]`.
- **AC-coupling DC balance:** All `LINK_*` pairs are AC-coupled through 100 nF series capacitors (`C101`–`C110`). IEEE 802.3 Clause 49 self-synchronous scrambling bounds continuous run length and keeps DC baseline wander within the 100 nF + 100 Ω (`τ = 10 µs` high-pass) time constant.

---

## 2. 64b/66b Block Format

Each 66-bit block on a physical lane is formed as `{payload[63:0], sync[1:0]}`:

| `sync[1:0]` | Class | `btype = payload[7:0]` | Symbol | Unscrambled `payload[63:0]` Layout (MSB..LSB) | Purpose |
| :---: | :--- | :---: | :---: | :--- | :--- |
| `2'b01` | **Data** | *(all 64 bits)* | `/D/` | `data[63:0]` | 64-bit packet timestamp or payload word |
| `2'b10` | **Control** | `8'h1E` | `/I/` (`BTYPE_IDLE`) | `{40'h0, remote_status[15:0], 8'h1E}` | Idle / training fill block & link health feedback |
| `2'b10` | **Control** | `8'h4B` | `/A/` (`BTYPE_ALIGN`) | `{32'h9A_C5_3C_69, am_seq[15:0], lane_id[7:0], 8'h4B}` | Periodic 2-lane Alignment Marker (`AM_PERIOD` blocks) |
| `2'b10` | **Control** | `8'h78` | `/S/` (`BTYPE_START`) | `{seq_num[31:0], pkt_len[15:0], stream_id[7:0], 8'h78}` | Start of Packet header |
| `2'b10` | **Control** | `8'hFF` | `/T/` (`BTYPE_TERM`) | `{dropped_cnt[23:0], crc32[31:0], 8'hFF}` | End of Packet trailer (IEEE CRC-32 + drop count) |
| `2'b10` | **Control** | `8'h55` | `/C/` (`BTYPE_CTRL`) | `{ctrl_arg[39:0], ctrl_op[15:0], 8'h55}` | Low-latency single-block ordered command (optional) |
| `2'b00`, `2'b11` | **Invalid** | — | — | *(Never transmitted)* | Invalid sync header; triggers Clause 49 error / slip |

- **Idle fill during bring-up:** While the link is training (`ST_EYE_SCAN`, `ST_BLOCK_LOCK`, `ST_DESKEW`), TX transmits continuous scrambled `/I/` blocks (with `/A/` every `AM_PERIOD` blocks per lane). Scrambled `/I/` guarantees >200 Mb/s transition density for Kria `IDELAYE3` eye scanning and safe AC-coupled baseline.

---

## 3. Scrambler & Descrambler (IEEE 802.3 Clause 49)

- **Polynomial:** $G(x) = 1 + x^{39} + x^{58}$ (58-bit LFSR `scr[57:0]`, reset seed `58'h3FF_FFFF_FFFF_FFFF`).
- **Scope:** `sync[1:0]` (`blk[1:0]`) bypasses the scrambler **unmodified**; only `payload[63:0]` (`blk[65:2]`) is scrambled/descrambled sequentially from bit `0` to bit `63`.
- **Per-bit equations (`i = 0 .. 63`):**
  - **TX Scrambler:**
    `s_bit = payload_in[i] ^ scr[38] ^ scr[57]`
    `scr   = {scr[56:0], s_bit}`
  - **RX Descrambler (self-synchronous):**
    `d_bit = payload_rx[i] ^ scr[38] ^ scr[57]`
    `scr   = {scr[56:0], payload_rx[i]}`
- Because the RX descrambler shifts in the received ciphertext bit `payload_rx[i]`, it automatically synchronizes to the TX scrambler state within **58 received bits** (one 64-bit block) with zero handshake, and each isolated single-bit channel error multiplies into at most 3 bit errors in the descrambled block (`x`, `x+39`, `x+58`), which CRC-32 catches deterministically.

---

## 4. 66:8 / 8:66 Gearboxes & Block Lock FSM

### 4.1 Gearbox Framing
- At 8 bits per `CLKDIV` (125 MHz @ 1.0 Gb/s nominal), **33 `CLKDIV` cycles = 264 bits = 4 x 66-bit blocks**.
- `link_gearbox_tx` accepts a new 66-bit block via `in_ready` on cycles where internal accumulator occupancy `bit_cnt <= 65` (4 cycles out of every 33). If `in_valid` is low when `in_ready` asserts, an Idle block `{64'h0000_0000_0000_001E, 2'b10}` is substituted automatically after scrambling.
- `link_gearbox_rx` appends 8 bits per `CLKDIV` cycle into a 140-bit shift accumulator and asserts `out_valid` whenever `>= 66` bits are available (4 cycles out of every 33). When `rx_slip` is pulsed for one cycle, 1 bit is discarded from the accumulator head, advancing the 66-bit extraction window by 1 bit time (1 UI = 1.0 ns @ 1.0 Gb/s). This unifies both intra-byte bit alignment (`0..7`) and block boundary alignment (`0..65`) inside plain Verilog-2001 logic.

### 4.2 Clause 49.2.13 Block Lock State Machine (`link_block_lock`)
- **Valid sync header check:** `sh_valid = (rx_sync == 2'b01) || (rx_sync == 2'b10)`.
- **Unlocked (`block_lock == 0`):**
  - Every `sh_valid` increments `sh_cnt`. Reaching **64 consecutive valid sync headers** transitions to `block_lock = 1`.
  - Any invalid sync header (`2'b00` or `2'b11`) resets `sh_cnt = 0`, increments `sh_err_cnt`, and pulses `rx_slip = 1` (with a 1-block pipeline settle holdoff before checking the next header).
- **Locked (`block_lock == 1`):**
  - Evaluates sliding windows of 64 received blocks (`win_cnt = 0..63`, `sh_invalid_cnt`).
  - Every invalid sync header increments `sh_invalid_cnt` and `sh_err_cnt`.
  - If **`sh_invalid_cnt == 16`** within a 64-block window, `block_lock` drops to `0`, `rx_slip` pulses, and acquisition restarts. Otherwise at `win_cnt == 63`, `win_cnt` and `sh_invalid_cnt` clear.

---

## 5. 2-Lane Striping & Alignment-Marker Deskew

Applies to the 2-lane uplink (`LINK_RX_D0`, `LINK_RX_D1`). (For 1-lane downlink `LINK_TX_D0`, Lane 0 passes directly without striping.)

1. **TX Striping (`link_tx_lanes`):**
   - Distributes unscrambled packet/idle blocks strictly alternating **Lane 0 (even)**, then **Lane 1 (odd)**.
   - Every `AM_PERIOD` block-pairs per lane (default `16384 = 2^14` in synthesis ≈ 10.8 ms interval; parameterizable e.g. `64` in simulation), pauses user `in_ready` for two lane emissions and injects `BTYPE_ALIGN` (`8'h4B`, magic `32'h9A_C5_3C_69`, shared `am_seq[15:0]`, `lane_id = 0 / 1`) simultaneously onto both lanes.
2. **RX Deskew (`link_rx_lanes`):**
   - After `l0_block_lock && l1_block_lock`, each lane writes descrambled 66-bit blocks into an independent 32-entry circular elastic FIFO (capable of absorbing up to ±15 blocks = ±990 UI of static + dynamic inter-lane skew).
   - Both FIFOs watch for `sync == 2'b10 && data[7:0] == 8'h4B && data[63:32] == 32'h9A_C5_3C_69` (`BTYPE_ALIGN`) and record the write index at which matching `am_seq[15:0]` arrived on Lane 0 and Lane 1.
   - Read pointers `rp0` and `rp1` are initialized cleanly just past the matched AM entry on both lanes, asserting `deskew_lock = 1` and reporting `skew_blocks = wp0_am - wp1_am`.
   - `BTYPE_ALIGN` and `BTYPE_IDLE` control blocks are stripped cleanly during readout, reconstructing the exact single-stream order (Lane 0 even block, then Lane 1 odd block) for `link_deframer`.

---

## 6. Packet Format & AERIS Radar Stream Mapping

### 6.1 Wire Packet Structure

Every packet transfers between **1 and 4096 payload bytes** framed as a contiguous sequence of `N + 3` blocks (`N = ceil(pkt_len / 8)`):

| Order | Block Type | `sync[1:0]` | `payload[63:0]` Fields |
| :---: | :--- | :---: | :--- |
| `0` | **`START` (`/S/`)** | `2'b10` | `[7:0] = 8'h78`, `[15:8] = stream_id[7:0]`, `[31:16] = pkt_len[15:0]`, `[63:32] = seq_num[31:0]` |
| `1` | **`TIMESTAMP`** | `2'b01` | `[63:0] = pps_timestamp_ns[63:0]` (PPS-disciplined monotonic timestamp) |
| `2 .. N+1` | **`DATA` (`/D/`)** | `2'b01` | `data_word[63:0]` (little-endian byte packed; unused trailing bytes in word `N+1` zero-padded) |
| `N+2` | **`TERM` (`/T/`)** | `2'b10` | `[7:0] = 8'hFF`, `[39:8] = crc32[31:0]`, `[63:40] = dropped_cnt[23:0]` |

- **Header constraints:** `1 <= pkt_len <= 4096`. `seq_num[31:0]` increments per packet/chirp per stream so upper layers can also cross-check sequence continuity.
- **Dropped packet counter (`dropped_cnt[23:0]`):** TX-side saturating counter incremented whenever the upstream radar FIFO overflows or rejects a frame; piggybacked in every `/T/` trailer so Kria PS/PL observes upstream losses even if whole packets never entered the link.
- **IEEE 802.3 CRC-32:** Polynomial `0x04C11DB7` (reflected `0xEDB88320`), initial seed `0xFFFFFFFF`, final XOR `0xFFFFFFFF`. Computed LSB-first over the **complete 64-bit `START` word**, the **64-bit `TIMESTAMP` word**, and all **`N` 64-bit `DATA` words** (all `8*N` bytes, with unused trailing bytes in the final word `= 8'h00`).
- **Receiver validation (`link_deframer`):** Buffers or tags incoming packet words and checks `crc32` upon receiving `/T/` plus `1 <= pkt_len <= 4096`. Only asserts `pkt_done_ok` if CRC matches and protocol framing is intact; otherwise asserts `pkt_done_err` and increments `crc_err_cnt`.
- **Intentional error-injection self-test in simulation (`PASS` lines with non-zero `crc_err`):** Normal clean runs of the verification testbenches deliberately inject single-bit channel errors on designated packets to confirm end-to-end CRC-32 error detection and packet rejection (`pkt_done_err` + `crc_err_cnt`):
  - `tb_pcs_loop`: deliberately injects bit errors into `3` packets (`p == 5, 13, 21` -> expects **`crc_err=3`**, `rx_good=25` out of `28`, `0` payload mismatches).
  - `tb_link_a2k` and `tb_link_k2a`: each deliberately inject a bit error into `1` packet (`p == 7` -> expects **`crc_err=1`**, `rx_good=19` out of `20`, `0` payload mismatches).
  In all benches, a non-zero `crc_err` matching the exact injected packet count is required for `PASS`; a `0` `crc_err_cnt` causes the run (or the `skip_crc` mutation) to `FAIL`.

### 6.2 Radar Stream IDs (Aligned with AERIS `radar_protocol.py` Semantics)

Rather than tunneling AERIS's legacy 11-byte (`0xAA .. 0x55`) UART/FTDI USB records verbatim, packets use native 64-bit-aligned bursts tagged by `stream_id[7:0]`:

| `stream_id` | Direction | Payload Contents (Reference: AERIS `radar_protocol.py`) | Typical `pkt_len` |
| :---: | :---: | :--- | :---: |
| `8'h01` | Artix -> Kria | Raw DDC / ADC I/Q chirp samples (interleaved `int16 I, int16 Q` per chirp; `seq_num = chirp_id`) | `512 .. 4096` B |
| `8'h02` | Artix -> Kria | Pre-processed range profile / CFAR vector (or `int16` range FFT bins) | `256 .. 1024` B |
| `8'h03` | Artix -> Kria | Range-Doppler cell tiles (each 9 B AERIS cell `{range_q[15:0], range_i[15:0], dop_re[15:0], dop_im[15:0], det[7:0]}` packed into 12 B or 16 B records, up to 4096 B) | `<= 4096` B |
| `8'h10` | Kria -> Artix | Host register write command matching `radar_protocol.Opcode` (`{opcode[7:0], addr[7:0], value[15:0]}` for radar mode `0x01`, trigger `0x02`, CFAR `0x21–0x27`, AGC `0x28–0x2C`, chirp timings `0x10–0x16`, status request `0xFF`) | `4 .. 16` B |
| `8'h11` | Artix -> Kria | Telemetry / `StatusResponse` snapshot (6 x 32-bit status words: mode, stream_ctrl, threshold, chirp timings, AGC gain, self-test flags) | `24 .. 64` B |
| `8'h7F` | Both | PRBS / loopback diagnostic burst for link bring-up and BER verification | `8 .. 4096` B |

---

## 7. Hardware Training FSM & Register Map

### 7.1 Hardware Training FSM (`link_rx_train_fsm`)
The receiver training FSM (`link_rx_train_fsm`) supports both receivers via parameterization:
- **Kria K26 Uplink RX (`Bank 66 HP`, 2 lanes):** `IDELAYE3` TIME mode with `VAR_LOAD = TRUE` (512 fine taps @ 4 ps/tap in XSim `ULTRASCALE_PLUS` behavioral simulation; requires `EN_VTC = 0` during `LOAD` and `>= 4` `CLK` cycles after `RST` deassertion per UG571). Sweeps `CNTVALUEIN` across `[0 .. 511]`.
- **Artix-7 Downlink RX (`Bank 14 HR`, 1 lane):** `IDELAYE2` `VAR_LOAD` mode (`REFCLK_FREQUENCY = 200.0`, 32 taps @ 78 ps/tap + 600 ps intrinsic in XSim `7SERIES`). Sweeps `CNTVALUEIN` across `[0 .. 31]`, bypassing multi-lane deskew (`SINGLE_LANE = 1`).

| State | Code | Action | Exit Condition |
| :--- | :---: | :--- | :--- |
| `ST_RESET` | `3'd0` | Hold `en_vtc = 0`; wait `>= 16` `CLKDIV` cycles after `rst == 0` so `IDELAY` reset synchronizer settles | Wait timer expired |
| `ST_EYE_SCAN` | `3'd1` | If `cfg_tap_override`, jump to load override; else sweep `CNTVALUEIN` from `0` to `MAX_TAP` (step `TAP_STEP`), allowing `link_block_lock` to align on entry into an eye and checking that descrambled blocks are error-free `/I/` (`8'h1E`) or `/A/` (`8'h4B`) training blocks (`l*_rx_blk_ok`); track the full passing tap window `[eye_left .. eye_right]` per lane | Full sweep complete |
| `ST_LOAD_OPT` | `3'd2` | Compute midpoint `(eye_left + eye_right) >> 1` per active lane and issue a 1-cycle `LOAD` pulse with `en_vtc = 0` | Optimal center tap loaded |
| `ST_BLOCK_LOCK` | `3'd3` | Wait for Clause 49 `l0_block_lock` (and `l1_block_lock` when `SINGLE_LANE == 0`) while `IDELAY` settles | Active lane(s) locked (or timeout -> re-scan) |
| `ST_DESKEW` | `3'd4` | Enable `link_rx_lanes` AM deskew across Lane 0 and Lane 1 (bypassed when `SINGLE_LANE == 1`) | `deskew_lock == 1` (or timeout -> restart) |
| `ST_LINK_UP` | `3'd5` | Assert `link_up = 1` (optional `en_vtc = 1` once BISC/VTC policy allows); monitor loss of `block_lock` or `deskew_lock` | Drops to `ST_BLOCK_LOCK` / `ST_DESKEW` if lock lost |

**Bidirectional Idle/AM Training Gate (`artix/top.v`):**
Because `link_rx_train_fsm` requires 6 consecutive clean descrambled `/I/` (`8'h1E`) or `/A/` (`8'h4B`) training blocks per `IDELAY` tap, [`artix_top`](../artix/top.v) holds `u_ul_pcs_tx.pkt_valid` low (transmitting continuous scrambled `/I/` + `/A/` markers only) until both directions are synchronized (`ul_tx_allow = dl_up_sync[1] & dl_rem_sync2[0]`, where `dl_rem_sync2[0]` reflects Kria's `link_up` fed back via downlink `/I/` `remote_status[0]`). On link drop or manual retrain (`ul_tx_allow -> 0`), `artix_top` lets any single in-flight packet finish cleanly on `ias_mux_eop` (`ul_in_pkt`) before stalling further `/S/` starts and returning the uplink to continuous `/I/` + `/A/` until `link_up` recovers.

### 7.2 Control & Diagnostic Register Map (Both Ends)

| Offset | Register | Access | Reset | Fields & Description |
| :---: | :--- | :---: | :---: | :--- |
| `0x00` | `LINK_CTRL` | R/W | `0x0000_0000` | `[0]` Soft Reset; `[1]` Loopback Enable; `[2]` Retrain Pulse (self-clearing); `[3]` `tap_override_en` (use `IDELAY_CTRL_L0/L1`); `[4]` `prbs7_tx_en` (bypass framer with PRBS-7 test pattern); `[5]` `prbs7_rx_chk_en`; `[6]` Clear Error Counters (W1C pulse) |
| `0x04` | `LINK_STATUS` | RO | `0x0000_0000` | `[2:0]` `train_state`; `[3]` `l0_block_lock`; `[4]` `l1_block_lock`; `[5]` `deskew_lock`; `[6]` `link_up`; `[7]` `idelayctrl_rdy`; `[23:16]` `remote_status[7:0]` (from `/I/`) |
| `0x08` | `IDELAY_CTRL_L0` | R/W | `0x0000_0000` | `[8:0]` Software `CNTVALUEIN` override for Lane 0 (`0..511`); `[24:16]` Readback active tap loaded on Lane 0; `[31]` Force `LOAD` |
| `0x0C` | `IDELAY_CTRL_L1` | R/W | `0x0000_0000` | `[8:0]` Software `CNTVALUEIN` override for Lane 1 (`0..511`); `[24:16]` Readback active tap loaded on Lane 1; `[31]` Force `LOAD` |
| `0x10` | `ERR_CNT_SH_L0` | RO | `0x0000_0000` | `[31:0]` Saturating invalid sync-header error count on Lane 0 |
| `0x14` | `ERR_CNT_SH_L1` | RO | `0x0000_0000` | `[31:0]` Saturating invalid sync-header error count on Lane 1 |
| `0x18` | `ERR_CNT_CRC` | RO | `0x0000_0000` | `[31:0]` Saturating deframer CRC-32 error packet count |
| `0x1C` | `PKT_CNT_RX` | RO | `0x0000_0000` | `[31:0]` Valid packets received (`pkt_done_ok`) |
| `0x20` | `PKT_CNT_DROP` | RO | `0x0000_0000` | `[23:0]` Latest TX `dropped_cnt` reported in `/T/` trailer; `[31:24]` RX FIFO overflow drops |
| `0x24` | `DESKEW_STATUS` | RO | `0x0000_0000` | `[7:0]` Signed measured inter-lane skew (`skew_blocks`); `[23:8]` Last matched `am_seq[15:0]` |
| `0x28` | `PRBS_ERR_CNT` | RO | `0x0000_0000` | `[31:0]` Saturating bit-error counter when `prbs7_rx_chk_en == 1` |
| `0x2C` | `EYE_SCAN_L0` | RO | `0x0000_0000` | `[8:0]` Discovered eye-left tap; `[24:16]` Discovered eye-right tap (Lane 0) |
| `0x30` | `EYE_SCAN_L1` | RO | `0x0000_0000` | `[8:0]` Discovered eye-left tap; `[24:16]` Discovered eye-right tap (Lane 1) |
| `0x34` | `ADCS_CTRL` | R/W | `0x0000_0001` | **Task 13 (AD9253 + DDC):** `[0]` `adcs_enable`; `[1]` `conv_spi_start_init` (W1P); `[3:2]` `sdr_ddc_ch_enable` (`[2]=ChA, [3]=ChB`) |
| `0x38` | `ADCS_STATUS` | RO | `0x0000_0000` | `[0]` `aligned`; `[1]` `idelay_done`; `[2]` `idelay_err`; `[3]` `bitslip_err`; `[8:4]` `best_tap`; `[16]` `conv_init_done`; `[17]` `conv_init_err`; `[31:24]` `ad9253_id` |
| `0x3C` | `CONV_SPI_CMD` | R/W | `0x0000_0000` | `[7:0]` `req_wdata`; `[20:8]` `req_addr[12:0]`; `[21]` `req_rw` (`0=W,1=R`); `[22]` `req_target` (`0=AD9484,1=AD9253`); `[31]` Start (W1P) |
| `0x40` | `CONV_SPI_RDATA` | RO | `0x0000_0000` | `[7:0]` `resp_rdata`; `[8]` `resp_valid_sticky`; `[9]` `req_ready` |
| `0x44` | `SDR_DDC_NCO_A` | R/W | `0x0000_0000` | `[31:0]` SDR DDC Ch A NCO frequency tuning word (`nco_ftw_a`) |
| `0x48` | `SDR_DDC_NCO_B` | R/W | `0x0000_0000` | `[31:0]` SDR DDC Ch B NCO frequency tuning word (`nco_ftw_b`) |
| `0x4C` | `SDR_DDC_DECIM` | R/W | `0x0040_0004` | `[15:0]` `decim_ratio` (`>=2`, even `>=4` enables HB FIR); `[25:16]` `words_per_pkt` (default `64` = `512 B`) |
| `0x50` | `SDR_DDC_DROP` | RO | `0x0000_0000` | `[23:0]` Saturating `sdr_ddc.dropped_cnt` across async CDC FIFO |
| `0x54` | `DACR_CTRL` | R/W | `0x00FF_0000` | **Task 14 (AD9708 + AD9767):** `[0]` `chirp_enable`; `[1]` `chirp_trig` (W1P); `[23:16]` `amp_scale[7:0]` (`0xFF` = full scale) |
| `0x58` | `DACR_F0_FTW` | R/W | `0x0000_0000` | `[31:0]` AD9708 radar chirp start FTW (`f0_ftw`) |
| `0x5C` | `DACR_DF_FTW` | R/W | `0x0000_0000` | `[31:0]` Signed AD9708 chirp slope step per clock (`df_ftw`) |
| `0x60` | `DACR_PULSE_LEN` | R/W | `0x0000_0400` | `[31:0]` Radar chirp duration in `dac_clk` cycles (`pulse_len`) |
| `0x64` | `DACR_PRI_LEN` | R/W | `0x0000_2000` | `[31:0]` Radar PRI in `dac_clk` cycles (`0` = trigger-only single shot) |
| `0x68` | `DACR_STATUS` | RO | `0x0000_0000` | `[0]` `chirp_active` |
| `0x6C` | `DACR_PULSE_CNT` | RO | `0x0000_0000` | `[31:0]` Total radar chirps transmitted (`pulse_cnt`) |
| `0x70` | `DACS_CTRL` | R/W | `0x0000_0000` | `[0]` AD9767 `tx_enable`; `[1]` clear/latch note (soft reset via `LINK_CTRL`) |
| `0x74` | `DACS_UNDERFLOW` | RO | `0x0000_0000` | `[31:0]` AD9767 `underflow_cnt` |
| `0x78` | `DACS_FIFO_LVL` | RO | `0x0000_0000` | `[9:0]` `dac_sdr.fifo_level_link` |
| `0x7C` | `ADAR_CTRL` | R/W | `0x0000_0000` | **Task 15 (ADAR1000 + RF SW):** `[4:0]` `active_beam_id`; `[5]` `tr_req` (`0=RX,1=TX`); `[6]` `soft_load` (W1P); `[7]` `start_init` (W1P); `[11:8]` `rf_sw_req[3:0]`; `[12]` `auto_tr_chirp` (drive `tr_req` from `chirp_active`) |
| `0x80` | `ADAR_GUARD` | R/W | `0x000C_000A` | `[15:0]` `guard_pre` cycles; `[31:16]` `guard_post` cycles |
| `0x84` | `ADAR_SW_SETTLE` | R/W | `0x0000_007D` | `[15:0]` `rf_switch.settle_cycles` (default `125` = `1 us @ 125 MHz`) |
| `0x88` | `ADAR_TBL_WR` | WO | `0x0000_0000` | `[7:0]` `tbl_wdata`; `[12:8]` `byte_idx` (`0..23`); `[15:13]` `chip_id` (`0..7`); `[20:16]` `beam_id` (`0..31`); `[31]` Write strobe (W1P) |
| `0x8C` | `ADAR_SPI_CMD` | R/W | `0x0000_0000` | `[7:0]` `wdata`; `[22:8]` `addr[14:0]`; `[23]` `rw`; `[26:24]` `chip_id`; `[31]` Trigger (W1P) |
| `0x90` | `ADAR_STATUS` | RO | `0x0000_0000` | `[0]` `init_done`; `[1]` `init_err`; `[2]` `load_busy`; `[3]` `tr_ready`; `[4]` `sw_ready`; `[9:5]` `current_beam_id`; `[17:10]` `spi_resp_rdata`; `[18]` `spi_req_ready`; `[22:19]` `sw_ctrl[3:0]` |
| `0x94` | `HK_I2C_CTRL` | R/W | `0x0000_0001` | **Task 16 (HK + XO + XADC + PPS):** `[0]` `poll_en` (auto-poll TMP1075 `7'h48` Reg `0x00`) |
| `0x98` | `HK_I2C_CMD` | R/W | `0x0000_0000` | `[6:0]` `dev_addr` (`0x48` TMP1075 / `0x50` M24C02); `[9:7]` `wr_len` (`0..4`); `[11:10]` `rd_len` (`0..2`); `[31]` Trigger (W1P) |
| `0x9C` | `HK_I2C_WDATA` | R/W | `0x0000_0000` | `[31:0]` Packed TX bytes (`[7:0]`=byte0 .. `[31:24]`=byte3) |
| `0xA0` | `HK_I2C_STATUS` | RO | `0x0000_0000` | `[15:0]` `req_rdata`; `[16]` `req_ready`; `[17]` `last_ack_err`; `[18]` `busy`; `[19]` `alert_active` (`~HK_ALERT_N`); `[20]` `tmp_valid` |
| `0xA4` | `HK_TEMP_ERR` | RO | `0x0000_0000` | `[15:0]` `tmp_raw` (TMP1075 `[15:4]*0.0625 C`); `[31:16]` `ack_err_cnt` |
| `0xA8` | `XO_CTRL` | R/W | `0x0000_0000` | `[0]` `use_ext_clk` (`CLK_SEL` `D8`: `0=Si549 Z`, `1=SMA 0`); `[1]` `prog_freq_500m` (`0=400MHz,1=500MHz`); `[2]` `prog_start` (W1P); `[3]` `delta_start` (W1P); `[8]` `xo_busy` (RO); `[9]` `xo_prog_done` (RO); `[10]` `xo_active_freq_500m` (RO); `[11]` `xo_ack_err` (RO); `[31:16]` `xo_ack_err_cnt` (RO) |
| `0xAC` | `XO_DELTA_M` | R/W | `0x0000_0000` | `[23:0]` Si549 `ADPLL_DELTA_M` (`±950 ppm`, Regs `231..233`) |
| `0xB0` | `XO_RAW_CMD` | R/W | `0x0000_0000` | `[7:0]` Si549 `reg_addr`; `[15:8]` `wdata`; `[16]` `rw` (`0=W,1=R`); `[31]` Trigger (W1P) |
| `0xB4` | `XO_RAW_RDATA` | RO | `0x0000_0000` | `[7:0]` `raw_resp_rdata`; `[8]` `raw_resp_valid_sticky`; `[9]` `raw_req_ready`; `[10]` `raw_resp_err` |
| `0xB8` | `XADC_TEMPV` | RO | `0x0000_0000` | `[11:0]` `xadc_temp_raw`; `[23:12]` `xadc_vccint_raw`; `[24]` `xadc_valid`; `[25]` `xadc_overtemp` |
| `0xBC` | `XADC_VCCAUX` | RO | `0x0000_0000` | `[11:0]` `xadc_vccaux_raw` |
| `0xC0` | `PPS_CTRL` | R/W | `0x0000_0800` | `[15:0]` `cfg_ts_step_q8` (default `0x0800` = `8.0 ns/clk`); `[16]` `cfg_pps_disc_en`; `[17]` `cfg_ts_clear` (W1P); `[24]` `pps_locked` (RO) |
| `0xC4` | `PPS_NOM_CYC` | R/W | `0x0773_5940` | `[31:0]` `cfg_nom_period_cyc` (default `125,000,000` @ `125 MHz`) |
| `0xC8` | `PPS_PERIOD_CYC` | RO | `0x0000_0000` | `[31:0]` Measured PPS period in `adc_clk` cycles |
| `0xCC` | `PPS_PPM_ERR` | RO | `0x0000_0000` | `[31:0]` Signed integer frequency offset (`ppm`) vs `PPS_NOM_CYC` |
| `0xD0` | `PPS_CNT` | RO | `0x0000_0000` | `[31:0]` Rising `PPS_SYNC` edge counter |
| `0xD4` | `TS_NOW_LO` | RO | `0x0000_0000` | `[31:0]` `pps_timestamp_ns[31:0]` snapshot (`sys_clk`) |
| `0xD8` | `TS_NOW_HI` | RO | `0x0000_0000` | `[31:0]` `pps_timestamp_ns[63:32]` snapshot (`sys_clk`) |
| `0xDC` | `PPS_LATCH_LO` | RO | `0x0000_0000` | `[31:0]` `pps_latch_ts[31:0]` captured on last `PPS_SYNC` edge |
| `0xE0` | `PPS_LATCH_HI` | RO | `0x0000_0000` | `[31:0]` `pps_latch_ts[63:32]` captured on last `PPS_SYNC` edge |
