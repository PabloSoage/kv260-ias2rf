# IAS_LINK sheet — specification and review guide

*25 September 2026 · `rev03/IAS_LINK.kicad_sch` · drawn by `_work/sheets/ias_link.py` from the
connection list in `_work/sheets/ias_link_spec.py`*

The link to the Kria: the Hirose connector on IAS1 with its five LVDS pairs and four single-ended
signals, each pair AC-coupled, and the two pairs the FPGA receives terminated here. Plus the IAS0
connector, which is only mechanical.

Everything on this sheet follows [INTERFACE_SPEC.md](INTERFACE_SPEC.md) §2–§6, which was verified
against the carrier schematic (XTP682). This sheet adds no new allocation.

---

## 1. What is on the sheet

| Part | What |
|---|---|
| **J101** | Hirose BM20B(0.8)-34DP on **IAS1** (KV260 J8). Pins as INTERFACE_SPEC §2–§4. Footprint `AVT_KHK_Lib:J-BM20B(0.8)-34DP`, the one in the original layout |
| **J102** | The same part on **IAS0** (KV260 J7). The SOM reaches IAS0 only through the carrier's AP1302 (B-01), so it's **mechanical only**: its 11 grounds connected, everything else marked no-connect |
| C101–C110 | 100 nF in series on all ten lines (§6.1: the HPA bank is at 1.2 V and the FPGA's LVDS is not). 0 Ω is the alternative stuffing if `VCCO_HPA` turns out to be 1.8 V |
| R101–R104, C111, C112 | On the two pairs the **FPGA receives** (`LINK_TX_D0`, `LINK_TX_CLK`): 2 × 49.9 Ω per pair with the centre at `+1V2`, decoupled. That terminates the pair and restores the common mode the capacitors removed |

The connector splits every pair across its two rows of pins, so it is drawn with a label on each
pin, and the capacitors sit in an orderly block beside it. The carrier's rails on pins 13, 17/18
and 23/24 are left unconnected: the adapter takes no power from the connector (ARCHITECTURE §9.1).

---

## 2. Decisions this sheet makes, for your approval

| Decision | Evidence | Alternative |
|---|---|---|
| **Termination and bias for the FPGA-bound pairs at `+1V2`** | An AC-coupled LVDS input needs its common mode restored. The XC7A50T has only HR banks, and those have no internal bias for AC-coupled inputs, so it's external. 1.2 V is the LVDS common mode, and the rail already exists | A resistor divider from another rail |
| **No parts for the Kria-bound pairs beyond the capacitors** | Their receiver is inside the SOM, in an HP bank, which has internal termination and bias (`DIFF_TERM_ADV`, `DQS_BIAS`). **To confirm** in AMD's UltraScale+ SelectIO guide (UG571), which isn't in the repository | Footprints for an external bias network, fitted only if needed |
| **The single-ended signals pass straight through** | `HK_SCL`/`HK_SDA` (14/22), `FPGA_PROG_B` (21) and `FPGA_IRQ` (15) are at the carrier's levels, **1.8 V, verified** in XTP682 (INTERFACE_SPEC §4.3). Translating them belongs next to the FPGA, on CONTROL. Pin 32, first given to FPGA_IRQ, is the carrier's 48 MHz camera clock and is left unconnected | — |

---

## 3. Two things this sheet hands on

- **To CONTROL and POWER: the FPGA's link bank must be at 2.5 V, not 1.2 V.** The FPGA *drives*
  three of the pairs, and Artix-7 LVDS outputs (`LVDS_25`) need a 2.5 V bank. The power tree's line
  *"+1V2 → FPGA VCCO, IAS-facing bank"* (ARCHITECTURE §9) doesn't hold for outputs. `+1V2` stays in
  use, as the termination centre here. **To confirm in UG471** (7 Series SelectIO), not in the
  repository.
- **To the root:** the old IAS0/IAS1 blocks from Rev01 still hold their own copies of these
  connectors. They go when the root is wired, the last step.

---

## 4. How the drawing was verified

| Check | Result |
|---|---|
| `_work/check_sheet.py ias_link`: 26 nets exact, 32 no-connects alone, every pin of the 18 parts accounted for | **PASS** |
| KiCad ERC on the sheet | 1 × `power_pin_not_driven` on `+1V2`, until POWER exists |

---

## 5. How to review this sheet

About 15 minutes.

1. **J101's pins against INTERFACE_SPEC §2–§4.** The connector is drawn with labels, so check
   each pin's label against the tables. Watch pins 26/27 and 29/30: N comes before P.
2. **§2's decisions**, and **§3's 2.5 V bank**.

```
py _work/check_sheet.py ias_link
```

---

## 6. Bring-up: measuring the link on the board

*Added 12 November 2026. Nothing here is built yet: it is the test plan for the first boards.*

**Why not Vivado's IBERT.** The IBERT IP, the one that plots 2-D eyes, drives only the gigabit
transceivers (GTH/GTY). This link runs on ordinary SelectIO pins through `OSERDESE2`/`ISERDESE2`
on the Artix-7 and `ISERDESE3` on the Kria, so IBERT cannot see it. The eye is measured instead
with each receiver's input delay line, as a **bathtub curve**: bit errors against the sampling
point.

**The test.**

1. The transmitter sends PRBS7 on every data lane of a direction, with the lane's clock forwarded
   as usual (source-synchronous DDR, up to 1 Gb/s per lane on a 500 MHz clock).
   - No clock recovery is involved, and the PRBS7 checker locks by itself after seven bits, so no
     8b/10b is needed for the test.
   - PRBS7 is balanced enough for the AC-coupling capacitors (C101–C106): its longest run is seven
     bits. The real traffic still needs 8b/10b or a scrambler (ARCHITECTURE §4.2).
2. The receiver steps its delay line through its whole range, one tap at a time. At each tap it
   counts errors over a fixed number of bits and stores tap against count.
   - 10⁹ bits per tap is one second and resolves a BER of 10⁻⁹. Each further decade costs ten times
     as long.
3. The counts go to the PS on the Kria side (AXI), or over the return channel and the HK bus from
   the Artix-7 side. Plotted, they make a U: its flat floor, where the count is zero, is the eye's
   open width at that BER.
4. The gateware keeps the same routine for start-up: centre each lane in its floor, as the ADCR
   bits are calibrated (CONTROL_SPEC).

**Resolution on each side.**

| Direction | Receiver | Delay line | Step | Points per 1 ns bit |
|---|---|---|---|---|
| `LINK_RX_*` (FPGA → Kria) | K26, HP bank | `IDELAYE3`, 512 taps, `TIME` mode | a few ps | hundreds |
| `LINK_TX_*` (Kria → FPGA) | XC7A50T, HR bank | `IDELAYE2`, 32 taps, `IDELAYCTRL` at 200 MHz | 78 ps | about 13 |

So the `LINK_TX` bathtub comes out much coarser than the `LINK_RX` one. Both ranges span more
than one bit. The `IDELAYE3` step and range are **to confirm** in UG571.

**What it cannot measure.**
- **The eye's height.** The delay moves the data against the clock, but the receiver's threshold
  cannot be moved, so the simulated eye openings in mV cannot be checked this way.
- **The sampling window, separately.** The floor is the bit minus the jitter on the lane minus the
  input flip-flop's setup and hold window. Take that window from the data sheets (DS181 for the
  Artix-7, DS925 for the Zynq UltraScale+ HP banks) before comparing with the simulation.

