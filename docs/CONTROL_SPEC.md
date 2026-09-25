# CONTROL sheet — specification and review guide

*25 September 2026 · `rev03/CONTROL.kicad_sch` (A1) · drawn by `_work/sheets/control.py` from the
connection list in `_work/sheets/control_spec.py`*

The front-end FPGA, **U1101 XC7A50T-2FTG256I** (AERIS-10's own part), with everything it needs to
boot and everything it talks to that is not on another sheet:

- the configuration flash, JTAG, the reset and DONE circuits;
- the Pmod cable from the KV260;
- the ribbon to AERIS-10's ADAR1000 beamformers;
- the LVDS terminations of every pair the FPGA receives, and the 22 Ω series resistors on every DAC
  line.

The FPGA is drawn as its four KiCad units, and it reads by net name: every ball has a short stub and
a name. A **hierarchical label** at a ball means the net leaves the sheet; a **plain label** means
it stays on it. The circuits sit nearby as small wired blocks.

The Xilinx documents behind every value are now on disk, fetched through the Internet Archive by
`_work/fetch_datasheets.py`: UG470 (configuration), UG471 (SelectIO), UG480 (XADC), UG483 (PCB
design), DS181 (Artix-7 data sheet), DS593 (JTAG cable), UG908 (Vivado programming) and the Micron
MT25QL128 datasheet.

---

## 1. Bank voltages: the plan changed on reading the package

The first plan put 42 signals at 1.8 V on bank 34. **In the FTG256, bank 34 has only 20 I/O and no
clock-capable pin** (the symbol's ball names show it). So:

| Bank | VCCO | Carries | Why this bank |
|---|---|---|---|
| 14 | 3.3 V | AD9484 on **AERIS-10's own balls**, CLK_FPGA on AERIS's `FPGA_ADC_CLOCK` balls, AD9253, the two link pairs the FPGA receives, flash | The flash pins live in bank 14. LVDS_25 **inputs** are allowed in a 3.3 V bank with `DIFF_TERM` off (UG471 Table 1-44 note 1, DS181 Table 11 note 1), so each pair gets an external 100 Ω, as AERIS does |
| 15 | 3.3 V | AD9708 on **AERIS's own balls**, `DACR_CLK` on AERIS's `FPGA_DAC_CLOCK`, AD9767, Pmod, `SW_CTRL0-3`, `CLK_SEL`, XO I²C | The DACs, switches and XO are 3.3 V parts |
| 34 | 2.5 V | Only the three link pairs the FPGA **drives** | LVDS_25 outputs need VCCO = 2.5 V (UG471). The other 14 balls stay unused |
| 35 | 1.8 V | 8 × ADAR1000 control + SPI (35 lines), converter SPI, `HK_SCL/SDA`, `FPGA_IRQ` | AERIS drives the ADAR1000s at 1.8 V; the ADCs' SPI is 1.8 V; the carrier's lines are taken as 1.8 V `[E]`: J8 carries `VCC1V8`, but the carrier schematic (XTP682) is not on disk to confirm the level of `I2C_SCL/SDA`, `PWDN` and `GPIO2` |

The pin table is in `control_spec.py`. On import it **proves itself against the symbol's own ball
names**:

- every ball is in the bank it is listed under;
- every `_P` net is on a `P` ball, with its `_N` on the same pair;
- the five clocks are on MRCC/SRCC balls: AD9484 DCO, AD9253 DCO, CLK_FPGA, the link receive clock
  and the Pmod SPI clock;
- all 256 balls are accounted for.

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
| **DXP/DXN to GND** | As AERIS. **Not verified**: the package guide UG475 is not on disk | Left open |
| **JTAG on the Xilinx 2 × 7, 2 mm header** | DS593 Figure 14: 2 VREF, 4 TMS, 6 TCK, 8 TDO, 10 TDI; 3–11 GND, 13 PGND; 1, 12, 14 unused. Direct to the FPGA, as UG470 Figure 2-14 | Digilent 1 × 6 |
| **The AERIS ribbon: an IDC 2 × 20.** Pins 1–32 carry CS, TX_LOAD, RX_LOAD and TR for each of the 8 ADAR1000s. Pins 33/35/37 carry the SPI (SCLK, SDIO, SDO), each next to a ground. 34, 36 and 38–40 are grounds | ARCHITECTURE §7.2, sized for 8 chips. **Only five grounds for 35 lines**: acceptable for static control lines and a few-MHz SPI, with `SLEW = SLOW` in the constraints | A 2 × 25 with a ground beside every signal |
| **No pull resistors on the ADAR lines here** | AERIS keeps them next to the chips (4.7 kΩ on LOAD, 22.1 kΩ on TR and SPI, 22.1 kΩ up on CS). **The AERIS end of this cable does not exist yet**: its Main Board has no such connector, because its own U42 drives these nets | Duplicate them here |
| **Pmod pinout** | Pmod pins 1–4 CS, MOSI, MISO, SCLK (INTERFACE_SPEC §4.2); 7 BEAM_STROBE, 8 PPS_SYNC, 9–10 spare. GND 5/11. The KV260's 3.3 V (6/12) is left open: the adapter takes no power from the Pmod. On an odd/even header Pmod pin *k* is pad 2*k*−1 and pin *k*+6 is pad 2*k* | — |
| **HK I²C pull-ups 4.7 kΩ to 1.8 V**, fitted | The carrier's own pull-ups are not known. Remove them if it has its own | — |
| **HK devices (temperature sensor, ID EEPROM) not drawn** | Deferred: they sit on the HK bus, which reaches the FPGA, and can be added without touching anything else | — |

---

## 3. Every value, and where it comes from

| Part | Value | Source |
|---|---|---|
| R1101–R1114 | 100 Ω across each received pair | UG471: no DIFF_TERM in a 3.3 V bank. AERIS R2–R12 for the AD9484 |
| RN1101–RN1107 | 4 × 22 Ω arrays, 27 lines, 1 spare | AERIS R23–R30 on the AD9708 |
| R1115–R1118, C1101 | 24.9 Ω × 4, 100 nF at the bias | §2 |
| R1119–R1128 | see §2 | UG470 Table 2-4, Figure 2-14; CCLK 22 Ω as AERIS (Figure 2-14 note 4: termination may be needed) |
| R1129 | 10 kΩ to +1V8_D | Holds FPGA_PROG_B high while the Kria is not driving it |
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
| `_work/check_sheet.py control`: 182 nets exact, 48 no-connects alone, every pin of the 100 parts accounted for | **PASS** |
| KiCad ERC | 7 warnings on this sheet, all `pin_to_pin`. KiCad's symbol types CFGBVS, VP, VN, VREFP, VREFN, DXP and DXN as bidirectional, and here they are tied to power nets on purpose (§2). Design total: 660 (was 672) |
| Pin tables | New project symbol MT25QL128ABA1ESE from the Micron datasheet Figure 6, cross-checked against KiCad's MT25QU (same family): agrees apart from pin 7's name (HOLD# vs RESET# variant) and the W-PDFN's exposed pad. SN74LVC1G07 pinout checked against TI's Pin Functions table (DBV) |

The generator needed **multi-unit symbols**: `_work/schgen.py` now reads which unit each pin belongs
to and places a unit by number. The sheets already drawn regenerate byte-identical.

---

## 6. How to review this sheet

About 45 minutes.

1. **§1's bank allocation**, and the pin table in `control_spec.py` against AERIS-10's U42 for
   the AD9484 and AD9708 balls (`py _work/aeris_reference_circuit.py U42`).
2. **§2's decisions**: the CLK_FPGA pad, the ADAR ribbon pinout and the missing AERIS end above all.
3. **The configuration block against UG470 Figure 2-14**, value by value.

```
py _work/sheets/control_spec.py     # the pin table's self-check
py _work/check_sheet.py control
```
