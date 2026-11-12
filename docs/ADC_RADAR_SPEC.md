# ADC_RADAR sheet — specification and review guide

*24 September 2026 · `rev03/ADC_RADAR.kicad_sch` · drawn by `_work/sheets/adc_radar.py` from the
connection list in `_work/sheets/adc_radar_spec.py`*

The radar receive path: the 120 MHz IF from AERIS-10 into the AD9484, through two AD8352 drivers.
It is AERIS-10's own Main Board circuit (ARCHITECTURE §7.1: *"replicated on the adapter board"*),
rebuilt from the datasheets and checked part by part against AERIS's schematic
(`_work/aeris_reference_circuit.py U1 U4 U8`).

```
IF_RX_B ──► U502 AD8352 ──► U503 AD8352 ──► U501 AD9484 ──► 10 LVDS pairs to the FPGA
single-ended   single-ended in,  differential,    8 bits,
50 ohm         15 dB             10 dB            400 / 500 MSPS
```

---

## 1. What drawing it changed

### 1.1 CONVERTERS became four sheets

The CONVERTERS sheet would have held about 200 parts, more than one review can check properly. It
is now `ADC_RADAR`, `ADC_SDR`, `DAC_RADAR` and `DAC_SDR`, each about the size of CLOCK. The split is
clean because the interfaces separate: the ADCs have the SPI bus and the LVPECL clocks, and the DACs
have parallel CMOS buses. Done by `_work/rev03_split_converters.py`; `hier_label_mismatch` stays at
0. The root page went from A3 to A2 to make room for the four blocks.

### 1.2 Interface changes

| Signal | Change | Why |
|---|---|---|
| `IF_RX_A_P/N` … `IF_TX_B_P/N` | **became `IF_RX_A`, `IF_RX_B`, `IF_TX_A`, `IF_TX_B`, single-ended 50 Ω** | What carries them is single-ended: the M3SWA2 routing switches (SPDT, one RF path each) and the SMAs. Eight differential lines could never have gone through four SPDTs. The AD8352 takes a single-ended input by itself (its datasheet, Figure 26), so the receive side needs no balun; the DACs will drive one |
| `ADCR_D_P[7..0]`, `ADCR_D_N[7..0]` | **became `ADCR_D0_P` … `ADCR_D7_N`**, one label per line | As the `ADCS_*` lines already were. The drawn sheet then has no bus, and `check_sheet.py` checks every line by name |

### 1.3 Decisions this sheet makes, for your approval

| Decision | Evidence | Alternative |
|---|---|---|
| **Two AD8352s in cascade, 15 + 10 dB = 25 dB** | AERIS-10 does exactly this: U8 with RG 56 Ω (15 dB), then U4 with RG 115 Ω (10 dB) | One stage (fewer parts, 37 mA less) if the IF arriving here is stronger than at AERIS's own ADC. Changing it is a resistor value; removing a stage is a redraw |
| **The first stage takes the single-ended values** (Table 7: RG 68 Ω, CD 0.6 pF), not AERIS's differential ones (Table 5: RG 56 Ω) | AERIS feeds its first stage differentially from the mixer; this board gets the IF through a single-ended switch | — |
| **The AD8352s run at 5 V**, not 3.3 V | The datasheet characterises the part at 5 V only (Table 1); 3 V is merely inside the allowed range. AERIS runs its two at 5 V. The power budget moved them from `+3V3_A` to `+5V0` | 3.3 V saves ~0.1 W but runs on uncharacterised distortion |
| **ENB tied to VCC, PWDN tied to ground** | The AD8352 evaluation board ties ENB to the supply (R10). The AD9484 powers down through SPI (register 0x08) as well as the pin | AERIS drives both from the FPGA (`EN_OPAMP_IF_*`, `ADC_PWRD`). Three more FPGA lines to save ~0.9 W when the radar is idle. Say if you want them |

### 1.4 Two requirements this sheet puts on CONTROL

- **`CONV_SPI_*` must be 1.8 V signals.** The AD9484's logic pins have an absolute maximum of
  DRVDD + 0.2 V = 2.0 V (datasheet, Absolute Maximum Ratings). A 3.3 V FPGA bank would damage it.
  AERIS scales its PWDN line with a 830 Ω / 1 kΩ divider for the same reason. The FPGA drives the
  SPI from a 1.8 V bank, or through a translator.
