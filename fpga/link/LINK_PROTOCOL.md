# IAS1-to-RF LVDS Link Protocol & PCS Specification

**Scope:** Line coding, scrambling, gearbox, framing, 2-lane striping/deskew, training state machine, packet format, and register map for the bidirectional AC-coupled LVDS link between the Artix-7 RF/DAQ FPGA (`XC7A50T-FTG256`) and Kria K26 (`XCK26-SFVC784`).

---

## 1. Physical & PCS Layering

| Direction | Data Lanes | Clock Pair | Raw Rate / Lane | Aggregate Raw Rate | Net 64b/66b Rate | SERDES Width | Parallel Clock (`CLKDIV`) |
| :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| **Uplink (Artix -> Kria)** | 2 (`LINK_RX_D0`, `LINK_RX_D1`) | `LINK_RX_CLK` (200 MHz DDR) | 400 Mb/s | **800 Mb/s** | 775.76 Mb/s | 8-bit DDR | 100 MHz |
| **Downlink (Kria -> Artix)** | 1 (`LINK_TX_D0`) | `LINK_TX_CLK` (200 MHz DDR) | 400 Mb/s | **400 Mb/s** | 387.88 Mb/s | 8-bit DDR | 100 MHz |

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
- At 8 bits per `CLKDIV` (100 MHz), **33 `CLKDIV` cycles = 264 bits = 4 x 66-bit blocks**.
- `link_gearbox_tx` accepts a new 66-bit block via `in_ready` on cycles where internal accumulator occupancy `bit_cnt <= 58` (4 cycles out of every 33). If `in_valid` is low when `in_ready` asserts, an Idle block `{64'h0000_0000_0000_001E, 2'b10}` is substituted automatically after scrambling.
- `link_gearbox_rx` appends 8 bits per `CLKDIV` cycle into a 132-bit shift accumulator and asserts `out_valid` whenever `>= 66` bits are available (4 cycles out of every 33). When `rx_slip` is pulsed for one cycle, 1 bit is discarded from the accumulator head, advancing the 66-bit extraction window by 1 bit time (1 UI = 2.5 ns). This unifies both intra-byte bit alignment (`0..7`) and block boundary alignment (`0..65`) inside plain Verilog-2001 logic.

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

### 7.1 Kria RX Training FSM (`link_rx_train_fsm`)
On the Kria K26 receiver (`IDELAYE3` TIME mode with `VAR_LOAD = TRUE` on Bank 66 HP, 512 fine taps @ ~4–5 ps/tap nominal ≈ 2.2 ns span):

| State | Code | Action | Exit Condition |
| :--- | :---: | :--- | :--- |
| `ST_RESET` | `3'd0` | Hold `en_vtc = 0`; wait `>= 16` `CLKDIV` cycles after `rst == 0` so `IDELAYE3` reset synchronizer settles | Wait timer expired |
| `ST_EYE_SCAN` | `3'd1` | If `cfg_tap_override`, load `cfg_tap_l0`/`l1` directly; else sweep taps `[0 .. 511]` (step `TAP_STEP`), measure sync-header lock / bit stability per tap, compute widest passing window midpoint `(t_start + t_end) / 2` and load optimal `CNTVALUEIN` (`en_vtc = 0`, 1-cycle `LOAD` pulse) | Optimal center tap loaded |
| `ST_BLOCK_LOCK` | `3'd2` | Wait for Clause 49 `l0_block_lock && l1_block_lock` while `IDELAYE3` settles | Both lanes locked (or timeout -> re-scan) |
| `ST_DESKEW` | `3'd3` | Enable `link_rx_lanes` AM deskew across Lane 0 and Lane 1 | `deskew_lock == 1` (or timeout -> restart) |
| `ST_LINK_UP` | `3'd4` | Assert `link_up = 1` (optional `en_vtc = 1` once BISC/VTC policy allows); monitor loss of `block_lock` or `deskew_lock` | Drops to `ST_BLOCK_LOCK` / `ST_EYE_SCAN` if lock lost |

### 7.2 Control & Diagnostic Register Map (Both Ends)

| Offset | Register | Access | Fields & Description |
| :---: | :--- | :---: | :--- |
| `0x00` | `LINK_CTRL` | R/W | `[0]` Soft Reset; `[1]` Loopback Enable; `[2]` Retrain Pulse (self-clearing); `[3]` `tap_override_en` (use `IDELAY_CTRL_L0/L1`); `[4]` `prbs7_tx_en` (bypass framer with PRBS-7 test pattern); `[5]` `prbs7_rx_chk_en`; `[6]` Clear Error Counters (W1C pulse) |
| `0x04` | `LINK_STATUS` | RO | `[2:0]` `train_state`; `[3]` `l0_block_lock`; `[4]` `l1_block_lock`; `[5]` `deskew_lock`; `[6]` `link_up`; `[7]` `idelayctrl_rdy`; `[23:16]` `remote_status[7:0]` (from `/I/`) |
| `0x08` | `IDELAY_CTRL_L0` | R/W | `[8:0]` Software `CNTVALUEIN` override for Lane 0 (`0..511`); `[24:16]` Readback active tap loaded on Lane 0; `[31]` Force `LOAD` |
| `0x0C` | `IDELAY_CTRL_L1` | R/W | `[8:0]` Software `CNTVALUEIN` override for Lane 1 (`0..511`); `[24:16]` Readback active tap loaded on Lane 1; `[31]` Force `LOAD` |
| `0x10` | `ERR_CNT_SH_L0` | RO | `[31:0]` Saturating invalid sync-header error count on Lane 0 |
| `0x14` | `ERR_CNT_SH_L1` | RO | `[31:0]` Saturating invalid sync-header error count on Lane 1 |
| `0x18` | `ERR_CNT_CRC` | RO | `[31:0]` Saturating deframer CRC-32 error packet count |
| `0x1C` | `PKT_CNT_RX` | RO | `[31:0]` Valid packets received (`pkt_done_ok`) |
| `0x20` | `PKT_CNT_DROP` | RO | `[23:0]` Latest TX `dropped_cnt` reported in `/T/` trailer; `[31:24]` RX FIFO overflow drops |
| `0x24` | `DESKEW_STATUS` | RO | `[7:0]` Signed measured inter-lane skew (`skew_blocks`); `[23:8]` Last matched `am_seq[15:0]` |
| `0x28` | `PRBS_ERR_CNT` | RO | `[31:0]` Saturating bit-error counter when `prbs7_rx_chk_en == 1` |
| `0x2C` | `EYE_SCAN_L0` | RO | `[8:0]` Discovered eye-left tap; `[24:16]` Discovered eye-right tap (Lane 0) |
| `0x30` | `EYE_SCAN_L1` | RO | `[8:0]` Discovered eye-left tap; `[24:16]` Discovered eye-right tap (Lane 1) |
