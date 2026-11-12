# CONTROL sheet — specification and review guide

*25 September 2026, housekeeping devices added 2 October · `rev03/CONTROL.kicad_sch` (A1) · drawn by `_work/sheets/control.py` from the
connection list in `_work/sheets/control_spec.py`*

The front-end FPGA, **U1101 XC7A50T-2FTG256I** (AERIS-10's own part), with everything it needs to
boot and everything it talks to that is not on another sheet:

- the configuration flash, JTAG, the reset and DONE circuits;
- the Pmod cable from the KV260;
- the ribbon to AERIS-10's ADAR1000 beamformers;
- the LVDS terminations of every pair the FPGA receives, and the 22 Ω series resistors on every DAC
  line;
- the housekeeping devices on the HK bus: a temperature sensor and the board ID EEPROM.

The FPGA is drawn as its four KiCad units, and it reads by net name: every ball has a short stub and
a name. A **hierarchical label** at a ball means the net leaves the sheet; a **plain label** means
it stays on it. The circuits sit nearby as small wired blocks.

The Xilinx documents behind every value are now on disk, fetched through the Internet Archive by
`_work/fetch_datasheets.py`: UG470 (configuration), UG471 (SelectIO), UG480 (XADC), UG483 (PCB
design), DS181 (Artix-7 data sheet), DS593 (JTAG cable), UG908 (Vivado programming), UG475 (packages
and pinout), Xilinx's ball list for the exact device (`xc7a50tftg256pkg.txt`) and the Micron
MT25QL128 datasheet. For the housekeeping devices: TI's TMP1075, ST's M24C02 (DS9398) and
Microchip's AT24CS02, the EEPROM considered first.

---

## 1. Bank voltages: the plan changed on reading the package

The first plan put 42 signals at 1.8 V on bank 34. **In the FTG256, bank 34 has only 20 I/O and no
clock-capable pin** (the symbol's ball names show it). So:

| Bank | VCCO | Carries | Why this bank |
|---|---|---|---|
| 14 | 3.3 V | AD9484 on **AERIS-10's own balls**, CLK_FPGA on AERIS's `FPGA_ADC_CLOCK` balls, AD9253, the two link pairs the FPGA receives, flash | The flash pins live in bank 14. LVDS_25 **inputs** are allowed in a 3.3 V bank with `DIFF_TERM` off (UG471 Table 1-44 note 1, DS181 Table 11 note 1), so each pair gets an external 100 Ω, as AERIS does |
| 15 | 3.3 V | AD9708 on **AERIS's own balls**, `DACR_CLK` on AERIS's `FPGA_DAC_CLOCK`, AD9767, Pmod, `SW_CTRL0-3`, `CLK_SEL`, XO I²C | The DACs, switches and XO are 3.3 V parts |
| 34 | 2.5 V | Only the three link pairs the FPGA **drives** | LVDS_25 outputs need VCCO = 2.5 V (UG471). The other 14 balls stay unused |
| 35 | 1.8 V | 8 × ADAR1000 control + SPI (35 lines), converter SPI, `HK_SCL/SDA`, `FPGA_IRQ`, `HK_ALERT` (ball K2) | AERIS drives the ADAR1000s at 1.8 V; the ADCs' SPI is 1.8 V; the carrier's lines are **1.8 V `[V]`**: I2C, reset and the interrupt input all sit on `PL_1V8` on the carrier (XTP682, INTERFACE_SPEC §4.3) |

The pin table is in `control_spec.py`. On import it **proves itself against the symbol's own ball
names**:

- every ball is in the bank it is listed under;
- every `_P` net is on a `P` ball, with its `_N` on the same pair;
- the five clocks are on MRCC/SRCC balls: AD9484 DCO, AD9253 DCO, CLK_FPGA, the link receive clock
  and the Pmod SPI clock;
- all 256 balls are accounted for.

**ADCR_DCO is wired inverted (12 November 2026).** N14 carries ADCR_DCO_N and P14 ADCR_DCO_P (the
`INVERTED` set in `control_spec.py`; the check above expects the swap). The AD9484 has DCO's P pin
west of N, so a pair from the FPGA arrived with its legs crossed and had to go round the chip
(51 mm against 39). **The gateware must invert the clock:** `IS_CLK_INVERTED` on the ISERDESE2
(or `IS_C_INVERTED` on an IDDR), or capture on the opposite edge.

**Pin swap for routing (7 October 2026).** Bank 35 as a whole, and the AD9767 (DACS) lines within
bank 15, were re-assigned at layout: each net to the ball nearest its far end, by a minimum
total-length matching, so no two lines of either bus cross. The AERIS-10 balls (DACR,
ADCR, CLK_FPGA), every pair and every clock-capable ball kept their place. The new tables are an
override block in `control_spec.py`, after the original ones, and the self-check above runs on
them. Nothing in bank 35 or among the DACS lines needs a particular ball, so the swap only changes
the FPGA's constraint file.

---

## 2. Decisions this sheet makes, for your approval

| Decision | Evidence | Alternative |
|---|---|---|
| **The bank allocation of §1** | FTG256 ball names; UG471 on LVDS in other-voltage banks | A larger package (CSG324) with more 1.8 V I/O |
| **CLK_FPGA through a matched attenuator:** 24.9 Ω series plus 24.9 Ω to +1V2 on each leg | The ADCLK948 swings 610–960 mV (its Table 1, V<sub>O</sub>). LVDS_25 accepts at most 600 mV (DS181 Table 11). The pad halves that to 305–480 mV and still looks like 50 Ω to the line. +1V2 sets V<sub>ICM</sub>, which must be 0.3–1.5 V | Plain 100 Ω, as for the ADCs, which would overdrive the input |
| **FPGA_PROG_B through a 74LVC1G07** open-drain buffer powered at 1.8 V | A 2N7002 level shifter with its gate at 1.8 V is not guaranteed to turn on: V<sub>GS(th)</sub> is up to 2.5 V. The LVC1G07 has V<sub>IH</sub> = 0.65 × V<sub>CC</sub> at 1.8 V and its output tolerates 5.5 V (SN74LVC1G07 datasheet) | BSS138 shifter |
| **Configuration exactly as UG470 Figure 2-14** (master SPI x4) | M[2:0] = 001 through 1 kΩ; INIT_B and PROGRAM_B 4.7 kΩ; FCS_B 2.4 kΩ; W and HOLD 4.7 kΩ; CFGBVS to VCCO_0; push button on PROGRAM_B (Table 2-4) | — |
| **PUDC_B high through 1 kΩ** (I/O pull-ups off while configuring) | Table 2-4: *"tied either directly, or via a ≤ 1 kΩ"*. **AERIS uses 4.7 kΩ, outside that limit.** High is AERIS's choice; AERIS's own pull resistors hold the ADAR lines meanwhile | PUDC_B low: pull-ups on, which would raise LOAD and TR during configuration |
| **Flash MT25QL128ABA1ESE** (128 Mb, SO8W) | In Vivado's configuration-memory list (UG908, `mt25ql128`). The Winbond W25Q128 that KiCad ships is not. AERIS uses a 1 Gb BGA; 128 Mb holds a 50T bitstream (about 17 Mb) several times over | AERIS's MT25QL01G |
| **XADC on its on-chip reference:** VP, VN, VREFP, VREFN to GNDADC; VCCADC and GNDADC through ferrites (UG480 Figure 1-2, right) | UG480 Table 1-1: *"This pin should always be connected to GNDADC if an external reference is not supplied."* **AERIS ties VREFP to +1V0: that is wrong**, confirmed now that UG480 is on disk | An external 1.25 V reference |
| **VCCBATT to GND** | DS181: *"If battery is not used, connect VCCBATT to either ground or VCCAUX"*; UG470 Figure 2-14 grounds it | — |
| **DXP/DXN to GND** | UG475 Table 1-12: *"When not used, tie to GND."* The XADC's own sensor reads the die temperature | An external thermal-diode monitor |
| **JTAG on the Xilinx 2 × 7, 2 mm header** | DS593 Figure 14: 2 VREF, 4 TMS, 6 TCK, 8 TDO, 10 TDI; 3–11 GND, 13 PGND; 1, 12, 14 unused. Direct to the FPGA, as UG470 Figure 2-14 | Digilent 1 × 6 |
| **The AERIS ribbon: an IDC 2 × 20.** Pins 1–32 carry CS, TX_LOAD, RX_LOAD and TR for each of the 8 ADAR1000s. Pins 33/35/37 carry the SPI (SCLK, SDIO, SDO), each next to a ground. 34, 36 and 38–40 are grounds | ARCHITECTURE §7.2, sized for 8 chips. **Only five grounds for 35 lines**: acceptable for static control lines and a few-MHz SPI, with `SLEW = SLOW` in the constraints | A 2 × 25 with a ground beside every signal |
| **No pull resistors on the ADAR lines here** | AERIS keeps them next to the chips (4.7 kΩ on LOAD, 22.1 kΩ on TR and SPI, 22.1 kΩ up on CS). **The AERIS end of this cable does not exist yet**: its Main Board has no such connector, because its own U42 drives these nets | Duplicate them here |
| **Pmod pinout** | Pmod pins 1–4 CS, MOSI, MISO, SCLK (INTERFACE_SPEC §4.2); 7 BEAM_STROBE, 8 PPS_SYNC, 9–10 spare. GND 5/11. The KV260's 3.3 V (6/12) is left open: the adapter takes no power from the Pmod. On an odd/even header Pmod pin *k* is pad 2*k*−1 and pin *k*+6 is pad 2*k* | — |
| **HK I²C pull-ups 10 kΩ to 1.8 V**, fitted (4.7 kΩ until 2 October) | The carrier already has 2.21 kΩ to `PL_1V8` (XTP682 sheet 8). With both, the bus sees 1.81 kΩ: 1.0 mA at 1.8 V. That is what the EEPROM must sink, and the M24C02 is specified at 0.7 mA for 0.2 V at 1.8 V (DS9398 Table 14); scaling that up gives about 0.3 V, under the 0.54 V (0.3 × V<sub>DD</sub>) a 1.8 V input reads as low. 4.7 kΩ would ask 1.2 mA. Kept so the bus idles high on the bench without a carrier: 10 kΩ alone is fast enough for 100 kHz | 4.7 kΩ; or none, relying on the carrier |
| **FPGA_IRQ on J8 pin 15, active high, 47 kΩ pull-down (R1133)** | Pin 15 is the only single-ended pin that goes **into** the SOM, through the carrier's SN74AVC4T245 at 1.8 V. The pin first allocated, 32, is the carrier's 48 MHz camera clock (INTERFACE_SPEC §4.3). With PUDC_B high the FPGA's pin floats until configured; the pull-down holds the translator's input at "no interrupt" | Pin 32, which would fight the carrier's clock |
| **The HK bus's addresses are free** | The carrier's TCA9546A channel 1 reaches only J8: `IAS1_I2C_SCK/SDA` appear on XTP682 sheets 8 (the switch) and 13 (J8) and nowhere else. So 0x48 and 0x50 are this board's | — |
| **Temperature sensor TMP1075DR** (U1104), SOIC-8, I²C **0x48** | 1.7–5.5 V, ±1 °C max from −40 to 110 °C, LM75-compatible registers (TMP1075 datasheet). A2..A0 to GND gives 0x48 (its Table 7-2). The FPGA's XADC already reads the die; this one reads the board | VSSOP-8 (DGK): its 0.65 mm pitch does not fit the Power class's 0.2 mm clearance, with V+ next to A0 (GND) |
| **`HK_ALERT`: the sensor's ALERT to the FPGA**, ball K2 (a free bank-35 ball; H3 until the pin swap below), 10 kΩ pull-up (R1134) | ALERT is open-drain (Table 5-1). The FPGA can fold it into `FPGA_IRQ`, the one line into the SOM | Leave ALERT unconnected and poll |
| **Board ID EEPROM M24C02-FMN6TP** (U1105), SOIC-8, I²C **0x50** | The -F grade runs from 1.7 V. Its output low is specified at **1.8 V: 0.2 V at 0.7 mA** (DS9398 Table 14). It holds the board's revision and serial number, written once | **AT24CS02**, which has a factory-programmed 128-bit serial number. Rejected: at 1.7 V its output low is specified for **0.15 mA** only (its Table 4-2), and this bus needs about 1 mA |
| **Write protection: WC pulled up (R1135, 10 kΩ), solder jumper JP1101 to GND** | WC high disables writes; floating, the M24C02 enables them (DS9398 §2.4). Closed, the jumper allows writing. JP1101 is copper only: not in the BOM or the placement file | WC to GND: writable from Linux at any time |

---

## 3. Every value, and where it comes from

| Part | Value | Source |
|---|---|---|
| R1101–R1114 | 100 Ω across each received pair | UG471: no DIFF_TERM in a 3.3 V bank. AERIS R2–R12 for the AD9484 |
| RN1101–RN1107 | 4 × 22 Ω arrays, 27 lines, 1 spare | AERIS R23–R30 on the AD9708 |
| R1115–R1118, C1101 | 24.9 Ω × 4, 100 nF at the bias | §2 |
| R1119–R1128 | see §2 | UG470 Table 2-4, Figure 2-14; CCLK 22 Ω as AERIS (Figure 2-14 note 4: termination may be needed) |
| R1129 | 10 kΩ to +1V8_D | Holds FPGA_PROG_B high while the Kria is not driving it (the carrier also has 10 kΩ, R208) |
| R1131, R1132 | 10 kΩ to +1V8_D | HK I²C pull-ups, §2 |
| U1104, C1182, R1134 | TMP1075DR, 100 nF, 10 kΩ | §2. TMP1075 §8.3: 0.01 µF typical bypass, more for a noisy supply. R1134 is the ALERT pull-up |
| U1105, C1183, R1135, JP1101 | M24C02-FMN6TP, 100 nF, 10 kΩ, solder jumper | §2 |
| R1133 | 47 kΩ to GND | FPGA_IRQ pull-down, §2. Stiff enough for a CMOS input: even 10 µA of leakage would leave it under 0.5 V |
| Q1101, D1101, R1130 | 2N7002, green LED, 330 Ω | DONE lamp, about 4 mA |
| Decoupling C1110–C1171 | FTG256/XC7A50T row of **UG483 Table 2-2**; types from Table 2-5 | VCCINT 330 µF + 3 × 4.7 µF + 5 × 0.47 µF; VCCBRAM 100 µF + 0.47 µF; VCCAUX 47 µF + 2 × 4.7 µF + 3 × 0.47 µF; VCCO_0 47 µF; per other bank 2 × 4.7 µF + 4 × 0.47 µF, and one 47 µF per group of banks at one voltage |
| FB1101, FB1102, C1175, C1176 | ferrites, 100 nF, 470 nF | UG480 Figure 1-2 |

---

## 4. Power sequencing — the open point from POWER, now answered

DS181 (*Power-On/Off Power Supply Sequencing*):

- The order VCCINT → VCCBRAM → VCCAUX → VCCO is **recommended**, *"to achieve minimum current draw
  and ensure that the I/Os are 3-stated at power-on"*. It is not a requirement.
- The **one hard limit** is on 3.3 V banks: VCCO − VCCAUX must not exceed 2.625 V for longer than
  T<sub>VCCO2VCCAUX</sub>, which is **300 ms per power cycle at T<sub>J</sub> = 125 °C** (800 ms at
  85 °C).
- Here VCCAUX (+1V8_D) is an LDO fed from +3V3_D. So that window only lasts while the LDO
  soft-starts (10 nF on NR/SS): milliseconds, not hundreds.
- The power-on currents of DS181 Table 6 (ICCINTQ + 120 mA, and so on) are far inside the 2 A the
  regulators give.

**The POWER sheet's "no sequencing" is therefore acceptable.** What is lost is the minimum inrush
current and tri-stated I/Os during the ramp. PUDC_B high keeps the I/Os floating anyway.

---

## 5. How the drawing was verified

| Check | Result |
|---|---|
| `control_spec.py` self-check: every ball against the symbol (bank, pair, clock capability, all 256 covered) | passes on import |
| The KiCad symbol against **Xilinx's own ball list** (`xc7a50tftg256pkg.txt`), all 256 balls by name | **identical**. Now part of the self-check, which fails if they ever differ (mutation-tested) |
| `_work/check_sheet.py control`: 184 nets exact, 47 no-connects alone, every pin of the 108 parts accounted for | **PASS** |
| KiCad ERC | 7 warnings on this sheet, all `pin_to_pin`. KiCad's symbol types CFGBVS, VP, VN, VREFP, VREFN, DXP and DXN as bidirectional, and here they are tied to power nets on purpose (§2). Design total: 660 (was 672) |
| Pin tables | New project symbol MT25QL128ABA1ESE from the Micron datasheet Figure 6, cross-checked against KiCad's MT25QU (same family): agrees apart from pin 7's name (HOLD# vs RESET# variant) and the W-PDFN's exposed pad. SN74LVC1G07 pinout checked against TI's Pin Functions table (DBV) |

The generator needed **multi-unit symbols**: `_work/schgen.py` now reads which unit each pin belongs
to and places a unit by number. The sheets already drawn regenerate byte-identical.

For the housekeeping devices it learned two more things (2 October): **derived symbols** (KiCad's
`extends`, as M24C02-FMN is of M24C01-FMN) are flattened the way KiCad embeds them, and a symbol the
library keeps out of the BOM (the solder jumper) stays out of it. DRC checks that the footprint
agrees.

---

## 6. How to review this sheet

About 50 minutes.

1. **§1's bank allocation**, and the pin table in `control_spec.py` against AERIS-10's U42 for
   the AD9484 and AD9708 balls (`py _work/aeris_reference_circuit.py U42`).
2. **§2's decisions**: the CLK_FPGA pad, the ADAR ribbon pinout and the missing AERIS end above all.
   Then the housekeeping block: the EEPROM chosen for its 1.8 V drive, and the HK pull-ups now 10 kΩ.
3. **The configuration block against UG470 Figure 2-14**, value by value.

```
py _work/sheets/control_spec.py     # the pin table's self-check
py _work/check_sheet.py control
```