- **The LVDS pairs are terminated at the receiver, 100 Ω each** (AD9484 p.16: *"as close to the
  receiver as possible"*): in the FPGA (`DIFF_TERM`) or as resistors on CONTROL. AERIS uses
  resistors (R2–R12).

---

## 2. Parts

| Ref | Part | Footprint | Note |
|---|---|---|---|
| U501 | AD9484BCPZ-500 | **custom** | CP-56-5 has a **5.10 mm** exposed pad (Figure 40). KiCad's 8×8 mm 56-pin parts have 6.6 mm or 5.1×4.96 mm. Draw it at layout, like the ADCLK948's |
| U502, U503 | AD8352ACPZ | `Package_CSP:LFCSP-16-1EP_3x3mm_P0.5mm_EP1.6x1.6mm` | CP-16-22: 1.60 mm pad, matches |
| FB501–FB503 + 51 passives | see `adc_radar_spec.py` | 0402, bulk 0805, ferrites 0603 | Each with its source |

The two datasheets are in the AERIS-10 repository, not in `_work/datasheets/`:
The PLFM_RADAR repository's `7_Components Datasheets and Application notes/AD9484/` holds `AD9484.pdf`
(Rev. A), `ad8352.pdf` (Rev. C) and the AD9484 evaluation board schematic.

---

## 3. Every value, and where it comes from

| Item | Value | Source |
|---|---|---|
| Input termination R501 | 64.9 Ω | AD8352 Figure 26: 65 Ω |
| RN R502, VIP to RGN | 200 Ω | AD8352 Figure 26 and text: *"an external resistor (RN) of 200 Ω is added between VIP and RGN"* to balance the outputs |
| VIN to ground R503, through C502 | 24.9 Ω | AD8352 Figure 26: 25 Ω |
| Stage 1 RG / RD / CD | 68 Ω / 4.3 kΩ / 0.6 pF | AD8352 **Table 7**, 15 dB, single-ended, 200 Ω load |
| Stage 2 RG / RD / CD | 115 Ω / 4.3 kΩ / 0.2 pF | AD8352 **Table 5**, 10 dB, differential, 200 Ω load. Same as AERIS R14, R15, C43 |
| VCM decoupling C504, C513 | 100 nF | AD8352 Table 4: *"typically decoupled to ground with a 0.1 µF capacitor"* |
| Coupling capacitors C501, C502, C507, C508, C510, C511, C516, C517 | 100 nF | AD8352 Figure 26, AD9484 Figure 30 |
| Load legs R506/R507, R510/R511 | 200 Ω | AD9484 Figure 30 |
| Centre-tap capacitors C509, C518 | 100 nF | AD9484 Figure 30 |
| Series R512, R513 | 24 Ω | AD9484 Figure 30 shows *R* without a value; 24 Ω is AERIS's (R1, R13) and the AD8352 datasheet's (p.14: *"the output 24 Ω resistors provide isolation"*) |
| Shunt C519 across VIN± | 2.7 pF | AD9484 Figure 30 shows *C*, *"dependent on the input frequency"*; 2.7 pF is AERIS's (C3), at the same 120 MHz IF |
| Clock termination R514 | 100 Ω | ADCLK948 Figure 17 and AD9484 Figure 31: 100 Ω across the pair at the receiver. AERIS R173 |
| VREF R515 | 20 kΩ to ground | AD9484 p.17: internal reference = *"pin is connected to 20 kΩ to ground"*. AERIS R38 |
| AVDD, DRVDD decoupling | 11 + 3 × 100 nF, one per pin; 10 µF per rail | AD9484 evaluation board: C320–C333 (AVDD, 11), C323/C327/C328 (DRVDD, 3), C314/C315 |
| AD8352 decoupling | 2 × 100 nF per device, 10 µF shared | AD8352 evaluation board: C6, C7, C1 |

**Judgement calls**, not taken from a datasheet:

| Item | Value | Reasoning |
|---|---|---|
| FB501, the drivers' ferrite | 600 Ω at 100 MHz, ≥ 0.5 A | Isolates the RF drivers from the `+5V0` buck. 78 mA flows through it |
| FB502, FB503, the ADC's ferrites | 220 Ω at 100 MHz, ≥ 1 A, DCR ≤ 0.1 Ω | The evaluation board has a ferrite per rail (E302, E303, *"50 ohms"*) without a part number. At 300 mA and 0.1 Ω, AVDD drops 30 mV and stays inside 1.7–1.9 V. Since 12 Nov +1V8_A starts at 1.85 V, to cover the copper's drop on the way as well (SIGNAL_INTEGRITY §9.1) |
| CML joined to the centre tap | as Figure 30 | **AERIS leaves CML open** and only decouples the centre tap. CML is an output that the SPI enables; while disabled it does nothing, and enabled it biases the inputs where the ADC wants them. Following the datasheet costs nothing |
| Load tables for 200 Ω | Tables 5 and 7 | The stages actually see about 300–350 Ω (400 Ω of load legs in parallel with the next input). The datasheet says to interpolate between its 200 Ω and 1 kΩ tables; AERIS uses the 200 Ω values on the same circuit |

**Signal level**, for orientation: the AD9484's full scale is 1.5 V p-p differential. With 25 dB of
gain that is about 84 mV p-p at `IF_RX_B`, **roughly −17 dBm** into 50 Ω. That ignores the small
losses in the coupling and the 24 Ω/2.7 pF network, so it is an approximation.

---

## 4. How the drawing was verified

| Check | Result |
|---|---|
| `_work/check_sheet.py adc_radar`: all 61 specified nets exist with **exactly** their pins; interface nets carry their labels; power nets their names; the 9 DNC pins are alone; all 199 pins of the 57 parts accounted for; no part missing or extra | **PASS** |
| The same check with the wire from RN to the RGN line deleted on purpose | Fails, naming the pins: `S1_RGN: not connected: ['R504.1', 'U502.3']` |
| KiCad ERC on the sheet | 3 × `power_pin_not_driven` (`+5V0`, `+1V8_A`, `+1V8_D`, until POWER exists); 2 × `pin_not_driven` (SCLK and CSB, until CONTROL drives them); 23 × `isolated_pin_label` on the outputs and SPI, until the root is wired |
| Pin tables | AD9484 and AD8352 both cross-checked against a second source (`_work/crosscheck_pinouts.py`: no conflicts). Their symbols were only **rearranged** for this sheet, not renumbered |

**Why the pin order of the AD8352 symbol looks odd.** Down the left it reads VIP, RGN, RGP, RDP,
RDN, VIN, which is not the chip's order. Each pair that takes a part is exactly one resistor length
(7.62 mm) apart, so RN, RG, RD and CD each sit straight across their two pins, and nothing crosses.
ENB sits on top next to VCC, which is what it is tied to. The pin **numbers** are unchanged: check
them, not their position.

**The ERC total moved from 500 to 672**, and not because of this sheet. After the split, KiCad
started reporting 144 sheet pins in the root as not connected, including CLOCK's and IAS_LINK's,
which it had not reported before. They are genuinely unconnected, because the root gets wired last.
Why KiCad did not count them before is **not established**.

---

## 5. How to review this sheet

Open the project in KiCad and go into ADC_RADAR. Keep this document and the two datasheets (§2)
next to it. About 40 minutes.

1. **The decisions in §1.3.** The IF single-ended, the 25 dB split over two stages, 5 V on the
   drivers, and dropping the FPGA's control of ENB and PWDN. These are yours to accept.
2. **U501's pins against AD9484 Table 7** (p.8): VIN± 35/36, CML 40, VREF 31, CLK± 44/45, SDIO/SCLK/CSB
   25/26/27, PWDN 29, and that each output's true pin (`+`) goes to the `_P` label.
3. **Stage 1 against AD8352 Figure 26** (p.12) **and Table 7** (p.13): RN from VIP to **RGN** (not
   RGP), 65 Ω termination on the source side of C501, 25 Ω on VIN.
4. **The interstage and output networks against AD9484 Figure 30** (p.15). Stage 2 against AD8352
   Table 5 (p.11).
5. **The judgement calls in §3.**
6. **Anything that reads badly.** Fix it directly in KiCad. From then on the `.kicad_sch` is the
   source, and the generator is not re-run over hand edits.

To confirm the wiring after you've touched it:

```
py _work/check_sheet.py adc_radar
```