**What to expect, from the board as routed** (SIGNAL_INTEGRITY §8, `lvds_eye.py` at 1 Gb/s
PRBS7; `lvds_skew.py` for the skew).

| Pair | Eye opening, routed / ideal | Zero-crossing spread, routed / ideal | Data − clock skew |
|---|---|---|---|
| `LINK_RX_D0` | 457 / 509 mV | 31 / 25 ps | +95 ps |
| `LINK_RX_D1` | 372 / 385 mV | 51 / 41 ps | +39 ps |
| `LINK_RX_CLK` | 392 / 395 mV | 10 / 10 ps | — |
| `LINK_TX_D0` | 665 / 674 mV | 62 / 64 ps | −40 ps |
| `LINK_TX_CLK` | 643 / 642 mV | 63 / 63 ps | — |

- **The width.** The simulation's spread is the board's own contribution: lossless lines, an ideal
  driver edge, no crosstalk, no driver or clock jitter. The floor should come out as roughly 1 ns
  minus that spread minus the receiver's window, and **narrower** by whatever the silicon adds.
  A floor much narrower than that points at the board: crosstalk, a reflection or a return path.
- **The centres.** The data − clock skew moves each lane's centre. On the Kria side,
  `LINK_RX_D0`'s floor should sit about 56 ps (95 − 39) away from `LINK_RX_D1`'s, give or take
  each receiver's own input delay. That is a direct check of the routed lengths.

