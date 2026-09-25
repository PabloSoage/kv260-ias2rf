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
