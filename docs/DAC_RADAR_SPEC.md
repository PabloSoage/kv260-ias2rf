# DAC_RADAR sheet — specification and review guide

*24 September 2026 · `rev03/DAC_RADAR.kicad_sch` · drawn by `_work/sheets/dac_radar.py` from the
connection list in `_work/sheets/dac_radar_spec.py`*

The radar chirp DAC: AERIS-10's AD9708 and its reconstruction filter, with a balun added so the
output is single-ended 50 Ω like everything the routing switches carry.

```
DACR_D0..7, DACR_CLK ──► U701 AD9708 ──► 50 Ω loads ──► LC filter (AERIS-10) ──► T701 balun ──► IF_TX_B
(FPGA, 3.3 V CMOS)       8 bits, 20 mA                  differential, 5 poles     2:1 Z         50 Ω
```

---

## 1. Decisions this sheet makes, for your approval

| Decision | Evidence | Alternative |
|---|---|---|
| **Internal 1.2 V reference, not AERIS's arrangement** | AERIS ties REFLO to AVDD, which disables the internal reference, and REFIO to +3.3 V. That makes 3.3 V the reference input, but the datasheet allows **0.1–1.25 V** there (Table 1, *Reference Input, Input Compliance Range*). Here REFLO goes to ACOM and REFIO gets its 0.1 µF, as the pin description says. **Worth telling the AERIS-10 author**: it may explain a lower-than-expected full scale on their board | — |
| **20 mA full scale** (RSET = 1.91 kΩ) | I_OUTFS = 32 × V_REFIO / RSET (Table 1 note 2). 20 mA is the maximum and gives the most output. Across 49.9 Ω that's 1.0 V, inside the 1.25 V output compliance | A larger RSET for less output: 3.83 kΩ gives 10 mA |
| **A 5th-order Butterworth for 100 Ω, −3 dB at 50 MHz (13 Nov), same topology and footprints as AERIS-10's filter** | Here the filter sits between 100 Ω differential at both ends: R702 + R703 at the DAC, and the 50 Ω line seen through T701's ratio of 2. AERIS-10's values (fitted as 110 nH / 110 pF) sag **2.0 dB** between 10 and 45 MHz in that termination (−3 dB at 70 MHz, −24 dB at 100 MHz). An independent review found this (docs/RF_REVIEW_GEMINI.md M1) and the ABCD model confirms it. New values, all E24, same parts and topology: C707/C708 22 pF to ground (11 pF differential) plus **C709 8.2 pF**, **L701–L704 270 nH** (Murata LQW18ANR27G, ±2 %), **C710 62 pF**, **C711 20 pF**. Response: flat to 30 MHz, −0.4 dB at 40, −3.4 dB at 50, −31 dB at 100, −40 dB at 125 MHz (the image of a 0–40 MHz tone clocked at 125 MSPS). The inductors' 3.4 Ω DCR, two per leg, costs about 0.6 dB flat | AERIS's values: wider passband (to ~65 MHz) but with the sag |
| **A balun after the filter (T701)** | The routing switch and the SMAs are single-ended; AERIS fed its mixer differentially | Keep the output differential and route it as a pair. That breaks the single-ended interface of §1.2 of ADC_RADAR_SPEC |
| **Series resistors on the data lines sit on CONTROL**, not here | A series resistor terminates the line at its *source* (the FPGA). AERIS uses 22 Ω (R23–R30); the datasheet suggests 20–100 Ω (p.9) | — |
| **SLEEP tied low** | It has an internal pull-down (pin 15); AERIS drives it from the FPGA | One more FPGA line |

**T701 is a Mini-Circuits ADT2-1T+** (chosen at layout, 25 Sep; [LAYOUT.md](LAYOUT.md) §5). Its
datasheet gives an impedance ratio of 2 (secondary/primary), 50 Ω, 0.4–450 MHz. The 100 Ω
secondary (pins 6 and 4) takes the filter's differential output, the primary (3 to the line, 1 to
ground) drives the 50 Ω single-ended line. The centre tap (5) is unused. The symbol is new, from
the datasheet's Pin Connections table.

---

## 2. Every value, and where it comes from

| Item | Value | Source |
|---|---|---|
| COMP1 to AVDD, C701 | 100 nF | Pin 19: *"Add 0.1 µF to AVDD for optimum performance"* (AERIS C39) |
| COMP2 to ACOM, C706 | 100 nF | Pin 23: *"Decouple to ACOM with 0.1 µF"* (AERIS C38) |
| REFIO, C705 | 100 nF | Pin 17: *"Requires 0.1 µF capacitor to ACOM when internal reference activated"* |
| RSET, R701 | 1.91 kΩ 1 % | 32 × 1.20 V / 1.91 kΩ = 20.1 mA |
| Loads, R702/R703 | 49.9 Ω | AERIS R115, R116 (50 Ω) |
| Filter | 22 p (×2, to ground), 8.2 p, 270 nH, 62 p, 270 nH, 20 p | 100 Ω Butterworth, §1; topology from AERIS C308/C309, C127, L22/L25, C141, L26/L27, C59 (`_work/aeris_reference_circuit.py L26 L27 C141`) |
| AVDD decoupling | 10 µF + 100 nF | Figure 22 (bulk) and p.10 (*"as close to the chip as physically possible"*) |
| DVDD decoupling | 100 nF | p.10 |

**The symbol is new.** KiCad's `Video:AD9708AR` has the right numbers, but it leaves out the NC
pins and its layout forced crossings around the reference pins. The project symbol is transcribed
from the datasheet's pin table (Rev. B). It agrees with KiCad's on all 21 pins they share; the 7
NC pins are marked as settled in `_work/crosscheck_pinouts.py`. The footprint is the stock
`SOIC-28W_7.5x17.9mm`, which matches R-28 (body 17.70–18.10 × 7.40–7.60 mm).

---

## 3. How the drawing was verified

| Check | Result |
|---|---|
| `_work/check_sheet.py dac_radar`: 23 nets exact, 7 NC pins alone, every pin of the 20 parts accounted for | **PASS** |
| `_work/crosscheck_pinouts.py` | AD9708AR against KiCad's own symbol: 21 of 21 shared pins agree |
| KiCad ERC on the sheet | 9 × `pin_not_driven` (the 8 data inputs and the clock, until CONTROL drives them); 2 × `power_pin_not_driven` (`+3V3_A`, `+3V3_D`, until POWER exists) |

---

## 4. How to review this sheet

About 20 minutes, with `AD9708.pdf` from the AERIS-10 component folder.

1. **§1's decisions**, the reference above all. It is the one place this sheet departs from AERIS-10
   on purpose.
2. **U701's pins against the Pin Function Descriptions** (p.4).
3. **The filter against AERIS's schematic**, part by part, with the script above.
4. **T701**: the ADT2-1T+ pin mapping above, against its datasheet.

```
py _work/check_sheet.py dac_radar
```