---

## 7. Bandwidth: what the five pairs carry, and how fast they can go

*Added 12 November 2026.*

**Five pairs at 1 Gb/s are not 5 Gb/s of data.** Two of the five pairs are the forwarded clocks,
one per direction, and carry no data. One data pair runs the other way.

| Pair | Direction | Carries | Raw rate |
|---|---|---|---|
| `LINK_RX_D0` | FPGA → Kria | data | 1 Gb/s |
| `LINK_RX_D1` | FPGA → Kria | data | 1 Gb/s |
| `LINK_RX_CLK` | FPGA → Kria | the 500 MHz DDR clock for the two above | — |
| `LINK_TX_D0` | Kria → FPGA | data | 1 Gb/s |
| `LINK_TX_CLK` | Kria → FPGA | its clock | — |

That makes 2 Gb/s towards the Kria and 1 Gb/s back.

**Payload after line coding.** The link is AC-coupled (C101–C106), so the stream must be DC-balanced:
either 8b/10b, or a scrambler with 64b/66b framing.

| Direction | Raw | 8b/10b (80 %) | 64b/66b (97 %) | Needed | Margin, 8b/10b / 64b/66b |
|---|---|---|---|---|---|
| FPGA → Kria | 2 Gb/s | 1.6 Gb/s | 1.94 Gb/s | radar DDC ÷16, one channel, 0.8 Gb/s + two SDR channels of 16-bit I/Q at 3.9 MSPS, 0.25 Gb/s = **1.05 Gb/s** | ~35 % / ~45 % |
| Kria → FPGA | 1 Gb/s | 0.8 Gb/s | 0.97 Gb/s | beam tables, TX baseband, control | — |

Two radar channels at ÷16 (1.6 Gb/s) would leave no margin under 8b/10b, and 18 % under 64b/66b
(ARCHITECTURE §3.2).

**How fast the pairs can go.** These pins are SelectIO, not transceivers: the K26's GTH lanes do not
reach any KV260 connector (BLOCKERS_AND_RISKS, item 3). The silicon sets the ceiling, about
**1.25 Gb/s** per pair for the Artix-7 −2 HR banks (DS181) and about **1.6 Gb/s** for the
UltraScale+ HP banks in native mode (DS925). Both figures are **to confirm** in those data sheets.
Several Gb/s per pair is out of reach on this connector.

The board as routed, simulated at higher rates (`lvds_eye.py`, PRBS7; eye opening, routed / an
ideal 100 Ω pair of the same length):

| Rate per pair | `LINK_RX_D0` | `LINK_RX_D1` | `LINK_TX_D0` |
|---|---|---|---|
| 1.0 Gb/s | 457 / 509 mV | 372 / 385 mV | 665 / 674 mV |
| 1.25 Gb/s | 576 / 581 mV | 491 / 524 mV | 401 / 401 mV |
| 1.6 Gb/s | 271 / 225 mV | **44 / 48 mV** | 324 / 328 mV |
| 2.5 Gb/s | 0 / 0 | 0 / 0 | 0 / 0 |

The routed pair follows the ideal one at every rate. What closes the eye is the LVDS driver's edges
and the receiver's input capacitance, not the copper. The opening also varies non-monotonically
with rate, because the reflections of the 2 pF inputs land at different points of the bit. So
**the routing holds at 1.25 Gb/s, which is also the silicon's ceiling**. At 1.6 Gb/s `LINK_RX_D1` is
nearly closed, even in the ideal case.

**If more is ever needed:**
- run the pairs at 1.25 Gb/s: 2.5 Gb/s raw towards the Kria, 2.4 Gb/s of payload under 64b/66b;
- add J9, the KV260's 15-pin camera connector: two more data pairs and a clock, on another cable
  (R-04 in ARCHITECTURE §4.1);
- reduce what crosses the link: decimate further on the Artix-7.
